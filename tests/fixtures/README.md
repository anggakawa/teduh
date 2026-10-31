Frozen copy of `data/` as migrated on 2026-10-31 (33 places + hotlines).

`scripts/check.mjs` asserts things that depend on this exact data (Ego Psychology sorts first,
the "Kesehatan mental + Terverifikasi + Buka hari ini" filter returns 3, TraitCare's hours…).
CI therefore builds the UI check against this fixture, not against live `data/`, so a new
contributor place cannot break the UI test. Update the fixture only together with check.mjs.
