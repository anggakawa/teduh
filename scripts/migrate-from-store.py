#!/usr/bin/env python3
"""Copy data from the local-maps-archive (places/*.json + hotlines.json + SCHEMA.md) into this repo.

Two modes. The archive is only read in both.

Full migration (one-time, 2026-10-31): records are copied verbatim (no field is changed); only the JSON
formatting is normalised (2-space indent, UTF-8, trailing newline) so later diffs stay small.
Re-running is safe: unchanged files are left alone, and existing repo files that differ are
NOT overwritten unless --force (the repo may already hold reviewed edits).
  python3 scripts/migrate-from-store.py --src /path/to/local-maps-archive [--force]

Field sync (--fields a,b): for places that already exist in the repo, copy ONLY the named archive
fields into the repo record and leave every other field alone. This is how new archive fields
reach the repo without undoing repo edits such as the phone-consent scrub (contacts, booking and
contact_sources stay as reviewed here). Keys whose name contains "internal" (e.g.
bpjs_info.catatan_internal) are private archive notes and are stripped, at any depth. A field
missing in the archive record is removed from the repo record. New archive places are reported,
not added (a new place needs the full consent review). hotlines.json and SCHEMA.md are not touched.
  python3 scripts/migrate-from-store.py --src /path/to/local-maps-archive --fields bpjs_info,biaya_gratis

After either mode run scripts/validate.py: the consent rule still applies to every phone number.
"""
import argparse, glob, os, re, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERNAL_KEY = re.compile(r"internal", re.I)


def strip_internal(v):
    """Drop every dict key whose name contains 'internal' (private archive notes), at any depth."""
    if isinstance(v, dict):
        return {k: strip_internal(x) for k, x in v.items() if not INTERNAL_KEY.search(k)}
    if isinstance(v, list):
        return [strip_internal(x) for x in v]
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fields", help="comma-separated archive fields to sync into existing repo places")
    ap.add_argument("--data", default=os.path.join(ROOT, "data"), help="repo data dir (default: data/)")
    a = ap.parse_args()
    out = os.path.join(a.data, "places")
    os.makedirs(out, exist_ok=True)
    stats = {"new": 0, "same": 0, "kept": 0, "overwritten": 0}

    def put(dst, obj):
        text = jsonio.dumps(obj)
        if os.path.exists(dst):
            with open(dst, encoding="utf-8") as fh:
                if fh.read() == text:
                    stats["same"] += 1; return
            if not a.force:
                stats["kept"] += 1; print(f"KEPT (differs, use --force): {os.path.relpath(dst, ROOT)}"); return
            stats["overwritten"] += 1
        else:
            stats["new"] += 1
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    records = []
    for f in sorted(glob.glob(os.path.join(a.src, "places", "*.json"))):
        rec = jsonio.read(f)
        stem = os.path.splitext(os.path.basename(f))[0]
        if rec.get("id") != stem:
            sys.exit(f"{f}: id {rec.get('id')!r} != filename; fix the archive first")
        records.append((stem, rec))

    if a.fields:
        fields = [x.strip() for x in a.fields.split(",") if x.strip()]
        fs = {"updated": 0, "same": 0, "not_in_repo": 0, "internal_keys_stripped": 0}
        for stem, rec in records:
            dst = os.path.join(out, stem + ".json")
            if not os.path.exists(dst):
                fs["not_in_repo"] += 1; print(f"SKIPPED (new place, needs the full consent review): {stem}"); continue
            cur = jsonio.read(dst)
            new = dict(cur)
            for k in fields:
                if k in rec:
                    clean = strip_internal(rec[k])
                    if clean != rec[k]:
                        fs["internal_keys_stripped"] += 1
                    new[k] = clean
                else:
                    new.pop(k, None)
            if new == cur:
                fs["same"] += 1; continue
            jsonio.write(dst, new)
            fs["updated"] += 1
        print(f"synced fields {fields}:", fs)
        return

    for stem, rec in records:
        put(os.path.join(out, stem + ".json"), rec)
    put(os.path.join(a.data, "hotlines.json"), jsonio.read(os.path.join(a.src, "hotlines.json")))
    shutil.copyfile(os.path.join(a.src, "SCHEMA.md"), os.path.join(a.data, "SCHEMA.md"))
    print("migrated:", stats)


if __name__ == "__main__":
    main()
