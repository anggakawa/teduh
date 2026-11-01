/* Small helpers: escaping, link detection, generic value rendering. */
(function (P) {
  'use strict';
  var DAYS = ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu', 'minggu'];
  var UNKNOWN = /^\s*(unknown|tidak diketahui|null|-)\s*$/i;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // Escape, then turn http(s) URLs into links. Input is plain text from data files.
  function linkify(s) {
    return esc(s).replace(/https?:\/\/[^\s;,)<]+/g, function (u) {
      var clean = u.replace(/[.]+$/, '');
      return '<a href="' + clean + '" target="_blank" rel="noopener noreferrer">' + clean + '</a>' + u.slice(clean.length);
    });
  }

  // senin_jumat -> "Senin–Jumat", poli_senin_kamis -> "Poli Senin–Kamis", rs_igd -> "RS IGD"
  function humanizeKey(k) {
    var parts = String(k).split(/[_.]/).filter(Boolean), out = [];
    parts.forEach(function (w, i) {
      var isDay = DAYS.indexOf(w.toLowerCase()) >= 0;
      var prevDay = i > 0 && DAYS.indexOf(parts[i - 1].toLowerCase()) >= 0;
      var word = /^(rs|igd|bpjs|mcu|abk|wa|ppa)$/i.test(w) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1);
      if (isDay && prevDay) out[out.length - 1] += '–' + word; else out.push(word);
    });
    return out.join(' ');
  }

  function isEmpty(v) {
    if (v == null) return true;
    if (typeof v === 'string') return v.trim() === '' || UNKNOWN.test(v);
    if (Array.isArray(v)) return v.every(isEmpty);
    if (typeof v === 'object') return Object.keys(v).every(function (k) { return isEmpty(v[k]); });
    return false;
  }

  // Render any JSON value (string / list / object) as safe HTML.
  function renderValue(v, labels) {
    if (isEmpty(v)) return '';
    if (typeof v !== 'object') return '<span>' + linkify(v) + '</span>';
    if (Array.isArray(v)) {
      var items = v.filter(function (x) { return !isEmpty(x); });
      if (items.length === 1 && typeof items[0] !== 'object') return '<span>' + linkify(items[0]) + '</span>';
      return '<ul class="vlist">' + items.map(function (x) { return '<li>' + renderValue(x, labels) + '</li>'; }).join('') + '</ul>';
    }
    var keys = Object.keys(v).filter(function (k) { return !isEmpty(v[k]); });
    return '<dl class="kv">' + keys.map(function (k) {
      var label = (labels && labels[k]) || humanizeKey(k);
      return '<dt>' + esc(label) + '</dt><dd>' + renderValue(v[k], labels) + '</dd>';
    }).join('') + '</dl>';
  }

  // Search token match. Tokens of 3 letters or fewer match whole words only (so "kis" never hits
  // "kisaran", "rs" never hits "kursus"); longer tokens match anywhere, as you type.
  var SHORT_TOKEN = 3;
  function reEscape(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function matchToken(text, w) {
    if (w.length > SHORT_TOKEN) return text.indexOf(w) >= 0;
    return new RegExp('(^|[^a-z0-9])' + reEscape(w) + '($|[^a-z0-9])').test(text);
  }

  function fold(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }

  function isMobile() { return window.matchMedia('(max-width: 899.98px)').matches; }
  function reducedMotion() { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; }

  // Inline stroke icon from config.icons (aria-hidden; label the parent instead).
  function icon(name, cls) {
    return '<svg class="ic' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true">' + (P.config.icons[name] || '') + '</svg>';
  }

  // "2026-10-31" -> "Okt 2026"
  function monthYear(iso) {
    var m = /^(\d{4})-(\d{2})/.exec(iso || '');
    return m ? P.config.months[+m[2] - 1] + ' ' + m[1] : '';
  }
  function checkedLabel(iso) { var my = monthYear(iso); return my ? 'dicek ' + my : ''; }

  // "Now" in the user's zone (Asia/Makassar = WITA). `?now=2026-10-31T13:56` overrides it for demos and
  // screenshots (read from the URL only — nothing is stored).
  function now() {
    var m = /[?&]now=(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/.exec(location.search);
    if (m) {
      var d = new Date(m[1] + ':00+08:00');
      if (!isNaN(d)) return d;
    }
    return new Date();
  }
  function wita(d) {
    var parts = new Intl.DateTimeFormat('en-GB', { timeZone: P.config.timeZone, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
      .formatToParts(d || now());
    var o = {};
    parts.forEach(function (x) { o[x.type] = x.value; });
    return { day: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(o.weekday), min: (+o.hour % 24) * 60 + (+o.minute) };
  }
  // Weekday in the user's zone, Monday = 0.
  function todayIdx(d) { return wita(d).day; }

  function span(v) {
    var m = /^(\d{2})\.(\d{2})–(\d{2})\.(\d{2})$/.exec(v || '');
    return m ? { s: +m[1] * 60 + +m[2], e: +m[3] * 60 + +m[4], from: m[1] + '.' + m[2], text: v } : null;
  }

  function nextOpen(week, t) {
    for (var i = 1; i <= 7; i++) {
      var d = (t + i) % 7, sp = span(week[d]);
      if (sp) return { when: i === 1 ? 'besok' : P.config.days[d], from: sp.from };
    }
    return null;
  }

  // SPEC §6 hours rules, evaluated against the current WITA time. Returns
  // { kind, rank, html (card line, open words wrapped in <b class="open">), text (plain), open, today }.
  // rank feeds the default "Buka dulu" sort: open/IGD-only 0 → later 1 → janji 2 → closed 3 → unknown 4 (d01: a hospital whose poli has closed sorts with closed).
  function hoursStatus(p, d) {
    var h = p._d.hours, w = wita(d), t = w.day;
    var lab = h && h.label && h.label !== 'Buka' ? h.label : '';
    var igd = !!(h && h.igd24);
    function r(kind, rank, open, lead, rest) {
      var html = (lead ? '<b class="open">' + esc(lead) + '</b>' + (rest ? ' ' : '') : '') + esc(rest || '');
      return { kind: kind, rank: rank, open: open, html: html, text: (lead ? lead + (rest ? ' ' : '') : '') + (rest || '') };
    }
    if (h && h.week) {
      var v = h.week[t], sp = span(v), nx;
      if (sp && w.min >= sp.s && w.min < sp.e) return r('open', 0, true, lab ? lab + ' buka sekarang' : 'Buka sekarang', sp.text);
      if (sp && w.min < sp.s) return r('later', 1, true, lab ? lab + ' buka nanti' : 'Buka nanti', sp.text);
      if (sp) return r('done', 3, false, igd ? 'IGD 24 jam' : '', (igd ? '· ' + (lab || 'Buka').toLowerCase() + ' ' : 'Hari ini ') + sp.text + ' · sudah tutup');
      if (igd) return r('igd', 0, true, 'IGD 24 jam', '· jadwal poli: telepon dulu');
      nx = nextOpen(h.week, t);
      if (v === 'tutup') return r('closed', 3, false, '', 'Tutup hari ini' + (nx ? ' · buka ' + nx.when + ' ' + nx.from : ''));
      return r('noday', 3, false, '', 'Tidak ada jadwal hari ini' + (nx ? ' · buka ' + nx.when + ' ' + nx.from : ''));
    }
    if (igd) return r('igd', 0, true, 'IGD 24 jam', '· jadwal poli: telepon dulu');
    if (p._d.booking_janji) return r('janji', 2, null, '', 'Dengan janji temu');
    return r('unknown', 4, null, '', 'Jam belum diketahui · telepon dulu');
  }

  // "Buka hari ini" chip: the place has opening hours today (or a 24h IGD).
  function opensToday(p, d) {
    var h = p._d.hours;
    if (!h) return false;
    if (h.igd24) return true;
    return !!(h.week && span(h.week[todayIdx(d)]));
  }

  // Highlight query words (already folded) inside plain text → safe HTML with <mark>.
  function highlight(text, words) {
    var src = String(text || ''), f = fold(src), marks = [];
    words.forEach(function (wd) {
      if (!wd) return;
      var i = 0;
      while ((i = f.indexOf(wd, i)) >= 0) { marks.push([i, i + wd.length]); i += wd.length; }
    });
    if (!marks.length) return esc(src);
    marks.sort(function (a, b) { return a[0] - b[0]; });
    var out = '', pos = 0;
    marks.forEach(function (m) {
      if (m[0] < pos) return;
      out += esc(src.slice(pos, m[0])) + '<mark>' + esc(src.slice(m[0], m[1])) + '</mark>';
      pos = m[1];
    });
    return out + esc(src.slice(pos));
  }

  function km(m) { return m < 1000 ? Math.round(m / 10) * 10 + ' m' : (m / 1000).toFixed(1).replace('.', ',') + ' km'; }

  P.util = { esc: esc, linkify: linkify, humanizeKey: humanizeKey, isEmpty: isEmpty, renderValue: renderValue, fold: fold, matchToken: matchToken, isMobile: isMobile, reducedMotion: reducedMotion,
    icon: icon, monthYear: monthYear, checkedLabel: checkedLabel, todayIdx: todayIdx, now: now, wita: wita, span: span,
    hoursStatus: hoursStatus, opensToday: opensToday, highlight: highlight, km: km };
})(window.Peta);
