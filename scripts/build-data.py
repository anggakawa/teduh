#!/usr/bin/env python3
"""Build data for Peta Lokal Banjarbaru v2.

Reads the repo data (data/places/*.json + data/hotlines.json), validates each record against
data/SCHEMA.md, adds a small `_d` (derived) block the page needs, and writes into site/data/:
  places.json, hotlines.json   (fetched by the page)
  data.js                      (file:// fallback: sets window.PETA_DATA)
  build-report.json            (counts, skipped files, warnings)

The source is read-only. site/data/ is generated (git-ignored); CI and the Pages deploy run this.

Usage:  python3 scripts/build-data.py [--src data] [--out site/data] [--strict]
        --strict: exit 1, before writing anything, if any record is skipped (used by CI)

Leak guard: every output payload is built first and the build exits non-zero, before writing
anything, if the text "catatan_internal" appears in any of them, or if any key in the parsed
payloads is refused by leaks.leaked_key_paths (leaks.py next to this file, the same module
validate.py and migrate-from-store.py use): "internal" after Unicode folding (NOTE_INTERNAL,
catatan-internal, catatan_ınternal …) or a key that is not a plain ASCII identifier
^[A-Za-z0-9_-]+$ (zero-width / soft-hyphen / BOM characters, look-alike letters, spaces).
"""
import argparse, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import leaks   # one rule for every guard: leaks.is_internal_key / leaks.is_plain_key
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(ROOT, "data")
DEFAULT_OUT = os.path.join(ROOT, "site", "data")

# Rough bounding box for Banjarbaru + neighbours (Martapura, Gambut). Coords outside -> no pin.
BOUNDS = {"lat": (-3.8, -3.1), "lng": (114.4, 115.2)}
SCHEMA_STATUS = {"active", "needs-check"}   # SCHEMA.md v2
REQUIRED = ["id", "name", "category", "status"]   # without these a record is skipped

# Category group = top-level slug of `category` (SCHEMA v2), also the marker file prefix.
TOP_CATEGORIES = ["kesehatan-mental", "tumbuh-kembang-anak", "layanan-pendampingan", "psikologi"]

# SCHEMA.md v2 field contract (documents fields as actually stored).
SCHEMA_FIELDS = {
    "id", "name", "short", "category", "subcategories", "tags", "also_in_categories",
    "address", "kelurahan", "kecamatan", "city", "lat", "lng", "coord_method", "latlng_method", "approx_coords",
    "contacts", "hours", "schedule", "services", "price_range", "price_per_session", "cost", "bpjs", "booking",
    "waitlist", "eligibility", "complaint_method", "therapists", "local_notes",
    "status", "open_issues", "field_confidence", "validation_note", "sources", "verified_at", "checked",
    "history", "what_changed", "archived_from", "facility_id", "contact_sources",
    # Explorer evidence fields (SCHEMA.md v2, optional, internal)
    "scope", "task", "schedule_note", "evidence", "independence_note", "head", "searched", "activity_evidence",
    # User-facing Indonesian display fields (SCHEMA.md v3, 2026-10-31)
    "address_display", "kelurahan_display", "kecamatan_display", "city_display", "address_note_id", "note_id",
    "hours_normalized", "hours_note_id", "name_display", "services_display", "booking_display", "search_terms",
    # BPJS status (SCHEMA.md v4, 2026-11-01)
    "bpjs_info",
    # Is the service free? (SCHEMA.md v5, 2026-11-01)
    "biaya_gratis",
}
DAY_IDX = {d: i for i, d in enumerate(["senin", "selasa", "rabu", "kamis", "jumat", "sabtu", "minggu"])}
CORE_FIELDS = ["id", "name", "short", "category", "subcategories", "tags", "address", "city", "lat", "lng",
               "contacts", "status", "sources", "checked"]
LIST_FIELDS = ["subcategories", "tags", "also_in_categories", "schedule", "services", "sources",
               "services_display", "booking_display", "search_terms", "hours_normalized"]

PHONE_RE = re.compile(r"(?<![\w/+])(?:\+?62[\s\-]?|\(?0)\d[\d\s\-.)]{5,}\d")
WAME_RE = re.compile(r"wa\.me/(\d{9,15})", re.I)
SHORT_RE = re.compile(r"^\s*(1\d{2})\b")
URL_RE = re.compile(r"(https?://[^\s;,)]+|(?<![\w@/.])(?:www\.)?(?:instagram\.com|facebook\.com|linktr\.ee)/[^\s;,)]+)")
UNKNOWN_RE = re.compile(r"^\s*(unknown|not published|tidak diketahui|-)\b", re.I)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def group_of(cat):
    top = (cat or "").split("/")[0]
    return top if top in TOP_CATEGORIES else None


# ---------- hours: best-effort parse of free-text hours into a week (Mon=0..Sun=6) ----------
DAY_WORDS = {
    0: ["senin", "sen", "mon", "monday"], 1: ["selasa", "sel", "tue", "tuesday"], 2: ["rabu", "rab", "wed", "wednesday"],
    3: ["kamis", "kam", "thu", "thursday"], 4: ["jumat", "jum'at", "jum", "fri", "friday"],
    5: ["sabtu", "sab", "sat", "saturday"], 6: ["minggu", "min", "ahad", "sun", "sunday"],
}
DAY_OF = {w: d for d, ws in DAY_WORDS.items() for w in ws}
DAY_RX = "(?:" + "|".join(sorted(map(re.escape, DAY_OF), key=len, reverse=True)) + ")"
TIME_RX = r"(\d{1,2})[.:](\d{2})"
SPAN_RE = re.compile(TIME_RX + r"\s*[–—-]\s*(?:" + TIME_RX + r"|(selesai))", re.I)
SEG_RE = re.compile(r"(?<![a-z])(" + DAY_RX + r"(?:\s*(?:[–—-]|&|,|dan|and)\s*" + DAY_RX + r")*)(?![a-z])\s*:?\s*"
                    r"(" + TIME_RX + r"\s*[–—-]\s*(?:" + TIME_RX + r"|selesai)|closed|tutup|libur)", re.I)


def days_of(expr):
    toks = re.findall(r"[A-Za-z']+|[–—-]|&|,", expr)
    out, prev, rng = [], None, False
    for t in toks:
        tl = t.lower()
        if tl in DAY_OF:
            d = DAY_OF[tl]
            if rng and prev is not None:
                out += [(prev + i) % 7 for i in range(1, (d - prev) % 7 + 1)]
            else:
                out.append(d)
            prev, rng = d, False
        elif t in "–—-":
            rng = True
    return sorted(set(out))


def fmt_span(m):
    a = f"{int(m.group(1)):02d}.{m.group(2)}"
    b = "selesai" if m.group(5) else f"{int(m.group(3)):02d}.{m.group(4)}"
    return f"{a}–{b}"


def parse_text_week(text, week):
    found = False
    for m in SEG_RE.finditer(text):
        val = m.group(2)
        span = SPAN_RE.search(val)
        v = fmt_span(span) if span else "tutup"
        for d in days_of(m.group(1)):
            if week[d] is None:
                week[d] = v; found = True
    return found


def parse_hours(hours):
    """Return {label, week[7], igd24} or None. Values: '09.00–17.00' | 'tutup' | None (unknown)."""
    if not hours:
        return None
    week, label, igd24 = [None] * 7, None, False
    items = hours.items() if isinstance(hours, dict) else [("", hours)] if isinstance(hours, str) else []
    for key, val in items:
        if not isinstance(val, str) or UNKNOWN_RE.match(val):
            continue
        k = key.lower()
        if "igd" in k:
            igd24 = igd24 or "24" in val
            continue
        if k.startswith(("posbakum", "clinic", "daftar_ulang")):
            continue
        parts = [p for p in k.split("_") if p]
        dayparts = [p for p in parts if p in DAY_OF]
        got = False
        if dayparts:
            span = SPAN_RE.search(val)
            v = fmt_span(span) if span else ("tutup" if re.search(r"tutup|closed|libur", val, re.I) else None)
            ds = days_of("–".join(dayparts)) if len(dayparts) == 2 else [DAY_OF[dayparts[0]]]
            for d in ds:
                if v and week[d] is None:
                    week[d] = v; got = True
        else:
            got = parse_text_week(val, week)
        if got and label is None:
            if re.search(r"poli|rawat_jalan|rehab", k):
                label = "Poli"
            elif re.search(r"office|court|kantor", k):
                label = "Kantor"
    if not any(week):
        return {"label": None, "week": None, "igd24": igd24} if igd24 else None
    return {"label": label or "Buka", "week": week, "igd24": igd24}


def week_from_normalized(items):
    """hours_normalized [{day, open, close[, closed]}] -> week[7]. Days not listed stay None (unknown)."""
    week = [None] * 7
    for it in items or []:
        d = DAY_IDX.get(str(it.get("day", "")).lower())
        if d is None:
            continue
        if it.get("closed") or not (it.get("open") and it.get("close")):
            week[d] = "tutup"
        else:
            week[d] = f"{it['open']}–{it['close']}"
    return week


def hours_of(rec):
    """Prefer hours_normalized (SCHEMA v3); the raw `hours` text still supplies label (Poli/Kantor) and IGD 24h."""
    parsed = parse_hours(rec.get("hours"))
    norm = rec.get("hours_normalized")
    if not isinstance(norm, list) or not norm:
        return parsed
    week = week_from_normalized(norm)
    if not any(week):
        return parsed
    label = (parsed or {}).get("label") or "Buka"
    return {"label": label, "week": week, "igd24": bool((parsed or {}).get("igd24"))}


BPJS_STATUS = {"ya", "sebagian", "tidak", "tidak_relevan", "belum_diketahui"}   # SCHEMA.md v4
BPJS_PUBLIC = ("status", "rujukan", "catatan_display", "sources", "checked")   # never catatan_internal; basis is not shipped
BPJS_SOURCE_PUBLIC = ("url", "note", "checked")
BPJS_ACCEPTS = ("ya", "sebagian")    # the statuses the "Terima BPJS" filter keeps
BPJS_SEARCH_WORDS = " bpjs jkn kis"   # SCHEMA v4 search_terms for places that take BPJS
LEAK_MARKER = "catatan_internal"


# SCHEMA.md v5 biaya_gratis. The "Gratis" tag comes only from this status (never from free text,
# never from BPJS acceptance). basis is evidence bookkeeping and is not shipped.
GRATIS_STATUS = {"ya", "bersyarat", "tidak", "belum_diketahui"}
GRATIS_TAG = {"ya": "Gratis", "bersyarat": "Gratis bersyarat"}   # tidak / belum_diketahui: no tag
GRATIS_PUBLIC = ("status", "syarat_display", "perlu_cek_ulang", "sources", "checked")


def bpjs_info_of(rec):
    bi = rec.get("bpjs_info")
    return bi if isinstance(bi, dict) and bi.get("status") in BPJS_STATUS else None


def public_sources(srcs):
    """Sources as shipped: {url, note, checked} from objects; bare strings only when they are an http(s) URL."""
    out = []
    for s in srcs if isinstance(srcs, list) else []:
        if isinstance(s, dict):
            kept = {k: s[k] for k in BPJS_SOURCE_PUBLIC if k in s}
            if kept:                  # a source with nothing public left ({} husk) is dropped
                out.append(kept)
        elif isinstance(s, str) and re.match(r"https?://", s.strip()):
            out.append({"url": s.strip()})
    return out


def gratis_info_of(rec):
    g = rec.get("biaya_gratis")
    return g if isinstance(g, dict) and g.get("status") in GRATIS_STATUS else None


def public_biaya_gratis(g, keep_status=True):
    keys = GRATIS_PUBLIC if keep_status else tuple(k for k in GRATIS_PUBLIC if k != "status")
    out = {k: g[k] for k in keys if k in g}
    if "perlu_cek_ulang" in out:
        out["perlu_cek_ulang"] = out["perlu_cek_ulang"] is True
    if "sources" in out:
        out["sources"] = public_sources(out["sources"])
    return out


def gratis_d(rec):
    """SCHEMA v5 -> what the UI needs: {status, tag, syarat, recheck} or None when there is no usable status."""
    g = gratis_info_of(rec)
    if not g:
        return None
    syarat = g.get("syarat_display") if isinstance(g.get("syarat_display"), str) else ""
    return {"status": g["status"], "tag": GRATIS_TAG.get(g["status"]), "syarat": syarat.strip() or None,
            "recheck": g.get("perlu_cek_ulang") is True}


def bpjs_accepts(status):
    return status in BPJS_ACCEPTS


def public_bpjs_info(bi, keep_status=True):
    """The site copy of bpjs_info: whitelisted keys only (catatan_internal stays in the archive).
    keep_status=False (invalid status): the status is dropped, the user-facing note is kept."""
    keys = BPJS_PUBLIC if keep_status else tuple(k for k in BPJS_PUBLIC if k not in ("status", "rujukan"))
    out = {k: bi[k] for k in keys if k in bi}
    if "sources" in out:
        out["sources"] = public_sources(out["sources"])
    return out


def cost_tags(rec):
    tags = []
    def txt(v):
        if isinstance(v, dict):
            return " ".join(txt(x) for x in v.values())
        if isinstance(v, list):
            return " ".join(txt(x) for x in v)
        return "" if not isinstance(v, str) or UNKNOWN_RE.match(v) and "Rp" not in v.split(".")[0] else v
    # "Gratis" / "Gratis bersyarat" come only from biaya_gratis (SCHEMA v5), rendered from _d.gratis.
    # SCHEMA v4: the BPJS chip is rendered from _d.bpjs; the legacy "BPJS" tag only without bpjs_info.
    if not bpjs_info_of(rec):
        bpjs = rec.get("bpjs") if isinstance(rec.get("bpjs"), str) else ""
        pr = rec.get("price_range") if isinstance(rec.get("price_range"), str) else ""
        if re.match(r"\s*(yes|ya)\b", bpjs, re.I) or re.search(r"BPJS (diterima|&|untuk)", pr):
            tags.append("BPJS")
    if re.search(r"Rp\s?\d", txt(rec.get("price_range")) + " " + txt(rec.get("price_per_session"))):
        tags.append("Berbayar")
    return tags


def norm_phone(s):
    d = re.sub(r"\D", "", s)
    if d.startswith("0"):
        d = "62" + d[1:]
    if not d.startswith("62") or not (9 <= len(d) <= 15):
        return None
    return d


def walk_strings(key, v):
    """Yield (key, string) pairs from nested contact values."""
    if isinstance(v, str):
        yield key, v
    elif isinstance(v, list):
        for x in v:
            yield from walk_strings(key, x)
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from walk_strings(f"{key}.{k}", x)


def extract_contacts(contacts):
    phones, links, seen, seen_url = [], [], {}, set()
    for key, val in walk_strings("", contacts or {}):
        key = key.strip(".")
        if UNKNOWN_RE.match(val):
            continue
        lk = key.lower()
        wa_key = "whatsapp" in lk or re.search(r"(^|_)wa(_|$)", lk) is not None
        wa_text = re.search(r"\bWA\b|whatsapp|wa\.me", val, re.I) is not None
        conflict = "conflict" in val.lower()
        found = [(m.group(0).strip(" .)"), norm_phone(m.group(0)), phone_source(val, m.end())) for m in PHONE_RE.finditer(val)]
        found += [(m.group(0), norm_phone(m.group(1)), None) for m in WAME_RE.finditer(val)]
        for disp, n, src in found:
            if not n:
                continue
            mobile = n.startswith("628")
            wa = mobile and (wa_key or wa_text)
            if n in seen:
                p = seen[n]
                p["wa"] = p["wa"] or wa
                p["conflict"] = p["conflict"] or conflict
                continue
            p = {"label": key, "display": disp if not disp.startswith("wa.me") else "+" + n,
                 "tel": "+" + n, "mobile": mobile, "wa": wa, "conflict": conflict,
                 "source": src if conflict else None}
            seen[n] = p
            phones.append(p)
        m = SHORT_RE.match(val)
        if m and m.group(1) not in seen:
            seen[m.group(1)] = p = {"label": key, "display": m.group(1), "tel": m.group(1),
                                    "mobile": False, "wa": False, "conflict": False}
            phones.append(p)
        for u in URL_RE.findall(val):
            url = u if u.startswith("http") else "https://" + u
            if url not in seen_url:
                seen_url.add(url); links.append({"label": key, "url": url})
        for em in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]*\w", val):
            url = "mailto:" + em
            if url not in seen_url:
                seen_url.add(url); links.append({"label": key, "url": url})
        if lk.startswith(("instagram", "x")) and not lk.startswith("x_"):
            for h in re.findall(r"(?<![\w.])@([A-Za-z0-9_.]{2,30})", val):
                base = "https://instagram.com/" if lk.startswith("instagram") else "https://x.com/"
                url = base + h.rstrip(".")
                if url not in seen_url:
                    seen_url.add(url); links.append({"label": key, "url": url})
    for p in phones:
        p["wa_url"] = "https://wa.me/" + p["tel"].lstrip("+") if p["mobile"] else None
    return phones, links


def phone_source(val, end):
    """'0812… (idalamat, 2 mirror pages = 1 source)' -> 'idalamat'; 'Google Maps via Exa' -> 'Google Maps'."""
    m = re.match(r"\s*\(([^)]*)\)", val[end - 1:] if val[end - 1:end] == ")" else val[end:])
    if not m:
        return None
    src = re.split(r",|;| via ", m.group(1))[0].strip()
    return src or None


# ---- Clean, user-facing address (SPEC §6 "Address": one clean line, never raw research notes) ----
# Uses address_display / kelurahan_display / city_display / address_note_id when the record has them
# (SPEC §11 proposal). Otherwise derives a clean line from the raw fields; everything cut away stays
# available under "Info lengkap & sumber". Only fixed Indonesian sentences are generated, never facts.
NOTE_WORDS = re.compile(r"conflict|unresolved|possibly|not verified|\bvs\b|likely|temporary|indozone", re.I)
KEL_FIX = {"guntungmanggis": "Guntung Manggis"}
ADDR_PREFIX = [(re.compile(r"^permanent:\s*", re.I), ""), (re.compile(r"^dinas office:\s*", re.I), "Kantor dinas: ")]
KEEP_PAREN = re.compile(r"^(?:[A-Z0-9 .,/]+|Km\s?[\d,.]+)$")


def _cut(text):
    """Split the clean part from research notes. Parentheticals are kept only when they are part of the
    address itself ('(III)', '(Km 33)', '(KCG)'); source notes like '(Google Maps)' are dropped.
    Then cut at ' — …', '; …', '. ENGLISH…'. Returns (clean, removed_text)."""
    removed = []
    def paren(m):
        if KEEP_PAREN.match(m.group(1).strip()):
            return m.group(0)
        removed.append(m.group(1)); return ""
    t = re.sub(r"\s*\(([^()]*)\)", paren, text)
    m = re.search(r"\s[—–]\s|;\s|\.\s+[A-Z]{4,}|\.\s+[A-Z][a-z]+ [a-z]", t)
    if m:
        removed.append(t[m.start():]); t = t[:m.start()]
    t = re.sub(r"\s+area$", "", t.strip(" ,."))
    return t, " ".join(removed).strip()


def _kel(name):
    n = re.sub(r"\s*\(.*?\)", "", name).strip(" ,.")
    return KEL_FIX.get(n.lower().replace(" ", ""), n)


def clean_address(rec):
    raw_addr = rec.get("address") if isinstance(rec.get("address"), str) else ""
    raw_kel = rec.get("kelurahan") if isinstance(rec.get("kelurahan"), str) else ""
    raw_kec = rec.get("kecamatan") if isinstance(rec.get("kecamatan"), str) else ""
    notes = []
    # address line
    if "address_display" in rec:
        line = rec["address_display"] or None
    elif not raw_addr or UNKNOWN_RE.match(raw_addr) or re.match(r"^At each\b", raw_addr):
        line = None
    else:
        a = raw_addr
        for rx, rep in ADDR_PREFIX:
            a = rx.sub(rep, a)
        line, rest = _cut(a)
        if rest and re.search(r"temporary", rest, re.I):
            notes.append("Sedang pindah sementara ke lokasi lain. Tanyakan alamat saat menelepon.")
        elif rest and NOTE_WORDS.search(rest):
            notes.append("Alamat berbeda antar sumber. Tanyakan saat menelepon.")
    # kelurahan
    kel, kel_alt = None, []
    if "kelurahan_display" in rec:
        kel = rec["kelurahan_display"] or None
    elif raw_kel and not UNKNOWN_RE.match(raw_kel) and not re.match(r"^all\b", raw_kel, re.I):
        k = re.sub(r"^(conflict(ing sources)?):\s*", "", raw_kel, flags=re.I)
        k = re.sub(r"\s*\([^()]*\)", "", k)
        k = re.split(r"\.\s", k)[0]
        parts = re.split(r"\s+vs\.?\s+|\s[—–]\s*possibly\s+|\s/\s", k)
        if len(parts) > 1:
            cands = []
            for x in parts:
                c = _kel(re.split(r"[,;]", x)[0])
                if c and c not in cands:
                    cands.append(c)
            kel, kel_alt = cands[0], cands
        else:
            kel = _kel(_cut(k)[0])
        if kel and len(kel.split()) > 4:
            kel, kel_alt = None, []
    if len(kel_alt) > 1 and not any("pindah" in n for n in notes):
        notes.append("Kelurahan berbeda antar sumber (" + " / ".join(kel_alt) + "). Tanyakan saat menelepon.")
    kel_in_area = None
    if line and kel and not kel_alt[1:] and kel.lower().replace(" ", "") not in line.lower().replace(" ", ""):
        if re.search(r"\b\d{5}\b", line):
            kel_in_area = kel           # line already ends in city + postcode: kelurahan goes on the sub-line
        else:
            line = f"{line}, {kel}"
    # area (kecamatan, city)
    kec = None
    if "kecamatan_display" in rec:
        kec = rec["kecamatan_display"] or None
    elif raw_kec and not UNKNOWN_RE.match(raw_kec) and not re.search(r"/|conflict|see |^all\b", raw_kec, re.I):
        kec = _cut(raw_kec)[0]
    city = city_display(rec)
    area = ", ".join(x for x in (kel_in_area, kec, city) if x and x.lower() not in (line or "").lower())
    if line:
        for bad, good in KEL_FIX.items():
            line = re.sub(bad, good, line, flags=re.I)
    if "address_note_id" in rec:
        notes = [rec["address_note_id"]] if rec["address_note_id"] else []
    return {"line": line, "area": area or None, "note": notes[0] if notes else None}


def city_display(rec):
    if rec.get("city_display"):
        return rec["city_display"]
    c = rec.get("city") if isinstance(rec.get("city"), str) else ""
    m = re.match(r"^\s*Kab(?:\.|upaten)\s+Banjar\s*\(([A-Z][a-z]+)\)", c)
    if m:
        return m.group(1)
    return re.split(r"\s\(|\s[–—-]\s", c)[0].strip() or None


def regional_place(rec):
    """Short place name for the 'Luar kota · …' tag."""
    kec = rec.get("kecamatan") if isinstance(rec.get("kecamatan"), str) else ""
    if kec and not UNKNOWN_RE.match(kec) and "/" not in kec and len(kec.split()) <= 2:
        return kec.strip()
    return city_display(rec)


def short_name(name):
    n = re.split(r"\s[–-]\s|\s\(", name or "")[0]
    return n.strip()


def maps_query(rec):
    name = rec.get("short") or short_name(rec["name"])
    city = rec.get("city") or "Banjarbaru"
    city = "Banjarbaru" if city.lower().startswith("banjarbaru") else re.split(r"[–(]", city)[0].strip()
    return f"{name}, {city}"


def search_text(rec):
    parts = []
    # SPEC §6: search matches name, services, kelurahan and tags (+ derived cost tags, added in derive()).
    # + Indonesian display fields and search_terms (synonyms, SCHEMA v3).
    for k in ("name", "short", "services", "services_display", "kelurahan", "kelurahan_display", "tags", "search_terms"):
        for _, s in walk_strings(k, rec.get(k)):
            parts.append(s)
    return " ".join(parts).lower()


def validate(rec, fname, warn):
    errs = [f"missing required field '{f}'" for f in REQUIRED if not rec.get(f)]
    if errs:
        return errs
    stem = os.path.splitext(os.path.basename(fname))[0]
    if rec["id"] != stem:
        warn(fname, f"id '{rec['id']}' != filename '{stem}'")
    for f in CORE_FIELDS:
        if f not in rec:
            warn(fname, f"missing core field '{f}'" + (" (falls back to name)" if f == "short" else
                                                         " (falls back to verified_at)" if f == "checked" else ""))
    if rec["status"] not in SCHEMA_STATUS:
        warn(fname, f"unknown status '{rec['status']}' (treated as needs-check)")
    if group_of(rec["category"]) is None:
        warn(fname, f"category top '{rec['category'].split('/')[0]}' not in {TOP_CATEGORIES}")
    for f in LIST_FIELDS:
        if f in rec and rec[f] is not None and not isinstance(rec[f], list):
            warn(fname, f"'{f}' should be a list, got {type(rec[f]).__name__}")
    for f in ("checked", "verified_at"):
        v = rec.get(f)
        if v and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)):
            warn(fname, f"{f} '{v}' not YYYY-MM-DD")
    if rec.get("checked") and rec.get("verified_at") and rec["checked"] != rec["verified_at"]:
        warn(fname, f"checked {rec['checked']} != verified_at {rec['verified_at']}")
    if rec.get("status") == "needs-check" and not rec.get("open_issues"):
        warn(fname, "needs-check without open_issues (schema: open_issues = why needs-check)")
    extra = sorted(set(rec) - SCHEMA_FIELDS)
    if extra:
        warn(fname, f"fields not in SCHEMA.md: {', '.join(extra)}")
    return []


def bpjs_d(rec):
    """SCHEMA v4 -> what the UI needs. `accepts` drives the "Terima BPJS" filter (ya + sebagian only);
    belum_diketahui is never folded into tidak."""
    bi = bpjs_info_of(rec)
    if not bi:
        return None
    st = bi["status"]
    rj = bi.get("rujukan") if isinstance(bi.get("rujukan"), bool) else None
    return {"status": st, "rujukan": rj if bpjs_accepts(st) else None, "accepts": bpjs_accepts(st)}


def bpjs_words(rec):
    bi = bpjs_info_of(rec)
    if bi:   # SCHEMA v4: places that take BPJS get the search words BPJS, JKN, KIS
        return BPJS_SEARCH_WORDS if bpjs_accepts(bi["status"]) else ""
    return " bpjs" if re.match(r"\s*(yes|ya)\b", str(rec.get("bpjs") or ""), re.I) else ""


def gratis_words(rec):
    g = gratis_d(rec)
    return " " + g["tag"].lower() if g and g["tag"] else ""


def derive(rec, fname, warn):
    lat, lng = rec.get("lat"), rec.get("lng")
    pin = None
    if is_num(lat) and is_num(lng):
        if BOUNDS["lat"][0] <= lat <= BOUNDS["lat"][1] and BOUNDS["lng"][0] <= lng <= BOUNDS["lng"][1]:
            pin = {"lat": lat, "lng": lng}
        else:
            warn(fname, f"lat/lng {lat},{lng} outside Banjarbaru bounds -> not pinned")
    elif lat is not None or lng is not None:
        warn(fname, f"lat/lng not numeric ({lat!r},{lng!r}) -> not pinned")
    approx = rec.get("approx_coords") if isinstance(rec.get("approx_coords"), dict) else None
    # Hard rule: approx_coords are OSM street midpoints and must never become a pin.
    if pin and approx and is_num(approx.get("lat")) and abs(approx["lat"] - pin["lat"]) < 1e-7 \
            and abs(approx.get("lng", 0) - pin["lng"]) < 1e-7:
        warn(fname, "lat/lng equals approx_coords (street midpoint) -> NOT pinned")
        pin = None
    city = (rec.get("city") or "")
    # SCHEMA v2: a tag containing "regional" = outside Banjarbaru. City text is a fallback.
    regional = any("regional" in str(t).lower() for t in rec.get("tags") or []) or \
        (bool(city) and not city.lower().startswith("banjarbaru"))
    phones, links = extract_contacts(rec.get("contacts"))
    q = maps_query(rec)
    from urllib.parse import quote
    if pin:
        dest = f"{pin['lat']},{pin['lng']}"
        maps = f"https://www.google.com/maps/search/?api=1&query={dest}"
    else:
        dest = quote(q)
        maps = f"https://www.google.com/maps/search/?api=1&query={quote(q)}"
    short = rec.get("short") or short_name(rec["name"])
    checked = rec.get("checked") or rec.get("verified_at")
    return {
        "group": group_of(rec.get("category")) or "kesehatan-mental",
        "short": short,
        "checked": checked if checked and re.match(r"^\d{4}-\d{2}", str(checked)) else None,
        "hours": hours_of(rec),
        "tags": cost_tags(rec),
        "booking_janji": bool(re.search(r"janji|appointment|booking|daftar", json.dumps(rec.get("booking") or "", ensure_ascii=False), re.I)),
        "pin": pin,
        "approx_only": pin is None,
        "has_approx": approx is not None,
        "needs_check": rec.get("status") != "active",
        "regional": regional,
        "phones": phones,
        "links": links,
        "maps_url": maps,
        "dir_url": f"https://www.google.com/maps/dir/?api=1&destination={dest}",
        "maps_query": q,
        "q": search_text(rec) + " " + " ".join(cost_tags(rec)).lower() + bpjs_words(rec) + gratis_words(rec),
        "bpjs": bpjs_d(rec),
        "gratis": gratis_d(rec),
        "addr": clean_address(rec),
        "place": regional_place(rec) if regional else None,
        "note_id": rec.get("note_id") if isinstance(rec.get("note_id"), str) else None,
        "hours_note": rec.get("hours_note_id") if isinstance(rec.get("hours_note_id"), str) else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()
    out_dir = a.out
    report = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "src": os.path.relpath(a.src, ROOT) if a.src.startswith(ROOT) else a.src,
              "skipped": [], "warnings": [], "schema_drift": []}
    warn = lambda f, m: report["warnings"].append({"file": os.path.basename(f), "msg": m})

    places, ids, seen_keys = [], set(), set()
    files = sorted(glob.glob(os.path.join(a.src, "places", "*.json")))
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception as e:
            report["skipped"].append({"file": os.path.basename(f), "reason": f"invalid JSON: {e}"}); continue
        if not isinstance(rec, dict):
            report["skipped"].append({"file": os.path.basename(f), "reason": "not an object"}); continue
        errs = validate(rec, f, warn)
        if errs:
            report["skipped"].append({"file": os.path.basename(f), "reason": "; ".join(errs)}); continue
        if rec["id"] in ids:
            report["skipped"].append({"file": os.path.basename(f), "reason": f"duplicate id {rec['id']}"}); continue
        ids.add(rec["id"]); seen_keys.update(rec.keys())
        rec["_d"] = derive(rec, f, warn)
        if "biaya_gratis" in rec:
            g = rec["biaya_gratis"]
            if gratis_info_of(rec):
                rec["biaya_gratis"] = public_biaya_gratis(g)
            elif isinstance(g, dict):
                warn(f, f"biaya_gratis.status {g.get('status')!r} not in SCHEMA -> status dropped (no tag), syarat_display kept")
                rec["biaya_gratis"] = public_biaya_gratis(g, keep_status=False)
            else:
                warn(f, f"biaya_gratis is not an object ({type(g).__name__}) -> dropped")
                del rec["biaya_gratis"]
        if "bpjs_info" in rec:
            bi = rec["bpjs_info"]
            if bpjs_info_of(rec):
                rec["bpjs_info"] = public_bpjs_info(bi)
            elif isinstance(bi, dict):
                # Unknown status: drop only the status (no chip, not in the filter); keep the Indonesian note.
                warn(f, f"bpjs_info.status {bi.get('status')!r} not in SCHEMA -> status dropped, catatan_display kept")
                rec["bpjs_info"] = public_bpjs_info(bi, keep_status=False)
            else:
                warn(f, f"bpjs_info is not an object ({type(bi).__name__}) -> dropped")
                del rec["bpjs_info"]
        places.append(rec)

    # Duplicate pins (same building listed twice) -> fine with clustering, but report.
    by_xy = {}
    for p in places:
        if p["_d"]["pin"]:
            by_xy.setdefault((p["_d"]["pin"]["lat"], p["_d"]["pin"]["lng"]), []).append(p["id"])
    for xy, idl in by_xy.items():
        if len(idl) > 1:
            report["warnings"].append({"file": ", ".join(idl), "msg": f"same coordinates {xy} (separate records for one building)"})

    report["schema_drift"] = {
        "fields_in_data_not_in_schema": sorted(seen_keys - SCHEMA_FIELDS),
        "status_values_not_in_schema": sorted({p["status"] for p in places} - SCHEMA_STATUS),
    }

    hotlines = []
    hp = os.path.join(a.src, "hotlines.json")
    try:
        with open(hp, encoding="utf-8") as fh:
            raw = json.load(fh)
        for i, h in enumerate(raw if isinstance(raw, list) else []):
            if not isinstance(h, dict) or not h.get("name"):
                report["skipped"].append({"file": f"hotlines.json[{i}]", "reason": "missing name"}); continue
            phones, links = extract_contacts(h.get("contacts"))
            h["_d"] = {"phones": phones, "links": links}
            hotlines.append(h)
    except Exception as e:
        report["skipped"].append({"file": "hotlines.json", "reason": str(e)})

    pinned = [p for p in places if p["_d"]["pin"]]
    unpinned = [p for p in places if not p["_d"]["pin"]]
    report["counts"] = {
        "files": len(files), "places": len(places), "pinned": len(pinned),
        "unpinned": len(unpinned),
        "unpinned_with_approx_coords": sum(p["_d"]["has_approx"] for p in unpinned),
        "needs_check": sum(p["_d"]["needs_check"] for p in places),
        "needs_check_pinned": sum(p["_d"]["needs_check"] for p in pinned),
        "regional": sum(p["_d"]["regional"] for p in places),
        "hotlines": len(hotlines),
        "by_group": {g: sum(p["_d"]["group"] == g for p in places) for g in TOP_CATEGORIES},
        "hours_parsed": sum(bool(p["_d"]["hours"] and p["_d"]["hours"]["week"]) for p in places),
        "missing_short": sum(not p.get("short") for p in places),
        "missing_checked": sum(not p.get("checked") for p in places),
        "bpjs": {s: sum(bool(p["_d"]["bpjs"]) and p["_d"]["bpjs"]["status"] == s for p in places) for s in sorted(BPJS_STATUS)},
        "gratis": {s: sum(bool(p["_d"]["gratis"]) and p["_d"]["gratis"]["status"] == s for p in places) for s in sorted(GRATIS_STATUS)},
    }
    report["unpinned_ids"] = [p["id"] for p in unpinned]

    # Hard-rule self-check.
    for p in places:
        if p["_d"]["pin"] and not (is_num(p.get("lat")) and is_num(p.get("lng"))):
            sys.exit(f"BUG: {p['id']} pinned without real lat/lng")

    meta = {"built_at": report["built_at"], "counts": report["counts"]}
    js = lambda o: json.dumps(o, ensure_ascii=False, indent=1)
    outputs = {
        "places.json": js({"meta": meta, "places": places}),
        "hotlines.json": js({"meta": meta, "hotlines": hotlines}),
        "build-report.json": js(report),
        "data.js": "/* generated by build-data.py — file:// fallback, do not edit */\nwindow.PETA_DATA = " +
                   json.dumps({"places": {"meta": meta, "places": places}, "hotlines": {"meta": meta, "hotlines": hotlines}},
                              ensure_ascii=False) + ";\n",
    }
    # Leak guard on the exact text that would be written (all files), before anything is written.
    leaked = [name for name, text in outputs.items() if LEAK_MARKER in text]
    if leaked:
        sys.exit(f"BUG: {LEAK_MARKER} would ship in {', '.join(leaked)}; nothing written")
    payloads = {"places.json": {"meta": meta, "places": places}, "hotlines.json": {"meta": meta, "hotlines": hotlines},
                "build-report.json": report}
    leaked = [f"{name}: {p}" for name, obj in payloads.items() for p in leaks.leaked_key_paths(obj)[:3]]
    if leaked:
        sys.exit(f"BUG: a key named *internal* would ship, or a key with hidden/non-ASCII characters "
                 f"({'; '.join(leaked)}; data.js too); nothing written")
    if a.strict and report["skipped"]:
        for sk in report["skipped"]:
            print(f"SKIPPED {sk['file']}: {sk['reason']}")
        sys.exit(f"--strict: {len(report['skipped'])} record(s) skipped; nothing written")
    os.makedirs(out_dir, exist_ok=True)
    for name, text in outputs.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    c = report["counts"]
    print(f"places {c['places']}/{c['files']} files | pinned {c['pinned']} | unpinned {c['unpinned']} "
          f"(with approx_coords {c['unpinned_with_approx_coords']}) | needs-check {c['needs_check']} | hotlines {c['hotlines']}")
    for s in report["skipped"]:
        print(f"SKIPPED {s['file']}: {s['reason']}")
    for w in report["warnings"]:
        print(f"WARN {w['file']}: {w['msg']}")
    print(f"hours parsed into a week for {c['hours_parsed']}/{c['places']} places (rest shown as written)")
    print("schema drift:", json.dumps(report["schema_drift"], ensure_ascii=False))


if __name__ == "__main__":
    main()
