# Delta capability academic-data

Status: planned; ruang lingkup disepakati. Rujukan: [proposal](../../proposal.md), [design](../../design.md), [tasks](../../tasks.md), [verification](../../verification.md).

## ADDED Requirements

### Requirement: ING-R01 Identitas Author dan namespace sumber

Sistem SHALL memberi setiap Author ID internal tetap dan menyimpan profil sumber dengan namespace `(source, external_author_id)`. Sistem SHALL mempertahankan identifier lama berjenis serta mendeteksi konflik key tanpa penyatuan berdasarkan nama.

#### Scenario: ID numerik sama dari dua sumber

- GIVEN Scholar dan Scopus memiliki external ID `123` dengan bukti orang berbeda.
- WHEN keduanya diingest dan satu key sumber dikirim ulang.
- THEN namespace tetap terpisah, mapping ulang stabil, dan raw identifier tidak menjadi ID orang global.

### Requirement: ING-R02 Lecturer terverifikasi dan identitas unresolved

Sistem SHALL membentuk LecturerProfile hanya dari mapping institusi UNESA terverifikasi, mempertahankan Author eksternal, dan menyimpan identitas ambigu sebagai unresolved. Pemrosesan SHALL otomatis tanpa antrean review manusia.

#### Scenario: Nama sama dan coauthor eksternal

- GIVEN dua penulis bernama sama, satu mapping institusi terbukti, serta satu coauthor eksternal.
- WHEN resolver memproses bukti tersedia.
- THEN hanya mapping terbukti mendapat LecturerProfile; kandidat ambigu unresolved dan coauthor tidak dipromosikan karena publikasi bersama.

### Requirement: ING-R03 Identitas Publication persisten

Sistem SHALL menjaga publication_id setelah update metadata, menerima DOI kosong, mempertahankan mapping sumber/legacy, dan mencatat metode fallback tanpa external ID/locator. Kemiripan judul SHALL tidak otomatis menyatukan publikasi.

#### Scenario: DOI baru dan judul berubah

- GIVEN publikasi tanpa DOI tersimpan melalui key sumber.
- WHEN key sama membawa DOI valid dan koreksi judul.
- THEN publication_id tetap, provenance berubah tercatat, dan record berjudul mirip tidak otomatis tergabung.

### Requirement: ING-R04 Snapshot dan provenance field

Sistem SHALL mempertahankan raw snapshot, normalisasi berversi, asal nilai canonical, serta nilai sumber berkonflik. Kebijakan pemilihan nilai SHALL eksplisit dan deterministik.

#### Scenario: Scholar dan Scopus berbeda

- GIVEN dua record terbukti publikasi sama tetapi tahun/venue berbeda.
- WHEN adapter memperbarui metadata canonical.
- THEN kedua nilai tetap dapat ditelusuri dan nilai terpilih menunjuk sumber serta aturan pemilihan.

### Requirement: ING-R05 Authorship berbasis bukti

Sistem SHALL menyimpan pasangan Author-Publication dengan beberapa bukti serta status tautan, membedakan ID sumber dari NIP/NIDN, dan menjaga tautan berbasis nama yang belum pasti sebagai unresolved.

#### Scenario: ID sumber dalam daftar penulis

- GIVEN Scholar author ID dan dua bukti authorship untuk satu publikasi.
- WHEN loader membentuk relasi canonical.
- THEN kedua bukti tersedia dan ID sumber tidak diperlakukan sebagai NIP tanpa mapping institusi yang benar.

### Requirement: ING-R06 Publikasi incomplete tersimpan

Sistem SHALL menyimpan publikasi sah berjudul dengan asal/key sumber walau metadata opsional kurang, mencatat missing_fields, serta memisahkan metadata_completeness, identity_status, ingestion_status, dan kg_readiness. Malformed record SHALL memiliki kegagalan beralasan.

#### Scenario: Metadata kurang dan payload invalid

- GIVEN publikasi berjudul tanpa DOI/abstrak/keyword dan payload tanpa judul.
- WHEN loader memvalidasi batch.
- THEN publikasi sah tersimpan incomplete, invalid memiliki error code, dan tidak ada klaim kesiapan semantik otomatis.

### Requirement: ING-R07 Commit atomik dan ingest idempotent

Sistem SHALL melakukan commit entity, mapping, source reference, dan bukti relasi secara atomik per record serta mencegah duplikasi ketika snapshot sama diproses ulang/concurrent.

#### Scenario: Retry setelah gagal commit

- GIVEN gagal sebelum commit lalu dua worker menerima snapshot sama.
- WHEN pemrosesan dilanjutkan.
- THEN mapping canonical tidak ganda, tidak ada orphan, checkpoint dapat dilanjutkan, dan entity tidak bertambah duplikat.

### Requirement: ING-R08 Kegagalan terisolasi dan retry terbatas

Sistem SHALL mengisolasi error per record, membatasi retry sementara, mempertahankan unresolved/incomplete, dan menulis hasil valid langsung ke database. Run SHALL melaporkan partial failure tanpa pending human approval.

#### Scenario: Satu record gagal dalam batch

- GIVEN record valid, transient error, dan invalid permanen.
- WHEN run memproses sampai batas attempt.
- THEN valid tersimpan, attempts berhenti pada limit, invalid tidak retry tanpa input berubah, dan setiap status dilaporkan berbeda.

### Requirement: ING-R09 Migrasi additive dan kompatibilitas

Migrasi SHALL mempertahankan raw legacy ID dengan mapping transactional, melakukan dry run tanpa write, mendeteksi konflik/duplikasi, serta menyediakan backup konsisten, restore proof, dan rollback yang menjaga write baru. Reset schema destruktif SHALL tidak digunakan.

#### Scenario: Backfill dan rollback

- GIVEN snapshot lama, konflik identifier, dan write baru setelah cutover uji.
- WHEN dry run, backfill, compatibility read, dan rollback dijalankan terpisah.
- THEN dry run tidak menulis, konflik tidak tergabung, pembaca lama dapat memetakan ID, dan rollback tidak kehilangan record baru.

### Requirement: ING-R10 Akses dan batas secret

Sistem SHALL membatasi ingest/raw snapshot ke service berwenang, mengecualikan secret dari payload/log, dan hanya menyajikan metadata akademik yang diizinkan ke mahasiswa.

#### Scenario: Secret sentinel dan akses raw

- GIVEN dummy secret unik dan account mahasiswa tanpa hak raw.
- WHEN ingest berjalan dan account mencoba snapshot/run internal melalui ID lain.
- THEN secret tidak tersimpan/terekspos, akses raw ditolak, dan service berwenang tetap berfungsi.
