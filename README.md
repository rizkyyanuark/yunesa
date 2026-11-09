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
- `scripts`: setup lokal, CI/deployment dan operasi. Verifier berada di `scripts/checks/airflow`, rehearsal kapasitas di `scripts/rehearsal/arm64`. Lihat [panduan script](scripts/README.md).
- `docs/database/supabase-schema.sql`: skema database Supabase.

Folder `data`, `saves`, dan `models` disiapkan kosong untuk state lokal. Dataset, model unduhan, naskah penelitian, kredensial, dan dependensi terpasang tidak disertakan.

## Repository dan sinkronisasi

Repository utama adalah [GitLab](https://gitlab.tugasakhir.space/rizkyyanuark/yunesa), dengan remote `origin`. [GitHub](https://github.com/rizkyyanuark/yunesa) menjadi salinan manual dengan remote `github`. Keduanya private.

Kirim branch perubahan ke GitLab, lalu buka Merge Request ke `main`:

Ikuti [panduan kontribusi](CONTRIBUTING.md) dan template MR untuk aturan branch, gate deployment, bukti release dan rollback.

```powershell
git push origin HEAD
```

Pipeline MR menjalankan lint/build frontend dan tes unit backend terpilih serta lint helper pada runner pemeriksaan ID 5. Job MR tidak mempublish image atau memakai secret produksi. Tinjau hasil pipeline pada commit terakhir sebelum merge.

Merge mensyaratkan pipeline berhasil; pipeline skipped tidak memenuhi syarat. Merge ke protected `main` menjalankan build image ARM64, integrasi dengan storage terisolasi, lalu deployment produksi otomatis jika kedua gate lulus. MR !1 tetap draft sampai review selesai.

Sinkronisasi GitHub tetap manual. Setelah MR digabung di GitLab, sinkronkan `main` lokal sebelum mengirim salinannya:

```powershell
git switch main
git pull --ff-only origin main
git push github main
```

Pipeline 36 dari commit `a805264` telah lulus build, integrasi, dan gate produksi pada 10 Oktober 2026. Status release dan batas baseline dicatat di [panduan deployment](docs/deployment.md) serta [bukti DEP-001](docs/evidence/dep-001-2026-10-10.md).

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

Baseline deployment di [yunesa.tugasakhir.space](https://yunesa.tugasakhir.space) memakai project Compose `yunesa-app`: web/API, worker Arq, PostgreSQL, Redis, Memgraph, Qdrant, dan MinIO. Acceptance DEP-001 memakai server t4g.small 2 GB dengan ETL/Airflow mati. State berada di `/opt/yunesa-app/shared`, terpisah dari volume legacy; secret berasal dari GitLab Variables scope `production`.

Integrasi Airflow menambahkan profile opsional `etl` pada Compose produksi, dengan kontrol SSH `on`, `off`, `status`, dan `logs`. Kode integrasi ini belum di-deploy ke produksi. Migrasi pemasangan terpisah, bootstrap terpercaya, dan pengukuran kapasitas harus mengikuti [panduan operasi Airflow](docs/operations/airflow.md); jangan memakai `compose down` sebagai saklar pada project gabungan.

Gate nyata membuktikan HTTPS, login/API auth, percakapan tersimpan, chat melalui worker, storage, serta Gemini dan SiliconFlow. Rollback antara dua release dengan source/digest sama dan restore PostgreSQL dari backup nyata juga lulus. Ini tidak menyelesaikan ING-001/KG-001/ANS-001: jalur pembangunan indeks yang masih bergantung pada Milvus/Neo4j tetap perlu pekerjaan tersendiri. Bukti backup, rollback, dan restore beserta batasnya dicatat di panduan deployment; kapasitas beban berkelanjutan dan pemulihan seluruh storage belum dibuktikan.

## Asal komponen

Aplikasi mempertahankan komponen dan rujukan upstream Yuxi-Know dari source sebelumnya. Pertahankan atribusi dan pemberitahuan lisensi yang tersedia pada komponen pihak ketiga.
