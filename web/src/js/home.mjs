// Tracewise home page: the approved "Paper Trail" interactions (ported unchanged from web/design-preview) plus the
// live signup, follow-up question and public counter. With JS off the page is complete and static (the forms then
// explain that JavaScript is needed to submit); with prefers-reduced-motion everything is shown without animation.
import * as api from './api.mjs';
import { call, formToken, prefetchFormToken } from './api.mjs';
import { CI_FREQUENCIES, MESSAGES, counterText, signupOutcome, validateSignup } from './validate.mjs';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const root = document.documentElement;
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
let motion = !reduce.matches;
const setAnim = () => root.classList.toggle('anim', motion);

// ---------------------------------------------------------------- threads: a path through each pinned card
// A soft hanging curve between consecutive pins (the string sags a little under its own weight).
function threadPath(container, pins, vertical, side = false) {
  const box = container.getBoundingClientRect();
  const pts = pins.map((p) => { const r = p.getBoundingClientRect(); return [r.left + r.width / 2 - box.left, r.top + r.height / 2 - box.top]; });
  if (pts.length < 2) return '';
  let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1], [x1, y1] = pts[i];
    if (vertical) { d += ` C ${(x0 - 14).toFixed(1)} ${(y0 + (y1 - y0) * 0.4).toFixed(1)}, ${(x1 - 14).toFixed(1)} ${(y1 - (y1 - y0) * 0.4).toFixed(1)}, ${x1.toFixed(1)} ${y1.toFixed(1)}`; continue; }
    if (side) { const k = Math.max(40, Math.abs(x1 - x0) * 0.6); const sx0 = pins[i - 1]._dir || 1, sx1 = pins[i]._dir || -1;
      d += ` C ${(x0 + sx0 * k).toFixed(1)} ${y0.toFixed(1)}, ${(x1 + sx1 * k).toFixed(1)} ${y1.toFixed(1)}, ${x1.toFixed(1)} ${y1.toFixed(1)}`; continue; }
    const sag = Math.min(90, Math.hypot(x1 - x0, y1 - y0) * 0.22);
    d += ` C ${(x0 + (x1 - x0) * 0.3).toFixed(1)} ${(Math.max(y0, y1) + sag).toFixed(1)}, ${(x0 + (x1 - x0) * 0.7).toFixed(1)} ${(Math.max(y0, y1) + sag).toFixed(1)}, ${x1.toFixed(1)} ${y1.toFixed(1)}`;
  }
  return d;
}
const isNarrow = () => window.matchMedia('(max-width: 640px)').matches;

// hero trail
const trail = $('.trail');
const trailSvg = $('.trail-thread', trail);
const trailPath = $('path', trailSvg);
const evs = $$('.ev', trail);
function layoutTrail() {
  const r = trail.getBoundingClientRect();
  trailSvg.setAttribute('viewBox', `0 0 ${r.width.toFixed(0)} ${r.height.toFixed(0)}`);
  trailSvg.setAttribute('preserveAspectRatio', 'none');
  // side pins: the string leaves each card from the edge that faces the next card, so it runs in the gutters
  const pins = evs.map((e) => $('.pin', e));
  if (!isNarrow()) { const box0 = trail.getBoundingClientRect(); pins.forEach((p) => { const r = p.getBoundingClientRect(), cr = p.parentElement.getBoundingClientRect(); p._dir = (r.left + r.width / 2) > (cr.left + cr.width / 2) ? 1 : -1; }); void box0; }
  trailPath.setAttribute('d', threadPath(trail, pins, isNarrow(), !isNarrow()));
  // pin heads sit on top of the thread (the string runs over the paper, the pins hold it down)
  $$('.pinhead', trailSvg).forEach((n) => n.remove());
  if (!$('#pin-grad', trailSvg)) trailSvg.insertAdjacentHTML('afterbegin', '<defs><radialGradient id="pin-grad" cx="35%" cy="30%" r="70%"><stop offset="0" stop-color="#A5F3FC"/><stop offset=".45" stop-color="#06B6D4"/><stop offset="1" stop-color="#0891B2"/></radialGradient></defs>');
  const box = trail.getBoundingClientRect();
  evs.forEach((e) => { const p = $('.pin', e).getBoundingClientRect(); const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('class', 'pinhead'); c.setAttribute('cx', (p.left + p.width / 2 - box.left).toFixed(1)); c.setAttribute('cy', (p.top + p.height / 2 - box.top).toFixed(1)); c.setAttribute('r', '9'); trailSvg.appendChild(c); });
  const len = trailPath.getTotalLength ? trailPath.getTotalLength() : 2000;
  trailPath.style.setProperty('--len', len.toFixed(0));
}
function playTrail() {
  if (!motion) { evs.forEach((e) => e.classList.add('in')); trail.classList.add('drawn', 'stamped'); return; }
  evs.forEach((e, i) => setTimeout(() => e.classList.add('in'), 120 + i * 260));
  setTimeout(() => trail.classList.add('drawn'), 520);
  setTimeout(() => trail.classList.add('stamped'), 1700);
}

// how-it-works thread: drawn once, when the steps scroll into view
const steps = $('[data-steps]');
const stepsSvg = $('.steps-thread', steps);
const stepsPath = $('path', stepsSvg);
function layoutSteps() {
  const r = steps.getBoundingClientRect();
  stepsSvg.setAttribute('width', r.width.toFixed(0)); stepsSvg.setAttribute('height', r.height.toFixed(0));
  stepsSvg.style.height = r.height + 'px';
  stepsPath.setAttribute('d', threadPath(steps, $$('.step .pin', steps), isNarrow()));
  stepsPath.style.setProperty('--len', (stepsPath.getTotalLength ? stepsPath.getTotalLength() : 1600).toFixed(0));
}
const io = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
  entries.forEach((en) => { if (en.isIntersecting) { en.target.classList.add('drawn'); io.unobserve(en.target); } });
}, { threshold: 0, rootMargin: '0px 0px -30% 0px' }) : null;

// ---------------------------------------------------------------- report tabs (WAI-ARIA tabs pattern)
const tabs = $$('[role=tab]');
function select(tab) {
  tabs.forEach((t) => { const on = t === tab; t.setAttribute('aria-selected', on); t.tabIndex = on ? 0 : -1; $('#' + t.getAttribute('aria-controls')).hidden = !on; });
}
tabs.forEach((t, i) => {
  t.addEventListener('click', () => select(t));
  t.addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; select(n); n.focus();
  });
});

// ---------------------------------------------------------------- the loupe: magnifies the cited log lines under the pointer
const loupe = $('.loupe'), inner = $('.loupe-inner'), zone = $('[data-loupe]'), wrap = $('.sheet-wrap');
if (zone && window.matchMedia('(hover: hover)').matches) {
  const Z = 1.9, R = 75;
  const clone = zone.cloneNode(true); clone.removeAttribute('data-loupe'); clone.style.width = zone.offsetWidth + 'px'; inner.appendChild(clone);
  zone.addEventListener('pointerenter', () => { clone.style.width = zone.offsetWidth + 'px'; loupe.classList.add('on'); });
  zone.addEventListener('pointerleave', () => loupe.classList.remove('on'));
  zone.addEventListener('pointermove', (e) => {
    const wr = wrap.getBoundingClientRect(), zr = zone.getBoundingClientRect();
    const x = e.clientX - wr.left, y = e.clientY - wr.top, zx = e.clientX - zr.left, zy = e.clientY - zr.top;
    loupe.style.left = x - R + 'px'; loupe.style.top = y - R + 'px';
    inner.style.transform = `translate(${R - zx * Z}px, ${R - zy * Z}px) scale(${Z})`;
  });
}

// ---------------------------------------------------------------- signup forms (hero and #join)
function turnstileToken(form) {
  const el = $('[name="cf-turnstile-response"]', form);
  return el ? el.value : undefined;
}

function resetTurnstile(form) {
  const w = $('.cf-turnstile', form);
  if (w && window.turnstile) { try { window.turnstile.reset(w); } catch { /* widget not ready */ } }
}

function wireSignup(form) {
  const email = $('input[name=email]', form);
  const github = $('input[name=github]', form);
  const updates = $('input[name=updates]', form);
  const honeypot = $('input[name=website]', form);
  const submit = $('button[type=submit]', form);
  const label = $('.btn-label', submit);
  const idleLabel = label.textContent;
  const formError = $('.form-error', form);
  const success = $('.form-success', form);
  const isFull = form.classList.contains('signup');
  let busy = false;
  let receipt = '';

  const fieldErr = (input) => input && $('#' + input.id + '-err');
  function showFieldError(input, message) {
    const err = fieldErr(input);
    input.setAttribute('aria-invalid', 'true');
    if (err) { err.textContent = message; err.hidden = false; }
  }
  function clearErrors() {
    for (const input of [email, github]) {
      if (!input) continue;
      input.removeAttribute('aria-invalid');
      const err = fieldErr(input);
      if (err) { err.hidden = true; err.textContent = ''; }
    }
    formError.hidden = true;
    formError.textContent = '';
  }
  function showFormError(message) {
    formError.textContent = message;
    formError.hidden = false;
  }
  function setBusy(on) {
    busy = on;
    form.classList.toggle('is-busy', on);
    form.setAttribute('aria-busy', String(on));
    submit.disabled = on;
    label.textContent = on ? 'Sending…' : idleLabel;
  }
  function showSuccess(addr) {
    for (const n of $$(':scope > :not(.form-success):not(.pin):not(.hp)', form)) n.hidden = true;
    const echo = $('[data-echo]', success);
    if (echo) echo.textContent = addr; // textContent: never HTML
    success.hidden = false;
    const st = $('.stamp', success);
    if (st && motion) {
      st.animate([{ transform: 'rotate(-5deg) scale(1.7)', opacity: 0 }, { transform: 'rotate(-5deg) scale(1)', opacity: 1 }],
        { duration: 240, easing: 'cubic-bezier(.3,1.6,.5,1)' });
    }
    const focusTarget = $('[data-success-focus]', success) || success;
    focusTarget.setAttribute('tabindex', '-1');
    focusTarget.focus({ preventScroll: !isFull });
  }

  // clear a field's error as soon as it is edited
  for (const input of [email, github]) input && input.addEventListener('input', () => {
    if (input.getAttribute('aria-invalid')) { input.removeAttribute('aria-invalid'); const err = fieldErr(input); if (err) err.hidden = true; }
  });
  // first interaction is a good moment to make sure a form token is ready
  form.addEventListener('focusin', () => { prefetchFormToken(); }, { once: true });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (busy) return; // repeated clicks and Enter presses while a request is in flight do nothing
    clearErrors();
    const v = validateSignup({ email: email.value, github: github ? github.value : '', updates: updates ? updates.checked : false });
    if (!v.ok) {
      if (v.errors.email) showFieldError(email, MESSAGES['email_' + v.errors.email]);
      if (v.errors.github) showFieldError(github, MESSAGES.github_invalid);
      (v.errors.email ? email : github).focus();
      return;
    }
    const ts = turnstileToken(form);
    if (ts === '') { showFormError('Please complete the anti-spam check above the button.'); return; }
    setBusy(true);
    try {
      let outcome;
      for (let attempt = 0; attempt < 2; attempt++) {
        const token = await formToken({ fresh: attempt > 0 });
        if (!token) { outcome = api.signupsClosed ? { kind: 'closed', message: MESSAGES.signups_closed } : { kind: 'error', message: MESSAGES.network }; break; }
        const body = { ...v.body, website: honeypot ? honeypot.value : '', form_token: token };
        if (body.github === null) delete body.github;
        if (ts !== undefined) body.turnstile_token = ts;
        const r = await call('/signup', { method: 'POST', json: body });
        outcome = signupOutcome(r.status, r.body);
        if (outcome.kind !== 'retry') break;
        outcome = { kind: 'error', message: 'This page was open for a long time. Please try again.' };
      }
      if (outcome.kind === 'success') {
        receipt = outcome.receipt;
        showSuccess(v.body.email);
      } else if (outcome.kind === 'field') {
        const input = outcome.field === 'github' ? github : email;
        if (input) { showFieldError(input, outcome.message); input.focus(); } else showFormError(outcome.message);
      } else {
        showFormError(outcome.message);
      }
      resetTurnstile(form);
    } finally {
      setBusy(false);
    }
  });

  // optional follow-up question, shown after a successful signup
  const followup = $('.followup', form);
  if (followup) {
    const done = $('.followup-done', form);
    let sent = false;
    followup.addEventListener('change', async (e) => {
      const value = e.target && e.target.value;
      if (!CI_FREQUENCIES.includes(value) || sent || !receipt) return;
      sent = true;
      for (const r of $$('input', followup)) r.disabled = true;
      const r = await call('/profile', { method: 'POST', json: { receipt, ci_failure_freq: value } });
      done.textContent = r.status === 204 ? 'Thanks — noted.' : "Thanks. We couldn't save that just now, and that's fine: it's optional.";
      done.hidden = false;
    });
  }
}

// ---------------------------------------------------------------- public counter (only ever a rounded-down figure ≥ 50)
async function loadCounter() {
  const box = $('[data-counter]');
  if (!box) return;
  const r = await call('/count');
  const text = r.status === 200 ? counterText(r.body) : null;
  if (text) { $('[data-counter-n]', box).textContent = text; box.hidden = false; }
}

// ---------------------------------------------------------------- start
root.classList.add('js');
setAnim();
const signupForms = $$('form[data-signup]');
signupForms.forEach(wireSignup);
// If the server isn't taking signups (email not configured), say so up front instead of letting people type.
prefetchFormToken().then(() => {
  if (!api.signupsClosed) return;
  for (const f of signupForms) {
    const err = $('.form-error', f);
    err.textContent = MESSAGES.signups_closed;
    err.hidden = false;
    $('button[type=submit]', f).disabled = true;
  }
});
loadCounter();
const relayout = () => { layoutTrail(); layoutSteps(); };
document.fonts.ready.then(() => { relayout(); playTrail(); if (io && motion) io.observe(steps); else steps.classList.add('drawn'); });
let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(relayout, 120); });
reduce.addEventListener('change', () => { motion = !reduce.matches; setAnim(); });
