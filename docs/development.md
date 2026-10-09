# Pengembangan dengan spesifikasi

Paket dokumentasi v0.1, 9 Oktober 2026.
Peta utama: [PRD](../PRD.md), [arsitektur](../ARCHITECTURE.md), [panduan agen](../AGENTS.md), dan [indeks perubahan](../openspec/README.md).

## Alur kerja

1. Rekonstruksi kondisi sekarang dari kode, entrypoint, konfigurasi, dan bukti pengujian.
2. Tulis proposal: masalah, tujuan, batas pekerjaan, dan dampak.
3. Tulis requirement dengan skenario penerimaan; jelaskan desain untuk keputusan yang berpengaruh.
4. Pecah tugas menjadi perubahan yang mempunyai bukti selesai.
5. Implementasikan dan jalankan pemeriksaan relevan.
6. Tinjau diff serta bukti, lalu perbarui spesifikasi jika keputusan berubah.
7. Konvergensikan capability spec dengan kontrak yang telah diterapkan, kemudian arsipkan change.

Perbaikan ejaan atau perubahan internal kecil tidak memerlukan desain baru. Perubahan data, akses, API, pipeline, model, dan storage membutuhkan kontrak eksplisit.

## Struktur dan status

Setiap change mempunyai proposal.md. ING-001 juga mempunyai design.md, tasks.md, verification.md, dan delta specs/academic-data/spec.md. KG-001 dan ANS-001 masih berupa proposal; rincian disusun ketika dependensinya siap.

Scope accepted berarti kebutuhan disepakati. Planned berarti pekerjaan belum dijalankan. Implemented memerlukan bukti penerimaan.

Delta menggunakan ADDED/MODIFIED/REMOVED Requirements, Requirement, dan Scenario dengan GIVEN/WHEN/THEN. Pertahankan ID requirement selama maknanya tetap sama.

Folder openspec/specs awalnya hanya berisi indeks karena belum ada baseline capability yang diverifikasi penuh. Observasi source tersedia di ARCHITECTURE.md. Jangan mempromosikan kebutuhan target seolah sudah selesai.

Setelah konvergensi, arsipkan dengan tanggal dan slug. Keputusan penting masuk [catatan keputusan](decisions/0001-yunesa-product-contract.md).

Struktur Markdown ini mengikuti pola OpenSpec. CLI belum dipasang atau dikonfigurasi. Perintah slash toolkit bukan perintah PowerShell; instalasi toolkit adalah pekerjaan terpisah bila diperlukan.

## Perintah yang tersedia

Perintah ini diperiksa terhadap konfigurasi repository, tetapi tidak dijalankan sebagai pengujian aplikasi dalam pekerjaan dokumentasi ini.

| Direktori | Perintah | Batas bukti |
|---|---|---|
| backend | uv run --group test pytest test/unit/test_package_import.py | Smoke test impor; bukan bukti pipeline lengkap |
| backend | uv run --group test pytest test/unit | Unit suite; pilih subset relevan sebelum memperluas |
| backend | uv run --group dev ruff check package/yunesa/etl | Pemeriksaan statis ETL tanpa perbaikan otomatis |
| web | pnpm exec eslint src | Pemeriksaan frontend tanpa --fix |
| web | pnpm build | Build frontend |
| root proyek | docker compose -p yunesa --env-file .env -f docker-compose.yml config --quiet | Validasi konfigurasi; memerlukan .env lokal |

uv run dapat menyiapkan dependency/lingkungan; pnpm memerlukan dependency terpasang. Jangan menjalankan instalasi hanya untuk pemeriksaan dokumen. Prasyarat setup tersedia di [README](../README.md).

Script pnpm lint saat ini memakai --fix dan --cache. Jangan gunakan untuk audit baca saja.

Tes integrasi memakai TEST_BASE_URL dan kredensial pengujian dari lingkungan lokal. Tes yang skip tanpa kredensial tidak membuktikan perilaku autentikasi. Folder backend/test/e2e saat ini baru berisi fixture; kasus E2E dibuat sesuai perubahan.

Gunakan database pengujian terisolasi untuk uji storage dan periksa isi data sesudah operasi. Jangan menjalankan SQL DROP terhadap data aktif.

## Bukti verifikasi

| Status | Arti |
|---|---|
| Passed | Pemeriksaan benar-benar dijalankan dan hasil relevan diperiksa |
| Inspected | Kode/konfigurasi dibaca; runtime belum dibuktikan |
| Not run | Belum dijalankan, dengan alasan |
| Inferred | Kesimpulan tidak langsung yang memerlukan pembuktian |

Catat snapshot/commit, konfigurasi tanpa secret, perintah, fixture, hasil, serta keterbatasan. Hasil mock/replay tidak sama dengan provider nyata.

Pengujian awal memakai sampel Sains Data: nama serupa, paper lintas sumber, DOI baru, abstrak kosong, provider gagal, dan pertanyaan Indonesia. Gunakan fixture sintetis untuk regresi dan sampel nyata yang diizinkan untuk evaluasi kesetiaan ringkasan serta ekstraksi.

Evaluasi pengembang terhadap sampel bukan antrean review manusia dalam pipeline produk.

## Rujukan

- [Spec Loop Yuxi](https://github.com/xerrors/Yuxi/blob/main/docs/develop-guides/spec-loop.md): inspeksi, perubahan, pembuktian, dan konvergensi.
- [OpenSpec](https://github.com/Fission-AI/OpenSpec): struktur perubahan dan spesifikasi Markdown.
- [ISO/IEC/IEEE 29148](https://www.iso.org/standard/72089.html): acuan rekayasa kebutuhan; paket ini tidak menyatakan sertifikasi atau kepatuhan penuh.
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/): acuan aksesibilitas yang akan diuji, bukan klaim kepatuhan UI saat ini.

