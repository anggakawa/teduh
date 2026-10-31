/* App controller: state, filtering, sorting, list ⇄ detail, search mode, sheet states, modals, quick exit.
   No history writes and no storage: nothing about the visit is saved (recent searches live in memory). */
(function (P) {
  'use strict';
  var C = P.config, U = P.util;
  var $ = function (id) { return document.getElementById(id); };
  var state = {
    places: [], byId: {}, active: new Set(), onlyOk: false, openToday: false, q: '', words: [], sort: 'buka', dist: null,
    selected: null, listScroll: 0, recent: [], searchMode: false, order: [], loaded: false
  };
  var mobile = function () { return U.isMobile(); };

  // ---------- filtering & sorting ----------
  function words(q) { return U.fold(q).split(/\s+/).filter(Boolean); }
  function matchesQuery(p, ws) { return ws.every(function (w) { return p._d.qf.indexOf(w) >= 0; }); }
  function filtered(o) {
    o = Object.assign({ active: state.active, onlyOk: state.onlyOk, openToday: state.openToday, words: state.words }, o || {});
    return state.places.filter(function (p) {
      if (o.active.size && !o.active.has(p._d.group)) return false;
      if (o.onlyOk && p._d.needs_check) return false;
      if (o.openToday && !U.opensToday(p)) return false;
      return matchesQuery(p, o.words);
    });
  }
  function sortList(vis) {
    var byName = function (a, b) { return a._d.short.localeCompare(b._d.short, 'id'); };
    var ver = function (a, b) { return (a._d.needs_check ? 1 : 0) - (b._d.needs_check ? 1 : 0); };
    if (state.sort === 'jarak' && state.dist) {
      var d = function (p) { return state.dist[p.id] == null ? 1e12 : state.dist[p.id]; };
      vis.sort(function (a, b) { return d(a) - d(b) || byName(a, b); });
    } else if (state.sort === 'nama') vis.sort(byName);
    else {   // "Buka dulu": open/IGD → later → janji → closed → unknown, then verified first, then name
      var rk = {};
      vis.forEach(function (p) { rk[p.id] = U.hoursStatus(p).rank; });
      vis.sort(function (a, b) { return rk[a.id] - rk[b.id] || ver(a, b) || byName(a, b); });
    }
    return vis;
  }
  function isFiltered() { return state.active.size > 0 || state.onlyOk || state.openToday; }
  function filterParts() {
    var parts = [];
    if (state.onlyOk) parts.push('Terverifikasi');
    if (state.openToday) parts.push('Buka hari ini');
    C.groups.forEach(function (g) { if (state.active.has(g.id)) parts.push(g.short); });
    return parts;
  }
  function sortDef() { return C.sorts.filter(function (s) { return s.id === state.sort; })[0]; }

  // ---------- header + empty states ----------
  function header(vis) {
    var n = vis.length, f = isFiltered(), cap = function (s) { return s.charAt(0).toUpperCase() + s.slice(1); };
    var pinned = vis.filter(function (p) { return p._d.pin; }).length;
    if (state.q.trim()) {
      return {
        title: mobile() ? n + ' hasil untuk “' + state.q.trim() + '”' : n + ' hasil',
        sub: mobile() ? cap(sortDef().sub) + ' · cari nama, layanan, kelurahan' : (f ? filterParts().join(' · ') : 'Semua kategori') + ' · nama, layanan, kelurahan',
        slot: mobile() && state.searchMode ? 'map' : f ? 'clear' : n ? 'sort' : null, live: n + ' hasil'
      };
    }
    if (f) return { title: n + ' layanan cocok', sub: filterParts().join(' · '), slot: 'clear', live: n + ' layanan cocok' };
    return {
      title: n + ' layanan',
      sub: mobile() ? 'Banjarbaru & sekitar · ' + sortDef().sub : pinned + ' di peta · ' + (n - pinned) + ' tanpa titik lokasi',
      slot: 'sort', live: n + ' layanan'
    };
  }

  function emptyState(vis) {
    if (vis.length) return null;
    if (state.words.length) {
      var broader = C.broaderTerms.filter(function (t) { return U.fold(t) !== U.fold(state.q.trim()); }).map(function (t) {
        return { term: t, n: filtered({ active: new Set(), onlyOk: false, openToday: false, words: words(t) }).length };
      }).filter(function (b) { return b.n > 0; }).slice(0, 3);
      return { kind: 'search', q: state.q.trim(), broader: broader };
    }
    var cats = C.groups.filter(function (g) { return state.active.has(g.id); });
    var noun = cats.length === 1 ? cats[0].noun : 'layanan';
    var cond = [];
    if (state.onlyOk) cond.push('terverifikasi');
    if (state.openToday) cond.push('buka hari ini');
    var un = state.onlyOk ? filtered({ onlyOk: false }).length : 0;
    var sentence = 'Belum ada ' + noun + (cond.length ? ' yang ' + cond.join(' dan ') : ' dengan filter ini') + '.' +
      (un ? ' Ada ' + un + ' tempat yang belum dicek.' : '');
    var cross = null, cs = cats.length === 1 && C.crossSuggest[cats[0].id];
    if (cs) {
      var cn = filtered({ active: new Set(), onlyOk: false, openToday: false, words: words(cs.q) }).length;
      if (cn) cross = { label: cs.label, q: cs.q, n: cn };
    }
    return { kind: 'filter', sentence: sentence, unchecked: un, cross: cross };
  }

  // ---------- map framing ----------
  function fitPad() {
    if (!mobile()) return { padding: [C.fitPadding, C.fitPadding] };
    var top = ($('chips').getBoundingClientRect().bottom || 150) + 8;
    return { paddingTopLeft: [24, top], paddingBottomRight: [24, P.sheet.height() + 16] };
  }
  // Area of the map container where a selected pin is fully visible.
  function band() {
    var m = $('map').getBoundingClientRect();
    if (!mobile()) return { top: 64, bottom: m.height - 40, left: 24, right: m.width - 24 };
    return { top: $('toprow').getBoundingClientRect().bottom + 8, bottom: window.innerHeight - P.sheet.height() - 8, left: 0, right: m.width };
  }

  // ---------- render ----------
  function refresh(o) {
    o = o || {};
    if (!state.loaded) return;
    var vis = sortList(filtered());
    var pinned = vis.filter(function (p) { return p._d.pin; }), unp = vis.filter(function (p) { return !p._d.pin; });
    state.order = pinned.concat(unp).map(function (p) { return p.id; });
    P.ui.renderList(vis, { dist: state.dist, words: state.words }, {
      pick: function (id) { select(id, 'list'); },
      hover: function (id) { if (!mobile()) { P.map.hover(id); P.ui.markListHover(id); } }
    });
    P.ui.renderHeader(header(vis));
    P.ui.renderSort(state.sort, !!state.dist);
    P.ui.renderEmpty(emptyState(vis), {
      clear: clearFilters,
      showun: function () { state.onlyOk = false; rechips(); refresh({ fit: true, sheet: 'half' }); },
      clearq: function () { setQuery(''); exitSearch(); refresh({ fit: true }); $('q').focus(); },
      search: function (q) { setQuery(q); addRecent(q); refresh({ fit: true, sheet: 'half' }); }
    });
    if (o.sheet && mobile() && !state.selected) P.sheet.set(o.sheet);
    var ids = pinned.map(function (p) { return p.id; });
    P.map.show(ids, !!o.fit, fitPad());
    $('mapNote').hidden = ids.length > 0;
    P.ui.markListSelected(state.selected);
  }

  function rechips() {
    P.ui.renderChips(state, {
      ok: function () { state.onlyOk = !state.onlyOk; afterFilter(); },
      today: function () { state.openToday = !state.openToday; afterFilter(); },
      cat: function (gid) { if (state.active.has(gid)) state.active.delete(gid); else state.active.add(gid); afterFilter(); }
    });
  }
  function afterFilter() {
    if (state.selected) closeDetail(true);
    rechips(); $('chips').scrollLeft = 0; $('listScroll').scrollTop = 0;
    refresh({ fit: true, sheet: 'half' });
  }
  function clearFilters() {
    state.active.clear(); state.onlyOk = false; state.openToday = false;
    rechips(); refresh({ fit: true, sheet: 'half' });
  }

  // ---------- search ----------
  function setQuery(q) {
    $('q').value = q; state.q = q; state.words = words(q);
    $('qClear').hidden = !q;
  }
  function addRecent(q) {
    q = (q || '').trim(); if (!q) return;
    state.recent = [q].concat(state.recent.filter(function (r) { return U.fold(r) !== U.fold(q); })).slice(0, 5);
    renderExtra();
  }
  function renderExtra() {
    P.ui.renderSearchExtra(state.recent, {
      pick: function (q) { setQuery(q); addRecent(q); submitSearch(); },
      remove: function (i) { state.recent.splice(i, 1); renderExtra(); }
    });
  }
  function enterSearch() {
    if (state.searchMode) return;
    if (state.selected) closeDetail(true);
    state.searchMode = true;
    document.body.dataset.search = '1';
    $('searchExtra').hidden = !mobile();
    if (mobile()) requestAnimationFrame(function () { P.sheet.set('full'); });
    refresh();
  }
  function exitSearch() {
    state.searchMode = false;
    document.body.dataset.search = '0';
    $('searchExtra').hidden = true;
  }
  function submitSearch() {
    addRecent(state.q);
    exitSearch();
    $('q').blur();
    refresh({ fit: true, sheet: 'half' });
  }

  // ---------- list ⇄ detail ----------
  function setMode(mode) {
    document.body.dataset.mode = mode;
    $('viewList').hidden = mode !== 'list';
    $('viewDetail').hidden = mode !== 'detail';
    $('mapBack').hidden = mode !== 'detail';
  }

  function select(id, from) {
    if (!id) {
      if (from === 'map' && mobile() && !state.selected && P.sheet.get() !== 'peek') P.sheet.set('peek');
      return;
    }
    var p = state.byId[id]; if (!p) return;
    if (state.searchMode) { addRecent(state.q); exitSearch(); $('q').blur(); }
    if (!state.selected) state.listScroll = $('listScroll').scrollTop;
    state.selected = id;
    P.ui.renderDetail(p, { dist: state.dist, onPhones: openPhones });
    var i = state.order.indexOf(id);
    $('detailPos').textContent = i >= 0 ? (i + 1) + ' dari ' + state.order.length : '';
    setMode('detail');
    P.ui.markListSelected(id);
    if (mobile()) P.sheet.set('half');
    P.map.hover(null);
    P.map.select(p._d.pin ? id : null, !!p._d.pin, band);
    if (from !== 'map' && from !== 'hash') (mobile() ? $('mapBack') : $('detailBack')).focus({ preventScroll: true });
  }

  function closeDetail(silent) {
    var prev = state.selected;
    if (!prev) return;
    state.selected = null;
    setMode('list');
    P.map.deselect();                               // the map stays where it is
    P.ui.markListSelected(null);
    if (mobile() && !silent) P.sheet.set('peek');
    $('listScroll').scrollTop = state.listScroll;
    if (!silent) {
      var b = document.querySelector('.card[data-id="' + CSS.escape(prev) + '"]');
      if (b) b.focus({ preventScroll: true });
    }
  }

  // ---------- quick exit: one tap, no confirm, replaces this history entry ----------
  function quickExit() {
    try { document.body.innerHTML = ''; } catch (e) { /* ignore */ }
    location.replace(C.quickExitUrl);
  }

  // ---------- modals (emergency, phone chooser): focus trapped, Esc / ✕ / scrim / swipe down close ----------
  var lastFocus = null;
  function openModal(id, from) {
    var m = $(id); lastFocus = from || document.activeElement;
    m.hidden = false; document.body.classList.add('has-modal');
    m.querySelector('.modal-card [data-close]').focus();
  }
  function closeModal() {
    var open = document.querySelector('.modal:not([hidden])');
    if (!open) return false;
    open.hidden = true; document.body.classList.remove('has-modal');
    if (lastFocus) lastFocus.focus({ preventScroll: true });
    return true;
  }
  function openPhones(p, btn) { P.ui.renderPhoneChooser(p); openModal('phoneModal', btn); }
  function trapFocus(e) {
    var m = document.querySelector('.modal:not([hidden]) .modal-card'); if (!m || e.key !== 'Tab') return;
    var f = m.querySelectorAll('a[href], button:not([disabled])'); if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { last.focus(); e.preventDefault(); }
    else if (!e.shiftKey && document.activeElement === last) { first.focus(); e.preventDefault(); }
  }
  function swipeToClose(card) {
    var y0 = null;
    card.addEventListener('pointerdown', function (e) { if (!e.target.closest('a, button')) y0 = e.clientY; });
    window.addEventListener('pointerup', function (e) { if (y0 != null && e.clientY - y0 > 60) closeModal(); y0 = null; });
  }

  // ---------- legend ----------
  function toggleLegend(force) {
    var open = typeof force === 'boolean' ? force : $('legendPop').hidden;
    $('legendPop').hidden = !open;
    $('legendBtn').setAttribute('aria-expanded', open);
    return open;
  }

  // ---------- location (on demand only, never stored) ----------
  function locate() {
    if (!navigator.geolocation) { P.ui.toast('Lokasi tidak tersedia di perangkat ini.'); return; }
    P.ui.toast('Mencari lokasi Anda…');
    navigator.geolocation.getCurrentPosition(function (pos) {
      var here = L.latLng(pos.coords.latitude, pos.coords.longitude);
      state.dist = {};
      state.places.forEach(function (p) { if (p._d.pin) state.dist[p.id] = here.distanceTo([p._d.pin.lat, p._d.pin.lng]); });
      state.sort = 'jarak';
      P.map.showYou(here.lat, here.lng);
      refresh();
      P.ui.toast('Diurutkan dari yang terdekat. Lokasi tidak disimpan.');
    }, function () { P.ui.toast('Lokasi tidak bisa diambil. Izinkan akses lokasi lalu coba lagi.'); }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
  }

  function wire() {
    $('detailBack').onclick = function () { closeDetail(); };
    $('mapBack').onclick = function () { closeDetail(); };
    $('quickExit').onclick = quickExit;
    $('emgRow').onclick = function () { openModal('emgModal', $('emgRow')); };
    document.querySelectorAll('.modal').forEach(function (m) {
      m.addEventListener('click', function (e) { if (e.target.closest('[data-close]')) closeModal(); });
      swipeToClose(m.querySelector('.modal-card'));
    });
    $('legendBtn').onclick = function () { toggleLegend(); };
    $('legendPop').addEventListener('click', function (e) { if (e.target.closest('[data-close]')) { toggleLegend(false); $('legendBtn').focus(); } });
    document.addEventListener('pointerdown', function (e) {
      if (!$('legendPop').hidden && !e.target.closest('#legendPop, #legendBtn')) toggleLegend(false);
    });
    $('locateBtn').onclick = locate;
    $('zoomIn').onclick = function () { P.map.getMap().zoomIn(); };
    $('zoomOut').onclick = function () { P.map.getMap().zoomOut(); };
    $('tileRetry').onclick = function () { $('tileError').hidden = true; P.map.retryTiles(); };
    $('clearFilters').onclick = clearFilters;
    $('toMap').onclick = function () { submitSearch(); if (mobile()) P.sheet.set('peek'); };
    $('sort').addEventListener('change', function (e) { state.sort = e.target.value; refresh(); });
    $('shead').addEventListener('click', function (e) {
      if (mobile() && P.sheet.get() === 'peek' && !e.target.closest('button, select, label')) P.sheet.set('half');
    });

    // search
    var q = $('q'), t;
    q.addEventListener('focus', enterSearch);
    q.addEventListener('input', function () {
      $('qClear').hidden = !q.value;
      if (!state.searchMode) enterSearch();
      clearTimeout(t);
      t = setTimeout(function () { state.q = q.value; state.words = words(q.value); $('listScroll').scrollTop = 0; refresh({ fit: !mobile() }); }, 120);
    });
    $('searchForm').addEventListener('submit', function (e) { e.preventDefault(); clearTimeout(t); state.q = q.value; state.words = words(q.value); submitSearch(); });
    $('qClear').onclick = function () { setQuery(''); refresh({ fit: !mobile() }); q.focus(); };
    $('qBack').onclick = function () { setQuery(''); exitSearch(); q.blur(); refresh({ fit: true, sheet: 'peek' }); };
    // desktop: leaving the field ends search mode (the ‹ icon) but keeps the query
    q.addEventListener('blur', function () {
      setTimeout(function () {
        if (!mobile() && document.activeElement !== q && !document.activeElement.closest('#searchForm')) exitSearch();
      }, 0);
    });

    var escTimes = [];
    document.addEventListener('keydown', function (e) {
      trapFocus(e);
      if (e.key !== 'Escape') return;
      var now = Date.now();
      escTimes = escTimes.filter(function (x) { return now - x < 1500; }); escTimes.push(now);
      if (escTimes.length >= 3) { quickExit(); return; }
      if (closeModal()) return;
      if (!$('legendPop').hidden) { toggleLegend(false); $('legendBtn').focus(); return; }
      if (P.map.getMap()) P.map.getMap().closePopup();
      if (state.selected) closeDetail();
      else if (state.searchMode) { exitSearch(); q.blur(); refresh({ sheet: 'half' }); }
    });
    var wasMobile = mobile();
    window.addEventListener('resize', function () {
      P.map.invalidate();
      if (mobile() !== wasMobile) { wasMobile = mobile(); refresh(); }
    });
  }

  function start() {
    P.map.init($('map'), {
      onSelect: select,
      onPan: function () { if (mobile() && P.sheet.get() !== 'peek' && !state.searchMode) P.sheet.set('peek'); },
      onHover: function (id) { if (!mobile()) P.ui.markListHover(id); },
      onTiles: function (ok) { $('tileError').hidden = ok; }
    });
    P.sheet.init($('sheet'), function () { P.map.invalidate(); }, { onDismiss: function () { closeDetail(); } });
    P.ui.renderLegend();
    renderExtra();
    rechips();
    wire();

    P.data.load().then(function (d) {
      state.places = d.places;
      d.places.forEach(function (p) { state.byId[p.id] = p; });
      state.loaded = true;
      P.map.setPlaces(d.places);
      P.ui.renderHotlines(d.hotlines);
      var m = d.meta || {}, c = m.counts || {};
      $('dataMeta').textContent = 'Data: ' + (c.places || d.places.length) + ' tempat · ' + (c.pinned || 0) + ' di peta · ' + (c.unpinned || 0) +
        ' tanpa titik · ' + (c.needs_check || 0) + ' belum dicek' + (d.via === 'file-fallback' ? ' · mode file' : '') + '. Peta © OpenStreetMap.';
      refresh();
      if (!mobile()) P.map.fit(P.map.pinnedIds());      // desktop: all pins, padding 48
      document.body.dataset.ready = '1';
      window.__PETA_STATE__ = { total: d.places.length, pinned: P.map.pinnedCount(), via: d.via, get: function () { return state; } };
      var hash = decodeURIComponent(location.hash.slice(1));
      if (hash && state.byId[hash]) select(hash, 'hash');
    }).catch(function (err) {
      console.error(err);
      P.ui.renderHeader({ title: 'Data belum bisa dimuat', sub: '', slot: null });
      P.ui.renderDataError(err && err.message);
      document.body.dataset.ready = 'error';
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})(window.Peta);
