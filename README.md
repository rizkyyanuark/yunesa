# Yunesa

Aplikasi basis pengetahuan akademik untuk data dosen dan publikasi UNESA, dengan API FastAPI, antarmuka Vue, ETL, knowledge graph, dan pencarian vektor.

## Pengembangan dengan spesifikasi

Mulai dari [PRD](PRD.md), [arsitektur](ARCHITECTURE.md), dan [panduan agen](AGENTS.md).
[Indeks SDD](openspec/README.md) memuat ING-001 sebagai pekerjaan pertama, kemudian KG-001 dan ANS-001.
[Alur pengembangan](docs/development.md) menjelaskan status dokumen, pemeriksaan, dan cara memperbarui spesifikasi.

Paket ini mencatat kebutuhan target dan kondisi kode yang diinspeksi. Spesifikasi yang disepakati belum berarti implementasi telah selesai atau diuji.

## Isi project

- `backend/server`: API dan worker aplikasi.
- `backend/package/yunesa`: library aplikasi, ETL, retrieval, dan resource IEEE.
- `backend/test`: tes aplikasi.
- `web`: source dan aset frontend.
- `configs`: konfigurasi contoh tanpa data akun pribadi.
- `docker`: Dockerfile dan konfigurasi layanan.
- `orchestration/dags`: DAG ETL Airflow.
- `scripts`: persiapan konfigurasi lokal dan utilitas.
- `docs/database/supabase-schema.sql`: skema database Supabase.

Folder `data`, `saves`, dan `models` disiapkan kosong untuk state lokal. Dataset, model unduhan, naskah penelitian, kredensial, dan dependensi terpasang tidak disertakan.

## Repository dan sinkronisasi

Repository utama adalah [GitLab](https://gitlab.tugasakhir.space/rizkyyanuark/yunesa), dengan remote `origin`. [GitHub](https://github.com/rizkyyanuark/yunesa) menjadi salinan manual dengan remote `github`. Keduanya private.

Setelah membuat commit lokal, kirim branch `main` ke keduanya:

```powershell
git push origin main
git push github main
```

Sinkronisasi GitHub tetap manual. Pipeline GitLab membangun image ARM64 dari protected `main`, menjalankan tes/lint serta integrasi dengan storage terisolasi, lalu melakukan deployment melalui wrapper pada server produksi. Pipeline 36 dari commit `a805264` telah lulus build, integrasi, dan gate produksi pada 10 Oktober 2026. Status release dan batas baseline dicatat di [panduan deployment](docs/deployment.md) serta [bukti DEP-001](docs/evidence/dep-001-2026-10-10.md).

## Menyiapkan lingkungan lokal

Gunakan Python 3.12 dan Docker Compose. Frontend menggunakan pnpm 10.11.0.

```powershell
python scripts/init-env.py
```

Perintah tersebut membuat `.env` baru dengan secret acak untuk layanan lokal dan path volume sesuai folder ini. Ia berhenti jika `.env` sudah ada. Isi kredensial provider yang diperlukan langsung di file lokal tersebut.

Validasi konfigurasi sebelum menjalankan layanan:

```powershell
docker compose -p yunesa --env-file .env -f docker-compose.yml config --quiet
```

Menjalankan aplikasi:

```powershell
docker compose -p yunesa --env-file .env -f docker-compose.yml up -d --build
```

Untuk ETL dan Airflow, tambahkan `--profile etl`.

Akses lokal: web `http://localhost:5173`, API `http://localhost:5050`, dan Airflow `http://localhost:8080`. Port bawaan dapat bertabrakan dengan stack lain yang sedang berjalan; sesuaikan pemetaan port sebelum menjalankan keduanya bersamaan.

## Frontend tanpa Docker

```powershell
cd web
pnpm install --frozen-lockfile
pnpm build
```

## Produksi

Deployment di [yunesa.tugasakhir.space](https://yunesa.tugasakhir.space) memakai project Compose `yunesa-app`: web/API, worker Arq, PostgreSQL, Redis, Memgraph, Qdrant, dan MinIO. Server tetap t4g.small 2 GB; ETL/Airflow mati. State baru berada di `/opt/yunesa-app/shared`, terpisah dari volume legacy; secret berasal dari GitLab Variables scope `production`.

Gate nyata membuktikan HTTPS, login/API auth, percakapan tersimpan, chat melalui worker, storage, serta Gemini dan SiliconFlow. Rollback antara dua release dengan source/digest sama dan restore PostgreSQL dari backup nyata juga lulus. Ini tidak menyelesaikan ING-001/KG-001/ANS-001: jalur pembangunan indeks yang masih bergantung pada Milvus/Neo4j tetap perlu pekerjaan tersendiri. Bukti backup, rollback, dan restore beserta batasnya dicatat di panduan deployment; kapasitas beban berkelanjutan dan pemulihan seluruh storage belum dibuktikan.

## Asal komponen

Aplikasi mempertahankan komponen dan rujukan upstream Yuxi-Know dari source sebelumnya. Pertahankan atribusi dan pemberitahuan lisensi yang tersedia pada komponen pihak ketiga.
