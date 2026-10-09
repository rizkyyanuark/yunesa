# Deployment baseline Yunesa

Tanggal rencana: 9 Oktober 2026 (Asia/Jakarta). Status: CI/CD dan deployment aplikasi baru belum diaktifkan; credentials dan acceptance runtime masih pending. Kontrak perubahan: [DEP-001](../openspec/changes/dep-001-initial-deployment/proposal.md).

## Keputusan yang berlaku

Server aplikasi tetap 2 GB. Baseline memakai web/API, PostgreSQL, Redis, Memgraph, dan Qdrant lokal. Worker Arq mengikuti kebutuhan chat yang diaktifkan. Provider yang dipilih ialah Gemini dan SiliconFlow; peran dan model persisnya harus mengikuti konfigurasi aplikasi dan dibuktikan dengan pemanggilan nyata. ETL, Airflow, scraping, dan pembangunan indeks otomatis tetap mati.

Domain target ialah `yunesa.tugasakhir.space`. DNS/TLS dan akses aplikasi lewat domain belum menjadi bukti keberhasilan hanya karena alamat tersebut disepakati. Inspeksi sesi mencatat RAM terpakai 1.230 MB sebelum cleanup stack lama; ukur release baru dengan workload yang dicatat sebelum menganggap kapasitasnya cukup.

## Infrastruktur yang telah diinspeksi dalam sesi

| Item | Observasi sesi | Tindak lanjut |
|---|---|---|
| GitLab utama | Project ID 6, `rizkyyanuark/yunesa`, private; `main` protected dengan push/merge Maintainer dan force push mati | Gunakan project ini sebagai source pipeline. |
| Registry project | `registry.tugasakhir.space:443/rizkyyanuark/yunesa` enabled; probe HEAD lokal mendapat Cloudflare HTTP 403 | Buktikan login/push/pull lewat Docker pada build host. |
| Runner build ID 1 | Tag `arm64-builder`, `docker`, `build`; assignment yang diamati pada project ID 3 | Verifikasi/reassign ke Yunesa sebelum job berjalan. |
| Shell runner deployment ID 2 | Dijeda, service dihentikan dan dinonaktifkan selama penyiapan | Periksa project/tag/wrapper lokal sebelum aktivasi untuk deployment baru. |
| Server aplikasi | EC2 `i-04ba2d1b2dcd7f757`, IP yang diamati `23.20.126.187` | Periksa IP, platform, SSH, disk, RAM, dan proses sebelum cutover; IP dapat berubah. |
| State lama | Backup `/var/backups/yunesa/legacy-20261009-before-cicd` lolos pemeriksaan integritas arsip dan checksum keempat file; root direktori berizin 700; delapan container serta network `tugas-akhir-network` telah dihapus | Source/image/volume lama tetap dipertahankan. Restore belum dibuktikan. |

Tabel ini mencatat inspeksi infrastruktur, bukan hasil smoke aplikasi. Sesudah container lama berhenti, observasi sesi mencatat RAM terpakai 437 MB dan tersedia 1.397 MB; ini belum menjadi konsumsi stack baru. Deployment baru harus memilih project Compose dan volume baru secara eksplisit. Jangan memasang volume lama, menjalankan migrasi, menghapus image/volume, atau menyalin data legacy ke stack baru sebagai efek samping deployment.

Server saat diinspeksi mempunyai `/etc/hosts` yang memetakan `gitlab.tugasakhir.space` dan `registry.tugasakhir.space` ke `172.31.1.32`. Registry origin `http://registry.tugasakhir.space/v2/` pada port 80 memberi HTTP 401, sesuai adanya auth registry; koneksi port 443, 5050, dan 5000 gagal. Prefix project memakai port 443 sehingga jalur TLS/DNS Docker masih perlu dikonfigurasi dan diuji. Respons 401 origin bukan bukti push/pull image berhasil.

## Checklist konfigurasi dan credentials

Secret CI memakai variable individual protected, dengan raw value dan environment scope `production`. Key/token/password harus masked; jangan mencetak nilainya. [Helper pengisian variable](../scripts/set-production-variables.ps1) mempertahankan password produksi yang sudah ada dan membuat masing-masing `GLOBAL_PASSWORD`/`JWT_SECRET_KEY` hanya ketika variable tersebut belum tersedia. Helper meminta provider key melalui input terminal tersamar dan menyimpan setelah pengguna mengetik `SIMPAN`. Dokumentasi dan artifact hanya menyimpan nama variable serta status kelengkapannya.

| Variable/prasyarat | Isi atau kegunaan | Penyimpanan/status |
|---|---|---|
| `CI_REGISTRY`, `CI_REGISTRY_IMAGE`, `CI_REGISTRY_USER`, `CI_REGISTRY_PASSWORD` | Variable bawaan GitLab untuk job build/publish | Jangan membuat salinan token job di source. |
| `GLOBAL_PASSWORD` | Secret layanan lokal | Protected/masked/raw, scope `production`; buat hanya bila absent. |
| `JWT_SECRET_KEY` | Signing secret aplikasi | Protected/masked/raw, scope `production`; buat hanya bila absent. |
| `GEMINI_API_KEY` | Provider Gemini | Protected/masked/raw, scope `production`; nilai pending. |
| `SILICONFLOW_API_KEY` | Provider SiliconFlow | Protected/masked/raw, scope `production`; nilai pending. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Provider Supabase bila digunakan | Opsional; protected/raw, scope `production`; key masked. |
| Credential `read_registry` pada server | Pull image dari registry project | Token dengan scope yang diperlukan; nilai pending. |
| DNS/TLS dan akses proxy | Domain menuju layanan baru | Periksa route dan sertifikat sebelum smoke publik. |

Shell runner ID 2 menjalankan wrapper deployment lokal. Pipeline awal tidak memakai variable private key SSH atau aggregate `.env`. Wrapper harus memilih project/volume baru secara eksplisit, membatasi job pada project Yunesa, dan menjaga file environment berizin terbatas. Domain target adalah konfigurasi nonsecret; nama variable nonsecret lain mengikuti implementasi pipeline yang diperiksa, bukan daftar dugaan.

Helper memerlukan PowerShell 7 dan `glab` yang sudah terautentikasi ke GitLab self-hosted. Dari root repository:

```powershell
pwsh -File scripts/set-production-variables.ps1 -ValidateOnly
pwsh -File scripts/set-production-variables.ps1
```

Perintah pertama membaca metadata tanpa mengambil nilai variable. Perintah kedua menerima input lokal, mempertahankan password yang sudah ada, lalu membuat atau memperbarui provider key. Variable baru dibuat hidden; GitLab tidak mengizinkan perubahan hidden pada variable visible yang sudah ada. Keberadaan script dan pemeriksaan sintaks tidak membuktikan credentials sudah tersimpan atau provider berhasil dipanggil.

Checklist environment aplikasi:

- [ ] `GLOBAL_PASSWORD` dan `JWT_SECRET_KEY` tersedia; secret acak lokal tidak dicetak atau masuk Git.
- [ ] `GEMINI_API_KEY` dan `SILICONFLOW_API_KEY` tersedia untuk provider/peran yang dipilih. Periksa [konfigurasi model](../backend/package/yunesa/config/static/models.py) serta [chat](../backend/package/yunesa/models/chat.py) dan [embedding](../backend/package/yunesa/models/embed.py) sebelum menentukan model.
- [ ] `POSTGRES_URL` dan `REDIS_URL` menunjuk layanan baseline yang benar.
- [ ] `YUNESA_VECTOR_BACKEND=qdrant`, `QDRANT_URI`, dan `QDRANT_API_KEY` cocok dengan layanan Qdrant. `MILVUS_URI`/`ZILLIZ_URI` tidak menunjuk port Qdrant.
- [ ] `NEO4J_URI`, user/password/database yang dipakai driver sesuai Memgraph yang dijalankan; query nyata membuktikan aksesnya.
- [ ] `LITE_MODE=false`, `SANDBOX_ENABLED=false`; konfigurasi skip startup khusus tes tidak digunakan pada release aplikasi.
- [ ] Project Compose, volume, direktori `data`/`saves` baru, model path, dan port telah diperiksa terhadap inventaris legacy.
- [ ] ETL/Airflow dan akses scraping tidak diaktifkan. Telemetry opsional hanya diaktifkan jika credentials dan tujuannya telah ditetapkan.
- [ ] Akun aplikasi awal dibuat melalui alur auth nyata pada deployment baru; provider/model aplikasi disimpan melalui jalur konfigurasi yang didukung.

## Gate aplikasi sebelum release

Periksa Compose tanpa mencetak konfigurasi hasil interpolasi yang memuat secret. Build API/web dari dependency frozen dan source commit yang sama. Deploy image yang telah dibangun pada runner; jangan build pada server aplikasi 2 GB. Perintah pipeline yang belum diimplementasikan tidak tersedia sebagai prosedur siap jalan.

Sebelum startup dengan secret produksi, perbaiki [log koneksi PostgreSQL](../backend/package/yunesa/storage/postgres/manager.py): pesan inisialisasi saat ini memasukkan bagian URL yang memuat username/password. Jangan mengirim log startup mentah ke output CI atau percakapan sebelum kredensial dihapus dari pesan tersebut. Konfigurasi produksi juga belum menyediakan MinIO yang digunakan jalur upload; operasi upload harus mempunyai storage nyata dan bukti uji sebelum dianggap siap.

Sesudah startup, bukti minimum mencakup query PostgreSQL, ping Redis, query Memgraph, dan request Qdrant dengan credential nyata. Lanjutkan dengan halaman web dan API lewat domain, login/me, penolakan request tanpa token, serta satu write/read state aplikasi yang diizinkan. Worker/queue harus dibuktikan bila chat menggunakannya. Uji provider nyata dengan prompt kecil dan catat model/peran tanpa key.

[Endpoint health](../backend/server/routers/system_router.py) saat ini hanya mengembalikan status handler. Health container atau HTTP 200 belum membuktikan dependency, persistensi, provider, atau hasil akademik. [KG service](../backend/package/yunesa/knowledge/services/kg_service.py) dan [KG storage](../backend/package/yunesa/knowledge/services/kg_storage_service.py) masih menulis indeks lewat Milvus; [graph writer](../backend/package/yunesa/knowledge/graphs/storage_neo4j.py) memakai sintaks Neo4j. Gap tersebut tetap terbuka sampai operasi terkait berhasil pada Memgraph/Qdrant.

Jalankan tes integration yang memutasi data pada stack CI terisolasi, bukan volume produksi. Fixture [integration](../backend/test/integration/conftest.py) memerlukan akun admin dan memiliki cleanup KB. Credentials yang tidak tersedia menghasilkan skip; skip belum memenuhi acceptance wajib.

## Backup, rollback, dan bukti

Sebelum mengganti release baru yang sudah menerima write, hentikan penerimaan pekerjaan dan quiesce penulis. Ambil backup konsisten PostgreSQL, graph/vector, queue yang relevan, serta `data`/`saves`. Gunakan mekanisme native atau snapshot saat layanan terkait berhenti. Simpan backup dan secret pada server dengan akses terbatas; hanya manifest nonsecret menjadi artifact CI.

Rollback aplikasi memakai image/config release baru sebelumnya dan mempertahankan volume barunya. Deployment pertama yang belum mempunyai release baik tidak dapat mengklaim rollback aplikasi berhasil. Restore backup dilakukan terpisah pada lingkungan pemulihan; periksa write setelah backup sebelum memulihkan state aktif. SQL [Supabase awal](database/supabase-schema.sql) berisi operasi DROP dan tidak menjadi langkah deploy.

Catat commit/digest image, platform, nama project/volume, command, timestamp Asia/Jakarta, hasil smoke, RAM/swap/disk, alasan gagal, dan lokasi backup/restore proof. Tandai `Passed`, `Inspected`, `Not run`, atau `Inferred` berdasarkan bukti. Runtime Memgraph/Qdrant, provider, domain, CI/CD, dan rollback tetap `Not run` sampai pemeriksaan tersebut dijalankan.
