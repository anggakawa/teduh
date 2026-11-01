/* Static config: labels, categories, icons, copy. Colours live in css/tokens.css (--cat-<slug>). */
window.Peta = window.Peta || {};
Peta.config = {
  appName: 'Teduh',
  // SPEC §5: mobile opens at zoom 13 on central Banjarbaru; desktop fits all pins (padding 48).
  center: [-3.456, 114.828],
  zoom: 13,
  fitPadding: 48,
  // Base map. Primary: OpenFreeMap "Positron" vector tiles (light, muted; free, no key, no limits:
  // https://openfreemap.org/), drawn by MapLibre GL inside Leaflet. vendor/maplibre is loaded lazily.
  // Fallback (no WebGL, MapLibre fails to load, or OpenFreeMap errors): OSM standard raster tiles,
  // desaturated via CSS (.teduh-tiles). OSM's tile policy needs a Referer: keep the referrer policy at strict-origin-when-cross-origin.
  // https://operations.osmfoundation.org/policies/tiles/
  tiles: {
    referrerPolicy: 'strict-origin-when-cross-origin',
    vector: {
      style: 'https://tiles.openfreemap.org/styles/positron',
      host: 'tiles.openfreemap.org',
      attribution: '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> &copy; <a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
      scripts: ['vendor/maplibre/maplibre-gl.js', 'vendor/maplibre/leaflet-maplibre-gl.js'],
      css: 'vendor/maplibre/maplibre-gl.css',
      timeoutMs: 8000
    },
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    className: 'teduh-tiles',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
    maxZoom: 19
  },
  dataUrls: { places: 'data/places.json', hotlines: 'data/hotlines.json', fallbackScript: 'data/data.js' },
  markerUrl: 'assets/markers/{slug}--{state}.svg',     // state: terverifikasi | belum-dicek
  quickExitUrl: 'https://www.google.com/search?q=cuaca+banjarbaru',
  // "Laporkan info salah": no report channel exists yet. Set a mailto:/form URL here to show the link.
  reportUrl: null,

  // Top-level category slugs (SCHEMA v2 `category` prefix) = `_d.group` = marker file prefix.
  groups: [
    { id: 'kesehatan-mental', label: 'Kesehatan mental', short: 'Kesehatan mental', noun: 'layanan kesehatan mental', icon: 'leaf' },
    { id: 'tumbuh-kembang-anak', label: 'Tumbuh kembang & ABK', short: 'Tumbuh kembang', noun: 'layanan tumbuh kembang', icon: 'blocks' },
    { id: 'layanan-pendampingan', label: 'Pendampingan & hukum', short: 'Pendampingan & hukum', noun: 'layanan pendampingan & hukum', icon: 'shield' },
    { id: 'psikologi', label: 'Biro tes psikologi', short: 'Biro tes psikologi', noun: 'biro tes psikologi', icon: 'clipboard' }
  ],
  // SPEC §7 empty filter state: optional cross-suggestion (search term shown only when it has results).
  crossSuggest: { psikologi: { label: 'Tes IQ juga ada di tempat lain', q: 'tes iq' } },
  // SPEC §6 search: fixed suggestions + broader terms offered when a search finds nothing.
  searchSuggestions: ['Tes IQ', 'Psikolog anak', 'Konseling'],
  broaderTerms: ['ABK', 'SLB', 'Terapi wicara', 'Tes IQ', 'Konseling', 'Psikolog'],
  sorts: [
    { id: 'buka', label: 'Buka dulu', sub: 'buka hari ini dulu' },
    { id: 'jarak', label: 'Terdekat', sub: 'terdekat dulu' },
    { id: 'nama', label: 'Nama A–Z', sub: 'urut nama' }
  ],
  // Emergency modal (SPEC §8). Titles are UI copy; every number comes from data/hotlines.json.
  hotlineCopy: [
    { match: /^Call Center 112/i, title: '112 · Call Center Kota Banjarbaru', sub: 'Darurat terpadu · 24 jam' },
    { match: /^SAPA 129/i, title: 'SAPA 129 · Kekerasan pada perempuan & anak', sub: 'KemenPPPA · 24 jam' },
    { match: /^Healing119/i, title: 'Healing119 · Dukungan psikologis', sub: 'Kemenkes · pertolongan pertama psikologis · 24 jam' }
  ],
  // Shown when data cannot load at all (SPEC §7) — national numbers, safe to hardcode.
  fallbackHotlines: [
    { label: 'Darurat 112', tel: '112' }, { label: 'SAPA 129', tel: '129' }, { label: 'Healing119', tel: '119' }
  ],

  months: ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'],
  days: ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu'],
  timeZone: 'Asia/Makassar',

  // Labels for contact keys; unknown keys are humanized.
  contactLabels: {
    phone: 'Telepon', whatsapp: 'WhatsApp', phone_whatsapp: 'Telepon/WA', instagram: 'Instagram',
    website: 'Situs web', web: 'Situs web', email: 'Email', facebook: 'Facebook', x: 'X',
    office_phone: 'Telepon kantor', old_landline: 'Telepon lama', booking_link: 'Link booking',
    online_registration: 'Pendaftaran online', online_form: 'Formulir online', note: 'Catatan',
    emergency: 'Darurat', hotline_wa: 'Hotline WA'
  },

  text: {
    verified: 'Terverifikasi',
    unchecked: 'Belum dicek',
    uncheckedTip: 'Info dari sumber publik, mohon konfirmasi via telepon.',
    unpinned: 'Tanpa titik di peta',
    unpinnedNote: 'Alamat atau titiknya belum pasti, jadi tidak ada pin. Telepon dulu sebelum datang.',
    regional: 'Luar kota',
    legendNote: 'Isi penuh + centang = terverifikasi · putih bergaris = belum dicek. Warna selalu berpasangan dengan ikon.',
    // SCHEMA v4 bpjs_info. belum_diketahui is "unknown", never "tidak"; tidak_relevan shows no BPJS chip.
    // Statuses without an entry here (tidak_relevan, or anything unexpected) get no chip.
    // Cards skip statuses listed in cardHidden (Angga, 2026-11-01: the grey chip is detail-only).
    bpjs: {
      status: {
        ya:              { chip: 'BPJS', aria: 'Terima BPJS' },
        sebagian:        { chip: 'BPJS sebagian', aria: 'BPJS hanya untuk sebagian layanan' },
        tidak:           { chip: 'Tidak terima BPJS', aria: 'Menurut sumber, tidak terima BPJS' },
        belum_diketahui: { chip: 'BPJS belum diketahui', aria: 'Status BPJS belum diketahui' }
      },
      cardHidden: ['belum_diketahui'],
      rujukan: 'perlu rujukan', rujukanAria: 'perlu surat rujukan dari faskes 1',
      filter: 'Terima BPJS', filterPart: 'Terima BPJS', filterCond: 'tercatat terima BPJS',
      row: 'BPJS',
      // {n} = places whose BPJS status is unknown (they are left out of the filter, not marked "tidak").
      filterNote: 'Tempat yang tercatat terima BPJS (semua atau sebagian layanan). Status BPJS {n} tempat lain belum diketahui, jadi tidak ikut tampil. Tanyakan langsung ke tempatnya.',
      filterNoteAll: 'Tempat yang tercatat terima BPJS (semua atau sebagian layanan).',
      emptyNote: 'Status BPJS {n} tempat lain belum diketahui.'
    },
    // SCHEMA v5 biaya_gratis. Only ya / bersyarat get a tag; tidak / belum_diketahui show nothing.
    // BPJS acceptance never implies gratis.
    gratis: {
      status: {
        ya:        { tag: 'Gratis', aria: 'Gratis' },
        bersyarat: { tag: 'Gratis bersyarat', aria: 'Gratis dengan syarat' }
      },
      row: 'Biaya',
      recheck: 'perlu dicek ulang',
      cardRecheck: 'cek ulang'       // short hint on the card tag when perlu_cek_ulang (aria says "perlu dicek ulang")
    },
    loadErrorFile: 'Data tidak bisa dimuat. Jalankan "python3 build-data.py" lalu buka lewat server lokal (lihat README).'
  },

  // 24×24 stroke icons from design/src/common.py (stroke 2, round caps).
  icons: {
    leaf: '<path d="M12 21v-8.5"/><path d="M12 13.5C12 9 9 6 4 6c0 4.6 3 7.5 8 7.5z"/><path d="M12 10.5C12 6.6 14.6 4 19.5 4c0 3.9-2.6 6.5-7.5 6.5z"/>',
    blocks: '<rect x="3.5" y="13" width="7.5" height="7.5" rx="1.5"/><rect x="13" y="13" width="7.5" height="7.5" rx="1.5"/><rect x="8.25" y="3.5" width="7.5" height="7.5" rx="1.5"/>',
    shield: '<path d="M12 2.6l8 3.1v5.8c0 4.8-3.3 8.5-8 10.2-4.7-1.7-8-5.4-8-10.2V5.7z"/><path d="M12 8v8.2M10.2 16.2h3.6M8 9.2h8M8 9.2l-1.6 3.6h3.2zM16 9.2l-1.6 3.6h3.2z"/>',
    clipboard: '<rect x="9" y="2.8" width="6" height="3.6" rx="1"/><path d="M15.5 4.6h2a1.5 1.5 0 0 1 1.5 1.5v13.4a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 5 19.5V6.1a1.5 1.5 0 0 1 1.5-1.5h2"/><path d="M9 11.5h6M9 15.5h4"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    phone: '<path d="M6.6 3.5h2.6l1.6 4.2-2 1.3a11 11 0 0 0 5.2 5.2l1.3-2 4.2 1.6v2.6a2 2 0 0 1-2.2 2A15.6 15.6 0 0 1 4.6 5.7a2 2 0 0 1 2-2.2z"/>',
    chat: '<path d="M4.5 19.5l1.2-3.8A7.8 7.8 0 1 1 8.6 18.5z"/><path d="M9 10.5h6M9 13.5h4"/>',
    route: '<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8.2 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.8"/>',
    info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.2M12 7.8v.1"/>',
    chev: '<path d="M6.5 9.5l5.5 5.5 5.5-5.5"/>',
    chevr: '<path d="M9.5 6l6 6-6 6"/>',
    pinoff: '<path d="M8.2 5.1A6.5 6.5 0 0 1 18.5 10c0 1.6-.6 3.2-1.4 4.6M14.6 17.9C13.3 19.6 12 21 12 21s-6.5-5.6-6.5-11c0-.9.2-1.8.5-2.6"/><path d="M3.5 3.5l17 17"/>',
    clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    pin: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.3"/>',
    flag: '<path d="M5.5 21V4.5M5.5 4.5h11l-2 4 2 4h-11"/>',
    locate: '<circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="1.6"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3"/>',
    x: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    calendar: '<rect x="4" y="5.5" width="16" height="14.5" rx="2"/><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    wallet: '<rect x="3.5" y="6" width="17" height="13" rx="2"/><path d="M16 12.5h1.5M3.5 9.5h17"/>',
    search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    back: '<path d="M14.5 6l-6 6 6 6"/>',
    plus: '<path d="M12 5.5v13M5.5 12h13"/>',
    minus: '<path d="M5.5 12h13"/>',
    sort: '<path d="M7 5v14M4 16l3 3 3-3M17 19V5M14 8l3-3 3 3"/>',
    history: '<path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4.5v3.5h3.5"/><path d="M12 8v4.2l2.8 1.8"/>',
    exit: '<path d="M14 4.5h4a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5h-4"/><path d="M10 8l-4 4 4 4M6 12h9"/>',
    wa: '<path d="M4.5 19.5l1.2-3.8A7.8 7.8 0 1 1 8.6 18.5z"/><path d="M9.2 8.6c.2 2.6 2.4 5 5.2 5.4l1-1.2-1.6-.9-.7.6c-.9-.4-1.6-1.1-2-2l.6-.7-.8-1.7z"/>',
    people: '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5"/><circle cx="16.5" cy="9.5" r="2.4"/><path d="M15.5 14.2c2.4-.3 4.4 1.2 5 4.3"/>'
  }
};
