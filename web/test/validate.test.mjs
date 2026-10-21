// Unit tests for the browser-side checks (node --test web/test/*.test.mjs). The same cases as the server's, so both agree.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { counterText, normalizeEmail, normalizeGithub, signupOutcome, tokenFromHash, validateSignup } from '../src/js/validate.mjs';

test('normalizeEmail accepts and lower-cases', () => {
  assert.equal(normalizeEmail('  Ada@Example.COM '), 'ada@example.com');
  assert.equal(normalizeEmail('first.last+ci@sub.example.org'), 'first.last+ci@sub.example.org');
});

test('normalizeEmail rejects what the server rejects', () => {
  for (const bad of ['', '  ', 'ada', 'ada@', '@example.com', 'ada@localhost', 'ada@@example.com', 'a da@example.com',
    'ada@example.com\nBcc: x@y.com', '<ada@example.com>', `a@${'x'.repeat(250)}.com`, `${'x'.repeat(65)}@example.com`]) {
    assert.equal(normalizeEmail(bad), null, JSON.stringify(bad));
  }
});

test('normalizeGithub', () => {
  assert.equal(normalizeGithub(''), null);
  assert.equal(normalizeGithub('  '), null);
  assert.equal(normalizeGithub('@octocat'), 'octocat');
  assert.equal(normalizeGithub('https://github.com/octo-cat/'), 'octo-cat');
  for (const bad of ['-bad', 'bad-', 'a--b', 'x'.repeat(40), 'has space', '<script>', 'a/b']) assert.equal(normalizeGithub(bad), undefined, bad);
});

test('validateSignup builds a minimal body and reports field errors', () => {
  assert.deepEqual(validateSignup({ email: 'Ada@Example.com', github: '@octocat', updates: true }),
    { ok: true, errors: {}, body: { email: 'ada@example.com', github: 'octocat', updates: true } });
  assert.deepEqual(validateSignup({ email: '' }).errors, { email: 'missing' });
  assert.deepEqual(validateSignup({ email: 'nope', github: 'a--b' }).errors, { email: 'invalid', github: 'invalid' });
  assert.equal(validateSignup({ email: 'a@b.co' }).body.updates, false); // consent is never assumed
});

test('signupOutcome maps every server answer to a UI state', () => {
  assert.deepEqual(signupOutcome(202, { status: 'check_email', receipt: 'r' }), { kind: 'success', receipt: 'r' });
  assert.equal(signupOutcome(422, { error: 'invalid_email' }).field, 'email');
  assert.equal(signupOutcome(422, { error: 'invalid_github' }).field, 'github');
  assert.equal(signupOutcome(400, { error: 'form_expired' }).kind, 'retry');
  assert.match(signupOutcome(400, { error: 'challenge_failed' }).message, /anti-spam/);
  assert.match(signupOutcome(429, null).message, /Too many/);
  assert.match(signupOutcome(503, { error: 'unavailable' }).message, /temporarily unavailable/);
  assert.equal(signupOutcome(503, { error: 'signups_closed' }).kind, 'closed');
  assert.match(signupOutcome(503, { error: 'signups_closed' }).message, /aren't open yet/);
  assert.match(signupOutcome(0, null).message, /couldn't reach/);
  assert.match(signupOutcome(500, { error: '<b>raw</b>' }).message, /Something went wrong/); // server text is never shown
  assert.equal(signupOutcome(200, { status: 'check_email' }).kind, 'error'); // only the documented success counts
});

test('tokenFromHash reads only a well-formed token', () => {
  assert.equal(tokenFromHash('#token=abc_DEF-123'), 'abc_DEF-123');
  assert.equal(tokenFromHash('#token=1b2c.ffee'), '1b2c.ffee');
  assert.equal(tokenFromHash(''), null);
  assert.equal(tokenFromHash('#other=1'), null);
  assert.equal(tokenFromHash('#token=<script>'), null);
  assert.equal(tokenFromHash('#token=' + 'a'.repeat(201)), null);
});

test('counterText shows only rounded figures from 50', () => {
  assert.equal(counterText({ shown: false }), null);
  assert.equal(counterText({ shown: true, count_floor: 50 }), '50+');
  assert.equal(counterText({ shown: true, count_floor: 120 }), '120+');
  for (const bad of [0, 40, 49, 55, '60', null]) assert.equal(counterText({ shown: true, count_floor: bad }), null, String(bad));
  assert.equal(counterText(null), null);
});
