# KG-001 — Ringkasan dan konstruksi knowledge graph

Status: **direncanakan**. Dokumen ini menyatakan perilaku target; belum menjadi bukti implementasi atau hasil pengujian.

Dependensi: kontrak identitas, publikasi, kepenulisan, dan sumber pada [ING-001](../ing-001-academic-data/proposal.md).

Acuan produk: [PRD](../../../PRD.md). Acuan komponen dan kondisi saat ini: [arsitektur](../../../ARCHITECTURE.md).

## Masalah dan tujuan

Yunesa perlu mengubah metadata publikasi menjadi graph yang mempertahankan konteks paper dan jejak bukti. Metadata lintas bahasa harus melalui ringkasan Inggris yang konsisten sebelum ekstraksi semantik. Setiap pembaruan harus menjaga identitas serta sumber yang sudah tersimpan.

Hasil perubahan ini adalah pipeline yang dapat membangun dan memperbarui KG dari paper yang siap, menyimpan kegagalan per paper, serta menyediakan versi graph dan indeks yang dapat ditelusuri oleh fitur jawaban.

## Cakupan dan batas

- Gunakan ontologi aplikasi yang tercatat dalam arsitektur sebagai baseline, dengan penyesuaian `Author` dan profil/peran `Lecturer` yang telah disepakati.
- Bentuk relasi struktural dari metadata terverifikasi; bentuk relasi semantik dari ringkasan Inggris saja.
- Simpan otomatis hasil yang lolos validasi; kasus belum pasti tetap memiliki status dan alasan.
- Jadwalkan pembaruan mingguan dan sediakan pemicu ulang manual dengan hak akses server.
- Antrean persetujuan manusia dan dashboard review tidak menjadi syarat pipeline.
- Pemilihan backend graph/vector dan rancangan migrasi rinci belum ditetapkan oleh proposal ini.

## Kebutuhan dan penerimaan yang direncanakan

### KG-R01 — Ringkasan Inggris berdasarkan sumber

Judul dan abstrak asli menghasilkan ringkasan Inggris sekitar 2–4 kalimat. Ringkasan mempertahankan nama teknis, angka, negasi, serta tingkat kepastian sumber. Metadata asli tetap tersimpan.

Penerimaan: sampel Sains Data berbahasa Indonesia dan Inggris diperiksa terhadap sumbernya. Ringkasan tidak menambah metode, dataset, hasil, atau klaim yang tidak tersedia. Sumber yang tidak memadai menghasilkan status belum siap dan alasan, bukan ringkasan rekaan.

### KG-R02 — Satu input semantik untuk seluruh extractor

Semua jalur ekstraksi semantik hanya menerima ringkasan Inggris yang valid. Judul, kata kunci, atau abstrak tidak menjadi tambahan maupun fallback tersembunyi. Data terstruktur tetap boleh membentuk relasi kepenulisan dan venue.

Penerimaan: setiap jalur extractor diuji dengan dan tanpa ringkasan valid. Tanpa ringkasan valid, ekstraksi ditunda; tidak ada jalur yang diam-diam membaca sumber lain sebagai input semantik.

### KG-R03 — Ontologi dan identitas yang konsisten

Setiap entitas dan relasi mengikuti versi ontologi yang tercatat. `Author` mewakili semua penulis; profil/peran `Lecturer` terkait hanya jika identitas dosen UNESA terverifikasi. Penulis luar tidak otomatis menjadi dosen UNESA. Kategori tanpa bukti boleh kosong.

Penerimaan: tipe atau relasi yang tidak diizinkan ditolak dari hasil siap pakai. Nama yang sama tidak menggabungkan penulis tanpa bukti. Penggabungan konsep mempertahankan tipe dan makna, bukan hanya kesamaan label.

### KG-R04 — Hasil dan metrik tetap memiliki konteks paper

Klaim hasil atau nilai metrik menyertakan publikasi, metode/model, dataset atau kondisi yang disebutkan, serta bukti teks. Klaim tidak digabung menjadi sifat umum suatu model hanya karena label atau nilainya sama.

Penerimaan: dua paper dengan metrik bernama sama dan nilai/kondisi berbeda tetap dapat dibedakan. Kondisi yang tidak disebut sumber tetap ditandai tidak tersedia.

### KG-R05 — Validasi otomatis dan penyimpanan

Periksa skema, identitas referensi, tipe relasi, bukti teks, dan kesetiaan ringkasan melalui pemeriksaan yang dapat diaudit. Skor keyakinan model bukan satu-satunya syarat lolos. Hasil valid langsung disimpan tanpa persetujuan admin.

Penerimaan: hasil tidak valid atau belum pasti tetap tercatat dengan alasan, tetapi tidak dipublikasikan sebagai bukti jawaban terverifikasi. Ekstraksi yang valid dengan nol konsep juga tercatat; sistem tidak memaksa kategori terisi. Kualitas faktual dinilai melalui evaluasi sampel, bukan diasumsikan dari validasi format.

### KG-R06 — Jejak versi dan dukungan teks

Simpan ID publikasi/sumber, snapshot judul dan abstrak atau referensi versinya, ringkasan, versi model dan prompt, versi ontologi/extractor, waktu proses, serta potongan dan posisi teks pendukung. Rujukan potongan selalu menunjuk versi teks tertentu.

Penerimaan: satu relasi dapat ditelusuri ke keluaran ekstraksi, potongan ringkasan, dan sumber pembentuknya. Potongan ringkasan tidak dilabeli kutipan asli abstrak; pemetaan ke potongan sumber asli hanya disimpan jika benar-benar tersedia dan diperiksa.

### KG-R07 — Pembaruan dan pemulihan per paper

Pipeline berjalan mingguan dan dapat dijalankan ulang manual. Kegagalan satu paper tidak menghentikan paper lain. Percobaan ulang terbatas membedakan kegagalan sementara dari data tidak valid; nilai batas dan jedanya ditetapkan dalam desain.

Penerimaan: kegagalan provider yang disimulasikan tercatat per paper, paper lain selesai, dan percobaan berhenti saat batas tercapai. Pemicu bersamaan atau pengulangan batch tidak menghasilkan duplikasi identitas maupun relasi.

### KG-R08 — Pembaruan graph dan indeks tanpa kehilangan hasil baik

Pembangunan inkremental dan pembangunan ulang menggunakan identitas stabil. Versi ringkasan/ontologi baru menandai hasil turunannya untuk diperbarui. Kegagalan pembaruan tidak mengganti hasil terakhir yang berhasil dengan keluaran parsial.

Penerimaan: pengujian kegagalan di antara penyimpanan, graph, dan indeks membuktikan bahwa versi siap pakai dapat dikenali. Hubungan usang diganti setelah pembaruan berhasil, jejak versi lama tetap dapat dibaca, dan retrieval tidak diam-diam mencampur versi yang tidak cocok.

## Hal yang harus diselesaikan sebelum implementasi

- Pastikan kontrak ING-001 serta pemetaan ID lama ke ID stabil.
- Putuskan backend graph/vector; konfigurasi pengembangan dan produksi saat ini berbeda.
- Inventarisasi seluruh extractor dan proses penulisan untuk menghilangkan fallback semantik.
- Tetapkan representasi hasil/metrik per paper, validasi fidelitas, dan aturan kesiapan yang terukur.
- Tetapkan waktu mingguan, zona waktu, batas retry, serta mekanisme publikasi versi graph/indeks.
- Tentukan pemetaan istilah dengan resource taksonomi yang tersedia tanpa menghilangkan istilah sumber.

## Verifikasi dan batas bukti

Mulai dengan fixture sintetis dan sampel Sains Data yang boleh digunakan, termasuk metadata tidak lengkap, nama serupa, abstrak multilingual, dan kegagalan provider. Uji integrasi memakai backend yang dipilih. Catat terpisah hasil lulus, hanya diperiksa, belum dijalankan, dan kesimpulan tidak langsung.

Tidak ada klaim peningkatan akurasi, kecepatan, atau kesiapan produksi sebelum hasilnya diukur. Konsumsi bukti oleh chat dirinci pada [ANS-001](../ans-001-evidence-answers/proposal.md).
