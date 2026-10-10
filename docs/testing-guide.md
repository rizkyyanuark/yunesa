# Panduan pengujian manual Yunesa

Kolega menjalankan pengujian dan mengisi [template laporan](testing-report-template.md). Dokumen ini memberi langkah pemeriksaan; keberadaan checklist tidak berarti hasilnya sudah lulus.

Perbaikan dark mode disiapkan lokal dan belum dideploy. Untuk menguji hasil perbaikan, gunakan build lokal dari branch perbaikan atau tunggu release yang memuatnya. Hasil dari produksi sebelum deployment adalah baseline sebelum perbaikan, bukan hasil retest.

## Sebelum mulai

- Catat URL yang benar-benar diuji, tanggal/jam beserta zona waktu, browser dan versinya, OS, ukuran viewport dalam pixel CSS, zoom, serta tema aplikasi dan OS. URL produksi: [yunesa.tugasakhir.space](https://yunesa.tugasakhir.space).
- Minta pemilik deployment memberikan commit/release yang sedang aktif. Commit checkout lokal dapat berbeda dari release produksi. Jika identitas build belum diketahui, tulis `Unknown`, lalu minta informasi tersebut sebelum menyimpulkan hasil perbaikan.
- Gunakan akun uji yang diberikan pemilik aplikasi. Halaman `/extensions` memerlukan SuperAdmin; akun tanpa hak tersebut diarahkan ke `/agent`. Jika akses tidak tersedia, catat `Blocked`, jangan mengubah role sendiri.
- Mulai dengan browser normal, zoom 100%, dan viewport desktop. Ulangi bagian visual utama pada lebar sekitar 390 pixel CSS serta zoom 150% dan 200%. Catat ukuran sebenarnya; jika perangkat kedua tidak tersedia, tandai pemeriksaannya `Not run`.
- Zoom harus memakai kontrol bawaan browser. CSS `zoom` atau viewport yang diperkecil hanya menjadi bukti reflow terpisah; jangan melabelinya sebagai zoom browser. Jika kontrol otomatis tidak mendukung zoom, catat subpemeriksaan tersebut `Not run` dan kasus yang belum lengkap `Blocked`.
- Pakai data uji tanpa informasi pribadi. Jangan mengubah model/provider, memasang MCP/Skills, menjalankan ingestion, atau mengganti konfigurasi produksi untuk membuat pemeriksaan lulus.

Tema dipilih dari menu avatar/profil, lalu `Switch to dark mode (Beta)` atau `Switch to light mode`. Pilihan tema disimpan pada browser yang sama; pilihan eksplisit aplikasi harus tetap berlaku sesudah refresh dan perpindahan halaman.

## Prioritas: dark mode Extension Management

Buka `/extensions`. Tab yang tersedia adalah **Tools**, **MCP**, **Subagents**, dan **Skills**. Simpan satu screenshot utuh dengan tab, sidebar, dan area detail terlihat, kemudian satu crop bila diperlukan untuk menunjukkan masalah.

Fokus penerimaan perbaikan ini: latar sidebar keempat tab, gradasi header detail Subagents, dan kotak kode `System Prompt`. Pengujian visual tidak memerlukan pemanggilan model berbayar.

Rujukan warna sidebar mengikuti [source Yuxi pada commit 031e2c7](https://github.com/xerrors/Yuxi/blob/031e2c72681edb8f95f71b60ceb66881f7915b8d/web/src/assets/css/extensions.less): surface dan border berasal dari token tema. Gunakan hasil yang diharapkan di tabel untuk menilai Yunesa; versi dan tata letak Yuxi sudah berbeda.

| ID | Langkah | Hasil yang diharapkan |
|---|---|---|
| DM-01 | Aktifkan dark mode. Buka keempat tab secara berurutan, pilih item yang tersedia, lalu scroll daftar dan detail. | Sidebar, detail, header, border, scrollbar, dan kartu menggunakan warna tema gelap yang selaras; tidak ada bidang putih/abu terang luas dari tema terang. Teks dan status tetap terbaca. |
| DM-02 | Tools: pilih `Ask User Question` bila tersedia. Baca Description, Usage guidelines, serta contoh kode dari atas hingga bawah. | Latar daftar dan detail konsisten; teks biasa maupun kode dapat dibaca; highlight item terpilih tidak menyamarkan tulisan. |
| DM-03 | Subagents: pilih `research-agent` bila tersedia, kemudian item lain. Periksa header detail, `System Prompt`, Description, dan Tools. | Header tidak memiliki gradasi ke putih; kotak System Prompt memiliki latar gelap dan teks terbaca; area detail tetap konsisten saat item berubah. |
| DM-04 | Pada setiap tab, gunakan pencarian dengan nama yang tersedia, kemudian istilah yang tidak cocok, lalu kosongkan pencarian. Tekan tombol refresh satu kali. | Hasil pencarian, keadaan kosong, loading yang sempat terlihat, serta hasil refresh mengikuti tema; pencarian dapat dipulihkan. Error yang muncul dicatat, tidak dianggap hasil kosong yang berhasil. |
| DM-05 | Hover kartu/tab/tombol, buka filter atau menu yang tersedia, lalu tutup. Gunakan Tab/Shift+Tab dan Enter/Space pada kontrol yang dapat difokuskan; Escape pada dialog. | Hover, item terpilih, popover/dialog, dan fokus keyboard tetap terlihat tanpa latar putih yang menyilaukan. Kontrol yang tidak dapat dipakai melalui keyboard dicatat sebagai temuan. |
| DM-06 | Dari halaman yang sama, ubah dark ke light, lalu kembali ke dark. Refresh; pindah ke `/agent`, lalu kembali ke Extensions. | Kedua tema berubah tanpa sisa warna tema sebelumnya. Tema terakhir bertahan sesudah refresh dan navigasi. Jika muncul kilatan putih, lampirkan rekaman singkat. |
| DM-07 | Ulangi DM-01 sampai DM-03 dalam light mode. | Teks, kode, kartu, status, dan border tetap terbaca; perbaikan dark mode tidak menggelapkan panel light mode. |
| DM-08 | Pada viewport sempit dan zoom 150% serta 200%, ulangi Tools/Subagents, tab switching, serta scroll. | Judul, tab, pencarian, dan detail dapat dijangkau; tidak ada konten terpotong yang tidak dapat diakses atau halaman overflow tanpa kebutuhan. Catat perilaku sidebar dan scroll sebenarnya. |

Jika item MCP/Skills tidak tersedia, periksa keadaan kosong dan tulis keterbatasan pemeriksaan detail. Jangan memasang extension untuk memenuhi checklist. Gambar/logo yang memang memiliki warna terang bukan otomatis bug; tunjukkan elemen UI yang salah mengikuti tema.

## Opsional: regresi aplikasi singkat

Jalankan bagian ini hanya bila pemilik aplikasi meminta regresi fungsional. Acceptance dark mode cukup memakai DM-01 sampai DM-08; kasus opsional yang tidak dijalankan tetap `Not run`. CHAT-01 memanggil provider nyata dan dapat memakai kuota berbayar, sehingga satu percakapan singkat sudah cukup.

| ID | Langkah | Hasil yang diharapkan |
|---|---|---|
| AUTH-01 | Dalam jendela privat tanpa login, buka `/extensions` dan `/agent`. Login memakai akun uji yang sah, lalu Sign Out. | Halaman terlindungi meminta login. Setelah login, halaman sesuai role dapat dibuka. Setelah Sign Out, halaman terlindungi kembali meminta login. Catat redirect dan error sebenarnya. |
| CHAT-01 | Buka `/agent`, pilih agent yang tersedia, lalu `Create New Chat`. Kirim satu pesan singkat tanpa tool, misalnya `Balas dengan satu kalimat salam.` Tunggu sampai respons selesai. | Pesan terkirim, indikator proses berakhir, dan respons assistant terlihat. Error provider/worker memiliki pesan yang dapat dipahami. Catat durasi dan ID percakapan/run bila tersedia; tidak perlu mengulang banyak request berbayar. |
| STATE-01 | Pada percakapan uji tadi, refresh dan buka ulang dari riwayat. Rename judul dengan prefix `QA-`, lalu refresh lagi. Hapus hanya percakapan buatan penguji dan periksa riwayat. | Pesan dan judul bertahan sesudah refresh; percakapan yang dihapus tidak kembali di riwayat. Simpan bukti sebelum cleanup. |

Baseline produksi saat ini menjalankan web/API, worker, PostgreSQL, Redis, Memgraph, Qdrant, dan MinIO pada server 2 GB. ETL/Airflow tidak aktif. Ingestion akademik, pembangunan indeks, dan jawaban berbasis KG belum diterima sebagai fitur siap uji; jika dijadwalkan, catat `Blocked` dengan alasan tersebut. Chat umum yang berhasil tidak membuktikan retrieval akademik. Upload file, query database langsung, dan restore data memerlukan skenario terpisah dari pemilik aplikasi; laporkan sebagai `Not run` bila tidak diminta. Lihat [batas deployment](deployment.md).

## Isi laporan dan bukti

Status tiap kasus: **Pass** bila hasil sesuai dan ada bukti, **Fail** bila berbeda, **Blocked** bila prasyarat menghalangi pemeriksaan, atau **Not run** bila belum dijalankan. Jangan menyimpulkan seluruh fitur lulus berdasarkan satu halaman.

Untuk setiap temuan, isi langkah bernomor, expected/actual, frekuensi (misalnya 3 dari 3 percobaan), dampak, severity, dan bukti. Gunakan:

- **S1**: layanan tidak dapat dipakai, kehilangan data, atau akses yang tidak berhak.
- **S2**: alur utama atau teks penting tidak dapat digunakan/dibaca.
- **S3**: visual tidak konsisten atau masalah memiliki cara sementara untuk melanjutkan.
- **S4**: detail kosmetik kecil tanpa hambatan penggunaan.

Nama bukti disarankan `BUG-001-dark-subagents-desktop.png`. Screenshot harus menunjukkan konteks dan area masalah; crop tambahan boleh memperjelasnya. Untuk error, buka DevTools Console/Network dan ambil pesan, method/path, HTTP status, waktu, serta request/trace ID bila ada. Jangan menyertakan password, API key, token, Authorization, cookie, URL bertoken, data pribadi, atau HAR mentah. Jika HAR dibutuhkan, pemilik aplikasi harus meninjau sanitasi sebelum dibagikan.

Kirim satu bundle `yunesa-qa-YYYYMMDD.zip` berisi `report.md` dari template, folder `screenshots/`, rekaman singkat bila diperlukan, dan `logs-sanitized/` untuk error. Pada pengujian ulang, sebutkan build baru dan BUG-ID lama agar hasil sebelum/sesudah dapat dibandingkan. Berikan bundle kepada pemilik aplikasi untuk direview bersama; dokumen ini tidak mengirim pesan kepada kolega.

Sebelum packaging, jalankan pemeriksaan JSON dari root repository:

```powershell
python scripts/sanitize-qa-evidence.py --write screenshots/sanitized-network-logs.json
python scripts/sanitize-qa-evidence.py --check screenshots/sanitized-network-logs.json
```

Tambahkan semua file JSON bukti yang akan dibagikan sebagai argumen. Pada `--check`, exit 0 berarti tidak ada redaksi tambahan yang dikenali dan exit 1 berarti masih perlu redaksi. `--write` menghasilkan exit 0 setelah sanitasi berhasil; exit 2 berarti file tidak dapat diperiksa atau ditulis. Periksa screenshot secara visual; script tidak memeriksa gambar. Cantumkan HEAD dan hash file bila source masih berupa worktree yang belum di-commit, dan bedakan URL frontend dari backend proxy. Jangan menyebut pengujian lokal terisolasi bila API yang dipakai adalah produksi.
