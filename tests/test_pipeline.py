#!/usr/bin/env python3
"""End-to-end tests for the submission pipeline: sample issue bodies -> issue_to_place.py ->
validate.py -> build-data.py, plus guard_pr.py on synthetic base/head pairs.
Each case runs against a throwaway copy of data/. Run: python3 tests/test_pipeline.py"""
import json, os, shutil, subprocess, sys, tempfile, unittest, warnings
warnings.simplefilter("ignore", ResourceWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ISSUES = os.path.join(ROOT, "tests", "issues")


def run(*args, **kw):
    return subprocess.run([PY, *args], capture_output=True, text=True, cwd=ROOT, **kw)


class Submission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        shutil.copytree(os.path.join(ROOT, "data"), self.data)
        self.out = os.path.join(self.tmp, "out")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def submit(self, name, issue=101):
        r = run("scripts/issue_to_place.py", "--body-file", os.path.join(ISSUES, name), "--issue", str(issue),
                "--date", "2026-10-31", "--data", self.data, "--out", self.out)
        summary = json.load(open(os.path.join(self.out, "summary.json"), encoding="utf-8"))
        return r, summary

    def place(self, pid):
        return json.load(open(os.path.join(self.data, "places", pid + ".json"), encoding="utf-8"))

    def assert_valid_and_builds(self):
        v = run("scripts/validate.py", "--data", self.data)
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
        b = run("scripts/build-data.py", "--src", self.data, "--out", os.path.join(self.tmp, "site-data"), "--strict")
        self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
        return json.load(open(os.path.join(self.tmp, "site-data", "places.json"), encoding="utf-8"))["places"]

    def rejected(self, name, needle):
        r, s = self.submit(name)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertFalse(s["ok"])
        self.assertIn(needle, s["error"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.data, "places"))),
                         sorted(os.listdir(os.path.join(ROOT, "data", "places"))), "rejected submission wrote a file")
        return s

    # --- valid ---
    def test_new_place_exact_pin(self):
        r, s = self.submit("01-tempat-baru.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((s["kind"], s["id"], s["pin"]), ("baru", "biro-psikologi-contoh-sejahtera", "exact"))
        p = self.place(s["id"])
        self.assertEqual(p["status"], "needs-check")
        self.assertEqual((p["lat"], p["lng"]), (-3.4421, 114.8153))
        self.assertIn("issue #101", p["coord_method"])
        self.assertEqual(p["contacts"], {"phone": "0511-470000", "whatsapp": "0812-0000-1111"})
        # consent policy: every number carries the owner-published source from the form
        self.assertEqual(sorted((c["number"], c["url"]) for c in p["contact_sources"]),
                         [("0511-470000", "https://example.org/biro-contoh/kontak"),
                          ("0812-0000-1111", "https://example.org/biro-contoh/kontak")])
        self.assertTrue(all("issue #101" in c["note"] for c in p["contact_sources"]))
        self.assertEqual(p["services"], ["konseling dewasa", "konseling pasangan", "tes minat bakat"])
        self.assertEqual(p["category"], "kesehatan-mental/biro-psikologi")
        self.assertEqual(p["sources"][0]["url"], "https://example.org/biro-contoh")
        built = {x["id"]: x for x in self.assert_valid_and_builds()}
        d = built[s["id"]]["_d"]
        self.assertTrue(d["needs_check"]); self.assertEqual(d["pin"], {"lat": -3.4421, "lng": 114.8153})
        body = open(os.path.join(self.out, "pr_body.md"), encoding="utf-8").read()
        self.assertIn("Closes #101", body)

    def test_new_place_viewport_link_is_never_a_pin(self):
        r, s = self.submit("02-tempat-baru-viewport.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(s["pin"], "approx")
        p = self.place(s["id"])
        self.assertIsNone(p["lat"]); self.assertIsNone(p["lng"])
        self.assertEqual(p["approx_coords"]["lat"], -3.4152)
        self.assertEqual((p["city"], p["kecamatan"], p["cost"]), ("Kabupaten Banjar", "Martapura", "Rp150.000/sesi"))
        built = {x["id"]: x for x in self.assert_valid_and_builds()}
        self.assertIsNone(built[s["id"]]["_d"]["pin"])
        self.assertTrue(built[s["id"]]["_d"]["regional"])

    def test_correction_downgrades_verified_and_drops_stale_display(self):
        before = self.place("traitcare-biro-psikologi-banjarbaru")
        self.assertEqual(before["status"], "active")
        r, s = self.submit("03-koreksi.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p = self.place("traitcare-biro-psikologi-banjarbaru")
        self.assertEqual(p["status"], "needs-check")
        self.assertTrue(p["hours"].startswith("Senin–Jumat 10.00–18.00"))
        self.assertNotIn("hours_normalized", p)          # old weekly table would show stale times
        self.assertEqual(s["changed"], ["hours"])
        self.assertEqual((p["lat"], p["lng"]), (before["lat"], before["lng"]))   # pin untouched
        self.assertEqual(p["address"], before["address"])
        self.assertIn("previous status: active", p["history"][-1]["what_changed"])
        self.assert_valid_and_builds()

    def test_closed_report_flags_but_never_deletes(self):
        r, s = self.submit("10-koreksi-tutup.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        p = self.place("birru-care-banjarbaru")
        self.assertEqual(p["status"], "needs-check")
        self.assertIn("tutup permanen", p["note_id"])
        self.assert_valid_and_builds()

    # --- rejected ---
    def test_malicious_body_rejected(self):
        self.rejected("04-berbahaya.md", "kode/markup")

    def test_no_source_url_rejected(self):
        self.rejected("05-tanpa-sumber.md", "minimal satu tautan")

    def test_missing_consent_rejected(self):
        self.rejected("06-tanpa-konfirmasi.md", "konfirmasi")

    def test_bad_phone_rejected(self):
        self.rejected("07-telepon-ngawur.md", "tidak terbaca sebagai nomor")

    def test_phone_without_consent_rejected(self):
        self.rejected("12-nomor-tanpa-persetujuan.md", "centang konfirmasi")

    def test_phone_without_source_link_rejected(self):
        self.rejected("13-nomor-tanpa-sumber.md", "wajib memuat tautan")

    def test_phone_in_other_field_rejected(self):
        self.rejected("14-nomor-di-kolom-lain.md", "hanya boleh ditulis")

    def test_uncited_phone_fails_validation(self):
        f = os.path.join(self.data, "places", "birru-care-banjarbaru.json")
        rec = json.load(open(f, encoding="utf-8"))
        self.assertTrue(rec["contact_sources"])
        rec["contact_sources"] = []
        json.dump(rec, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        v = run("scripts/validate.py", "--data", self.data)
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("has no contact_sources entry", v.stdout + v.stderr)

    def test_duplicate_new_place_rejected(self):
        self.rejected("08-duplikat.md", "sudah ada di peta")

    def test_unknown_place_correction_rejected(self):
        self.rejected("09-koreksi-tidak-ditemukan.md", "tidak ditemukan")

    def test_free_text_issue_rejected(self):
        self.rejected("11-bukan-formulir.md", "tidak dikenali")


class MapLinks(unittest.TestCase):
    def test_kinds(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from issue_to_place import map_coords
        cases = {
            "https://www.google.com/maps/place/X/@-3.45,114.82,17z/data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d-3.4512345!4d114.8234567": ("exact", -3.4512345),
            "https://www.google.com/maps/search/?api=1&query=-3.4512,114.8234": ("exact", -3.4512),
            "https://www.google.com/maps/@-3.4512,114.8234,17z": ("viewport", -3.4512),
            "https://www.openstreetmap.org/?mlat=-3.4512&mlon=114.8234": ("exact", -3.4512),
            "https://www.openstreetmap.org/#map=17/-3.4512/114.8234": ("viewport", -3.4512),
            "geo:-3.4512,114.8234": ("exact", -3.4512),
            "https://maps.app.goo.gl/AbCdEf": ("none", None),
            "https://evil.example/maps?query=-3.45,114.82": ("none", None),
            "": ("none", None),
        }
        for url, (kind, lat) in cases.items():
            k, la, _, _ = map_coords(url)
            self.assertEqual((k, la), (kind, lat), url)


class Guard(unittest.TestCase):
    """guard_pr.py compares a base and a head data dir."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = os.path.join(self.tmp, "base"); self.head = os.path.join(self.tmp, "head")
        for d in (self.base, self.head):
            shutil.copytree(os.path.join(ROOT, "data"), d)
        self.owners = os.path.join(self.tmp, "CODEOWNERS")
        open(self.owners, "w").write("* @maintainer-a\n/data/places/ @maintainer-a @maintainer-b\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def edit(self, pid, **changes):
        f = os.path.join(self.head, "places", pid + ".json")
        rec = json.load(open(f, encoding="utf-8")); rec.update(changes)
        json.dump(rec, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def guard(self, author):
        return run("scripts/guard_pr.py", "--base", self.base, "--head", self.head, "--author", author, "--codeowners", self.owners)

    def test_sync_state_is_code_owner_only(self):
        sp = os.path.join(self.head, ".store-sync.json")
        st = json.load(open(sp, encoding="utf-8")); st["bnn-kota-banjarbaru"]["bpjs_info"] = "0" * 64
        json.dump(st, open(sp, "w", encoding="utf-8"))
        g = self.guard("random-contributor")
        self.assertNotEqual(g.returncode, 0)
        self.assertIn(".store-sync.json changed by @random-contributor", g.stdout)
        self.assertEqual(self.guard("maintainer-a").returncode, 0)

    def test_contributor_cannot_flip_to_active(self):
        self.edit("biro-sagraha-psikologi-banjarbaru", status="active")
        r = self.guard("random-contributor")
        self.assertEqual(r.returncode, 1, r.stdout); self.assertIn("needs-check -> active", r.stdout)

    def test_codeowner_can_flip_to_active(self):
        self.edit("biro-sagraha-psikologi-banjarbaru", status="active")
        self.assertEqual(self.guard("maintainer-b").returncode, 0)

    def test_bot_cannot_add_active_place(self):
        rec = json.load(open(os.path.join(self.head, "places", "talenta-aditama.json")))
        rec.update(id="tempat-palsu", status="active")
        json.dump(rec, open(os.path.join(self.head, "places", "tempat-palsu.json"), "w"))
        r = self.guard("github-actions[bot]")
        self.assertEqual(r.returncode, 1, r.stdout); self.assertIn("new place with status active", r.stdout)

    def test_pin_change_needs_method_and_new_sources_need_urls(self):
        self.edit("birru-care-banjarbaru", lat=-3.44, lng=114.82)
        r = self.guard("random-contributor")
        self.assertEqual(r.returncode, 1); self.assertIn("coord_method", r.stdout)

    def test_pin_from_approx_is_blocked(self):
        rec = json.load(open(os.path.join(self.head, "places", "birru-care-banjarbaru.json")))
        ap = rec["approx_coords"]
        self.edit("birru-care-banjarbaru", lat=ap["lat"], lng=ap["lng"], coord_method="copied")
        r = self.guard("maintainer-a")
        self.assertEqual(r.returncode, 1); self.assertIn("approx_coords", r.stdout)

    def test_new_phone_needs_cited_source(self):
        rec = json.load(open(os.path.join(self.head, "places", "traitcare-biro-psikologi-banjarbaru.json"), encoding="utf-8"))
        contacts = dict(rec.get("contacts") or {}, phone="0511-470001")
        self.edit("traitcare-biro-psikologi-banjarbaru", contacts=contacts)
        r = self.guard("maintainer-a")
        self.assertEqual(r.returncode, 1, r.stdout); self.assertIn("must cite a public http(s) source", r.stdout)
        cs = (rec.get("contact_sources") or []) + [{"number": "0511-470001", "url": "https://example.org/traitcare/kontak"}]
        self.edit("traitcare-biro-psikologi-banjarbaru", contacts=contacts, contact_sources=cs)
        r = self.guard("maintainer-a")
        self.assertNotIn("must cite", r.stdout)

    def test_unchanged_passes(self):
        self.assertEqual(self.guard("random-contributor").returncode, 0)


class TmpData(unittest.TestCase):
    """Base: a throwaway copy of data/ plus helpers (edit a place, validate, build)."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = os.path.join(self.tmp, "data")
        shutil.copytree(os.path.join(ROOT, "data"), self.data)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def path(self, pid, data=None):
        return os.path.join(data or self.data, "places", pid + ".json")

    def edit(self, pid, fn, data=None):
        f = self.path(pid, data)
        rec = json.load(open(f, encoding="utf-8")); fn(rec)
        json.dump(rec, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def validate(self):
        return run("scripts/validate.py", "--data", self.data)

    def build(self):
        out = os.path.join(self.tmp, "site-data")
        b = run("scripts/build-data.py", "--src", self.data, "--out", out, "--strict")
        return b, out


class BpjsGratis(TmpData):
    """SCHEMA v4 bpjs_info + v5 biaya_gratis: schema, privacy rules, field sync, and the site tag."""
    def test_repo_data_has_both_fields_and_no_internal_notes(self):
        counts = {}
        for f in sorted(os.listdir(os.path.join(ROOT, "data", "places"))):
            text = open(os.path.join(ROOT, "data", "places", f), encoding="utf-8").read()
            self.assertNotIn("internal", text.lower(), f)
            rec = json.loads(text)
            self.assertIn("bpjs_info", rec, f); self.assertIn("biaya_gratis", rec, f)
            counts[rec["biaya_gratis"]["status"]] = counts.get(rec["biaya_gratis"]["status"], 0) + 1
        self.assertEqual(counts, {"ya": 1, "bersyarat": 4, "tidak": 9, "belum_diketahui": 19})

    def test_internal_note_is_rejected(self):
        self.edit("rsd-idaman-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_internal="evidence"))
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("bpjs_info.catatan_internal", v.stdout)
        self.assertIn("must not be in the public repo", v.stdout)

    def test_invalid_status_is_rejected_by_the_field_schema(self):
        self.edit("bnn-kota-banjarbaru", lambda r: r["biaya_gratis"].update(status="gratis"))
        self.edit("rsd-idaman-kota-banjarbaru", lambda r: r["bpjs_info"].update(status="maybe"))
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("schema: biaya_gratis/status", v.stdout)
        self.assertIn("schema: bpjs_info/status", v.stdout)

    def test_no_phone_in_display_fields_even_when_cited(self):
        def add(r):
            r["biaya_gratis"]["syarat_display"] += " Info: 0812-0000-1111."
            r["contact_sources"] = (r.get("contact_sources") or []) + [{"number": "0812-0000-1111", "url": "https://example.org/kontak"}]
        self.edit("posbakum-pengadilan-agama-banjarbaru", add)
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("no phone numbers in biaya_gratis", v.stdout)

    def test_site_tag_comes_only_from_biaya_gratis_status(self):
        def free_text(r):
            r["cost"] = "Gratis"
            r["bpjs_info"]["catatan_display"] = "Layanan ini gratis."
            r["biaya_gratis"] = {"status": "tidak", "syarat_display": "Bayar sesuai tarif."}
        self.edit("klinik-psikologi-fusfa", free_text)
        b, out = self.build()
        self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
        text = "".join(open(os.path.join(out, n), encoding="utf-8").read() for n in ("places.json", "hotlines.json", "data.js", "build-report.json"))
        self.assertNotIn("catatan_internal", text)
        places = {p["id"]: p for p in json.loads(open(os.path.join(out, "places.json"), encoding="utf-8").read())["places"]}
        for p in places.values():
            self.assertFalse(any("gratis" in t.lower() for t in p["_d"]["tags"]), p["id"])
            self.assertNotIn("basis", p.get("biaya_gratis") or {}, p["id"])
        self.assertEqual(places["klinik-psikologi-fusfa"]["_d"]["gratis"]["tag"], None)
        self.assertEqual(places["posbankum-kelurahan-kota-banjarbaru"]["_d"]["gratis"]["tag"], "Gratis")
        bnn = places["bnn-kota-banjarbaru"]["_d"]["gratis"]
        self.assertEqual((bnn["tag"], bnn["recheck"]), ("Gratis bersyarat", True))
        tagged = sorted(i for i, p in places.items() if p["_d"]["gratis"] and p["_d"]["gratis"]["tag"])
        self.assertEqual(tagged, ["bnn-kota-banjarbaru", "posbakum-pengadilan-agama-banjarbaru", "posbakum-pengadilan-negeri-banjarbaru",
                                  "posbakumadin-banjarbaru", "posbankum-kelurahan-kota-banjarbaru"])
        # Puspaga Provinsi: the 2019 source never says gratis -> belum_diketahui, no tag, recheck kept (2026-11-01)
        pp = places["puspaga-provinsi-kalimantan-selatan"]["_d"]["gratis"]
        self.assertEqual((pp["status"], pp["tag"], pp["recheck"]), ("belum_diketahui", None, True))
        # BPJS acceptance never implies gratis
        self.assertTrue(all(not (p["_d"]["gratis"] or {}).get("tag") for p in places.values()
                            if (p["_d"]["bpjs"] or {}).get("accepts") and (p.get("biaya_gratis") or {}).get("status") not in ("ya", "bersyarat")))

    def test_build_refuses_to_ship_internal_notes(self):
        self.edit("talenta-aditama", lambda r: r.update(catatan_internal="x"))
        b, out = self.build()
        self.assertNotEqual(b.returncode, 0)
        self.assertIn("catatan_internal would ship", b.stderr)
        self.assertFalse(os.path.exists(out))

    def test_field_sync_keeps_the_consent_scrub_and_strips_internal_keys(self):
        arc = os.path.join(self.tmp, "archive")
        shutil.copytree(os.path.join(ROOT, "data"), arc)
        pid = "biro-sagraha-psikologi-banjarbaru"
        before = json.load(open(self.path(pid), encoding="utf-8"))
        def archive_side(r):
            r["contacts"] = {"phone": "0812-0000-2222"}           # an unconsented archive number
            r["bpjs_info"] = {"status": "ya", "catatan_display": "Terima BPJS.", "catatan_internal": "x", "sources": [{"url": "https://example.org", "note_internal": "y"}]}
            r["biaya_gratis"] = {"status": "bersyarat", "syarat_display": "Gratis untuk warga.", "basis": "inferred", "perlu_cek_ulang": False}
        self.edit(pid, archive_side, data=arc)
        new = json.load(open(self.path(pid, arc), encoding="utf-8")); new.update(id="tempat-baru-arsip")
        json.dump(new, open(self.path("tempat-baru-arsip", arc), "w", encoding="utf-8"))
        r = run("scripts/migrate-from-store.py", "--src", arc, "--fields", "bpjs_info,biaya_gratis", "--data", self.data)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SKIPPED (new place", r.stdout)
        self.assertFalse(os.path.exists(self.path("tempat-baru-arsip")))
        after = json.load(open(self.path(pid), encoding="utf-8"))
        self.assertEqual(after["contacts"], before["contacts"])
        self.assertEqual(after["bpjs_info"], {"status": "ya", "catatan_display": "Terima BPJS.", "sources": [{"url": "https://example.org"}]})
        self.assertEqual(after["biaya_gratis"]["status"], "bersyarat")
        self.assertEqual({k: after[k] for k in after if k not in ("bpjs_info", "biaya_gratis")},
                         {k: before[k] for k in before if k not in ("bpjs_info", "biaya_gratis")})
        self.assertEqual(self.validate().returncode, 0)



class PrivacyGuards(TmpData):
    """QA re-check 2026-11-01: R-B1 (field allowlist + pre-write checks), R-M1 (folded internal keys),
    R-M2 (strict phone scan), R-M3 (hand edits kept), R-m4..m8 and --strict before writing."""
    SAGRAHA = "biro-sagraha-psikologi-banjarbaru"

    def archive(self):
        arc = os.path.join(self.tmp, "archive")
        if not os.path.exists(arc):
            shutil.copytree(os.path.join(ROOT, "data"), arc)
        return arc

    def tree(self):
        out = {}
        for dp, _, fs in os.walk(self.data):
            for f in fs:
                out[os.path.relpath(os.path.join(dp, f), self.data)] = open(os.path.join(dp, f), "rb").read()
        return out

    def sync(self, *extra, fields="bpjs_info,biaya_gratis"):
        return run("scripts/migrate-from-store.py", "--src", self.archive(), "--fields", fields, "--data", self.data, *extra)

    # ---- R-B1 ----
    def test_qa_attack_contacts_booking_sources_is_refused_and_writes_nothing(self):
        arc = self.archive()
        def attack(r):
            r["contacts"] = {"phone": "0812-0000-2222", "email": "orang.pribadi@gmail.com"}
            r["booking_display"] = "WA 0812 0000 3333"
            r["sources"] = (r.get("sources") or []) + [{"url": "https://wa.me/6281200004444", "note": "kontak pribadi"}]
        for pid in ("bnn-kota-banjarbaru", self.SAGRAHA, "talenta-aditama"):
            self.edit(pid, attack, data=arc)
        before = self.tree()
        for fields in ("contacts,booking_display,sources", "bpjs_info,contacts", "cost", "sources"):
            r = self.sync(fields=fields)
            self.assertNotEqual(r.returncode, 0, fields)
            self.assertIn("only bpjs_info, biaya_gratis may be synced", r.stderr)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.validate().returncode, 0)

    def test_phone_email_or_internal_key_in_synced_fields_aborts_the_whole_run(self):
        cases = {
            "spaced": lambda r: r["bpjs_info"].update(catatan_display="Daftar via 62 812 3456 7890."),
            "wa_prefix": lambda r: r["biaya_gratis"].update(syarat_display="Hubungi WA0812-3456-7890."),
            "note": lambda r: r["biaya_gratis"].update(sources=[{"url": "https://example.org/a", "note": "SKTM,08123456789"}]),
            "wa_url": lambda r: r["bpjs_info"].update(sources=[{"url": "https://wa.me/6281234567890"}]),
            "tel_url": lambda r: r["bpjs_info"].update(sources=[{"url": "tel:+62-812-3456-7890"}]),
            "email": lambda r: r["biaya_gratis"].update(syarat_display="Tanya ke admin.posbakum@gmail.com."),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                shutil.rmtree(os.path.join(self.tmp, "archive"), ignore_errors=True)
                arc = self.archive()
                # an innocent change elsewhere must not be written either (collect first, write second)
                self.edit("talenta-aditama", lambda r: r["bpjs_info"].update(catatan_display="Catatan baru yang sah."), data=arc)
                self.edit("posbakum-pengadilan-agama-banjarbaru", fn, data=arc)
                before = self.tree()
                r = self.sync()
                self.assertNotEqual(r.returncode, 0, name)
                self.assertIn("nothing written", r.stderr)
                self.assertEqual(self.tree(), before, name)

    def test_internal_keys_are_stripped_with_folding_and_no_husks(self):
        arc = self.archive()
        def side(r):
            r["bpjs_info"] = {"status": "ya", "catatan_display": "Terima BPJS.", "NOTE_INTERNAL": "a", "catatan-internal": "b",
                              "catatan internal": "c", "catatan_\u0131nternal": "d",
                              "sources": [{"url": "https://example.org"}, {"internal_note": "only private"}], "checked": "2026-11-01"}
        self.edit(self.SAGRAHA, side, data=arc)
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = json.load(open(self.path(self.SAGRAHA), encoding="utf-8"))
        self.assertEqual(after["bpjs_info"], {"status": "ya", "catatan_display": "Terima BPJS.", "sources": [{"url": "https://example.org"}], "checked": "2026-11-01"})
        self.assertEqual(self.validate().returncode, 0)

    # ---- R-M3 ----
    def test_hand_edit_is_kept_without_force_and_never_popped(self):
        arc = self.archive()
        hand = "Koreksi tangan di repo: rehabilitasi gratis, bawa KTP."
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display=hand))
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Versi arsip yang baru."), data=arc)
        self.edit("talenta-aditama", lambda r: r.pop("biaya_gratis"), data=arc)
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("KEPT (differs from the last sync and from the archive, use --force): bnn-kota-banjarbaru.bpjs_info", r.stdout)
        self.assertIn("KEPT (archive has no biaya_gratis; use --force to remove): talenta-aditama.biaya_gratis", r.stdout)
        self.assertEqual(json.load(open(self.path("bnn-kota-banjarbaru"), encoding="utf-8"))["bpjs_info"]["catatan_display"], hand)
        self.assertIn("biaya_gratis", json.load(open(self.path("talenta-aditama"), encoding="utf-8")))
        r = self.sync("--force")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OVERWRITE (--force) bnn-kota-banjarbaru.bpjs_info", r.stdout)
        self.assertEqual(json.load(open(self.path("bnn-kota-banjarbaru"), encoding="utf-8"))["bpjs_info"]["catatan_display"], "Versi arsip yang baru.")
        self.assertNotIn("biaya_gratis", json.load(open(self.path("talenta-aditama"), encoding="utf-8")))

    def test_unchanged_since_last_sync_is_updated_and_only_limits_the_run(self):
        arc = self.archive()
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Versi arsip yang baru."), data=arc)
        self.edit("talenta-aditama", lambda r: r["bpjs_info"].update(catatan_display="Juga baru."), data=arc)
        r = self.sync("--only", "bnn-kota-banjarbaru")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("UPDATE bnn-kota-banjarbaru.bpjs_info", r.stdout)
        self.assertEqual(json.load(open(self.path("bnn-kota-banjarbaru"), encoding="utf-8"))["bpjs_info"]["catatan_display"], "Versi arsip yang baru.")
        self.assertNotEqual(json.load(open(self.path("talenta-aditama"), encoding="utf-8"))["bpjs_info"]["catatan_display"], "Juga baru.")

    # ---- R-m7 ----
    def test_repo_only_place_is_reported(self):
        arc = self.archive()
        os.remove(self.path("talenta-aditama", arc))
        r = self.sync()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("NOT IN STORE: talenta-aditama", r.stdout)

    # ---- R-M2 / R-m4 ----
    def test_phone_detector_formats_and_no_false_positives(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import phones
        hits = ["62 812 3456 7890", "62-812-3456-7890", "WA0812-3456-7890", "SKTM,08123456789", "0 8 1 2 3 4 5 6 7 8 9 0",
                "08 12 34 56 78 90", "0812\u20133456\u20137890", "\uff10\uff18\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19\uff10",
                "+\uff16\uff12 812 3456 7890", "https://wa.me/6281234567890", "tel:+62-812-3456-7890", "Telp 0812 3456 7890",
                # QA R2-M1: dotted / coloned groups that only look like clock times
                "08.12.3456.7890", "0 8.12 34.56 78.90", "08.12.34.56.78.90", "08:12 3456 7890", "+62 8.12 34.56 78.90",
                # QA R2-m1: landlines with a bare 62 prefix or spaced-out digits
                "62-511-4772123", "0 5 1 1 4 7 7 2 1 2 3", "(0511) 123456", "0511.4772123", "021-5551234",
                # QA R3-M1: a clock time in context must not hide the first group of a phone
                "jam 08.12 3456 7890", "Hubungi jam 08.12 3456 7890", "pukul 08.12-34.56 78.90 WITA",
                "08.00\u201308.12 3456 7890", "08.12 WITA 3456 7890", "08.12 - 13.45 67 89 0", "08.12 s.d. 13.45 6789",
                "08.00-08.12-34.56-78.90", "jam 08.12/3456/7890", "jam 08.12 (3456) 7890", "jam 08.12 34.56 78.90",
                # QA R3-M1 note: a comma inside a digit run is a separator too
                "0812, 3456 7890", "08.12,3456,7890", "jam 08.00, 0812 3456 7890"]
        for t in hits:
            self.assertTrue(phones.find_strict(t), t)
        for t in ("Rp290.000", "Rp 1.500.000", "tahun 2019-2024", "UU No. 35 Tahun 2014", "NIK 6372041234567890", "2026-11-01",
                  "Senin\u2013Jumat 08.00\u201316.00, Sabtu 08.00 - 12.00", "NIP 198012312005011001",
                  # real clock times stay masked (R2-M1): ranges, zone suffix, jam/pukul
                  "08.00 - 12.00", "jam 08.00 WITA", "08.00 - 12.00 08.00", "8:30-15:30", "08.00\u201316.00 WITA",
                  "pukul 07.30 s.d. 14.00 WIB", "jam 08.00-12.00 dan 13.00-15.00", "Rp 08.000", "Rp 50.000 - Rp 100.000",
                  "jam 08.00 - 12.00 WITA, 13.00 - 15.00 WITA", "Senin 08.00-12.00, 2024", "08.00-14.00 (Senin-Kamis), 08.00-11.00 (Jumat)",
                  # comma lists that must not become a number (R3-M1)
                  "Rp 50.000, 75.000, 100.000", "Rp 25.000, 50.000 dan 100.000", "tahun 2019, 2020, 2021", "2019, 2020, 2021, 2022, 2023",
                  "NIK 6372012345678901, 6271012345678902", "01-11-2026, 02-11-2026", "01, 02, 03, 04, 05, 06", "0, 5, 10, 15 km",
                  "https://bnn.go.id/konten/unggahan/2024/05/Rehabilitasi_Standar-Pelayanan.pdf"):
            self.assertEqual(phones.find_strict(t), [], t)
        self.assertEqual(phones.find("https://wa.me/6281234567890"), ["6281234567890"])   # consent check sees wa.me links too

    def test_validate_rejects_phone_email_and_non_http_urls_in_display_fields(self):
        self.edit("posbakum-pengadilan-agama-banjarbaru", lambda r: r["biaya_gratis"].update(syarat_display="Tanya 62 812 3456 7890 atau admin@posbakum.id."))
        self.edit("rsd-idaman-kota-banjarbaru", lambda r: r["bpjs_info"].update(sources=[{"url": "tel:0812"}, {"url": "https://wa.me/6281234567890"}, {"url": "MC Kalsel 2019"}]))
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("phone 6281234567890 in biaya_gratis.syarat_display", v.stdout)
        self.assertIn("email admin@posbakum.id in biaya_gratis.syarat_display", v.stdout)
        for i in range(3):
            self.assertIn(f"schema: bpjs_info/sources/{i}", v.stdout)
        self.assertIn("phone 6281234567890 in bpjs_info.sources[1].url", v.stdout)

    # ---- R-M1 / R-m5 ----
    def test_folded_internal_keys_fail_validate_and_build(self):
        for key in ("NOTE_INTERNAL", "catatan-internal", "catatan internal", "catatan_\u0131nternal"):
            with self.subTest(key):
                self.edit("talenta-aditama", lambda r: r.update(services_meta=[{key: "x"}]))
                v = self.validate()
                self.assertNotEqual(v.returncode, 0)
                self.assertIn("must not be in the public repo", v.stdout)
                b, out = self.build()
                self.assertNotEqual(b.returncode, 0)
                self.assertIn("key named *internal* would ship", b.stderr)
                self.assertFalse(os.path.exists(out))
                self.edit("talenta-aditama", lambda r: r.pop("services_meta"))

    def test_hotlines_nested_internal_key_is_rejected(self):
        f = os.path.join(self.data, "hotlines.json")
        h = json.load(open(f, encoding="utf-8"))
        L = h if isinstance(h, list) else h["hotlines"]
        L[0]["contacts"] = dict(L[0].get("contacts") or {}, **{"NOTE_INTERNAL": "x"})
        json.dump(h, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("NOTE_INTERNAL: keys containing 'internal'", v.stdout)

    # ---- R-m3 / R-m6 / --strict ----
    def test_basis_and_empty_sources_do_not_ship(self):
        self.edit("rsd-idaman-kota-banjarbaru", lambda r: r["bpjs_info"].update(sources=[{"url": "https://example.org"}]))
        b, out = self.build()
        self.assertEqual(b.returncode, 0, b.stderr)
        places = json.load(open(os.path.join(out, "places.json"), encoding="utf-8"))["places"]
        for p in places:
            self.assertNotIn("basis", p.get("bpjs_info") or {}, p["id"])
            self.assertNotIn("basis", p.get("biaya_gratis") or {}, p["id"])
            for fld in ("bpjs_info", "biaya_gratis"):
                self.assertNotIn({}, (p.get(fld) or {}).get("sources") or [], p["id"])

    def test_strict_exits_before_writing(self):
        self.edit("talenta-aditama", lambda r: r.update(name=None))
        b, out = self.build()
        self.assertNotEqual(b.returncode, 0)
        self.assertIn("nothing written", b.stderr)
        self.assertFalse(os.path.exists(out))

    # ---- R-m8 ----
    def test_ui_fixture_matches_data(self):
        """CI builds the UI check from tests/fixtures/data; it must be the same as data/ so real data is exercised."""
        fx = os.path.join(ROOT, "tests", "fixtures", "data")
        names = lambda d: sorted(os.listdir(os.path.join(d, "places")))
        self.assertEqual(names(fx), names(os.path.join(ROOT, "data")))
        for rel in [os.path.join("places", n) for n in names(fx)] + ["hotlines.json", ".store-sync.json"]:
            self.assertEqual(open(os.path.join(fx, rel), "rb").read(), open(os.path.join(ROOT, "data", rel), "rb").read(),
                             f"tests/fixtures/data/{rel} differs from data/{rel}: re-sync the fixture (see tests/fixtures/README.md)")


class QaRecheck2(TmpData):
    """QA re-check 2 (c935c9d): R2-M1 clock masking, R2-M2 key shape, R2-M3 --initial-import, R2-m1..m6."""
    def archive(self):
        arc = os.path.join(self.tmp, "archive")
        if not os.path.exists(arc):
            shutil.copytree(os.path.join(ROOT, "data"), arc)
        return arc

    def tree(self):
        out = {}
        for dp, _, fs in os.walk(self.data):
            for f in fs:
                out[os.path.relpath(os.path.join(dp, f), self.data)] = open(os.path.join(dp, f), "rb").read()
        return out

    def migrate(self, *args):
        return run("scripts/migrate-from-store.py", "--src", self.archive(), "--data", self.data, *args)

    # ---- R2-M1 end to end: a clock-shaped phone no longer reaches the repo ----
    def test_clock_shaped_phone_is_refused_by_sync_and_validate(self):
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Hubungi 08.12.3456.7890"), data=self.archive())
        self.edit("talenta-aditama", lambda r: r["biaya_gratis"].update(syarat_display="WA 0 8.12 34.56 78.90"), data=self.archive())
        before = self.tree()
        r = self.migrate("--fields", "bpjs_info,biaya_gratis")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("phone 6281234567890 in bpjs_info.catatan_display", r.stderr)
        self.assertIn("phone 6281234567890 in biaya_gratis.syarat_display", r.stderr)
        self.assertEqual(self.tree(), before)
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Buka jam 08.00 WITA, Senin 08.00 - 12.00 08.00."))
        self.assertEqual(self.validate().returncode, 0)   # real opening hours are not a phone
        # R3-M1: QA's end-to-end case - a time in context in front of the rest of the number
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Hubungi jam 08.12 3456 7890"))
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("6281234567890", v.stdout)   # validate is the CI gate for phones; build only guards keys
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Buka 08.00 - 12.00 WITA."))
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Hubungi jam 08.12 3456 7890"), data=self.archive())
        before = self.tree()
        r = self.migrate("--fields", "bpjs_info,biaya_gratis", "--only", "bnn-kota-banjarbaru")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("phone 6281234567890 in bpjs_info.catatan_display", r.stderr)
        self.assertEqual(self.tree(), before)

    # ---- R2-m3: nothing about a refused run is echoed ----
    def test_refused_sync_prints_no_update_or_diff(self):
        self.edit("talenta-aditama", lambda r: r["bpjs_info"].update(catatan_display="Perubahan yang sah."), data=self.archive())
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update(catatan_display="Telp 0812 9999 8888"), data=self.archive())
        r = self.migrate("--fields", "bpjs_info,biaya_gratis")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("UPDATE", r.stdout)
        self.assertNotIn("Perubahan yang sah", r.stdout)
        self.assertNotIn("0812 9999 8888", r.stdout + r.stderr)   # only the normalised number is named, never the text
        ok = self.migrate("--fields", "bpjs_info,biaya_gratis", "--only", "talenta-aditama")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("UPDATE talenta-aditama.bpjs_info", ok.stdout)
        self.assertIn("bpjs_info.catatan_display:", ok.stdout)

    # ---- R2-m2 ----
    def test_obfuscated_email_is_caught_and_bank_numbers_are_a_documented_false_positive(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import leaks, phones
        for t in ("nama [at] gmail [dot] com", "nama (at) gmail.com", "nama @ gmail . com", "x.y [at] kemkes [dot] go [dot] id"):
            self.assertTrue(leaks.emails(t), t)
        for t in ("IG @dp3akb.kalsel", "bertemu di (at) kantor", "Datang jam 8. Bawa KTP."):
            self.assertEqual(leaks.emails(t), [], t)
        self.assertEqual(phones.find_strict("No. rek 0812345678"), ["62812345678"])   # CONTRIBUTING.md: known, accepted
        self.edit("posbakum-pengadilan-agama-banjarbaru", lambda r: r["biaya_gratis"].update(syarat_display="Tanya nama [at] gmail [dot] com."))
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("email nama [at] gmail [dot] com in biaya_gratis.syarat_display", v.stdout)

    # ---- R2-M2 ----
    def test_existing_keys_are_all_plain_identifiers(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import leaks
        for d in (os.path.join(ROOT, "data"), os.path.join(ROOT, "tests", "fixtures", "data")):
            for f in sorted(os.listdir(os.path.join(d, "places"))) + ["../hotlines.json"]:
                obj = json.load(open(os.path.join(d, "places", f), encoding="utf-8"))
                self.assertEqual(list(leaks.bad_keys(obj)), [], f)

    def test_hidden_character_keys_fail_validate_build_and_sync(self):
        keys = {"zero-width": "catatan_inter\u200bnal", "soft hyphen": "catatan_inter\u00adnal", "word joiner": "catatan_inter\u2060nal",
                "BOM": "\ufeffcatatan_internal", "Cyrillic i": "catatan_\u0456nternal", "small caps": "\u026a\u0274\u1d1b\u1d07\u0280\u0274\u1d00\u029f"}
        hp = os.path.join(self.data, "hotlines.json")
        pristine = open(hp, "rb").read()
        for name, key in keys.items():
            for where in ("place", "hotlines"):
                with self.subTest(f"{name} in {where}"):
                    if where == "place":
                        self.edit("talenta-aditama", lambda r: r.update(services_meta=[{key: "SECRET"}]))
                    else:
                        h = json.loads(pristine); L = h if isinstance(h, list) else h["hotlines"]; L[0][key] = "SECRET"
                        json.dump(h, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                    try:
                        v = self.validate()
                        self.assertNotEqual(v.returncode, 0)
                        self.assertIn("keys must be plain ASCII identifiers", v.stdout)
                        b, out = self.build()
                        self.assertNotEqual(b.returncode, 0)
                        # the BOM key still spells catatan_internal, so the text guard fires first
                        self.assertRegex(b.stderr, r"hidden/non-ASCII characters \(|catatan_internal would ship")
                        self.assertIn("nothing written", b.stderr)
                        self.assertFalse(os.path.exists(out))
                    finally:
                        if where == "place":
                            self.edit("talenta-aditama", lambda r: r.pop("services_meta", None))
                        else:
                            open(hp, "wb").write(pristine)
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update({"catatan_inter\u200bnal": "SECRET"}), data=self.archive())
        before = self.tree()
        r = self.migrate("--fields", "bpjs_info,biaya_gratis")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not a plain ASCII identifier", r.stderr)
        self.assertEqual(self.tree(), before)

    def test_build_and_validate_share_one_key_rule(self):
        """Parity (QA R2-M2): build-data.py has no copy of the rule; it calls scripts/leaks.py (v2 ships a
        byte-identical leaks.py next to its build-data.py)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_data", os.path.join(ROOT, "scripts", "build-data.py"))
        bd = importlib.util.module_from_spec(spec); spec.loader.exec_module(bd)
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import leaks
        self.assertFalse(hasattr(bd, "is_internal_key") or hasattr(bd, "internal_key_paths"))
        self.assertEqual(os.path.realpath(bd.leaks.__file__), os.path.realpath(leaks.__file__))
        sample = {k: 1 for k in ("status", "catatan_internal", "NOTE_INTERNAL", "catatan-internal", "catatan internal", "catatan_\u0131nternal",
                                 "catatan_inter\u200bnal", "catatan_\u0456nternal", "brand_link_Al-Birru", "kesehatan-mental",
                                 "catatan_inter_nal", "inter-nal", "In-Ter_Nal", "intern_al", "i_n_t_e_r_n_a_l", "international", "catatan_intrnal")}
        self.assertEqual(bd.leaks.leaked_key_paths(sample), leaks.leaked_key_paths(sample))
        self.assertEqual(sorted(leaks.leaked_key_paths(sample)), sorted([
            "catatan_internal", "NOTE_INTERNAL", "catatan-internal",
            "catatan_inter_nal", "inter-nal", "In-Ter_Nal", "intern_al", "i_n_t_e_r_n_a_l",
            ascii("catatan internal"), ascii("catatan_\u0131nternal"), ascii("catatan_inter\u200bnal"), ascii("catatan_\u0456nternal")]))

    def test_split_internal_keys_fail_validate_build_and_sync(self):
        """QA R3-M2: "internal" split by _ or - is still internal (place root, nested, hotlines)."""
        hp = os.path.join(self.data, "hotlines.json")
        pristine = open(hp, "rb").read()
        for where, key in (("hotlines", "inter-nal"), ("place", "catatan_inter_nal"), ("nested", "In-Ter_Nal"),
                           ("nested", "intern_al"), ("hotlines", "i_n_t_e_r_n_a_l")):
            with self.subTest(f"{key} in {where}"):
                try:
                    if where == "hotlines":
                        h = json.loads(pristine); L = h if isinstance(h, list) else h["hotlines"]; L[0][key] = "SECRET"
                        json.dump(h, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                    elif where == "place":
                        self.edit("talenta-aditama", lambda r: r.update({key: "SECRET"}))
                    else:
                        self.edit("talenta-aditama", lambda r: r.update(services_meta=[{key: "SECRET"}]))
                    v = self.validate()
                    self.assertNotEqual(v.returncode, 0)
                    self.assertIn("internal", v.stdout)
                    b, out = self.build()
                    self.assertNotEqual(b.returncode, 0)
                    self.assertIn("a key named *internal* would ship", b.stderr)
                    self.assertFalse(os.path.exists(out))
                finally:
                    open(hp, "wb").write(pristine)
                    self.edit("talenta-aditama", lambda r: (r.pop(key, None), r.pop("services_meta", None)))
        # migrate strips it like catatan_internal
        self.edit("bnn-kota-banjarbaru", lambda r: r["bpjs_info"].update({"catatan_inter_nal": "SECRET"}), data=self.archive())
        r = self.migrate("--fields", "bpjs_info,biaya_gratis", "--only", "bnn-kota-banjarbaru")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("SECRET", open(self.path("bnn-kota-banjarbaru"), encoding="utf-8").read())

    def test_only_existing_internal_key_is_catatan_internal(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import leaks
        keys = set()
        def walk(v):
            if isinstance(v, dict):
                keys.update(v); [walk(x) for x in v.values()]
            elif isinstance(v, list):
                [walk(x) for x in v]
        for d in (os.path.join(ROOT, "data"), os.path.join(ROOT, "tests", "fixtures", "data")):
            walk(json.load(open(os.path.join(d, "hotlines.json"), encoding="utf-8")))
            for f in os.listdir(os.path.join(d, "places")):
                walk(json.load(open(os.path.join(d, "places", f), encoding="utf-8")))
        self.assertEqual({k for k in keys if leaks.is_internal_key(k)} - {"catatan_internal"}, set())

    # ---- R2-M3 ----
    def test_a_mode_is_required(self):
        before = self.tree()
        r = run("scripts/migrate-from-store.py", "--src", self.archive(), "--data", self.data)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("one of the arguments --fields --initial-import is required", r.stderr)
        self.assertEqual(self.tree(), before)

    def test_initial_import_checks_everything_before_writing(self):
        arc = self.archive()
        new = json.load(open(self.path("talenta-aditama", arc), encoding="utf-8"))
        new.update(id="tempat-baru-arsip", catatan_internal="private", contacts={"phone": "0812-0000-7777"})
        new.pop("contact_sources", None)
        json.dump(new, open(self.path("tempat-baru-arsip", arc), "w", encoding="utf-8"), ensure_ascii=False)
        before = self.tree()
        r = self.migrate("--initial-import")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("places/tempat-baru-arsip.json: phone 6281200007777", r.stderr)
        self.assertIn("nothing written", r.stderr)
        self.assertEqual(self.tree(), before)
        # cited by a public source -> imported, with the internal note stripped
        new["contact_sources"] = [{"number": "0812-0000-7777", "url": "https://example.org/kontak"}]
        json.dump(new, open(self.path("tempat-baru-arsip", arc), "w", encoding="utf-8"), ensure_ascii=False)
        r = self.migrate("--initial-import")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = open(self.path("tempat-baru-arsip"), encoding="utf-8").read()
        self.assertNotIn("internal", text)
        self.assertEqual({k: v for k, v in before.items()}, {k: v for k, v in self.tree().items() if k != os.path.join("places", "tempat-baru-arsip.json")})
        self.assertEqual(self.validate().returncode, 0)

    def test_initial_import_never_overwrites_scrubbed_contacts_without_force(self):
        arc = self.archive()
        self.edit("biro-sagraha-psikologi-banjarbaru", lambda r: r.update(contacts={"phone": "0812-0000-2222"}), data=arc)
        open(os.path.join(arc, "SCHEMA.md"), "a", encoding="utf-8").write("\narchive-only line\n")
        before = self.tree()
        r = self.migrate("--initial-import")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("KEPT (would overwrite scrubbed contacts (contacts) and other reviewed edits; use --force): places/biro-sagraha-psikologi-banjarbaru.json", r.stdout)
        self.assertIn("KEPT (differs; use --force): SCHEMA.md", r.stdout)
        self.assertEqual(self.tree(), before)
        r = self.migrate("--initial-import", "--force")      # forced, but the uncited archive phone still blocks it
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("phone 6281200002222", r.stderr)
        self.assertEqual(self.tree(), before)

    # ---- R2-m4 / R2-m5 / R2-m6 ----
    def test_missing_state_warns_and_corrupt_state_stops_cleanly(self):
        sp = os.path.join(self.data, ".store-sync.json")
        os.remove(sp)
        r = self.migrate("--fields", "bpjs_info,biaya_gratis")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WARNING: no sync state", r.stderr)
        for bad, msg in (("{", "corrupt sync state"), ("[]", "invalid sync state"), ('{"bnn-kota-banjarbaru": {"bpjs_info": "x"}}', "invalid sync state")):
            with self.subTest(bad):
                open(sp, "w").write(bad)
                before = self.tree()
                r = self.migrate("--fields", "bpjs_info,biaya_gratis")
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(msg, r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertEqual(self.tree(), before)

    def test_unknown_only_id_is_an_error(self):
        r = self.migrate("--fields", "bpjs_info", "--only", "bnn-kota-banjarbaru,tidak-ada")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--only: unknown place id(s) tidak-ada", r.stderr)

    def test_sync_state_is_validated(self):
        sp = os.path.join(self.data, ".store-sync.json")
        st = json.load(open(sp, encoding="utf-8"))
        st["bnn-kota-banjarbaru"]["bpjs_info"] = "not-a-hash"
        st["tidak-ada"] = {"bpjs_info": "0" * 64}
        json.dump(st, open(sp, "w", encoding="utf-8"))
        v = self.validate()
        self.assertNotEqual(v.returncode, 0)
        self.assertIn("schema: bnn-kota-banjarbaru/bpjs_info", v.stdout)
        self.assertIn("tidak-ada: no such place", v.stdout)


class Templates(unittest.TestCase):
    """Every form field must survive GitHub's markdown rendering and reach the generator."""
    def test_rendered_forms_parse_to_all_ids(self):
        import yaml
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        from issue_to_place import load_forms, parse_body
        forms = load_forms()
        self.assertEqual(sorted(f["name"] for f in forms.values()), ["Koreksi info tempat", "Tambah tempat baru"])
        for fname in ("tambah-tempat.yml", "koreksi-tempat.yml"):
            t = yaml.safe_load(open(os.path.join(ROOT, ".github", "ISSUE_TEMPLATE", fname), encoding="utf-8"))
            ids = [b["id"] for b in t["body"] if b.get("id")]
            body = "\n\n".join(f"### {b['attributes']['label']}\n\nX-{b['id']}" for b in t["body"] if b.get("id"))
            name, fields = parse_body(body, forms)
            self.assertEqual(name, t["name"])
            self.assertEqual({k: v for k, v in fields.items()}, {i: f"X-{i}" for i in ids})
            # privacy: no field asks for the contributor's own contact details
            labels = " ".join(b["attributes"].get("label", "") + " " + b["attributes"].get("description", "")
                              for b in t["body"] if b.get("id")).lower()
            # phone consent policy: a source field and a required consent tick
            self.assertIn("sumber_nomor", ids, fname)
            cons = [b for b in t["body"] if b.get("id") == "persetujuan_nomor"]
            self.assertTrue(cons and all(o.get("required") for o in cons[0]["attributes"]["options"]), fname)
            for bad in ("email anda", "nama anda", "nomor anda", "hp anda", "kontak anda"):
                self.assertNotIn(bad, labels, fname)


if __name__ == "__main__":
    unittest.main(verbosity=2)
