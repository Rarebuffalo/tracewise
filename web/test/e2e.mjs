#!/usr/bin/env node
// End-to-end browser test of the real site + API (no dependencies: headless Chromium over the DevTools protocol).
//
//   node web/build.mjs && uv run python web/dev.py --port 8010 &      # disposable DB, file-based email
//   node web/test/e2e.mjs                                              # E2E_BASE_URL, E2E_MAIL_DIR, CHROME to override
//
// Covers: signup (validation, loading, success, follow-up, double submit), server and network failures, the
// confirmation link (success, repeat, invalid, missing), the owner notification, unsubscribe, the counter staying
// hidden, mobile layout, reduced motion, keyboard use, and zero console errors / CSP violations throughout.
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const BASE = (process.env.E2E_BASE_URL || 'http://127.0.0.1:8010').replace(/\/$/, '');
const MAIL = resolve(process.env.E2E_MAIL_DIR || '.waitlist-mail');
const CHROME = process.env.CHROME || ['/usr/bin/chromium', '/usr/bin/google-chrome', '/usr/bin/chromium-browser'].find(existsSync);
if (!CHROME) { console.error('e2e: no Chromium found (set CHROME)'); process.exit(2); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let passed = 0;
const failures = [];
async function check(name, fn) {
  try { await fn(); passed++; console.log(`  ok  ${name}`); } catch (e) { failures.push(name); console.log(`  FAIL ${name}\n       ${e.message}`); }
}
const assert = (cond, msg) => { if (!cond) throw new Error(msg); };

// ------------------------------------------------------------ minimal CDP client
const profile = mkdtempSync(join(tmpdir(), 'tw-e2e-'));
const chrome = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run',
  '--no-default-browser-check', '--disable-gpu', '--disable-extensions', '--mute-audio', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
let wsUrl;
for (let i = 0; i < 100 && !wsUrl; i++) {
  await sleep(100);
  const f = join(profile, 'DevToolsActivePort');
  if (existsSync(f)) { const [port] = readFileSync(f, 'utf8').split('\n'); wsUrl = await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json()).then((l) => l.find((t) => t.type === 'page')?.webSocketDebuggerUrl); }
}
if (!wsUrl) { console.error('e2e: Chromium did not start'); chrome.kill(); process.exit(2); }

const ws = new WebSocket(wsUrl);
await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
let seq = 0;
const waiting = new Map();
const listeners = [];
ws.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && waiting.has(m.id)) { const { res, rej } = waiting.get(m.id); waiting.delete(m.id); m.error ? rej(new Error(m.error.message)) : res(m.result); }
  else if (m.method) for (const l of listeners) l(m);
};
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; waiting.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const problems = [];
listeners.push((m) => {
  if (m.method === 'Runtime.exceptionThrown') problems.push('exception: ' + (m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text));
  if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') problems.push('console.error: ' + m.params.args.map((a) => a.value ?? a.description).join(' '));
  // API 4xx/503 answers and the deliberately failed request in the network-failure check are expected; nothing else
  if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') {
    const e = m.params.entry;
    const expectedApi = /\/api\/waitlist\//.test(e.url || '') && /status of (4\d\d|503)|ERR_INTERNET_DISCONNECTED/.test(e.text);
    const expected404 = (e.url || '').endsWith('/does-not-exist'); // the 404 page check visits it on purpose
    if (!expectedApi && !expected404) problems.push(`log: ${e.text} ${e.url || ''}`);
  }
});
await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable');

async function evaluate(expression) {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error('evaluate: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
  return r.result.value;
}
async function waitFor(expression, what, timeout = 8000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await evaluate(`!!(${expression})`)) return; await sleep(50); }
  throw new Error(`timed out waiting for ${what}`);
}
async function load(url) {
  const loaded = new Promise((r) => { const l = (m) => { if (m.method === 'Page.loadEventFired') { listeners.splice(listeners.indexOf(l), 1); r(); } }; listeners.push(l); });
  await send('Page.navigate', { url });
  await loaded;
}
async function go(path) {
  await load('about:blank'); // always a full document load, even when only the #fragment differs
  await load(BASE + path);
  await sleep(150);
}
const visibleState = () => evaluate(`[...document.querySelectorAll('[data-state]')].filter(s => !s.hidden).map(s => s.dataset.state).join(',')`);
const noOverflow = () => evaluate('document.documentElement.scrollWidth <= window.innerWidth');
async function key(k, code, keyCode, mods = 0) {
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: k, code, windowsVirtualKeyCode: keyCode, modifiers: mods });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code, windowsVirtualKeyCode: keyCode, modifiers: mods });
}
function mailFor(address, kind) {
  if (!existsSync(MAIL)) return [];
  return readdirSync(MAIL).filter((f) => f.includes(kind)).map((f) => JSON.parse(readFileSync(join(MAIL, f), 'utf8'))).filter((m) => m.to === address || (kind === 'owner' && m.text.includes(address)));
}
const fill = (sel, value) => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.focus(); e.value = ${JSON.stringify(value)}; e.dispatchEvent(new Event('input', {bubbles: true})); })()`);

const email = `e2e-${Date.now()}@example.com`;
console.log(`e2e against ${BASE} (mail: ${MAIL})`);

// ------------------------------------------------------------ desktop: home page
await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
await go('/');
await check('home renders the approved design with no preview markup', async () => {
  assert(await evaluate(`document.querySelector('h1').textContent.includes('Your CI failed.')`), 'h1 missing');
  assert(!(await evaluate(`!!document.querySelector('.preview-banner, .review, [data-preview-form]')`)), 'preview markup present');
  assert(await evaluate(`document.documentElement.classList.contains('anim')`), 'motion classes not applied');
  await waitFor(`document.querySelector('.trail').classList.contains('stamped')`, 'trail animation');
});
await check('counter stays hidden below 50 confirmed signups', async () => {
  await sleep(300);
  assert(await evaluate(`document.querySelector('[data-counter]').hidden`), 'counter visible');
});
await check('no horizontal overflow on desktop', async () => assert(await noOverflow(), 'overflow'));

await check('client validation: empty and invalid email, invalid GitHub', async () => {
  await evaluate(`document.querySelector('form.signup').requestSubmit()`);
  assert(await evaluate(`document.querySelector('#email-err').textContent.includes('enter your email')`), 'missing-email message');
  assert(await evaluate(`document.activeElement.id === 'email'`), 'focus not on email');
  await fill('#email', 'not-an-email'); await fill('#gh', 'bad--name');
  await evaluate(`document.querySelector('form.signup').requestSubmit()`);
  assert(await evaluate(`document.querySelector('#email').getAttribute('aria-invalid') === 'true'`), 'aria-invalid missing');
  assert(await evaluate(`!document.querySelector('#gh-err').hidden`), 'github error hidden');
});

await check('server outage (503) shows a retryable error and keeps the input', async () => {
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/waitlist/signup*' }] });
  const l = (m) => { if (m.method === 'Fetch.requestPaused') send('Fetch.fulfillRequest', { requestId: m.params.requestId, responseCode: 503, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from('{"error":"unavailable"}').toString('base64') }); };
  listeners.push(l);
  await fill('#email', email); await fill('#gh', '');
  await evaluate(`document.querySelector('form.signup').requestSubmit()`);
  await waitFor(`!document.querySelector('form.signup .form-error').hidden`, 'error message');
  assert(await evaluate(`document.querySelector('form.signup .form-error').textContent.includes('temporarily unavailable')`), 'wrong message');
  assert(await evaluate(`document.querySelector('#email').value === ${JSON.stringify(email)} && !document.querySelector('form.signup button[type=submit]').disabled`), 'form not usable');
  listeners.splice(listeners.indexOf(l), 1);
  await send('Fetch.disable');
});

await check('network failure shows a connection error', async () => {
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/waitlist/signup*' }] });
  const l = (m) => { if (m.method === 'Fetch.requestPaused') send('Fetch.failRequest', { requestId: m.params.requestId, errorReason: 'InternetDisconnected' }); };
  listeners.push(l);
  await evaluate(`document.querySelector('form.signup').requestSubmit()`);
  await waitFor(`document.querySelector('form.signup .form-error').textContent.includes("couldn't reach")`, 'network message');
  listeners.splice(listeners.indexOf(l), 1);
  await send('Fetch.disable');
});

await check('signup: loading state, one request despite repeated submits, success and echo', async () => {
  await evaluate(`(() => { window.__signups = 0; const orig = window.fetch; window.fetch = (u, o) => { if (String(u).endsWith('/signup')) window.__signups++; return orig(u, o); }; })()`);
  await fill('#gh', '@octocat');
  await evaluate(`document.querySelector('form.signup input[name=updates]').click()`);
  await evaluate(`(() => { const f = document.querySelector('form.signup'); f.requestSubmit(); f.requestSubmit(); f.querySelector('button[type=submit]').click(); })()`);
  assert(await evaluate(`document.querySelector('form.signup').getAttribute('aria-busy') === 'true' && document.querySelector('form.signup button[type=submit]').disabled`), 'no loading state');
  await waitFor(`!document.querySelector('form.signup .form-success').hidden`, 'success state');
  assert(await evaluate('window.__signups') === 1, `expected 1 request, saw ${await evaluate('window.__signups')}`);
  assert(await evaluate(`document.querySelector('form.signup [data-echo]').textContent`) === email, 'echo mismatch');
});

await check('follow-up answer is accepted', async () => {
  await evaluate(`document.querySelector('form.signup input[value=weekly]').click()`);
  await waitFor(`document.querySelector('form.signup .followup-done').textContent.includes('noted')`, 'thanks message');
});

let verify;
await check('verification email was written (local file mode) with fragment links', async () => {
  for (let i = 0; i < 40 && !verify; i++) { verify = mailFor(email, 'verify')[0]; if (!verify) await sleep(100); }
  assert(verify, 'no verification email');
  assert(/\/confirm\/#token=[A-Za-z0-9_-]{40,}/.test(verify.text) && /\/unsubscribe\/#token=/.test(verify.text), 'links missing');
});
const token = verify?.text.match(/\/confirm\/#token=([A-Za-z0-9_-]+)/)?.[1];
const unsub = verify?.text.match(/\/unsubscribe\/#token=([A-Za-z0-9._-]+)/)?.[1];

// ------------------------------------------------------------ confirmation page
await check('confirm page strips the token from the address bar and waits for a click', async () => {
  await go(`/confirm/#token=${token}`);
  assert(await evaluate('location.hash') === '', 'token still in the URL');
  assert(await visibleState() === 'ready', `state ${await visibleState()}`);
  assert(mailFor(email, 'owner').length === 0, 'owner notified before confirmation');
});
await check('confirming: success, follow-up offered, owner notified once', async () => {
  await evaluate(`document.querySelector('[data-confirm]').click()`);
  await waitFor(`!document.querySelector('[data-state=confirmed]').hidden`, 'confirmed state');
  assert(await evaluate(`!document.querySelector('.followup').hidden`), 'follow-up hidden');
  let owner = [];
  for (let i = 0; i < 40 && !owner.length; i++) { owner = mailFor(email, 'owner'); if (!owner.length) await sleep(100); }
  assert(owner.length === 1, `owner notifications: ${owner.length}`);
  assert(owner[0].text.includes('GitHub username: octocat') && owner[0].text.includes('Product-updates consent: yes') && owner[0].text.includes('CI fails: weekly'), 'owner email content');
});
await check('opening the same link again says already confirmed (no second notification)', async () => {
  await go(`/confirm/#token=${token}`);
  await evaluate(`document.querySelector('[data-confirm]').click()`);
  await waitFor(`!document.querySelector('[data-state=already_confirmed]').hidden`, 'already_confirmed');
  await sleep(300);
  assert(mailFor(email, 'owner').length === 1, 'duplicate owner notification');
});
await check('a made-up token is rejected; no token shows guidance', async () => {
  await go('/confirm/#token=thisIsNotARealTokenAtAll1234567890abcdefgh');
  await evaluate(`document.querySelector('[data-confirm]').click()`);
  await waitFor(`!document.querySelector('[data-state=invalid]').hidden`, 'invalid state');
  await go('/confirm/');
  assert(await visibleState() === 'missing', 'missing state');
});

// ------------------------------------------------------------ unsubscribe
await check('unsubscribe removes the signup; a second attempt finds nothing', async () => {
  await go(`/unsubscribe/#token=${unsub}`);
  assert(await evaluate('location.hash') === '', 'token still in the URL');
  await evaluate(`document.querySelector('[data-unsubscribe]').click()`);
  await waitFor(`!document.querySelector('[data-state=removed]').hidden`, 'removed');
  await go(`/unsubscribe/#token=${unsub}`);
  await evaluate(`document.querySelector('[data-unsubscribe]').click()`);
  await waitFor(`!document.querySelector('[data-state=not_found]').hidden`, 'not_found');
});

// ------------------------------------------------------------ keyboard
await check('keyboard: skip link first, report tabs follow arrow keys', async () => {
  await go('/');
  await key('Tab', 'Tab', 9);
  assert(await evaluate(`document.activeElement.classList.contains('skip')`), 'skip link not first');
  await evaluate(`document.querySelector('#tab-diag').focus()`);
  await key('ArrowRight', 'ArrowRight', 39);
  assert(await evaluate(`document.querySelector('#tab-inc').getAttribute('aria-selected') === 'true' && !document.querySelector('#panel-inc').hidden && document.activeElement.id === 'tab-inc'`), 'tabs');
});

// ------------------------------------------------------------ reduced motion
await check('prefers-reduced-motion: no animation classes, everything visible', async () => {
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await go('/');
  await sleep(300);
  assert(!(await evaluate(`document.documentElement.classList.contains('anim')`)), 'anim class present');
  assert(await evaluate(`[...document.querySelectorAll('.trail .ev')].every(e => getComputedStyle(e).opacity === '1')`), 'cards hidden');
  await send('Emulation.setEmulatedMedia', { features: [] });
});

await check('signups closed (email not configured): both forms say so and cannot submit', async () => {
  await send('Fetch.enable', { patterns: [{ urlPattern: '*/api/waitlist/form*' }] });
  const l = (m) => { if (m.method === 'Fetch.requestPaused') send('Fetch.fulfillRequest', { requestId: m.params.requestId, responseCode: 503, responseHeaders: [{ name: 'Content-Type', value: 'application/json' }], body: Buffer.from('{"error":"signups_closed"}').toString('base64') }); };
  listeners.push(l);
  await go('/');
  await waitFor(`[...document.querySelectorAll('form[data-signup]')].every(f => !f.querySelector('.form-error').hidden && f.querySelector('button[type=submit]').disabled)`, 'closed state');
  assert(await evaluate(`document.querySelector('form.signup .form-error').textContent.includes("aren't open yet")`), 'closed message');
  listeners.splice(listeners.indexOf(l), 1);
  await send('Fetch.disable');
});

// ------------------------------------------------------------ mobile
await send('Emulation.setDeviceMetricsOverride', { width: 375, height: 812, deviceScaleFactor: 2, mobile: true });
for (const path of ['/', '/confirm/', '/unsubscribe/', '/privacy/', '/does-not-exist']) {
  await check(`mobile 375px: no horizontal overflow on ${path}`, async () => {
    await go(path);
    await sleep(400);
    const offenders = await evaluate(`[...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > window.innerWidth + 0.5)
      .map(e => (e.tagName + '.' + (e.getAttribute('class') || '')).slice(0, 60) + ' ' + Math.round(e.getBoundingClientRect().right)).slice(0, 6).join(' | ')`);
    assert(await noOverflow(), `scrollWidth ${await evaluate('document.documentElement.scrollWidth')}: ${offenders}`);
  });
}
await check('mobile: hero signup works end to end', async () => {
  await go('/');
  const m = `e2e-mobile-${Date.now()}@example.com`;
  await fill('#hero-email', m);
  await evaluate(`document.querySelector('.inline-form').requestSubmit()`);
  await waitFor(`!document.querySelector('.inline-form .form-success').hidden`, 'hero success', 10000);
  assert(await evaluate(`document.querySelector('.inline-form [data-echo]').textContent`) === m, 'echo');
});

await check('no console errors, exceptions or CSP violations anywhere', async () => assert(problems.length === 0, problems.join('\n       ')));

ws.close();
chrome.kill();
await sleep(200);
rmSync(profile, { recursive: true, force: true });
console.log(`\n${passed} passed, ${failures.length} failed`);
process.exit(failures.length ? 1 : 0);
