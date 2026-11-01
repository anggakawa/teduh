// Screenshots for review. Usage: node scripts/screens.mjs [baseUrl]  → screenshots/*.png (390×844 and 1440×900).
// Map tiles are stubbed locally (scripts/tile-stub.mjs) so screenshot runs never hit a public tile server;
// LIVE_TILES=1 shows the real base map for a one-off review.
// Uses the read-only ?now= override so the hours copy matches the mockups (Sabtu 31 Okt 2026, 13.56 WITA).
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import path from 'path';
import { stubTiles } from './tile-stub.mjs';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');   // screenshots/ at the repo root
const require = createRequire((process.env.PW_DIR || '/tmp/pw') + '/');
const { chromium } = require('playwright-core');
const base = (process.argv[2] || 'http://localhost:8765/').replace(/\/?$/, '/') + 'index.html?now=2026-10-31T13:56';
const out = n => path.join(root, 'screenshots', n + '.png');
const b = await chromium.launch({ executablePath: process.env.CHROME || '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const w = (p, ms = 600) => p.waitForTimeout(ms);
async function page(width, height, mobile) {
  const ctx = await b.newContext({ viewport: { width, height }, deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile, timezoneId: 'Asia/Makassar' });
  await stubTiles(ctx);
  const p = await ctx.newPage();
  await p.goto(base); await p.waitForSelector('body[data-ready="1"]'); await w(p, 2500);
  return p;
}
const shots = [];
const snap = async (p, n) => { await w(p, 1200); await p.screenshot({ path: out(n) }); shots.push(out(n)); };

// ---- mobile 390×844 ----
let m = await page(390, 844, true);
await snap(m, 'm-01-main');
await m.click('.card[data-id="traitcare-biro-psikologi-banjarbaru"]'); await w(m);
await m.evaluate(() => Peta.sheet.set('full')); await m.click('.wk');
await snap(m, 'm-02-detail-verified');
await m.click('#mapBack'); await w(m);
await m.click('.card[data-id="biro-sagraha-psikologi-banjarbaru"]');
await snap(m, 'm-03-detail-unverified');
await m.click('#mapBack'); await w(m);
await m.click('#q'); await m.fill('#q', 'bahasa isyarat'); await m.press('#q', 'Enter');
await snap(m, 'm-04-empty-search');
await m.click('#qClear'); await m.keyboard.press('Escape'); await w(m);
await m.click('.chip[data-t="ok"]'); await m.click('.chip[data-group="psikologi"]');
await snap(m, 'm-05-empty-filter');
await m.click('#clearFilters'); await w(m);
// BPJS (SCHEMA v4): filter active, then a detail with the BPJS row in view
await m.click('.chip[data-t="bpjs"]'); await m.evaluate(() => Peta.sheet.set('full'));
await snap(m, 'm-07-bpjs-filter');
await m.click('.card[data-id="rsu-syifa-medika-banjarbaru"]'); await w(m);
await m.evaluate(() => { Peta.sheet.set('full'); document.querySelector('#detailBody .irow-bpjs').scrollIntoView({ block: 'center' }); });
await snap(m, 'm-08-detail-bpjs');
await m.click('#mapBack'); await w(m); await m.click('#clearFilters'); await w(m);
// Gratis (SCHEMA v5 biaya_gratis): bersyarat + perlu_cek_ulang in the detail
await m.click('.card[data-id="bnn-kota-banjarbaru"]'); await w(m);
await m.evaluate(() => { Peta.sheet.set('full'); document.querySelector('#detailBody .irow-gratis').scrollIntoView({ block: 'center' }); });
await snap(m, 'm-09-detail-gratis');
await m.click('#mapBack'); await w(m); await m.evaluate(() => Peta.sheet.set('peek'));
await m.click('#emgRow'); await m.locator('#quickExit').hover().catch(() => {});
await snap(m, 'm-06-darurat-keluar-cepat');
await m.context().close();

// ---- desktop 1440×900 ----
let d = await page(1440, 900, false);
await snap(d, 'd-01-main');
await d.click('.card[data-id="rsd-idaman-kota-banjarbaru"]'); await w(d); await d.click('.wk');
await snap(d, 'd-02-detail-verified');
await d.click('#detailBack'); await w(d);
await d.click('.card[data-id="biro-sagraha-psikologi-banjarbaru"]');
await snap(d, 'd-03-detail-unverified');
await d.click('#detailBack'); await w(d);
await d.fill('#q', 'bahasa isyarat');
await snap(d, 'd-04-empty-search');
await d.click('#empty [data-act="clearq"]'); await w(d);
await d.click('.chip[data-t="bpjs"]');
await snap(d, 'd-06-bpjs-filter');
await d.click('.card[data-id="rsd-idaman-kota-banjarbaru"]'); await w(d);
await d.evaluate(() => document.querySelector('#detailBody .irow-bpjs').scrollIntoView({ block: 'center' }));
await snap(d, 'd-07-detail-bpjs');
await d.click('#detailBack'); await w(d); await d.click('#clearFilters'); await w(d);
await d.click('.card[data-id="posbakum-pengadilan-agama-banjarbaru"]'); await w(d);
await d.evaluate(() => document.querySelector('#detailBody .irow-gratis').scrollIntoView({ block: 'center' }));
await snap(d, 'd-08-detail-gratis');
await d.click('#detailBack'); await w(d);
await d.click('#emgRow'); await d.hover('#quickExit');
await snap(d, 'd-05-darurat-keluar-cepat');
await d.context().close();
await b.close();
console.log(shots.join('\n'));
