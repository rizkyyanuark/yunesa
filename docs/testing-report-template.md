# Laporan pengujian manual Yunesa

Salin template ini menjadi `report.md`. Ikuti [panduan pengujian](testing-guide.md); isi hasil berdasarkan eksekusi yang benar-benar dilakukan.

## Identitas pengujian

| Field | Isi |
|---|---|
| Penguji | |
| Tanggal/jam dan zona waktu | |
| URL/environment | |
| Commit/release aktif dan sumber informasinya | Unknown sampai dikonfirmasi pemilik deployment |
| Versi aplikasi bila ditampilkan | |
| Browser dan versi | |
| OS dan versi | |
| Viewport (pixel CSS), resolusi layar, zoom | |
| Tema aplikasi; tema OS; forced dark/extension browser jika aktif | |
| Role akun uji (tanpa password/token) | |
| Kondisi khusus (cache, privat/normal, jaringan) | |

## Hasil kasus

Ganti status awal dengan `Pass`, `Fail`, `Blocked`, atau `Not run`. Bukti dapat berupa nama file screenshot, catatan hasil yang konkret, atau BUG-ID. Jelaskan alasan untuk kasus yang belum dapat diperiksa.

| ID | Cakupan | Tema/viewport | Status | Bukti / BUG-ID / alasan |
|---|---|---|---|---|
| DM-01 | Empat tab dan surface Extensions | | Not run | |
| DM-02 | Tools: daftar, detail, kode | | Not run | |
| DM-03 | Subagents: header dan System Prompt | | Not run | |
| DM-04 | Pencarian, kosong, refresh/loading/error | | Not run | |
| DM-05 | Hover, menu/dialog, fokus keyboard | | Not run | |
| DM-06 | Toggle tema dan persistensi refresh/navigasi | | Not run | |
| DM-07 | Regresi light mode | | Not run | |
| DM-08 | Viewport sempit dan zoom 150%/200% | | Not run | |
| AUTH-01 | Login, role, redirect, Sign Out | | Not run | |
| CHAT-01 | Chat nyata melalui agent/worker | | Not run | |
| STATE-01 | Riwayat, rename, refresh, delete | | Not run | |

## Temuan BUG-001

Duplikasi bagian ini untuk setiap masalah. Pisahkan temuan yang memiliki langkah atau akar masalah berbeda.

| Field | Isi |
|---|---|
| Judul singkat | |
| Case ID / URL / tab / nama item | |
| Severity dan dampak bagi pengguna | S1 / S2 / S3 / S4; jelaskan dampaknya |
| Prasyarat | Role, tema, data/item yang dipilih |
| Frekuensi | ... dari ... percobaan |
| Screenshot/rekaman | `screenshots/BUG-001-....png` |
| Log sanitasi / HTTP status / request ID | Jika ada; jangan isi credentials |
| Workaround | Ada/tidak; langkah bila ada |

Langkah reproduksi:

1. [isi langkah]
2. [isi langkah]
3. [isi langkah]

Expected: [isi hasil yang diharapkan]

Actual: [isi hasil yang terjadi]

Perbandingan light/dark, viewport lain, atau sesudah refresh: [isi]

## Ringkasan dan pengujian ulang

- Jumlah kasus: Pass ..., Fail ..., Blocked ..., Not run ...
- Temuan yang paling menghambat: [isi]
- Keterbatasan: item/role/perangkat/fitur yang belum dapat diperiksa; ingestion/KG tidak otomatis dianggap lulus.
- Data uji yang dibuat dan cleanup yang dilakukan: [isi]
- Lokasi bundle bukti: [isi]
- Rekomendasi penguji: diterima / perlu perbaikan / belum cukup bukti, beserta alasan.
- Pengujian ulang: BUG-ID ..., build ..., tanggal ..., hasil ..., bukti ...
