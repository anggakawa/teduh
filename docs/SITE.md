# Teduh — Peta layanan Banjarbaru (v2)

> Catatan repo: dokumen ini berasal dari folder v2. Di repo ini situs ada di `site/`, data di `data/`, dan skrip di `scripts/` (`python3 scripts/build-data.py`, `SITE_DIR=site node scripts/check.mjs`). Lihat README.md di akar repo.

A calm local map of services that other maps lack: mental health, child development/ABK, legal aid and protection, and psychological testing. The design follows `../design/design.md` (Artist spec). It is static HTML with no build tooling. Leaflet 1.9.4 and Leaflet.markercluster 1.5.3 are vendored in `vendor/`, and Plus Jakarta Sans (OFL) is self-hosted in `assets/fonts/`, so the page works over file:// apart from the map tiles.

## Run

```bash
cd /workspace/peta/v2
python3 build-data.py            # (re)build data/ from the archive
python3 -m http.server 8000      # then open http://localhost:8000/
```

You can also double-click `index.html` (file://). `fetch()` fails over file://, so the page falls back to loading `data/data.js` (`window.PETA_DATA`). Map tiles still need an internet connection.

Deep link: `index.html#<place-id>` opens a place's detail, for example `#uptd-ppa-kota-banjarbaru`. For privacy the app only reads the hash. It never writes the URL or localStorage. **Keluar cepat** (or Esc pressed 3×) calls `location.replace()` to a weather search.

## Rebuild data

`build-data.py` uses only the Python standard library. It reads the archive read-only:

- `…/local-maps-archive/places/*.json`: one file per place.
- `…/local-maps-archive/hotlines.json`

It writes these files:

| File | Purpose |
|---|---|
| `data/places.json` | `{meta, places[]}`. Each place keeps its original fields and adds a derived `_d` block. |
| `data/hotlines.json` | `{meta, hotlines[]}` |
| `data/data.js` | The same data as a script, used as the file:// fallback |
| `data/build-report.json` | Counts, skipped or invalid files, warnings, and schema drift |

Use `--src /other/archive` to point at a different copy of the archive. The script logs skipped files (invalid JSON or a missing `id`/`name`/`category`/`status`) and prints warnings.

Validation follows the archive's `SCHEMA.md` (v2) field contract:

- `status` must be `active` or `needs-check`.
- The top-level category must be one of the 4 slugs.
- `short` and `checked` are expected. A missing one produces a warning, and the script falls back to a shortened `name` or to `verified_at`.
- `checked` must equal `verified_at`, and dates must be YYYY-MM-DD.
- List fields must be lists.
- A `needs-check` place should have `open_issues`.
- Any field that is not in SCHEMA.md is reported as information only.

The derived `_d` block contains:

- `group`: the top-level category slug (`kesehatan-mental` | `tumbuh-kembang-anak` | `layanan-pendampingan` | `psikologi`). It is also the marker file prefix and the `--cat-*` token.
- `short`, `checked`: the display name and the check date. The UI shows the date as "dicek Okt 2026".
- `hours`: a best-effort `{label, week[7], igd24}` parsed from the free-text hours. When parsing fails the UI shows the hours as written.
- `tags`: `Gratis` / `BPJS` / `Berbayar`, set only when the data says so.
- `pin`: `{lat,lng}` or `null`
- `needs_check`
- `regional`: a tag containing "regional" (SCHEMA v2), or a city other than Banjarbaru
- `phones[]`: each with `tel`, `wa_url`, and the flags `wa` (the source confirms WhatsApp) and `conflict`
- `links[]`: websites, Instagram, and `mailto:` links
- `maps_url`, `dir_url`
- `q`: the search text

## Hard rules (enforced in two places, checked by a test)

1. **A place gets a pin only when it has a real numeric `lat`/`lng`.** `approx_coords` are OSM street midpoints and are never used for a pin. `build-data.py` also refuses a pin when `lat/lng` equals `approx_coords`, and `js/data.js` re-checks this rule in the browser. Places without a pin appear in the list under **"Lokasi belum terverifikasi"** with a Google Maps search link that uses the name and city, not the approximate coordinates.
2. **A `needs-check` place stays visibly marked**, following the Artist's spec. No orange and no dashed "!" style is used anywhere.
   - **Pin:** the hollow `…--belum-dicek.svg` marker (white fill, outlined in the category colour).
   - **List and detail:** a grey `Belum dicek ⓘ` chip. The detail also shows "Info dari sumber publik, mohon konfirmasi via telepon." and the `open_issues`.
   - **Cluster:** the share of the ring for unchecked places is drawn in grey, and a small hollow badge shows how many unchecked places the cluster holds.
   - **Legend:** both pin states for each category, plus the chip.

## Structure

```
index.html
css/fonts.css      ← @font-face for the self-hosted Plus Jakarta Sans (variable woff2, latin + latin-ext)
css/tokens.css     ← SINGLE SWAP POINT: palette, category colours (--cat-<slug>[-deep|-tint]), radii, shadows, type, sizes
css/app.css        ← layout and components; uses only tokens
assets/markers/    ← 8 Teduh pin SVGs (copied from design/markers)
assets/brand/      ← logo, mark, app icon (copied from design/)
assets/fonts/      ← Plus Jakarta Sans woff2 + OFL.txt
js/config.js       ← categories, icons, months/days, copy, tiles, quick-exit URL, reportUrl
js/util.js         ← escaping, renderers, dicek date, today's hours (Asia/Makassar)
js/data.js         ← fetch + file:// fallback + pin-rule guard
js/map.js          ← Leaflet, SVG pins (L.icon, anchor [18,44]), clusters, legend, locate
js/sheet.js        ← mobile bottom sheet: peek / half / full, drag + fling
js/ui.js           ← chips, cards, detail, emergency sheet
js/app.js          ← state, filtering, sort, selection, quick exit
build-data.py      ← data build and SCHEMA v2 validation
scripts/check.mjs  ← headless browser checks and screenshots
vendor/            ← leaflet 1.9.4, leaflet.markercluster 1.5.3 (only MarkerCluster.css is used; clusters are styled by Teduh)
```

## Swapping the visual style

Edit or replace `css/tokens.css` only. `app.css` reads every colour, font, radius, shadow and size from these variables. Category colours are `--cat-<slug>`, `--cat-<slug>-deep` and `--cat-<slug>-tint`. The pins are image files, so a palette change also needs new `assets/markers/*.svg` (from `design/src`). Category names and icons are in `js/config.js` (`groups`, `icons`). The tile look is the `--tiles-filter` token.

## Using a CDN instead of vendor/ (SRI computed from the vendored files)

```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH" crossorigin=""></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" integrity="sha384-pmjIAcz2bAn0xukfxADbZIb3t8oRT9Sv0rvO+BR5Csr6Dhqq+nZs59P0pPKQJkEV" crossorigin="">
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js" integrity="sha384-eXVCORTRlv4FUUgS/xmOyr66XBVraen8ATNLMESp92FKXLAMiKkerixTiBvXriZr" crossorigin=""></script>
```

## Checks

```bash
python3 -m http.server 8765 &      # from this folder
node scripts/check.mjs             # needs playwright-core (PW_DIR, default /tmp/pw) + Chrome (CHROME)
node scripts/screens.mjs           # review screenshots → screenshots/ (390×844 and 1440×900)
```

Add `?now=2026-10-31T13:56` to the URL to freeze "now" for the hours copy, as in the mockups. It is read-only; nothing is stored.

`check.mjs` covers the following:

- Static checks: `css/tokens.css` is the design drop-in, no old values remain, and there is no raw hex outside the tokens.
- States: loading skeleton, data error and tile error.
- Desktop chrome (d01–d03): the 380px panel, header, Keluar cepat with its Esc tooltip, collapsed legend, zoom and attribution.
- List: sort "Buka dulu" (d01 order); no category chip on cards; grey "Belum dicek" chip; "Terverifikasi · dicek Okt 2026"; time-aware hours copy; card aria-labels.
- Unpinned places are listed under "Tanpa titik di peta" with a pin-off line (SPEC §11.2). approx_coords never become pins.
- No orange, dashed or "!" styling. Clusters show hollow grey counts. List and marker hover are linked.
- Details: verified (RSD, TraitCare) and unverified (Sagraha: notice, phone chooser). The selected pin is 1.3× and drawn above the clusters.
- Filters and search: m04 filter results, the m07 empty state with "tampilkan yang belum dicek", search highlights, and the d03 empty state with broader-term chips.
- Darurat modal: order, focus trap, Esc returning focus, and Keluar cepat drawn above the modal.
- Nothing is written to storage or history. Keluar cepat (one tap, or Esc ×3) replaces the history entry.
- Mobile: peek/half/full positions; grab cycle; drag; search mode; recent searches kept in memory only; detail at half with the pin visible; ≥44px hit areas.
- prefers-reduced-motion and the file:// fallback.
