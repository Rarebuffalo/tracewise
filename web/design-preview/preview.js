/* Tracewise design preview — interactions. No network requests; the forms never submit anywhere.
   Everything degrades to a complete static page: with JS off or prefers-reduced-motion, all content is visible. */
(() => {
  'use strict';
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

  // ---------------------------------------------------------------- forms (preview only: validate, then show the success state; nothing is sent)
  function setState(form, state) {
    const email = $('input[type=email]', form), err = $('.err', form), ok = $('.form-success', form);
    const fields = $$('.field, .consent, button[type=submit], .form-note', form).filter((n) => !n.closest('.form-success'));
    if (state === 'error') { email.setAttribute('aria-invalid', 'true'); if (err) { err.hidden = false; email.setAttribute('aria-describedby', 'email-err'); } email.focus(); }
    else { email.removeAttribute('aria-invalid'); if (err) err.hidden = true; }
    const success = state === 'success';
    if (ok) ok.hidden = !success;
    if (form.classList.contains('signup')) fields.forEach((n) => { n.hidden = success; });
    const echo = $('[data-echo]', form); if (echo && email.value) echo.textContent = email.value;
    if (success && ok) { const st = $('.stamp', ok); if (st && motion) { st.animate([{ transform: 'rotate(-5deg) scale(1.7)', opacity: 0 }, { transform: 'rotate(-5deg) scale(1)', opacity: 1 }], { duration: 240, easing: 'cubic-bezier(.3,1.6,.5,1)' }); } }
  }
  $$('[data-preview-form]').forEach((form) => {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const email = $('input[type=email]', form);
      setState(form, email.value && email.checkValidity() ? 'success' : 'error');
    });
  });

  // ---------------------------------------------------------------- review panel (preview only)
  const toggle = $('.review-toggle'), body = $('#review-body');
  toggle.addEventListener('click', () => { const open = body.hidden; body.hidden = !open; toggle.setAttribute('aria-expanded', open); });
  $('[data-opt=motion]').checked = motion;
  $('[data-opt=motion]').addEventListener('change', (e) => { motion = e.target.checked; setAnim(); evs.forEach((x) => x.classList.remove('in')); trail.classList.remove('drawn', 'stamped'); requestAnimationFrame(() => requestAnimationFrame(playTrail)); });
  $('[data-opt=grain]').addEventListener('change', (e) => document.body.classList.toggle('no-grain', !e.target.checked));
  $$('input[name=ctr]').forEach((r) => r.addEventListener('change', () => { $('[data-counter]').hidden = r.value !== 'shown' || !r.checked; }));
  $$('[data-state]').forEach((b) => b.addEventListener('click', () => { const f = $('form.signup'); setState(f, b.dataset.state); f.scrollIntoView({ behavior: motion ? 'smooth' : 'auto', block: 'center' }); }));

  // ---------------------------------------------------------------- start
  setAnim();
  const relayout = () => { layoutTrail(); layoutSteps(); };
  document.fonts.ready.then(() => { relayout(); playTrail(); if (io && motion) io.observe(steps); else steps.classList.add('drawn'); });
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(relayout, 120); });
  reduce.addEventListener('change', () => { motion = !reduce.matches; setAnim(); });
})();
