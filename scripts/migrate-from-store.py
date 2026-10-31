#!/usr/bin/env python3
"""One-time migration: copy the local-maps-archive (places/*.json + hotlines.json + SCHEMA.md)
into this repo, one file per place, so the repo becomes the source of truth.

The archive is only read. Records are copied verbatim (no field is changed); only the JSON
formatting is normalised (2-space indent, UTF-8, trailing newline) so later diffs stay small.
Re-running is safe: unchanged files are left alone, and existing repo files that differ are
NOT overwritten unless --force (the repo may already hold reviewed edits).

Usage: python3 scripts/migrate-from-store.py --src /path/to/local-maps-archive [--force]
"""
import argparse, glob, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    out = os.path.join(ROOT, "data", "places")
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

    for f in sorted(glob.glob(os.path.join(a.src, "places", "*.json"))):
        rec = jsonio.read(f)
        stem = os.path.splitext(os.path.basename(f))[0]
        if rec.get("id") != stem:
            sys.exit(f"{f}: id {rec.get('id')!r} != filename; fix the archive first")
        put(os.path.join(out, stem + ".json"), rec)
    put(os.path.join(ROOT, "data", "hotlines.json"), jsonio.read(os.path.join(a.src, "hotlines.json")))
    shutil.copyfile(os.path.join(a.src, "SCHEMA.md"), os.path.join(ROOT, "data", "SCHEMA.md"))
    print("migrated:", stats)


if __name__ == "__main__":
    main()
