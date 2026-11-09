# Persiapan lokal acceptance ARM64 native

Tanggal 8 November 2026, zona waktu Asia/Jakarta. Pemilik mengotorisasi adaptor native dua vCPU, bundle image, controller satu jam dan verifikasi cleanup lokal. AWS launch, perubahan produksi, commit dan push tetap di luar otorisasi. Task 6.3 tetap terbuka dengan progres OpenSpec 25/28.

## Jalur yang disiapkan

`check-airflow-arm64-vm.py --native-lease --bundle --proof` menjadi entrypoint SSH untuk resource sementara yang kelak diotorisasi. Jalur tersebut memeriksa identitas IMDSv2 sebelum mutasi guest, memeriksa checksum bundle/source, memasang dependency OS, memuat image, lalu menjalankan prepare dan measure pada `check-airflow-arm64-capacity.py --mode native --lease`. Jalur emulasi mempertahankan default dan pemeriksaannya sendiri.

Adaptor native mensyaratkan identitas account/region/AMI/instance/type dari lease, Linux ARM64, dua vCPU dan RAM dalam 4 MiB dari `1,879,024 KiB`. Zram memakai target audited `939,508 KiB`, dengan disk swap 4 GiB. Pengaturan health probe berasal dari Compose sumber. Pengecualian timeout/probe QEMU tidak diterapkan pada mode native.

`airflow_capacity_session.py` membagi validasi sesi dan deadline absolut antara guest, driver dan controller. Lease memiliki jangka tepat 3.600 detik. ID tiga instance existing yang telah diinventaris ditolak secara eksplisit, dan resource juga harus cocok tag sesi, launch token, waktu launch serta identitas fixture. Clock workload tidak di-reset saat controller dibuat ulang.

`airflow-native-controller.py` menyediakan render offline, pemeriksaan watchdog, supervisi command anak dan cleanup untuk fixture yang sudah dibuat. Operasi AWS dibatasi allowlist pembacaan dan cleanup. Controller tidak menyediakan launch atau create-resource. Mutasi cleanup melalui CLI mensyaratkan `--allow-cloud-cleanup`.

## Controller dan cleanup

Watchdog guest memakai timer UTC persisten pada menit 54 dengan shutdown behavior EC2 `terminate`. Scheduler mempunyai target satu instance pada menit 55, flexible window OFF, dua retry dengan event age 120 detik dan auto-delete schedule. Sebelum workload, controller memeriksa schedule, policy/trust role dan hash unit guest yang aktif.

Command anak mempunyai batas absolut menit 51. Pada deadline controller menghentikan tree proses lokal dan menjalankan finalizer. Receipt atomik menyimpan event dan kegagalan. Controller baru mempertahankan receipt, dapat melanjutkan cleanup parsial, dan menolak replay workload yang sudah dimulai. Error awal tetap terlihat ketika cleanup ikut gagal.

Finalizer menargetkan ID fixture yang tercatat, menunggu termination secara bounded, memeriksa penghapusan EBS/ENI, lalu membersihkan schedule, SG, key pair, inline policy/role dan private key lokal dengan path/hash yang cocok. Respons EC2 terminal dapat kehilangan mapping disk/interface, sehingga verifikasi state tersebut mempertahankan pemeriksaan identitas/tag/token dan memakai ID inventaris untuk audit penghapusan. AccessDenied tidak diperlakukan sebagai resource absent. Resource ancillary dengan tag berbeda dipertahankan dan dilaporkan sebagai pending.

Jika controller offline, Scheduler/guest mengakhiri compute. SG/key pair/IAM yang belum dibersihkan menunggu controller kembali. Presisi Scheduler dan waktu termination AWS tetap menjadi batas eksternal. Pengiriman nyata dan izin mutasi belum diuji.

## Bukti lokal

| Pemeriksaan | Hasil |
| --- | --- |
| Regresi Windows, Python 3.12 | 24 pemeriksaan passed, 19,722 detik pada run final |
| Regresi Linux, checker tanpa jaringan | 24 pemeriksaan passed, 19,060 detik pada run final |
| Subprocess controller | Command Python nyata berhasil, exit 7 diteruskan, proses sleep nyata dihentikan pada deadline, dan interupsi tetap menuju cleanup |
| Validasi identitas/kapasitas | Data ARM64 dua vCPU/RAM target diterima. Delapan vCPU, AMD64, RAM berlebih, identitas produksi dan lease lebih panjang ditolak |
| Failure/recovery controller | Missing/wrong watchdog, IAM trust salah, tag asing, AccessDenied, cleanup parsial, receipt lintas sesi dan replay mempunyai jalur penolakan atau recovery |
| Kontrak artefak kapasitas | Driver mensyaratkan `result.json` dengan identitas fixture, successful run, hasil graph, worker kosong, peak worker teramati, pelepasan memori, application cycles dan restart delta nol. Nilai gagal/parsial ditolak oleh pemeriksaan kontrak lokal |
| SDK Scheduler | `aws scheduler create-schedule --generate-cli-skeleton output` menerima payload secara offline, exit 0. Endpoint diarahkan ke loopback dan memakai credential sintetis khusus validasi |
| Unit systemd | `systemd-analyze verify` dan `systemd-analyze calendar` menerima unit service/timer serta tanggal UTC. File disalin ke container dengan mode 0644 sebelum pemeriksaan |
| CLI image ARM64 | `python -m server.worker_health` pada network `none` menolak Redis scheme invalid dengan exit 1 dan satu baris `Worker heartbeat check failed (RuntimeError)`, tanpa traceback atau password |
| Docker archive | Sembilan konfigurasi Linux ARM64, tag set sesuai, checksum dan gzip CRC diverifikasi |
| Arsip terpotong | Salinan 64 KiB awal arsip sebenarnya ditolak dengan EOFError. Salinan negatif dibersihkan |
| Docker load nyata | Sembilan image diimpor dari arsip, exit 0, 398,75 detik. Seluruh identitas image cocok sebelum/sesudah |

Deadline subprocess diuji dengan lease satu jam yang waktu mulainya digeser mendekati batas menit 51. Waktu tunggu proses berjalan nyata selama sisa pendek tersebut. Pengujian tidak menunggu satu jam penuh. AWS EC2/IAM/Scheduler dan SSH guest memakai boundary fixture karena resource berbayar dan hardware native belum diotorisasi. Controller, finalizer, persistence receipt, CLI render dan subprocess bukan mock. Container Linux diberi network `none` sehingga regresi itu tidak menghubungi AWS.

Pemeriksaan image ARM64 lokal menggunakan dukungan eksekusi ARM64 Docker pada laptop AMD64. Pengujian ini mencakup packaging/CLI. Penerimaan workload dan kapasitas EC2 native belum dijalankan. Docker load menggunakan content store lokal yang telah mempunyai image tersebut. Durasi fresh import pada EC2 belum diukur.

## Koreksi selama persiapan

Inspeksi alias image multiarsitektur tanpa platform eksplisit sempat memilih konfigurasi AMD64. Bundle preparer kini memilih `linux/arm64` secara eksplisit pada inspect/save/create dan memeriksa konfigurasi di arsip.

Pemeriksaan CLI menemukan ARQ melempar `RuntimeError` untuk Redis URI scheme invalid. Health module sebelumnya menangani ValueError, OSError dan RedisError. Handler diperluas dengan RuntimeError, kemudian thin image dan bundle dibangun ulang. Pemeriksaan akhir memastikan exit nonzero, error teredaksi serta tidak ada traceback/credential.

Model boundary EC2 diperbaiki agar respons merupakan snapshot dan mapping disk/interface dapat kosong setelah termination. Regresi akhir memeriksa cleanup dengan bentuk respons terminal tersebut. Ini tetap verifikasi lokal atas kontrak API, dengan perilaku AWS aktual sebagai batas yang belum dilalui.

## Artefak dan provenance

Bundle aktif berada di `.cache/airflow-native-preparation/bundle-v2/` dan diabaikan Git.

- `images.tar.gz` berukuran **2.446.742.583 byte**, SHA-256 `62f362d38d975c934ecaba90d538cad00dfafdf9d3d454a8519fe1ee06274566`.
- `source.tar.gz` berukuran **57.363 byte**, SHA-256 `0a24a5dee069f5bf2d6c7721b412528dc6c0040504c6c9537b2588179faa5f45` pada source refresh final.
- `bundle.json` mencatat sembilan image, source bootstrap/helper, hash module health, seluruh Python orchestration, handler KG, factory Memgraph dan writer graph yang dibaca kembali dari filesystem image.
- Git HEAD referensi tetap `b6924e196f6728c73dd70864c20b1c655db9f50f`. Manifest file yang belum di-commit mencatat source sebenarnya, termasuk perbaikan setelah HEAD tersebut.

Log regresi berada di `.cache/airflow-native-controller-{windows,linux}-check.log`. Proof schema, systemd, health image dan load tersimpan di `.cache/airflow-native-preparation/`. Arsip image generasi pertama yang sudah digantikan dihapus setelah cocok checksum dan path workspace diverifikasi. Manifest/receipt cleanup-nya tetap tersedia.

## File yang disentuh

- `scripts/rehearsal/arm64/airflow_capacity_session.py` untuk identitas/deadline/payload watchdog.
- `scripts/rehearsal/arm64/airflow-native-controller.py` untuk render, preflight, supervisi serta cleanup.
- `scripts/rehearsal/arm64/check-airflow-native-preparation.py` untuk regresi lokal dengan batas AWS/SSH eksplisit.
- `scripts/rehearsal/arm64/prepare-airflow-arm64-bundle.py` untuk build thin image, pencocokan source, export, refresh source dan verify.
- `scripts/rehearsal/arm64/check-airflow-arm64-capacity.py` dan `scripts/rehearsal/arm64/check-airflow-arm64-vm.py` untuk jalur native pada verifier existing.
- `backend/server/worker_health.py` untuk error scheme Redis yang teredaksi.
- Runbook [rencana launch](../operations/airflow-arm64-native-launch-plan.md) dan laporan ini.

## Batas yang masih terbuka

Persiapan lokal tidak membuktikan availability launch, IAM write/PassRole, delivery Scheduler, timer poweroff aktual, IMDS nyata pada fixture, startup/DAG/paging pada native ARM64 atau cleanup AWS end-to-end. Throughput upload belum diukur. Arsip memerlukan sekitar 32,6 Mbps payload agar transfer selesai sepuluh menit, sebelum overhead. Instalasi dan load juga harus masuk tahap bootstrap 20 menit.

Task 6.3 memerlukan hasil workload, destination query, resource peak, core traffic dan successful OFF pada fixture native yang kelak diotorisasi. Task 6.2 mempertahankan batas provider/chat dan task 5.5 memerlukan jendela produksi terpisah. ING-001/KG-001 tetap mempunyai penerimaan sendiri.
