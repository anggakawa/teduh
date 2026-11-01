"""Find and normalise Indonesian phone numbers in free text (shared by validate, guard, issue parser).

Consent policy (CONTRIBUTING.md): a phone/WhatsApp number may be published only when the institution
or owner publishes it itself (official site, signboard, official social account, owner-managed
business profile) or the owner agreed to be listed. Every number in a place record must therefore be
listed in `contact_sources` with a public http(s) URL where the owner publishes it.
"""
import re, unicodedata

# +62 / 62 / 0 prefix, then a mobile (8x) or area code (2x-7x), then more digits with optional separators. Not preceded by a word
# character, '-', '.', ',' or '=' (so ids inside URLs, prices and dates do not match).
PHONE_RE = re.compile(r"(?<![\w\-.,=])(?:\+62[\s\-.]?\(?|62|\(?0)(?:8[1-9]|[2-7]\d)[\d\s\-.()]{5,17}\d(?![\w])")


def normalize(s):
    """'0812-0000-1111' / '+62 812 0000 1111' / 'wa.me/6281200001111' -> '6281200001111'."""
    d = re.sub(r"\D", "", s or "")
    if d.startswith("0"):
        d = "62" + d[1:]
    return d


# Strict detector for fields that must carry no contact at all (bpjs_info / biaya_gratis, SCHEMA v4/v5).
# Separators (spaces, - . / ( ) and every Unicode dash) are removed first, so "0 8 1 2 …", "62-812-…",
# "08 12 34 56 78 90" and "0812–3456–7890" collapse to one digit run; then a mobile number is
# (+)62 or 0, then 8, then 7-11 digits, not glued to other digits (so NIK, prices, years never match).
SEPARATORS = re.compile(r"[\s\-.\/()\u2010-\u2015\u2212\ufe58\ufe63]+")
CLOCK = re.compile(r"(?<!\d)\d{1,2}[.:]\d{2}(?!\d)")   # 08.00 / 8:30 are times, never part of a number
MOBILE_RUN = re.compile(r"(?<![\d+])(?:\+?62|0)8\d{7,11}(?!\d)")


def find(text):
    """All phone-like numbers in a string, normalised, in order (duplicates removed).
    The text is NFKC-normalised (fullwidth digits, ＋６２). In an http(s) URL only wa.me/ and
    api.whatsapp.com phone=… numbers count (ids in other URLs are not phone numbers)."""
    out = []
    if not isinstance(text, str):
        return out
    text = unicodedata.normalize("NFKC", text)
    if re.match(r"^\s*https?://", text, re.I):
        hits = re.findall(r"(?:wa\.me/|whatsapp\.com/send\?phone=)\+?(\d{9,15})", text, re.I)
        hits += [m.group(0) for m in PHONE_RE.finditer(re.sub(r"^\s*https?://\S*", " ", text, flags=re.I))]
    else:
        hits = [m.group(0) for m in PHONE_RE.finditer(text)]
    for h in hits:
        n = normalize(h)
        if 10 <= len(n) <= 15 and n.startswith("62") and n not in out:
            out.append(n)
    return out


def find_strict(text):
    """find() plus the separator-blind mobile-number scan, for fields that must hold no contact at
    all. Nothing is skipped: URLs (wa.me/…, tel:…) are scanned like any other text."""
    out = []
    if not isinstance(text, str):
        return out
    text = unicodedata.normalize("NFKC", text)
    hits = [m.group(0) for m in PHONE_RE.finditer(text)]
    hits += [m.group(0) for m in MOBILE_RUN.finditer(SEPARATORS.sub("", CLOCK.sub("|", text)))]
    hits += re.findall(r"(?:wa\.me/|tel:|phone=)\s*\+?([\d\s\-.]{9,20}\d)", text, re.I)
    for h in hits:
        n = normalize(h)
        if 10 <= len(n) <= 15 and n.startswith("62") and n not in out:
            out.append(n)
    return out


def in_record(rec, strict=False):
    """{normalised number: [json paths]} for every string in a place record.
    Default: URL fields and contact_sources are skipped (consent check). strict=True (bpjs_info /
    biaya_gratis): every string is scanned with find_strict, url fields included."""
    found = {}
    finder = find_strict if strict else find

    def walk(v, path):
        if isinstance(v, str):
            for n in finder(v):
                found.setdefault(n, []).append(path)
        elif isinstance(v, dict):
            for k, x in v.items():
                if not strict and k in ("url", "contact_sources"):
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
