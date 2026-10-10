# Deployment baseline Yunesa

Pembaruan: 10 Oktober 2026 (Asia/Jakarta). Pipeline 36 pada commit `a8052647081a8af87d211fe14414cdcbb1d9f387` telah lulus build 132, integrasi ARM 133, dan deploy 134 pada 13:29:52. Gate produksi membuktikan HTTPS, auth/persistensi, chat melalui worker, storage, dan kedua provider. Redeploy 136 membuat backup; rollback 135 dan restore PostgreSQL terisolasi passed dengan canary tersimpan. Kontrak perubahan: [DEP-001](../openspec/changes/dep-001-initial-deployment/proposal.md); command, identitas release, serta batas bukti: [bukti DEP-001](evidence/dep-001-2026-10-10.md).

## Keputusan yang berlaku

Server aplikasi tetap 2 GB. Baseline aktif memakai web/API, worker Arq, PostgreSQL, Redis, Memgraph, Qdrant, dan MinIO lokal. Gemini `gemini-flash-latest` untuk chat dan SiliconFlow `Qwen/Qwen3-Embedding-0.6B` untuk embedding telah dipanggil nyata. ETL, Airflow, scraping, dan pembangunan indeks otomatis tetap mati.

Domain [yunesa.tugasakhir.space](https://yunesa.tugasakhir.space) telah melewati login/API auth, thread CRUD, serta chat async dengan respons tersimpan melalui HTTPS. Snapshot pasca-rollback 13:38:49 pada t4g.small: RAM 1.835 MiB total, 771 MiB available, swap used 336 MiB; disk 37,7 GiB total, 17,05 GiB free. Delapan container ARM64 running/healthy, tanpa OOM/restart. Peak cgroup API 384 MiB dan worker 256 MiB mencapai batas RAM masing-masing; current swap API 55,22 MiB, worker 227,44 MiB, PostgreSQL 10 MiB. Stack bergantung pada swap; hasil ini membuktikan smoke, bukan kapasitas beban berkelanjutan.

## Infrastruktur yang telah diinspeksi dalam sesi

| Item | Observasi sesi | Tindak lanjut |
|---|---|---|
| GitLab utama | Project ID 6, `rizkyyanuark/yunesa`, private; `main` protected dengan push/merge Maintainer dan force push mati | Gunakan project ini sebagai source pipeline. |
| Registry project | `registry.tugasakhir.space:443/rizkyyanuark/yunesa` enabled; image ARM64 dengan digest telah dipakai pada integrasi 133 dan deploy 134 | Pertahankan identitas image dalam manifest release. |
| Runner build ID 1 | Tag `arm64-builder`, `docker`, `build`; assigned ke project 6, locked/protected, tidak menerima job tanpa tag | Owner lama project 3 dipertahankan; CI project 3 telah dinonaktifkan. |
| Shell runner deployment ID 2 | Assigned ke project 6, locked/protected, service aktif; wrapper root; online | Deploy 134 dan redeploy 136 success; gate tetap wajib pada release berikutnya. |
| Server aplikasi | EC2 `i-04ba2d1b2dcd7f757`, IP yang diamati `23.20.126.187` | Periksa IP, platform, SSH, disk, RAM, dan proses sebelum cutover; IP dapat berubah. |
| State lama | Backup `/var/backups/yunesa/legacy-20261009-before-cicd` lolos pemeriksaan integritas arsip dan checksum keempat file; root direktori berizin 700; delapan container serta network `tugas-akhir-network` telah dihapus | Source/image/volume lama tetap dipertahankan. Restore belum dibuktikan. |

Sesudah container lama berhenti, snapshot awal mencatat RAM terpakai 437 MB dan tersedia 1.397 MB; pengukuran stack baru dicatat di atas dan pada bukti sesi. Deployment baru memakai project Compose `yunesa-app` dan volume baru secara eksplisit. Volume/source/image legacy tetap dipertahankan; tidak ada migrasi atau restore data legacy sebagai efek samping deployment.

Alias private lama telah dihapus dari `/etc/hosts` produksi setelah backup dan flush DNS. BuildKit memakai override hostname pada container builder milik job ke `172.31.1.32`, dengan hostname sertifikat tetap `registry.tugasakhir.space`/`gitlab.tugasakhir.space`. HTTPS origin dari build host terverifikasi: registry 401, GitLab 200, dan `ssl_verify_result=0`. Prefix image tetap memakai port 443; TLS tidak dinonaktifkan.

Registry sekarang mengembalikan URL upload relatif melalui `REGISTRY_HTTP_RELATIVEURLS=true`. Jalur upload Cloudflare menolak layer besar dengan 413, sehingga BuildKit mengirimnya langsung melalui HTTPS origin. Nginx origin memakai sertifikat Let's Encrypt untuk kedua domain, berlaku sampai 8 Januari 2027; simulasi `certbot renew --dry-run` berhasil. Hook renewal memvalidasi dan reload Nginx. Backup konfigurasi berada di `/var/backups/yunesa-registry/tls-20261010T040233Z/`.

Pipeline 28 berhasil mengunggah blob sampai 300 MB tetapi manifest ditolak dengan `MANIFEST_BLOB_UNKNOWN`. Ini cocok dengan masalah attestation BuildKit yang didokumentasikan [GitLab Support](https://support.gitlab.com/hc/en-us/articles/29426166749596-Push-to-Container-Registry-Fails-Error-error-from-registry-blob-unknown-to-registry). Pipeline berikutnya memakai `BUILDX_NO_DEFAULT_ATTESTATIONS=1`; job 117 pada pipeline 30 berhasil mempublish ketiga image ARM64. Identitas release tetap dicatat lewat commit dan digest image; keberhasilan build tidak menggantikan gate runtime.

## Checklist konfigurasi dan credentials

Secret CI memakai variable individual protected, dengan raw value dan environment scope `production`. Key/token/password harus masked; jangan mencetak nilainya. [Helper pengisian variable](../scripts/set-production-variables.ps1) mempertahankan password produksi yang sudah ada dan membuat masing-masing `GLOBAL_PASSWORD`/`JWT_SECRET_KEY` hanya ketika variable tersebut belum tersedia. Helper meminta provider key melalui input terminal tersamar dan menyimpan setelah pengguna mengetik `SIMPAN`. Dokumentasi dan artifact hanya menyimpan nama variable serta status kelengkapannya.

| Variable/prasyarat | Isi atau kegunaan | Penyimpanan/status |
|---|---|---|
| `CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD` | Variable bawaan GitLab untuk job build/publish | Jangan membuat salinan token job di source. |
| `GLOBAL_PASSWORD` | Secret layanan lokal | Protected/masked/raw, scope `production`; buat hanya bila absent. |
| `JWT_SECRET_KEY` | Signing secret aplikasi | Protected/masked/raw, scope `production`; buat hanya bila absent. |
| `GEMINI_API_KEY` | Provider Gemini | Protected/masked/hidden/raw, scope `production`; pemanggilan chat nyata available. |
| `SILICONFLOW_API_KEY` | Provider SiliconFlow | Protected/masked/hidden/raw, scope `production`; pemanggilan embedding nyata available. |
| `ADMIN_PASSWORD` | Password akun awal `rizkyyanuark`, berbeda dari password storage | Protected/masked/hidden/raw, scope `production`; metadata tersedia. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Provider Supabase bila digunakan | Opsional; protected/raw, scope `production`; key masked. |
| Credential registry pada server | Pull image dari registry project | Token job CI dipakai lewat stdin dan Docker config sementara; tidak disimpan sebagai PAT permanen. |
| DNS/TLS dan akses proxy | Domain menuju layanan baru | Periksa route dan sertifikat sebelum smoke publik. |

Shell runner ID 2 menjalankan wrapper deployment lokal. Pipeline awal tidak memakai variable private key SSH atau aggregate `.env`. Wrapper harus memilih project/volume baru secara eksplisit, membatasi job pada project Yunesa, dan menjaga file environment berizin terbatas. Domain target adalah konfigurasi nonsecret; nama variable nonsecret lain mengikuti implementasi pipeline yang diperiksa, bukan daftar dugaan.

Helper mendukung Windows PowerShell 5.1 dan PowerShell 7, dengan `glab` yang sudah terautentikasi ke GitLab self-hosted. Dari root repository:

```powershell
powershell.exe -NoProfile -File scripts/set-production-variables.ps1 -ValidateOnly
powershell.exe -NoProfile -File scripts/set-production-variables.ps1
powershell.exe -NoProfile -File scripts/set-production-variables.ps1 -AdminPasswordOnly
```

Perintah pertama membaca metadata tanpa mengambil nilai variable. Perintah kedua menerima input lokal, mempertahankan password yang sudah ada, lalu membuat atau memperbarui provider key. Perintah ketiga hanya mengisi password admin: 12–128 karakter dengan huruf besar, huruf kecil, angka, dan simbol, sesuai kontrak auth aplikasi. Variable baru dibuat hidden; GitLab tidak mengizinkan perubahan hidden pada variable visible yang sudah ada. Metadata tidak membuktikan provider berhasil dipanggil.

Checklist environment aplikasi:

- [x] `GLOBAL_PASSWORD` dan `JWT_SECRET_KEY` tersedia melalui metadata variable produksi; nilai tidak dicetak atau masuk Git.
- [x] `GEMINI_API_KEY` dan `SILICONFLOW_API_KEY` tersedia untuk provider/peran yang dipilih; chat Gemini dan embedding SiliconFlow nyata available. Konfigurasi terdapat pada [model](../backend/package/yunesa/config/static/models.py), [chat](../backend/package/yunesa/models/chat.py), dan [embedding](../backend/package/yunesa/models/embed.py).
- [x] `POSTGRES_URL` dan `REDIS_URL` menunjuk layanan baseline yang benar; round trip PostgreSQL/Redis serta chat worker passed.
- [x] `YUNESA_VECTOR_BACKEND=qdrant`, `QDRANT_URI`, dan `QDRANT_API_KEY` sesuai Qdrant; collections=0 pada probe. `MILVUS_URI`/`ZILLIZ_URI` tidak diarahkan ke Qdrant.
- [x] Driver Memgraph menjalankan `RETURN 1`; ini belum menguji writer indeks Neo4j.
- [x] `LITE_MODE=false`, `SANDBOX_ENABLED=false`; konfigurasi skip startup khusus tes tidak digunakan pada release aplikasi.
- [x] Project Compose, volume, `data`/`saves`/model path baru, dan port terpisah dari inventaris legacy.
- [x] ETL/Airflow, scraping, dan telemetry opsional tidak diaktifkan.
- [x] Akun aplikasi awal dibuat melalui API auth nyata; login berhasil. Model/peran default yang dipakai gate telah dipanggil melalui client aplikasi.

## Gate aplikasi sebelum release

Implementasi pipeline ada pada [GitLab CI](../.gitlab-ci.yml), [build helper](../scripts/ci-build.sh), dan [integration helper](../scripts/ci-integration.py). Push protected `main` membangun API/web/MinIO ARM64 pada runner ID 1 dan menjalankan tes backend serta lint. Job `integration-baseline` kemudian memakai digest hasil build pada stack terisolasi; job environment `production` bergantung pada keberhasilan build dan integrasi. Job deploy memakai resource group tunggal. Rollback merupakan job manual dan memerlukan dua release yang telah lolos gate. Runner deployment dibuka kembali setelah gate 129 berhasil.

[Override Compose CI](../docker-compose.ci.yml) memakai delapan layanan nyata: PostgreSQL, Redis, Memgraph, Qdrant, MinIO, API, worker, dan web. Nama project mengandung job ID dan nonce; semua volume memakai namespace baru, tanpa bind mount host atau port publik. Jaringan internal menghalangi akses provider eksternal. Job menolak variable secret aplikasi produksi dan memakai password/admin sintetis; placeholder provider hanya memenuhi konfigurasi startup, tanpa pemanggilan Gemini/SiliconFlow atau chat berbayar.

Gate menginisialisasi admin melalui API internal, memeriksa query storage, upload/read/delete MinIO beserta proxy object, lalu frontend, login/me, 401 tanpa token, dan conversation create/read/delete lewat `http://web`. Job ARM 129 dan 133 lulus seluruh probe; delapan layanan tetap running/healthy, tanpa OOM atau restart. Cleanup memverifikasi label kepemilikan sebelum `compose down --volumes` pada project CI tersebut dan memastikan volume anonim serta resource namespace hilang; status cleanup passed. Artifact `artifacts/integration-baseline.json` menyimpan bukti yang telah divalidasi dan error tersanitasi. Timeout job 45 menit menyediakan waktu cleanup; integrasi berikutnya `interruptible=false` untuk menghindari pembatalan otomatis saat cleanup.

Bootstrap administratif memakai [installer](../scripts/install-deployment-host.py) dari source commit yang sama: `sudo python3 scripts/install-deployment-host.py --source /path/to/committed/source`. Installer menempatkan wrapper dan konfigurasi milik root di `/opt/yunesa-app`; sudoers hanya mengizinkan `/opt/yunesa-app/bin/deploy deploy` dan `rollback`. Request secret dikirim melalui stdin JSON oleh [request helper](../scripts/production-request.py), kemudian disimpan pada berkas root600. `ADMIN_PASSWORD` hanya masuk berkas bootstrap admin; tidak menjadi environment API/worker. Token registry job hanya dipakai pada Docker config sementara.

Untuk arsip bootstrap dari Windows, gunakan `git -c core.autocrlf=false -c core.eol=lf archive --format=tar --output=<archive.tar> <commit>`. Kedua flag diperlukan: audit menemukan 289 CR pada probe Python hasil arsip ketika `core.eol=crlf` masih berlaku, walaupun blob Git memakai LF. Bandingkan byte Compose/probe hasil ekstraksi dengan blob commit sebelum upload, lalu checksum source dengan manifest konfigurasi host sebelum runner dibuka kembali. Bootstrap host terbaru dari commit `a805264` terverifikasi canonical, checksum `695466f5298b40e39332eba027735f30ce33305fbdbc25d967b61e8826b07940`. Backup konfigurasi sebelumnya berada di `/opt/yunesa-app/backups/host-bootstrap-a805264-lf/` dengan berkas root600.

MinIO dibangun dari source upstream resmi commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a` melalui [Dockerfile](../docker/minio.Dockerfile), karena image publik yang diperiksa tidak dapat ditarik. Image menyertakan lisensi dan arsip source commit tersebut. Compile/publish ARM64 dan operasi upload/read/delete telah lulus pada CI serta gate produksi. Nginx meneruskan GET/HEAD object bucket `public`; byte object publik serta penolakan listing/bucket `knowledgebases` dengan 404 terverifikasi. Upload besar dan concurrency belum diuji.

Inspeksi terbaru: runner ID 1/2 telah diassign ke project ID 6, locked/protected dan tidak menerima job tanpa tag. Project lama ID 3 masih menjadi owner runner karena GitLab tidak mengizinkan unassign owner; fitur CI project lama telah dinonaktifkan. Runner build terverifikasi alive dan memakai HTTPS GitLab publik. Builder BuildKit sementara tetap memakai override hostname ke origin private dengan TLS terverifikasi, seperti dijelaskan di atas; koneksi service runner build tetap memakai HTTP VPC yang sudah ada. Dua cache compiler Rust yang tidak dipakai container telah dihapus untuk menyediakan sekitar 16 GB ruang build; data aplikasi tetap pada volume masing-masing.

Host produksi telah menghapus alias private GitLab/registry dari `/etc/hosts` dengan backup dan flush DNS. HTTPS registry memberi 401 dengan Bearer challenge; login/push/pull telah dibuktikan dan gate produksi memakai image ARM64 yang dipull. Caddy paket Ubuntu aktif dengan HTTP dan HTTPS menuju localhost8088, tanpa redirect otomatis, serta header upstream HTTPS. Sertifikat origin Let's Encrypt terverifikasi dan berlaku hingga 7 Januari 2027; web/API/auth/chat melalui HTTPS publik passed. Backup konfigurasi proxy berada di `/var/backups/yunesa/proxy-bootstrap-20261009T164954Z/`.

Deploy 130 gagal pada request object publik karena edge mengembalikan 403 untuk User-Agent Python urllib bawaan sebelum request mencapai Nginx. Probe kini memakai identitas aplikasi `Yunesa-Deployment-Readiness/1.0`; health/frontend memberi 200 dan object yang tidak ada memberi 404. Tidak ada gate storage yang dilonggarkan: seluruh probe integrasi 133 dan deploy 134 dijalankan kembali dan passed.

Periksa Compose tanpa mencetak konfigurasi hasil interpolasi yang memuat secret. Build API/web dari dependency frozen dan source commit yang sama. Deploy image yang telah dibangun pada runner; jangan build pada server aplikasi 2 GB. Bootstrap admin dilakukan melalui API internal dengan input stdin, sementara Nginx publik menolak endpoint inisialisasi. Gate produksi terpisah memakai credentials sebenarnya dan memeriksa domain HTTPS, login, 401 tanpa token, state percakapan, chat async melalui worker, object storage, serta pemanggilan Gemini dan SiliconFlow. Gate CI tanpa provider tidak memenuhi acceptance produksi tersebut.

[Log koneksi PostgreSQL](../backend/package/yunesa/storage/postgres/manager.py) tidak memuat URL credentials. Gate melakukan upload/read/delete object sintetis dan memeriksa respons publik sesuai byte serta penolakan bucket private. Tes unit build memakai placeholder provider khusus pengujian logika; penerimaan provider produksi memakai client dan key nyata. Failure path memakai key palsu hanya dalam environment child process: chat menghasilkan error dan embedding unavailable; secret global/CI tidak diubah.

Bukti produksi mencakup query PostgreSQL, Redis write/read, Memgraph `RETURN 1`, Qdrant collections=0, dan round trip MinIO. Login/me, 401 tanpa token, thread CRUD, serta chat async lewat worker dengan respons assistant tersimpan passed melalui jalur lokal dan HTTPS publik. Browser menampilkan landing/login; login interaktif UI dan penerimaan Terms belum dilakukan. Gemini `gemini-flash-latest` dan SiliconFlow `Qwen/Qwen3-Embedding-0.6B` tersedia pada pemanggilan nyata; key tidak dicatat.

[Endpoint health](../backend/server/routers/system_router.py) saat ini hanya mengembalikan status handler. Health container atau HTTP 200 belum membuktikan dependency, persistensi, provider, atau hasil akademik. [KG service](../backend/package/yunesa/knowledge/services/kg_service.py) dan [KG storage](../backend/package/yunesa/knowledge/services/kg_storage_service.py) masih menulis indeks lewat Milvus; [graph writer](../backend/package/yunesa/knowledge/graphs/storage_neo4j.py) memakai sintaks Neo4j. Gap tersebut tetap terbuka sampai operasi terkait berhasil pada Memgraph/Qdrant.

Jalankan tes integration yang memutasi data pada stack CI terisolasi, bukan volume produksi. Fixture [integration](../backend/test/integration/conftest.py) memerlukan akun admin dan memiliki cleanup KB. Credentials yang tidak tersedia menghasilkan skip; skip belum memenuhi acceptance wajib.

## Backup, rollback, dan bukti

Sebelum mengganti release baru yang sudah menerima write, hentikan penerimaan pekerjaan dan quiesce penulis. Ambil backup konsisten PostgreSQL, graph/vector, queue yang relevan, serta `data`/`saves`. Gunakan mekanisme native atau snapshot saat layanan terkait berhenti. Simpan backup dan secret pada server dengan akses terbatas; hanya manifest nonsecret menjadi artifact CI.

Rollback aplikasi memakai image/config release sebelumnya dan mempertahankan volume barunya. Redeploy 136 dari commit/digest yang sama membentuk release kedua serta backup `/opt/yunesa-app/backups/20261010T063155Z`; rollback 135 success pada 13:35:58. `current` kembali ke release pertama `a8052647081a8af87d211fe14414cdcbb1d9f387-20261010062931`, `previous` menunjuk release kedua `a8052647081a8af87d211fe14414cdcbb1d9f387-20261010063150`. Gate auth/storage/HTTP lokal dan publik passed; canary conversation tetap terbaca sesudah rollback.

Restore PostgreSQL dari backup tepat tersebut ke container/volume baru terisolasi passed: delapan checksum diverifikasi; users=1, knowledge_bases=0, canary=1, checkpoints=16, checkpoint_blobs=10, checkpoint_writes=22, checkpoint_migrations=10. Fixture milik audit dibersihkan. Arsip graph/vector/Redis/MinIO hanya lolos checksum; belum dipulihkan. Latihan rollback commit/digest yang sama membuktikan mekanisme dan preservasi state, bukan kompatibilitas downgrade lintas versi/skema. Restore data legacy, full storage DR, serta fresh-host credentials/config/application-auth recovery belum dibuktikan. SQL [Supabase awal](database/supabase-schema.sql) berisi operasi DROP dan tidak menjadi langkah deploy.

Pemeriksaan akhir 13:44:33: delapan container tetap running/healthy, restart 0 dan tanpa OOM; RAM available 776 MiB, swap used 336 MiB, disk free 17,05 GiB. Curl IPv4 dari Windows memberi `/` 200, `/api/system/health` 200, dan `/api/auth/me` 401, semuanya `ssl_verify_result=0`. Jalur negatif publik juga menolak inisialisasi admin dengan 403 dan password sintetis yang salah dengan 401. Canary pemulihan dihapus melalui API publik terautentikasi dan diverifikasi absent. Resource fixture restore produksi dan integrasi build diperiksa dengan label kepemilikan tepat: container=0, volume=0, network=0.

Guard backup menghitung seluruh run nonterminal, termasuk `pending` dan `cancel_requested`; run harus selesai atau dibatalkan melalui jalur aplikasi sebelum cutover. Error filesystem/arsip dinormalisasi menjadi kegagalan deployment agar jalur pemulihan layanan dijalankan. Akun shell runner tidak lagi berada dalam group Docker; akses administratifnya melalui dua operasi wrapper sudo yang tetap.

Catat commit/digest image, platform, nama project/volume, command, timestamp Asia/Jakarta, hasil smoke, RAM/swap/disk, alasan gagal, dan lokasi backup/restore proof. Build/integrasi ARM, smoke runtime/provider/domain produksi, backup, rollback commit/digest yang sama, serta restore PostgreSQL terisolasi sudah `Passed`. Commit dokumen akhir dapat lebih baru dari source release aktif `a805264`; identitas production mengikuti manifest dan symlink `current`. Hasil akademik ING-001/KG-001/ANS-001, load berkelanjutan, dan pemulihan seluruh stack tidak disimpulkan dari baseline ini.
