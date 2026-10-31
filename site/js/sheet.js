/* Mobile bottom sheet (SPEC §4): peek 288 / half 55% / full (list: below the chip row, detail: below the
   top row). Drag the handle/header — or, below full, the content itself; fling > 0.5 px/ms moves one step.
   Handle tap: one step up, full → half. Content scrolls only at full; there, pulling down at scrollTop 0
   drags the sheet. In the detail, dragging below peek closes the detail (back to the list at peek).
   Desktop (≥900px) = static panel.

   Touch input uses touch events (non-passive touchmove, so a drag can preventDefault the browser's own
   pan); mouse/pen use pointer events. The sheet itself is `touch-action: none` (only the content at full
   is `pan-y`): with `pan-y` on the whole sheet the browser claimed every vertical swipe and sent
   pointercancel on the first move, so the sheet never followed the finger. */
(function (P) {
  'use strict';
  var U = P.util;
  var el, state = 'peek', h = 0, drag = null, onChange = function () {}, onDismiss = null, suppressClick = false;
  var DISMISS = 64;   // px below peek, in the detail, that closes it

  function vh() { return window.innerHeight; }
  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name); }
  function detail() { return document.body.dataset.mode === 'detail'; }
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

  // ---- gesture core (shared by touch and pointer) ----
  function begin(target, y, t) {
    if (!U.isMobile()) return false;
    if (target.closest('select, input, .sort, .linkbtn')) return false;
    var inBody = target.closest('.sbody');
    if (inBody && state === 'full' && inBody.scrollTop > 0) return false;    // at full the content scrolls
    drag = { y: y, h0: h, lastY: y, lastT: t, moved: false, body: inBody, v: 0 };
    return true;
  }
  // -> true when the sheet consumed the move (caller prevents the browser default)
  function step(y, t) {
    if (!drag) return false;
    var dy = y - drag.y;
    if (!drag.moved) {
      if (Math.abs(dy) < 8) return false;
      if (drag.body && state === 'full' && (dy < 0 || drag.body.scrollTop > 0)) { drag = null; return false; }  // scroll
      drag.y = y; dy = 0;                                       // start from here: no jump by the slop
    }
    drag.moved = true;
    var minH = detail() && onDismiss ? Math.max(80, heightFor('peek') - DISMISS * 2) : Math.max(120, heightFor('peek') - 40);
    var px = Math.max(minH, Math.min(vh() - fullTop(), drag.h0 - dy));
    drag.v = (y - drag.lastY) / Math.max(1, t - drag.lastT);
    drag.lastY = y; drag.lastT = t;
    apply(px, false);
    return true;
  }
  function finish() {
    if (!drag) return;
    var d = drag; drag = null;
    if (!d.moved) return;
    suppressClick = true; setTimeout(function () { suppressClick = false; }, 0);
    if (detail() && onDismiss && h < heightFor('peek') - DISMISS / 2 && (state === 'peek' || d.v > 0.5 || h < heightFor('peek') - DISMISS)) {
      onDismiss(); return;          // closes the detail; the app snaps the list to peek
    }
    set(nearest(h, d.v));
  }

  // touch: touchmove must be non-passive so a sheet drag can stop the page/content pan
  function tStart(e) { if (e.touches.length === 1) begin(e.target, e.touches[0].clientY, e.timeStamp); else drag = null; }
  function tMove(e) { if (drag && e.touches.length === 1 && step(e.touches[0].clientY, e.timeStamp) && e.cancelable) e.preventDefault(); }
  // mouse / pen
  function pStart(e) { if (e.pointerType === 'touch' || e.button > 0) return; begin(e.target, e.clientY, e.timeStamp); }
  function pMove(e) { if (e.pointerType !== 'touch' && drag && step(e.clientY, e.timeStamp) && e.cancelable) e.preventDefault(); }
  function pEnd(e) { if (e.pointerType !== 'touch') finish(); }

  function init(sheetEl, cb, opts) {
    el = sheetEl; onChange = cb || onChange; onDismiss = (opts && opts.onDismiss) || null;
    el.addEventListener('touchstart', tStart, { passive: true });
    el.addEventListener('touchmove', tMove, { passive: false });
    el.addEventListener('touchend', finish);
    el.addEventListener('touchcancel', finish);
    el.addEventListener('pointerdown', pStart);
    window.addEventListener('pointermove', pMove, { passive: false });
    window.addEventListener('pointerup', pEnd);
    window.addEventListener('pointercancel', pEnd);
    el.addEventListener('click', function (e) { if (suppressClick) { e.stopPropagation(); e.preventDefault(); } }, true);
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
