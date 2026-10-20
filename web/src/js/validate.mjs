// Client-side checks. They mirror the server's rules (src/tracewise/waitlist/security.py) so people get instant
// feedback; the server re-validates everything and is the only authority.

// WHATWG "valid e-mail address" (what <input type=email> uses), plus: the domain must contain a dot.
const EMAIL_RE = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$/;
const GITHUB_RE = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/;
export const MAX_EMAIL = 254;
export const CI_FREQUENCIES = ['daily', 'weekly', 'monthly', 'rarely'];

/** Trimmed, lower-cased address, or null if it isn't a valid address. */
export function normalizeEmail(raw) {
  const s = String(raw ?? '').trim();
  if (!s || s.length > MAX_EMAIL || !EMAIL_RE.test(s)) return null;
  return s.toLowerCase();
}

/** '' → null; strips a leading @ or a github.com URL; returns undefined if it is not a valid username. */
export function normalizeGithub(raw) {
  let s = String(raw ?? '').trim();
  for (const p of ['https://github.com/', 'http://github.com/', 'github.com/', '@']) {
    if (s.toLowerCase().startsWith(p)) s = s.slice(p.length);
  }
  s = s.replace(/^\/+|\/+$/g, '');
  if (s === '') return null;
  return GITHUB_RE.test(s) ? s : undefined;
}

/** Validate the signup form values. Returns {ok, errors, body}. */
export function validateSignup({ email, github = '', updates = false }) {
  const errors = {};
  const e = normalizeEmail(email);
  if (e === null) errors.email = String(email ?? '').trim() ? 'invalid' : 'missing';
  const g = normalizeGithub(github);
  if (g === undefined) errors.github = 'invalid';
  const ok = Object.keys(errors).length === 0;
  return { ok, errors, body: ok ? { email: e, github: g, updates: Boolean(updates) } : null };
}

/** The message shown for a server or network outcome. Never echoes server text into the page. */
export const MESSAGES = {
  email_missing: 'Please enter your email address.',
  email_invalid: 'Please enter an email address like name@example.com.',
  github_invalid: "That doesn't look like a GitHub username (letters, numbers and single hyphens, up to 39 characters).",
  challenge_failed: "We couldn't verify the anti-spam check. Please try again.",
  rate_limited: 'Too many attempts from your network. Please try again in a little while.',
  signups_closed: "Signups aren't open yet. Please check back soon — nothing was saved.",
  unavailable: "Signups are temporarily unavailable. Please try again in a few minutes — nothing was lost on your side.",
  network: "We couldn't reach the server. Check your connection and try again.",
  unknown: 'Something went wrong on our side. Please try again.',
};

/** Map an API response (status code + parsed body or null) to a UI outcome. */
export function signupOutcome(status, body) {
  if (status === 202 && body && body.status === 'check_email') return { kind: 'success', receipt: String(body.receipt || '') };
  const err = body && typeof body.error === 'string' ? body.error : '';
  if (status === 422 && err === 'invalid_email') return { kind: 'field', field: 'email', message: MESSAGES.email_invalid };
  if (status === 422 && err === 'invalid_github') return { kind: 'field', field: 'github', message: MESSAGES.github_invalid };
  if (status === 400 && err === 'form_expired') return { kind: 'retry' };
  if (status === 400 && err === 'challenge_failed') return { kind: 'error', message: MESSAGES.challenge_failed };
  if (status === 429) return { kind: 'error', message: MESSAGES.rate_limited };
  if (status === 503 && err === 'signups_closed') return { kind: 'closed', message: MESSAGES.signups_closed };
  if (status === 503) return { kind: 'error', message: MESSAGES.unavailable };
  if (status === 0) return { kind: 'error', message: MESSAGES.network };
  return { kind: 'error', message: MESSAGES.unknown };
}

/** Read a token from a URL fragment like "#token=abc". */
export function tokenFromHash(hash) {
  const h = String(hash || '').replace(/^#/, '');
  const v = new URLSearchParams(h).get('token');
  return v && v.length <= 200 && /^[A-Za-z0-9._-]+$/.test(v) ? v : null;
}

/** Public counter text, or null when it must stay hidden. */
export function counterText(data) {
  if (!data || data.shown !== true) return null;
  const n = data.count_floor;
  if (typeof n !== 'number' || !Number.isInteger(n) || n < 50 || n % 10 !== 0) return null;
  return `${n}+`;
}
