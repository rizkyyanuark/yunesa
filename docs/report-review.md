# Review retest Extensions — 10 Oktober 2026

Perbaikan berjalan melalui frontend lokal dan API produksi: surface dark mode selaras, chip light mode terbaca, filter Tools dapat ditutup dengan Escape, dan detail pada viewport 390 px serta zoom Chrome 150%/200% dapat diakses. Satu chat nyata serta rename, reload, soft delete, dan logout telah diuji. Hasil dan identitas source tersedia pada [laporan retest](report.md).

Review source empat file frontend tidak menemukan masalah yang menghalangi cakupan tersebut. Lint seluruh frontend dan build terakhir exit 0. Build masih memberi warning chunk besar yang sudah ada; CI belum diubah pada saat retest UI 10 Oktober.

## Batas penerimaan

**11 kasus Pass, 0 Fail, 0 Blocked** pada cakupan laporan. Pemilik mengatur zoom bawaan Chrome; Codex memverifikasi DPR/viewport dan menjalankan interaksi. Zoom 200% menemukan detail setinggi 24 px pada jendela 640×311, lalu perbaikan jendela pendek memberi detail sekitar 261 px dengan scroll halaman. Retest 200%, 150%, dan mobile source final lulus. Bukti viewport reflow sebelumnya tetap dicatat terpisah dari native zoom.

Skills tree yang sebelumnya dilaporkan gagal berhasil dimuat dari API produksi. Hasil tersebut tidak membuktikan backend lokal kolega telah diperbaiki. Chat umum yang berhasil juga tidak membuktikan ingestion, knowledge graph, atau retrieval akademik siap produksi.

## Provenance bukti

- Source yang diuji adalah HEAD `a1af17e` ditambah worktree lokal; SHA256 empat file dicatat dalam laporan dan manifest bundle.
- Bukti final berada pada `screenshots/takeover/`. Bukti lama serta salinan laporan kolega diberi identitas terpisah.
- Log JSON disanitasi kembali sebelum packaging. Satu credential multipart yang tersisa telah dihapus dari bukti lokal.
- Manifest bundle mencatat hash file worktree yang diuji dan hash blob Git dengan normalisasi line ending. Deskripsi MR/PR menautkan bundle retest beserta SHA256 arsip; attachment awal tetap merupakan bukti pengujian sebelumnya.

## Status review dan release

[GitLab MR !1](https://gitlab.tugasakhir.space/rizkyyanuark/yunesa/-/merge_requests/1) adalah review utama; [GitHub PR #1](https://github.com/rizkyyanuark/yunesa/pull/1) salinan manual. Keduanya tetap draft untuk review source dan bukti final pada branch `codex/fix-extension-dark-mode`.

Pembaruan CI 11 Oktober menambahkan pemeriksaan frontend dan backend pada MR; lihat [panduan deployment](deployment.md#gate-aplikasi-sebelum-release). Bukti UI tetap merujuk source frontend `7db7258`; perubahan CI tidak mengubah empat file frontend yang diuji. Tinjau diff final, hasil pipeline commit terbaru, dan bukti retest sebelum merge. Merge ke protected `main` akan menjalankan build, integrasi, dan deployment produksi otomatis. Environment staging terpisah belum tersedia; merge dan deployment belum dilakukan.
