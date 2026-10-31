"""Find and normalise Indonesian phone numbers in free text (shared by validate, guard, issue parser).

Consent policy (CONTRIBUTING.md): a phone/WhatsApp number may be published only when the institution
or owner publishes it itself (official site, signboard, official social account, owner-managed
business profile) or the owner agreed to be listed. Every number in a place record must therefore be
listed in `contact_sources` with a public http(s) URL where the owner publishes it.
"""
import re

# +62 / 62 / 0 prefix, then a mobile (8x) or area code (2x-7x), then more digits with optional separators. Not preceded by a word
# character, '-', '.', ',' or '=' (so ids inside URLs, prices and dates do not match).
PHONE_RE = re.compile(r"(?<![\w\-.,=])(?:\+62[\s\-.]?\(?|62|\(?0)(?:8[1-9]|[2-7]\d)[\d\s\-.()]{5,17}\d(?![\w])")


def normalize(s):
    """'0812-0000-1111' / '+62 812 0000 1111' / 'wa.me/6281200001111' -> '6281200001111'."""
    d = re.sub(r"\D", "", s or "")
    if d.startswith("0"):
        d = "62" + d[1:]
    return d


def find(text):
    """All phone-like numbers in a string, normalised, in order (duplicates removed)."""
    out = []
    if not isinstance(text, str) or re.match(r"^\s*https?://", text):
        return out
    for m in PHONE_RE.finditer(text):
        n = normalize(m.group(0))
        if 10 <= len(n) <= 15 and n.startswith("62") and n not in out:
            out.append(n)
    return out


def in_record(rec):
    """{normalised number: [json paths]} for every string in a place record except URL fields."""
    found = {}

    def walk(v, path):
        if isinstance(v, str):
            for n in find(v):
                found.setdefault(n, []).append(path)
        elif isinstance(v, dict):
            for k, x in v.items():
                if k in ("url", "contact_sources"):
                    continue
                walk(x, f"{path}.{k}" if path else k)
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")

    walk(rec, "")
    return found


def cited(rec):
    """{normalised number: url} from contact_sources (only http(s) URLs count)."""
    out = {}
    for c in rec.get("contact_sources") or []:
        if isinstance(c, dict) and re.match(r"^https?://", c.get("url") or ""):
            out.setdefault(normalize(c.get("number") or ""), c["url"])
    return out
