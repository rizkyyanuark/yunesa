# Desain DEP-001

Status: rencana deployment. Dokumen ini belum membuktikan kompatibilitas storage, pipeline aktif, atau aplikasi siap digunakan.

Pembaruan implementasi 10 Oktober 2026: pipeline build/deploy/rollback dan wrapper root tersedia. Build memakai tiga image digest API/web/MinIO ARM64; MinIO berasal dari source resmi yang dikunci. Runner 1/2 telah diassign ke project 6 dan protected/locked; CI project legacy 3 dinonaktifkan karena runner tidak dapat dilepas dari owner project. HTTPS registry telah memberi auth challenge setelah alias hosts usang dihapus. Caddy dan TLS origin telah diuji sampai instance yang benar. Bukti login/push/pull Docker, workload aplikasi, provider, dan pemulihan release masih menunggu job nyata.

Bootstrap admin memakai `ADMIN_PASSWORD` terpisah yang disimpan sebagai variable production protected/masked/hidden, dengan aturan password aplikasi tetap berlaku. `/api/auth/initialize` ditolak melalui Nginx publik; wrapper memasukkan credential melalui stdin ke probe dalam container API, kemudian memakai endpoint auth nyata pada localhost. Profil `/api/auth/me` memakai dependency yang mewajibkan login, sehingga request tanpa token harus 401. `GLOBAL_PASSWORD` dipakai storage, bukan password login. API/worker tidak menerima admin credential sebagai environment.

## Arsitektur baseline

Runner build menghasilkan image API dan web untuk platform server. GitLab project Yunesa menyimpan image bertag commit. Shell runner deployment ID 2 akan menjalankan wrapper lokal yang mengambil image dan menjalankan Compose pada server aplikasi 2 GB setelah konfigurasi runner diperiksa. Pipeline tidak memerlukan private key SSH; key administrasi hanya dipakai saat bootstrap server. Nginx web meneruskan `/api/` ke API; PostgreSQL, Redis, Memgraph, dan Qdrant melayani jaringan internal. Worker memakai image API yang sama apabila chat melalui Arq diaktifkan. ETL/Airflow tetap di luar baseline.

Registry project yang telah diperiksa dalam sesi ialah `registry.tugasakhir.space:443/rizkyyanuark/yunesa` (GitLab project ID 6). Probe HEAD dari klien lokal mendapat Cloudflare HTTP 403 tanpa auth challenge. Server memetakan domain GitLab/registry melalui `/etc/hosts` ke `172.31.1.32`; origin registry `/v2/` pada HTTP port 80 memberi 401, sedangkan port 443 belum menerima koneksi. Jalur TLS/DNS yang cocok dengan prefix registry harus diperbaiki dan push/pull Docker dari build host dibuktikan. Runner build ID 1 memiliki tag `arm64-builder`, `docker`, `build`, tetapi assignment yang diamati masih pada project ID 3. Assignment dan kemampuan menerima job Yunesa harus diperiksa sebelum pipeline dianggap siap.

## Batas kompatibilitas source

- [Production Compose](../../../docker-compose.prod.yml) memakai Memgraph/Qdrant, sedangkan [development Compose](../../../docker-compose.yml) memakai Neo4j/Milvus. Baseline ini mempertahankan pilihan pengguna untuk Memgraph/Qdrant.
- [Resolver vector](../../../backend/package/yunesa/graphrag/academic_graphrag.py) memerlukan `YUNESA_VECTOR_BACKEND=qdrant` atau URI Qdrant tanpa konfigurasi Milvus/Zilliz aktif. URI Milvus tidak boleh diarahkan ke port Qdrant.
- [Registrasi KB](../../../backend/package/yunesa/knowledge/__init__.py), [KG service](../../../backend/package/yunesa/knowledge/services/kg_service.py), dan [KG storage service](../../../backend/package/yunesa/knowledge/services/kg_storage_service.py) masih memiliki jalur Milvus. [Adapter Qdrant](../../../backend/package/yunesa/graphrag/storage/qdrant_storage.py) mempunyai search/upsert, tetapi keberadaannya belum membuktikan wiring build KG end-to-end.
- [Graph writer](../../../backend/package/yunesa/knowledge/graphs/storage_neo4j.py) memakai constraint/index/fulltext Neo4j. Operasi yang belum kompatibel dengan Memgraph tidak boleh diklaim siap atau diuji dengan hasil palsu.
- [Health API](../../../backend/server/routers/system_router.py) hanya membuktikan HTTP handler hidup. [Startup aplikasi](../../../backend/server/utils/lifespan.py) dapat mencatat sebagian kegagalan dependency lalu melanjutkan. Gate deployment harus memeriksa dependency dan jalur login/storage yang diperlukan baseline.

DEP-001 tidak menutup kekurangan ingestion, penulisan indeks, atau kualitas evidence. Jika alur baseline menyentuh operasi yang belum kompatibel, acceptance tetap gagal sampai implementasinya diperbaiki dalam cakupan yang dinyatakan.

## Release dan state

Gunakan project Compose, direktori state, dan volume baru yang berbeda dari deployment lama. Catat nama project dan volume sebelum startup; jangan mengandalkan default yang mungkin menunjuk state lama. Image release membawa source aplikasi. Bind mount source host yang menimpa image harus disingkirkan dari konfigurasi release.

Catatan sesi menyebut backup legacy di `/var/backups/yunesa/legacy-20261009-before-cicd`, integritas arsip dan checksum keempat file backup berhasil diperiksa, delapan container lama serta network `tugas-akhir-network` telah dihapus, dan source/image/volume lama dipertahankan. Root direktori backup berizin 700. Runner deployment lama ID 2 telah dijeda, dihentikan, dan dinonaktifkan agar pekerjaan lama tidak berjalan selama konfigurasi baru disiapkan. Catatan tersebut bukan latihan restore dan tidak mengotorisasi migrasi data. Periksa kembali inventaris server sebelum deployment baru.

Backup release baru menyimpan manifest image/config tanpa secret dalam artifact CI dan data konsisten pada server dengan akses terbatas. Hentikan penerimaan pekerjaan baru dan quiesce penulis sebelum backup state. Gunakan backup native yang dapat dipulihkan atau snapshot volume saat layanan terkait berhenti; jangan menganggap salinan direktori database hidup konsisten.

Rollback release mengembalikan image dan konfigurasi release baru sebelumnya sambil mempertahankan volume baru. Restore data merupakan tindakan terpisah dengan pemeriksaan write yang terjadi setelah backup. Jangan memakai SQL [Supabase awal](../../../docs/database/supabase-schema.sql) yang berisi `DROP TABLE` sebagai prosedur deployment.

## Pipeline dan gate

1. Validasi source/config, dependency frozen, lint non-mutating, serta tes relevan.
2. Build dan publish API/web dengan tag commit pada runner build; catat platform dan digest.
3. Jalankan integration pada state CI terisolasi. Akun uji memakai API auth nyata; tes wajib yang skip karena secret tidak tersedia belum memenuhi gate.
4. Serialisasi deployment melalui satu resource group. Branch `main` yang diperiksa sudah protected: hanya Maintainer dapat push/merge dan force push tidak diizinkan. Batasi credentials deployment pada branch/job yang dilindungi; jangan mencetak `.env` atau konfigurasi Compose yang berisi secret.
5. Periksa secret, kapasitas, inventaris volume, backup, dan akses registry sebelum cutover. Pull image dan restart layanan baseline tanpa menjalankan profile ETL/tunnel secara implisit.
6. Periksa dependency, web/API lewat domain, login, satu state write/read yang diizinkan, dan provider yang diaktifkan. Catat workload serta RAM/swap/disk.
7. Jika gate gagal, simpan alasan tanpa secret dan pulihkan release sebelumnya bila tersedia. Deployment pertama yang gagal tetap gagal; jangan menyebut container sehat sebagai release berhasil.

Pipeline dan deploy belum diaktifkan sampai credentials, runner assignment, wrapper lokal, konfigurasi, dan gate tersebut siap. Secret memakai variable individual protected dengan environment scope `production`; tidak ada file `.env` gabungan pada variable CI. Nama variable serta checklist tersedia pada [docs/deployment.md](../../../docs/deployment.md).
