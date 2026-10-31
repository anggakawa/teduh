// Browser check for Teduh (design/ui SPEC §10). Usage: SITE_DIR=site node scripts/check.mjs [baseUrl]  (default http://localhost:8765/, serving SITE_DIR)
// Needs playwright-core (PW_DIR, default /tmp/pw) and Chrome (CHROME, default /usr/bin/google-chrome).
// Time-aware copy is checked at a fixed moment via the read-only ?now= override (Saturday 31 Oct 2026, 13.56 WITA).
import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import path from 'path';
import { stubTiles, isTileUrl, TILE_HOSTS, LIVE } from './tile-stub.mjs';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = process.env.SITE_DIR ? path.resolve(process.env.SITE_DIR) : path.resolve(here, '../site');
const require = createRequire((process.env.PW_DIR || '/tmp/pw') + '/');
const { chromium } = require('playwright-core');
const base = (process.argv[2] || 'http://localhost:8765/').replace(/\/?$/, '/');
const NOW = '?now=2026-10-31T13:56';
const data = JSON.parse(readFileSync(path.join(root, 'data/places.json'), 'utf8')).places;
const TITLE = 'Teduh — Peta layanan Banjarbaru';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
const dicek = iso => `dicek ${MONTHS[+iso.slice(5, 7) - 1]} ${iso.slice(0, 4)}`;
const tokens = readFileSync(path.join(root, 'css/tokens.css'), 'utf8');
const appCss = readFileSync(path.join(root, 'css/app.css'), 'utf8');

const fails = [];
const ok = (cond, msg) => { console.log((cond ? 'PASS ' : 'FAIL ') + msg); if (!cond) fails.push(msg); };
const isTile = isTileUrl;
const wait = (p, ms = 350) => p.waitForTimeout(ms);

// ---- static: tokens + no stale hardcoded values (SPEC §1, §10 "Tokens") ----
ok(/--sheet-peek:\s*288px/.test(tokens) && /--chip-h:\s*36px/.test(tokens) && /--unverified-ring:\s*#8A948F/i.test(tokens) && /--z-qexit:\s*3000/.test(tokens), 'tokens.css is the design/ui drop-in (peek 288, chip 36, ring #8A948F, z-qexit 3000)');
const stale = ['#B9B2A6', '250px', '34px', 'z-index: 1100', '.22s', 'orange'].filter(s => appCss.toLowerCase().includes(s.toLowerCase()));
ok(stale.length === 0, `app.css hardcodes none of the old values (${stale.join(', ') || 'none'})`);
const hexes = (appCss.match(/#[0-9a-f]{3,8}\b/gi) || []).filter(h => h.toUpperCase() !== '#F3E3B5');
ok(hexes.length === 0, `app.css has no raw colours besides the search <mark> (${hexes.join(', ') || 'none'})`);

const browser = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron', OSM_URL = /^https:\/\/tile\.openstreetmap\.org\/\d+\/\d+\/\d+\.png$/;
const ATTR_VEC = 'OpenFreeMap © OpenMapTiles Data from OpenStreetMap', ATTR_OSM = '© OpenStreetMap contributors';
const siteSrc = ['index.html', 'js/map.js', 'js/config.js', 'js/app.js'].map(f => readFileSync(path.join(root, f), 'utf8')).join('\n');
ok(!/no-referrer/i.test(siteSrc) && /<meta name="referrer" content="strict-origin-when-cross-origin">/.test(siteSrc), 'referrer policy: strict-origin-when-cross-origin, "no-referrer" appears nowhere (OSM tile policy needs a Referer)');

// ================= live tile verification (LIVE_TILES=1 only; one desktop + one mobile load, nothing else) =================
if (LIVE) {
  for (const [vp, mob] of [[{ width: 1440, height: 900 }, false], [{ width: 390, height: 844 }, true]]) {
    const ctx = await browser.newContext({ viewport: vp, isMobile: mob, hasTouch: mob });
    const p = await ctx.newPage(), res = [];
    p.on('response', r => { if (isTile(r.url())) res.push({ u: r.url(), s: r.status(), ref: r.request().headers()['referer'] || null }); });
    await p.goto(base + 'index.html'); await p.waitForSelector('body[data-ready="1"]'); await wait(p, 5000);
    const info = await p.evaluate(() => ({ base: Peta.map.baseInfo(), attr: document.querySelector('.leaflet-control-attribution').textContent, err: document.getElementById('tileError').hidden }));
    const tilesN = res.filter(r => /\.(pbf|png)$/.test(r.u)).length, notOk = res.filter(r => r.s !== 200);
    ok(info.base.kind === 'vector' && res.some(r => r.u === STYLE_URL), `live ${vp.width}: base map is OpenFreeMap Positron (${info.base.kind})`);
    ok(tilesN > 0 && notOk.length === 0, `live ${vp.width}: ${tilesN} tiles, every tile-host response 200, none 403 (${notOk.map(r => r.s + ' ' + r.u).join(' | ') || 'ok'})`);
    ok(res.every(r => r.ref), `live ${vp.width}: every tile request carries a Referer (${[...new Set(res.map(r => r.ref))].join(', ')})`);
    ok(info.attr.includes(ATTR_VEC) && info.err, `live ${vp.width}: attribution "${ATTR_VEC}", no tile error banner`);
    await ctx.close();
  }
  await browser.close();
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL CHECKS PASSED');
  process.exit(fails.length ? 1 : 0);
}

// Every other context is kept off the public tile servers (scripts/tile-stub.mjs). tileLog = what was intercepted,
// tileSeen = every tile-host request the browser made; equal lengths prove nothing reached a real tile server.
const tileLog = [], tileSeen = [];
const newContext0 = browser.newContext.bind(browser);
browser.newContext = async o => {
  const c = await newContext0(o);
  c.on('request', r => { if (isTile(r.url())) tileSeen.push(r.url()); });
  await stubTiles(c, tileLog);
  return c;
};
const abortTiles = (p, re = TILE_HOSTS) => p.route(re, r => { tileLog.push({ url: r.request().url(), referer: r.request().headers()['referer'] || null, how: 'abort' }); return r.abort(); });

async function open(url, viewport, mobile) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 1, isMobile: !!mobile, hasTouch: !!mobile, timezoneId: 'Asia/Makassar' });
  const page = await ctx.newPage();
  const errors = [], bad = [], assets = new Map();
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !isTile(m.text())) errors.push(m.text()); });
  page.on('requestfailed', r => { if (!isTile(r.url())) bad.push(r.url() + ' ' + r.failure()?.errorText); });
  page.on('response', r => {
    const u = r.url();
    if (/\/assets\//.test(u)) assets.set(u.replace(/^.*\/assets\//, 'assets/'), r.status());
    if (r.status() >= 400 && !isTile(u)) bad.push(u + ' ' + r.status());
  });
  // record any storage / history writes
  await page.addInitScript(() => {
    window.__writes = [];
    for (const s of ['localStorage', 'sessionStorage']) {
      try { const st = window[s]; const orig = st.setItem.bind(st); st.setItem = (k, v) => { window.__writes.push(s + ':' + k); return orig(k, v); }; } catch (e) {}
    }
    const ps = history.pushState.bind(history), rs = history.replaceState.bind(history);
    history.pushState = (...a) => { window.__writes.push('pushState'); return ps(...a); };
    history.replaceState = (...a) => { window.__writes.push('replaceState'); return rs(...a); };
    try { const od = indexedDB.open.bind(indexedDB); indexedDB.open = (...a) => { window.__writes.push('indexedDB'); return od(...a); }; } catch (e) {}
  });
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForSelector('body[data-ready="1"]', { timeout: 15000 });
  await wait(page, 2000);
  return { page, ctx, errors, bad, assets };
}

const shouldPin = data.filter(p => typeof p.lat === 'number' && typeof p.lng === 'number').map(p => p.id);
const approxOnly = data.filter(p => !(typeof p.lat === 'number' && typeof p.lng === 'number'));
const nc = data.filter(p => p._d.needs_check);
const byId = Object.fromEntries(data.map(p => [p.id, p]));
const TC = 'traitcare-biro-psikologi-banjarbaru', SG = 'biro-sagraha-psikologi-banjarbaru', RSD = 'rsd-idaman-kota-banjarbaru';

// ================= loading skeleton (data delayed) =================
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const p = await ctx.newPage();
  await p.route('**/data/places.json', async r => { await new Promise(res => setTimeout(res, 1500)); r.continue(); });
  await p.goto(base + 'index.html' + NOW);
  await wait(p, 300);
  const sk = await p.evaluate(() => ({ vis: !document.getElementById('skeleton').hidden, n: document.querySelectorAll('#skeleton .skc').length,
    anim: getComputedStyle(document.querySelector('.sk')).animationDuration, h: document.getElementById('sh1').textContent }));
  ok(sk.vis && sk.n === 3 && sk.anim === '1.2s' && sk.h === 'Memuat…', `loading: 3 skeleton cards with 1.2s shimmer + "Memuat…" (${JSON.stringify(sk)})`);
  await p.waitForSelector('body[data-ready="1"]');
  ok(await p.locator('#skeleton').isHidden(), 'loading: skeleton replaced by the list');
  await ctx.close();
}
// ================= data error =================
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const p = await ctx.newPage();
  await p.route('**/data/**', r => r.abort());
  await p.goto(base + 'index.html' + NOW);
  await p.waitForSelector('body[data-ready="error"]', { timeout: 15000 });
  const de = await p.evaluate(() => ({ h: document.getElementById('sh1').textContent, tels: [...document.querySelectorAll('#dataError a[href^="tel:"]')].map(a => a.getAttribute('href')) }));
  ok(de.h === 'Data belum bisa dimuat' && de.tels.includes('tel:112') && de.tels.includes('tel:129'), `data error: message + emergency tel links (${JSON.stringify(de)})`);
  ok(await p.locator('#emgRow').isVisible(), 'data error: Darurat row still visible');
  await ctx.close();
}
// ================= tile error =================
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await abortTiles(p);
  await p.goto(base + 'index.html' + NOW);
  await p.waitForSelector('body[data-ready="1"]');
  await wait(p, 3000);
  ok(await p.locator('#tileError').isVisible() && await p.locator('.card').count() === data.length, 'tile error: "Peta belum bisa dimuat" notice with retry; the list still works');
  await p.unroute(TILE_HOSTS); await p.click('#tileRetry'); await wait(p, 2500);
  ok(await p.locator('#tileError').isHidden() && await p.evaluate(() => Peta.map.baseInfo().kind) === 'vector', 'tile error: "Coba lagi" reloads the base map and hides the notice once tiles load');
  await ctx.close();
}

// ================= base map fallback: OpenFreeMap unreachable -> OSM raster with a Referer =================
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await ctx.newPage();
  await abortTiles(p, /openfreemap\.org/);
  const from = tileLog.length;
  await p.goto(base + 'index.html' + NOW);
  await p.waitForSelector('body[data-ready="1"]');
  await wait(p, 2500);
  const info = await p.evaluate(() => ({ base: Peta.map.baseInfo(), attr: document.querySelector('.leaflet-control-attribution').textContent, err: document.getElementById('tileError').hidden, filt: getComputedStyle(document.querySelector('.leaflet-tile-pane .teduh-tiles') || document.body).filter }));
  const osm = tileLog.slice(from).filter(t => t.how === 'stub');
  ok(info.base.kind === 'raster' && osm.length > 0 && osm.every(t => OSM_URL.test(t.url)), `fallback: OpenFreeMap down -> OSM raster tiles at https://tile.openstreetmap.org/{z}/{x}/{y}.png (${osm.length})`);
  ok(osm.every(t => t.referer === base.replace(/^(\w+:\/\/[^/]+).*$/, '$1/')), `fallback: every OSM tile request sends the site origin as Referer (${[...new Set(osm.map(t => t.referer))].join(', ')})`);
  ok(info.attr.includes(ATTR_OSM) && !info.attr.includes('OpenFreeMap') && info.err, `fallback: attribution switches to "${ATTR_OSM}", no error banner`);
  ok(/saturate/.test(info.filt), `fallback: OSM raster is desaturated via .teduh-tiles (${info.filt})`);
  await ctx.close();
}

// ================= desktop =================
const D = await open(base + 'index.html' + NOW, { width: 1440, height: 900 });
const { page } = D;
ok(await page.title() === TITLE, `title is "${TITLE}"`);
const st = await page.evaluate(() => ({
  ids: Peta.map.pinnedIds(),
  info: Object.fromEntries(Peta.map.pinnedIds().map(id => [id, Peta.map.markerInfo(id)])),
  via: window.__PETA_STATE__.via,
  font: getComputedStyle(document.body).fontFamily,
  fontOk: document.fonts.check('600 17px "Plus Jakarta Sans"'),
}));
ok(st.via === 'fetch', `data loaded via fetch (${st.via})`);
const bm = await page.evaluate(() => ({ base: Peta.map.baseInfo(), attr: document.querySelector('.leaflet-control-attribution').textContent, err: document.getElementById('tileError').hidden, canvas: !!document.querySelector('.leaflet-gl-layer canvas'), meta: document.querySelector('meta[name=referrer]').content }));
const vt = tileLog.filter(t => t.how === 'stub' && /openfreemap/.test(t.url));
ok(bm.base.kind === 'vector' && bm.canvas && vt.some(t => t.url === STYLE_URL), `base map: OpenFreeMap Positron (${STYLE_URL}) drawn by MapLibre in Leaflet`);
ok(vt.some(t => /\/planet\/.+\.pbf$/.test(t.url)) && vt.every(t => new URL(t.url).host === 'tiles.openfreemap.org'), `base map: vector tiles requested from tiles.openfreemap.org only (${vt.length} requests)`);
ok(bm.meta === 'strict-origin-when-cross-origin' && vt.every(t => t.referer === base.replace(/^(\w+:\/\/[^/]+).*$/, '$1/')), `base map: tile requests send the site origin as Referer (${[...new Set(vt.map(t => t.referer))].join(', ')})`);
ok(bm.attr.includes(ATTR_VEC) && bm.err, `base map: attribution "${ATTR_VEC}" visible, no tile error banner`);
ok(/Plus Jakarta Sans/.test(st.font) && st.fontOk, 'Plus Jakarta Sans loaded (self-hosted)');
ok(st.ids.length === shouldPin.length, `pins ${st.ids.length} == places with real lat/lng ${shouldPin.length}`);
ok(approxOnly.every(p => !st.ids.includes(p.id)), `no pin for the ${approxOnly.length} places without real lat/lng (approx_coords never pinned)`);
const pinnedNc = nc.filter(p => st.ids.includes(p.id));
ok(pinnedNc.every(p => st.info[p.id].iconUrl === `assets/markers/${p._d.group}--belum-dicek.svg`), `every pinned "belum dicek" place uses the hollow marker (${pinnedNc.length})`);
ok(st.ids.filter(id => !byId[id]._d.needs_check).every(id => st.info[id].iconUrl === `assets/markers/${byId[id]._d.group}--terverifikasi.svg`), 'verified places use the filled marker');
ok(st.ids.every(id => st.info[id].title === `${byId[id].name_display || byId[id].name} (${byId[id]._d.needs_check ? 'Belum dicek' : 'Terverifikasi'})`), 'marker title/alt = "name (Terverifikasi|Belum dicek)"');
const imgs = await page.$$eval('.leaflet-marker-icon.teduh-pin', els => els.map(e => e.naturalWidth));
ok(imgs.length > 0 && imgs.every(w => w > 0), `marker SVGs loaded (${imgs.length} on screen)`);
ok(D.bad.length === 0, 'no 404s / failed requests (excluding tiles)' + (D.bad.length ? ': ' + D.bad.join(' | ') : ''));

// desktop chrome (d01)
const dt = await page.evaluate(() => {
  const r = id => document.getElementById(id).getBoundingClientRect();
  const q = document.getElementById('q');
  return { brand: document.querySelector('.brand .wm').textContent, tag: document.querySelector('.tagline').textContent, brandH: document.getElementById('brand').getBoundingClientRect().height,
    ph: q.placeholder, qexit: r('quickExit'), legend: r('legendBtn'), legendText: document.getElementById('legendBtn').textContent.trim(), legendOpen: !document.getElementById('legendPop').hidden,
    zoom: !!document.getElementById('zoomCtl').offsetHeight, panel: r('sheet').width, sh1: document.getElementById('sh1').textContent, sh2: document.getElementById('sh2').textContent,
    sort: document.getElementById('sortLabel').textContent, attr: document.querySelector('.leaflet-control-attribution').textContent,
    chips: [...document.querySelectorAll('#chips .chip')].map(c => c.textContent.trim()) };
});
ok(dt.brand === 'Teduh' && /Peta layanan bantuan/.test(dt.tag) && Math.round(dt.brandH) === 64, 'desktop: 64px panel header with logo, "Teduh" and tagline');
ok(dt.ph === 'Cari layanan, tempat, BPJS…', 'search placeholder "Cari layanan, tempat, BPJS…"');
ok(dt.qexit.top === 16 && 1440 - dt.qexit.right === 16, 'desktop: Keluar cepat fixed top-right 16px');
ok(dt.legendText === 'Keterangan' && !dt.legendOpen && dt.legend.left === 380 + 16, 'desktop: "Keterangan" pill top-left of the map, collapsed by default');
ok(dt.zoom, 'desktop: zoom control bottom-right');
ok(Math.round(dt.panel) === 380, 'desktop: 380px panel');
ok(dt.sh1 === `${data.length} layanan` && dt.sh2 === `${shouldPin.length} di peta · ${approxOnly.length} tanpa titik lokasi` && dt.sort === 'Buka dulu', `desktop header "${dt.sh1}" / "${dt.sh2}" / "${dt.sort}"`);
ok(/Leaflet/.test(dt.attr) && dt.attr.includes(ATTR_VEC), `desktop attribution "Leaflet | ${ATTR_VEC}"`);
ok(dt.chips[0] === 'Terverifikasi saja' && dt.chips[1] === 'Buka hari ini' && dt.chips.length === 6, `chips: toggles first, then 4 categories (${dt.chips.join(' | ')})`);
await page.hover('#quickExit'); await wait(page, 250);
ok(await page.locator('#qexitTip').evaluate(e => getComputedStyle(e).opacity === '1' && /Esc/.test(e.textContent)), 'desktop: Keluar cepat tooltip "Tekan Esc 3× untuk keluar"');
await page.mouse.move(700, 500);

// list cards
const cards = await page.$$eval('.card', bs => bs.map(b => ({ id: b.dataset.id, name: b.querySelector('.cname').textContent,
  nc: b.querySelector('.ncchip')?.textContent || null, ok: b.querySelector('.st.ok')?.textContent || '', cchip: !!b.querySelector('.cchip'),
  aria: b.getAttribute('aria-label'), hrs: b.querySelector('.hrs')?.textContent || '', unpinned: !!b.closest('#listUnpinned') })));
ok(cards.length === data.length, `list shows all ${data.length} places`);
ok(cards[0].id.startsWith('ego-psychology'), `default sort "Buka dulu": Ego Psychology first (${cards[0].id})`);
ok(cards.every(c => !c.cchip), 'cards carry no category chip (tile colour/icon only)');
ok(nc.every(p => cards.find(c => c.id === p.id)?.nc === 'Belum dicek'), `every unchecked place has the grey "Belum dicek" chip, no date (${nc.length})`);
ok(cards.filter(c => !byId[c.id]._d.needs_check).every(c => c.ok === `Terverifikasi · ${dicek(byId[c.id]._d.checked)}`), 'verified cards read "Terverifikasi · dicek Okt 2026"');
const badAria = cards.filter(c => !(c.aria && c.aria.startsWith((byId[c.id].name_display || byId[c.id].name) + ', ') && c.aria.split(', ').length >= 3)).map(c => c.aria);
ok(badAria.length === 0, 'cards have aria-label "name, status, hours"' + (badAria.length ? ': ' + badAria.join(' | ') : ''));
ok(approxOnly.every(p => cards.find(c => c.id === p.id)?.unpinned) && await page.locator('#unpinnedTitle').textContent() === 'Tanpa titik di peta', 'unpinned places listed under "Tanpa titik di peta"');
const nopin = await page.$$eval('#listUnpinned .card', bs => bs.map(b => !!b.querySelector('.hrs--nopin .ic')));
ok(nopin.length > 0 && nopin.every(Boolean), `unpinned cards show the pin-off line instead of the hours line (SPEC §11.2, ${nopin.length})`);
const H = id => cards.find(c => c.id === id).hrs;
ok(/^Buka sekarang 08\.00–18\.00$/.test(H(cards[0].id)), `time-aware: Ego "Buka sekarang 08.00–18.00" (${H(cards[0].id)})`);
ok(/Buka nanti 15\.00–21\.00/.test(cards.find(c => /birru/.test(c.id) && /Buka nanti/.test(c.hrs))?.hrs || ''), 'time-aware: Al-Birru "Buka nanti 15.00–21.00"');
ok(/sudah tutup/.test(H(SG)), `time-aware: Sagraha closed earlier today (${H(SG)})`);
ok(/IGD 24 jam/.test(H(RSD)) && /sudah tutup/.test(H(RSD)), `time-aware: RSD Idaman "${H(RSD)}"`);
ok(cards.every(c => c.hrs.trim().length > 0), 'every card has an hours line with a clock icon');

// no orange / dashed "!" anywhere
const styleScan = await page.evaluate(() => {
  const css = [...document.styleSheets].flatMap(s => { try { return [...s.cssRules].map(r => r.cssText); } catch { return []; } }).join('\n');
  const bangs = [...document.querySelectorAll('.leaflet-marker-pane *, #legendPop *, .card *, #detailBody *')].filter(e => e.children.length === 0 && e.textContent.trim() === '!').length;
  const dashed = [...document.querySelectorAll('.leaflet-marker-pane *, #legendPop *, .chips *, .cards *')].filter(e => getComputedStyle(e).borderStyle.includes('dashed')).length;
  return { orange: /orange|--color-warn|badge--warn/i.test(css), bangs, dashed };
});
ok(!styleScan.orange && styleScan.bangs === 0 && styleScan.dashed === 0, `no orange, dashed or "!" unchecked styling (${JSON.stringify(styleScan)})`);

// clusters
await page.evaluate(() => Peta.map.getMap().setZoom(11, { animate: false }));
await wait(page, 800);
const cl = await page.$$eval('.leaflet-marker-pane .teduh-cluster', els => els.map(e => ({ w: e.getBoundingClientRect().width, aria: e.getAttribute('aria-label'), badge: e.querySelector('.tc-unchecked')?.textContent || null,
  ring: getComputedStyle(e).borderTopColor })));
ok(cl.length > 0 && cl.every(c => Math.round(c.w) === 40 && c.ring === 'rgb(47, 111, 98)') && cl.some(c => c.badge) && cl.every(c => !c.badge || /belum dicek/.test(c.aria)),
  `clusters: 40px white disc, primary ring, grey count = belum dicek (${cl.length})`);
await page.evaluate(() => Peta.map.fit(Peta.map.pinnedIds()));
await wait(page, 600);

// legend popover (c01)
await page.click('#legendBtn'); await wait(page);
const lg = await page.evaluate(() => ({ open: !document.getElementById('legendPop').hidden, imgs: [...document.querySelectorAll('#legendPop img')].map(i => i.getAttribute('src')), text: document.getElementById('legendPop').textContent }));
ok(lg.open && lg.imgs.length === 5 && lg.imgs.filter(s => s.includes('belum-dicek')).length === 1 && /Keterangan/.test(lg.text) && /Belum dicek/.test(lg.text), 'legend popover: 4 category pins + hollow "Belum dicek" row');
await page.keyboard.press('Escape'); await wait(page);
ok(await page.locator('#legendPop').isHidden(), 'legend closes with Esc');

// hover linking
await page.hover(`.card[data-id="${TC}"]`); await wait(page, 200);
const hv = await page.evaluate(id => Peta.map.markerInfo(id).size[0], TC);
ok(hv > 36, `desktop: hovering a card enlarges its pin (${hv})`);
await page.mouse.move(700, 880);

// detail: RSD Idaman (d02)
await page.click(`.card[data-id="${RSD}"]`); await wait(page, 1200);
const d2 = await page.evaluate(id => ({ name: document.querySelector('.dname').textContent, back: document.getElementById('detailBack').offsetHeight > 0, pos: document.getElementById('detailPos').textContent,
  t1: document.querySelector('.today .t1')?.textContent, t2: document.querySelector('.today .t2')?.textContent, t3: document.querySelector('.today .t3')?.textContent,
  ctrl: document.getElementById('controls').offsetHeight, mapBack: document.getElementById('mapBack').offsetHeight,
  info: Peta.map.markerInfo(id), tags: [...document.querySelectorAll('.drow .tag')].map(t => t.textContent) }), RSD);
ok(d2.name === byId[RSD].name && d2.back && /^\d+ dari \d+$/.test(d2.pos) && d2.mapBack === 0 && d2.ctrl === 0, `desktop detail: "‹ Daftar" + "${d2.pos}", no map-back, search hidden`);
ok(d2.t1 === 'Hari ini, Sabtu · Poli sudah tutup' && d2.t2 === '07.45–11.00 WITA' && d2.t3 === 'IGD rumah sakit buka 24 jam', `today box "${d2.t1}" / "${d2.t2}" / "${d2.t3}"`);
ok(d2.info.zIndexOffset === 5000 && !d2.info.inCluster && d2.info.onMap && Math.round(d2.info.size[0]) === 47, `selected pin: 1.3×, zIndexOffset 5000, outside the cluster (${JSON.stringify(d2.info)})`);
ok(await page.locator('.teduh-ground').count() === 1, 'selected pin has a ground shadow');
await page.click('.wk'); await wait(page, 200);
const wk = await page.$$eval('#weekList > div', rs => rs.map(r => ({ t: r.textContent, now: r.classList.contains('now') })));
ok(wk.length === 7 && wk.filter(w => w.now).length === 1 && /Sabtu · hari ini/.test(wk.find(w => w.now).t) && /Tutup/.test(wk[6].t), 'Jadwal expands to 7 rows, today highlighted, Minggu "Tutup"');
ok(await page.locator('#detailBody .seclabel').first().textContent() === 'Layanan', 'LAYANAN section label');
await page.click('#detailBack'); await wait(page);
ok(await page.evaluate(() => document.body.dataset.mode) === 'list' && await page.evaluate(id => Peta.map.markerInfo(id).zIndexOffset, RSD) !== 5000, 'back to list deselects the pin');

// detail: TraitCare (verified)
await page.click(`.card[data-id="${TC}"]`); await wait(page, 1000);
const tc = await page.evaluate(() => ({ st: document.querySelector('#detailBody .st.ok')?.textContent, acts: [...document.querySelectorAll('.acts .act')].map(a => a.textContent.trim()),
  pri: document.querySelectorAll('.acts .act.pri').length, addr: [...document.querySelectorAll('.irow')].map(r => r.textContent).find(t => /Pandu/.test(t)), notice: !!document.querySelector('.notice'),
  rute: document.querySelector('.acts a[href*="destination="]')?.getAttribute('href') || '' }));
ok(tc.st === `Terverifikasi · ${dicek(byId[TC]._d.checked)}` && !tc.notice, 'TraitCare: "Terverifikasi · dicek Okt 2026", no notice');
ok(tc.acts.join('|') === 'Rute' && tc.pri === 1, `TraitCare actions ${tc.acts.join(' / ')} (no Telepon/WhatsApp: no owner-published number yet, consent policy)`);
ok(/destination=-3\./.test(tc.rute), 'Rute uses real lat,lng');
ok(/Jl\. Pandu, Banjarbaru/.test(tc.addr) && /Kelurahan berbeda antar sumber \(Guntung Manggis \/ Guntung Paikat\)/.test(tc.addr), 'TraitCare address: clean line + Indonesian conflict sub-line');
await page.click('#detailBack'); await wait(page);

// detail: Sagraha (unchecked, 2 numbers)
await page.click(`.card[data-id="${SG}"]`); await wait(page, 1000);
const sg = await page.evaluate(() => ({ nc: document.querySelector('#detailBody .ncchip')?.textContent, ok: !!document.querySelector('#detailBody .st.ok'),
  notice: document.querySelector('.notice')?.textContent || '', acts: [...document.querySelectorAll('.acts .act')].map(a => a.textContent.trim()), t1: document.querySelector('.today .t1')?.textContent }));
ok(sg.nc === 'Belum dicek' && !sg.ok && /Info dari sumber publik, mohon konfirmasi via telepon\./.test(sg.notice), 'Sagraha: grey chip + notice "Info dari sumber publik, mohon konfirmasi via telepon."');
ok(sg.acts.join('|') === 'Rute', `Sagraha actions ${sg.acts.join(' / ')} (numbers removed: no owner-published source)`);
ok(sg.t1 === 'Hari ini, Sabtu · Sudah tutup', `Sagraha today "${sg.t1}"`);
await page.click('#detailBack'); await wait(page);

// detail: Birru Care (phone + WhatsApp, both from the owner's site)
const BC = 'birru-care-banjarbaru';
await page.click(`.card[data-id="${BC}"]`); await wait(page, 1000);
const bc = await page.evaluate(() => ({ acts: [...document.querySelectorAll('.acts .act')].map(a => a.textContent.trim()), pri: document.querySelectorAll('.acts .act.pri').length,
  tel: document.querySelector('.acts a[href^="tel:"]')?.getAttribute('href') }));
ok(bc.acts.slice(0, 2).join('|') === 'Telepon|WhatsApp' && bc.pri === 1 && bc.tel === 'tel:+6285342881997', `Birru Care actions ${bc.acts.join(' / ')} (Telepon filled, ${bc.tel})`);
await page.click('#detailBack'); await wait(page);

// phone chooser: no record has two conflicting owner-published numbers now, so inject example
// entries (not real numbers) into Sagraha in this page only.
{
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const cp = await ctx.newPage();
  await cp.route('**/data/places.json', async r => {
    const body = JSON.parse(await (await r.fetch()).text());
    const sgp = body.places.find(x => x.id === SG);
    sgp._d.phones = [['Contoh A', '+620000000001'], ['Contoh B', '+620000000002']].map(([source, tel]) =>
      ({ label: 'phone', display: tel, tel, mobile: false, wa: false, conflict: true, source }));
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await cp.goto(base + 'index.html' + NOW); await cp.waitForSelector('body[data-ready="1"]'); await wait(cp, 500);
  await cp.click(`.card[data-id="${SG}"]`); await wait(cp, 1000);
  const ca = await cp.evaluate(() => [...document.querySelectorAll('.acts .act')].map(a => a.textContent.trim()));
  ok(ca[0] === 'Telepon · 2 nomor', `two conflicting numbers -> chooser button (${ca.join(' / ')})`);
  await cp.click('.acts [data-act="phones"]'); await wait(cp);
  const ph = await cp.$$eval('#phoneList .hl', hs => hs.map(h => h.textContent));
  ok(ph.length === 2 && ph.every(t => /Sumber: /.test(t)), `phone chooser lists 2 numbers with sources (${ph.join(' | ')})`);
  await cp.keyboard.press('Escape'); await wait(cp);
  ok(await cp.locator('#phoneModal').isHidden(), 'phone chooser closes with Esc');
  await ctx.close();
}

// unpinned detail
const un = approxOnly.find(p => p.approx_coords) || approxOnly[0];
await page.click(`.card[data-id="${un.id}"]`); await wait(page, 500);
const ud = await page.evaluate(() => ({ text: document.getElementById('detailBody').textContent, rute: document.querySelectorAll('.acts a[href*="/maps/dir/"]').length }));
ok(/Tanpa titik di peta/.test(ud.text) && ud.rute === 0, `unpinned detail (${un.id}): "Tanpa titik di peta", Rute hidden`);
const wa = await page.$$eval('#detailBody a[href^="https://wa.me/"]', as => as.map(a => a.href));
ok(wa.every(h => /^https:\/\/wa\.me\/62\d{8,13}$/.test(h)), 'WA links normalized');
await page.click('#detailBack'); await wait(page);

// filters (m04) + empty (m07)
await page.click('.chip[data-t="ok"]'); await page.click('.chip[data-t="today"]'); await page.click('.chip[data-group="tumbuh-kembang-anak"]'); await wait(page, 500);
const f4 = await page.evaluate(() => ({ h1: document.getElementById('sh1').textContent, h2: document.getElementById('sh2').textContent, clear: !document.getElementById('clearFilters').hidden,
  ids: [...document.querySelectorAll('.card')].map(c => c.dataset.id), shown: Peta.map.shownCount(), first: document.querySelector('#chips .chip[data-group]')?.dataset.group,
  pressed: [...document.querySelectorAll('#chips .chip[aria-pressed="true"]')].length }));
ok(f4.h1 === '3 layanan cocok' && f4.h2 === 'Terverifikasi · Buka hari ini · Tumbuh kembang' && f4.clear, `filter header "${f4.h1}" / "${f4.h2}" + Hapus filter`);
ok(f4.ids.length === 3 && f4.shown === 3 && f4.first === 'tumbuh-kembang-anak' && f4.pressed === 3, `filter list+map 3 results, active chip pinned first, aria-pressed (${f4.ids.join(', ')})`);
await page.click('#clearFilters'); await page.click('.chip[data-t="ok"]'); await page.click('.chip[data-group="psikologi"]'); await wait(page, 500);
const e7 = await page.evaluate(() => ({ h1: document.getElementById('sh1').textContent, text: document.getElementById('empty').textContent, btns: [...document.querySelectorAll('#empty .btn')].map(b => b.textContent), note: !document.getElementById('mapNote').hidden }));
ok(e7.h1 === '0 layanan cocok' && /Belum ada biro tes psikologi yang terverifikasi\. Ada 1 tempat yang belum dicek\./.test(e7.text), 'empty (filter): sentence with live unchecked count');
ok(e7.btns.join('|') === 'Hapus filter|Tampilkan 1 yang belum dicek' && /Tes IQ juga ada di tempat lain · cari “tes iq” \(\d+\)/.test(e7.text) && e7.note, 'empty (filter): two buttons, cross-suggestion, map chip');
await page.click('#empty [data-act="showun"]'); await wait(page);
ok(await page.locator('.card').count() === 1 && !(await page.locator('.chip[data-t="ok"]').getAttribute('aria-pressed') === 'true'), '"Tampilkan 1 yang belum dicek" drops the verified filter');
await page.click('#clearFilters'); await wait(page);

// search (d03 empty + results)
await page.fill('#q', 'terapi wicara'); await wait(page, 500);
const sr = await page.evaluate(() => ({ h1: document.getElementById('sh1').textContent, marks: document.querySelectorAll('.card mark').length }));
ok(sr.h1 === '9 hasil' && sr.marks > 0, `search "terapi wicara": ${sr.h1}, matches highlighted (${sr.marks} marks)`);
await page.fill('#q', 'bahasa isyarat'); await wait(page, 500);
const e3 = await page.evaluate(() => ({ h1: document.getElementById('sh1').textContent, h2: document.getElementById('sh2').textContent, text: document.getElementById('empty').textContent,
  broader: [...document.querySelectorAll('#empty .bchip')].map(b => b.textContent), note: !document.getElementById('mapNote').hidden, back: getComputedStyle(document.getElementById('qBack')).display }));
ok(e3.h1 === '0 hasil' && e3.h2 === 'Semua kategori · nama, layanan, kelurahan' && /Tidak ada hasil untuk “bahasa isyarat”/.test(e3.text), 'empty (search): "0 hasil" header + message');
ok(e3.broader.length >= 2 && e3.broader.every(b => /· \d+$/.test(b)) && /Hapus pencarian/.test(e3.text) && e3.note && e3.back !== 'none', `empty (search): broader chips with live counts (${e3.broader.join(', ')}), map chip, ‹ back icon`);
await page.click('#empty .bchip'); await wait(page, 500);
ok(+/^(\d+)/.exec(await page.locator('#sh1').textContent())[1] > 0, 'broader chip runs that search');
await page.fill('#q', 'bpjs'); await wait(page, 400);
const nb = await page.locator('.card').count();
ok(nb > 0 && nb < data.length, `search "bpjs" filters the list (${nb})`);
await page.click('#qClear'); await wait(page, 400);

// emergency modal (m08) + focus trap
await page.click('#emgRow'); await wait(page);
const em = await page.evaluate(() => ({ title: document.getElementById('emgTitle').textContent, sub: document.getElementById('emgSub').textContent,
  names: [...document.querySelectorAll('#hotlines .hl .n')].map(n => n.textContent), big: [...document.querySelectorAll('#hotlines .hbtn.big')].map(b => b.getAttribute('href')),
  hrefs: [...document.querySelectorAll('#hotlines a')].map(a => a.getAttribute('href')), line: document.querySelector('.hline')?.textContent || '',
  qz: +getComputedStyle(document.getElementById('quickExit')).zIndex, mz: +getComputedStyle(document.getElementById('emgModal')).zIndex,
  top: (() => { const r = document.getElementById('quickExit').getBoundingClientRect(); return document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)?.closest('#quickExit') != null; })() }));
ok(em.title === 'Bantuan darurat' && /^Gratis · nomor resmi · dicek \w+ \d{4}$/.test(em.sub), `modal header "${em.title}" / "${em.sub}"`);
ok(/^112 /.test(em.names[0]) && /^SAPA 129/.test(em.names[1]) && /^Healing119/.test(em.names[2]) && em.big.length === 1 && em.big[0] === 'tel:112', `hotlines ordered 112 → SAPA 129 → Healing119, only 112 filled (${em.names.join(' | ')})`);
ok(em.hrefs.includes('tel:129') && em.hrefs.some(h => /^https:\/\/wa\.me\/62811/.test(h)) && em.hrefs.includes('tel:119') && /Ambulans PSC 119/.test(em.line) && /Polres/.test(em.line), 'SAPA call + WhatsApp, Healing119, PSC/Polres line');
ok(em.qz > em.mz && em.top, `Keluar cepat stays above the modal (z ${em.qz} > ${em.mz}) and clickable`);
const focusIn = [];
for (let i = 0; i < 9; i++) { await page.keyboard.press('Tab'); focusIn.push(await page.evaluate(() => !!document.activeElement.closest('#emgModal .modal-card'))); }
ok(focusIn.every(Boolean), 'emergency modal traps focus');
await page.keyboard.press('Escape'); await wait(page);
ok(await page.locator('#emgModal').isHidden() && await page.evaluate(() => document.activeElement.id) === 'emgRow', 'modal closes with Esc and returns focus to the Darurat row');

// privacy: no storage, no history writes
const priv = await page.evaluate(() => ({ writes: window.__writes, ls: localStorage.length, ss: sessionStorage.length, hash: location.hash, hl: history.length }));
ok(priv.writes.length === 0 && priv.ls === 0 && priv.ss === 0 && priv.hash === '', `no storage/history writes (${JSON.stringify(priv)})`);
ok(await page.locator('#liveCount[aria-live="polite"]').count() === 1, 'result count is announced (aria-live)');
ok(D.errors.length === 0, 'no JS errors on desktop' + (D.errors.length ? ': ' + D.errors.join(' | ') : ''));
await D.ctx.close();

// ================= mobile =================
const M = await open(base + 'index.html' + NOW, { width: 390, height: 844 }, true);
const mp = M.page;
const sheetH = () => mp.evaluate(() => Math.round(document.getElementById('sheet').getBoundingClientRect().height));
ok(await sheetH() === 288, `mobile: launches at peek 288px (${await sheetH()})`);
const mt = await mp.evaluate(() => {
  const r = s => document.querySelector(s).getBoundingClientRect();
  return { top: r('#toprow').top, search: r('#searchForm').top, searchH: r('#searchForm').height, chips: r('#chips .chipsin').top, chipH: r('#chips .chip').height,
    fab: r('#locateBtn'), leg: r('#legendBtn'), sheetTop: r('#sheet').top, attr: r('.leaflet-control-attribution'), emg: r('#emgRow'),
    h1: document.getElementById('sh1').textContent, h2: document.getElementById('sh2').textContent, sort: document.getElementById('sortLabel').textContent,
    first: document.querySelector('.card .cname').textContent, legendText: getComputedStyle(document.querySelector('#legendBtn .lb-t')).display };
});
ok(mt.top === 4 && mt.search === 52 && mt.searchH === 48 && mt.chips === 108 && mt.chipH === 36, `mobile: top row 4, search 52 (48 tall), chips 108 (36 tall) (${mt.top}/${mt.search}/${mt.chips})`);
ok(Math.round(mt.sheetTop - mt.fab.bottom) === 12 && Math.round(mt.fab.top - mt.leg.bottom) === 8 && 390 - mt.fab.right === 12 && mt.legendText === 'none', 'mobile: ⓘ and locate FABs in the right gutter, 12 above the sheet, 8 apart');
ok(Math.round(mt.sheetTop - mt.attr.bottom) === 4 && mt.attr.left < 50, 'mobile: attribution bottom-left, 4px above the sheet');
ok(mt.emg.bottom <= 844 && mt.emg.height >= 56, 'mobile: Darurat row pinned at the sheet bottom');
ok(mt.h1 === `${data.length} layanan` && mt.h2 === 'Banjarbaru & sekitar · buka hari ini dulu' && mt.sort === 'Urutkan', `mobile header "${mt.h1}" / "${mt.h2}" + Urutkan`);
ok(mt.first.startsWith('Ego Psychology'), 'mobile: Ego Psychology first');
// sheet: tap grab cycles; header tap → half
await mp.click('#grabBtn'); await wait(mp, 400);
ok(await sheetH() === Math.round(844 * 0.55), 'mobile: grab tap peek → half (55%)');
await mp.click('#grabBtn'); await wait(mp, 400);
const fullTop = await mp.evaluate(() => [document.getElementById('sheet').getBoundingClientRect().top, document.getElementById('chips').getBoundingClientRect().bottom]);
ok(Math.abs(fullTop[0] - fullTop[1]) < 2, `mobile: full list stops right below the chip row (${Math.round(fullTop[0])} / ${Math.round(fullTop[1])})`);
ok(await mp.locator('#grabBtn').getAttribute('aria-label') === 'Perkecil daftar', 'grab button label switches to "Perkecil daftar" at full');
await mp.click('#grabBtn'); await wait(mp, 400);
// drag the header down to peek
const sb = await mp.locator('#shead').boundingBox();
await mp.mouse.move(sb.x + 30, sb.y + 10); await mp.mouse.down(); await mp.mouse.move(sb.x + 30, sb.y + 200, { steps: 8 }); await mp.mouse.up(); await wait(mp, 400);
ok(await sheetH() === 288, 'mobile: dragging the header snaps back to peek');

// search mode (m03)
await mp.click('#q'); await mp.fill('#q', 'terapi wicara'); await wait(mp, 500);
const s3 = await mp.evaluate(() => ({ mode: document.body.dataset.search, chips: document.getElementById('chips').offsetHeight, extra: !document.getElementById('searchExtra').hidden,
  sug: [...document.querySelectorAll('#suggest [data-q]')].map(b => b.textContent), h1: document.getElementById('sh1').textContent, h2: document.getElementById('sh2').textContent,
  peta: !document.getElementById('toMap').hidden, state: document.getElementById('sheet').dataset.state, back: getComputedStyle(document.getElementById('qBack')).display,
  match: document.querySelector('.card .crow--match')?.textContent }));
ok(s3.mode === '1' && s3.chips === 0 && s3.extra && s3.back !== 'none' && s3.state === 'full', 'mobile search mode: ‹ back, chips hidden, suggestions shown, sheet full');
ok(s3.sug.join('|') === 'Tes IQ|Psikolog anak|Konseling', 'suggestions "Tes IQ · Psikolog anak · Konseling"');
ok(s3.h1 === '9 hasil untuk “terapi wicara”' && s3.h2 === 'Buka hari ini dulu · cari nama, layanan, kelurahan' && s3.peta, `search header "${s3.h1}" + Peta`);
ok(/terapi wicara/i.test(s3.match || ''), `match row shows why it matched ("${s3.match}")`);
await mp.press('#q', 'Enter'); await wait(mp, 400);
await mp.click('#q'); await wait(mp, 300);
const rec = await mp.evaluate(() => ({ items: [...document.querySelectorAll('#recent .schip-b')].map(b => b.textContent), note: document.querySelector('.sx-note').textContent, ls: localStorage.length + sessionStorage.length, w: window.__writes }));
ok(rec.items[0] === 'terapi wicara' && rec.note === 'hanya sesi ini' && rec.ls === 0 && rec.w.length === 0, 'recent searches: in memory only ("hanya sesi ini"), nothing stored');
await mp.click('#qBack'); await wait(mp, 400);
ok(await mp.evaluate(() => document.body.dataset.search) === '0' && await mp.inputValue('#q') === '', 'search ‹ back clears and leaves search mode');

// detail (m05): map-back only, pin visible above the sheet
await mp.click('#grabBtn'); await wait(mp, 400);
await mp.click(`.card[data-id="${TC}"]`); await wait(mp, 1500);
const vis = await mp.evaluate(() => {
  const pin = document.querySelector('.teduh-pin.is-selected')?.getBoundingClientRect();
  const sheet = document.getElementById('sheet').getBoundingClientRect();
  const top = document.getElementById('toprow').getBoundingClientRect();
  return pin && { pinTop: Math.round(pin.top), pinBottom: Math.round(pin.bottom), sheetTop: Math.round(sheet.top), topBottom: Math.round(top.bottom), mode: document.body.dataset.mode,
    mapBack: document.getElementById('mapBack').offsetHeight, dback: document.getElementById('detailBack').offsetHeight, state: document.getElementById('sheet').dataset.state };
});
ok(vis && vis.mode === 'detail' && vis.state === 'half' && vis.pinBottom < vis.sheetTop && vis.pinTop > vis.topBottom, `mobile detail at half, selected pin visible between top row and sheet ${JSON.stringify(vis)}`);
ok(vis && vis.mapBack === 40 && vis.dback === 0, 'mobile detail: only the map-back button (no "‹ Daftar")');
await mp.click('#mapBack'); await wait(mp, 400);
ok(await mp.evaluate(() => document.body.dataset.mode) === 'list' && await sheetH() === 288, 'mobile: map-back returns to the list at peek');
ok(M.bad.length === 0, 'mobile: no failed requests' + (M.bad.length ? ': ' + M.bad.join(' | ') : ''));
ok(M.errors.length === 0, 'no JS errors on mobile' + (M.errors.length ? ': ' + M.errors.join(' | ') : ''));
// touch targets
const small = await mp.evaluate(() => [...document.querySelectorAll('#toprow button, #toprow a, .chip, #locateBtn, #legendBtn, .card, #emgRow, #sortWrap')]
  .filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect(); const a = getComputedStyle(e, '::after'); const ext = a.content !== 'none' ? 8 : 0; return { id: e.id || e.className, h: r.height + ext }; })
  .filter(x => x.h < 44));
ok(small.length === 0, `mobile hit areas ≥ 44px (${JSON.stringify(small)})`);
// quick exit (Esc ×3)
await mp.route('https://www.google.com/**', r => r.fulfill({ status: 200, contentType: 'text/html', body: 'ok' }));
await mp.keyboard.press('Escape'); await mp.keyboard.press('Escape'); await mp.keyboard.press('Escape');
await wait(mp, 800);
ok(mp.url().startsWith('https://www.google.com/'), `Keluar cepat via Esc ×3 → ${mp.url()}`);
await M.ctx.close();
// ================= touch gestures on the sheet (real touch events via CDP, not mouse) =================
// The live bug (31 Oct 2026): `touch-action: pan-y` on the sheet let the browser own every vertical swipe,
// so it sent pointercancel on the first move and the sheet never followed the finger.
{
  const T = await open(base + 'index.html' + NOW, { width: 390, height: 844 }, true);
  const tp = T.page;
  const cdp = await T.ctx.newCDPSession(tp);
  await tp.evaluate(() => { window.__pc = 0; addEventListener('pointercancel', () => window.__pc++, true); });
  const S = () => tp.evaluate(() => { const s = document.getElementById('sheet'), b = s.querySelector('.view:not([hidden]) .sbody');
    return { mode: document.body.dataset.mode, state: s.dataset.state, top: Math.round(s.getBoundingClientRect().top), h: Math.round(s.getBoundingClientRect().height), scroll: b ? Math.round(b.scrollTop) : -1 }; });
  // slow swipe (< 0.5 px/ms, so it snaps to the nearest point, not a fling); returns the sheet top halfway through
  async function swipe(y0, y1, x = 195, ms = 800, steps = 20) {
    let mid = null;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y: y0 }] });
    for (let i = 1; i <= steps; i++) {
      await tp.waitForTimeout(ms / steps);
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x, y: y0 + (y1 - y0) * i / steps }] });
      if (i === steps / 2) mid = (await S()).top;
    }
    await tp.waitForTimeout(50);
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await wait(tp, 450);
    return mid;
  }
  const ta = await tp.evaluate(() => ({ sheet: getComputedStyle(document.getElementById('sheet')).touchAction, grab: getComputedStyle(document.getElementById('grabBtn')).touchAction }));
  ok(ta.sheet === 'none' && ta.grab === 'none', `touch: sheet and handle own vertical drags (touch-action ${JSON.stringify(ta)})`);
  let s0 = await S(), mid;
  mid = await swipe(s0.top + 8, s0.top - 176);
  let s1 = await S();
  ok(mid < s0.top - 60 && s1.state === 'half', `touch: dragging the handle up follows the finger (mid top ${mid} < ${s0.top}) and snaps peek → half (${s1.state})`);
  s0 = s1; mid = await swipe(s0.top + 30, s0.top - 200);
  s1 = await S();
  ok(mid < s0.top - 60 && s1.state === 'full', `touch: dragging the list header up: half → full (${s1.state}, top ${s1.top})`);
  const bodyY = s1.top + 360;
  await swipe(bodyY, bodyY - 250);
  s1 = await S();
  ok(s1.state === 'full' && s1.scroll > 100, `touch: at full the list scrolls with a swipe up (scrollTop ${s1.scroll}, ${s1.state})`);
  await swipe(bodyY - 100, bodyY + 50);
  let s2 = await S();
  ok(s2.state === 'full' && s2.scroll < s1.scroll, `touch: at full and scrolled, a swipe down scrolls the list back (${s1.scroll} → ${s2.scroll}), sheet stays full`);
  await tp.evaluate(() => { document.getElementById('listScroll').scrollTop = 0; }); await wait(tp, 100);
  await swipe(bodyY, bodyY + 220);
  s2 = await S();
  ok(s2.state !== 'full' && s2.top > s1.top + 100, `touch: at scrollTop 0, pulling the list down drags the sheet (full → ${s2.state})`);
  mid = await swipe(s2.top + 8, s2.top + 200);
  s2 = await S();
  ok(s2.state === 'peek' && s2.mode === 'list', `touch: dragging the handle down snaps to peek (${s2.state})`);
  await tp.tap('#grabBtn'); await wait(tp, 400); const g1 = (await S()).state;
  await tp.tap('#grabBtn'); await wait(tp, 400); const g2 = (await S()).state;
  await tp.tap('#grabBtn'); await wait(tp, 400); const g3 = (await S()).state;
  ok([g1, g2, g3].join('|') === 'half|full|half', `touch: tapping the handle cycles peek → half → full → half (${[g1, g2, g3].join(' → ')})`);
  // detail
  await tp.tap(`.card[data-id="${SG}"]`); await wait(tp, 1200);
  s0 = await S();
  ok(s0.mode === 'detail' && s0.state === 'half', `touch: detail opens at half (${s0.mode}/${s0.state})`);
  mid = await swipe(s0.top + 8, s0.top + 176);
  s1 = await S();
  ok(mid > s0.top + 60 && s1.mode === 'detail' && s1.state === 'peek', `touch: detail handle drag down follows the finger (mid ${mid}) and snaps half → peek (${s1.mode}/${s1.state})`);
  mid = await swipe(s1.top + 30, s1.top - 400, 195, 1000, 20);
  s1 = await S();
  ok(s1.mode === 'detail' && s1.state === 'full', `touch: detail header drag up to full (${s1.state}, top ${s1.top})`);
  const dy = s1.top + 300;
  await swipe(dy, dy + 250);
  s2 = await S();
  ok(s2.mode === 'detail' && s2.state !== 'full', `touch: detail at full + scrollTop 0, pulling the content down drags the sheet (${s2.state})`);
  if (s2.state === 'half') { await swipe(s2.top + 8, s2.top + 176); s2 = await S(); }
  ok(s2.mode === 'detail' && s2.state === 'peek', `touch: detail reaches peek (${s2.state})`);
  await swipe(s2.top + 8, s2.top + 160);
  s2 = await S();
  ok(s2.mode === 'list' && s2.state === 'peek', `touch: dragging down from peek in the detail closes it, back to the list at peek (${s2.mode}/${s2.state})`);
  await tp.tap(`.card[data-id="${SG}"]`); await wait(tp, 1200);
  await tp.tap('#mapBack'); await wait(tp, 500);
  s2 = await S();
  ok(s2.mode === 'list' && s2.state === 'peek', `touch: the map back button still closes the detail (${s2.mode}/${s2.state})`);
  ok(T.errors.length === 0, 'touch: no JS errors' + (T.errors.length ? ': ' + T.errors.join(' | ') : ''));
  await T.ctx.close();
}
// quick exit (one tap, history replaced)
{
  const Q = await open(base + 'index.html' + NOW, { width: 390, height: 844 }, true);
  await Q.page.route('https://www.google.com/**', r => r.fulfill({ status: 200, contentType: 'text/html', body: 'ok' }));
  const hl = await Q.page.evaluate(() => history.length);
  await Q.page.click('#quickExit'); await wait(Q.page, 800);
  ok(Q.page.url().startsWith('https://www.google.com/') && await Q.page.evaluate(() => history.length) === hl, 'Keluar cepat: one tap, replaces the history entry');
  await Q.ctx.close();
}
// reduced motion
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, reducedMotion: 'reduce' });
  const p = await ctx.newPage(); await p.goto(base + 'index.html' + NOW); await p.waitForSelector('body[data-ready="1"]');
  ok(await p.evaluate(() => getComputedStyle(document.getElementById('sheet')).transitionDuration) === '0s', 'prefers-reduced-motion: sheet transition off');
  await ctx.close();
}

// ================= file:// fallback =================
const F = await open('file://' + path.join(root, 'index.html'), { width: 1280, height: 800 });
const fv = await F.page.evaluate(() => ({ via: window.__PETA_STATE__.via, pins: Peta.map.pinnedCount(), font: document.fonts.check('600 17px "Plus Jakarta Sans"'), img: [...document.querySelectorAll('.teduh-pin')].every(i => i.naturalWidth > 0) }));
ok(fv.via === 'file-fallback' && fv.pins === shouldPin.length && fv.font && fv.img, `file:// works via data.js fallback (${JSON.stringify(fv)})`);
await F.ctx.close();

ok(tileLog.length > 0 && tileSeen.length === tileLog.length, `no request reached a public tile server: ${tileSeen.length} tile-host requests, all ${tileLog.length} answered by the local stub`);
await browser.close();
console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL CHECKS PASSED');
process.exit(fails.length ? 1 : 0);
