"""Private-data detectors shared by validate.py, migrate-from-store.py and the tests.

- Internal keys: a key is private when "internal" appears in it after Unicode folding
  (NFKC, casefold, combining marks removed, dotless ı -> i). So catatan_internal, NOTE_INTERNAL,
  catatan-internal, "catatan internal", catatanInternal and catatan_ınternal are all caught.
  build-data.py carries the same rule inline (it is also shipped standalone in v2).
- Email addresses (SCHEMA.md v4/v5: bpjs_info / biaya_gratis carry no contacts).
"""
import re, unicodedata

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")


def fold_key(k):
    s = unicodedata.normalize("NFKC", str(k)).casefold()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s.replace("\u0131", "i")


def is_internal_key(k):
    return "internal" in fold_key(k)


def internal_keys(v, path=""):
    """JSON paths of every dict key that is_internal_key, at any depth."""
    if isinstance(v, dict):
        for k, x in v.items():
            p = f"{path}.{k}" if path else str(k)
            if is_internal_key(k):
                yield p
            yield from internal_keys(x, p)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from internal_keys(x, f"{path}[{i}]")


def emails(v, path=""):
    """[(path, email)] for every email address in any string (keys included), NFKC-normalised."""
    out = []
    def walk(x, p):
        if isinstance(x, str):
            out.extend((p, m.group(0)) for m in EMAIL_RE.finditer(unicodedata.normalize("NFKC", x)))
        elif isinstance(x, dict):
            for k, y in x.items():
                kp = f"{p}.{k}" if p else str(k)
                if "@" in str(k):
                    walk(str(k), kp + "(key)")
                walk(y, kp)
        elif isinstance(x, list):
            for i, y in enumerate(x):
                walk(y, f"{p}[{i}]")
    walk(v, path)
    return out
