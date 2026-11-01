#!/usr/bin/env python3
"""Copy data from the local-maps-archive (places/*.json + hotlines.json + SCHEMA.md) into this repo.

Two modes. The archive is only read in both.

Full migration (one-time, 2026-10-31): records are copied verbatim (no field is changed); only the JSON
formatting is normalised (2-space indent, UTF-8, trailing newline) so later diffs stay small.
Re-running is safe: unchanged files are left alone, and existing repo files that differ are
NOT overwritten unless --force (the repo may already hold reviewed edits).
  python3 scripts/migrate-from-store.py --src /path/to/local-maps-archive [--force]

Field sync (--fields bpjs_info,biaya_gratis): for places that already exist in the repo, copy ONLY
these archive fields into the repo record and leave every other field alone. Only the fields in
SYNCABLE are accepted (contacts, booking, sources … went through the phone-consent scrub here and
must never be re-copied from the archive). Rules:
  - keys whose name contains "internal" (leaks.is_internal_key) are stripped at any depth; a dict or
    list left empty by the stripping is dropped;
  - every cleaned value must pass, BEFORE anything is written: the field JSON Schema, the strict
    phone scan (phones.in_record strict), the internal-key check and the email scan. One failure
    aborts the whole run with nothing written;
  - a repo value is replaced only when it still equals what the last sync wrote (recorded as a hash
    in data/.store-sync.json) or the repo has no value yet. A repo value that differs from both the
    last-synced and the new archive value is a hand edit: KEPT unless --force;
  - a field missing in the archive record is never removed from the repo without --force;
  - --only id1,id2 limits the run to those places;
  - new archive places are reported, not added (a new place needs the full consent review); repo
    places with no archive record are reported as NOT IN STORE. hotlines.json and SCHEMA.md are not
    touched.
  python3 scripts/migrate-from-store.py --src /path/to/local-maps-archive --fields bpjs_info,biaya_gratis [--only id] [--data dir] [--force]

After either mode run scripts/validate.py: the consent rule still applies to every phone number.
"""
import argparse, glob, hashlib, json, os, shutil, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonio, leaks, phones

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNCABLE = ("bpjs_info", "biaya_gratis")      # the ONLY fields --fields may copy (R-B1)
STATE_FILE = ".store-sync.json"               # {place id: {field: sha256 of the value the last sync wrote}}
_DROP = object()


def strip_internal(v):
    """Drop every dict key that leaks.is_internal_key, at any depth. A dict/list that only held
    internal notes (so is empty after stripping) is dropped too; containers empty in the archive stay."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if leaks.is_internal_key(k):
                continue
            y = strip_internal(x)
            if y is not _DROP:
                out[k] = y
        return _DROP if v and not out else out
    if isinstance(v, list):
        out = [y for y in (strip_internal(x) for x in v) if y is not _DROP]
        return _DROP if v and not out else out
    return v


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def field_problems(field, value, validator):
    """Everything that must stop a sync of this cleaned value (checked before any write)."""
    probs = [f"schema: {'/'.join(map(str, e.path)) or '(root)'}: {e.message[:160]}" for e in validator.iter_errors(value)]
    probs += [f"phone {n} in {', '.join(ps[:3])}" for n, ps in sorted(phones.in_record({field: value}, strict=True).items())]
    probs += [f"email {e} in {pth}" for pth, e in leaks.emails(value, field)]
    probs += [f"internal key {pth}" for pth in leaks.internal_keys(value, field)]
    return probs


def sync_fields(a, records):
    fields = [x.strip() for x in a.fields.split(",") if x.strip()]
    bad = [f for f in fields if f not in SYNCABLE]
    if bad or not fields:
        sys.exit(f"--fields: only {', '.join(SYNCABLE)} may be synced (refused: {', '.join(bad) or 'nothing given'}); "
                 "other fields went through the phone-consent review in this repo")
    only = {x.strip() for x in (a.only or "").split(",") if x.strip()}
    from jsonschema import Draft202012Validator
    validators = {f: Draft202012Validator(jsonio.read(os.path.join(ROOT, "schema", f + ".schema.json"))) for f in fields}

    out = os.path.join(a.data, "places")
    state_path = os.path.join(a.data, STATE_FILE)
    state = jsonio.read(state_path) if os.path.exists(state_path) else {}
    new_state = json.loads(json.dumps(state))
    store_ids = {stem for stem, _ in records}
    fs = {"updated": 0, "same": 0, "kept": 0, "not_in_repo": 0, "not_in_store": 0, "internal_keys_stripped": 0}
    writes, problems = [], []

    for stem, rec in records:
        if only and stem not in only:
            continue
        dst = os.path.join(out, stem + ".json")
        if not os.path.exists(dst):
            fs["not_in_repo"] += 1; print(f"SKIPPED (new place, needs the full consent review): {stem}"); continue
        cur = jsonio.read(dst)
        new = dict(cur)
        for k in fields:
            last = state.get(stem, {}).get(k)
            if k not in rec:
                if k in cur:
                    if a.force:
                        new.pop(k); new_state.get(stem, {}).pop(k, None)
                        print(f"REMOVED (--force; not in the archive): {stem}.{k}")
                    else:
                        fs["kept"] += 1; print(f"KEPT (archive has no {k}; use --force to remove): {stem}.{k}")
                continue
            clean = strip_internal(rec[k])
            if clean is _DROP:
                clean = {}
            if clean != rec[k]:
                fs["internal_keys_stripped"] += 1
            for msg in field_problems(k, clean, validators[k]):
                problems.append(f"{stem}.{k}: {msg}")
            if cur.get(k) == clean:
                new_state.setdefault(stem, {})[k] = digest(clean)
                continue
            hand_edit = k in cur and digest(cur[k]) != last
            if hand_edit and not a.force:
                fs["kept"] += 1
                print(f"KEPT (differs from the last sync and from the archive, use --force): {stem}.{k}")
                continue
            print(f"{'OVERWRITE (--force)' if hand_edit else 'UPDATE'} {stem}.{k}:")
            for sub in sorted(set(cur.get(k) or {}) | set(clean) if isinstance(clean, dict) else [""]):
                old_v = (cur.get(k) or {}).get(sub) if sub else cur.get(k)
                new_v = clean.get(sub) if sub else clean
                if old_v != new_v:
                    print(f"  {k}.{sub}: {json.dumps(old_v, ensure_ascii=False)[:160]} -> {json.dumps(new_v, ensure_ascii=False)[:160]}")
            new[k] = clean
            new_state.setdefault(stem, {})[k] = digest(clean)
        if new == cur:
            fs["same"] += 1
        else:
            writes.append((dst, new)); fs["updated"] += 1

    for f in sorted(glob.glob(os.path.join(out, "*.json"))):
        stem = os.path.splitext(os.path.basename(f))[0]
        if stem not in store_ids and (not only or stem in only):
            fs["not_in_store"] += 1; print(f"NOT IN STORE: {stem}")

    if problems:
        for m in problems:
            print(f"REFUSED {m}", file=sys.stderr)
        sys.exit(f"field sync aborted: {len(problems)} problem(s) in the cleaned archive values; nothing written")
    for dst, obj in writes:
        jsonio.write(dst, obj)
    if new_state != state:
        jsonio.write(state_path, new_state)
    print(f"synced fields {fields}:", fs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fields", help="fields to sync into existing repo places (only: " + ",".join(SYNCABLE) + ")")
    ap.add_argument("--only", help="with --fields: comma-separated place ids to limit the sync to")
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
        sync_fields(a, records)
        return

    for stem, rec in records:
        put(os.path.join(out, stem + ".json"), rec)
    put(os.path.join(a.data, "hotlines.json"), jsonio.read(os.path.join(a.src, "hotlines.json")))
    shutil.copyfile(os.path.join(a.src, "SCHEMA.md"), os.path.join(a.data, "SCHEMA.md"))
    print("migrated:", stats)


if __name__ == "__main__":
    main()
