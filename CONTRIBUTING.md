# Kontribusi Yunesa

## Branch dan Merge Request

Setiap perubahan dikembangkan pada branch `<type>/<slug>`, misalnya `feat/lecturer-import`, `fix/login-error`, atau `chore/deployment-evidence`. Gunakan huruf kecil dan tanda hubung untuk slug. Aturan yang sama berlaku untuk pengembang maupun agen.

Gunakan `feat/` untuk fitur, `fix/` untuk perbaikan perilaku, `chore/` untuk CI dan pemeliharaan, `refactor/` untuk perubahan struktur, serta `docs/` untuk dokumentasi. Branch berumur pendek dan ditujukan ke `main` melalui MR.

Alurnya adalah branch perubahan, implementasi dan verifikasi lokal, MR ke `main`, review bukti, merge setelah pipeline hijau, build ARM64, integrasi core dan Airflow, deployment otomatis, lalu pemeriksaan bukti release.

Proteksi `main` menggunakan Allowed to push **No one**, Allowed to merge **Maintainers**, dan force push nonaktif. Merge mensyaratkan pipeline berhasil. Pipeline skipped tidak memenuhi syarat. Hapus source branch setelah merge. Squash dipilih ketika merapikan commit pekerjaan menjadi satu perubahan yang dapat ditinjau.

Gunakan template MR bawaan untuk menjelaskan perilaku pengguna, bukti pengujian, kebutuhan bootstrap atau migrasi, dan rollback. Persetujuan harus mencakup commit terbaru. Merge ke `main` memicu deployment produksi setelah semua gate berhasil.

## Pemeriksaan sebelum merge

`verify-backend` memeriksa tes backend terpilih dan lint. `verify-frontend` menjalankan lint serta build frontend. `verify-deployment` menjalankan kontrak release/lifecycle dan request deployment pada Linux. Gate deployment juga berjalan pada protected `main` sebelum build.

```sh
python -B scripts/checks/airflow/check-airflow-contracts.py
python -B scripts/checks/check-production-request.py
```

Kedua perintah membutuhkan Linux, Python 3.12 dan Git. Suite lifecycle membutuhkan root untuk memverifikasi penolakan pengguna tidak berwenang. Gunakan container lokal terisolasi untuk menjalankannya.

Pengujian platform image dan observasi worker Docker berada di `scripts/checks/airflow/check-airflow-docker-contracts.py`. CI menjalankannya sesudah gate Airflow dengan `YUNESA_CONTRACT_IMAGE` menunjuk digest image Airflow hasil build. Pemeriksaan ini membutuhkan Docker lokal.

## Deployment dan bukti release

Sebelum deploy, request memastikan pipeline berasal dari protected default branch dan commit masih sama dengan HEAD remote. Kegagalan membaca HEAD menghentikan request sebelum helper deployment dipanggil. Rollback manual tetap dapat dijalankan dari pipeline lama untuk pemulihan.

Helper produksi harus mengenali probe stdin JSON `{"release_evidence_protocol":2}`. Respons memuat versi protokol, `operation_seconds=1800`, dan `recovery_seconds=1200`. Probe memakai command `deploy` yang sudah diizinkan sudoers dan berhenti setelah membaca konfigurasi tepercaya, sebelum membuat state atau menjalankan Docker. Refresh bootstrap yang ditinjau melalui installer administratif sebelum pertama kali menggunakan request versi ini. Helper lama ditolak pada pemeriksaan protokol sebelum deployment dimulai.

Wrapper memberi operasi utama 30 menit dan recovery anggaran terpisah 20 menit. Deadline operasi atau SIGTERM/SIGINT masuk ke jalur recovery yang sama dengan kegagalan deployment. SIGTERM/SIGINT berikutnya yang diterima wrapper selama recovery tidak mereset anggarannya. Kegagalan drain mempertahankan admission tertutup dan dilaporkan sebagai `quiescence_closed`. Setelah readiness dan lifecycle terverifikasi, finalisasi singkat pointer release menyelesaikan penulisan metadata sebelum mengakhiri operasi.

Client menunggu gabungan anggaran wrapper ditambah 120 detik, yaitu 3120 detik pada konfigurasi ini. Job deploy/rollback mempunyai timeout 60 menit untuk pemeriksaan awal, recovery, finalisasi dan pengunggahan artifact. Recovery yang melewati deadline dilaporkan `deadline_exceeded`. SIGKILL, host mati atau I/O kernel yang macet memerlukan pemeriksaan manual terhadap jurnal serta runtime aktual.

Request memvalidasi commit, checksum konfigurasi, lima digest image, readiness storage/auth/persistence/provider dan lifecycle Airflow. Rollback memvalidasi identitas release tujuan. Release lama sebelum integrasi Airflow boleh memiliki kedua identitas image ETL kosong hanya ketika lifecycle OFF.

Job deploy dan rollback menyimpan `artifacts/production-release.json` serta `artifacts/production-health.json` selama 30 hari dengan `when: always`. Kegagalan merekam tahap, kategori, exit code wrapper bila tersedia, status recovery, dan `diagnostic_reference`. Referensi berbentuk `release-<32 digit hex>` menunjuk `/opt/yunesa-app/diagnostics/<referensi>.jsonl`. Direktori milik root berizin 700 dan file berizin 600. Catatan di-flush serta fsync saat setiap tahap berubah, dan mempertahankan kegagalan utama bersama hasil recovery. Jurnal menyimpan label command, exit code dan error wrapper yang disaring terhadap secret request. Raw stdout/stderr command tidak disimpan. Artifact hanya menerima field terstruktur yang diizinkan. Jika penyimpanan jurnal gagal, referensi dilaporkan tidak tersedia. Pembatalan paksa job dapat menghentikan proses sebelum artifact selesai ditulis.

Image rollback mempertahankan volume bersama. Tinjau kompatibilitas skema dan kebutuhan pemulihan data sebelum menggunakan rollback pada perubahan migrasi.
