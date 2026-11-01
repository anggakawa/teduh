Frozen copy of `data/` as migrated on 2026-10-31 (33 places + hotlines), with `bpjs_info` and `biaya_gratis` synced on 2026-11-01 (SCHEMA v4/v5, `scripts/migrate-from-store.py --fields bpjs_info,biaya_gratis --data tests/fixtures/data`).

`scripts/check.mjs` asserts things that depend on this exact data (Ego Psychology sorts first,
the "Kesehatan mental + Terverifikasi + Buka hari ini" filter returns 3, TraitCare's hours…).
CI therefore builds the UI check against this fixture, not against live `data/`, so a new
contributor place cannot break the UI test. Update the fixture only together with check.mjs.

The fixture must stay identical to `data/` (places, hotlines.json, .store-sync.json): CI's data
job fails on any drift (`diff -r --exclude=SCHEMA.md data tests/fixtures/data`, also
`tests/test_pipeline.py` PrivacyGuards.test_ui_fixture_matches_data), so the UI check always runs
on the real data. A data change therefore lands in both directories in the same PR.
