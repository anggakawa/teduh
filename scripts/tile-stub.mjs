// Keeps the browser checks (check.mjs, screens.mjs) off every public tile server.
// OSM's tile policy forbids automated/headless traffic ("Headless bots that pan/zoom the map"), and test runs
// from CI or the box must never count against OpenFreeMap or OSM either. Every request to a known tile host is
// answered locally: OpenFreeMap gets a tiny style with one empty vector source, raster hosts get a flat PNG.
// Set LIVE_TILES=1 only for a single, deliberate live verification.
export const TILE_HOSTS = /^https?:\/\/([a-z0-9-]+\.)*(openfreemap\.org|tile\.openstreetmap\.org|openstreetmap\.fr|basemaps\.cartocdn\.com|cartocdn\.com|stadiamaps\.com|arcgisonline\.com|thunderforest\.com)\//i;
export const isTileUrl = u => TILE_HOSTS.test(u);
export const LIVE = process.env.LIVE_TILES === '1';

// 1×1 PNG in the Positron land colour; Leaflet stretches it to the 256px tile box.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP49PENAAWoAtD979jYAAAAAElFTkSuQmCC', 'base64');
const STYLE = {
  version: 8, name: 'teduh-test-stub',
  sources: { openmaptiles: { type: 'vector', tiles: ['https://tiles.openfreemap.org/planet/stub/{z}/{x}/{y}.pbf'], minzoom: 0, maxzoom: 14 } },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#F2F1EC' } },
    { id: 'water', type: 'fill', source: 'openmaptiles', 'source-layer': 'water', paint: { 'fill-color': '#D9E3E6' } }
  ]
};

// log: every intercepted tile request { url, referer, how } so checks can assert host, Referer and "nothing went live".
export async function stubTiles(ctx, log = []) {
  if (LIVE) return log;
  await ctx.route(TILE_HOSTS, route => {
    const req = route.request(), url = req.url();
    log.push({ url, referer: req.headers()['referer'] || null, how: 'stub' });
    if (/openfreemap\.org\/styles\//.test(url)) return route.fulfill({ status: 200, contentType: 'application/json', headers: { 'access-control-allow-origin': '*' }, body: JSON.stringify(STYLE) });
    if (/\.pbf(\?|$)/.test(url)) return route.fulfill({ status: 200, contentType: 'application/x-protobuf', headers: { 'access-control-allow-origin': '*' }, body: Buffer.alloc(0) });
    if (/\.png(\?|$)/.test(url)) return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: PNG });
    return route.fulfill({ status: 404, headers: { 'access-control-allow-origin': '*' }, body: '' });
  });
  return log;
}
