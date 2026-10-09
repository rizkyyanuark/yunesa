# Rancangan ING001

Status: planned. Perubahan di dokumen ini belum diimplementasikan.

## Bukti kondisi sumber

Pemeriksaan source dilakukan tanpa menjalankan ETL atau membaca nilai kredensial.

| Jalur yang diperiksa | Temuan dan implikasi |
| --- | --- |
| [unesa_papers.py](../../../backend/package/yunesa/etl/services/unesa_papers.py), baris 473-505 | Fungsi bernama `run_supabase_insert` memakai `PostgresClient`; filter completeness membuang baris sebelum upsert dan `links_count` bernilai 0. Nama fungsi tidak membuktikan Supabase ialah storage aktif jalur ini. |
| [postgres_client.py](../../../backend/package/yunesa/etl/clients/postgres_client.py), baris 174-184 dan 210-225 | Fallback ID memakai hash DOI lowercase atau judul lowercase. Upsert metadata inti belum membawa provenance enrichment. |
| [hasher.py](../../../backend/package/yunesa/etl/utils/hasher.py), baris 33-42 | Helper memakai prefiks `doi:` atau judul ternormalisasi beserta tahun. Perbedaan aturan dengan loader memungkinkan ID berbeda untuk input sama. |
| [kg_service.py](../../../backend/package/yunesa/knowledge/services/kg_service.py), baris 243-253 | `author_ids` langsung masuk field `nip`; ID profil sumber tidak selalu NIP. Adapter KG harus diperbaiki saat integrasi KG001. |
| [enricher.py](../../../backend/package/yunesa/etl/transform/enricher.py), baris 164-186 | Payload provenance sudah dibuat; ING001 membawa bukti tersebut sampai storage canonical. |

Temuan ini berasal dari code path lokal, bukan pemeriksaan isi/schema database berjalan.

## Model logical

Nama berikut merupakan kontrak logical; belum merupakan tabel baru yang tersedia.

| Entitas | Kontrak utama |
| --- | --- |
| Author | `author_id` internal tetap, nama tampilan, identitas resolved/unresolved; termasuk penulis di luar UNESA. |
| LecturerProfile | Mengacu ke Author; bukti status dosen UNESA, identifier institusi, program/unit bila tersedia, serta waktu berlakunya informasi. |
| SourceAuthorProfile | Namespace `(source, external_author_id)` unik; locator, snapshot, mapping Author beserta bukti dan status. |
| Publication | `publication_id` internal tetap; DOI opsional dan metadata canonical terpilih tanpa menghapus versi sumber. |
| SourcePublication | Key/locator Scholar atau Scopus, raw snapshot, hasil normalisasi, serta mapping Publication. |
| Authorship | Pasangan Author-Publication, posisi bila tersedia, status tautan, dan kumpulan bukti sumber. |
| LegacyIdentifier | Mapping namespace dataset/jenis identifier lama ke ID canonical, termasuk NIP/NIDN, ID database, dan hash paper lama. |
| IngestionRun | Waktu, versi adapter, snapshot input, jumlah processed/accepted/failed/incomplete/unresolved, serta attempts per record. |

ID canonical tidak dihitung ulang dari nama, judul, tahun, atau DOI. ID sumber ialah identifier berjenis, bukan ID orang lintas sumber. NIP/NIDN tetap string dengan provenance; kosong/sentinel tidak menjadi key bersama.

Nama sama, afiliasi tertulis, atau coauthorship tidak cukup untuk menggabungkan Author atau memberinya LecturerProfile. Mapping institusi harus memiliki bukti terverifikasi. Identitas ambigu tetap unresolved; sistem mengevaluasi ulang otomatis bila ada bukti baru, tanpa antrean review manusia.

## Identitas publikasi dan provenance

Pencocokan menggunakan mapping record sumber tersimpan, lalu identifier publikasi kuat yang tervalidasi. Kemiripan judul/tahun hanya kandidat pencocokan, bukan dasar penyatuan otomatis.

Tanpa external ID, adapter memakai locator sumber stabil bila ada. Jika locator juga kosong, simpan key fallback dan metodenya pada snapshot ingest. Hash payload mengidentifikasi snapshot, bukan identitas publikasi permanen. Snapshot identik harus idempotent; deduplikasi lintas snapshot tanpa bukti tidak boleh diklaim.

DOI yang datang kemudian menjadi identifier tambahan pada publikasi sama melalui mapping sumber. Konflik DOI atau kemungkinan salah gabung mempertahankan record terpisah dan bukti dengan status konflik otomatis.

Raw snapshot append-only untuk audit. Normalisasi mencatat versi adapter, waktu akses, dan key sumber. Setiap nilai canonical menunjuk snapshot/field pendukung. Nilai Scholar dan Scopus yang berbeda tetap tersedia; kebijakan prioritas field harus eksplisit dan deterministik.

Bukti authorship dapat berasal dari beberapa sumber. Simpan origin, locator, observasi, mapping identitas, serta alasan status. Relasi hanya berdasarkan nama tetap unresolved; daftar ID sumber tidak diperlakukan sebagai NIP.

## Validasi dan kegagalan

Publikasi sah memerlukan judul nonkosong, asal sumber, dan key/locator fallback tercatat. DOI, abstrak, keyword, venue, tahun, atau profil penulis yang kurang menghasilkan `missing_fields`, bukan penghapusan record.

Pisahkan `identity_status`, `metadata_completeness`, `ingestion_status`, dan `kg_readiness`. Readiness mengacu ke kontrak input KG001; ING001 tidak membuat ringkasan/assertion semantik. Bukti struktural yang valid tetap tersedia meskipun sebagian metadata kurang.

Malformed payload, identifier bertentangan, dan error storage memiliki error code berbeda. Error per record tersimpan tanpa secret atau seluruh payload dalam log; record valid lain terus diproses.

Retry otomatis hanya bagi kegagalan sementara, dibatasi konfigurasi attempts/backoff. Invalid permanen tidak retry tanpa perubahan input. Run melaporkan partial failure; insert sukses tidak menyiratkan identitas terverifikasi, metadata lengkap, atau KG sukses.

## Alur penyimpanan

1. Baca input ETL yang tersedia dan simpan identitas raw snapshot.
2. Normalisasi field dengan nilai sumber serta namespace identifier tetap tersedia.
3. Validasi dan cari mapping sumber/legacy yang telah ada.
4. Bentuk/perbarui Author, Publication, profil, dan bukti yang didukung.
5. Commit atomik per record: entity, mapping, source reference, authorship evidence, dan status ingest.
6. Catat hasil run dan metadata untuk adapter KG001/ANS001.

Unique constraint/transaksi menangani worker concurrent. Gagal commit tidak meninggalkan mapping atau edge tanpa entity induk. Hasil yang lolos validasi langsung tersimpan tanpa pending approval.

## Migrasi dan kompatibilitas

Inventaris schema, key, row count, identifier, dan pembaca data pada target sebelum implementasi migrasi. Dry run mendeteksi duplicate key, namespace collision, orphan links, serta mapping yang belum pasti; belum menulis target.

Ambil backup konsisten dan buktikan restore terpisah sebelum cutover. Gunakan schema additive dan backfill bertahap dengan checkpoint; jangan menjalankan ulang init SQL yang melakukan `DROP`.

Mapping legacy transactional mempertahankan raw ID. Jika satu ID lama menunjuk objek berbeda, mapping tersebut berstatus konflik tanpa penggabungan diam-diam. Pilih compatibility view/adapter setelah inventaris agar pembaca lama tetap dapat memetakan ID.

Rollback mengembalikan pembaca ke schema lama dengan jurnal write sejak cutover; rekonsiliasi tidak boleh kehilangan publikasi baru. Latihan gagal-migrasi dan restore harus lulus sebelum penerapan target.

## Batas akses

Raw snapshot mengecualikan credential header, cookie, token, dan `.env`. Ingest melalui service berwenang; API mahasiswa hanya menyajikan metadata akademik yang diizinkan. Snapshot/log internal tidak otomatis menjadi endpoint publik.

ING001 tidak mengubah deployment, menjalankan scraping, atau mengganti ETL dengan pipeline paralel. Seluruh acceptance pada [verification.md](verification.md) masih `NOT RUN`.
