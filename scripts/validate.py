#!/usr/bin/env python3
"""Validate repo data: JSON Schema (schema/*.schema.json, from SCHEMA.md v3) + hard rules.

Hard rules (errors):
  - id == file name, ids unique, facility_id points to an existing place
  - approx_coords never become a pin: lat/lng must not equal approx_coords
  - a pin must be inside the Banjarbaru area box (same box as build-data.py)
  - at least one http(s) source; no markup or javascript: in any text field
  - phone consent policy: every phone/WhatsApp number in a record (any field) is listed in
    contact_sources with a public http(s) URL where the owner publishes it, and every
    contact_sources entry matches a number in the record (also for hotlines.json)
Prints GitHub annotations when run in Actions. Exit 1 on any error.

Usage: python3 scripts/validate.py [--data data] [files...]   (files default to all places)
"""
import argparse, glob, json, os, re, sys
from jsonschema import Draft202012Validator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phones

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOUNDS = {"lat": (-3.8, -3.1), "lng": (114.4, 115.2)}   # keep in sync with scripts/build-data.py
BAD_TEXT = re.compile(r"<\s*/?\s*(script|iframe|img|svg|a|style|object|embed)\b|javascript:|data:text/html|on\w+\s*=", re.I)
IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def strings(v, path=""):
    if isinstance(v, str):
        yield path, v
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from strings(x, f"{path}.{k}" if path else k)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from strings(x, f"{path}[{i}]")


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def check_place(rec, fname, ids):
    errs = []
    stem = os.path.splitext(os.path.basename(fname))[0]
    if rec.get("id") != stem:
        errs.append(f"id '{rec.get('id')}' must equal the file name '{stem}'")
    lat, lng, ap = rec.get("lat"), rec.get("lng"), rec.get("approx_coords")
    if is_num(lat) and is_num(lng):
        if isinstance(ap, dict) and is_num(ap.get("lat")) and is_num(ap.get("lng")) \
                and abs(ap["lat"] - lat) < 1e-6 and abs(ap["lng"] - lng) < 1e-6:
            errs.append("lat/lng equals approx_coords: approx_coords must NEVER become a pin (set lat/lng to null)")
        if not (BOUNDS["lat"][0] <= lat <= BOUNDS["lat"][1] and BOUNDS["lng"][0] <= lng <= BOUNDS["lng"][1]):
            errs.append(f"lat/lng {lat},{lng} outside the Banjarbaru area box")
    elif (lat is None) != (lng is None):
        errs.append("lat and lng must both be numbers or both be null")
    fid = rec.get("facility_id")
    if fid and fid not in ids:
        errs.append(f"facility_id '{fid}' is not an existing place id")
    # Older archive records cite a few offline sources by title (not URL); that stays allowed,
    # but every record needs at least one checkable http(s) source. New sources added in a PR
    # must be URLs (scripts/guard_pr.py).
    urls = [s.get("url", "") for s in rec.get("sources") or [] if isinstance(s, dict)]
    if not any(re.match(r"^https?://", u) for u in urls):
        errs.append("needs at least one source with an http(s) URL")
    for path, s in strings(rec):
        if BAD_TEXT.search(s):
            errs.append(f"{path}: markup/script-like text is not allowed")
    errs += check_phones(rec)
    return errs


def check_phones(rec):
    """Consent policy: a number is published only with a public source where the owner publishes it."""
    errs = []
    found, cited = phones.in_record(rec), phones.cited(rec)
    for n, paths in sorted(found.items()):
        if n not in cited:
            errs.append(f"phone {n} ({', '.join(paths[:3])}) has no contact_sources entry with an http(s) URL "
                        "where the institution/owner publishes it (consent policy, CONTRIBUTING.md)")
    for c in rec.get("contact_sources") or []:
        if isinstance(c, dict) and phones.normalize(c.get("number") or "") not in found:
            errs.append(f"contact_sources number {c.get('number')!r} does not appear in the record (remove the entry)")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("files", nargs="*")
    a = ap.parse_args()
    place_schema = json.load(open(os.path.join(ROOT, "schema", "place.schema.json"), encoding="utf-8"))
    hot_schema = json.load(open(os.path.join(ROOT, "schema", "hotlines.schema.json"), encoding="utf-8"))
    pv, hv = Draft202012Validator(place_schema), Draft202012Validator(hot_schema)

    all_files = sorted(glob.glob(os.path.join(a.data, "places", "*.json")))
    ids = {os.path.splitext(os.path.basename(f))[0] for f in all_files}
    files = [os.path.abspath(f) for f in a.files] if a.files else all_files
    problems = 0

    def report(fname, msg):
        nonlocal problems
        problems += 1
        rel = os.path.relpath(fname, ROOT)
        print(f"::error file={rel}::{msg}" if IN_ACTIONS else f"ERROR {rel}: {msg}")

    seen = {}
    for f in files:
        if not f.endswith(".json") or os.sep + "places" + os.sep not in f:
            continue
        if not os.path.exists(f):
            continue   # deleted in this change
        try:
            rec = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            report(f, f"invalid JSON: {e}"); continue
        for e in sorted(pv.iter_errors(rec), key=lambda e: list(e.path)):
            report(f, f"schema: {'/'.join(map(str, e.path)) or '(root)'}: {e.message[:200]}")
        if isinstance(rec, dict):
            for m in check_place(rec, f, ids):
                report(f, m)
            if rec.get("id") in seen:
                report(f, f"duplicate id (also in {seen[rec['id']]})")
            seen[rec.get("id")] = os.path.basename(f)

    hp = os.path.join(a.data, "hotlines.json")
    if os.path.exists(hp):
        hot = json.load(open(hp, encoding="utf-8"))
        for e in hv.iter_errors(hot):
            report(hp, f"schema: {'/'.join(map(str, e.path))}: {e.message[:200]}")
        for i, h in enumerate(hot if isinstance(hot, list) else []):
            if isinstance(h, dict):
                for m in check_phones(h):
                    report(hp, f"[{i}] {m}")

    n = len([f for f in files if f.endswith(".json")])
    print(f"validated {n} place file(s) + hotlines: {problems} error(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
