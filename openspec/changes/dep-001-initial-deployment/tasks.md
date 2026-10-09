# Tugas DEP-001

Status awal: implementasi CI/CD direncanakan; deployment aplikasi dan acceptance belum dijalankan. Checklist berubah hanya berdasarkan bukti.

- [ ] DEP-T01: Verifikasi assignment runner build ID 1 pada project Yunesa ID 6, platform server/image, akses registry, dan isolasi build dari server 2 GB. DEP-R01/R06.
- [ ] DEP-T02: Tetapkan project Compose/state baru; periksa kembali backup legacy dan nama volume tanpa mengubah data lama. DEP-R05.
- [ ] DEP-T03: Koreksi konfigurasi baseline Memgraph/Qdrant, image commit, source dalam image, network/port, healthcheck, dan log PostgreSQL yang memuat kredensial. Periksa dependency MinIO untuk upload yang diaktifkan. ETL/Airflow tetap mati. DEP-R02/R07.
- [ ] DEP-T04: Siapkan secret deployment/provider dan pilihan model/peran Gemini/SiliconFlow; validasi nama variable terhadap implementasi tanpa menulis nilainya di repo. DEP-R04/R06.
- [ ] DEP-T05: Implementasikan pipeline build, integration terisolasi, deploy ter-serialisasi, backup, serta rollback; periksa lint/config dan diff. DEP-R01/R05/R06.
- [ ] DEP-T06: Buktikan readiness PostgreSQL/Redis/Memgraph/Qdrant dan jalur web/API/auth/persistensi nyata. Operasi Milvus/Neo4j yang belum kompatibel tetap dicatat sebagai gap. DEP-R02/R03.
- [ ] DEP-T07: Buktikan domain `yunesa.tugasakhir.space`, provider nyata, failure path, dan konsumsi RAM/swap/disk pada server 2 GB. DEP-R03/R04/R07.
- [ ] DEP-T08: Latih rollback release dan restore terpisah, simpan bukti tanpa secret, lalu perbarui kontrak yang benar-benar terbukti sebelum arsip. DEP-R05/R06.

Untuk setiap tugas, catat tanggal Asia/Jakarta, commit, command atau user path, hasil `Passed`/`Inspected`/`Not run`/`Inferred`, serta lokasi bukti. Tidak ada checklist yang selesai hanya karena dokumen ini tersedia.
