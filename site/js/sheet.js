/* Mobile bottom sheet (SPEC §4): peek 288 / half 55% / full (list: below the chip row, detail: below the
   top row). Drag the handle/header — or, below full, the content itself; fling > 0.5 px/ms moves one step.
   Handle tap: one step up, full → half. Content scrolls only at full. Desktop (≥900px) = static panel. */
(function (P) {
  'use strict';
  var U = P.util;
  var el, state = 'peek', h = 0, drag = null, onChange = function () {}, suppressClick = false;

  function vh() { return window.innerHeight; }
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name); }
  function fullTop() {
    var b = document.body, ref;
    if (b.dataset.mode === 'detail') ref = document.getElementById('toprow');
    else if (b.dataset.search === '1') ref = document.getElementById('searchExtra');
    else ref = document.getElementById('chips');
    if (!ref || !ref.getBoundingClientRect().height) ref = document.getElementById('toprow');
    return Math.round((ref ? ref.getBoundingClientRect().bottom : 60) + (b.dataset.mode === 'detail' ? 8 : 0));
  }
  function heightFor(s) {
    var full = vh() - fullTop();
    if (s === 'peek') return Math.min(parseInt(css('--sheet-peek'), 10) || 288, full);
    if (s === 'full') return full;
    return Math.min(Math.round(vh() * (parseFloat(css('--sheet-half')) || 0.55)), full);
  }

  function apply(px, animate) {
    h = px;
    el.classList.toggle('is-dragging', !animate);
    el.style.height = px + 'px';
    document.documentElement.style.setProperty('--sheet-h', px + 'px');
  }

  function set(s, opts) {
    if (!el || !U.isMobile()) return;
    var changed = s !== state;
    state = s;
    el.dataset.state = s;
    apply(heightFor(s), true);
    var g = document.getElementById('grabBtn');
    if (g) g.setAttribute('aria-label', s === 'full' ? 'Perkecil daftar' : 'Perbesar daftar');
    if (!(opts && opts.silent)) onChange(s, changed);
  }

  function nearest(px, v) {
    var order = ['peek', 'half', 'full'];
    if (Math.abs(v) > 0.5) {
      var i = order.indexOf(state) + (v < 0 ? 1 : -1);
      return order[Math.max(0, Math.min(2, i))];
    }
    var best = 'half', d = 1e9;
    order.forEach(function (s) { var dd = Math.abs(heightFor(s) - px); if (dd < d) { d = dd; best = s; } });
    return best;
  }

  function start(e) {
    if (!U.isMobile() || e.button > 0) return;
    if (e.target.closest('select, input, .sort, .linkbtn, #grabBtn')) return;
    var inBody = e.target.closest('.sbody');
    if (inBody && state === 'full' && !(inBody.scrollTop <= 0)) return;      // at full the content scrolls
    drag = { y: e.clientY, h0: h, lastY: e.clientY, lastT: e.timeStamp, moved: false, body: inBody, v: 0 };
  }
  function move(e) {
    if (!drag) return;
    var dy = e.clientY - drag.y;
    if (!drag.moved) {
      if (Math.abs(dy) < 8) return;
      if (drag.body && state === 'full' && dy < 0) { drag = null; return; }   // full + swipe up = scroll
    }
    drag.moved = true;
    var px = Math.max(120, Math.min(vh() - fullTop(), drag.h0 - dy));
    drag.v = (e.clientY - drag.lastY) / Math.max(1, e.timeStamp - drag.lastT);
    drag.lastY = e.clientY; drag.lastT = e.timeStamp;
    apply(px, false);
    if (e.cancelable) e.preventDefault();
  }
  function end() {
    if (!drag) return;
    var d = drag; drag = null;
    if (d.moved) { suppressClick = true; setTimeout(function () { suppressClick = false; }, 0); set(nearest(h, d.v)); }
  }

  function init(sheetEl, cb) {
    el = sheetEl; onChange = cb || onChange;
    el.addEventListener('pointerdown', start);
    el.addEventListener('click', function (e) { if (suppressClick) { e.stopPropagation(); e.preventDefault(); } }, true);
    window.addEventListener('pointermove', move, { passive: false });
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
    document.getElementById('grabBtn').addEventListener('click', function () {
      set(state === 'peek' ? 'half' : state === 'half' ? 'full' : 'half');
    });
    window.addEventListener('resize', function () {
      if (U.isMobile()) set(state, { silent: true });
      else { el.style.height = ''; document.documentElement.style.removeProperty('--sheet-h'); }
    });
    if (U.isMobile()) set('peek', { silent: true });
  }

  P.sheet = { init: init, set: set, get: function () { return state; }, height: function () { return U.isMobile() ? h : 0; }, fullTop: fullTop };
})(window.Peta);
