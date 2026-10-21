// Tiny client for /api/waitlist/*. Same origin by default; a different API origin can be set at build time
// (PUBLIC_API_BASE), and is then also the only extra origin in the Content-Security-Policy connect-src.
const BASE = (document.documentElement.dataset.api || '').replace(/\/+$/, '') + '/api/waitlist';
const TIMEOUT_MS = 15000;

/** Returns {status, body}; status 0 means the request never got an answer (offline, timeout, blocked). */
export async function call(path, { method = 'GET', json } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(BASE + path, {
      method,
      headers: json === undefined ? {} : { 'Content-Type': 'application/json' },
      body: json === undefined ? undefined : JSON.stringify(json),
      // Cookies go only to this site's own origin. The waitlist sets none; this lets Vercel's preview login cookie
      // through (without it, Deployment Protection redirects to vercel.com and the CSP blocks the redirect).
      credentials: 'same-origin',
      cache: 'no-store',
      signal: ctl.signal,
    });
    let body = null;
    if (res.status !== 204) {
      try { body = await res.json(); } catch { body = null; }
    }
    return { status: res.status, body };
  } catch {
    return { status: 0, body: null };
  } finally {
    clearTimeout(timer);
  }
}

// ---- form token: proves a human-paced submission. Fetched on load; refreshed when it has expired.
let tokenAt = 0;
let token = null;
let pending = null;
/** True once the server has said it is not accepting signups (email not configured). */
export let signupsClosed = false;

export function prefetchFormToken() {
  if (!pending) {
    pending = call('/form').then((r) => {
      pending = null;
      if (r.status === 200 && r.body && typeof r.body.form_token === 'string') { token = r.body.form_token; tokenAt = Date.now(); }
      if (r.status === 503 && r.body && r.body.error === 'signups_closed') signupsClosed = true;
      return token;
    });
  }
  return pending;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** A form token at least ~2 s old (the server treats faster submissions as automated). */
export async function formToken({ fresh = false } = {}) {
  if (fresh || !token || Date.now() - tokenAt > 90 * 60 * 1000) { token = null; await prefetchFormToken(); }
  const age = Date.now() - tokenAt;
  if (token && age < 2300) await sleep(2300 - age);
  return token;
}
