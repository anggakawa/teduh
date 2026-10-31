/* Map: Leaflet + markercluster with the Teduh SVG pins (SPEC §5). Only places with real lat/lng get a
   marker — approx_coords never do. The selected pin lives outside the cluster group with a ground shadow. */
(function (P) {
  'use strict';
  var C = P.config, U = P.util;
  var map, cluster, tiles, markers = {}, shown = {}, selectedId = null, ground = null, youMarker = null, hoverId = null;
  var opts = {};
  var SIZE = { base: [36, 46, 18, 44], hover: [41.4, 52.9, 20.7, 50.6], sel: [46.8, 59.8, 23.4, 57.2] };

  function markerUrl(group, needsCheck) {
    return C.markerUrl.replace('{slug}', group).replace('{state}', needsCheck ? 'belum-dicek' : 'terverifikasi');
  }

  // 36×46 anchored at the tip; hover/focus 1.15×; selected 1.3×.
  function pinIcon(p, state) {
    var s = SIZE[state || 'base'];
    return L.icon({
      iconUrl: markerUrl(p._d.group, p._d.needs_check),
      iconSize: [s[0], s[1]], iconAnchor: [s[2], s[3]],
      className: 'teduh-pin' + (state === 'sel' ? ' is-selected' : '') + (p._d.needs_check ? ' is-unchecked' : ' is-verified')
    });
  }

  function label(p) { return (p.name_display || p.name) + ' (' + (p._d.needs_check ? C.text.unchecked : C.text.verified) + ')'; }

  // 40px white disc, 3px primary ring, count 14/600; hollow sub-badge = how many are "belum dicek".
  function clusterIcon(c) {
    var kids = c.getAllChildMarkers(), n = kids.length;
    var un = kids.filter(function (m) { return m.options.place._d.needs_check; }).length;
    var title = n + ' layanan' + (un ? ', ' + un + ' belum dicek' : '');
    return L.divIcon({
      className: 'teduh-cluster-wrap',
      html: '<div class="teduh-cluster" role="img" aria-label="' + U.esc(title) + '"><span class="tc-count">' + n + '</span>' +
            (un ? '<span class="tc-unchecked">' + un + '</span>' : '') + '</div>',
      iconSize: [40, 40]
    });
  }

  function sameSpot(kids) {
    var a = kids[0].getLatLng();
    return kids.every(function (m) { return m.getLatLng().equals(a, 1e-7); });
  }

  // Same building (records with identical coordinates): a small list instead of a spiderfy.
  function miniList(c) {
    var kids = c.getAllChildMarkers();
    var html = '<div class="mini"><p class="mini-h">' + kids.length + ' layanan di lokasi ini</p><ul>' + kids.map(function (m) {
      var p = m.options.place;
      return '<li><button type="button" class="mini-b" data-id="' + U.esc(p.id) + '"><img src="' + markerUrl(p._d.group, p._d.needs_check) +
        '" width="20" height="26" alt=""><span>' + U.esc(p._d.short) + '</span>' + U.icon('chevr') + '</button></li>';
    }).join('') + '</ul></div>';
    var pop = L.popup({ closeButton: true, autoPanPaddingTopLeft: [16, 140], className: 'teduh-mini', offset: [0, -16] })
      .setLatLng(c.getLatLng()).setContent(html).openOn(map);
    var el = pop.getElement();
    el.addEventListener('click', function (e) {
      var b = e.target.closest('.mini-b'); if (!b) return;
      map.closePopup(pop); opts.onSelect(b.dataset.id, 'map');
    });
  }

  function init(el, o) {
    opts = o;
    var mobile = U.isMobile();
    map = L.map(el, { zoomControl: false, attributionControl: false, tap: true, zoomSnap: 0.5 }).setView(C.center, C.zoom);
    tiles = L.tileLayer(C.tiles.url, { maxZoom: C.tiles.maxZoom, className: C.tiles.className }).addTo(map);
    var tileOk = false, tileErr = 0;
    tiles.on('tileload', function () { tileOk = true; if (opts.onTiles) opts.onTiles(true); });
    tiles.on('tileerror', function () { tileErr++; if (!tileOk && tileErr >= 4 && opts.onTiles) opts.onTiles(false); });
    L.control.attribution({ position: mobile ? 'bottomleft' : 'bottomright', prefix: mobile ? false : '<a href="https://leafletjs.com">Leaflet</a>' })
      .addAttribution(C.tiles.attribution).addTo(map);
    cluster = L.markerClusterGroup({
      showCoverageOnHover: false, zoomToBoundsOnClick: false, spiderfyOnMaxZoom: false,
      // SPEC §5: radius 40; from zoom 16 only identical coordinates still group (= same building).
      maxClusterRadius: function (z) { return z >= 16 ? 1 : 40; },
      iconCreateFunction: clusterIcon
    });
    cluster.on('clusterclick', function (e) {
      var kids = e.layer.getAllChildMarkers();
      if (sameSpot(kids) && (map.getZoom() >= 16 || kids.length < 6)) {
        if (map.getZoom() < 16) map.setView(e.layer.getLatLng(), 16, { animate: !U.reducedMotion() });
        miniList(e.layer);
      } else e.layer.zoomToBounds({ padding: [48, 48] });
    });
    map.addLayer(cluster);
    map.on('click', function () { opts.onSelect(null, 'map'); });
    map.on('dragstart', function () { if (opts.onPan) opts.onPan(); });
    return map;
  }

  function setPlaces(places) {
    markers = {};
    places.forEach(function (p) {
      if (!p._d.pin) return; // HARD RULE: no pin without real lat/lng (approx_coords are never used)
      var t = label(p);
      var m = L.marker([p._d.pin.lat, p._d.pin.lng], { icon: pinIcon(p), place: p, keyboard: true, title: t, alt: t });
      m.on('click', function (e) { L.DomEvent.stop(e); opts.onSelect(p.id, 'map'); });
      m.on('mouseover', function () { if (p.id !== selectedId) m.setIcon(pinIcon(p, 'hover')); if (opts.onHover) opts.onHover(p.id); });
      m.on('mouseout', function () { if (p.id !== selectedId) m.setIcon(pinIcon(p)); if (opts.onHover) opts.onHover(null); });
      m.on('add', function () {
        var ie = m.getElement(); if (!ie || ie._teduh) return;
        ie._teduh = 1;
        ie.addEventListener('focus', function () { if (p.id !== selectedId) m.setIcon(pinIcon(p, 'hover')); });
        ie.addEventListener('blur', function () { if (p.id !== selectedId) m.setIcon(pinIcon(p)); });
      });
      markers[p.id] = m;
    });
  }

  function bounds(ids) {
    var ll = ids.map(function (id) { return markers[id]; }).filter(Boolean).map(function (m) { return m.getLatLng(); });
    return ll.length ? L.latLngBounds(ll) : null;
  }

  function fit(ids, pad) {
    var b = bounds(ids);
    if (!b) return false;
    map.fitBounds(b, Object.assign({ maxZoom: 15, animate: !U.reducedMotion() }, pad || { padding: [C.fitPadding, C.fitPadding] }));
    return true;
  }

  // Show only these markers (filters hide the rest), optionally framing them.
  function show(ids, doFit, pad) {
    shown = {};
    ids.forEach(function (id) { shown[id] = true; });
    cluster.clearLayers();
    cluster.addLayers(ids.filter(function (id) { return markers[id] && id !== selectedId; }).map(function (id) { return markers[id]; }));
    if (selectedId && markers[selectedId] && !shown[selectedId]) deselect();
    if (doFit) fit(ids, pad);
  }

  function deselect() {
    var m = selectedId && markers[selectedId];
    if (m) {
      map.removeLayer(m);
      m.setIcon(pinIcon(m.options.place));
      m.setZIndexOffset(0);
      if (shown[selectedId]) cluster.addLayer(m);
    }
    if (ground) { map.removeLayer(ground); ground = null; }
    selectedId = null;
  }

  // band(): {top,bottom,left,right} in map container px where a selected pin is fully visible.
  function select(id, pan, band) {
    if (selectedId === id) return;
    deselect();
    var m = id && markers[id];
    if (!m) return;
    selectedId = id;
    cluster.removeLayer(m);                                   // never hidden inside a cluster
    ground = L.marker(m.getLatLng(), { icon: L.divIcon({ className: 'teduh-ground', iconSize: [28, 8], iconAnchor: [14, 4] }),
      interactive: false, keyboard: false, zIndexOffset: 4999 }).addTo(map);
    m.setIcon(pinIcon(m.options.place, 'sel'));
    m.setZIndexOffset(5000);
    m.addTo(map);
    if (!pan) return;
    var b = band ? band() : null, size = map.getSize();
    b = b || { top: 0, bottom: size.y, left: 0, right: size.x };
    var anim = { animate: !U.reducedMotion() };
    var target = L.point((b.left + b.right) / 2, (b.top + b.bottom) / 2 + 26);   // pin tip slightly below centre
    var off = target.subtract(size.divideBy(2));
    if (map.getZoom() < 14) {
      var z = 15;
      map.setView(map.unproject(map.project(m.getLatLng(), z).subtract(off), z), z, anim);
      return;
    }
    var pt = map.latLngToContainerPoint(m.getLatLng());
    var inside = pt.x > b.left + 30 && pt.x < b.right - 30 && pt.y > b.top + 64 && pt.y < b.bottom - 12;
    if (!inside) map.panBy(pt.subtract(target), anim);                         // pan only, zoom unchanged
  }

  // Desktop card hover: matching pin 1.15×, the other single pins fade to 55%.
  function hover(id) {
    if (hoverId === id) return;
    hoverId = id;
    Object.keys(markers).forEach(function (k) {
      var m = markers[k];
      if (k !== selectedId) m.setIcon(pinIcon(m.options.place, k === id ? 'hover' : null));
      m.setOpacity(id && k !== id && k !== selectedId ? 0.55 : 1);
    });
  }

  function showYou(lat, lng) {
    if (youMarker) youMarker.remove();
    var col = getComputedStyle(document.documentElement).getPropertyValue('--primary').trim() || '#2F6F62';
    youMarker = L.circleMarker([lat, lng], { radius: 8, color: '#FFFFFF', weight: 3, fillColor: col, fillOpacity: 1, interactive: false }).addTo(map);
    map.setView([lat, lng], Math.max(map.getZoom(), 13));
  }

  function retryTiles() { if (tiles) tiles.redraw(); }
  function invalidate() { if (map) map.invalidateSize(); }
  function pinnedCount() { return Object.keys(markers).length; }
  function pinnedIds() { return Object.keys(markers); }
  function markerInfo(id) {
    var m = markers[id];
    return m && { iconUrl: m.options.icon.options.iconUrl, title: m.options.title, className: m.options.icon.options.className,
      zIndexOffset: m.options.zIndexOffset, inCluster: cluster.hasLayer(m), onMap: map.hasLayer(m), size: m.options.icon.options.iconSize };
  }
  function shownCount() { return Object.keys(shown).filter(function (id) { return markers[id]; }).length; }
  function getMap() { return map; }

  P.map = { init: init, setPlaces: setPlaces, show: show, fit: fit, select: select, deselect: deselect, hover: hover, invalidate: invalidate,
            pinnedCount: pinnedCount, pinnedIds: pinnedIds, markerInfo: markerInfo, shownCount: shownCount, showYou: showYou,
            getMap: getMap, markerUrl: markerUrl, retryTiles: retryTiles };
})(window.Peta);
