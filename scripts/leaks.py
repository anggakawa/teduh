"""Private-data detectors shared by validate.py, migrate-from-store.py and the tests.

- Internal keys: a key is private when "internal" appears in it after Unicode folding
  (NFKC, casefold, combining marks removed, dotless ı -> i). So catatan_internal, NOTE_INTERNAL,
  catatan-internal, "catatan internal", catatanInternal and catatan_ınternal are all caught.
- Key shape (R2-M2): every data key must be a plain ASCII identifier, KEY_RE = ^[A-Za-z0-9_-]+$.
  That closes what folding cannot: zero-width / soft-hyphen / word-joiner / BOM characters inside a
  key ("catatan_inter\u200bnal"), Cyrillic or small-caps look-alikes, spaces. The hyphen is allowed
  because existing data uses it (field_confidence.brand_link_Al-Birru) and the build output keys
  groups by slug (by_group["kesehatan-mental"]). With ASCII-only keys the "internal" check is exact.
- Email addresses (SCHEMA.md v4/v5: bpjs_info / biaya_gratis carry no contacts), including the
  common obfuscations "nama [at] gmail [dot] com" / "nama (at) gmail.com" / "nama @ gmail . com".
build-data.py (repo and v2) imports this module; it is not a second copy of the rules.
"""
import re, unicodedata

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_AT = r"(?:\s*@\s*|\s*[\[({<]\s*(?:at|et)\s*[\])}>]\s*)"
_DOT = r"(?:\s*\.\s*|\s*[\[({<]\s*(?:dot|titik)\s*[\])}>]\s*)"
# Obfuscated forms only count with a real-looking last label, so "IG @dp3akb.kalsel" (an Instagram
# handle) is not an email. Known limit: other spellings ("nama at gmail titik com") are not caught.
_TLD = r"(?:com|net|org|id|co|go|ac|sch|or|my|web|biz|info|io|me|edu|gov|mil)"
OBFUSCATED_EMAIL_RE = re.compile(rf"[A-Za-z0-9._%+\-]+{_AT}[A-Za-z0-9\-]+(?:{_DOT}[A-Za-z0-9\-]+)*{_DOT}{_TLD}\b", re.I)
KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def is_plain_key(k):
    """A key is acceptable only as a plain ASCII identifier (letters, digits, _ and -)."""
    return isinstance(k, str) and KEY_RE.fullmatch(k) is not None


def bad_keys(v, path=""):
    """JSON paths (key shown with escapes) of every dict key that is not is_plain_key, at any depth."""
    if isinstance(v, dict):
        for k, x in v.items():
            p = f"{path}.{k}" if path else str(k)
            if not is_plain_key(k):
                yield f"{path}.{ascii(str(k))}" if path else ascii(str(k))
            yield from bad_keys(x, p)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from bad_keys(x, f"{path}[{i}]")


def leaked_key_paths(v, path=""):
    """Everything a key guard must refuse, one path per key: internal keys and non-plain keys
    (a non-plain key is shown escaped, e.g. 'catatan_inter\\u200bnal')."""
    out = []
    def walk(x, p):
        if isinstance(x, dict):
            for k, y in x.items():
                kp = f"{p}.{k}" if p else str(k)
                if not is_plain_key(k):
                    out.append(f"{p}.{ascii(str(k))}" if p else ascii(str(k)))
                elif is_internal_key(k):
                    out.append(kp)
                walk(y, kp)
        elif isinstance(x, list):
            for i, y in enumerate(x):
                walk(y, f"{p}[{i}]")
    walk(v, path)
    return out


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
            t = unicodedata.normalize("NFKC", x)
            found = [m.group(0) for m in EMAIL_RE.finditer(t)]
            found += [o for o in (m.group(0) for m in OBFUSCATED_EMAIL_RE.finditer(t)) if not any(f in o for f in found)]
            out.extend((p, e) for e in found)
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
