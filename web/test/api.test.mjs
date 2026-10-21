// The API client's request options. Runs in Node with a stub document and fetch; the browser enforces what
// `credentials: 'same-origin'` means (cookies only to this site's own origin, never to another).
import assert from 'node:assert/strict';
import { test } from 'node:test';

const calls = [];
globalThis.fetch = async (url, init) => {
  calls.push({ url, init });
  return { status: 200, json: async () => ({ form_token: 't' }) };
};

async function load(api) {
  globalThis.document = { documentElement: { dataset: { api } } };
  return import(`../src/js/api.mjs?api=${encodeURIComponent(api)}`); // a fresh module per base
}

test('same-origin API: relative URL, cookies only to this origin, no caching', async () => {
  const { call } = await load('');
  calls.length = 0;
  const r = await call('/form');
  assert.equal(r.status, 200);
  assert.equal(calls[0].url, '/api/waitlist/form');
  assert.equal(calls[0].init.credentials, 'same-origin'); // lets Vercel's preview-protection cookie through
  assert.notEqual(calls[0].init.credentials, 'include'); // never sends cookies cross-origin
  assert.equal(calls[0].init.cache, 'no-store');
  assert.equal(calls[0].init.method, 'GET');
});

test('JSON POST keeps the same credentials policy', async () => {
  const { call } = await load('');
  calls.length = 0;
  await call('/signup', { method: 'POST', json: { email: 'a@b.co' } });
  assert.equal(calls[0].init.credentials, 'same-origin');
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json');
});

test('a separate API origin (PUBLIC_API_BASE) still gets no cookies from the browser', async () => {
  const { call } = await load('https://api.tracewise-build-test.org/');
  calls.length = 0;
  await call('/form');
  assert.equal(calls[0].url, 'https://api.tracewise-build-test.org/api/waitlist/form');
  assert.equal(calls[0].init.credentials, 'same-origin'); // cross-origin request → browser omits cookies
});
