# Retest Extensions Yunesa — 10 Oktober 2026

Perbaikan surface dark mode, fokus filter Tools, keterbacaan chip, serta layout mobile dan jendela pendek sudah berjalan melalui aplikasi nyata. Chat singkat, penyimpanan pesan/judul, cleanup, dan proteksi rute juga berhasil. Zoom bawaan Chrome 150%/200% telah diuji: pemilik mengubah pengaturan zoom, lalu Codex mengukur layout, menjalankan interaksi, dan menyimpan screenshot.

Laporan ini menggantikan ringkasan sebelumnya setelah pengujian diambil alih atas permintaan pemilik. Laporan kolega sebelum takeover disimpan sebagai `screenshots/original/report-colleague-before-takeover.md` dalam bundle. Bukti lama di luar `screenshots/takeover/` merupakan provenance, bukan hasil retest source terbaru.

## Identitas dan batas lingkungan

| Field | Hasil terverifikasi |
|---|---|
| Penguji | Codex, melalui kontrol browser; login dilakukan pemilik akun |
| Tanggal | 10 Oktober 2026, WIB; chat dan pemeriksaan akhir dimulai sekitar 22:46 |
| Frontend | `http://127.0.0.1:5174`, Vite 7.3.1 dari worktree lokal |
| Backend | Proxy `/api` ke `https://yunesa.tugasakhir.space`; memakai API produksi |
| Source | Branch `codex/fix-extension-dark-mode`, HEAD dasar `a1af17ec84758458ce1c81fd3f5e010d60bc4c78` ditambah perubahan worktree yang dicatat di bawah |
| Identitas runtime | File lokal dilayani Vite dan perubahan terlihat melalui UI/HMR; bukan deployment source ini ke produksi |
| Browser | Codex In-app Browser dan Chrome; versi browser/OS tidak dikumpulkan |
| Viewport | IAB 1280×800, 390×844, reflow 854×533/640×400; Chrome native zoom 150%: 853×414, 200%: 640×311 pixel CSS |
| Tema | Dark/light dipilih melalui menu avatar; tema OS tidak dikumpulkan |
| Akses | Akun pemilik dengan role SuperAdmin; tanpa password/token dalam bukti |
| Data uji | Satu percakapan baru, satu prompt singkat tanpa tool; tidak mengubah provider, role, extension, ingestion, atau data akademik |

Source belum di-commit pada saat diuji. SHA256 berikut berasal dari file worktree dengan line ending CRLF. Git menormalisasi blob ke LF sesuai `.gitattributes`; manifest bundle juga mencatat hash blob Git agar reviewer dapat membandingkan source yang dipublikasikan tanpa menyamakan kedua representasi byte tersebut.

| File | SHA256 |
|---|---|
| `web/src/assets/css/extensions.less` | `d721479cee9b5b06d279e7d75e6ee42b173b7c6ec229c8efa125ea013dc30b0c` |
| `web/src/components/SubAgentsComponent.vue` | `9bbf1f5833dfaa58544fbbe00eb4e5b0fa2dc684cbd4cb0e64d0f925e8c39f08` |
| `web/src/components/ToolsManagerComponent.vue` | `b102b659dd665cc48bbdcda506eb50832098790ab1406f0329b39a08cce4cc34` |
| `web/src/views/ExtensionsView.vue` | `0cb780f007bd65b46a93a68644be85e0006e8a5bea59912bd8c3f1af1e67d3de` |

## Hasil kasus

Nama bukti berikut relatif terhadap `screenshots/takeover/` di bundle. Langkah pengujian mengacu pada [panduan](testing-guide.md). Status berlaku untuk cakupan yang dijelaskan; bukan audit seluruh fitur aplikasi.

| ID | Status | Eksekusi dan bukti |
|---|---|---|
| DM-01 | Pass | Keempat tab dimuat dari API nyata dalam dark mode. Sidebar `rgb(8, 8, 8)`, detail dan header mengikuti tema. `DM-01-tools-dark.jpg`, `DM-01-mcp-dark.jpg`, `DM-01-skills-dark.jpg`, `DM-03-subagents-dark.jpg`. |
| DM-02 | Pass | Ask User Question: Description, kategori, tag, dan tabel Arguments terbaca; detail dapat discroll sampai akhir. `DM-01-tools-dark.jpg`, `DM-08-tools-390-scroll-dark.jpg`. Tidak menjalankan tool tersebut. |
| DM-03 | Pass | Research dan critique dipilih melalui UI. Header tidak bergradasi putih; System Prompt gelap dengan foreground `rgb(215, 217, 217)` dan background `rgb(21, 22, 22)`. `DM-03-subagents-dark.jpg`, `DM-03-critique-dark.jpg`. |
| DM-04 | Pass | Pencarian cocok/tidak cocok, clear, dan refresh dijalankan pada Tools/MCP/Subagents/Skills. Daftar pulih; Skills memuat tree dan SKILL.md. Loading tombol disabled sempat diamati. `qa-results.json`, `DM-04-tools-empty.jpg`, `DM-07-skills-light.jpg`. Kegagalan jaringan paksa tidak disimulasikan. |
| DM-05 | Pass | Filter Tools: Enter membuka menu; Escape dari item menu menutup dan mengembalikan fokus ke trigger; kategori Debug menunjukkan hasil kosong dan All memulihkan. Tab menuju Refresh, Shift+Tab kembali ke search. Space/Enter memilih kartu Tools. `DM-05-menu-open.jpg`, `DM-05-escape-focus.jpg`, `qa-results.json`. Tidak mengklaim audit keyboard penuh pengelolaan MCP/Skills/Subagents. |
| DM-06 | Pass | Toggle dark→light→dark melalui avatar. Reload dark dan light mempertahankan pilihan. Navigasi `/agent`→`/extensions` mempertahankan dark. `DM-06-reload-dark.jpg`, assertion reload/navigation di `qa-results.json`. Tidak merekam video untuk menilai kilatan warna selama pemuatan. |
| DM-07 | Pass | Keempat tab dibuka dalam light mode. Tools tag memakai gray-700; Added memakai success-900. Kontras Added light 9.15:1/dark 10.06:1; metadata light 4.70:1. Warna terukur dari DOM final. `DM-07-tools-light.jpg`, `DM-07-subagents-light.jpg`, `DM-07-mcp-light.jpg`, `DM-07-skills-light.jpg`. |
| DM-08 | Pass | Pada 390 px detail selebar 340 px; daftar/detail dapat discroll tanpa overflow horizontal halaman. Native zoom Chrome 150% terukur DPR 2.25 dengan viewport 853×414; 200% DPR 3 dengan viewport 640×311 (baseline DPR 1.5). Tools/Subagents dapat discroll sampai akhir; pencarian dan empat tab dapat diakses. Pada jendela pendek, halaman dapat discroll dan detail mempertahankan tinggi sekitar 261 px. Retest source final 150% dan 390 px lulus. `DM-08-subagents-390-dark-final.jpg`, `DM-08-native-150-tools-dark-final.jpg`, `DM-08-native-150-subagents-dark-final.jpg`, `DM-08-native-200-tools-scroll.jpg`, `DM-08-native-200-subagents-dark.jpg`, `DM-08-native-200-subagents-scroll.jpg`. CSS zoom tidak digunakan. Zoom dikembalikan ke 100% dan DPR 1.5 terverifikasi. |
| AUTH-01 | Pass | Login pemilik memberi akses SuperAdmin. Sign Out melalui UI menuju `/login`; akses langsung `/extensions` dan `/agent` sesudahnya kembali ke login. Request tanpa kredensial `GET /api/auth/me` melalui proxy menghasilkan 401, `Please log in first`. `AUTH-01-signout.jpg`, `AUTH-01-extensions-protected.jpg`, `AUTH-01-agent-protected.jpg`, `AUTH-01-api-unauthorized.json`. Tidak mengklaim pengujian semua role atau revocation token server. |
| CHAT-01 | Pass | Smart Assistant menerima satu pesan `QA-20261010: balas hanya "Halo QA" tanpa menggunakan tools.` dan menampilkan respons selesai `Halo QA`. `CHAT-01-real-response.jpg`. Memakai provider/worker nyata; tidak membuktikan retrieval akademik. |
| STATE-01 | Pass | Percakapan `05ac6ae5-de33-430f-8e17-8de722894cd2` di-rename menjadi `QA-dark-mode-20261010`. Reload mempertahankan pesan, respons, dan judul. Hanya chat ini dihapus melalui soft delete aplikasi; setelah reload tidak muncul, percakapan lama `Hello` tetap ada. `STATE-01-renamed-reloaded.jpg`, `STATE-01-cleanup.jpg`. |

Ringkasan akhir: **11 Pass, 0 Fail, 0 Blocked** pada cakupan di tabel. `qa-results.json` juga menyimpan pengukuran, observation, dan kegagalan sebelum perbaikan; jumlah assertion tidak sama dengan jumlah kasus akhir. Keterbatasan kontrol zoom otomatis diselesaikan dengan bantuan pemilik mengubah zoom Chrome. Probe yang salah container atau terlalu dini selama animasi dicatat sebagai observation dan diikuti pemeriksaan container/state yang benar.

## Temuan dan retest

- **BUG-001, Skills tree:** laporan sebelumnya menyebut HTTP 404. Pada API produksi yang dipakai retest, tree dan SKILL.md `deep-reporter` berhasil dimuat. Tidak direproduksi; topologi backend pengujian lama belum terverifikasi. Tidak ada perubahan backend untuk temuan ini.
- **BUG-002, detail mobile terdesak:** diperbaiki dengan susunan daftar di atas detail pada lebar ≤768 px. Lebar detail 340 px pada viewport 390 px dan scroll sampai bagian terakhir terbukti melalui UI.
- **Kontras light mode:** Added sebelumnya terukur sekitar 3.37:1. Token success-900 memperbaikinya menjadi 9.15:1. Chip metadata dan tag Tools ikut memakai token foreground yang lebih terbaca.
- **Filter keyboard:** Escape dan pemilihan kategori sekarang menutup menu dan mengembalikan fokus; kartu Tools dapat dipilih dengan Enter/Space.
- **BUG-003, jendela pendek pada zoom 200%:** viewport 640×311 menyisakan detail setinggi 24 px. Pada lebar ≤768 px dan tinggi ≤480 px, layout kini memberi main panel minimal 340 px serta scroll halaman. Detail terukur sekitar 261 px dan scroll sampai bagian terakhir lulus. Bukti sebelum perbaikan: `DM-08-native-200-before-fix.jpg`; hasil final: `DM-08-native-200-subagents-dark.jpg`.

## Pemeriksaan source dan bukti

Perintah dari direktori `web`:

```powershell
node node_modules/eslint/bin/eslint.js .
node node_modules/vite/bin/vite.js build
```

Keduanya exit 0 setelah perubahan source terakhir. Build mentransformasi **8651 modules**, selesai **1m13s**. Warning chunk >500 kB masih ada; tidak menghalangi build. Log: `frontend-lint.log`, `frontend-build.log`. Screenshot desktop source final: `DM-03-subagents-dark-desktop-final.jpg`.

`scripts/sanitize-qa-evidence.py` memeriksa JSON bukti sebelum dibagikan. Satu field password multipart yang tertinggal di log kolega telah disanitasi. Pemeriksaan ulang bersih; tidak mengirim nilai kredensial ke reviewer. Log browser takeover tidak memuat error/warning pada pengambilan terakhir. Sanitasi otomatis tidak menggantikan pemeriksaan visual gambar atau audit keamanan menyeluruh.

Bundle `yunesa-qa-20261010.zip` memuat laporan, catatan review, bukti lama yang diberi provenance, bukti takeover, dan manifest hash. Screenshot/ZIP/log merupakan artifact generated yang diabaikan Git. Gunakan attachment retest yang ditautkan pada deskripsi MR/PR; attachment awal hanya memuat bukti pengujian sebelumnya.

## Keputusan

Seluruh kasus yang dijadwalkan pada tabel didukung bukti nyata. Hasil ini cukup untuk review perubahan Extensions; bukan penerimaan seluruh fitur Yunesa. Tinjau commit final dan bundle retest sebelum merge. CI hanya berjalan pada protected `main` dan merge memicu deployment produksi; pengujian yang lulus tidak otomatis menyetujui deployment. MR belum di-merge.
