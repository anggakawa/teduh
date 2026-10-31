#!/usr/bin/env python3
"""PR guard: compare place data between the PR base and head.

Fails (exit 1) when:
  - a place becomes verified (status -> "active", or a new place arrives as "active") and the PR
    author is not a code owner of that file. CODEOWNERS is read from the BASE branch, so a PR
    cannot add its own author. Teams (@org/team) are not resolved here; list maintainers by
    username, or rely on branch protection "Require review from Code Owners" for teams.
  - a place file is deleted by a non-code-owner;
  - lat/lng change without a coord_method/latlng_method naming where the pin came from;
  - lat/lng equal approx_coords (base or head): approx_coords never become a pin;
  - a source added in this PR is not an http(s) URL;
  - a phone/WhatsApp number that is new or changed in this PR has no contact_sources entry with a
    public http(s) URL where the institution/owner publishes it (phone consent policy).

Usage: python3 scripts/guard_pr.py --base <base data dir> --head <head data dir> --author <login> --codeowners <file>
"""
import argparse, fnmatch, glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phones

IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def load(d):
    out = {}
    for f in glob.glob(os.path.join(d, "places", "*.json")):
        try:
            out[os.path.basename(f)] = json.load(open(f, encoding="utf-8"))
        except Exception:
            out[os.path.basename(f)] = None   # validate.py reports invalid JSON
    return out


def owners_for(path, codeowners):
    """GitHub semantics, simplified: the LAST matching pattern wins."""
    owners = []
    if not os.path.exists(codeowners):
        return owners
    for line in open(codeowners, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pat, *who = line.split()
        p = pat.lstrip("/")
        if p.endswith("/"):
            p += "**"
        if p == "*" or fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, p.replace("**", "*")) \
                or ("/" not in p.rstrip("*") and fnmatch.fnmatch(os.path.basename(path), p)):
            owners = [w.lstrip("@").lower() for w in who]
    return owners


def same(a, b):
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 1e-6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--codeowners", required=True)
    a = ap.parse_args()
    base, head = load(a.base), load(a.head)
    author = a.author.lower()
    errors = []

    def err(fname, msg):
        errors.append(msg)
        rel = f"data/places/{fname}"
        print(f"::error file={rel}::{msg}" if IN_ACTIONS else f"ERROR {rel}: {msg}")

    def is_owner(fname):
        return author in owners_for(f"data/places/{fname}", a.codeowners)

    for fname in sorted(set(base) - set(head)):
        if not is_owner(fname):
            err(fname, f"place deleted by @{a.author}, who is not a code owner (close the place with status needs-check + note instead)")

    for fname, h in sorted(head.items()):
        if not isinstance(h, dict):
            continue
        b = base.get(fname) if isinstance(base.get(fname), dict) else None
        if h.get("status") == "active" and (b is None or b.get("status") != "active") and not is_owner(fname):
            what = "new place with status active" if b is None else f"status {b.get('status')} -> active"
            err(fname, f"{what}: only code owners may mark a place verified (author @{a.author})")
        lat, lng = h.get("lat"), h.get("lng")
        moved = b is None and lat is not None or b is not None and (not same(lat, b.get("lat")) or not same(lng, b.get("lng"))) \
            and not (lat is None and lng is None)
        if moved:
            method = h.get("coord_method") or h.get("latlng_method")
            old = (b or {}).get("coord_method") or (b or {}).get("latlng_method")
            if not method or (b is not None and method == old):
                err(fname, "lat/lng changed: set coord_method to say where this exact pin comes from")
            for src in (h, b or {}):
                ap_ = src.get("approx_coords")
                if isinstance(ap_, dict) and same(ap_.get("lat"), lat) and same(ap_.get("lng"), lng):
                    err(fname, "lat/lng equal approx_coords: approx_coords must never become a pin")
                    break
        old_urls = {s.get("url") for s in (b or {}).get("sources") or [] if isinstance(s, dict)}
        for s in h.get("sources") or []:
            u = s.get("url", "") if isinstance(s, dict) else ""
            if u not in old_urls and not re.match(r"^https?://", u):
                err(fname, f"new source must be an http(s) URL (got {u[:60]!r})")
        old_nums = set(phones.in_record(b)) if b else set()
        cited = phones.cited(h)
        for n, paths in sorted(phones.in_record(h).items()):
            if n not in old_nums and n not in cited:
                err(fname, f"new/changed phone {n} ({', '.join(paths[:2])}) must cite a public http(s) source "
                           "where the institution/owner publishes it: add it to contact_sources")

    changed = sorted(f for f in set(base) | set(head) if base.get(f) != head.get(f))
    print(f"guard: {len(changed)} place file(s) changed, author @{a.author}: {len(errors)} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
