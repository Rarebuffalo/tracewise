// The build's own guarantees: production needs operator details, configuration is validated, and the output has
// no template leftovers, no preview markup and nothing that looks like a secret.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const BUILD = fileURLToPath(new URL('../build.mjs', import.meta.url));
// Clearly fake identity for tests only: not a real operator or inbox, and never used in a deployment.
const TEST_ID = { PUBLIC_OPERATOR_NAME: 'Build-Test Operator Ltd', PUBLIC_CONTACT_EMAIL: 'privacy@tracewise-build-test.org' };
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

const PROD = { VERCEL_ENV: 'production', VERCEL_PROJECT_PRODUCTION_URL: 'tw.example.vercel.app' };

test('production build refuses to ship without operator details, and says where to set them', () => {
  const b = build(PROD);
  assert.notEqual(b.status, 0);
  assert.match(b.stderr, /PUBLIC_OPERATOR_NAME is not set/);
  assert.match(b.stderr, /PUBLIC_CONTACT_EMAIL is not set/);
  assert.match(b.stderr, /Environment Variables, environment "Production"/);
  assert.match(b.stderr, /Redeploy/);
});

test('production build needs both identity values, not just one', () => {
  const onlyName = build({ ...PROD, PUBLIC_OPERATOR_NAME: TEST_ID.PUBLIC_OPERATOR_NAME });
  assert.notEqual(onlyName.status, 0);
  assert.match(onlyName.stderr, /PUBLIC_CONTACT_EMAIL is not set/);
  assert.doesNotMatch(onlyName.stderr, /PUBLIC_OPERATOR_NAME is not set/);
  const onlyContact = build({ ...PROD, PUBLIC_CONTACT_EMAIL: TEST_ID.PUBLIC_CONTACT_EMAIL });
  assert.notEqual(onlyContact.status, 0);
  assert.match(onlyContact.stderr, /PUBLIC_OPERATOR_NAME is not set/);
  const blank = build({ ...PROD, PUBLIC_OPERATOR_NAME: '   ', PUBLIC_CONTACT_EMAIL: ' ' });
  assert.notEqual(blank.status, 0); // whitespace is not a value
});

test('production build rejects placeholder identities', () => {
  for (const name of ['CHANGE_ME', 'TODO', 'TBD', 'Your Name', 'example']) {
    const b = build({ ...PROD, PUBLIC_OPERATOR_NAME: name, PUBLIC_CONTACT_EMAIL: TEST_ID.PUBLIC_CONTACT_EMAIL });
    assert.notEqual(b.status, 0, name);
    assert.match(b.stderr, /looks like a placeholder/, name);
  }
  for (const mail of ['privacy@example.com', 'a@mail.example.org', 'p@site.invalid', 'p@site.test', 'p@localhost']) {
    const b = build({ ...PROD, PUBLIC_OPERATOR_NAME: TEST_ID.PUBLIC_OPERATOR_NAME, PUBLIC_CONTACT_EMAIL: mail });
    assert.notEqual(b.status, 0, mail);
  }
});

test('preview builds keep visible placeholders and stay unindexed', () => {
  const b = build({ VERCEL_ENV: 'preview', VERCEL_PROJECT_PRODUCTION_URL: 'tw.example.vercel.app' });
  assert.equal(b.status, 0, b.stderr);
  assert.match(b.stderr, /PUBLIC_OPERATOR_NAME is not set: the privacy notice shows a visible placeholder/);
  assert.match(b.read('privacy/index.html'), /class="placeholder">\[PUBLIC_CONTACT_EMAIL not set\]/);
  assert.match(b.read('index.html'), /noindex, nofollow/);
});

test('runtime secrets in the build environment never reach the output', () => {
  const secrets = {
    WAITLIST_SECRET: 'wl-secret-SHOULD-NOT-LEAK-6f1d0c2a9b8e7d6c5b4a3f2e1d0c9b8a',
    RESEND_API_KEY: 're_SHOULDNOTLEAKaaaaaaaaaaaaaaaa',
    CRON_SECRET: 'cron-SHOULD-NOT-LEAK-0123456789abcdef0123456789abcdef',
    WAITLIST_DATABASE_URL: 'postgresql://tracewise_waitlist:pw-SHOULD-NOT-LEAK@db.invalid/w',
    WAITLIST_DATABASE_URL_MIGRATIONS: 'postgresql://owner:pw2-SHOULD-NOT-LEAK@db.invalid/w',
    WAITLIST_TURNSTILE_SECRET: '0x-turnstile-SHOULD-NOT-LEAK',
    WAITLIST_OWNER_NOTIFY_EMAIL: 'owner-SHOULD-NOT-LEAK@tracewise-build-test.org',
  };
  const b = build({ ...PROD, ...TEST_ID, ...secrets });
  assert.equal(b.status, 0, b.stderr);
  const walk = (d) => readdirSync(d).flatMap((f) => (statSync(join(d, f)).isDirectory() ? walk(join(d, f)) : [join(d, f)]));
  for (const f of walk(b.out)) {
    const text = readFileSync(f, 'latin1');
    assert.doesNotMatch(text, /SHOULD-NOT-LEAK|SHOULDNOTLEAK/, f);
  }
  assert.doesNotMatch(b.stdout + b.stderr, /SHOULD-NOT-LEAK|SHOULDNOTLEAK/); // not in the build log either
});

test('production build: indexed, canonical, sitemap, operator shown', () => {
  const b = build({ ...PROD, ...TEST_ID });
  assert.equal(b.status, 0, b.stderr);
  const home = b.read('index.html');
  assert.match(home, /content="index, follow"/);
  assert.match(home, /<link rel="canonical" href="https:\/\/tw\.example\.vercel\.app\/">/);
  assert.match(b.read('confirm/index.html'), /noindex, nofollow/); // token pages are never indexed
  assert.match(b.read('sitemap.xml'), /<loc>https:\/\/tw\.example\.vercel\.app\/privacy\/<\/loc>/);
  assert.doesNotMatch(b.read('sitemap.xml'), /confirm|unsubscribe/);
  assert.match(b.read('privacy/index.html'), /Build-Test Operator Ltd/);
  assert.match(b.read('privacy/index.html'), /mailto:privacy@tracewise-build-test\.org/);
  assert.doesNotMatch(b.read('privacy/index.html'), /not set\]/);
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
