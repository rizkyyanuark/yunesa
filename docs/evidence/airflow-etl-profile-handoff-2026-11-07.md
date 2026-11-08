# Handoff integrate-airflow-etl-profile

## Pembaruan setelah takeover

Pemilik meminta pekerjaan diambil alih kembali. Status dan bukti terbaru berada di [laporan verifikasi](airflow-etl-profile-2026-11-07.md) serta checklist OpenSpec. Handoff berikut menyimpan konteks historis. Pemilik sudah mengizinkan registry/push localhost dan melanjutkan tanpa provider/chat. Rehearsal native memakai konfigurasi staging terpasang root, sementara validasi ARM64 dicatat terpisah.

Pemilik meminta pekerjaan tersisa diteruskan oleh kolega pada 7 November 2026. Pengujian lanjutan dihentikan setelah fixture terakhir selesai gagal dan membersihkan containernya.

## Batas otorisasi

1. Lanjutkan implementasi dan verifikasi lokal untuk change `integrate-airflow-etl-profile`.
2. Deployment produksi, instalasi bootstrap produksi, commit, push Git dan publikasi registry eksternal memerlukan instruksi baru dari pemilik. Registry dan push localhost sudah diizinkan untuk pengujian lokal.
3. Dukungan Memgraph sudah disetujui. Perluasan arsitektur atau backend lain perlu persetujuan tersendiri.
4. Operasi destruktif hanya boleh menyentuh fixture yang kepemilikannya telah diverifikasi melalui label/project. Pertahankan container aplikasi lain.
5. Pertahankan pekerjaan lokal yang sudah ada. Hindari reset/clean Git, pembersihan Docker global dan penghapusan volume diagnosis tanpa otorisasi.

## Mulai dari keadaan aktual

- Repository `C:\Users\rizky\Documents\GitHub\yunesa`, branch `main`, HEAD `b6924e196f6728c73dd70864c20b1c655db9f50f` pada handoff.
- Working tree memuat perubahan tracked dan file untracked. Penghapusan `docs/database/supabase-schema.sql` sudah ada sebelum pekerjaan ini.
- OpenSpec mencatat **17/28 task selesai**, dengan sebelas task tetap terbuka. Gunakan checkbox aktual sebagai sumber progress.
- Baca `AGENTS.md`, `SPEC.md`, `README.md`, seluruh artifact change dan [laporan bukti](airflow-etl-profile-2026-11-07.md).
- Gunakan skill `openspec-apply-change` dan `antislop-code`. Ambil kembali `openspec instructions apply --change integrate-airflow-etl-profile --json` sebelum melanjutkan.
- Verifikasi ulang branch, HEAD, diff, versi Docker dan image lokal. Bukti ini berasal dari working-tree build yang belum dipublikasikan.

## Bukti yang sudah tersedia

| Area | Hasil |
| --- | --- |
| ARM64 | Kedua image linux/arm64 dibangun, tiga DAG diimpor, 48 command dirender dan diterima parser/registry worker, 18 command worker terdaftar. |
| Launch race | Dua puluh race Docker nyata menghasilkan tiga start dan tujuh belas penolakan. Worker yang sudah berjalan selesai tanpa dibunuh. Reservation ambigu/interrupted bertahan. |
| Kontrak Linux | Tiga belas tes lulus, termasuk otorisasi, flock, checksum, input release, state/gate rusak, deadline dan worker auto-remove yang menghilang saat observasi. |
| Pool | KG dan lecturer eligible, lima belas observasi menunjukkan maksimum satu worker. Alokasi Docker komponen dan worker diperiksa. |
| Drain | Timeout satu detik gagal dengan worker tetap berjalan. Backup batal sebelum core stop. Normal off, repeated off dan on berhasil. |
| Resumed work | `manual__drain_a7df6a11` dan `manual__drain_fd5ced63` sukses. PostgreSQL ID tetap sama selama siklus switch. |
| Destination | Pembacaan Memgraph mengonfirmasi empat node/lima relasi sesuai artefak dan judul publication fixture. GLiNER, vector persistence dan provider eksternal dinonaktifkan. |
| Reconcile | Status read-only, stale-boot gate degraded, OFF tetap OFF dan ON membuka gate setelah readiness. Pengujian memakai record boot lama. |
| Recovery komponen | A → B → A, mismatch image ditolak, pemulihan A, OFF lintas release dan legacy core-only OFF berhasil. A/B memakai image dan versi Airflow yang sama. |
| Pemeriksaan pendukung | 33 unit test worker lulus dengan satu warning SQLAlchemy existing. Ruff scripts/orchestration, kompilasi 20 sumber Python, Compose 8/12 service dan OpenSpec strict lulus. |

Suite unit existing menggunakan beberapa monkeypatch/fake I/O. Bukti integrasi di atas memakai Airflow, Docker, PostgreSQL dan Memgraph nyata. ING-001, penerimaan KG-001 lengkap dan ANS-001 tetap memerlukan acceptance tersendiri.

Unpause lecturer pada uji pool menghasilkan satu run jadwal yang mendahului run manual. Run fixture `scheduled__2026-10-31T19:00:00+00:00` dibatalkan melalui API agar run manual eligible. Run manual kemudian dibatalkan setelah observasi, sebelum scraping eksternal. Intervensi ini tercatat dalam `pool-intervention.json`; helper kini memiliki penanganan jadwal fixture tersebut.

## Kegagalan terakhir yang harus ditangani dahulu

Perintah `--postflight` mencapai fase `stopped-scheduler-recovery`, melewati assertion pemulihan dan repeated on dengan scheduler yang sama, kemudian masuk `isolated-worker-oom`. Keseluruhan perintah berakhir **exit 1** dan tidak menghasilkan `postflight.json` sukses.

- Scenario mengatur worker 32 MiB dengan allowance memory/swap total 32 MiB.
- Run `manual__oom_6a34510f` mencatat `load_data=failed`, `try_number=2`. Task downstream menjadi `upstream_failed`; log scheduler mencatat DagRun failed.
- Harness timeout pada `wait_until(failed_worker)`. Field Docker `OOMKilled` belum tertangkap sehingga penyebab kernel OOM belum boleh dinyatakan terverifikasi.
- Provider Docker yang terpasang menjalankan `remove_container` pada blok `finally` untuk `auto_remove="success"`. Container yang gagal juga dapat terhapus sebelum polling melihat terminal state.
- Source yang diperiksa berada di image pada `/home/airflow/.local/lib/python3.12/site-packages/airflow/providers/docker/operators/docker.py`, sekitar baris 457–461. Verifikasi lagi terhadap versi provider yang benar-benar dibangun.
- `worker_oom()` mengasumsikan container gagal masih dapat di-inspect. Perbaiki asumsi tersebut dan observabilitas produk untuk penyebab kegagalan resource. Pilihan desain mencakup capture state sebelum cleanup, event Docker yang dibatasi, atau retensi container gagal yang disengaja.
- Pertahankan cleanup worker sukses dan propagasi kegagalan task. Uji penyebab OOM, state retry/failure, tampilan status serta cleanup secara nyata.
- Ubah source repository dan bangun image yang relevan. Hindari patch sementara pada site-packages container sebagai bukti implementasi.

Diagnostic terakhir ada di `.cache/airflow-native-recovery/postflight-failure.json`. `completed` kosong karena hasil postflight ditulis setelah seluruh rangkaian selesai. Assertion scheduler yang telah terlewati perlu direkam kembali dalam laporan postflight lengkap setelah perbaikan.

## Task terbuka dan urutan kerja

| Task | Pekerjaan tersisa |
| --- | --- |
| 3.3 | Prioritaskan kegagalan OOM di atas. Lengkapi sampling workload representatif, core traffic, memory/swap/peak/OOM/restart dan budget terukur. |
| 6.4 | Setelah edit final, jalankan kembali verifikasi relevan, inspeksi diff dan petakan bukti serta batas setiap requirement. |
| 2.2 | Verifikasi kontrak CI, manifest/dotenv dan MR checks. Publikasi registry mengikuti otorisasi baru. |
| 3.4 | Finalisasi budget dan workload limits berdasarkan pengukuran 3.3. Nilai saat ini bersifat sementara. |
| 4.4 | Lengkapi reboot/reconciliation pada host Linux/systemd nyata. Simulasi record boot sudah lulus. |
| 5.1 | Lengkapi urutan deploy/rollback/backup dengan core stack penuh. Busy lock dan abort-before-core-stop telah lulus. |
| 5.3 | Lengkapi wrapper deploy/rollback penuh, kegagalan partial cutover dan kompatibilitas metadata. Rehearsal komponen A/B belum mencakup seluruh core. |
| 5.4 | Inventaris pemasangan lama yang aktual dan rehearsal adoption dengan history/log/key yang sesuai. |
| 5.5 | Jendela produksi terpisah setelah otorisasi pemilik. |
| 6.2 | Lengkapi core identities, health, authenticated API, queued chat dan rangkaian deploy/rollback penuh. |
| 6.3 | Ukur host kelas target. Hasil native laptop dan emulasi ARM64 memiliki batas bukti yang berbeda. |

Default komponen produksi adalah 384 MiB memory, 768 MiB memory/swap total dan 256 CPU shares. Worker default 512 MiB, 1 GiB memory/swap total dan 1024 shares. Fixture native memakai komponen 512 MiB/1 GiB. CPU shares merupakan bobot relatif. Kapasitas server 2 GB masih memerlukan pengukuran.

Default readiness/drain administratif tetap 180/600 detik. Fixture menggunakan readiness 600 detik setelah cold startup lokal melampaui 180 detik. Wrapper memvalidasi override 1–3600 detik. Windows sempat melaporkan free physical memory 521 MiB dari sekitar 16 GiB; sampel berikutnya yang disimpan menunjukkan 740 MiB. Kondisi laptop dapat berkontribusi pada latensi lokal.

## Fixture dan bukti lokal

Tidak ada container fixture yang berjalan saat handoff. Container yang masih berjalan adalah dua service `personal-agentic` yang healthy. Volume berikut sengaja dipertahankan untuk diagnosis.

```text
yunesa-airflow-it-c4a18f07-root
yunesa-airflow-it-c4a18f07-control
yunesa-airflow-it-c4a18f07-data
yunesa-airflow-it-c4a18f07-logs
yunesa-airflow-it-c4a18f07_memgraph-data
yunesa-airflow-it-c4a18f07_postgres-data
```

Direktori `.cache/airflow-native-recovery/` berisi `result.json`, `progress.json`, `worker-runtime-final.json`, `worker-status.json`, `component-allocations.json`, `pool-intervention.json`, `initial-http-failure.json`, `startup-deadline-failure.json`, `reconcile-failure.json`, `postflight-failure.json` dan `windows-memory.json`. Bukti ARM ada di `.cache/airflow-final-proof/`. File cache tersebut diabaikan Git dan perlu tersedia jika melanjutkan fixture yang sama.

Helper memakai bound 60 menit, controller `--rm`, tanpa port host, dan cleanup project di `finally`. `worker_oom()` memulihkan file Compose pada `finally`; verifikasi kembali resource config volume sebelum reuse. Desired state yang tersimpan dapat masih ON meskipun seluruh container fixture telah dibersihkan.

`--resume` dibuat untuk melanjutkan kegagalan HTTP awal dan mengulang pembuatan synthetic release B/legacy. Kedua direktori release kini sudah ada, sehingga replay mode tersebut perlu ditinjau dahulu. Gunakan namespace baru untuk rehearsal penuh yang baru, atau `--postflight` pada volume yang dipertahankan setelah memperbaiki kasus terakhir. Hindari menulis hasil sukses buatan untuk memenuhi prasyarat helper.

Contoh menjalankan postflight pada volume retained setelah source dan image yang diperlukan siap.

```powershell
$project = 'yunesa-airflow-it-c4a18f07'
$proof = Join-Path (Get-Location) '.cache/airflow-native-recovery'
docker run --rm --name "$project-controller" `
  --label "io.yunesa.integration=$project" --memory 256m --cpus 1 `
  --mount "type=bind,src=$((Get-Location).Path),dst=/source,readonly" `
  --mount "type=bind,src=$proof,dst=/proof" `
  --mount "type=volume,src=$project-root,dst=/opt/yunesa-app" `
  --mount "type=volume,src=$project-control,dst=/opt/yunesa-app/shared/airflow/control" `
  --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock `
  yunesa-airflow-check:local python /source/scripts/airflow-local-check.py `
  --project $project --postflight
```

## Aturan penerimaan

1. Reproduksi kegagalan dan baca jalur produk sebelum mengedit. Batasi file perubahan sesuai masalah yang teramati.
2. Gunakan API/CLI Airflow, operator, worker dan destination nyata. Catat provider yang dinonaktifkan atau belum tersedia.
3. Setiap perubahan operator/DAG/package image memerlukan rebuild image terkait dan verifikasi ARM64 final kembali. Perubahan host helper memerlukan pengujian kontrak dan jalur CLI yang relevan.
4. Pertahankan shared lifecycle lock, admission fail-closed, reservation ambigu, pause choices, core identities, log/history dan keterkaitan manifest/environment image.
5. Recovery yang menjalankan migrasi harus melakukan drain/stop runtime dahulu. Periksa panduan resmi Airflow 3.1.7 dan urutan kode aktual.
6. Perbarui checkbox hanya setelah seluruh acceptance task tersebut terpenuhi, kemudian refresh instruksi OpenSpec. Bedakan bukti komponen dari wrapper/core acceptance.
7. Catat run ID, image ID/digest, command, exit code, hasil DB dan batas verifikasi. Bedakan exit 137 akibat cleanup dari OOM yang dikonfirmasi Docker/kernel.
8. Redaksi credential dari diagnostics. Pertahankan env/key/dump sensitif pada penyimpanan fixture yang dibatasi.
9. Selesaikan dengan `SUMMARY`, `PROOF` dan `NEXT` sesuai AGENTS, termasuk batas tanpa deployment/commit/push dan semua risiko yang masih terbuka.

Pengaturan emulasi ARM64 binfmt/QEMU telah diregistrasikan ulang pada Docker VM saat verifikasi. Image ARM64 yang terakhir diterima tercatat dalam laporan bukti. Rebuild setelah perubahan kode akan menghasilkan identitas baru yang harus dicatat.
