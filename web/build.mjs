#!/usr/bin/env node
// Builds the static site into web/dist. Zero dependencies (Node ≥ 20): partials, build-time variables, asset
// versioning, robots/sitemap, and checks that nothing unrendered or secret ends up in the output.
//
// Build-time variables (all public; they end up in the HTML). See web/.env.example and web/docs/deployment.md.
//   PUBLIC_SITE_URL            canonical origin (default: https://$VERCEL_PROJECT_PRODUCTION_URL, else none)
//   PUBLIC_API_BASE            API origin if it is NOT this site (default: same origin, recommended)
//   PUBLIC_OPERATOR_NAME       who runs the waitlist (privacy notice) — required for production builds
//   PUBLIC_CONTACT_EMAIL       privacy/data-request contact (privacy notice) — required for production builds
//   PUBLIC_DATABASE_PROVIDER   e.g. "Neon (AWS us-east-1)" (privacy notice)
//   PUBLIC_TURNSTILE_SITE_KEY  Cloudflare Turnstile site key (optional; pair with WAITLIST_TURNSTILE_SECRET)
//   PUBLIC_VERIFY_TTL_HOURS    shown in copy; defaults to WAITLIST_VERIFY_TTL_HOURS, else 48
//   PUBLIC_ALLOW_INDEXING      "true"/"false"; default: index only Vercel production builds
import { createHash } from 'node:crypto';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const WEB = dirname(fileURLToPath(import.meta.url));
const SRC = join(WEB, 'src');
const PUB = join(WEB, 'public');
const OUT = process.env.WEB_OUT_DIR ? resolve(process.env.WEB_OUT_DIR) : join(WEB, 'dist');
const env = process.env;
const warnings = [];

const fail = (msg) => { console.error(`build: ERROR: ${msg}`); process.exit(1); };
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');

function origin(name, value) {
  if (!value) return '';
  let u;
  try { u = new URL(value); } catch { fail(`${name} must be an origin like https://example.com`); }
  if (!['https:', 'http:'].includes(u.protocol) || (u.pathname !== '/' && u.pathname !== '') || u.search || u.hash) {
    fail(`${name} must be an origin like https://example.com (got ${value})`);
  }
  return u.origin;
}

// ------------------------------------------------------------ configuration
const vercelEnv = env.VERCEL_ENV || '';
const production = vercelEnv === 'production';
const siteUrl = origin('PUBLIC_SITE_URL', env.PUBLIC_SITE_URL || (env.VERCEL_PROJECT_PRODUCTION_URL ? `https://${env.VERCEL_PROJECT_PRODUCTION_URL}` : ''));
const apiBase = origin('PUBLIC_API_BASE', env.PUBLIC_API_BASE || '');
const turnstileKey = (env.PUBLIC_TURNSTILE_SITE_KEY || '').trim();
if (turnstileKey && !/^[A-Za-z0-9_-]{8,100}$/.test(turnstileKey)) fail('PUBLIC_TURNSTILE_SITE_KEY has an unexpected format');
const ttl = String(env.PUBLIC_VERIFY_TTL_HOURS || env.WAITLIST_VERIFY_TTL_HOURS || '48');
if (!/^\d{1,3}$/.test(ttl) || +ttl < 1 || +ttl > 168) fail('PUBLIC_VERIFY_TTL_HOURS must be 1–168');
const allowIndexing = env.PUBLIC_ALLOW_INDEXING ? env.PUBLIC_ALLOW_INDEXING === 'true' : production;
const operator = (env.PUBLIC_OPERATOR_NAME || '').trim();
const contact = (env.PUBLIC_CONTACT_EMAIL || '').trim();
const dbProvider = (env.PUBLIC_DATABASE_PROVIDER || '').trim();
if (contact && !/^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/.test(contact)) fail('PUBLIC_CONTACT_EMAIL is not an email address');
if (production && (!operator || !contact)) {
  fail('production builds need PUBLIC_OPERATOR_NAME and PUBLIC_CONTACT_EMAIL (the privacy notice names who runs the waitlist and how to reach them)');
}
const consentVersion = (readFileSync(join(WEB, '..', 'src', 'tracewise', 'waitlist', 'service.py'), 'utf8').match(/^CONSENT_VERSION = "([^"]+)"/m) || [])[1];
if (!consentVersion) fail('could not read CONSENT_VERSION from src/tracewise/waitlist/service.py');

const placeholder = (what) => { warnings.push(`${what} is not set: the privacy notice shows a visible placeholder`); return `<span class="placeholder">[${esc(what)} not set]</span>`; };
const vars = {
  PUBLIC_API_BASE: esc(apiBase),
  PUBLIC_TURNSTILE_SITE_KEY: esc(turnstileKey),
  PUBLIC_VERIFY_TTL_HOURS: esc(ttl),
  CONSENT_VERSION: esc(consentVersion),
  OPERATOR: operator ? esc(operator) : placeholder('PUBLIC_OPERATOR_NAME'),
  CONTACT: contact ? `<a href="mailto:${esc(contact)}">${esc(contact)}</a>` : placeholder('PUBLIC_CONTACT_EMAIL'),
  DATABASE_PROVIDER: dbProvider ? esc(dbProvider) : 'A managed PostgreSQL provider (named here before launch)',
};
const flags = { TURNSTILE: Boolean(turnstileKey) };

const TS = 'https://challenges.cloudflare.com';
const csp = [
  "default-src 'self'",
  `script-src 'self'${flags.TURNSTILE ? ' ' + TS : ''}`,
  "style-src 'self'",
  "img-src 'self' data:",
  "font-src 'self'",
  "media-src 'self'",
  `connect-src 'self'${apiBase ? ' ' + apiBase : ''}`,
  `frame-src ${flags.TURNSTILE ? TS : "'none'"}`,
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'self'",
].join('; ');

// ------------------------------------------------------------ assets
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
cpSync(PUB, OUT, { recursive: true });
for (const required of ['media/tracewise-paper-trail-720p.mp4', 'media/tracewise-paper-trail-poster.jpg', 'media/tracewise-paper-trail.en.vtt']) {
  if (!existsSync(join(OUT, required))) warnings.push(`missing web/public/${required} (the film section will not play)`);
}
const hash = (buf) => createHash('sha256').update(buf).digest('hex').slice(0, 12);

// JS modules: version every import so a new deployment never mixes old and new modules from a cache.
const jsDir = join(SRC, 'js');
const jsFiles = readdirSync(jsDir).filter((f) => f.endsWith('.mjs'));
const jsHash = {};
for (const f of jsFiles) jsHash[f] = hash(readFileSync(join(jsDir, f)));
// a module's version also covers the modules it imports
const versionOf = (f) => hash(Buffer.from(jsFiles.map((g) => jsHash[g]).join('') + f));
mkdirSync(join(OUT, 'js'));
for (const f of jsFiles) {
  const code = readFileSync(join(jsDir, f), 'utf8').replace(/from '\.\/([a-z-]+\.mjs)'/g, (_, dep) => {
    if (!jsHash[dep]) fail(`${f} imports missing module ${dep}`);
    return `from './${dep}?v=${versionOf(dep)}'`;
  });
  writeFileSync(join(OUT, 'js', f), code);
}
const css = readFileSync(join(SRC, 'css', 'site.css'));
mkdirSync(join(OUT, 'css'));
writeFileSync(join(OUT, 'css', 'site.css'), css);
const cssVersion = hash(css);

// ------------------------------------------------------------ pages
const partials = Object.fromEntries(readdirSync(join(SRC, 'partials')).map((f) => [f.replace(/\.html$/, ''), readFileSync(join(SRC, 'partials', f), 'utf8')]));
const PAGES = { 'index.html': 'index.html', 'confirm.html': 'confirm/index.html', 'unsubscribe.html': 'unsubscribe/index.html', 'privacy.html': 'privacy/index.html', '404.html': '404.html' };
const indexable = [];

for (const [srcName, outName] of Object.entries(PAGES)) {
  let html = readFileSync(join(SRC, srcName), 'utf8');
  const metaMatch = html.match(/^<!--meta (.*?)-->\n/);
  if (!metaMatch) fail(`${srcName}: missing <!--meta ...--> line`);
  const meta = Object.fromEntries([...metaMatch[1].matchAll(/(\w+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
  html = html.slice(metaMatch[0].length);
  html = html.replace(/\{\{> (\w+)\}\}/g, (_, n) => { if (!(n in partials)) fail(`${srcName}: unknown partial ${n}`); return partials[n]; });
  html = html.replace(/<!--#if (\w+)-->([\s\S]*?)<!--#endif-->/g, (_, flag, inner) => (flags[flag] ? inner : ''));
  const robots = meta.robots || (allowIndexing ? 'index, follow' : 'noindex, nofollow');
  if (robots.startsWith('index')) indexable.push(meta.path);
  const pageVars = {
    ...vars,
    TITLE: esc(meta.title),
    DESCRIPTION: esc(meta.description),
    ROBOTS: esc(robots),
    CSP: esc(csp),
    CANONICAL: siteUrl && robots.startsWith('index') ? `<link rel="canonical" href="${esc(siteUrl + meta.path)}">\n` : '',
    OG_IMAGE: siteUrl ? `<meta property="og:image" content="${esc(siteUrl)}/media/tracewise-paper-trail-poster.jpg">\n` : '',
  };
  html = html.replace(/\{\{([A-Z_]+)\}\}/g, (m, k) => { if (!(k in pageVars)) fail(`${srcName}: unknown variable ${k}`); return pageVars[k]; });
  html = html.replace('href="/css/site.css"', `href="/css/site.css?v=${cssVersion}"`);
  html = html.replace(/src="\/js\/([a-z-]+\.mjs)"/g, (_, f) => { if (!jsHash[f]) fail(`${srcName}: missing script ${f}`); return `src="/js/${f}?v=${versionOf(f)}"`; });
  if (/\{\{|<!--#|<!--meta/.test(html)) fail(`${srcName}: unrendered template syntax`);
  if (/design preview|preview-banner|data-preview-form/i.test(html)) fail(`${srcName}: design-preview markup leaked into the production page`);
  if (/style="/.test(html)) fail(`${srcName}: inline style attribute (blocked by the CSP)`);
  if (/<script(?![^>]*\bsrc=)[^>]*>/.test(html)) fail(`${srcName}: inline script (blocked by the CSP)`);
  mkdirSync(dirname(join(OUT, outName)), { recursive: true });
  writeFileSync(join(OUT, outName), html);
}

writeFileSync(join(OUT, 'robots.txt'), allowIndexing
  ? `User-agent: *\nDisallow: /confirm/\nDisallow: /unsubscribe/\nDisallow: /api/\n${siteUrl ? `Sitemap: ${siteUrl}/sitemap.xml\n` : ''}`
  : 'User-agent: *\nDisallow: /\n');
if (allowIndexing && siteUrl) {
  const urls = indexable.map((p) => `  <url><loc>${esc(siteUrl + p)}</loc></url>`).join('\n');
  writeFileSync(join(OUT, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`);
}

// ------------------------------------------------------------ safety: nothing secret-looking in the output
const SECRETISH = [/re_[A-Za-z0-9]{16,}/, /postgres(ql)?:\/\/[^\s"'<]*:[^\s"'<]*@/i, /WAITLIST_SECRET\s*=/, /CRON_SECRET\s*=/, /sk-[A-Za-z0-9]{20,}/];
const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]));
let bytes = 0;
for (const f of walk(OUT)) {
  bytes += statSync(f).size;
  if (!/\.(html|mjs|css|txt|xml|vtt|svg)$/.test(f)) continue;
  const text = readFileSync(f, 'utf8');
  for (const re of SECRETISH) if (re.test(text)) fail(`${relative(WEB, f)} contains something that looks like a secret (${re})`);
}

for (const w of warnings) console.warn(`build: warning: ${w}`);
console.log(`build: ${Object.keys(PAGES).length} pages, ${(bytes / 1e6).toFixed(1)} MB → ${relative(process.cwd(), OUT) || OUT}`
  + ` (indexing ${allowIndexing ? 'on' : 'off'}, turnstile ${flags.TURNSTILE ? 'on' : 'off'}, api ${apiBase || 'same origin'})`);
