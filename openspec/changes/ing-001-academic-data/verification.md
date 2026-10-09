# Verifikasi ING001

Status implementasi: planned. Acceptance: `NOT RUN`.

Source inspection pada [design.md](design.md) hanya membuktikan kondisi awal. Belum ada pipeline, migration, scraper, query database target, atau acceptance test yang dijalankan untuk perubahan ini.

## Rencana penerimaan

| ID | Requirement | Fixture/aksi dan hasil yang harus dibuktikan | Status |
| --- | --- | --- | --- |
| ING-V01 | R07 | Ulang snapshot sama lalu concurrent ingest; entity/mapping/authorship tidak ganda, nilai canonical konsisten, observasi run tetap tercatat. | NOT RUN |
| ING-V02 | R01/R02/R05 | Dua nama sama dan satu coauthor eksternal tetap terpisah; hanya mapping institusi terbukti mendapat LecturerProfile; ambigu unresolved tanpa review queue. | NOT RUN |
| ING-V03 | R01 | Scholar ID `123` dan Scopus ID `123` tidak bertabrakan; ulang key sama stabil; duplicate key dengan bukti bertentangan dilaporkan. | NOT RUN |
| ING-V04 | R03 | Publikasi tanpa DOI kemudian mendapat DOI/judul baru pada key sumber sama; publication_id tetap, identifier/provenance bertambah. | NOT RUN |
| ING-V05 | R03 | Judul mirip tanpa bukti kuat tetap terpisah; fallback tanpa external ID tercatat; snapshot identik dapat diulang tanpa duplikasi. | NOT RUN |
| ING-V06 | R04 | Publikasi sama dari Scholar/Scopus dengan tahun/venue berbeda; kedua raw value bertahan, nilai canonical mengikuti aturan tercatat. | NOT RUN |
| ING-V07 | R05 | Authorship memiliki dua bukti sumber; ID sumber tidak menjadi NIP; raw NIP hanya dipetakan melalui namespace institusi. | NOT RUN |
| ING-V08 | R06 | Publikasi tanpa DOI/abstrak/keyword tersimpan dengan missing fields; tanpa judul malformed; ingestion_status berbeda dari readiness. | NOT RUN |
| ING-V09 | R07/R09 | Gagal sebelum commit kemudian retry; tidak ada orphan entity/mapping/edge, write parsial rollback, checkpoint melanjutkan input. | NOT RUN |
| ING-V10 | R09 | Dry run tanpa write; restore berhasil; legacy read terjaga setelah backfill; konflik ID lama dan rollback dengan write baru tidak kehilangan record. | NOT RUN |
| ING-V11 | R08 | Satu transient error, satu invalid, satu valid; attempts terbatas, invalid tidak retry tanpa input berubah, valid tersimpan, run partial failure. | NOT RUN |
| ING-V12 | R10 | Dummy secret unik tidak muncul pada snapshot/log/API; mahasiswa ditolak mengakses raw/run internal melalui ID lain; service sah tetap ingest. | NOT RUN |

## Pemetaan requirement ke bukti rencana

| Requirement | Skenario verifikasi | Status |
| --- | --- | --- |
| ING-R01 | ING-V02, ING-V03 | NOT RUN |
| ING-R02 | ING-V02 | NOT RUN |
| ING-R03 | ING-V04, ING-V05 | NOT RUN |
| ING-R04 | ING-V06 | NOT RUN |
| ING-R05 | ING-V02, ING-V07 | NOT RUN |
| ING-R06 | ING-V08 | NOT RUN |
| ING-R07 | ING-V01, ING-V09 | NOT RUN |
| ING-R08 | ING-V11 | NOT RUN |
| ING-R09 | ING-V09, ING-V10 | NOT RUN |
| ING-R10 | ING-V12 | NOT RUN |

## Tingkat bukti

Integration test memakai PostgreSQL pada lingkungan uji yang dapat dipulihkan. Fixture akademik khusus tes tidak dipresentasikan sebagai data dosen nyata. Doubles diperbolehkan pada boundary Scholar/Scopus untuk menghindari scraping berbayar/nondeterministik; kontrak adapter tetap diuji.

Smoke test menjalankan wiring ETL nyata dengan snapshot input yang diizinkan dan database uji. Perbandingan row, ID, provenance, status, serta hasil restart membuktikan storage. Test yang hanya memeriksa pemanggilan mock tidak cukup.

[test_etl_dispatch.py](../../../backend/package/yunesa/etl/tests/test_etl_dispatch.py) saat ini memiliki `test_paper_supabase_insert_skips_incomplete_rows`; ekspektasinya harus berubah bersama kontrak. File acceptance/integration tests baru masih direncanakan.

Implementer menetapkan command setelah memeriksa runner dan environment aktual; tidak ada perintah migrasi/acceptance baru yang diklaim siap dieksekusi.

## Catatan pelaksanaan

Setiap ING-V mencatat tanggal, commit/diff, environment, command/aksi, snapshot fixture, output/assertion, PASS/FAIL/BLOCKED, serta lokasi bukti tanpa secret. BLOCKED menyebut dependency yang belum tersedia dan tidak menggantikan PASS.

Catat row count sebelum/sesudah, accepted/incomplete/unresolved/failed, retry limit efektif, dan mapping berubah. Referensi backup serta restore proof disimpan tanpa kredensial atau data privat di repo.

## Penutupan

Seluruh ING-R memiliki bukti PASS, restore/rollback target terbukti, dan pembaca legacy teruji. Keterbatasan data yang disengaja dicatat sebagai status; requirement gagal tetap terbuka.

KG001/ANS001 diverifikasi sendiri; ING001 selesai belum membuktikan ringkasan setia sumber, kualitas KG, rekomendasi, atau graf jawaban.
