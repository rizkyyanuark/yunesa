# Scripts Yunesa

Entry point CI, deployment, bootstrap, kontrol produksi, dan setup lokal untuk aplikasi utama berada langsung di direktori ini. `.gitlab-ci.yml` memanggil `ci-build.sh`, `ci-integration.py`, dan `production-request.py`.

## Verifikasi Kontrak Deployment

Pemeriksaan kontrak deployment untuk 3 image produksi (`API`, `WEB`, `MINIO`) pada Linux dengan Python dan Git:

```sh
python scripts/checks/check-production-request.py
```

Gate `verify-deployment` menjalankan suite ini pada MR dan protected `main`. Diagnostik heartbeat worker ARQ tersedia di `scripts/checks/check-worker-health.py`. Lihat `CONTRIBUTING.md` untuk kontrak artifact dan kebutuhan protokol helper produksi.

Pipeline ETL, Knowledge Graph batch, dan orkestrasi Airflow dikelola terpisah pada repository `yunesa-ingestion`.
