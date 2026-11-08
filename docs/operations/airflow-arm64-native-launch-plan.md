# Rencana instance ARM64 sementara untuk task 6.3

Disiapkan pada 8 November 2026, zona waktu Asia/Jakarta. Penyusunan rencana dilanjutkan dengan persiapan dan pengujian lokal yang diotorisasi pemilik. Launch, perubahan produksi, commit, dan push masih memerlukan instruksi tersendiri. Task 6.3 tetap terbuka.

## Sasaran dan batas penerimaan

Gunakan satu EC2 `t4g.small` terpisah untuk menguji delapan service core, Airflow, dan satu DAG KG melalui jalur aplikasi sebenarnya. Seluruh image harus Linux ARM64. Gunakan data sintetis serta credential fixture baru. Provider/chat tetap ditunda.

Penerimaan mencakup seluruh hasil berikut.

- Frontend, login, penolakan akses tanpa otorisasi, dan conversation write/read/delete berhasil sebelum, selama, dan setelah workload.
- DAG `unesa_kg_construction` mencapai `success` melalui API, scheduler, operator, dan container ETL sebenarnya.
- Workload dibatasi satu sampel, GLiNER dimatikan, graph write diaktifkan, dan vector write dimatikan. Query Memgraph independen menghasilkan empat node dan lima relationship dalam namespace fixture.
- Sampling RAM/swap host, zram, PSI, cgroup peak/events dan restart mencakup startup serta worker. Worker singkat harus tetap mempunyai bukti peak yang tersimpan sebelum container dihapus.
- Tidak ada OOM atau kenaikan restart pada percobaan yang diterima. Identitas delapan container core tetap sama selama pengukuran.
- CLI OFF berhasil, admission tertutup, init dan runtime Airflow berhenti, reservation kosong, serta nol worker ETL aktif. Catat pelepasan memori setelah OFF dengan pengukuran sebelum/sesudah.
- Simpan run ID, manifest source/image, rentang observasi, hasil aplikasi, destination query, exit code dan cleanup receipt di laptop.

Deadline, hilangnya sampling, kegagalan workload, atau forced termination sebelum OFF selesai menghasilkan bukti kegagalan/parsial. Status 6.3 mengikuti hasil tersebut. Keberhasilan init saja belum memenuhi penerimaan.

## Konfigurasi yang diusulkan

| Komponen | Rencana |
| --- | --- |
| Region dan AZ | `us-east-1`, `us-east-1c` |
| Compute | Satu `t4g.small` On-Demand, ARM64, dua vCPU, RAM nominal 2 GiB |
| CPU credit | `unlimited`, sama dengan konfigurasi Yunesa yang dibaca. Rekam credit balance/surplus dan batasi seluruh percobaan satu jam |
| AMI | Kandidat Canonical `ami-0bec8cef5313300ad`, Ubuntu 24.04 ARM64, owner `099720109477`. Revalidasi sebelum launch |
| Linux-visible RAM | Target audit Yunesa `1,879,024 KiB`. Toleransi perbedaan kernel maksimum 4 MiB, catat nilai aktual dan selisih bertanda |
| Disk | Satu root gp3 40 GiB terenkripsi dengan AWS-managed key, IOPS/throughput bawaan, `DeleteOnTermination=true` |
| Swap | Disk swap `4,194,300 KiB` usable dan zram zstd sekitar `939,508 KiB`, prioritas zram 100. Rekam kapasitas aktual dan toleransi rounding 4 KiB |
| Network | Kandidat VPC `vpc-090590aa06ada5b80`, subnet `subnet-05e0009ae63fcd4e7`. Gunakan route/IGW existing setelah revalidasi |
| Security group | Group fixture baru, SSH hanya dari IP operator `/32`, tanpa port aplikasi publik. Tidak menggunakan SG produksi |
| Konektivitas keluar | HTTPS untuk dependency yang telah ditetapkan dan DNS. Tidak memasang NAT gateway, load balancer, atau VPC endpoint baru |
| IP publik | Satu IPv4 ephemeral. Tidak mengalokasikan Elastic IP |
| SSH dan identitas | Key pair sementara, IMDSv2 wajib, tanpa IAM instance profile atau credential AWS di guest |
| Project fixture | Project/root/network/volume khusus sesi. Nama sesi unik disertakan pada tag dan manifest, dengan tag `Purpose=yunesa-task-6-3` serta `ExpiresAt` UTC |
| Secrets dan data | Credential acak khusus fixture, izin file terbatas, tanpa salinan database, key, log atau secret produksi |

Guest menggunakan kernel/systemd/Docker sendiri dan menjalankan ARM64 langsung pada Graviton. VM ini berada pada VPC existing, sehingga pengujian harus menjaga pemisahan credential, volume, service dan port. Akses aplikasi melalui SSH tunnel atau jaringan internal fixture. Workload tidak menghubungi storage/provider produksi.

Subnet mempunyai route existing `0.0.0.0/0` menuju IGW. Pada pemeriksaan, AMI berstatus `available`, arsitektur `arm64`, dan subnet mempunyai 4.090 alamat IPv4 tersedia. Pemeriksaan ini belum membuktikan kapasitas launch EC2, izin perubahan IAM, `iam:PassRole`, atau izin penulisan Scheduler.

## Estimasi biaya total

Asumsi perhitungan adalah satu jam, Linux On-Demand di `us-east-1`, gp3 40 GiB, satu IPv4, tanpa Marketplace software fee dan tanpa kredit/free-tier yang diasumsikan. Konversi memakai kurs perencanaan **Rp17.000/US$**, bukan kurs pasar yang diverifikasi. November dihitung 720 jam untuk prorata EBS.

| Komponen | Estimasi US$ | Dasar |
| --- | --- | --- |
| EC2 satu jam | 0,016800 | AWS Pricing API, SKU `9GWX7R3VJUG9P8Y8`, diperiksa pada 8 November 2026 |
| gp3 40 GiB satu jam | 0,004444 | `40 × 0,08 / 720` |
| IPv4 satu jam | 0,005000 | Tarif US$0,005/alamat/jam |
| Subtotal tanpa surplus CPU | **0,026244** | Sekitar **Rp446** |
| Surplus CPU dalam skenario dua core 100% selama satu jam | Hingga sekitar 0,064000 | Baseline 20% per vCPU, `2 × (1 − 0,20) × 0,04`. Rekonsiliasi mengikuti credit aktual |
| Subtotal termasuk skenario CPU tersebut | **0,090244** | Sekitar **Rp1.534**, sebelum transfer/pajak |
| Alokasi transfer/export proof maksimum 100 MiB | 0,010000 | Cadangan perencanaan, pemakaian/free allowance akun belum diperiksa |
| Cadangan tersisa sampai anggaran | 0,049756 | Pajak, pembulatan, invocation Scheduler dan keterlambatan singkat cleanup |
| Anggaran perencanaan seluruh percobaan | **US$0,15 / Rp2.550** | Tidak menjanjikan batas tagihan AWS yang keras |

T4g memperoleh 24 CPU credit/jam dan tidak memperoleh launch credit. Surplus yang belum terbayar dapat ditagihkan saat terminate. Simpan metrik credit yang tersedia dan rekonsiliasi biaya setelah pemakaian muncul. Invocation Scheduler memakai free tier jika masih tersedia. Di luar free tier, satu invocation bernilai sangat kecil dan masuk cadangan. Bukti tagihan mungkin muncul setelah instance dihapus. [CPU dan tarif On-Demand](https://aws.amazon.com/ec2/pricing/on-demand/), [baseline credit](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html), [tagihan surplus saat terminate](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode-concepts.html)

Tarif EBS dan IPv4 dihitung terpisah dari compute. Resource nonbillable seperti SG, key pair dan IAM role tetap termasuk inventaris cleanup. [EBS](https://aws.amazon.com/ebs/pricing/), [IPv4](https://aws.amazon.com/vpc/pricing/), [EventBridge Scheduler](https://aws.amazon.com/eventbridge/pricing/)

## Persiapan sebelum waktu berbayar

Tahap ini harus selesai sebelum satu instance diminta. Dokumen ini belum menjalankan tahap tersebut.

1. Siapkan adaptor native pada helper yang sudah ada. Helper saat ini mensyaratkan delapan vCPU dan mempunyai pengaturan timing QEMU. Jalur native harus memverifikasi dua vCPU, Linux ARM64, toleransi RAM, metadata identitas EC2 fixture, dan deadline absolut. Pertahankan validasi jalur emulasi secara terpisah.
2. Gunakan probe/timing dari Compose sumber untuk native. Hindari membawa `start_period=1800s`, `start_interval=120s`, atau deadline init 3600 detik dari pengecualian QEMU. Setiap timeout eksperimental tambahan harus dinyatakan dalam bukti.
3. Siapkan image ARM64 dengan module `server.worker_health` terbaru. Image API yang ada di Docker laptop masih bertag `integration-arm64`, sementara thin image perbaikan berada pada disk guest QEMU. Buat/revalidasi thin image secara lokal sebelum launch, tanpa menyalakan kembali workload QEMU.
4. Inventaris sembilan image dari Docker lokal, verifikasi `Architecture=arm64`, simpan image/config digest, hash bundle dan source file manifest. Working tree berisi perubahan yang belum di-commit, sehingga HEAD saja tidak mewakili seluruh source yang diuji.
5. Ekspor dan kompres bundle di laptop. Ukur ukuran aktual. Tidak ada build aplikasi atau push registry eksternal pada instance. Transfer dilakukan dengan SSH ke instance sementara, lalu `docker load` dari stream agar tidak memerlukan salinan tar besar di root disk.
6. Ukur/perkirakan koneksi upload sebelum launch. Bundle harus dapat ditransfer dan dimuat dalam jendela persiapan 20 menit. Jika waktu transfer tidak dapat diperkirakan dengan memadai, persiapan satu jam belum siap.
7. Siapkan paket Docker/Python/helper, source bootstrap, input akademik sintetis, unit watchdog, controller berdeadline dan manifest cleanup secara lokal. Verifikasi sintaks dan penanganan error/interupsi tanpa membuat resource AWS.
8. Review izin IAM, quota On-Demand Graviton, availability AMI, default EBS encryption, IP operator dan kapasitas subnet. Tidak mengaktifkan layanan, mengubah quota, atau memperluas policy produksi secara otomatis.
9. Selesaikan review controller dan izin launch. Gunakan client token idempoten per sesi. Jika respons launch tidak pasti, cari instance dengan token/tag sesi sebelum mencoba ulang, agar hanya satu instance dibuat.

## Batas satu jam dan urutan percobaan

Tetapkan `T0` dari waktu UTC controller tepat sebelum request `RunInstances`, serta `E=T0+60 menit`. Clock instance dan controller harus sinkron. Semua deadline adalah waktu absolut yang sama, termasuk bila SSH atau controller tersambung ulang. Tampilan operator menyertakan WIB dan UTC. Satu jam mencakup launch, bootstrap, transfer, workload, ekspor dan cleanup.

| Waktu sejak T0 | Tahap dan batas |
| --- | --- |
| 0–2 menit | Terima/pulihkan ID instance, pasang termination Scheduler dan read-back target/deadline. Jika watchdog AWS belum terkonfirmasi dalam dua menit, terminate fixture segera |
| 2–20 menit | Konfirmasi guest watchdog, identitas EC2/ARM64/RAM, swap, dependency dan image load. Jika persiapan belum selesai pada menit 20, simpan kegagalan lalu cleanup |
| 20–27 menit | Delapan service core sehat dan baseline aplikasi lolos. Aborsi bila baseline belum lolos pada menit 27 |
| 27–35 menit | CLI ON serta readiness/import DAG. Deadline ON dibatasi sisa waktu tahap. Kegagalan langsung menuju bukti dan cleanup |
| 35–42 menit | Jalankan satu DAG KG dan trafik aplikasi bersamaan. Pada menit 42 berhenti menunggu hasil baru dan mulai drain/ekspor |
| 42–47 menit | Query hasil, OFF dan pengukuran memori. Bounded OFF menerima maksimum sisa waktu tahap. Simpan kondisi draining jika masih ada aktivitas |
| 47–51 menit | Ekspor proof terpilih, verifikasi hash dan penerimaan lokal. Streaming log/sampel sudah berlangsung sejak awal agar putus koneksi tetap menyisakan bukti |
| 51–54 menit | Jalur normal langsung terminate, tunggu status dan bersihkan inventaris sementara |
| Menit 54 | Watchdog guest mengajukan poweroff dengan EC2 shutdown behavior `terminate` |
| Menit 55 | Scheduler AWS mengajukan `TerminateInstances` pada ID fixture yang sama, independen dari laptop dan guest |
| 55–60 menit | Cadangan delivery/retry dan verifikasi cleanup. Tidak ada retry workload, perpanjangan waktu, restart atau instance pengganti |

Scheduler mempunyai presisi 60 detik. Termination juga bergantung pada respons AWS, sehingga satu jam adalah deadline operasional dengan margin, bukan jaminan shutdown atau tagihan berhenti pada detik tepat. Jika state belum `terminated` pada E, controller melakukan retry termination terarah dan melaporkan penyimpangan waktu. [Presisi Scheduler](https://docs.aws.amazon.com/scheduler/latest/UserGuide/schedule-types.html)

## Cleanup otomatis

### Watchdog AWS

Sebelum launch, siapkan role Scheduler sementara dengan trust `scheduler.amazonaws.com`, pembatasan source account/group, dan izin terminate hanya pada instance bertag sesi fixture. Setelah ID instance diperoleh, batasi resource policy ke ARN instance itu sebelum mengaktifkan jadwal. Role tidak ditempelkan pada guest.

Buat satu schedule UTC sekali jalan pada T0+55 menit, flexible window `OFF`, `ActionAfterCompletion=DELETE`, dan target universal `arn:aws:scheduler:::aws-sdk:ec2:terminateInstances`. Input berisi satu ID fixture yang diverifikasi, tanpa wildcard atau selector produksi. Gunakan retry maksimum dua kali dan event age 120 detik. Read-back harus cocok dengan ID, sesi, deadline, role dan region sebelum bootstrap/workload dilanjutkan.

Jika pemasangan/read-back schedule gagal, jalur error controller segera men-terminate instance baru. Jika launch atau penyiapan berhenti sebelum ID diterima, controller memulihkan ID melalui client token/tag sesi. Watchdog guest menjadi lapisan tambahan selama celah pemasangan schedule. Kemampuan write/pass-role dan delivery end-to-end belum diuji pada tahap rencana. [Universal target](https://docs.aws.amazon.com/scheduler/latest/UserGuide/managing-targets-universal.html), [CreateSchedule](https://docs.aws.amazon.com/scheduler/latest/APIReference/API_CreateSchedule.html), [retry policy](https://docs.aws.amazon.com/scheduler/latest/APIReference/API_RetryPolicy.html)

### Watchdog guest

User data memasang timer systemd absolut pada T0+54 menit sebelum instalasi paket besar. Timer persisten saat reboot dan mengajukan shutdown jika deadline sudah lewat. Tetapkan `InstanceInitiatedShutdownBehavior=terminate` saat launch. Watchdog diperiksa sebelum menjalankan aplikasi. Jika verifikasinya gagal, controller mengakhiri fixture. Laptop terputus tidak membatalkan schedule AWS atau timer guest.

Poweroff dapat terlambat ketika guest bermasalah. Scheduler AWS tetap menargetkan instance. Pada deadline, cleanup boleh mengakhiri task/migrasi sintetis yang masih aktif. Hasil tersebut wajib dicatat sebagai pengujian parsial/gagal dan tidak digunakan sebagai bukti successful OFF. [Termination dan volume](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/how-ec2-instance-termination-works.html)

### Finalizer controller dan pemeriksaan akhir

Controller mencatat ID instance, volume, ENI, SG, key pair, role/policy dan schedule segera setelah setiap operasi berhasil. `finally` mencakup selesai normal, error, timeout dan interupsi yang dapat ditangani. Cleanup hanya menyentuh ID yang tercatat dan memiliki identitas sesi cocok. Nama atau prefix saja tidak cukup.

1. Simpan bukti terpilih yang sudah tersedia, dengan batas waktu ekspor dan redaksi credential.
2. Panggil terminate pada instance fixture, lalu tunggu `terminated` secara bounded.
3. Konfirmasi root EBS terhapus, ENI launch terhapus dan IPv4 ephemeral dilepas. Semua volume yang dibuat saat launch harus mempunyai `DeleteOnTermination=true`.
4. Hapus schedule setelah termination terverifikasi bila masih ada. Schedule yang terpicu juga memiliki auto-delete.
5. Hapus SG fixture setelah ENI terlepas, key pair sementara, inline policy/role Scheduler serta private key fixture lokal. Pertahankan receipt dan bukti yang sudah disanitasi.
6. Bandingkan inventaris sebelum/sesudah dan laporkan resource tersisa secara eksplisit. Ulangi cleanup hanya untuk ID sesi yang sama.

Jika laptop mati, Scheduler dan guest menangani pengakhiran compute. EBS dengan delete-on-termination serta IPv4 ephemeral mengikuti lifecycle instance. SG, key pair dan IAM role tidak terhapus otomatis oleh termination. Finalizer akan membersihkannya saat controller kembali, dan audit tertunda ini harus muncul pada laporan. Resource tersebut tidak mempunyai biaya per jam tersendiri. Rencana tidak mengklaim seluruh resource ancillary terhapus saat controller offline.

## Status kesiapan saat rencana dibuat

| Pemeriksaan | Status |
| --- | --- |
| Harga EC2, spesifikasi dan mode CPU target | Dibaca dari AWS API |
| Kandidat AMI, subnet dan route existing | Dibaca dari AWS API |
| Scheduler dapat diinventaris | Berhasil, belum ada schedule di region pada saat pemeriksaan |
| ARM64 API/Airflow/ETL image di Docker laptop | Architecture dan identitas dibaca. API perlu thin image dengan health module terbaru |
| Adaptor native dua vCPU dan controller satu jam | Implementasi lokal tersedia. Regresi controller mencakup subprocess nyata, deadline, interupsi, identitas resource, cleanup parsial dan replay |
| Bundle kompresi serta estimasi upload/load | Sembilan image ARM64 telah diekspor dan diverifikasi. Arsip sekitar 2,45 GB. Kecepatan upload menuju EC2 masih belum diukur |
| Write IAM, PassRole dan Scheduler | Belum dibuktikan |
| Cleanup AWS end-to-end | Belum diuji |
| Launch dan penerimaan task 6.3 | Menunggu instruksi terpisah dan kesiapan di atas |

Tahap rencana diikuti persiapan lokal. Controller, adaptor dan bundle didokumentasikan dalam [bukti persiapan native](../evidence/airflow-native-preparation-2026-11-08.md). Hasil diagnosis sebelumnya tersedia dalam [laporan fixture](../evidence/airflow-diagnosis-2026-11-08.md).

## Entrypoint persiapan lokal

Bundle aktif berada di `.cache/airflow-native-preparation/bundle-v2/`. File `bundle.json` memetakan source yang belum di-commit, sembilan image, ukuran arsip dan checksum. `source.tar.gz` berisi helper dan orchestration yang diperlukan. `images.tar.gz` memakai Docker archive untuk platform `linux/arm64`.

```powershell
python scripts/prepare-airflow-arm64-bundle.py verify --output .cache/airflow-native-preparation/bundle-v2
python scripts/check-airflow-native-preparation.py
```

Jika hanya helper lokal berubah, `refresh-source` memperbarui arsip source setelah memeriksa ulang arsip image serta source aplikasi tertanam. Perubahan source aplikasi memerlukan image yang cocok dan bundle baru.

Controller `airflow-native-controller.py` mempunyai operasi `render`, `check`, `supervise` dan `cleanup`. Implementasi ini tidak mempunyai operasi launch atau pembuatan resource. `render` sepenuhnya offline. `check` membaca EC2, Scheduler dan IAM lalu memeriksa timer guest melalui SSH. `supervise` dan `cleanup` memerlukan flag eksplisit `--allow-cloud-cleanup`. Flag tersebut baru digunakan pada fixture yang sudah dibuat dalam tahap yang diotorisasi tersendiri.

Lease aktual mencatat `session` berupa 16 karakter heksadesimal, `account_id`, `region`, `instance_id`, `started_at` dan `expires_at` numerik dengan selisih tepat 3.600 detik, serta `volume_id`, `eni_id`, `security_group_id` dan `key_pair_id`. Bagian `ssh` mencatat `host`, `key`, `key_sha256` dan `known_hosts`. Semua tag `ExpiresAt` memakai representasi integer Unix UTC yang sama. Nama resource mengikuti `yunesa-6-3-<session>`. Path private key berada di bawah direktori receipt, dalam subdirektori bernama sesi tersebut, dengan nama file `fixture_ed25519`.

`render` menghasilkan policy terminate dengan ARN instance tunggal dan kondisi tag, trust Scheduler dengan source account/group, payload schedule menit 55, serta unit systemd menit 54. Contoh yang dipakai pemeriksaan lokal menggunakan account/instance sintetis. Contoh tersebut tidak digunakan untuk launch. Sebelum menjalankan workload, controller memeriksa shutdown behavior `terminate`, identitas/tag/token/waktu launch EC2, root EBS delete-on-termination, ENI/SG, ketiadaan Elastic IP, target/deadline/role schedule, policy/trust IAM dan hash unit guest yang aktif.

Pada tahap cloud yang kelak diotorisasi, command anak untuk `supervise` adalah entrypoint `check-airflow-arm64-vm.py` dengan `--native-lease`, `--bundle` dan `--proof`. Jalur native ini memeriksa IMDSv2 sebelum mutasi guest, memasang dependency, memuat image, menjalankan prepare/baseline/measure, mengalirkan observasi ke laptop dan mengekspor proof terpilih. Guest menerima lease root-owned dan menggunakan `check-airflow-arm64-capacity.py --mode native --lease` sebagai jalur kapasitas yang sama. Jalur QEMU tetap menggunakan default `emulated`.

Controller menghentikan command anak paling lambat menit 51 dan menjalankan finalizer. Receipt disimpan atomik serta dipertahankan ketika cleanup dilanjutkan. Workload yang sudah dimulai tidak diputar ulang oleh controller baru. Jika deadline tercapai sebelum ekspor final selesai, `observations.jsonl` dan log lokal yang sudah dialirkan tetap menjadi bukti parsial, dan penerimaan gagal. Scheduler/guest tetap menjadi jalur pengakhiran saat controller mati.

Ukuran bundle 2.446.742.583 byte membutuhkan throughput payload sekitar 32,6 Mbps untuk transfer sepuluh menit, atau 16,3 Mbps untuk dua puluh menit, sebelum overhead. Jendela bootstrap 20 menit juga mencakup instalasi dan `docker load`, sehingga angka 16,3 Mbps belum memadai untuk menyatakan kesiapan. Ukur koneksi dan cadangkan waktu load sebelum memutuskan launch satu jam.
