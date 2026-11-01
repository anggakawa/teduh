"""Find and normalise Indonesian phone numbers in free text (shared by validate, guard, issue parser).

Known false positive (accepted, documented in CONTRIBUTING.md): a bank account number that looks
like a phone ("No. rek 0812345678") is reported as a phone. In bpjs_info / biaya_gratis that is the
right outcome anyway (no account numbers there either); elsewhere cite it or leave it out.

Consent policy (CONTRIBUTING.md): a phone/WhatsApp number may be published only when the institution
or owner publishes it itself (official site, signboard, official social account, owner-managed
business profile) or the owner agreed to be listed. Every number in a place record must therefore be
listed in `contact_sources` with a public http(s) URL where the owner publishes it.
"""
import re, unicodedata

# +62 / 62 / 0 prefix, then a mobile (8x) or area code (2x-7x), then more digits with optional separators. Not preceded by a word
# character, '-', '.', ',' or '=' (so ids inside URLs, prices and dates do not match).
PHONE_RE = re.compile(r"(?<![\w\-.,=])(?:\+62[\s\-.]?\(?|62[\s\-.]?|\(?0)(?:8[1-9]|[2-7]\d)[\d\s\-.()]{5,17}\d(?![\w])")


def normalize(s):
    """'0812-0000-1111' / '+62 812 0000 1111' / 'wa.me/6281200001111' -> '6281200001111'."""
    d = re.sub(r"\D", "", s or "")
    if d.startswith("0"):
        d = "62" + d[1:]
    elif d.startswith("620"):          # +62 0812… (trunk 0 kept after the country code)
        d = "62" + d[3:]
    return d


# Strict detector for fields that must carry no contact at all (bpjs_info / biaya_gratis, SCHEMA v4/v5).
# Structural, not separator by separator (QA re-check 4):
#   1. NFKC, then blank out ONLY allowlisted number shapes: time RANGES (HH.MM <dash or range word> HH.MM
#      [WIB/WITA/WIT], hours and minutes validated, chained with more ranges/times as in
#      "08.00 - 12.00, 13.00 - 15.00"), Rp/IDR amounts, years 19xx/20xx and dates (dd/mm/yyyy, dd-mm-yy,
#      yyyy-mm-dd, dd Month yyyy …). A single time is NOT exempt. An allowlisted shape that touches
#      other digits (only non-letters in between) is not blanked, so "0812-2019-3344" or
#      "08.00-08.12 3456 7890" cannot hide a number.
#   2. Split what is left on letters only (range words and WIB/WITA/WIT count as glue, not letters).
#      In a segment every non-letter character is ignored: the digit groups are joined, and any run of
#      consecutive groups that is a whole number is reported: mobile (+)62 / 620 / 0, then 8, then 7-11
#      digits; landline (+)62 / 0, then 2-7, then 7-10 digits. A run starts and ends on a group
#      boundary, so a 16-digit NIK or an 18-digit NIP (one group) never matches.
#   3. wa.me/…, tel:…, phone=… links are read as before.
_DASH = r"[-\u2010-\u2015\u2212\ufe58\ufe63]"
_RANGE_WORD = r"(?:s\.?\s?d\b\.?|s/d\b|sampai\b|hingga\b)"
_ZONE = r"\bWI(?:B|TA?)\b"
_T = r"(?<![\d.:,])(?:[01]?\d|2[0-3])[.:][0-5]\d(?![\d]|[.:,]\d)"
_RANGE = rf"{_T}\s*(?:{_DASH}|\b{_RANGE_WORD})\s*{_T}(?:\s*{_ZONE})?"
_TIME_CHAIN = re.compile(rf"{_RANGE}(?:(?:[\s,;/&]+|\s+dan\s+)(?:{_RANGE}|{_T}(?:\s*{_ZONE})?))*", re.I)
_MONTHS = (r"(?:jan(?:uari|uary)?|feb(?:ruari|ruary)?|mar(?:et|ch)?|apr(?:il)?|mei|may|jun[ei]?|jul[iy]?|"
           r"agu(?:stus)?|aug(?:ust)?|sep(?:t(?:ember)?)?|okt(?:ober)?|oct(?:ober)?|nov(?:ember)?|des(?:ember)?|dec(?:ember)?)\.?")
_ALLOW = [
    re.compile(r"\b(?:rp|idr)\.?\s?(?:[1-9]\d{0,2}(?:[.,]\d{3})*|0(?![.,]?\d))(?:,(?:-|00))?(?!\d)", re.I),  # Rp 50.000,- / Rp 0 (never a leading 0: "Rp 08.123…" is a phone)
    re.compile(r"(?<![\d.:/-])(?:[0-2]?\d|3[01])[/.\-](?:0?\d|1[0-2])[/.\-](?:(?:19|20)\d\d|\d\d)(?![\d.:/-]*\d)"),  # 05/11/2026
    re.compile(r"(?<![\d.:/-])(?:19|20)\d\d-(?:0?\d|1[0-2])-(?:[0-2]?\d|3[01])(?![\d])"),            # 2026-11-01
    re.compile(rf"(?<![\d.:])(?:[0-2]?\d|3[01])\s+{_MONTHS}\s+(?:19|20)\d\d(?!\d)", re.I),            # 1 November 2026
    re.compile(r"(?<![\d.:,])(?:19|20)\d\d(?![\d]|[.:,]\d)"),                                         # 2024
]
_GLUE_WORDS = re.compile(rf"\b{_RANGE_WORD}|{_ZONE}", re.I)
_LETTER = re.compile(r"[^\W\d_]+")
MOBILE = re.compile(r"(?:620?|0)8\d{7,11}")
LANDLINE = re.compile(r"(?:62|0)[2-7]\d{7,10}")


MAX_ALLOW_LEN = 20000      # longer texts get no exemptions at all (fail closed, and keeps the fixpoint below cheap)


def allowlisted_spans(text):
    """(start, end) of every allowlisted shape that does not touch other digits (see step 1).

    Past MAX_ALLOW_LEN characters nothing is exempt: every digit counts, so a long text can only
    give more hits, never fewer. Real bpjs/gratis fields are a few hundred characters. Below the
    cap the release is a graph walk over the spans, linear in the text length."""
    if len(text) > MAX_ALLOW_LEN:
        return []
    spans = [m.span() for m in _TIME_CHAIN.finditer(text)]
    taken = bytearray(len(text) + 1)            # a shape starting inside an earlier one is not added
    for rx in _ALLOW:
        for a, b in spans:
            taken[a:b] = b"\1" * (b - a)
        spans += [m.span() for m in rx.finditer(text) if not taken[m.start()]]
    spans.sort()
    cover = {}                                  # position -> spans holding it (each pattern's own matches
    for j, (a, b) in enumerate(spans):          # never overlap, so a position is in at most 6 spans)
        for i in range(a, b):
            cover.setdefault(i, []).append(j)

    def neighbour(i, step):                     # first letter/digit from i, skipping everything else
        while 0 <= i < len(text) and not text[i].isalpha() and not text[i].isdigit():
            i += step
        return i if 0 <= i < len(text) and text[i].isdigit() else None

    # span j is released when a neighbouring digit is outside every kept span: either free from the
    # start, or once all spans holding that digit have been released (a graph walk, not a rescan)
    released, todo, waiters, pending = set(), [], {}, {}
    for j, (a, b) in enumerate(spans):
        for side, p in ((0, neighbour(a - 1, -1)), (1, neighbour(b, 1))):
            if p is None:
                continue
            holders = cover.get(p, [])
            if not holders:
                if j not in released:
                    released.add(j); todo.append(j)
            else:
                pending[(j, side)] = len(holders)
                for k in holders:
                    waiters.setdefault(k, []).append((j, side))
    while todo:
        for j, side in waiters.get(todo.pop(), []):
            pending[(j, side)] -= 1
            if pending[(j, side)] == 0 and j not in released:
                released.add(j); todo.append(j)
    return [sp for j, sp in enumerate(spans) if j not in released]


def strict_numbers(text):
    """Every whole number found by steps 1-2, as digit strings."""
    for a, b in reversed(allowlisted_spans(text)):
        text = text[:a] + " x " + text[b:]          # a letter: the blanked shape splits the segment
    text = _GLUE_WORDS.sub(" ", text)
    out = []
    for seg in _LETTER.split(text):
        groups = re.findall(r"\d+", seg)
        found = []
        for i in range(len(groups)):
            run = ""
            for j in range(i, len(groups)):
                run += groups[j]
                if len(run) > 15:
                    break
                if MOBILE.fullmatch(run) or LANDLINE.fullmatch(run):
                    found.append((i, j, run))
        # a number inside a longer number ("0200 00000" in "0882-0200-00000") is the same number
        # (a run spans at most 15 groups, so only the 15 starts before i can contain it: linear time)
        maxend = {}
        for i, j, _ in found:
            maxend[i] = max(maxend.get(i, j), j)
        out += [r for i, j, r in found
                if not (maxend[i] > j or any(maxend.get(a, -1) >= j for a in range(max(0, i - 15), i)))]
    return out


def _collect(hits):
    """Normalise raw matches to 62… and keep the Indonesian-length ones, in order, without duplicates."""
    out = []
    for h in hits:
        n = normalize(h)
        if 10 <= len(n) <= 15 and n.startswith("62") and n not in out:
            out.append(n)
    return out


def find(text):
    """All phone-like numbers in a string, normalised, in order (duplicates removed).
    The text is NFKC-normalised (fullwidth digits, ＋６２). In an http(s) URL only wa.me/ and
    api.whatsapp.com phone=… numbers count (ids in other URLs are not phone numbers)."""
    if not isinstance(text, str):
        return []
    text = unicodedata.normalize("NFKC", text)
    if re.match(r"^\s*https?://", text, re.I):
        hits = re.findall(r"(?:wa\.me/|whatsapp\.com/send\?phone=)\+?(\d{9,15})", text, re.I)
        hits += [m.group(0) for m in PHONE_RE.finditer(re.sub(r"^\s*https?://\S*", " ", text, flags=re.I))]
    else:
        hits = [m.group(0) for m in PHONE_RE.finditer(text)]
    return _collect(hits)


def find_strict(text):
    """find() plus the structural scan (strict_numbers), for fields that must hold no contact at
    all. Nothing is skipped: URLs (wa.me/…, tel:…) are scanned like any other text."""
    if not isinstance(text, str):
        return []
    text = unicodedata.normalize("NFKC", text)
    hits = [m.group(0) for m in PHONE_RE.finditer(text)]
    hits += strict_numbers(text)
    hits += re.findall(r"(?:wa\.me/|tel:|phone=)\s*\+?([\d\s\-.]{9,20}\d)", text, re.I)
    return _collect(hits)


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
