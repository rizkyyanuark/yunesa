# Indeks spesifikasi Yunesa

Paket v0.1, 9 Oktober 2026. Struktur ini menggunakan Markdown; toolkit OpenSpec belum dipasang.

## Mulai di sini

- [PRD](../PRD.md): tujuan dan kebutuhan produk.
- [Arsitektur](../ARCHITECTURE.md): kondisi kode dan target.
- [Panduan agen](../AGENTS.md): aturan kerja.
- [Alur pengembangan](../docs/development.md): dari proposal ke bukti.
- [Keputusan produk](../docs/decisions/0001-yunesa-product-contract.md): keputusan yang berlaku.

## Perubahan

| ID | Cakupan | Status |
|---|---|---|
| [ING-001](changes/ing-001-academic-data/proposal.md) | Identitas, publikasi, kepenulisan, sumber, dan kontrak data | Scope accepted; desain/tugas disiapkan; belum diimplementasikan |
| [KG-001](changes/kg-001-knowledge-graph/proposal.md) | Ringkasan Inggris, ekstraksi, KG, indeks, dan pipeline | Scope accepted; proposal awal; bergantung pada ING-001 |
| [ANS-001](changes/ans-001-evidence-answers/proposal.md) | Jawaban, sitasi, graph bukti, dan akses | Scope accepted; proposal awal; bergantung pada KG-001 |

ING-001: [desain](changes/ing-001-academic-data/design.md), [tugas](changes/ing-001-academic-data/tasks.md), [delta spec](changes/ing-001-academic-data/specs/academic-data/spec.md), [verifikasi](changes/ing-001-academic-data/verification.md).

## Capability specs

[Index capability](specs/README.md) belum memuat kontrak yang telah diverifikasi penuh. Requirement baru berada dalam folder perubahan sampai implementasi dan bukti penerimaannya selesai.

Penerbitan dokumen tidak menandai kemampuan aplikasi sebagai lulus pengujian. Perubahan selesai harus memperbarui capability spec sebelum diarsipkan.

