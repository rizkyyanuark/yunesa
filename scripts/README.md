# Scripts Yunesa

Entry point CI, deployment, bootstrap, kontrol SSH dan setup lokal berada langsung di direktori ini. `.gitlab-ci.yml` memanggil `ci-build.sh`, `ci-integration.py`, `ci-airflow-integration.py` dan `production-request.py`.

## Verifikasi Airflow

`checks/airflow/` berisi verifier untuk kontrak deployment, DAG, adopsi metadata/log, init, race, release/rollback, restart, boot Linux dan heartbeat worker. Jalankan verifier integrasi dengan dependency serta resource lokal terisolasi sesuai panduan operasional.

Pemeriksaan kontrak deployment pada Linux root dengan Python dan Git

```sh
python scripts/checks/airflow/check-airflow-contracts.py
python scripts/checks/check-production-request.py
```

Gate `verify-deployment` menjalankan kedua suite pada MR dan protected `main`. Kontrak platform image dan observasi worker Docker berada pada `checks/airflow/check-airflow-docker-contracts.py`, dijalankan gate integrasi dengan `YUNESA_CONTRACT_IMAGE` menunjuk image Airflow yang diuji. Lihat `CONTRIBUTING.md` untuk kontrak artifact dan kebutuhan protokol helper produksi.

`airflow-local-check.py` tetap menjadi helper bersama untuk gate CI dan verifier. Gate CI mengimpornya langsung.

## Rehearsal ARM64

`rehearsal/arm64/` berisi enam alat untuk kapasitas, driver VM/native, sesi/deadline, controller dan bundle source/image.

```sh
python scripts/rehearsal/arm64/check-airflow-native-preparation.py
python scripts/rehearsal/arm64/prepare-airflow-arm64-bundle.py --help
```

Tes persiapan memakai batas AWS simulasi. Eksekusi workload serta cleanup cloud mengikuti lease dan otorisasi resource pada panduan rehearsal.

Arsip source baru menyimpan path direktori ini. Buat ulang arsip source setelah perubahan layout sebelum memakai bundle rehearsal berikutnya.

Panduan operasi dan bukti pengujian tersedia di `docs/operations/airflow.md` dan `docs/evidence/` pada root repository.
