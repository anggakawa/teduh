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
