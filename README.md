# Teduh — Peta layanan Banjarbaru

Peta layanan kesehatan mental, tumbuh kembang anak, dan pendampingan di Banjarbaru & sekitar.
Situs: https://anggakawa.github.io/teduh/

Repo ini adalah **sumber data utama**: satu berkas JSON per tempat, ditambah situs statis yang
dibangun dari data itu dan diterbitkan ke GitHub Pages.

## Isi repo

| Folder | Isi |
|---|---|
| `site/` | Situs (HTML/CSS/JS, Leaflet & font disertakan). `site/data/` dibuat oleh `build-data.py`, tidak di-commit. |
| `data/places/<id>.json` | Satu tempat per berkas. `id` = nama berkas. |
| `data/hotlines.json` | Layanan tanpa lokasi (112, SAPA 129, dll.). |
| `data/SCHEMA.md` | Penjelasan kolom (SCHEMA v5: v3 + `contact_sources`, v4 `bpjs_info`, v5 `biaya_gratis`). |
| `schema/*.schema.json` | JSON Schema dari SCHEMA.md (`place`, `hotlines`, serta `bpjs_info` dan `biaya_gratis` yang dirujuk dari `place`). |
| `scripts/build-data.py` | Membaca `data/`, memvalidasi, menulis `site/data/`. |
| `scripts/validate.py` | JSON Schema + aturan wajib (approx_coords tidak pernah jadi pin, nomor bersumber, tanpa nomor di `bpjs_info`/`biaya_gratis`, tanpa catatan internal, dll.). |
| `scripts/guard_pr.py` | Aturan PR: kontributor tidak bisa mengubah status jadi terverifikasi. |
| `scripts/phones.py` | Mengenali nomor telepon/WA di data (dipakai untuk aturan persetujuan nomor). Untuk `bpjs_info` / `biaya_gratis` ada pemindai ketat (`find_strict`): teks dinormalisasi NFKC, pemisah dibuang, URL `wa.me` / `tel:` ikut diperiksa. |
| `scripts/leaks.py` | Aturan bersama (dipakai `validate.py`, `migrate-from-store.py`, `build-data.py`) untuk kunci `*internal*` (dilipat: NFKC, huruf kecil, ı → i), bentuk kunci (hanya `A-Z a-z 0-9 _ -`), dan alamat email (termasuk `nama [at] gmail [dot] com`). |
| `scripts/issue_to_place.py` | Mengubah isian formulir issue menjadi perubahan JSON. |
| `scripts/migrate-from-store.py` | Migrasi dari arsip lama. Wajib memilih mode. `--initial-import` (impor penuh, sudah dijalankan 31 Okt 2026) hanya menulis bila semua cek `validate.py` lolos (skema, persetujuan nomor, kunci) dan tidak menimpa berkas yang berbeda (kontak yang sudah disaring) tanpa `--force`. `--fields bpjs_info,biaya_gratis` hanya menyalin dua kolom itu (kolom lain ditolak) ke tempat yang sudah ada, membuang kunci `*internal*`, dan berhenti tanpa menulis (dan tanpa mencetak diff) bila ada nomor telepon, email, atau kunci terlarang. Nilai yang diubah tangan di repo dipertahankan kecuali `--force` (jejak sinkron terakhir: `data/.store-sync.json`, skema `schema/store-sync.schema.json`, hanya pemilik kode yang boleh mengubahnya); `--only <id>` membatasi ke tempat tertentu (id yang tidak dikenal = galat). Kontak yang sudah disaring tidak pernah disentuh. |
| `scripts/check.mjs`, `scripts/screens.mjs` | Uji browser dan tangkapan layar situs. |
| `tests/` | Contoh isi issue, tes pipeline, dan data beku untuk uji UI. |
| `.github/` | Formulir issue, workflow, CODEOWNERS. |

## Alur data

```
Kontributor isi formulir issue ("Tambah tempat baru" / "Koreksi info tempat")
        │  label otomatis: usulan-data
        ▼
Pengelola membaca issue → menambah label  data-submission
        ▼
Workflow "Usulan data ke PR": parse formulir → tulis/patch data/places/<id>.json
  • status selalu needs-check ("Belum dicek")
  • lat/lng hanya dari tautan peta berkoordinat tepat; selain itu approx/tanpa titik
  • validasi + build → buka PR "Closes #N" → komentar di issue
  (isian tidak valid → komentar alasan + label perlu-perbaikan, tanpa PR)
        ▼
CI di PR: schema, aturan wajib, guard, build-data.py, tes pipeline, check.mjs
        ▼
Pengelola (CODEOWNERS) review & merge → workflow Pages membangun dan menerbitkan situs
        ▼
Verifikasi (status "active") hanya lewat PR terpisah oleh CODEOWNERS setelah dicek.
```

Detail untuk kontributor dan pengelola: [CONTRIBUTING.md](CONTRIBUTING.md).

## Menjalankan secara lokal

```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
python3 scripts/validate.py                  # schema + aturan wajib
python3 scripts/build-data.py --strict       # menulis site/data/
python3 tests/test_pipeline.py               # contoh issue → JSON → validasi → build, dan guard
cd site && python3 -m http.server 8765       # buka http://localhost:8765/
```

Uji browser (butuh `playwright-core` dan Google Chrome). CI menjalankannya pada data beku
`tests/fixtures/data` agar tempat baru tidak mematahkan uji tampilan:

```bash
npm install --prefix /tmp/pw playwright-core@1.64.1
rm -rf /tmp/uisite && cp -r site /tmp/uisite
python3 scripts/build-data.py --src tests/fixtures/data --out /tmp/uisite/data
(cd /tmp/uisite && python3 -m http.server 8765 &)
SITE_DIR=/tmp/uisite TEDUH_DATA=tests/fixtures/data PW_DIR=/tmp/pw node scripts/check.mjs
PW_DIR=/tmp/pw node scripts/screens.mjs http://localhost:8765/   # tangkapan layar → screenshots/ (tidak di-commit)
```

## BPJS dan Gratis

- **BPJS** (`bpjs_info`, SCHEMA v4): chip di kartu dan detail untuk `ya` / `sebagian` (+ "perlu rujukan") / `tidak`; `belum_diketahui` hanya tampil di detail (abu-abu, tidak pernah ditulis "tidak"); `tidak_relevan` tanpa chip. Filter "Terima BPJS" = `ya` + `sebagian`.
- **Gratis** (`biaya_gratis`, SCHEMA v5): tag hanya dari `biaya_gratis.status`: `ya` → "Gratis", `bersyarat` → "Gratis bersyarat" (syarat tampil di detail), `tidak` / `belum_diketahui` → tanpa tag. `perlu_cek_ulang: true` menambah "· cek ulang" di tag kartu (aria: "perlu dicek ulang") dan "perlu dicek ulang" di detail. Teks bebas tidak pernah dibaca sebagai "gratis", dan terima BPJS tidak berarti gratis.
- **Privasi**: `catatan_internal` dan kunci lain yang memuat "internal" setelah dilipat (NFKC + huruf kecil + ı → i, jadi juga `NOTE_INTERNAL`, `catatan-internal`, `catatan internal`, `catatan_ınternal`) ditolak `validate.py` (tempat dan `hotlines.json`), dibuang oleh `migrate-from-store.py --fields`, dan membuat `build-data.py` berhenti tanpa menulis apa pun bila muncul sebagai kunci di keluaran (atau bila teks `catatan_internal` muncul). Semua kunci juga wajib berupa pengenal ASCII polos (`^[A-Za-z0-9_-]+$`), jadi karakter tersembunyi (zero-width, soft hyphen, BOM) dan huruf mirip (Kiril `і`) tidak bisa menyamarkan kunci internal. Tidak boleh ada nomor telepon atau email di `bpjs_info` / `biaya_gratis`; URL sumbernya wajib `http(s)://` dan bukan `wa.me`. `basis` disimpan di data repo sebagai asal-usul, tetapi tidak dikirim ke situs (`bpjs_info` maupun `biaya_gratis`).

Coba generator dengan contoh isi issue:

```bash
python3 scripts/issue_to_place.py --body-file tests/issues/01-tempat-baru.md --issue 1 --out out
git status data/ && git clean -fd data/ && git checkout data/   # lihat hasilnya, lalu kembalikan
```

`?now=2026-10-31T13:56` di URL membekukan "waktu sekarang" untuk teks jam buka (hanya dibaca, tidak disimpan).

## Aturan wajib

- `approx_coords` (titik tengah jalan/tampilan peta) **tidak pernah** menjadi pin.
- Tempat yang belum dicek tampil dengan pin berongga dan chip abu-abu "Belum dicek".
- Usulan dari formulir selalu `needs-check`; hanya CODEOWNERS yang boleh mengubah ke `active`.
- Situs tidak menyimpan riwayat atau data di browser (tanpa localStorage/history).
- Jam dan catatan ditampilkan sesuai sumber; data tidak dikarang.
- **Nomor telepon/WhatsApp** hanya dicantumkan jika sudah publik **dan** dicantumkan sendiri oleh
  lembaga/pemiliknya (situs resmi, akun resmi, halaman instansi), atau pemiliknya setuju. Setiap nomor
  wajib punya entri `contact_sources` berisi tautan http(s) ke halaman itu; CI menolak nomor tanpa
  sumber. Nomor pribadi staf atau perorangan tidak dicantumkan tanpa persetujuan. Lihat
  [CONTRIBUTING.md](CONTRIBUTING.md#nomor-telepon--whatsapp).

## Penerbitan

Repo publik: https://github.com/anggakawa/teduh, situs di GitHub Pages: https://anggakawa.github.io/teduh/
(Pages bersumber dari workflow GitHub Actions). Pengaturan repo:

- Workflow permissions: read & write, dan **Allow GitHub Actions to create and approve pull requests** aktif.
- Label: `usulan-data`, `tempat-baru`, `koreksi`, `data-submission`, `perlu-perbaikan`.
- Branch protection `main`: wajib PR, wajib review CODEOWNERS, wajib status check
  `Data (schema, rules, guard, build, tests)`.
- PR dari bot memakai `GITHUB_TOKEN`, sehingga CI tidak berjalan otomatis di PR itu. Pengelola bisa
  menutup lalu membuka ulang PR agar CI berjalan. (Opsional nanti: secret `TEDUH_BOT_TOKEN` dari
  GitHub App / akun bot yang **bukan** CODEOWNERS.)
