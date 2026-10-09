# Keputusan 0001: produk dan kontrak data Yunesa

Tanggal: 9 Oktober 2026 (Asia/Jakarta).
Status: accepted untuk rancangan; penerapan dilacak oleh change spec.
Dasar: keputusan pemilik proyek dalam sesi perumusan.

## Konteks

Aplikasi dipisahkan dari proyek skripsi dan sudah memiliki ETL serta komponen GraphRAG. Pemilik proyek melaporkan data ETL sudah tersimpan; pemetaan dosen, publikasi, dan integrasinya masih perlu diperbaiki.

Audit source menemukan dukungan graph dalam chat, tetapi belum membuktikan alur lengkap. Dokumen membedakan kondisi kode dari target.

## Keputusan yang berlaku

1. Mahasiswa UNESA mencari dosen berdasarkan topik, dengan publikasi dan graph bukti.
2. Gunakan seluruh data lintas prodi yang tersedia; Sains Data menjadi sampel awal.
3. Login memakai akun aplikasi; jawaban hanya memakai indeks internal.
4. Graph awal berfokus pada bukti jawaban dan dapat diperluas.
5. ETL Scholar/Scopus menjadi dasar; pertahankan sumber metadata, data mentah, serta pemetaan ID lama.
6. Author adalah identitas semua penulis. Lecturer merupakan profil/peran UNESA terverifikasi. Penulis luar tidak otomatis menjadi dosen UNESA.
7. Metadata valid yang belum lengkap tetap disimpan dan dapat ditampilkan dengan status. Kesiapan ekstraksi merupakan status terpisah.
8. Ringkasan Inggris sekitar 2–4 kalimat dibentuk dari judul dan abstrak. Semua ekstraksi semantik hanya membaca ringkasan tersebut.
9. Ontologi constants.py menjadi baseline, dengan delta Author dinyatakan pada KG-001. Resource IEEE mendukung penyelarasan konsep.
10. Hasil yang lolos validasi otomatis langsung disimpan. Identitas ambigu tetap unresolved; tidak ada antrean atau persetujuan admin.
11. Pipeline mingguan dapat dipicu manual. Retry per paper dibatasi; paper lain tetap berjalan.
12. Urutan implementasi: ING-001, KG-001, lalu ANS-001.

## Keputusan yang digantikan

Usulan review admin untuk identitas dan hasil ekstraksi telah digantikan oleh proses otomatis dengan status unresolved/failed. Jangan menghidupkan kembali antrean review sebagai syarat pipeline.

Input semantik gabungan judul, TLDR, keyword, dan fallback abstrak digantikan oleh ringkasan Inggris saja. Ringkasan satu kalimat maksimal 55 kata bukan kontrak target baru.

## Konsekuensi

- Pisahkan kelengkapan, kepastian identitas, kesiapan KG, dan status eksekusi.
- Pertahankan bukti serta versi pengolahan sampai graph jawaban.
- Rerun harus menjaga ID, mencegah efek duplikat, dan melindungi hasil terakhir yang valid.
- Perubahan Author/Lecturer memerlukan migrasi dan kompatibilitas query lama.
- Kelulusan format tidak menjamin fakta benar; ukur mutu melalui sampel sebelum klaim performa.
- Backend produksi graph/vector belum dipilih. Selesaikan selisih dev/prod melalui pemeriksaan kompatibilitas.

## Verifikasi

Ini kontrak target. Bukti implementasi dimulai pada [ING-001](../../openspec/changes/ing-001-academic-data/verification.md), kemudian KG-001 dan ANS-001.

[PRD](../../PRD.md) memuat kebutuhan yang berlaku. [Arsitektur](../../ARCHITECTURE.md) memuat kondisi kode serta batas perubahan.

