# ING001: kontrak data akademik

Status: ruang lingkup disepakati; implementasi direncanakan.
Tanggal rancangan: 2026-10-09. Capability: `academic-data`.

## Masalah

ETL Scholar/Scopus sudah tersedia, tetapi kontrak identitas penulis, dosen, dan publikasi belum konsisten. Jalur PostgreSQL menolak baris incomplete, menghitung fallback ID publikasi dengan aturan berbeda, dan belum menyimpan seluruh provenance enrichment. Jalur KG juga memperlakukan daftar ID penulis sumber sebagai NIP. Bukti kode ada di [design.md](design.md).

ING001 menetapkan kontrak database canonical sebelum pekerjaan ringkasan, KG, dan jawaban. Kontrak ini diperlukan agar publikasi sah tetap tersimpan dan bukti rekomendasi dapat ditelusuri.

## Perubahan yang direncanakan

- Gunakan identitas internal `Author` bagi semua penulis, dengan profil `Lecturer` hanya bagi dosen UNESA yang identitas institusinya terverifikasi.
- Simpan profil dan record sumber dengan namespace `(source, external_id)` atau fallback locator tercatat.
- Pertahankan ID publikasi ketika judul berubah atau DOI baru ditemukan; DOI bersifat opsional.
- Simpan snapshot raw, hasil normalisasi, bukti authorship, konflik nilai, dan provenance setiap field.
- Pertahankan publikasi sah yang incomplete; bedakan metadata kurang, record malformed, dan kesiapan KG.
- Proses hasil valid otomatis ke database. Identitas ambigu tetap unresolved tanpa antrean review manusia.
- Sediakan mapping ID lama dan migrasi bertahap dengan dry run, backup, serta prosedur pemulihan.

## Batas pekerjaan

ING001 menggunakan ETL yang ada; implementasinya memperbaiki adapter dan kontrak storage. Rancangan ini belum menjalankan scraping, migrasi, atau perubahan data.

KG001 berikutnya menangani ringkasan Inggris 2-4 kalimat dari judul/abstrak asli, ekstraksi semantik hanya dari ringkasan, validasi otomatis, dan penulisan KG. ANS001 menangani chat, hasil terstruktur, serta graf bukti yang dapat diperluas. Scheduler mingguan dan rerun manual seluruh pipeline mengikuti rancangan orkestrasi tersebut.

Cakupan produk ialah data UNESA yang tersedia dari sumber terhubung; Sains Data menjadi sampel validasi awal. Kontrak ini tidak menyatakan indeks seluruh UNESA sudah lengkap.

## Dampak dan penyelesaian

Model logical baru memengaruhi loader PostgreSQL, adapter metadata, dan pembaca ID legacy. Skema fisik serta strategi cutover ditetapkan setelah inventaris database pada lingkungan implementasi.

Pekerjaan selesai setelah requirement pada [spec.md](specs/academic-data/spec.md) terbukti melalui [verification.md](verification.md), tugas pada [tasks.md](tasks.md) selesai, dan wiring ETL nyata lulus smoke test pada lingkungan yang dapat dipulihkan.
