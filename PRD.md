# Yunesa: PRD v0.1

Tanggal keputusan: 9 Oktober 2026 (Asia/Jakarta).
Status: arah produk disepakati; implementasi dan verifikasi mengikuti setiap spesifikasi perubahan.

Yunesa membantu mahasiswa UNESA menemukan dosen yang relevan dengan topik penelitian melalui publikasi pendukung dan graph bukti yang dapat diperiksa.

## Pengguna dan masalah

Pengguna utama adalah mahasiswa UNESA yang mempunyai topik atau minat penelitian dan ingin menemukan dosen beserta karya yang mendukung relevansinya. Hasil harus menjelaskan hubungan dosen, publikasi, dan konsep penelitian.

Cakupan produk meliputi lintas prodi berdasarkan data UNESA yang tersedia dalam indeks. Sains Data menjadi sampel validasi awal. Cakupan ini tidak menyatakan bahwa seluruh publikasi UNESA sudah tersedia.

Penulis luar UNESA dapat muncul sebagai konteks kepenulisan dan kolaborasi ketika buktinya tersedia. Penulis tersebut tidak otomatis menjadi dosen UNESA.

## Alur utama

1. Mahasiswa login dengan akun aplikasi Yunesa.
2. Mahasiswa mengajukan topik atau pertanyaan, termasuk dalam bahasa Indonesia.
3. Sistem mencari bukti pada indeks yang sudah dibangun.
4. Sistem menampilkan dosen yang relevan, alasan yang didukung bukti, dan publikasi pendukung.
5. Graph menampilkan hubungan yang mendukung jawaban tersebut terlebih dahulu.
6. Mahasiswa membuka sumber atau memperluas graph untuk memahami konteks tambahan.

Graph dan sitasi memakai identitas serta versi bukti yang konsisten dengan jawaban. Relasi hasil ekstraksi ditandai sebagai hasil pengolahan teks; ringkasan AI tidak ditampilkan sebagai kutipan langsung dari abstrak.

## Kebutuhan produk

| ID | Kebutuhan | Spesifikasi |
|---|---|---|
| PRD-R01 | Login aplikasi dan pembatasan akses diterapkan pada server, termasuk artefak percakapan. | [ANS-001](openspec/changes/ans-001-evidence-answers/proposal.md) |
| PRD-R02 | Pencarian topik menghasilkan dosen dan publikasi pendukung yang dapat diperiksa. | ANS-001 |
| PRD-R03 | Jawaban menyertakan graph bukti terfokus yang dapat diperluas. | ANS-001 |
| PRD-R04 | Jawaban menggunakan indeks Yunesa; tidak beralih diam-diam ke pencarian web langsung. | ANS-001 |
| PRD-R05 | Data identitas, kepenulisan, publikasi, dan sumber tetap konsisten setelah pembaruan. | [ING-001](openspec/changes/ing-001-academic-data/proposal.md) |
| PRD-R06 | ETL Scholar/Scopus yang ada menjadi dasar pengembangan; publikasi valid yang belum lengkap tetap tersimpan dengan status. | ING-001 |
| PRD-R07 | Satu identitas Author dapat mempunyai profil Lecturer UNESA terverifikasi dan beberapa profil sumber. | ING-001 |
| PRD-R08 | Ringkasan Inggris sekitar 2–4 kalimat dari judul dan abstrak menjadi satu-satunya input ekstraksi semantik. | [KG-001](openspec/changes/kg-001-knowledge-graph/proposal.md) |
| PRD-R09 | Ontologi aplikasi yang ada menjadi baseline, dengan perluasan Author dan profil Lecturer yang dinyatakan eksplisit. | KG-001 |
| PRD-R10 | Ekstraksi yang lolos validasi otomatis langsung disimpan; tidak ada antrean pemeriksaan manusia. | ING-001, KG-001 |
| PRD-R11 | Pipeline berjalan mingguan, dapat dipicu manual, dan melanjutkan paper lain ketika satu paper gagal. Percobaan ulang dibatasi. | KG-001 |
| PRD-R12 | Bukti tidak tersedia, cakupan indeks terbatas, dan kegagalan layanan disampaikan sebagai keadaan berbeda. | ANS-001 |

## Kontrak data dan pengetahuan

- ID internal stabil; perubahan DOI, nama, judul, atau afiliasi tidak boleh memutus referensi lama.
- Pemetaan profil sumber memakai pasangan sumber dan ID eksternal. Nama yang sama tidak cukup untuk menyatukan orang.
- DOI boleh kosong. Deduplikasi publikasi membutuhkan bukti kesamaan; kemiripan judul saja tidak cukup.
- Informasi asli tiap sumber tetap dapat ditelusuri, termasuk konflik nilai dan waktu pengambilan.
- Identitas ambigu disimpan sebagai belum terselesaikan dan dievaluasi ulang saat bukti baru tersedia. Tidak ada langkah review admin wajib.
- Kelengkapan metadata, kepastian identitas, kesiapan KG, dan hasil proses merupakan status yang berbeda.
- Publikasi belum lengkap dapat tampil sebagai metadata dengan penjelasan keterbatasannya. Record tersebut belum menjadi bukti bagi klaim yang tidak didukung.
- Judul, abstrak, dan kata kunci asli tetap tersimpan. Semua jalur ekstraksi semantik menggunakan ringkasan Inggris yang sudah valid.
- Metadata terverifikasi membentuk relasi struktural. Konsep dan relasi semantik berasal dari ringkasan menurut ontologi.
- Kategori ontologi yang tidak didukung sumber boleh kosong. Angka, nama teknis, negasi, dan tingkat kepastian dipertahankan.
- Hasil dan metrik tetap berada dalam konteks paper/eksperimennya. Kepenulisan bersama tidak membuktikan kerja sama aktif atau hubungan pembimbing.
- Skor model bukan bukti kebenaran. Pemeriksaan otomatis mencakup struktur, referensi, dan dukungan teks; mutu aktual diuji dengan sampel.

## Cakupan versi awal

Termasuk: penguatan ingestion dan identitas, ringkasan Inggris, KG dan indeks yang dapat ditelusuri, serta satu alur mahasiswa dari topik ke dosen dan graph bukti.

Tidak menjadi pekerjaan versi ini: platform RAG lintas organisasi, platform agen umum, SSO kampus, chat tamu, pencarian web saat menjawab, dashboard review manusia, redesign seluruh UI, atau deployment produksi otomatis. Kemampuan warisan dalam kode tidak otomatis menjadi komitmen produk.

## Penerimaan produk

- Batch yang sama dapat dijalankan ulang tanpa menambah duplikat atau merusak referensi.
- Nama penulis yang serupa tidak menghasilkan pemetaan identitas yang tidak terbukti.
- Publikasi lintas sumber mempertahankan semua asal metadata yang dipakai.
- Judul/abstrak Indonesia menghasilkan ringkasan Inggris yang setia pada sumber; konsep yang tidak disebut tidak dibuat.
- Paper yang tidak siap atau gagal memiliki alasan yang bisa ditelusuri; paper lain tetap berjalan.
- Mahasiswa dapat menelusuri setiap rekomendasi dosen ke publikasi dan hubungan yang mendukungnya.
- Sitasi, graph, dan jawaban merujuk bukti yang sama, termasuk setelah pembaruan indeks.
- Pengujian mencakup pertanyaan Indonesia, hasil kosong, layanan gagal, login, dan kepemilikan percakapan.
- Graph mempunyai alternatif teks yang menyampaikan hubungan dan sumber, serta interaksi keyboard yang dapat digunakan.

## Ukuran keberhasilan

Catat rasio duplikasi, cakupan pemetaan penulis, kelengkapan metadata, kegagalan per tahap, kesetiaan ringkasan, ketepatan entitas/relasi, kecocokan sitasi dan graph, latensi, serta biaya per batch/query. Setiap pengukuran harus menyertakan dataset, versi, metode, dan penyebutnya.

Target angka belum ditetapkan. Ukur baseline pada sampel Sains Data sebelum menentukan ambang rilis; jangan menulis persentase akurasi atau peningkatan performa tanpa pengukuran.

## Urutan pengembangan

1. ING-001: kontrak dan integrasi data akademik.
2. KG-001: ringkasan, ekstraksi ontologi, pembangunan KG, indeks, dan orkestrasi.
3. ANS-001: jawaban mahasiswa dan graph bukti.

[Kondisi kode dan target arsitektur](ARCHITECTURE.md) memisahkan observasi implementasi dari rancangan. [Alur SDD](docs/development.md) menjelaskan cara mengubah kebutuhan menjadi bukti yang dapat ditinjau.

