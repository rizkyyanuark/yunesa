# ANS-001 — Jawaban akademik dengan graph bukti

Status: **direncanakan**. Proposal ini mencatat kontrak target; belum menyatakan fitur lolos pengujian.

Dependensi: [ING-001](../ing-001-academic-data/proposal.md) untuk identitas dan sumber; [KG-001](../kg-001-knowledge-graph/proposal.md) untuk konsep, graph, indeks, dan versi bukti.

Acuan produk: [PRD](../../../PRD.md). Peta komponen: [arsitektur](../../../ARCHITECTURE.md).

## Masalah dan tujuan

Mahasiswa perlu menemukan dosen UNESA yang relevan dengan topik penelitian dan memeriksa dasar jawabannya. Daftar dosen tanpa publikasi pendukung atau graph yang tidak terkait klaim belum memenuhi kebutuhan ini.

Perubahan ini menyediakan alur topik penelitian → dosen → alasan relevansi → publikasi → graph bukti. Cakupan data tetap lintas prodi UNESA sesuai indeks yang tersedia, dengan pengujian awal pada Sains Data.

## Cakupan dan batas

- Gunakan akun aplikasi Yunesa dan pemeriksaan akses di server.
- Jawaban mengambil bukti dari indeks yang sudah diproses; tidak mencari web langsung.
- Tampilkan hasil terstruktur bersama chat, graph terfokus, dan perluasan hubungan sesuai permintaan.
- Sertakan waktu pembaruan dan batas cakupan data yang diketahui.
- Tidak menyimpulkan ketersediaan pembimbing, kerja sama aktif, atau kualitas dosen dari kepenulisan saja.
- Dashboard persetujuan admin dan klaim peningkatan performa tidak termasuk proposal ini.

## Kebutuhan dan penerimaan yang direncanakan

### ANS-R01 — Akun dan kepemilikan percakapan

Chat, riwayat, dan bukti yang melekat pada percakapan mengikuti identitas pengguna. Server memeriksa autentikasi serta kepemilikan; penyembunyian kontrol UI tidak menjadi pengaman akses.

Penerimaan: pengunjung yang belum login dan akun lain tidak dapat membaca atau mengubah percakapan privat melalui penggantian ID request. Kebijakan akses data akademik umum ditetapkan terpisah dari kepemilikan percakapan.

### ANS-R02 — Topik mahasiswa menuju hasil yang dapat diperiksa

Pertanyaan topik menghasilkan dosen UNESA yang identitasnya terverifikasi, alasan relevansi yang didukung data, dan publikasi pendukung. Penulis luar boleh tampil sebagai konteks kolaborasi dengan penanda perannya.

Penerimaan: setiap rekomendasi memiliki jalur kepenulisan ke publikasi pendukung. Penulis belum terpetakan tidak dipromosikan menjadi dosen UNESA. Publikasi bersama dijelaskan sebagai kepenulisan bersama, tanpa klaim relasi sosial tambahan.

### ANS-R03 — Bukti dari indeks dan pencarian lintas bahasa

Retrieval hanya memakai data siap pakai pada versi indeks yang diketahui. Pertanyaan bahasa Indonesia dapat mencari konsep dan ringkasan Inggris. Strategi lintas bahasa dipilih berdasarkan pengujian; terjemahan istilah tidak boleh menambah fakta.

Penerimaan: pasangan pertanyaan Indonesia dan Inggris pada sampel yang sama dinilai terhadap publikasi rujukan yang ditetapkan. Jejak retrieval mencatat versi indeks. Tidak ada hasil web langsung yang disisipkan ke jawaban sebagai bukti indeks.

### ANS-R04 — Klaim, graph, dan sumber merujuk bukti yang sama

Klaim faktual memiliki ID bukti yang menghubungkannya dengan publikasi, entitas/relasi, dan teks pendukung. Graph awal menampilkan bukti yang dipakai jawaban; hasil eksplorasi tambahan diberi konteks sebagai perluasan.

Penerimaan: membuka klaim atau relasi mengarah ke bukti yang sesuai, bukan hanya judul paper yang mirip. Klaim tanpa dukungan tidak ditampilkan sebagai fakta. Ringkasan hasil AI dibedakan dari kutipan asli sumber.

### ANS-R05 — Graph terfokus dan dapat diperluas

Tampilan awal membatasi graph pada jalur pendukung jawaban. Pengguna dapat membuka hubungan tambahan dan melihat arti node/relasi serta sumbernya. Node tambahan tidak otomatis dianggap mendukung jawaban awal.

Penerimaan: contoh jawaban memiliki subgraph yang dapat ditelusuri dari dosen ke paper dan konsep. Perluasan tidak mengubah identitas node atau menghapus fokus bukti awal. Batas jumlah node dan strategi pemuatan ditetapkan saat desain.

### ANS-R06 — Kekosongan bukti, cakupan, dan kegagalan dibedakan

Bedakan bukti tidak ditemukan, cakupan data belum diketahui/belum lengkap, dan layanan gagal. Jawaban tidak menyimpulkan bahwa dosen atau riset tidak ada hanya karena indeks tidak memberi hasil.

Penerimaan: skenario indeks kosong, prodi belum terindeks, data belum diperbarui, dan layanan gagal menampilkan kondisi berbeda serta langkah lanjutan yang sesuai. Kegagalan tidak diubah menjadi jawaban sukses kosong.

### ANS-R07 — Bukti jawaban lama tetap dapat ditelusuri

Jawaban menyimpan referensi versi publikasi, ringkasan, hasil ekstraksi, dan indeks yang dipakai. Pembaruan data tidak mengganti bukti historis secara diam-diam; koreksi atau keterbatasan bukti lama ditampilkan jika relevan.

Penerimaan: setelah pembaruan paper atau pembangunan ulang KG, percakapan lama tetap membuka versi bukti yang dirujuk. Jika bukti harus dihapus sesuai kebijakan retensi, sistem menjelaskan ketidaktersediaannya dan tidak mengalihkan ke versi berbeda seolah sama.

### ANS-R08 — Graph dapat dipahami melalui teks dan keyboard

Sediakan daftar atau tabel hubungan yang setara dengan graph, nama kontrol yang jelas, navigasi keyboard, fokus terlihat, serta kondisi loading, kosong, dan gagal yang dapat dipahami. Warna bukan satu-satunya pembeda jenis node atau status.

Penerimaan: pengguna dapat memeriksa dosen, publikasi, relasi, dan sumber tanpa mouse atau pemahaman posisi visual graph. Pemeriksaan aksesibilitas mencakup fokus, kontras, pembacaan teks, dan pembesaran 200%; hasilnya dicatat tanpa klaim kepatuhan menyeluruh sebelum audit.

## Hal yang harus diselesaikan sebelum implementasi

- Selesaikan versi bukti dan kontrak ID pada ING-001/KG-001.
- Petakan payload chat, renderer graph, dan penyimpanan riwayat yang sudah ada.
- Tetapkan cara mengaitkan klaim jawaban dengan ID bukti, termasuk saat streaming.
- Pilih strategi retrieval lintas bahasa melalui fixture dan evaluasi yang dapat diulang.
- Tentukan indikator cakupan data, arti waktu pembaruan, batas graph, dan retensi bukti.
- Pastikan sumber publikasi bisa dibuka atau tampilkan keterangan ketika tautan sumber tidak tersedia.

## Verifikasi dan batas bukti

Susun skenario Sains Data dengan pertanyaan, publikasi rujukan, penulis yang benar, dan bukti relasi yang diperiksa. Lengkapi dengan kasus nama serupa, metadata kurang, tanpa bukti, kegagalan layanan, dan akses antarakun. Fixture deterministik menguji kontrak; pemeriksaan provider nyata menguji integrasi.

Catat hasil lulus, hanya diperiksa, belum dijalankan, dan kesimpulan tidak langsung secara terpisah. Nilai mutu jawaban, keterlacakan bukti, dan kegunaan graph berdasarkan hasil pengujian; target numerik serta klaim peningkatan ditetapkan setelah baseline diukur.
