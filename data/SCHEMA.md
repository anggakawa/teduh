# Local Maps Archive — Banjarbaru (schema v5, 2026-11-01; documents fields as actually stored)
places/<id>.json = one place. inbox/ = raw Explorer batches. hotlines.json = no-location services. Build for map: /workspace/peta/v2/build-data.py

Core (all places): id, name, short (display name), category ("<top>/<sub>", top = kesehatan-mental | tumbuh-kembang-anak | layanan-pendampingan | psikologi), subcategories[], tags[] (tag containing "regional" = outside Banjarbaru), also_in_categories[]
Location: address, kelurahan, kecamatan, city, lat, lng (null = no verified pin), coord_method/latlng_method, approx_coords (OSM street midpoint, NEVER a pin)
Contact & access: contacts {phone, whatsapp, instagram, website, email, ...} (free text; "unknown" = not found), hours (free text or {label: text}; not yet normalized), schedule[] ({poli/practitioner/day/time} free-form), services[], price_range, price_per_session, cost, bpjs, booking[], waitlist, eligibility, complaint_method, therapists
Knowledge: local_notes (local info not on other maps; often English, to be translated)
Quality: status = active | needs-check, open_issues (why needs-check), field_confidence {field: "confirmed (2+ sources)" | "single source" | "stale" | "conflict"}, validation_note, sources[{url, note, checked}], verified_at = checked (YYYY-MM-DD), history[{batch, date, what_changed}], what_changed, archived_from
Links: facility_id (service unit belonging to another place record, e.g. hospital polis)
Extra free-form evidence fields (optional, from Explorer): scope, task, schedule_note, evidence, independence_note, head (person in charge), searched (what was searched without result), activity_evidence.
Duplicate coordinates are intentional: hospital service units are separate records sharing a facility (see facility_id).

## v3 (2026-10-31): user-facing Indonesian display fields
Raw fields (name, address, kelurahan, kecamatan, city, hours, services, booking, open_issues, validation_note) stay as internal evidence and are never rewritten. The map shows the *_display / *_id fields when they exist and falls back to the raw field otherwise. Display text holds only facts already in the record; uncertainty is stated, not resolved.
- name_display: Indonesian name when the raw name carries English (7 places). Map pin title, card aria and detail header.
- address_display: one clean street line (no source notes). Key present with null = no address shown.
- kelurahan_display / kecamatan_display: clean name; null when sources conflict (the conflict goes in address_note_id). Key present = overrides the raw field.
- city_display: "Banjarbaru" or "Kabupaten Banjar" (Martapura, Gambut). Outside-city logic still uses tags/city.
- address_note_id: short Indonesian sub-line under the address (conflicts, temporary moves, unknown address).
- note_id: short Indonesian reason. Shown in the "Belum dicek" notice for needs-check places, and as "Catatan" under "Info lengkap" for active places. Translation of open_issues (+ facts from validation_note/contacts), never new facts.
- hours_normalized: [{day, open, close}] with day = senin..minggu and times "HH.MM". A day the source states as closed is {day, open: null, close: null, closed: true}. A day not listed = unknown. Only filled where the raw `hours` already states weekly hours (22 places). The raw `hours` text still provides the Poli/Kantor label and IGD 24 jam.
- hours_note_id: Indonesian note on the hours (whose hours they are, stale schedule, conflicting start time).
- services_display: Indonesian services list (replaces services in the UI when present).
- booking_display: Indonesian "Cara daftar" list (replaces booking in the UI when present). [] = nothing to show.
- search_terms: Indonesian search synonyms (e.g. psikiater/dokter jiwa, KDRT, bantuan hukum, keterlambatan bicara). Searched but not displayed except in the "matched" row. Add a term only when the record's services/tags support it (no "tunarungu"/"bahasa isyarat" yet: no place lists them).

## v3.1 (2026-10-31, repo): contact_sources (phone consent policy)
One new optional field, in places/<id>.json and in each hotlines.json entry. Nothing else changed.
- contact_sources: [{number, url, note?, checked?}]. One entry per phone/WhatsApp number in the record. `number` is written as in `contacts` (any format; matched on digits, 0… = 62…). `url` (http(s), required) is a public page where the institution or owner publishes that number itself: official website, official social account, government page, or an owner-managed business profile. `note` says what was checked, `checked` = YYYY-MM-DD.
- Rule (scripts/validate.py): every phone-like number anywhere in the record (contacts, booking, notes, source notes) must have a contact_sources entry, and every entry must still match a number in the record. Google-Maps mirrors, directories, news, theses and personal pages do not count as the owner publishing a number.
- Numbers without such a source were removed from the repo data on 2026-10-31 (history batch "privacy-audit"; contacts value starts with "unknown (removed …)"). The private archive still holds them for re-verification.

## v4 (2026-11-01): bpjs_info (BPJS Kesehatan / JKN status)
The raw `bpjs` field (free text, Explorer evidence) stays untouched. `bpjs_info` is the structured, user-facing version; the map prefers it.
bpjs_info = {
  status: "ya" | "sebagian" | "tidak" | "tidak_relevan" | "belum_diketahui",
    ya = BPJS accepted for the services in this record; sebagian = only some polis/services (e.g. poli reguler yes, poli eksekutif no);
    tidak = a source says BPJS is not accepted; tidak_relevan = not a health facility (legal aid, KUA, school, Puspaga, UPTD PPA, biro tes, BNN rehab which is free anyway);
    belum_diketahui = no source either way (never guess).
  rujukan: true | false | null   (true = needs a referral from faskes tingkat 1 / FKTP; null = unknown or not applicable),
  basis: "confirmed_online" | "inferred" | "none"   (inferred = follows from the facility type or a general BPJS rule, not stated by the place),
  catatan_display: short Indonesian, user-facing (shown in the detail's BPJS row; may mention "gratis" only when a source says so),
  catatan_internal: archive only. Never stored in this public repo (stripped by scripts/migrate-from-store.py --fields; rejected by schema/bpjs_info.schema.json and scripts/validate.py) and never shipped to the site,
  sources: [{url, note, checked}] (may be [] when the evidence is the record's existing cost/sources),
  checked: "YYYY-MM-DD"
}
Build (repo): status ya/sebagian sets `_d.bpjs.accepts` (the "Terima BPJS" filter and the BPJS chip) and the search words bpjs, jkn, kis. Re-check every 3 months together with the rest.


## v5 (2026-11-01): biaya_gratis (is the service free?)
Structured replacement for reading "gratis"/"free" out of free text (cost, bpjs_info.catatan_display). Raw `cost`/`price_*` stay untouched as evidence.
biaya_gratis = {
  status: "ya" | "bersyarat" | "tidak" | "belum_diketahui",
    ya = a source says the main service is free for everyone it serves; bersyarat = free only under a condition (e.g. tidak mampu + SKTM) or only part of the service is free (BNN: rehab free, SKHPN urine test paid);
    tidak = a source shows a price or says patients pay (umum/eksekutif; BPJS coverage is NOT "gratis" here, see bpjs_info); belum_diketahui = no source (never guess).
  syarat_display: short Indonesian, user-facing (who qualifies, what to bring, what is still paid). No phone numbers or personal data in display fields.
  basis: "confirmed_online" | "old_source" (source > 1 year old) | "inferred" | "none",
  perlu_cek_ulang: true when the source is stale or a quoted price is old,
  sources: [{url, note, checked}], checked: "YYYY-MM-DD"
}
Rule: no phone numbers in bpjs_info.catatan_display or biaya_gratis.syarat_display (contacts live in `contacts`; booking_display may still name the booking line). A phone kept for provenance goes only in the archive's bpjs_info.catatan_internal, which never enters this repo. scripts/validate.py fails on any phone number inside bpjs_info or biaya_gratis.
Build (repo): the site tag comes only from biaya_gratis.status (ya -> "Gratis", bersyarat -> "Gratis bersyarat"; tidak / belum_diketahui -> no tag); free text is never parsed for "gratis". The detail shows syarat_display for ya/bersyarat and "perlu dicek ulang" when perlu_cek_ulang is true. basis stays in the repo data as provenance and is not shipped to the site.
JSON Schema: schema/bpjs_info.schema.json, schema/biaya_gratis.schema.json (referenced from schema/place.schema.json).
Sync: python3 scripts/migrate-from-store.py --src <archive> --fields bpjs_info,biaya_gratis (copies only these fields into existing places; the phone-consent scrub of contacts/booking stays).
