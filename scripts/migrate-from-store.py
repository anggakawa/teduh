#!/usr/bin/env python3
"""Copy data from the local-maps-archive (places/*.json + hotlines.json + SCHEMA.md) into this repo.

The archive is only read. Pick exactly one mode; without one the script refuses to run.

Field sync (--fields bpjs_info,biaya_gratis): for places that already exist in the repo, copy ONLY
these archive fields into the repo record and leave every other field alone. Only the fields in
SYNCABLE are accepted (contacts, booking, sources … went through the phone-consent scrub here and
must never be re-copied from the archive). Rules:
  - keys whose name contains "internal" (leaks.is_internal_key) are stripped at any depth; a dict or
    list left empty by the stripping is dropped;
  - every cleaned value must pass, BEFORE anything is written or any diff is printed: the field JSON
    Schema, the strict phone scan (phones.in_record strict), the email scan and the key guard
    (leaks.leaked_key_paths: internal or non-plain keys). One failure aborts the whole run with
    nothing written;
  - a repo value is replaced only when it still equals what the last sync wrote (recorded as a hash
    in data/.store-sync.json, schema/store-sync.schema.json) or the repo has no value yet. A repo
    value that differs from both the last-synced and the new archive value is a hand edit: KEPT
    unless --force. A missing state file is a warning (every differing value is then KEPT); a corrupt
    one stops the run;
  - a field missing in the archive record is never removed from the repo without --force;
  - --only id1,id2 limits the run to those places; an id that is in neither the repo nor the
    archive is an error;
  - new archive places are reported, not added (a new place needs the full consent review); repo
    places with no archive record are reported as NOT IN STORE. hotlines.json and SCHEMA.md are not
    touched.
  python3 scripts/migrate-from-store.py --src /path/to/local-maps-archive --fields bpjs_info,biaya_gratis [--only id] [--data dir] [--force]

Initial import (--initial-import; the one-time import was done 2026-10-31, so this is only for
rebuilding an empty data dir): whole records are copied with only the JSON formatting normalised,
after stripping internal keys. Before anything is written, every record and hotlines.json that
would be written must pass what validate.py checks: the place / hotlines schema, the phone consent
rule (every number cited in contact_sources), no phone or email in bpjs_info / biaya_gratis, and the
key guard. An existing repo file that differs is KEPT unless --force (its contacts were scrubbed
for consent here; the message names the contact fields that would change). SCHEMA.md is only
replaced with --force too.
  python3 scripts/migrate-from-store.py --src /path/to/local-maps-archive --initial-import [--data dir] [--force]

After either mode run scripts/validate.py.
"""
import argparse, glob, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonio, leaks, phones

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNCABLE = ("bpjs_info", "biaya_gratis")      # the ONLY fields --fields may copy (R-B1)
STATE_FILE = ".store-sync.json"               # {place id: {field: sha256 of the value the last sync wrote}}
CONTACT_FIELDS = ("contacts", "contact_sources", "booking", "booking_display", "complaint_method")
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


def cleaned(v):
    c = strip_internal(v)
    return {} if c is _DROP else c


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def schema_validator(name):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    schemas = [jsonio.read(f) for f in glob.glob(os.path.join(ROOT, "schema", "*.schema.json"))]
    registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas if "$id" in s)
    return Draft202012Validator(jsonio.read(os.path.join(ROOT, "schema", name)), registry=registry)


def schema_errors(validator, value):
    return [f"schema: {'/'.join(map(str, e.path)) or '(root)'}: {e.message[:160]}" for e in validator.iter_errors(value)]


def field_problems(field, value, validator):
    """Everything that must stop a sync of this cleaned value (checked before any write)."""
    probs = schema_errors(validator, value)
    probs += [f"phone {n} in {', '.join(ps[:3])}" for n, ps in sorted(phones.in_record({field: value}, strict=True).items())]
    probs += [f"email {e} in {pth}" for pth, e in leaks.emails(value, field)]
    probs += [f"key {pth} (internal or not a plain ASCII identifier)" for pth in leaks.leaked_key_paths(value, field)]
    return probs


def changed_subkeys(old, new):
    """The sub-keys whose value differs ([""] = compare the whole value when it is not a dict)."""
    if not (isinstance(old, dict) or old is None) or not isinstance(new, dict):
        return [""]
    old = old or {}
    return [k for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]


def short(v):
    return json.dumps(v, ensure_ascii=False)[:160]


# ---------------------------------------------------------------- field sync: state
def load_state(path):
    """The last-sync hashes. Missing: warn (differing values are then KEPT). Corrupt: stop, clearly."""
    if not os.path.exists(path):
        print(f"WARNING: no sync state ({path}): differing values are treated as hand edits and KEPT", file=sys.stderr)
        return {}
    try:
        state = jsonio.read(path)
    except (OSError, ValueError) as e:
        sys.exit(f"{path}: corrupt sync state ({e.__class__.__name__}: {e}); restore it from git or delete it "
                 "(then differing values are KEPT as hand edits); nothing written")
    errs = schema_errors(schema_validator("store-sync.schema.json"), state)
    if errs:
        sys.exit(f"{path}: invalid sync state ({'; '.join(errs[:3])}); restore it from git or delete it; nothing written")
    return state


# ---------------------------------------------------------------- field sync: plan / check / apply
def plan_place(stem, rec, cur, fields, last, force):
    """What a sync would do to one repo place. Nothing is printed or written here.
    Returns {new, state, changes, notes, values, stripped}:
      new      the record to write (== cur when nothing changes)
      state    {field: digest or None (drop)} updates for .store-sync.json
      changes  [(label, field, old, new)] for the UPDATE/OVERWRITE/REMOVED report
      notes    KEPT lines (no field values, safe to print before the checks)
      values   [(field, cleaned archive value)] that check() must pass"""
    p = {"new": dict(cur), "state": {}, "changes": [], "notes": [], "values": [], "stripped": 0}
    for k in fields:
        if k not in rec:
            if k in cur:
                if force:
                    p["new"].pop(k); p["state"][k] = None
                    p["changes"].append(("REMOVED (--force; not in the archive)", k, cur[k], None))
                else:
                    p["notes"].append(f"KEPT (archive has no {k}; use --force to remove): {stem}.{k}")
            continue
        clean = cleaned(rec[k])
        if clean != rec[k]:
            p["stripped"] += 1
        p["values"].append((k, clean))
        if cur.get(k) == clean:
            p["state"][k] = digest(clean)
            continue
        hand_edit = k in cur and digest(cur[k]) != last.get(k)
        if hand_edit and not force:
            p["notes"].append(f"KEPT (differs from the last sync and from the archive, use --force): {stem}.{k}")
            continue
        p["changes"].append(("OVERWRITE (--force)" if hand_edit else "UPDATE", k, cur.get(k), clean))
        p["new"][k] = clean
        p["state"][k] = digest(clean)
    return p


def check(plans, validators):
    """Every problem in every cleaned archive value of the run (empty list: safe to apply)."""
    return [f"{stem}.{k}: {msg}" for stem, p in plans for k, v in p["values"] for msg in field_problems(k, v, validators[k])]


def apply(plans, out, state, state_path):
    new_state = json.loads(json.dumps(state))
    for stem, p in plans:
        for label, k, old, new in p["changes"]:
            print(f"{label} {stem}.{k}:")
            for sub in changed_subkeys(old, new):
                o = (old or {}).get(sub) if sub else old
                n = (new or {}).get(sub) if sub else new
                print(f"  {k}{'.' + sub if sub else ''}: {short(o)} -> {short(n)}")
        for k, d in p["state"].items():
            if d is None:
                new_state.get(stem, {}).pop(k, None)
            else:
                new_state.setdefault(stem, {})[k] = d
        if p["changes"]:
            jsonio.write(os.path.join(out, stem + ".json"), p["new"])
    new_state = {k: v for k, v in new_state.items() if v}
    if new_state != state:
        jsonio.write(state_path, new_state)


def parse_fields(spec):
    fields = [x.strip() for x in spec.split(",") if x.strip()]
    bad = [f for f in fields if f not in SYNCABLE]
    if bad or not fields:
        sys.exit(f"--fields: only {', '.join(SYNCABLE)} may be synced (refused: {', '.join(bad) or 'nothing given'}); "
                 "other fields went through the phone-consent review in this repo")
    return fields


def sync_fields(a, records):
    fields = parse_fields(a.fields)
    out = os.path.join(a.data, "places")
    repo_ids = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(out, "*.json"))}
    store = dict(records)
    only = {x.strip() for x in (a.only or "").split(",") if x.strip()}
    unknown = sorted(only - repo_ids - set(store))
    if unknown:
        sys.exit(f"--only: unknown place id(s) {', '.join(unknown)} (in neither the repo nor the archive); nothing written")
    validators = {f: schema_validator(f + ".schema.json") for f in fields}
    state_path = os.path.join(a.data, STATE_FILE)
    state = load_state(state_path)
    fs = {"updated": 0, "same": 0, "kept": 0, "not_in_repo": 0, "not_in_store": 0, "internal_keys_stripped": 0}

    plans = []
    for stem, rec in records:
        if only and stem not in only:
            continue
        if stem not in repo_ids:
            fs["not_in_repo"] += 1; print(f"SKIPPED (new place, needs the full consent review): {stem}"); continue
        p = plan_place(stem, rec, jsonio.read(os.path.join(out, stem + ".json")), fields, state.get(stem, {}), a.force)
        for m in p["notes"]:
            print(m)
        fs["kept"] += len(p["notes"]); fs["internal_keys_stripped"] += p["stripped"]
        fs["updated" if p["changes"] else "same"] += 1
        plans.append((stem, p))
    for stem in sorted(repo_ids - set(store)):
        if not only or stem in only:
            fs["not_in_store"] += 1; print(f"NOT IN STORE: {stem}")

    problems = check(plans, validators)
    if problems:
        for m in problems:
            print(f"REFUSED {m}", file=sys.stderr)
        sys.exit(f"field sync aborted: {len(problems)} problem(s) in the cleaned archive values; nothing written")
    apply(plans, out, state, state_path)
    print(f"synced fields {fields}:", fs)


# ---------------------------------------------------------------- initial import
def initial_import(a, records):
    import validate   # the same rules CI runs, applied before anything is written
    out = os.path.join(a.data, "places")
    pv, hv = schema_validator("place.schema.json"), schema_validator("hotlines.schema.json")
    ids = {stem for stem, _ in records} | {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(out, "*.json"))}
    stats = {"new": 0, "same": 0, "kept": 0, "overwritten": 0, "internal_keys_stripped": 0}
    writes, problems = [], []

    def plan(dst, obj, label):
        """None when the file stays as it is; otherwise the text to write."""
        text = jsonio.dumps(obj)
        if os.path.exists(dst):
            cur_text = open(dst, encoding="utf-8").read()
            if cur_text == text:
                stats["same"] += 1; return None
            if not a.force:
                cur = json.loads(cur_text)
                touched = [k for k in CONTACT_FIELDS if isinstance(cur, dict) and isinstance(obj, dict) and cur.get(k) != obj.get(k)]
                why = f"would overwrite scrubbed contacts ({', '.join(touched)}) and other reviewed edits" if touched else "differs"
                stats["kept"] += 1; print(f"KEPT ({why}; use --force): {label}"); return None
            stats["overwritten"] += 1
        else:
            stats["new"] += 1
        return text

    for stem, rec in records:
        clean = cleaned(rec)
        if clean != rec:
            stats["internal_keys_stripped"] += 1
        dst = os.path.join(out, stem + ".json")
        text = plan(dst, clean, f"places/{stem}.json")
        if text is None:
            continue
        problems += [f"places/{stem}.json: {m}" for m in schema_errors(pv, clean) + validate.check_place(clean, dst, ids)]
        writes.append((dst, text))

    hot = cleaned(jsonio.read(os.path.join(a.src, "hotlines.json")))
    hp = os.path.join(a.data, "hotlines.json")
    text = plan(hp, hot, "hotlines.json")
    if text is not None:
        problems += [f"hotlines.json: {m}" for m in schema_errors(hv, hot) + validate.internal_key_errors(hot)]
        problems += [f"hotlines.json[{i}]: {m}" for i, h in enumerate(hot if isinstance(hot, list) else [])
                     if isinstance(h, dict) for m in validate.check_phones(h)]
        writes.append((hp, text))

    schema_text = open(os.path.join(a.src, "SCHEMA.md"), encoding="utf-8").read()
    sp = os.path.join(a.data, "SCHEMA.md")
    if not os.path.exists(sp) or open(sp, encoding="utf-8").read() != schema_text:
        if os.path.exists(sp) and not a.force:
            print("KEPT (differs; use --force): SCHEMA.md")
        else:
            writes.append((sp, schema_text))

    if problems:
        for m in problems:
            print(f"REFUSED {m}", file=sys.stderr)
        sys.exit(f"initial import aborted: {len(problems)} problem(s); nothing written")
    os.makedirs(out, exist_ok=True)
    for dst, text in writes:
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print("imported:", stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fields", help="fields to sync into existing repo places (only: " + ",".join(SYNCABLE) + ")")
    mode.add_argument("--initial-import", action="store_true", help="one-time full import (done 2026-10-31), with every validate.py check before writing")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--only", help="with --fields: comma-separated place ids to limit the sync to")
    ap.add_argument("--data", default=os.path.join(ROOT, "data"), help="repo data dir (default: data/)")
    a = ap.parse_args()
    if a.only and not a.fields:
        ap.error("--only works with --fields")

    records = []
    for f in sorted(glob.glob(os.path.join(a.src, "places", "*.json"))):
        rec = jsonio.read(f)
        stem = os.path.splitext(os.path.basename(f))[0]
        if rec.get("id") != stem:
            sys.exit(f"{f}: id {rec.get('id')!r} != filename; fix the archive first")
        records.append((stem, rec))

    if a.fields:
        sync_fields(a, records)
    else:
        initial_import(a, records)


if __name__ == "__main__":
    main()
