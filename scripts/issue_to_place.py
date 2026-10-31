#!/usr/bin/env python3
"""Turn a Teduh issue-form submission into a place JSON change (new file or patch).

The issue body is untrusted input. This script:
  - parses the GitHub issue-form markdown ("### <label>" + value) using the labels in
    .github/ISSUE_TEMPLATE/*.yml, so form and parser cannot drift apart;
  - rejects markup/script-like text, over-long values and malformed phone numbers;
  - phone consent policy: a phone/WhatsApp number is accepted only with the consent checkbox
    ticked and a public http(s) link where the institution/owner publishes it ("Sumber nomor");
    the link is recorded per number in contact_sources. Numbers in any other field are rejected;
  - ALWAYS sets status "needs-check" (a submission can never mark a place verified);
  - sets lat/lng ONLY from a map link that carries exact coordinates (pin in the URL);
    a viewport-only link (".../@lat,lng,17z", "#map=17/lat/lng") becomes approx_coords,
    which are never a pin; short links are never fetched;
  - never deletes a record (a "tutup permanen" report only flags it for review);
  - writes data/places/<id>.json plus out/summary.json, out/pr_body.md, out/comment.md.

Exit codes: 0 = change written, 2 = submission rejected (comment.md explains why), 1 = bug.

Usage: python3 scripts/issue_to_place.py --body-file body.md --issue 12 [--date 2026-10-31] [--out out]
"""
import argparse, glob, json, os, re, sys, unicodedata
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jsonio
import phones as phonelib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, ".github", "ISSUE_TEMPLATE")
WITA = timezone(timedelta(hours=8))
BOUNDS = {"lat": (-3.8, -3.1), "lng": (114.4, 115.2)}   # same box as build-data.py / validate.py
NO_RESPONSE = {"_No response_", "None", "_Tidak ada jawaban_"}
BAD_TEXT = re.compile(r"<\s*/?\s*(script|iframe|img|svg|a|style|object|embed)\b|javascript:|data:text/html|on\w+\s*=", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+", re.I)
PHONE_OK = re.compile(r"^\+?[0-9][0-9 ()\-.]{4,22}[0-9]$")
MAX_LEN = {"nama": 160, "tempat": 160, "alamat": 300, "kelurahan": 80, "telepon": 120, "whatsapp": 60,
           "biaya": 300, "peta": 600, "sumber_nomor": 1000, "layanan": 1500, "jam": 800, "cara_daftar": 800, "sumber": 2000, "catatan": 1500}

CATEGORY = {
    "Kesehatan mental — psikolog / biro psikologi": "kesehatan-mental/biro-psikologi",
    "Kesehatan mental — rumah sakit / poli jiwa": "kesehatan-mental/rumah-sakit",
    "Tumbuh kembang anak — terapi / klinik tumbuh kembang": "tumbuh-kembang-anak/terapi-ABK",
    "Tumbuh kembang anak — sekolah (SLB / inklusi)": "tumbuh-kembang-anak/pendidikan",
    "Pendampingan — bantuan hukum": "layanan-pendampingan/bantuan-hukum",
    "Pendampingan — perlindungan perempuan, anak & keluarga": "layanan-pendampingan/layanan-perlindungan",
    "Biro tes psikologi / asesmen": "psikologi/biro-tes-asesmen",
}
KECAMATAN = {  # dropdown -> (kecamatan, city)
    "Banjarbaru Utara": ("Banjarbaru Utara", "Banjarbaru"),
    "Banjarbaru Selatan": ("Banjarbaru Selatan", "Banjarbaru"),
    "Landasan Ulin": ("Landasan Ulin", "Banjarbaru"),
    "Liang Anggang": ("Liang Anggang", "Banjarbaru"),
    "Cempaka": ("Cempaka", "Banjarbaru"),
    "Martapura (Kabupaten Banjar)": ("Martapura", "Kabupaten Banjar"),
    "Gambut (Kabupaten Banjar)": ("Gambut", "Kabupaten Banjar"),
    "Tidak tahu": ("unknown", None),
}
JENIS = {"Info salah atau sudah berubah": "ubah", "Tempat pindah alamat": "pindah", "Tempat sudah tutup permanen": "tutup"}
# Raw field -> display overrides that would otherwise keep showing the OLD value in the UI.
STALE_DISPLAY = {
    "name": ["name_display"],
    "address": ["address_display", "address_note_id"],
    "kelurahan": ["kelurahan_display"],
    "kecamatan": ["kecamatan_display"],
    "hours": ["hours_normalized", "hours_note_id"],
    "services": ["services_display"],
    "booking": ["booking_display"],
}


class Rejected(Exception):
    pass


# ---------- form parsing ----------
def load_forms():
    import yaml
    forms = {}
    for f in sorted(glob.glob(os.path.join(TEMPLATES, "*.yml"))):
        if f.endswith("config.yml"):
            continue
        t = yaml.safe_load(open(f, encoding="utf-8"))
        fields = {b["attributes"]["label"]: b["id"] for b in t["body"] if b.get("id")}
        forms[os.path.basename(f)] = {"name": t["name"], "fields": fields}
    return forms


def parse_body(body, forms):
    """Split '### Label' sections; pick the form whose labels match best."""
    body = body.replace("\r\n", "\n")
    sections, cur = {}, None
    for line in body.split("\n"):
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            cur = m.group(1); sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    sections = {k: "\n".join(v).strip() for k, v in sections.items()}
    best = max(forms.values(), key=lambda fm: len(set(fm["fields"]) & set(sections)))
    if not set(best["fields"]) & set(sections):
        raise Rejected("Isi issue tidak dikenali sebagai formulir Teduh. Mohon buat issue baru lewat formulir \"Tambah tempat baru\" atau \"Koreksi info tempat\".")
    out = {}
    for label, fid in best["fields"].items():
        v = sections.get(label, "")
        out[fid] = "" if v in NO_RESPONSE else v
    return best["name"], out


def clean(fid, v):
    v = unicodedata.normalize("NFC", v)
    v = "".join(ch for ch in v if ch in "\n\t" or unicodedata.category(ch)[0] != "C").strip()
    if len(v) > MAX_LEN.get(fid, 2000):
        raise Rejected(f"Isian \"{fid}\" terlalu panjang (maks. {MAX_LEN.get(fid, 2000)} karakter).")
    if BAD_TEXT.search(v):
        raise Rejected(f"Isian \"{fid}\" berisi kode/markup yang tidak diizinkan. Tulis teks biasa saja.")
    return v


def lines(v):
    return [re.sub(r"^\s*[-*•]\s*", "", x).strip() for x in v.split("\n") if x.strip()]


def phones(v, label):
    nums = [x.strip() for x in re.split(r"[,;/\n]| atau ", v) if x.strip()]
    for n in nums:
        if not PHONE_OK.match(n):
            raise Rejected(f"Nomor {label} \"{n[:40]}\" tidak terbaca sebagai nomor telepon. Tulis angka saja, mis. 0511-123456.")
    return nums


PHONE_FIELDS = ("telepon", "whatsapp", "sumber_nomor")


def phone_consent(f, issue, date):
    """-> [(number, url)] for the phone/WA fields, or Rejected. Enforces the consent policy."""
    nums = [(n, "telepon") for n in (phones(f["telepon"], "telepon") if f.get("telepon") else [])] + \
           [(n, "WhatsApp") for n in (phones(f["whatsapp"], "WhatsApp") if f.get("whatsapp") else [])]
    for fid, v in f.items():
        if fid not in PHONE_FIELDS and phonelib.find(URL_RE.sub(" ", v)):
            raise Rejected("Nomor telepon/WhatsApp hanya boleh ditulis di kolom \"Nomor telepon tempat\" atau "
                           "\"Nomor WhatsApp tempat\", lengkap dengan sumbernya. Hapus nomor dari kolom lain lalu kirim ulang.")
    if not nums:
        return []
    if not re.search(r"^- \[[xX]\]", f.get("persetujuan_nomor", ""), re.M):
        raise Rejected("Untuk mencantumkan nomor telepon/WhatsApp, centang konfirmasi bahwa nomor itu dicantumkan sendiri "
                       "oleh lembaga/pemiliknya di tempat publik atau pemiliknya sudah setuju.")
    urls = list(dict.fromkeys(u.rstrip(".,;") for u in URL_RE.findall(f.get("sumber_nomor", ""))))
    if not urls:
        raise Rejected("Kolom \"Sumber nomor telepon/WhatsApp\" wajib memuat tautan (https://…) ke halaman tempat "
                       "lembaga/pemiliknya sendiri mencantumkan nomor itu, mis. situs resmi atau akun media sosial resmi.")
    uniq = list(dict.fromkeys(n for n, _ in nums))
    return [(n, urls[i] if len(urls) == len(uniq) else urls[0]) for i, n in enumerate(uniq)]


# ---------- coordinates ----------
def in_box(lat, lng):
    return BOUNDS["lat"][0] <= lat <= BOUNDS["lat"][1] and BOUNDS["lng"][0] <= lng <= BOUNDS["lng"][1]


def decimals(s):
    return len(s.split(".")[1]) if "." in s else 0


def map_coords(link):
    """-> (kind, lat, lng, note). kind: exact | viewport | none. Never fetches the URL."""
    if not link:
        return "none", None, None, ""
    from urllib.parse import urlparse, parse_qs, unquote
    link = link.strip().split()[0]
    num = r"(-?\d{1,2}\.\d+)"
    if link.lower().startswith("geo:"):
        m = re.match(rf"geo:{num},\s*(-?\d{{2,3}}\.\d+)", link, re.I)
        return ("exact", float(m.group(1)), float(m.group(2)), "geo: URI") if m else ("none", None, None, "geo: tanpa koordinat")
    u = urlparse(link)
    host = (u.hostname or "").lower()
    google = re.search(r"(^|\.)google\.[a-z.]+$", host) and (u.path.startswith("/maps") or host.startswith("maps."))
    osm = host.endswith("openstreetmap.org")
    if host in ("maps.app.goo.gl", "goo.gl"):
        return "none", None, None, "tautan pendek tidak dibuka otomatis"
    if not (google or osm):
        return "none", None, None, "bukan tautan Google Maps/OpenStreetMap"
    full = unquote(link)
    q = parse_qs(u.query)
    if google:
        m = re.search(rf"!3d{num}!4d(-?\d{{2,3}}\.\d+)", full)
        if m:
            return "exact", float(m.group(1)), float(m.group(2)), "Google Maps place data (!3d/!4d)"
        for key in ("query", "q", "destination"):
            m = re.match(rf"^\s*{num},\s*(-?\d{{2,3}}\.\d+)\s*$", (q.get(key) or [""])[0])
            if m:
                return "exact", float(m.group(1)), float(m.group(2)), f"Google Maps {key}= pin"
        m = re.search(rf"@{num},(-?\d{{2,3}}\.\d+)", full) or re.match(rf"^{num},(-?\d{{2,3}}\.\d+)$", (q.get("ll") or [""])[0])
        if m:
            return "viewport", float(m.group(1)), float(m.group(2)), "Google Maps view centre (@/ll), not a pin"
    if osm:
        if q.get("mlat") and q.get("mlon"):
            try:
                return "exact", float(q["mlat"][0]), float(q["mlon"][0]), "OpenStreetMap marker (mlat/mlon)"
            except ValueError:
                pass
        m = re.search(rf"map=\d+(?:\.\d+)?/{num}/(-?\d{{2,3}}\.\d+)", u.fragment or "")
        if m:
            return "viewport", float(m.group(1)), float(m.group(2)), "OpenStreetMap view centre (#map=), not a pin"
    return "none", None, None, "tautan tanpa koordinat"


# ---------- record building ----------
def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60].rstrip("-") or "tempat"


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()).strip()


def find_place(ref, places):
    ref = ref.strip().lstrip("#")
    if ref in places:
        return ref
    m = re.search(r"#([a-z0-9-]+)\s*$", ref)
    if m and m.group(1) in places:
        return m.group(1)
    n = norm(ref)
    hits = [pid for pid, p in places.items()
            if n and n in {norm(p.get(k) or "") for k in ("name", "short", "name_display")}]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        hits = [pid for pid, p in places.items() if n and len(n) >= 6 and n in norm(" ".join(str(p.get(k) or "") for k in ("name", "short", "name_display")))]
        if len(hits) == 1:
            return hits[0]
    raise Rejected(("Tempat \"%s\" cocok dengan beberapa data: %s. " % (ref[:80], ", ".join(sorted(hits)[:5])) if hits else
                    "Tempat \"%s\" tidak ditemukan di data. " % ref[:80]) +
                   "Tulis nama persis seperti di peta, atau kode tempat dari alamat halaman (bagian setelah #).")


def sources_from(v, issue, date):
    urls = list(dict.fromkeys(u.rstrip(".,;") for u in URL_RE.findall(v)))
    if not urls:
        raise Rejected("Kolom \"Sumber / bukti\" wajib memuat minimal satu tautan yang diawali https://.")
    rest = URL_RE.sub("", v).strip()
    return [{"url": u, "note": f"dari kontributor (issue #{issue}), belum dicek tim", "checked": date} for u in urls], rest


def apply_location(rec, f, issue, prev, changed, warnings, is_new):
    kind, lat, lng, how = map_coords(f.get("peta", ""))
    if kind in ("exact", "viewport") and not in_box(lat, lng):
        warnings.append(f"Koordinat dari tautan peta ({lat}, {lng}) di luar area Banjarbaru & sekitar, jadi diabaikan.")
        kind = "none"
    if kind == "exact" and (decimals(str(lat)) < 4 or decimals(str(lng)) < 4):
        kind = "viewport"; how += "; fewer than 4 decimals, treated as approximate"
    if kind == "exact":
        for k in ("lat", "lng", "coord_method"):
            prev[k] = rec.get(k)
        rec["lat"], rec["lng"] = lat, lng
        rec["coord_method"] = f"contributor map link (issue #{issue}): {how}; exact coordinates in the URL, not yet checked by the team"
        rec.pop("latlng_method", None)
        changed += ["lat", "lng", "coord_method"]
    elif kind == "viewport":
        prev["approx_coords"] = rec.get("approx_coords")
        rec["approx_coords"] = {"lat": lat, "lng": lng, "precision": "map view centre from a contributor link, NOT the building",
                                "method": f"contributor map link (issue #{issue}): {how}"}
        changed.append("approx_coords")
        if is_new:
            rec["lat"] = rec["lng"] = None
        warnings.append("Tautan peta hanya memuat titik tengah tampilan peta, bukan titik tempat, jadi tidak dipasang sebagai pin.")
    else:
        if is_new:
            rec["lat"] = rec["lng"] = None
        if f.get("peta"):
            warnings.append(f"Tautan peta tidak dipakai untuk pin ({how}). Tim akan mengecek lokasinya.")


def set_field(rec, key, value, prev, changed):
    if rec.get(key) == value:
        return
    prev[key] = rec.get(key)
    rec[key] = value
    changed.append(key)


def build(form_name, f, issue, date, places):
    f = {k: clean(k, v) for k, v in f.items()}
    if len(re.findall(r"^- \[[xX]\]", f.get("persetujuan", ""), re.M)) < 2:
        raise Rejected("Kedua kotak konfirmasi wajib dicentang.")
    srcs, evidence_text = sources_from(f.get("sumber", ""), issue, date)
    phone_srcs = phone_consent(f, issue, date)
    prev, changed, warnings, dropped = {}, [], [], []
    is_new = form_name == "Tambah tempat baru"

    if is_new:
        if not f.get("nama"):
            raise Rejected("Nama tempat wajib diisi.")
        if f.get("kategori") not in CATEGORY:
            raise Rejected("Kategori tidak dikenali. Pilih salah satu kategori dari daftar.")
        n = norm(f["nama"])
        dup = [pid for pid, p in places.items() if n in {norm(p.get(k) or "") for k in ("name", "short", "name_display")}]
        pid = slugify(f["nama"])
        if dup or pid in places:
            raise Rejected("Tempat dengan nama ini sudah ada di peta (%s). Gunakan formulir \"Koreksi info tempat\"." % ", ".join(dup or [pid]))
        rec = {"id": pid, "name": f["nama"], "short": f["nama"], "category": CATEGORY[f["kategori"]],
               "subcategories": [], "tags": [], "address": "unknown", "kelurahan": "unknown", "kecamatan": "unknown",
               "city": "Banjarbaru", "lat": None, "lng": None, "contacts": {}, "hours": "unknown", "schedule": [],
               "services": [], "price_range": "unknown", "booking": [], "local_notes": "", "status": "needs-check",
               "open_issues": "", "field_confidence": {}, "validation_note": "", "sources": [],
               "verified_at": date, "checked": date, "history": [], "archived_from": f"issue #{issue}",
               "search_terms": []}
        changed.append("(tempat baru)")
    else:
        pid = find_place(f.get("tempat", ""), places)
        rec = json.loads(json.dumps(places[pid]))
        jenis = JENIS.get(f.get("jenis"), "ubah")
        if f.get("nama"):
            set_field(rec, "name", f["nama"], prev, changed)
            if places[pid].get("short") == places[pid].get("name"):
                set_field(rec, "short", f["nama"], prev, changed)

    if f.get("layanan"):
        set_field(rec, "services", lines(f["layanan"]), prev, changed)
    elif is_new:
        raise Rejected("Kolom \"Layanan\" wajib diisi.")
    for fid, key in (("alamat", "address"), ("kelurahan", "kelurahan"), ("biaya", "cost")):
        if f.get(fid):
            set_field(rec, key, f[fid], prev, changed)
    if f.get("kecamatan") in KECAMATAN:
        kec, city = KECAMATAN[f["kecamatan"]]
        set_field(rec, "kecamatan", kec, prev, changed)
        if city:
            set_field(rec, "city", city, prev, changed)
            set_field(rec, "city_display", city, prev, changed)
    if f.get("jam"):
        set_field(rec, "hours", f["jam"], prev, changed)
    if f.get("cara_daftar"):
        set_field(rec, "booking", lines(f["cara_daftar"]), prev, changed)
    if f.get("telepon") or f.get("whatsapp"):
        contacts = dict(rec.get("contacts") or {})
        if f.get("telepon"):
            contacts["phone"] = " / ".join(phones(f["telepon"], "telepon"))
        if f.get("whatsapp"):
            contacts["whatsapp"] = " / ".join(phones(f["whatsapp"], "WhatsApp"))
        set_field(rec, "contacts", contacts, prev, changed)

    apply_location(rec, f, issue, prev, changed, warnings, is_new)

    # Display overrides that would keep showing the old value: drop them, maintainer re-adds after review.
    for raw, disp in STALE_DISPLAY.items():
        if raw in changed:
            for d in disp:
                if d in rec:
                    prev[d] = rec.pop(d); dropped.append(d)

    # contact_sources: keep entries whose number is still in the record, add the contributor's links.
    in_rec = phonelib.in_record(rec)
    cs = [c for c in rec.get("contact_sources") or [] if phonelib.normalize(c.get("number", "")) in in_rec]
    have = {phonelib.normalize(c["number"]) for c in cs}
    for n, url in phone_srcs:
        if phonelib.normalize(n) not in have:
            cs.append({"number": n, "url": url, "note": f"dari kontributor (issue #{issue}), belum dicek tim", "checked": date})
            have.add(phonelib.normalize(n))
    if cs != (rec.get("contact_sources") or []):
        set_field(rec, "contact_sources", cs, prev, changed)
    elif not cs:
        rec.pop("contact_sources", None)

    if not is_new and not [c for c in changed if c != "approx_coords"] and jenis == "ubah":
        raise Rejected("Tidak ada kolom yang diubah. Isi kolom yang perlu dikoreksi, lalu kirim ulang.")

    # Verification is never granted by a submission.
    prev["status"] = rec.get("status")
    rec["status"] = "needs-check"
    reason = {"tutup": "reported as permanently closed", "pindah": "reported as moved"}.get(
        "ubah" if is_new else jenis, "new place" if is_new else "correction")
    issue_txt = f"Contributor submission via issue #{issue} ({reason}); not yet checked by the team."
    rec["open_issues"] = issue_txt if is_new or not rec.get("open_issues") else f"{issue_txt} Earlier: {rec['open_issues']}"
    if not is_new and prev.get("note_id") is None and "note_id" in rec:
        prev["note_id"] = rec["note_id"]
    rec["note_id"] = {
        "tutup": "Ada laporan bahwa tempat ini sudah tutup permanen. Belum dicek tim; mohon telepon dulu.",
        "pindah": "Ada laporan bahwa tempat ini pindah alamat. Belum dicek tim; mohon telepon dulu.",
    }.get("ubah" if is_new else jenis, "Info dari kontributor, belum dicek tim. Mohon konfirmasi via telepon.")
    rec["sources"] = (rec.get("sources") or []) + [s for s in srcs if s["url"] not in {x.get("url") for x in rec.get("sources") or []}]
    fc = dict(rec.get("field_confidence") or {})
    for k in changed:
        if not k.startswith("("):
            fc[k] = f"single source (contributor, issue #{issue})"
    if is_new:
        fc["exists"] = f"single source (contributor, issue #{issue})"
    rec["field_confidence"] = fc
    notes = [x for x in (evidence_text, f.get("catatan")) if x]
    if notes:
        rec["validation_note"] = ((rec.get("validation_note") or "") + f" Contributor note (issue #{issue}): " + " | ".join(notes)).strip()
    what = ("New place submitted" if is_new else f"Correction submitted ({reason})") + f" via issue #{issue}; fields: {', '.join(changed) or '-'}" + \
           (f"; display overrides dropped for review: {', '.join(dropped)}" if dropped else "") + f"; previous status: {prev.get('status') or '-'}."
    rec["what_changed"] = what
    rec["history"] = (rec.get("history") or []) + [{"batch": f"issue-{issue}", "date": date, "what_changed": what}]
    return pid, rec, prev, changed, dropped, warnings, (None if is_new else jenis)


# ---------- output ----------
def safe(v):
    """For markdown: no backticks (fence breaks); @ and # neutralised so nothing pings or links."""
    s = json.dumps(v, ensure_ascii=False)
    return s.replace("`", "'").replace("@", "@\u200b").replace("#", "#\u200b")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--issue", required=True, type=int)
    ap.add_argument("--date", default=datetime.now(WITA).strftime("%Y-%m-%d"))
    ap.add_argument("--data", default=os.path.join(ROOT, "data"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    places = {os.path.splitext(os.path.basename(p))[0]: jsonio.read(p)
              for p in glob.glob(os.path.join(a.data, "places", "*.json"))}
    summary = {"issue": a.issue, "ok": False}
    try:
        body = open(a.body_file, encoding="utf-8").read()
        if len(body) > 20000:
            raise Rejected("Isi issue terlalu panjang.")
        form_name, fields = parse_body(body, load_forms())
        pid, rec, prev, changed, dropped, warnings, jenis = build(form_name, fields, a.issue, a.date, places)
    except Rejected as e:
        summary["error"] = str(e)
        jsonio.write(os.path.join(a.out, "summary.json"), summary)
        with open(os.path.join(a.out, "comment.md"), "w", encoding="utf-8") as fh:
            fh.write(f"Terima kasih atas usulannya. Usulan ini belum bisa diproses otomatis:\n\n> {e}\n\n"
                     "Silakan sunting issue ini (atau buat issue baru lewat formulir), lalu pengelola akan memprosesnya lagi.\n")
        print("REJECTED:", e)
        sys.exit(2)

    path = os.path.join(a.data, "places", pid + ".json")
    jsonio.write(path, rec)
    kind = "baru" if form_name == "Tambah tempat baru" else "koreksi"
    pin = "exact" if "lat" in changed else ("approx" if "approx_coords" in changed else "none")
    summary.update({"ok": True, "kind": kind, "jenis": jenis, "id": pid, "file": f"data/places/{pid}.json",
                    "changed": changed, "dropped_display": dropped, "pin": pin, "warnings": warnings,
                    "branch": f"data/issue-{a.issue}",
                    "title": f"Data: {'tempat baru' if kind == 'baru' else 'koreksi'} {pid} (issue #{a.issue})"})
    jsonio.write(os.path.join(a.out, "summary.json"), summary)

    diff = {k: {"sebelum": prev.get(k), "sesudah": rec.get(k)} for k in changed if not k.startswith("(")}
    pin_txt = {"exact": "titik dari tautan peta dengan koordinat tepat (tetap pin berongga \"Belum dicek\")",
               "approx": "hanya perkiraan (approx_coords), **tidak** dipasang sebagai pin",
               "none": "tidak ada titik baru" if kind == "koreksi" else "tanpa titik (muncul di \"Tanpa titik di peta\")"}[pin]
    body = [f"Dibuat otomatis dari issue #{a.issue}. Closes #{a.issue}", "",
            f"- Tempat: `{pid}` ({'baru' if kind == 'baru' else 'koreksi' + (' — ' + jenis if jenis != 'ubah' else '')})",
            f"- Berkas: `{summary['file']}`",
            f"- Status dipaksa: `needs-check` (sebelumnya: `{prev.get('status') or '-'}`)",
            f"- Lokasi: {pin_txt}"]
    if dropped:
        body.append(f"- Kolom tampilan dihapus supaya nilai lama tidak tampil: {', '.join('`'+d+'`' for d in dropped)}. Isi ulang setelah dicek.")
    for w in warnings:
        body.append(f"- Catatan: {w}")
    body += ["", "### Perubahan (teks dari kontributor, belum dicek)", "", "````text"]
    body += [f"{k}: {safe(v['sebelum'])} → {safe(v['sesudah'])}" for k, v in diff.items()] if kind == "koreksi" else \
            [f"{k}: {safe(v['sesudah'])}" for k, v in diff.items()]
    body += ["````", "", "### Cek pengelola sebelum merge",
             "- [ ] Buka setiap tautan sumber; pastikan info cocok dan sumbernya publik/resmi",
             "- [ ] Tidak ada data pribadi (nomor pribadi, cerita klien, nama kontributor)",
             "- [ ] Setiap nomor telepon/WA: buka tautan `contact_sources`; nomor itu memang dicantumkan sendiri oleh lembaga/pemiliknya (situs/akun resmi, profil bisnis milik pemilik), bukan nomor pribadi staf",
             "- [ ] Kategori, nama, alamat masuk akal; tidak duplikat dengan tempat lain",
             "- [ ] Lokasi: pin hanya jika koordinat tepat; approx_coords tidak pernah jadi pin",
             "- [ ] Status tetap `needs-check`. Mengubah ke `active` hanya oleh CODEOWNERS di PR terpisah setelah dicek (telepon/2 sumber)",
             "- [ ] Bila perlu, tambahkan kolom tampilan (`*_display`, `note_id`, `hours_normalized`) di commit pengelola"]
    with open(os.path.join(a.out, "pr_body.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(body) + "\n")
    with open(os.path.join(a.out, "comment.md"), "w", encoding="utf-8") as fh:
        fh.write(f"Terima kasih! Usulan ini sudah diubah menjadi pull request untuk diperiksa tim: __PR_URL__\n\n"
                 f"- Tempat: `{pid}`\n- Status di peta: **Belum dicek** sampai tim memeriksa sumbernya.\n- Lokasi: {pin_txt}\n"
                 + "".join(f"- Catatan: {w}\n" for w in warnings))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
