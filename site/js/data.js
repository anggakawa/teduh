/* Data loading: fetch() the built JSON; if that fails (e.g. opened via file://),
   fall back to data/data.js which sets window.PETA_DATA. */
(function (P) {
  'use strict';
  var C = P.config;

  function getJSON(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' → HTTP ' + r.status);
      return r.json();
    });
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src; s.onload = resolve; s.onerror = function () { reject(new Error('gagal memuat ' + src)); };
      document.head.appendChild(s);
    });
  }

  function load() {
    return Promise.all([getJSON(C.dataUrls.places), getJSON(C.dataUrls.hotlines)])
      .then(function (r) { return { places: r[0], hotlines: r[1], via: 'fetch' }; })
      .catch(function (err) {
        console.warn('fetch gagal, memakai fallback data.js:', err);
        return loadScript(C.dataUrls.fallbackScript).then(function () {
          if (!window.PETA_DATA) throw new Error('data.js tidak berisi PETA_DATA');
          return { places: window.PETA_DATA.places, hotlines: window.PETA_DATA.hotlines, via: 'file-fallback' };
        });
      })
      .then(function (d) {
        var places = (d.places.places || []).filter(function (p) { return p && p.id && p._d; });
        places.forEach(function (p) {
          p._d.qf = P.util.fold(p._d.q);
          // Defence in depth for the hard rule: only real numeric lat/lng may become a pin.
          var ok = p._d.pin && typeof p.lat === 'number' && typeof p.lng === 'number' &&
                   p._d.pin.lat === p.lat && p._d.pin.lng === p.lng;
          if (!ok) p._d.pin = null;
          p._d.approx_only = !p._d.pin;
        });
        return { places: places, hotlines: d.hotlines.hotlines || [], meta: d.places.meta || {}, via: d.via };
      });
  }

  P.data = { load: load };
})(window.Peta);
