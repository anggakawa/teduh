# Ikut melengkapi data Teduh

## Untuk kontributor

Anda tidak perlu menyentuh kode. Buka tab **Issues → New issue**, lalu pilih:

- **Tambah tempat baru** — layanan yang belum ada di peta.
- **Koreksi info tempat** — info salah atau berubah, tempat pindah, atau sudah tutup.
  Isi hanya kolom yang perlu diubah.

Yang wajib: **sumber/bukti berupa tautan** (situs resmi, akun resmi, Google Maps, berita, direktori).
Tautan peta boleh ditambahkan; titik hanya dipasang jika tautannya memuat koordinat tepat
(tautan "Bagikan" dari pin Google Maps, atau OpenStreetMap dengan penanda). Tautan pendek
(`maps.app.goo.gl`) tidak dibuka otomatis.

### Nomor telepon / WhatsApp

Nomor hanya dicantumkan jika **sudah publik dan dicantumkan sendiri oleh lembaga/pemiliknya**
(situs resmi, akun media sosial resmi, profil bisnis milik tempat itu, halaman instansi pemerintah),
atau pemiliknya sudah setuju nomornya dicantumkan.

- Tulis nomor hanya di kolom "Nomor telepon tempat" / "Nomor WhatsApp tempat".
- Isi "Sumber nomor telepon/WhatsApp" dengan tautan ke halaman tempat pemiliknya mencantumkan nomor
  itu (satu tautan per baris, urutan sama dengan nomornya), lalu centang konfirmasinya.
- Direktori, mesin pencari, berita, skripsi, atau unggahan orang lain **tidak cukup** sebagai sumber nomor.
- Jangan menulis nomor pribadi psikolog, terapis, staf, atau perorangan tanpa persetujuan mereka.

Usulan yang memuat nomor tanpa tautan sumber atau tanpa konfirmasi ditolak otomatis.

**Privasi.** Issue terbuka untuk umum dan nama akun GitHub Anda terlihat. Formulir tidak meminta
data pribadi Anda. Jangan menulis nomor pribadi seseorang, cerita pribadi, diagnosis, atau
pengalaman sebagai klien. Pengelola akan menyunting atau menyembunyikan issue yang memuat data pribadi.

Semua usulan tampil sebagai **"Belum dicek"** sampai tim memeriksanya. Formulir ini bukan layanan
bantuan. Dalam keadaan darurat, telepon **112**, atau **SAPA 129** untuk kekerasan pada perempuan & anak.

## Untuk pengelola (CODEOWNERS)

### 1. Triase issue
- Baca issue berlabel `usulan-data`. Jika memuat data pribadi: sunting bagian itu (atau sembunyikan
  komentar/hapus issue), lalu minta kontributor mengirim ulang tanpa data pribadi.
- Spam/tidak relevan: tutup.
- Layak diproses: tambahkan label **`data-submission`**. Workflow akan membuat PR `data/issue-<N>`
  dan berkomentar di issue. Jika isian tidak valid, bot berkomentar alasannya dan memberi label
  `perlu-perbaikan`; setelah kontributor menyunting issue, lepas lalu pasang lagi `data-submission`.

### 2. Review PR dari bot
Centang daftar di badan PR:
- Buka **setiap** tautan sumber. Info harus cocok dan sumbernya publik/resmi.
- Tidak ada data pribadi di berkas JSON.
- Setiap nomor telepon/WA punya entri `contact_sources` (`number`, `url`, opsional `note`, `checked`).
  Buka tautannya: nomor harus tercantum di halaman milik lembaga/pemiliknya sendiri. Jika tidak,
  hapus nomornya dari PR. Setelah dicek, ganti `note` "belum dicek tim" dan isi `checked`.
- Tidak duplikat dengan tempat lain (cek nama mirip, alamat sama).
- Kategori tepat. Jika tidak yakin, ubah di PR.
- Lokasi: pin (`lat`/`lng`) hanya dari koordinat tepat, dengan `coord_method` yang menyebut asalnya.
  `approx_coords` tidak pernah menjadi pin (CI menolak).
- Koreksi menghapus kolom tampilan yang akan menampilkan nilai lama (`address_display`,
  `hours_normalized`, `services_display`, …). Isi ulang di commit Anda bila sudah dicek, mengikuti
  `data/SCHEMA.md` (teks tampilan hanya berisi fakta yang ada di sumber).
- Status tetap `needs-check`. Merge jika data layak tampil sebagai "Belum dicek".

### 3. Verifikasi (status `active`)
Hanya setelah dicek (telepon ke tempat, atau 2+ sumber independen yang baru):
- Buat **PR terpisah** atas nama Anda sendiri: ubah `status` ke `active`, isi `checked`/`verified_at`
  (YYYY-MM-DD), perbarui `field_confidence`, `history`, dan hapus/ubah `open_issues`.
- CI (`guard_pr.py`) menolak perubahan ke `active` jika penulis PR tidak tercantum di
  `.github/CODEOWNERS` untuk `/data/places/` (dibaca dari branch dasar, jadi PR tidak bisa
  menambahkan dirinya sendiri). Bot tidak pernah boleh tercantum di CODEOWNERS.

### 4. Tempat tutup / pindah
Laporan "tutup permanen" hanya menandai tempat (`needs-check` + catatan). Setelah dipastikan,
pengelola memutuskan: hapus berkas (hanya CODEOWNERS; CI menolak penghapusan oleh orang lain)
atau biarkan dengan catatan.

### 5. Setelah merge
Workflow **Pages** memvalidasi, menjalankan `build-data.py`, dan menerbitkan `site/`. Issue tertutup
otomatis lewat "Closes #N".

## Aturan yang dicek CI di setiap PR

| Cek | Skrip |
|---|---|
| JSON Schema (SCHEMA v3), `id` = nama berkas, minimal satu sumber http(s), tanpa markup/script | `scripts/validate.py` |
| `approx_coords` tidak pernah jadi pin; pin di area Banjarbaru & sekitar | `validate.py`, `guard_pr.py` |
| Hanya CODEOWNERS yang boleh membuat `active` atau menghapus tempat | `guard_pr.py` |
| Perubahan `lat`/`lng` wajib menyebut asal di `coord_method`; sumber baru harus URL | `guard_pr.py` |
| Setiap nomor telepon/WA punya `contact_sources` dengan tautan http(s); nomor baru/berubah di PR wajib bersumber | `validate.py`, `guard_pr.py` |
| `build-data.py --strict` berjalan tanpa data terlewat | `scripts/build-data.py` |
| Tes pipeline (contoh issue baru, koreksi, berbahaya/tidak valid) | `tests/test_pipeline.py` |
| Uji tampilan situs di data beku | `scripts/check.mjs` |

## Audit nomor telepon (31 Oktober 2026)

Sebelum repo dipublikasikan, semua nomor di data diperiksa satu per satu. Nomor yang dipertahankan
sudah dicek tercantum di halaman resmi lembaga/pemiliknya dan kini punya `contact_sources`. Nomor
yang hanya ditemukan di Google Maps, direktori, mesin pencari, skripsi, atau dokumen pribadi, dan
nomor pribadi praktisi/perorangan, dihapus dari data repo (ditandai `field_confidence.phone` dan
entri `history` "privacy-audit"). Nomor itu bisa ditambahkan kembali lewat formulir koreksi jika ada
sumber resmi dari pemiliknya atau persetujuan pemiliknya.
