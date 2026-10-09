# Tugas ING001

Status: planned. Semua kotak belum selesai; dokumen tidak menyelesaikan tugas implementasi.

- [ ] ING-T01: Inventaris schema PostgreSQL target, pembaca data, namespace ID, duplicate key, dan row count; tetapkan schema additive serta rollback. ING-R01, ING-R03, ING-R09; bukti ING-V09/V10.
- [ ] ING-T02: Tambahkan kontrak Author, LecturerProfile, SourceAuthorProfile, dan identifier legacy; pisahkan profile ID sumber dari NIP/NIDN. ING-R01, ING-R02; bukti ING-V02/V03.
- [ ] ING-T03: Terapkan Publication ID tetap, DOI opsional, SourcePublication, fallback locator, dan mapping paper ID lama. ING-R03; bukti ING-V04/V05.
- [ ] ING-T04: Bawa raw snapshot, normalisasi, provenance field, dan nilai bertentangan sampai storage. ING-R04; bukti ING-V06.
- [ ] ING-T05: Simpan Authorship dengan beberapa bukti dan status unresolved; hentikan penyatuan berdasarkan nama atau interpretasi ID sumber sebagai NIP. ING-R02, ING-R05; bukti ING-V02/V07.
- [ ] ING-T06: Ganti filter pembuangan incomplete dengan klasifikasi malformed/incomplete, missing fields, dan status terpisah. ING-R06; bukti ING-V08.
- [ ] ING-T07: Terapkan transaksi per record, unique constraint, checkpoint, dan upsert idempotent untuk retry/concurrent ingest. ING-R07; bukti ING-V01/V09.
- [ ] ING-T08: Tambahkan error code per record, retry bounded sementara, dan ringkasan partial run; hasil valid langsung ditulis tanpa review queue. ING-R08; bukti ING-V11.
- [ ] ING-T09: Buat fixture dan integration tests ING-V01..V12; perbarui regression test yang mengharapkan incomplete dibuang. Seluruh requirement; bukti ING-V01..V12.
- [ ] ING-T10: Uji dry run, backup/restore, backfill, compatibility mapping, dan rollback pada database terpisah sebelum target. ING-R09; bukti ING-V10.
- [ ] ING-T11: Batasi snapshot/log dan akses service; uji sentinel secret serta penolakan akses raw oleh mahasiswa. ING-R10; bukti ING-V12.
- [ ] ING-T12: Jalankan smoke test ETL nyata pada target uji, periksa diff/data counts, dan catat command, output, lingkungan, serta risiko aktual. Seluruh requirement; bukti ING-V01..V12.

T01 mendahului schema edit; T02-T06 sebelum T07-T08; T09 melengkapi tiap perubahan. T10-T11 sebelum cutover; T12 menutup perubahan. Regression test boleh mendahului perbaikan code.

## Hasil implementasi

- Migrasi additive, pemetaan legacy, serta prosedur restore/rollback yang teruji.
- Source/test canonical dan compatibility adapter yang diperlukan.
- Bukti requirement-scenario-test serta smoke test pada [verification.md](verification.md).
- Batas metadata incomplete dan identitas unresolved tercatat, tanpa klaim KG/rekomendasi sudah selesai.
