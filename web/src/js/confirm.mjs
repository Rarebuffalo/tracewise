// /confirm#token=…  The token is in the fragment, so it never reaches a server log. It is removed from the address
// bar immediately, and only sent when the person presses the button (mail scanners that open links don't confirm).
import { call } from './api.mjs';
import { CI_FREQUENCIES, tokenFromHash } from './validate.mjs';

const $ = (s, r = document) => r.querySelector(s);
const token = tokenFromHash(location.hash);
if (location.hash) history.replaceState(null, '', location.pathname + location.search);

const states = [...document.querySelectorAll('[data-state]')];
function show(name) {
  for (const s of states) s.hidden = s.dataset.state !== name;
  const el = states.find((s) => s.dataset.state === name);
  const h = el && el.querySelector('h1, h2, [data-focus]');
  if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
}

let receipt = '';
let busy = false;
const btn = $('[data-confirm]');
const label = btn && $('.btn-label', btn);

async function confirm() {
  if (busy || !token) return;
  busy = true;
  btn.disabled = true;
  btn.closest('.state').classList.add('is-busy');
  label.textContent = 'Confirming…';
  const r = await call('/confirm', { method: 'POST', json: { token } });
  busy = false;
  btn.disabled = false;
  btn.closest('.state').classList.remove('is-busy');
  label.textContent = 'Confirm my spot';
  const status = r.status === 200 && r.body ? r.body.status : r.status === 429 ? 'rate_limited' : r.status === 0 ? 'network' : 'error';
  if (r.body && typeof r.body.receipt === 'string') receipt = r.body.receipt;
  if (status === 'confirmed' || status === 'already_confirmed') {
    show(status);
    const q = $('.followup');
    if (q && receipt) { q.hidden = false; }
    return;
  }
  if (['expired', 'invalid', 'rate_limited', 'network'].includes(status)) { show(status); return; }
  show('error');
}

if (!token) show('missing');
else {
  show('ready');
  btn.addEventListener('click', confirm);
  for (const b of document.querySelectorAll('[data-retry]')) b.addEventListener('click', () => { show('ready'); confirm(); });
}

const followup = $('.followup');
if (followup) {
  const done = $('.followup-done');
  let sent = false;
  followup.addEventListener('change', async (e) => {
    const value = e.target && e.target.value;
    if (!CI_FREQUENCIES.includes(value) || sent || !receipt) return;
    sent = true;
    for (const r of followup.querySelectorAll('input')) r.disabled = true;
    const r = await call('/profile', { method: 'POST', json: { receipt, ci_failure_freq: value } });
    done.textContent = r.status === 204 ? 'Thanks — noted.' : "Thanks. We couldn't save that just now, and that's fine: it's optional.";
    done.hidden = false;
  });
}
