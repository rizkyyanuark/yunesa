# DEP-001: deployment awal pada server 2 GB

Tanggal keputusan: 2026-10-09 (Asia/Jakarta).
Status: cakupan disepakati; implementasi dan acceptance deployment belum selesai.

## Tujuan dan keputusan

Pemilik produk memilih server 2 GB yang sudah tersedia, Memgraph dan Qdrant lokal, serta provider Gemini dan SiliconFlow. Domain target ialah `yunesa.tugasakhir.space`. Inspeksi sesi mencatat RAM terpakai 1.230 MB sebelum cleanup stack lama; angka tersebut belum menjadi pengukuran release baru.

DEP-001 menyiapkan web, API, storage, dan pipeline GitLab untuk deployment baseline. Worker Arq tetap diperlukan jika alur chat menjalankan pekerjaan lewat queue. ETL, Airflow, scraper, dan konstruksi indeks otomatis belum diaktifkan.

## Batas pekerjaan

- Build image di runner terpisah dan deploy image dengan identitas commit ke server aplikasi.
- Terapkan konfigurasi Memgraph/Qdrant secara eksplisit, secret lokal, akses domain, readiness, backup, dan rollback.
- Gunakan deployment baru dengan state baru yang terpisah dari volume release lama. Volume dan image lama tetap dipertahankan; DEP-001 tidak memigrasikan atau menghapus data lama.
- Pertahankan server 2 GB tanpa upgrade atau pemindahan storage ke layanan eksternal.
- Jangan menyatakan ING-001, KG-001, atau ANS-001 selesai melalui deployment ini. Kemampuan yang masih terikat Milvus memerlukan perubahan tersendiri sebelum dipakai pada Qdrant.

## Kontrak penerimaan

| ID | Kontrak yang harus dibuktikan | Bukti yang diperlukan |
|---|---|---|
| DEP-R01 | Build API/web mempunyai tag commit dan platform yang cocok dengan server; runner tidak menjalankan build pada server aplikasi. | Log build, manifest image, dan identitas image container. |
| DEP-R02 | Konfigurasi runtime memilih Qdrant secara eksplisit dan query Memgraph yang dipakai baseline berhasil. | Probe layanan dan pemanggilan API nyata dengan konfigurasi tanpa secret. |
| DEP-R03 | Domain menyajikan frontend dan API melalui jalur proxy aplikasi; login dan akses server bekerja. | HTTP/browser domain, login/me, serta penolakan request tanpa token. |
| DEP-R04 | Provider Gemini/SiliconFlow dipakai pada peran yang dikonfigurasi tanpa fallback sukses palsu. | Satu alur nyata untuk setiap peran provider yang diaktifkan, berikut failure path tanpa membocorkan key. |
| DEP-R05 | Deployment baru tidak memakai atau mengubah volume lama dan dapat rollback ke release baru sebelumnya. | Inventaris project/volume, manifest release, backup, dan latihan pemulihan terpisah. |
| DEP-R06 | Pipeline hanya menerapkan release yang lolos gate, berjalan satu deployment pada satu waktu, dan gagal jelas ketika secret/readiness belum tersedia. | Log pipeline beserta kegagalan terkontrol dan hasil smoke. |
| DEP-R07 | Stack baseline bertahan pada kapasitas 2 GB dengan ETL/Airflow mati. | RAM, swap, disk, container status, dan observasi selama smoke workload yang dicatat. |

Seluruh kontrak runtime berstatus `NOT RUN` sampai bukti aktual dicatat. Rincian desain ada pada [design.md](design.md), pekerjaan pada [tasks.md](tasks.md), dan prasyarat operasi pada [panduan deployment](../../../docs/deployment.md).
