// /unsubscribe#token=…  Removes the signup entirely (unsubscribe and deletion are the same action here).
// Like confirmation, the token stays in the fragment and is only sent when the person presses the button.
import { call } from './api.mjs';
import { tokenFromHash } from './validate.mjs';

const token = tokenFromHash(location.hash);
if (location.hash) history.replaceState(null, '', location.pathname + location.search);

const states = [...document.querySelectorAll('[data-state]')];
function show(name) {
  for (const s of states) s.hidden = s.dataset.state !== name;
  const h = states.find((s) => s.dataset.state === name)?.querySelector('h1');
  if (h) { h.setAttribute('tabindex', '-1'); h.focus(); }
}

const btn = document.querySelector('[data-unsubscribe]');
const label = btn && btn.querySelector('.btn-label');
let busy = false;

async function go() {
  if (busy || !token) return;
  busy = true;
  btn.disabled = true;
  btn.closest('.state').classList.add('is-busy');
  label.textContent = 'Removing…';
  const r = await call('/unsubscribe', { method: 'POST', json: { token } });
  busy = false;
  btn.disabled = false;
  btn.closest('.state').classList.remove('is-busy');
  label.textContent = 'Remove me from the list';
  if (r.status === 200 && r.body && r.body.status === 'removed') show('removed');
  else if (r.status === 200 && r.body && r.body.status === 'not_found') show('not_found');
  else if (r.status === 429) show('rate_limited');
  else show('error');
}

if (!token) show('missing');
else {
  show('ready');
  btn.addEventListener('click', go);
  for (const b of document.querySelectorAll('[data-retry]')) b.addEventListener('click', () => { show('ready'); go(); });
}
