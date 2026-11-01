/* UI: chips, list header, cards, empty/loading/error states, detail, hotline + phone modals, legend.
   Pure rendering + DOM events; state lives in app.js. */
(function (P) {
  'use strict';
  var C = P.config, U = P.util, esc = U.esc, icon = U.icon;
  var $ = function (id) { return document.getElementById(id); };
  var groupsById = {};
  C.groups.forEach(function (g) { groupsById[g.id] = g; });

  function catChip(p) {
    var g = groupsById[p._d.group];
    return '<span class="cchip cat--' + g.id + '">' + icon(g.icon) + esc(g.label) + '</span>';
  }

  // Verified = green check + "dicek Okt 2026". Belum dicek = grey chip (never orange); no date in the list.
  function statusHtml(p, inDetail) {
    if (!p._d.needs_check) {
      var when = U.checkedLabel(p._d.checked);
      return '<span class="st ok">' + icon('check') + C.text.verified + (when ? ' · ' + esc(when) : '') + '</span>';
    }
    return '<span class="ncchip"' + (inDetail ? '' : ' title="' + esc(C.text.uncheckedTip) + '"') + '>' + C.text.unchecked + icon('info') + '</span>';
  }
  function statusText(p) {
    return p._d.needs_check ? C.text.unchecked : C.text.verified + (p._d.checked ? ' ' + U.checkedLabel(p._d.checked) : '');
  }

  // SCHEMA v4 BPJS chip: ya = tinted + check, sebagian / tidak = outlined, belum_diketahui = neutral grey
  // (like "Belum dicek", never "tidak"), tidak_relevan = no chip. Rujukan is appended for ya/sebagian.
  var has = Object.prototype.hasOwnProperty;
  function bpjsInfo(p) {
    var b = p._d.bpjs, T = C.text.bpjs, st = b && typeof b.status === 'string' ? b.status : '';
    if (!st || !has.call(T.status, st)) return null;
    var t = T.status[st], rj = b.rujukan === true;
    return { status: st, label: t.chip + (rj ? ' · ' + T.rujukan : ''), aria: t.aria + (rj ? ', ' + T.rujukanAria : '') };
  }
  // o.card: leave out statuses that are detail-only; o.hidden: a visual copy screen readers skip.
  function bpjsChip(p, o) {
    var i = bpjsInfo(p);
    o = o || {};
    if (!i || (o.card && C.text.bpjs.cardHidden.indexOf(i.status) >= 0)) return '';
    var a11y = o.hidden ? ' aria-hidden="true"' : ' role="img" aria-label="' + esc(i.aria) + '"';
    return '<span class="tag bpjs bpjs--' + esc(i.status) + '" data-bpjs="' + esc(i.status) + '"' + a11y + ' title="' + esc(i.aria) + '">' +
      (i.status === 'ya' ? icon('check') : '') + esc(i.label) + '</span>';
  }
  // SCHEMA v5 gratis tag, from _d.gratis.status only (never from text or from BPJS).
  function gratisInfo(p) {
    var g = p._d.gratis, T = C.text.gratis.status, st = g && typeof g.status === 'string' ? g.status : '';
    return st && has.call(T, st) ? { status: st, label: T[st].tag, aria: T[st].aria } : null;
  }
  function gratisTag(p, o) {
    var i = gratisInfo(p);
    if (!i) return '';
    return '<span class="tag tag-gratis gratis--' + esc(i.status) + '" data-gratis="' + esc(i.status) + '"' + (o && o.hidden ? ' aria-hidden="true"' : '') + '>' + esc(i.label) + '</span>';
  }
  function tagsHtml(p, ctx, o) {
    var out = (p._d.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + '</span>'; });
    var gt = gratisTag(p);
    if (gt) out.unshift(gt);
    var bc = bpjsChip(p, o);
    if (bc) out.unshift(bc);
    if (p._d.regional) out.push('<span class="tag">' + esc(C.text.regional) + (p._d.place ? ' · ' + esc(p._d.place) : '') + '</span>');
    if (ctx && ctx.dist && ctx.dist[p.id] != null) out.push('<span class="tag tag-dist">' + esc(U.km(ctx.dist[p.id])) + '</span>');
    return out.join('');
  }

  function hoursLine(p) {
    var h = U.hoursStatus(p);
    return '<span class="hrs hrs--' + h.kind + '">' + icon(h.kind === 'janji' ? 'calendar' : 'clock') + '<span>' + h.html + '</span></span>';
  }

  // ---------- chips (SPEC §3: toggles first, active categories pinned to the start) ----------
  function renderChips(st, on) {
    var el = $('chips');
    var toggles =
      '<button type="button" class="chip vchip' + (st.onlyOk ? ' on' : '') + '" data-t="ok" aria-pressed="' + st.onlyOk + '">' + icon('check') + '<span>Terverifikasi saja</span></button>' +
      '<button type="button" class="chip tchip' + (st.openToday ? ' on' : '') + '" data-t="today" aria-pressed="' + st.openToday + '">' + icon('clock') + '<span>Buka hari ini</span></button>' +
      '<button type="button" class="chip bpjschip' + (st.bpjs ? ' on' : '') + '" data-t="bpjs" aria-pressed="' + st.bpjs + '">' + icon('wallet') + '<span>' + esc(C.text.bpjs.filter) + '</span></button>';
    var groups = C.groups.slice().sort(function (a, b) { return (st.active.has(b.id) ? 1 : 0) - (st.active.has(a.id) ? 1 : 0); });
    el.innerHTML = '<div class="chipsin">' + toggles + '<span class="cbreak" aria-hidden="true"></span>' + groups.map(function (g) {
      var a = st.active.has(g.id);
      return '<button type="button" class="chip cat--' + g.id + (a ? ' on' : '') + '" data-group="' + g.id + '" aria-pressed="' + a + '">' +
        icon(g.icon) + '<span>' + esc(g.label) + '</span></button>';
    }).join('') + '</div>';
    el.onclick = function (e) {
      var b = e.target.closest('.chip'); if (!b) return;
      if (b.dataset.t === 'ok') on.ok(); else if (b.dataset.t === 'today') on.today(); else if (b.dataset.t === 'bpjs') on.bpjs(); else on.cat(b.dataset.group);
    };
  }

  // ---------- search extras (mobile search mode): memory-only recent searches + fixed suggestions ----------
  function renderSearchExtra(recent, on) {
    $('recentRow').hidden = !recent.length;
    $('recent').innerHTML = recent.map(function (r, i) {
      return '<span class="schip"><button type="button" class="schip-b" data-q="' + esc(r) + '">' + esc(r) + '</button>' +
        '<button type="button" class="schip-x" data-i="' + i + '" aria-label="Hapus ' + esc(r) + ' dari riwayat">' + icon('x') + '</button></span>';
    }).join('');
    $('suggest').innerHTML = C.searchSuggestions.map(function (s) {
      return '<button type="button" class="schip schip-b" data-q="' + esc(s) + '">' + esc(s) + '</button>';
    }).join('');
    $('searchExtra').onclick = function (e) {
      var x = e.target.closest('.schip-x'); if (x) { on.remove(+x.dataset.i); return; }
      var b = e.target.closest('[data-q]'); if (b) on.pick(b.dataset.q);
    };
  }

  // SCHEMA v3: Indonesian display lists win over the raw (often English) research text.
  function svcList(p) { return Array.isArray(p.services_display) ? p.services_display : Array.isArray(p.services) ? p.services : []; }
  function bookList(p) { var b = Array.isArray(p.booking_display) ? p.booking_display : p.booking; return Array.isArray(b) ? b : b ? [b] : []; }

  // ---------- list ----------
  function matchRow(p, words) {
    if (!words || !words.length) return '';
    var nameF = U.fold(p.name);
    if (words.every(function (w) { return nameF.indexOf(w) >= 0; })) return '';
    var kel = 'kelurahan_display' in p ? p.kelurahan_display : p.kelurahan;
    var fields = [].concat(svcList(p), Array.isArray(p.tags) ? p.tags : [], Array.isArray(p.search_terms) ? p.search_terms : [], kel ? [kel] : [], p._d.tags || []);
    var best = null, bestN = 0;
    fields.forEach(function (f) {
      if (typeof f !== 'string') return;
      var ff = U.fold(f), n = words.filter(function (w) { return ff.indexOf(w) >= 0; }).length;
      if (n > bestN || (n === bestN && n && f.length < best.length)) { best = f; bestN = n; }
    });
    return best ? '<span class="crow crow--match">' + icon('search') + '<span>' + U.highlight(best, words) + '</span></span>' : '';
  }

  // Card aria-label: name, status, hours, then the BPJS status and the gratis tag when they show on the card.
  function cardAria(p, h) {
    var parts = [p.name_display || p.name, statusText(p), h.text];
    if (bpjsChip(p, { card: true })) parts.push(bpjsInfo(p).aria);
    var gi = gratisInfo(p);
    if (gi) parts.push(gi.aria);
    return parts.join(', ');
  }
  function card(p, ctx) {
    var g = groupsById[p._d.group], h = U.hoursStatus(p);
    var tags = tagsHtml(p, ctx, { card: true });
    var aria = cardAria(p, h);
    return '<li><button type="button" class="card' + (p._d.needs_check ? ' is-unchecked' : '') + '" data-id="' + esc(p.id) + '" aria-label="' + esc(aria) + '">' +
      '<span class="ctile cat--' + g.id + '">' + icon(g.icon) + '</span>' +
      '<span class="cbody"><span class="cname">' + esc(p._d.short) + '</span>' +
      '<span class="crow">' + statusHtml(p) + '</span>' + matchRow(p, ctx.words) +
      // SPEC §11.2: places without a pin show a pin-off line instead of an unknown-hours line.
      '<span class="crow">' + (!p._d.pin && h.kind === 'unknown' ? '<span class="hrs hrs--nopin">' + icon('pinoff') + '<span>' + esc(C.text.unpinned) + ' · telepon dulu</span></span>' : hoursLine(p)) + '</span>' +
      (tags ? '<span class="crow crow--tags">' + tags + '</span>' : '') + '</span>' +
      '<span class="cchev">' + icon('chevr') + '</span></button></li>';
  }

  function renderList(visible, ctx, on) {
    $('skeleton').hidden = true;
    var pinned = visible.filter(function (p) { return p._d.pin; });
    var unpinned = visible.filter(function (p) { return !p._d.pin; });
    $('list').innerHTML = pinned.map(function (p) { return card(p, ctx); }).join('');
    $('listUnpinned').innerHTML = unpinned.map(function (p) { return card(p, ctx); }).join('');
    $('unpinnedSection').hidden = unpinned.length === 0;
    $('unpinnedNote').textContent = C.text.unpinnedNote;
    var sc = $('listScroll');
    sc.onclick = function (e) { var b = e.target.closest('.card'); if (b) on.pick(b.dataset.id); };
    sc.onmouseover = function (e) { var b = e.target.closest('.card'); on.hover(b ? b.dataset.id : null); };
    sc.onmouseleave = function () { on.hover(null); };
  }

  // Header (SPEC §3/§10): title, sub-line, and one right slot (sort | Hapus filter | Peta).
  function renderHeader(o) {
    $('sh1').textContent = o.title;
    $('sh2').textContent = o.sub;
    $('sortWrap').hidden = o.slot !== 'sort';
    $('clearFilters').hidden = o.slot !== 'clear';
    $('toMap').hidden = o.slot !== 'map';
    $('liveCount').textContent = o.live || '';
  }

  function renderSort(cur, hasDist) {
    $('sort').innerHTML = C.sorts.map(function (s) {
      var dis = s.id === 'jarak' && !hasDist;
      return '<option value="' + s.id + '"' + (dis ? ' disabled' : '') + (s.id === cur ? ' selected' : '') + '>' + esc(s.label) + (dis ? ' (aktifkan lokasi)' : '') + '</option>';
    }).join('');
    var s = C.sorts.filter(function (x) { return x.id === cur; })[0];
    $('sortLabel').textContent = U.isMobile() ? 'Urutkan' : s.label;
  }

  // SPEC §7 empty states. kind 'filter' (m07) or 'search' (d03). Counts are always live from the data.
  function renderEmpty(o, on) {
    var el = $('empty');
    if (!o) { el.hidden = true; el.innerHTML = ''; $('dataMeta').hidden = false; return; }
    var html = '<div class="ill">' + icon('search') + '</div>';
    if (o.kind === 'search') {
      html += '<h3>Tidak ada hasil untuk “' + esc(o.q) + '”</h3><p>Belum ada data layanan khusus ' + esc(o.q) + '.' +
        (o.broader.length ? ' Coba kata yang lebih umum:' : '') + '</p>' +
        (o.broader.length ? '<div class="broader">' + o.broader.map(function (b) {
          return '<button type="button" class="bchip" data-q="' + esc(b.term) + '">' + esc(b.term) + ' · ' + b.n + '</button>';
        }).join('') + '</div>' : '') +
        '<div class="btns"><button type="button" class="btn sec" data-act="clearq">Hapus pencarian</button></div>';
    } else {
      html += '<h3>Belum ada layanan yang cocok</h3><p>' + esc(o.sentence) + '</p><div class="btns">' +
        '<button type="button" class="btn pri" data-act="clear">Hapus filter</button>' +
        (o.unchecked ? '<button type="button" class="btn sec" data-act="showun">Tampilkan ' + o.unchecked + ' yang belum dicek</button>' : '') + '</div>' +
        (o.cross ? '<p class="cross">' + esc(o.cross.label) + ' · <button type="button" class="linkbtn" data-q="' + esc(o.cross.q) + '">cari “' + esc(o.cross.q) + '” (' + o.cross.n + ')</button></p>' : '');
    }
    el.innerHTML = html; el.hidden = false; $('dataMeta').hidden = true;
    el.onclick = function (e) {
      var b = e.target.closest('[data-act],[data-q]'); if (!b) return;
      if (b.dataset.q) on.search(b.dataset.q); else on[b.dataset.act]();
    };
  }

  function renderDataError(err) {
    $('skeleton').hidden = true;
    var el = $('dataError'); el.hidden = false;
    el.innerHTML = '<div class="notice-inline">' + icon('info') + '<span><b>Data belum bisa dimuat.</b> ' + esc(C.text.loadErrorFile) +
      (err ? ' <span class="mut">(' + esc(err) + ')</span>' : '') + '</span></div>' +
      '<p class="de-l">Butuh bantuan sekarang?</p><div class="de-b">' + C.fallbackHotlines.map(function (h) {
        return '<a class="hbtn" href="tel:' + esc(h.tel) + '">' + icon('phone') + esc(h.label) + '</a>';
      }).join('') + '</div>';
  }

  function markListSelected(id) {
    document.querySelectorAll('.card.is-selected').forEach(function (b) { b.classList.remove('is-selected'); b.removeAttribute('aria-current'); });
    if (id) {
      var b = document.querySelector('.card[data-id="' + CSS.escape(id) + '"]');
      if (b) { b.classList.add('is-selected'); b.setAttribute('aria-current', 'true'); }
    }
  }
  function markListHover(id) {
    document.querySelectorAll('.card.is-hover').forEach(function (b) { b.classList.remove('is-hover'); });
    if (id) { var b = document.querySelector('.card[data-id="' + CSS.escape(id) + '"]'); if (b) b.classList.add('is-hover'); }
  }

  // ---------- detail ----------
  function irow(ic, main, subs, cls) {
    if (!main) return '';
    return '<div class="irow' + (cls ? ' ' + cls : '') + '">' + icon(ic) + '<div class="ival"><div class="im">' + main + '</div>' +
      (subs || []).filter(Boolean).map(function (s) { return '<div class="s">' + s + '</div>'; }).join('') + '</div></div>';
  }
  // Detail: the BPJS / cost note (catatan_display) as a visible info row, under the address.
  function bpjsRow(p) {
    var b = p.bpjs_info, note = b && typeof b.catatan_display === 'string' ? b.catatan_display : '';
    if (!b || !note) return '';
    var i = bpjsInfo(p);
    // The header already announces the chip; this copy is visual only.
    return irow('wallet', i ? bpjsChip(p, { hidden: true }) : '<span class="ilab">' + esc(C.text.bpjs.row) + '</span>', [esc(note)], 'irow-bpjs');
  }
  // Detail: the gratis tag + syarat_display, and a quiet "perlu dicek ulang" when the source is stale.
  function gratisRow(p) {
    var g = p._d.gratis, i = gratisInfo(p);
    if (!i) return '';
    var subs = [g.syarat ? esc(g.syarat) : '', g.recheck ? '<span class="recheck">' + esc(C.text.gratis.recheck) + '</span>' : ''];
    return irow('wallet', gratisTag(p, { hidden: true }), subs, 'irow-gratis');
  }
  function labelled(label, v) { var r = U.renderValue(v, C.contactLabels); return r ? '<div class="ilabel">' + esc(label) + '</div>' + r : ''; }

  function conflictPhones(p) { return (p._d.phones || []).filter(function (x) { return x.conflict; }); }

  // SPEC §3: hide missing actions instead of disabling them. Two conflicting numbers → "Telepon · 2 nomor" chooser.
  function actions(p) {
    var phones = p._d.phones || [], conf = conflictPhones(p);
    var tel = phones.filter(function (x) { return !x.conflict; })[0];
    var wa = phones.filter(function (x) { return x.wa && x.wa_url; })[0];
    var out = [];
    if (conf.length > 1 && !tel) out.push('<button type="button" class="act pri" data-act="phones">' + icon('phone') + '<span>Telepon · ' + conf.length + ' nomor</span></button>');
    else if (tel || phones[0]) out.push('<a class="act pri" href="tel:' + esc((tel || phones[0]).tel) + '">' + icon('phone') + '<span>Telepon</span></a>');
    if (wa) out.push('<a class="act' + (out.length ? '' : ' pri') + '" href="' + esc(wa.wa_url) + '" target="_blank" rel="noopener noreferrer">' + icon('wa') + '<span>WhatsApp</span></a>');
    if (p._d.pin) out.push('<a class="act' + (out.length ? '' : ' pri') + '" href="' + esc(p._d.dir_url) + '" target="_blank" rel="noopener noreferrer">' + icon('route') + '<span>Rute</span></a>');
    return out.length ? '<div class="acts acts--' + out.length + '">' + out.join('') + '</div>' : '';
  }

  function todayBox(p) {
    var h = p._d.hours, w = U.wita(U.now()), t = w.day, D = C.days, st = U.hoursStatus(p);
    if (!h) return '';
    var lab = h.label && h.label !== 'Buka' ? h.label + ' ' : '';
    if (!h.week) {   // IGD only
      return '<div class="today"><div class="row"><div class="tl">' + icon('clock') + '<div><div class="t1">Hari ini, ' + D[t] + ' · <b>IGD 24 jam</b></div>' +
        '<div class="t2 t2--sm">' + (p._d.hours_note ? esc(p._d.hours_note) : 'Jadwal poli: telepon dulu') + '</div></div></div></div></div>';
    }
    var v = h.week[t], sp = U.span(v), word, big;
    if (st.kind === 'open') word = lab ? lab + 'buka sekarang' : 'Buka sekarang';
    else if (st.kind === 'later') word = lab ? lab + 'buka nanti' : 'Buka nanti';
    else if (sp) word = lab ? lab + 'sudah tutup' : 'Sudah tutup';
    else if (v === 'tutup') word = 'Tutup';
    else word = 'Tidak ada jadwal';
    var open = st.kind === 'open' || st.kind === 'later';
    var nx = !sp && st.text.split(' · buka ')[1];
    big = sp ? sp.text + ' WITA' : (nx ? 'Buka ' + nx + ' WITA' : 'Telepon dulu');
    var week = D.map(function (d, i) {
      var x = h.week[i];
      return '<div' + (i === t ? ' class="now"' : '') + '><span>' + d + (i === t ? ' · hari ini' : '') + '</span><span class="' + (x && x !== 'tutup' ? '' : 'c') + '">' +
        (x ? (x === 'tutup' ? 'Tutup' : esc(x)) : 'Belum diketahui') + '</span></div>';
    }).join('');
    return '<div class="today"><div class="row"><div class="tl">' + icon('clock') + '<div><div class="t1">Hari ini, ' + D[t] + ' · <b class="' + (open ? 'open' : 'shut') + '">' + esc(word) + '</b></div>' +
      '<div class="t2">' + esc(big) + '</div>' + (h.igd24 ? '<div class="t3">IGD rumah sakit buka 24 jam</div>' : '') +
      (p._d.hours_note ? '<div class="t3">' + esc(p._d.hours_note) + '</div>' : '') + '</div></div>' +
      '<button type="button" class="wk" aria-expanded="false" aria-controls="weekList">Jadwal ' + icon('chev') + '</button></div>' +
      '<div class="week" id="weekList" hidden>' + week + '</div></div>';
  }

  // Unchecked notice reason: `note_id` (Indonesian, SPEC §11.6) when the data has it; otherwise only fixed
  // sentences derived from structured facts. The English open_issues stay under "Info lengkap & sumber".
  function noticeReason(p) {
    if (p._d.note_id) return p._d.note_id;
    var r = [], conf = conflictPhones(p), a = p._d.addr || {};
    if (conf.length > 1) r.push('Ada ' + conf.length + ' nomor telepon dari sumber berbeda.');
    if (a.note) r.push(a.note.replace(/ Tanyakan[^.]*\.$/, ''));
    if (!(p._d.phones || []).length) r.push('Belum ada nomor kontak yang tercatat.');
    if (!p._d.pin) r.push('Titik lokasinya belum pasti.');
    return r.join(' ');
  }

  function renderDetail(p, ctx) {
    var a = p._d.addr || {};
    var phones = p._d.phones || [];
    var phoneRows = phones.map(function (x) {
      var sub = x.conflict ? (x.source ? 'Dari ' + esc(x.source) + ' · ' : '') + 'nomor berbeda antar sumber'
        : x.wa ? 'Telepon &amp; WhatsApp' : x.mobile ? 'Telepon · WhatsApp belum tercatat' : 'Telepon · tidak ada WhatsApp di data';
      return irow('phone', '<a class="num" href="tel:' + esc(x.tel) + '">' + esc(x.display) + '</a>', [sub]);
    }).join('');
    var booking = bookList(p).filter(function (b) { return !U.isEmpty(b); });
    var bookRow = booking.length ? irow('calendar', p._d.booking_janji ? 'Dengan janji temu' : 'Cara daftar', [booking.map(esc).join(' · ')]) : '';
    var merge = a.line && a.area && a.line.indexOf(',') < 0;      // street only → "Jl. Pandu, Banjarbaru" (m05)
    var addrMain = a.line ? esc(a.line + (merge ? ', ' + a.area : '')) : 'Alamat belum diketahui';
    var addrSubs = [a.area && !merge ? esc(a.area) : '', a.note ? esc(a.note) : '',
      !p._d.pin ? esc(C.text.unpinned) + ' · <a href="' + esc(p._d.maps_url) + '" target="_blank" rel="noopener noreferrer">cari di Google Maps</a>' : ''];
    var hoursRow = !p._d.hours ? irow('clock', 'Jam belum diketahui', [p._d.hours_note ? esc(p._d.hours_note) + ' Telepon dulu sebelum datang.' : 'Telepon dulu sebelum datang' + (!U.isEmpty(p.hours) ? ' · catatan sumber ada di “Info lengkap”' : '')]) : '';
    var links = (p._d.links || []).filter(function (l) { return !/^https:\/\/wa\.me\//.test(l.url); }).map(function (l) {
      var lab = C.contactLabels[l.label.split('.')[0]] || U.humanizeKey(l.label);
      return '<a href="' + esc(l.url) + '" target="_blank" rel="noopener noreferrer">' + esc(lab) + '</a>';
    }).join(' · ');

    var services = svcList(p).filter(function (s) { return !U.isEmpty(s); });
    var svc = services.length ? '<p class="seclabel">Layanan</p><div class="svc">' + services.map(function (s, i) {
      return '<span' + (i >= 4 ? ' hidden' : '') + '>' + esc(s) + '</span>';
    }).join('') + (services.length > 4 ? '<button type="button" class="svc-more">+' + (services.length - 4) + ' lainnya</button>' : '') + '</div>' : '';

    var sources = (p.sources || []).map(function (s) {
      return '<li><a href="' + esc(s.url) + '" target="_blank" rel="noopener noreferrer">' + esc((s.url || '').replace(/^https?:\/\/(www\.)?/, '').slice(0, 48)) + '</a>' +
        (s.checked ? ' <span class="mut">(' + esc(U.checkedLabel(s.checked)) + ')</span>' : '') + '</li>';
    }).join('');

    var notice = p._d.needs_check ? '<div class="notice">' + icon('info') + '<div><b>' + esc(C.text.uncheckedTip) + '</b>' +
      (noticeReason(p) ? '<div class="s">' + esc(noticeReason(p)) + '</div>' : '') + '</div></div>' : '';

    var html = '<div class="dhead"><h2 class="dname" id="dname" tabindex="-1">' + esc(p.name_display || p.name) + '</h2>' +
      '<div class="drow">' + catChip(p) + statusHtml(p, true) + tagsHtml(p, ctx) + '</div></div>' +
      notice + actions(p) + todayBox(p) +
      '<div class="info">' + phoneRows + bookRow + hoursRow + irow('pin', addrMain, addrSubs) + bpjsRow(p) + gratisRow(p) +
      (links ? irow('link', links) : '') + '</div>' + svc +
      '<details class="more"><summary>Info lengkap &amp; sumber</summary><div class="more-b">' +
      labelled('Jam (sesuai sumber)', p.hours) + labelled('Jadwal praktik', p.schedule) +
      labelled('Biaya', p.cost) + labelled('Kisaran biaya', p.price_range) + labelled('Per sesi', p.price_per_session) + (p.bpjs_info ? '' : labelled('BPJS', p.bpjs)) +
      labelled('Siapa yang bisa', p.eligibility) + labelled('Tenaga / terapis', p.therapists) + labelled('Cara melapor / mengadu', p.complaint_method) +
      labelled('Catatan lokal', p.local_notes) +
      labelled('Alamat (teks asli)', [p.address, p.kelurahan, p.kecamatan, p.city]) + labelled('Kontak (teks asli)', p.contacts) +
      (p._d.needs_check ? '' : labelled('Catatan', p.note_id)) + labelled('Catatan peneliti (teks asli)', p.open_issues) +
      labelled('Tingkat keyakinan per data', p.field_confidence) + labelled('Catatan validasi', p.validation_note) +
      (sources ? '<div class="ilabel">Sumber</div><ul class="plain">' + sources + '</ul>' : '') +
      '<p class="mut">ID: ' + esc(p.id) + (p._d.checked ? ' · ' + esc(U.checkedLabel(p._d.checked)) : '') + '</p></div></details>' +
      (C.reportUrl ? '<a class="report" href="' + esc(C.reportUrl) + '" target="_blank" rel="noopener">' + icon('flag') + '<span>Laporkan info salah</span></a>' : '');

    var body = $('detailBody');
    body.innerHTML = html;
    var wk = body.querySelector('.wk');
    if (wk) wk.onclick = function () {
      var open = wk.getAttribute('aria-expanded') !== 'true';
      wk.setAttribute('aria-expanded', open); $('weekList').hidden = !open;
    };
    var more = body.querySelector('.svc-more');
    if (more) more.onclick = function () { body.querySelectorAll('.svc span[hidden]').forEach(function (s) { s.hidden = false; }); more.remove(); };
    var ph = body.querySelector('[data-act="phones"]');
    if (ph) ph.onclick = function () { ctx.onPhones(p, ph); };
    $('detailScroll').scrollTop = 0;
  }

  function renderPhoneChooser(p) {
    $('phoneTitle').textContent = 'Telepon ' + p._d.short;
    $('phoneList').innerHTML = conflictPhones(p).map(function (x) {
      return '<div class="hl"><div class="n">' + esc(x.display) + '</div><div class="d">' + (x.source ? 'Sumber: ' + esc(x.source) : 'Sumber publik') + '</div>' +
        '<div class="bs"><a class="hbtn" href="tel:' + esc(x.tel) + '">' + icon('phone') + 'Telepon</a></div></div>';
    }).join('');
  }

  // ---------- hotlines (SPEC §8): 112 (only filled button) → SAPA 129 → Healing119 → text line ----------
  function renderHotlines(list) {
    var find = function (rx) { return list.filter(function (h) { return rx.test(h.name); })[0]; };
    var checked = '';
    list.forEach(function (h) { (h.sources || []).forEach(function (s) { if (s.checked && s.checked > checked) checked = s.checked; }); });
    $('emgSub').textContent = 'Gratis · nomor resmi' + (checked ? ' · ' + U.checkedLabel(checked) : '');
    var out = '', line = '';
    C.hotlineCopy.forEach(function (c, idx) {
      var h = find(c.match); if (!h) return;
      var ct = h.contacts || {}, btns = [];
      var sub = c.sub + (ct.online_form ? ' · ada formulir online' : '') + (/queue/i.test(JSON.stringify(h.hours || '')) ? ', bisa antre' : '');
      if (idx === 0) {
        btns.push('<a class="hbtn big" href="tel:112">' + icon('phone') + 'Telepon 112</a>');
        var amb = (h._d.phones || []).filter(function (x) { return /psc/i.test(x.label); })[0];
        var pol = /\b(1\d{2})\b/.exec(ct.polres_banjarbaru || '');
        line = (amb ? 'Ambulans PSC 119 Banjarbaru <a href="tel:' + esc(amb.tel) + '">' + esc(amb.display) + '</a>' : '') +
          (pol ? ' · Polres <a href="tel:' + pol[1] + '">' + pol[1] + '</a>' : '');
      } else {
        var main = /^\s*(1\d{2})(.*)$/.exec(ct.phone || '');
        if (main) btns.push('<a class="hbtn" href="tel:' + main[1] + '">' + icon('phone') + 'Telepon ' + esc(main[1] + main[2].replace(/\s*ext\s*/i, ', ext ')) + '</a>');
        var wa = (h._d.phones || []).filter(function (x) { return x.mobile && /whatsapp|wa/i.test(x.label); })[0];
        if (wa) btns.push('<a class="hbtn" href="' + esc(wa.wa_url) + '" target="_blank" rel="noopener noreferrer">' + icon('wa') + 'WhatsApp <small>' + esc(wa.display) + '</small></a>');
      }
      out += '<div class="hl"><div class="n">' + esc(c.title) + '</div><div class="d">' + esc(sub) + '</div><div class="bs">' + btns.join('') + '</div></div>';
    });
    $('hotlines').innerHTML = out + (line ? '<p class="hline">' + line + '</p>' : '');
  }

  // ---------- legend popover (SPEC §3: collapsed by default) ----------
  function renderLegend() {
    $('legendPop').innerHTML = '<div class="lp-h"><b>Keterangan</b><button type="button" class="lp-x" data-close aria-label="Tutup keterangan">' + icon('x') + '</button></div>' +
      '<ul>' + C.groups.map(function (g) {
        return '<li><img src="' + P.map.markerUrl(g.id, false) + '" width="22" height="28" alt="">' + esc(g.label) + '</li>';
      }).join('') +
      '<li class="lp-sep"><img src="' + P.map.markerUrl('kesehatan-mental', true) + '" width="22" height="28" alt=""><span><span class="ncchip">' + C.text.unchecked + icon('info') + '</span> info dari sumber publik</span></li>' +
      '<li><span class="teduh-cluster lp-cl"><span class="tc-count">3</span><span class="tc-unchecked">1</span></span><span>Beberapa layanan berdekatan · angka kecil = belum dicek</span></li></ul>';
  }

  var toastT;
  function toast(msg) {
    var t = $('toast'); t.textContent = msg; t.hidden = false;
    clearTimeout(toastT); toastT = setTimeout(function () { t.hidden = true; }, 3200);
  }

  P.ui = { renderChips: renderChips, renderSearchExtra: renderSearchExtra, renderList: renderList, renderHeader: renderHeader, renderSort: renderSort,
           renderEmpty: renderEmpty, renderDataError: renderDataError, markListSelected: markListSelected, markListHover: markListHover,
           renderDetail: renderDetail, renderPhoneChooser: renderPhoneChooser, renderHotlines: renderHotlines, renderLegend: renderLegend,
           toast: toast, statusHtml: statusHtml,
           // Pure HTML builders, exposed so check.mjs can render synthetic places (no DOM side effects).
           fragments: { card: card, tagsHtml: tagsHtml, bpjsRow: bpjsRow, bpjsInfo: bpjsInfo, gratisRow: gratisRow } };
})(window.Peta);
