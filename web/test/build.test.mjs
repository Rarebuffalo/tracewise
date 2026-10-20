// The build's own guarantees: production needs operator details, configuration is validated, and the output has
// no template leftovers, no preview markup and nothing that looks like a secret.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const BUILD = fileURLToPath(new URL('../build.mjs', import.meta.url));
const clean = Object.fromEntries(Object.entries(process.env).filter(([k]) => !k.startsWith('PUBLIC_') && !k.startsWith('VERCEL') && !k.startsWith('WAITLIST_')));

function build(env = {}) {
  const out = mkdtempSync(join(tmpdir(), 'tw-web-'));
  const r = spawnSync(process.execPath, [BUILD], { env: { ...clean, WEB_OUT_DIR: out, ...env }, encoding: 'utf8' });
  return { ...r, out, read: (p) => readFileSync(join(out, p), 'utf8') };
}

test('local build: noindex, placeholders flagged, same-origin API, no Turnstile', () => {
  const b = build();
  assert.equal(b.status, 0, b.stderr);
  const home = b.read('index.html');
  assert.match(home, /<meta name="robots" content="noindex, nofollow">/);
  assert.match(home, /data-api=""/);
  assert.doesNotMatch(home, /challenges\.cloudflare\.com/);
  assert.match(b.read('privacy/index.html'), /class="placeholder">\[PUBLIC_OPERATOR_NAME not set\]/);
  assert.equal(b.read('robots.txt'), 'User-agent: *\nDisallow: /\n');
  for (const p of ['index.html', 'confirm/index.html', 'unsubscribe/index.html', 'privacy/index.html', '404.html']) {
    const html = b.read(p);
    assert.doesNotMatch(html, /\{\{|<!--#|Design preview|preview-banner|data-preview-form/, p);
    assert.match(html, /http-equiv="Content-Security-Policy"/, p);
  }
});

test('production build refuses to ship without operator details', () => {
  const b = build({ VERCEL_ENV: 'production', VERCEL_PROJECT_PRODUCTION_URL: 'tw.example.vercel.app' });
  assert.notEqual(b.status, 0);
  assert.match(b.stderr, /PUBLIC_OPERATOR_NAME and PUBLIC_CONTACT_EMAIL/);
});

test('production build: indexed, canonical, sitemap, operator shown', () => {
  const b = build({ VERCEL_ENV: 'production', VERCEL_PROJECT_PRODUCTION_URL: 'tw.example.vercel.app',
    PUBLIC_OPERATOR_NAME: 'Example Ltd', PUBLIC_CONTACT_EMAIL: 'privacy@example.com' });
  assert.equal(b.status, 0, b.stderr);
  const home = b.read('index.html');
  assert.match(home, /content="index, follow"/);
  assert.match(home, /<link rel="canonical" href="https:\/\/tw\.example\.vercel\.app\/">/);
  assert.match(b.read('confirm/index.html'), /noindex, nofollow/); // token pages are never indexed
  assert.match(b.read('sitemap.xml'), /<loc>https:\/\/tw\.example\.vercel\.app\/privacy\/<\/loc>/);
  assert.doesNotMatch(b.read('sitemap.xml'), /confirm|unsubscribe/);
  assert.match(b.read('privacy/index.html'), /Example Ltd/);
});

test('Turnstile adds the widget and the CSP allowance only when configured', () => {
  const b = build({ PUBLIC_TURNSTILE_SITE_KEY: '0x4AAAAAAAexample' });
  assert.equal(b.status, 0, b.stderr);
  const home = b.read('index.html');
  assert.equal((home.match(/class="cf-turnstile/g) || []).length, 2);
  assert.match(home, /script-src &#39;self&#39; https:\/\/challenges\.cloudflare\.com/);
});

test('invalid configuration fails the build', () => {
  assert.notEqual(build({ PUBLIC_SITE_URL: 'https://example.com/path' }).status, 0);
  assert.notEqual(build({ PUBLIC_API_BASE: 'javascript:alert(1)' }).status, 0);
  assert.notEqual(build({ PUBLIC_TURNSTILE_SITE_KEY: '"><script>' }).status, 0);
  assert.notEqual(build({ PUBLIC_CONTACT_EMAIL: 'not an email' }).status, 0);
  assert.notEqual(build({ PUBLIC_VERIFY_TTL_HOURS: '0' }).status, 0);
});

test('values are HTML-escaped and a secret-looking value stops the build', () => {
  const ok = build({ PUBLIC_OPERATOR_NAME: 'A <b>&</b> "B"', PUBLIC_CONTACT_EMAIL: 'p@example.com' });
  assert.equal(ok.status, 0, ok.stderr);
  assert.match(ok.read('privacy/index.html'), /A &lt;b&gt;&amp;&lt;\/b&gt; &quot;B&quot;/);
  const leak = build({ PUBLIC_OPERATOR_NAME: 're_AbCdEfGhIjKlMnOpQrSt', PUBLIC_CONTACT_EMAIL: 'p@example.com' });
  assert.notEqual(leak.status, 0);
  assert.match(leak.stderr, /looks like a secret/);
});

test('module imports and asset links are versioned', () => {
  const b = build();
  assert.match(b.read('js/home.mjs'), /from '\.\/api\.mjs\?v=[0-9a-f]{12}'/);
  assert.match(b.read('index.html'), /src="\/js\/home\.mjs\?v=[0-9a-f]{12}"/);
  assert.ok(existsSync(join(b.out, 'assets/fonts/Geist-Variable-latin.woff2')));
});
