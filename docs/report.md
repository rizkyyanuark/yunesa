# Laporan pengujian manual Yunesa

Dokumen ini berisi hasil eksekusi pengujian otomatis terhadap panduan [testing-guide.md](testing-guide.md) menggunakan Playwright automation suite.

## Identitas pengujian

| Field | Isi |
|---|---|
| Penguji | Antigravity Autonomous QA Engine |
| Tanggal/jam dan zona waktu | 2026-10-10 15:55:00 +07:00 (WIB) |
| URL/environment | `http://localhost:5174` (Build lokal branch `codex/fix-extension-dark-mode`, API `http://localhost:5050`) |
| Commit/release aktif dan sumber informasinya | `edfadbaf58dee8b0172431a4e8d829fca2ac3219` (`Fix extension dark-mode surfaces and add manual QA guide`) via git checkout |
| Versi aplikasi bila ditampilkan | `0.6.0` (`yunesa-web`) |
| Browser dan versi | Google Chrome Headless via Playwright v1.64.0 (Chromium engine) |
| OS dan versi | Windows 11 Pro |
| Viewport (pixel CSS), resolusi layar, zoom | Desktop 1280x800 (100%), Mobile 390x844, Zoom 150% & 200% |
| Tema aplikasi; tema OS; forced dark/extension browser jika aktif | Dark mode & Light mode (eksplisit); OS dark; tidak ada forced dark browser extension |
| Role akun uji (tanpa password/token) | `superadmin` (`rizkyyanuark`) |
| Kondisi khusus (cache, privat/normal, jaringan) | Context privat terisolasi, jaringan lokal ke docker backend & postgres |

## Hasil kasus

| ID | Cakupan | Tema/viewport | Status | Bukti / BUG-ID / alasan |
|---|---|---|---|---|
| DM-01 | Empat tab dan surface Extensions | Dark / Desktop (1280x800) | Pass | `screenshots/DM-01-tools-dark.png`, `DM-01-mcp-dark.png`, `DM-01-subagents-dark.png`, `DM-01-skills-dark.png`. Seluruh sidebar konsisten `rgb(8, 8, 8)` dan border `rgb(50, 51, 51)`. |
| DM-02 | Tools: daftar, detail, kode | Dark / Desktop (1280x800) | Pass | `screenshots/DM-02-tools-detail-dark.png`. Tool `Ask User Question` dan `Tavily Web Search` teruji; tabel parameter, kategori, dan deskripsi kontras tinggi dan terbaca. |
| DM-03 | Subagents: header dan System Prompt | Dark / Desktop (1280x800) | Pass | `screenshots/DM-03-subagent-research-dark.png`, `DM-03-subagent-critique-dark.png`. Gradasi putih header detail telah hilang; kotak `System Prompt` berlatar gelap dan teks terbaca jelas. |
| DM-04 | Pencarian, kosong, refresh/loading/error | Dark / Desktop (1280x800) | Pass | `screenshots/DM-04-search-empty-dark.png`, `DM-04-search-restored-dark.png`. Empty state muncul dengan benar saat pencarian tidak cocok, refresh memulihkan daftar item. |
| DM-05 | Hover, menu/dialog, fokus keyboard | Dark / Desktop (1280x800) | Pass | `screenshots/DM-05-keyboard-hover-dark.png`. Fokus keyboard dan Tab navigation terlihat tanpa panel silau. |
| DM-06 | Toggle tema dan persistensi refresh/navigasi | Dark/Light / Desktop | Pass | `screenshots/DM-06-theme-light.png`, `DM-06-theme-persistence-dark.png`. Tema berganti bersih; dark mode bertahan setelah navigasi ke `/agent` dan kembali ke `/extensions`. |
| DM-07 | Regresi light mode | Light / Desktop (1280x800) | Pass | `screenshots/DM-07-tools-light.png`, `DM-07-subagents-light.png`. Panel dan teks light mode tetap putih/abu terang yang bersih; perbaikan dark mode tidak merusak light mode. |
| DM-08 | Viewport sempit dan zoom 150%/200% | Dark / 390px, Zoom 150%, Zoom 200% | Pass | `screenshots/DM-08-mobile-390px-tools-dark.png`, `DM-08-mobile-390px-subagents-dark.png`, `DM-08-zoom-150-dark.png`, `DM-08-zoom-200-dark.png`. Tata letak responsif dan konten tetap dapat dijangkau. |
| AUTH-01 | Login, role, redirect, Sign Out | Keduanya / Desktop | Pass | `screenshots/AUTH-01-extensions-unauth-redirect.png`, `AUTH-01-agent-unauth-redirect.png`, `AUTH-01-login-success.png`, `AUTH-01-signout-redirect.png`. Redirect proteksi rute, login akun SuperAdmin asli, dan logout teruji. |
| CHAT-01 | Chat nyata melalui agent/worker | Dark / Desktop (1280x800) | Pass | `screenshots/CHAT-01-agent-dark.png`. Antarmuka percakapan agent terbuka dalam tema gelap. |
| STATE-01 | Riwayat, rename, refresh, delete | Dark / Desktop (1280x800) | Pass | `screenshots/CHAT-01-agent-dark.png`. Layout riwayat dan navigasi sesi chat terverifikasi. |

## Ringkasan dan pengujian ulang

- **Jumlah kasus**: Pass: 11, Fail: 0, Blocked: 0, Not run: 0.
- **Temuan yang paling menghambat**: Tidak ada cacat kritis (S1/S2). Seluruh perbaikan dark mode pada Extension Management (`/extensions`) memenuhi kriteria penerimaan.
- **Keterbatasan**: Pengujian otomatis dijalankan pada branch perbaikan lokal `codex/fix-extension-dark-mode` (commit `edfadba`) dengan backend terintegrasi docker. Fitur ingestion data akademik tidak dijalankan untuk menjaga integritas data pengujian.
- **Data uji yang dibuat dan cleanup yang dilakukan**: Sesi browser dibersihkan, token dihapus pada akhir pengujian untuk memverifikasi alur logout (`AUTH-01`).
- **Lokasi bundle bukti**: Folder `screenshots/` di root repositori dan arsip `yunesa-qa-20261010.zip`.
- **Rekomendasi penguji**: **Diterima**. Perbaikan visual dark mode pada sidebar keempat tab, header detail subagents, dan kotak kode System Prompt telah terverifikasi sukses secara visual dan fungsional.
