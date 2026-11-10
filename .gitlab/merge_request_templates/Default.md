## Perubahan perilaku

Jelaskan pemicu perubahan dan hasil yang dapat diamati pengguna.

## Bukti verifikasi

| Skenario | Perintah atau jalur pengguna | Hasil aktual | Bukti |
|---|---|---|---|
| Jalur utama | | | |
| Kegagalan atau batas yang relevan | | | |

## Dampak release

- Kebutuhan migrasi data atau perubahan secret
- Kebutuhan refresh bootstrap dan kompatibilitas release sebelumnya
- Dampak pada aplikasi, database, DAG, worker dan lifecycle Airflow
- Rencana rollback serta batas pemulihan data

## Pemeriksaan merge

- [ ] Bukti sesuai dengan commit terbaru dan batas pengujian dicatat.
- [ ] Semua gate MR berhasil dan review selesai.
- [ ] Perubahan bootstrap, migrasi atau konfigurasi produksi mempunyai rencana pelaksanaan.
- [ ] Artifact release dan health akan ditinjau setelah deployment otomatis selesai.
