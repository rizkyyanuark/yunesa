# DEP-001: deployment awal pada server 2 GB

Tanggal keputusan: 2026-10-09 (Asia/Jakarta).
Status 10 Oktober 2026: deployment baseline, gate produksi, rollback release, dan restore PostgreSQL terisolasi Passed dalam scope bukti di bawah.

## Tujuan dan keputusan

Pemilik produk memilih server 2 GB yang sudah tersedia, Memgraph dan Qdrant lokal, serta provider Gemini dan SiliconFlow. Domain aktif ialah `yunesa.tugasakhir.space`. Snapshot akhir produksi pada 13:44:33 Asia/Jakarta mencatat RAM total 1.835 MiB, tersedia 776 MiB, swap terpakai 336 MiB, dan disk tersedia 17,05 dari 37,7 GiB. Ini merupakan pengukuran smoke baseline, bukan bukti kapasitas concurrency atau beban berkepanjangan.

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

## Hasil acceptance 10 Oktober 2026

Pipeline 36 untuk source `a8052647081a8af87d211fe14414cdcbb1d9f387` menghasilkan build job 132, integration job 133, dan deploy job 134 berstatus success. Deploy selesai pada 13:29:52 Asia/Jakarta dengan release `a8052647081a8af87d211fe14414cdcbb1d9f387-20261010062931`. Redeploy job 136 selesai pada 13:33:08 dengan release kedua `a8052647081a8af87d211fe14414cdcbb1d9f387-20261010063150` dan backup release sebelumnya.

| Kontrak | Status | Batas bukti |
|---|---|---|
| DEP-R01 | Passed | Build/publish dan runtime image ARM64 bertag commit dengan digest; build berjalan pada host terpisah. |
| DEP-R02 | Passed untuk baseline | PostgreSQL/Redis roundtrip, Memgraph `RETURN 1`, Qdrant listing dengan collections=0, serta MinIO S3 dan proxy object berhasil. Ini belum membuktikan pembangunan KG atau pengisian indeks. |
| DEP-R03 | Passed untuk jalur HTTP | HTTPS publik, frontend, login/me, penolakan tanpa token, thread CRUD, serta respons chat tersimpan berhasil. Browser landing/login diamati; submit login UI dan penerimaan Terms belum diuji. |
| DEP-R04 | Passed | Gemini `gemini-flash-latest` dan embedding `siliconflow/Qwen/Qwen3-Embedding-0.6B` dipanggil melalui client nyata. Credential invalid dalam environment child process menghasilkan chat error dan embedding unavailable. |
| DEP-R05 | Passed untuk rollback release dan restore PostgreSQL | State baru terpisah, backup, redeploy, rollback job 135, persistence canary setelah rollback, dan restore PostgreSQL terisolasi dari backup aktual terbukti. Storage lain baru diperiksa checksum. |
| DEP-R06 | Passed untuk gate deployment | Build, integration terisolasi, deploy ter-serialisasi, dan kegagalan gate tercatat. Deploy 130 gagal saat HTTPS readiness mendapat Cloudflare 403; request kini memakai identitas HTTP `Yunesa-Deployment-Readiness/1.0`, lalu gate 133/134 Passed. |
| DEP-R07 | Passed untuk smoke baseline | Server tetap t4g.small 2 GB, ETL/Airflow mati, dan snapshot RAM/swap/disk dicatat. Load/concurrency belum diuji. |

Rollback job 135 selesai pada 13:35:58 Asia/Jakarta dan mengembalikan current ke release pertama `a8052647081a8af87d211fe14414cdcbb1d9f387-20261010062931`; release kedua menjadi previous. Canary thread `42c6d9dd-312e-4b8e-b91e-4a37c3f7acbe` tetap terbaca melalui HTTPS setelah rollback. Identitas source deployment tersebut berbeda dari commit dokumentasi berikutnya.

DEP-T08 Passed untuk mekanisme rollback dua release dengan source dan tiga digest yang sama, serta restore PostgreSQL terisolasi dari backup `/opt/yunesa-app/backups/20261010T063155Z/`. Delapan checksum backup terverifikasi; hasil restore memuat users=1, knowledge_bases=0, canary=1, checkpoints=16, blobs=10, writes=22, dan migrations=10. Canary produksi kemudian dihapus lewat API publik terautentikasi dan ketiadaannya diverifikasi. Resource restore dan CI milik latihan telah dibersihkan.

Scope pemulihan ini tidak mencakup kompatibilitas lintas versi/schema, restore storage selain PostgreSQL, restore legacy, PostgreSQL roles/ACL, atau pemulihan credential/config/autentikasi aplikasi pada host baru. Acceptance ING-001/KG-001/ANS-001 berada di luar bukti baseline ini.

Rincian hasil dan command tersedia pada [catatan bukti DEP-001](../../../docs/evidence/dep-001-2026-10-10.md). Rincian desain ada pada [design.md](design.md), pekerjaan pada [tasks.md](tasks.md), dan prasyarat operasi pada [panduan deployment](../../../docs/deployment.md).
