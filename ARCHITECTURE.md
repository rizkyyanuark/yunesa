# Arsitektur Yunesa

Tanggal baseline: 9 Oktober 2026. Dokumen ini memisahkan kondisi source yang diperiksa dari target yang telah dipilih pemilik produk.

## Status dan batas bukti

Baseline berasal dari pembacaan source di folder `yunesa`. Keberadaan modul, konfigurasi, atau tes tidak membuktikan layanan sedang berjalan atau perilakunya telah lolos pengujian.

Target di bawah menjadi arah implementasi berikutnya. Penulisan dokumen ini tidak mengubah aplikasi, database, model, konfigurasi deployment, atau remote Git.

## Stack dan pintu masuk saat ini

| Lapisan | Kondisi source | Pintu masuk |
|---|---|---|
| Web | Vue 3, Vite, Pinia, Ant Design Vue; pnpm 10.11.0 | [package.json](web/package.json), [router](web/src/router/index.js) |
| HTTP API | FastAPI; router bisnis berada di `/api` | [server.main](backend/server/main.py), [router registry](backend/server/routers/__init__.py) |
| Agent dan pekerjaan latar | Streaming chat, sinkronisasi, run, cancel dan events; worker Arq dengan Redis | [chat router](backend/server/routers/chat_router.py), [worker](backend/server/worker_main.py) |
| Library aplikasi | Python 3.12; package lokal editable | [backend project](backend/pyproject.toml), [package](backend/package/yunesa) |
| ETL | CLI worker memilih task; Airflow menjadwalkan task melalui DockerOperator | [ETL worker](backend/package/yunesa/etl/run_worker.py), [DAG](orchestration/dags) |
| Metadata akademik | Jalur load paper yang diperiksa memakai PostgreSQL; adapter dan skema Supabase juga masih tersedia | [paper service](backend/package/yunesa/etl/services/unesa_papers.py), [Postgres client](backend/package/yunesa/etl/clients/postgres_client.py), [SQL Supabase](docs/database/supabase-schema.sql) |
| Graph dan retrieval | Builder NetworkX, graph storage, vector storage, AcademicGraphRAG | [knowledge](backend/package/yunesa/knowledge), [GraphRAG](backend/package/yunesa/graphrag) |

Router web saat ini menyediakan landing/login/OIDC, chat `/agent`, dashboard dan graph untuk admin, serta extensions untuk superadmin. Route `/database` mengarah ke `/graph`; adanya file view lama tidak menjamin fitur tersebut aktif.

## Batas modul

| Modul | Tanggung jawab yang dipertahankan | Batas yang harus dijaga |
|---|---|---|
| `etl/clients` | Berkomunikasi dengan satu sumber seperti UNESA, PDDIKTI, Scholar, Scopus atau layanan enrichment | Menghasilkan record sumber dan status fetch; tidak menetapkan identitas kanonis dari nama yang ambigu |
| `etl/services` dan `etl/pipelines` | Mengatur extraction, normalization, enrichment, checkpoint dan load | Menyimpan hasil per paper serta alasan kegagalan; satu kegagalan tidak menghapus record lain |
| `etl/transform` | Membersihkan nilai, melengkapi metadata dan membuat ringkasan | Menjaga metadata asli, hasil turunan dan provenance sebagai informasi terpisah |
| Identity dan metadata | Menetapkan Author/paper kanonis dan menghubungkan external ID | Satu aturan identitas dipakai loader, builder dan retrieval; kandidat ambigu tetap unresolved |
| `knowledge` | Ontologi, ekstraksi, normalisasi konsep, graph dan quality checks | Hanya ringkasan yang valid menjadi input ekstraksi semantik; metadata tetap membentuk relasi struktural |
| `graphrag` | Mengambil evidence graph/vector dan menggabungkan hasil | Evidence mendukung klaim jawaban; hubungan semantik tidak dinaikkan menjadi fakta authorship |
| API dan worker | Otorisasi, lifecycle run, response dan event | Validasi payload dan hak akses di server; UI guard tidak menggantikan pemeriksaan server |
| Web | Chat mahasiswa, hasil dosen terstruktur dan penelusuran bukti | Memakai kontrak hasil/evidence; tidak membuat relasi graph dari tebakan jawaban LLM |

Baris Identity dan metadata menyatakan batas target. Implementasi saat ini masih tersebar dalam cleaner, enricher, loader, dan builder; dokumen ini tidak mengklaim modul baru sudah tersedia.

## Alur target yang disetujui

1. Scraper mengambil profil author dan paper, lalu menyimpan snapshot sumber beserta waktu, sumber dan identitas record sumber.
2. Normalizer mempertahankan metadata asli dan menghasilkan record kanonis. ID profil sumber terverifikasi memetakan identitas Author. Hubungan Author-Publication dibentuk otomatis hanya ketika record kepenulisan sumber mendukung pemetaan tersebut; bukti yang belum cukup tetap unresolved.
3. Enrichment melengkapi metadata. Record yang belum lengkap tetap tersimpan dengan daftar field yang hilang dan alasan kegagalan.
4. Generator membuat ringkasan berbahasa Inggris sekitar 2 sampai 4 kalimat dari judul dan abstract asli. Ringkasan berorientasi ontologi dan hanya memuat informasi yang didukung judul atau abstract.
5. Validator otomatis memeriksa kelengkapan metadata dan ringkasan. Hasil yang lolos langsung disimpan ke database sesuai tahapnya.
6. Ekstraktor mengambil unsur semantik hanya dari ringkasan tervalidasi. Builder menggabungkannya dengan metadata publikasi, identitas Author dan peran Lecturer yang terverifikasi.
7. Graph dan vector index diterbitkan sebagai versi yang dapat ditelusuri. Retrieval menghasilkan hasil dosen, evidence dan subgraf yang mendukung jawaban.
8. Chat menampilkan hasil terstruktur dan jalur hubungan yang dapat dibuka sampai sumber pendukungnya.

Pipeline ini berjalan tanpa review, persetujuan, atau kurasi manusia. Identitas ambigu disimpan sebagai unresolved dan dievaluasi ulang otomatis ketika evidence baru tersedia. Ambiguitas tidak boleh berubah menjadi verified hanya karena retry selesai atau skor kemiripan tinggi.

Pemrosesan dijalankan mingguan dan dapat dipicu manual. Retry dibatasi per paper, mempunyai alasan serta waktu retry berikutnya, dan tidak mengulang seluruh korpus karena satu kegagalan. Batas percobaan, backoff dan batas beban diputuskan dalam spec; nilainya belum diukur atau ditetapkan di sini.

Keberhasilan ingestion, kelengkapan metadata, validitas ringkasan, kesiapan KG dan kesiapan retrieval merupakan status berbeda. Status berhasil menyimpan record tidak berarti record tersebut siap dipakai untuk jawaban.

## Identitas dan ontologi target

`Author` menjadi entitas penulis kanonis, termasuk penulis eksternal. `Lecturer` adalah peran dosen yang didukung profil atau identitas institusi terverifikasi. Status dosen tidak diberikan hanya karena nama penulis mirip nama dosen.

Baseline ontologi riset berasal dari [constants.py](backend/package/yunesa/knowledge/constants.py): Problem, ResearchTopic, Task, Method, Model, Algorithm, Tool, Dataset, Metric, Result, Innovation, Domain/Field dan Keyword. Implementasi saat ini menyimpan kategori tersebut pada `concept_type` milik node `Concept`.

Relasi baseline mencakup `HAS_AUTHOR`, `PUBLISHES`, `HAS_TOPIC`, `SOLVES_PROBLEM`, `WORKS_ON_TASK`, `USES_METHOD`, `USES_MODEL`, `USES_DATASET`, `EVALUATED_WITH`, `HAS_RESULT`, `PROPOSES_INNOVATION`, `BELONGS_TO_DOMAIN`, `HAS_KEYWORD`, `COLLABORATES_WITH` dan `PUBLISHED_IN_VENUE`. Migrasi Author dan peran Lecturer harus mempertahankan makna relasi tersebut serta versi skemanya.

[IEEE taxonomy](backend/package/yunesa/knowledge/resources/ieee-taxonomy.ttl) dan [thesaurus](backend/package/yunesa/knowledge/resources/ieee-thesaurus.ttl) menjadi vocabulary untuk normalisasi dan hierarki konsep. Keduanya tidak menggantikan skema relasi aplikasi. Alias otomatis harus menyimpan evidence dan versi resolusi; hasil ambigu tidak memerlukan antrean review manusia.

Satu aturan `paper_id` dan mapping `(source, external_author_id)` ke Author kanonis diperlukan. DOI yang baru ditemukan atau metadata judul yang diperbaiki harus memperbarui identitas/evidence tanpa menghasilkan paper duplikat atau memutus relasi yang sah. Bentuk tabel serta strategi migrasinya masih perlu spec teknis.

## Evidence graph untuk jawaban

Source sudah mengembalikan graph per query. [AcademicGraphRAG](backend/package/yunesa/graphrag/academic_graphrag.py) menggabungkan subgraf retrieval, structured rows dan graph query. [Tool KB](backend/package/yunesa/agents/toolkits/kbs/tools.py) mempertahankan entities/relationships dalam citations, lalu mengirim graph ringkas ke UI.

[QueryKbTool](web/src/components/ToolCallingResult/tools/QueryKbTool.vue) dan [KbResultGroupedList](web/src/components/sources/KbResultGroupedList.vue) sudah memiliki wiring graph, grounding, canvas dan daftar triples. Alur ini belum dibuktikan dengan pengujian runtime pada folder baru.

Target kontrak evidence harus menghubungkan hasil dosen atau klaim jawaban dengan node/edge ID, paper, source snapshot, versi metadata, versi ringkasan/extractor dan versi graph. Setiap edge memiliki jenis hubungan serta dasar evidence yang dapat ditelusuri.

Authorship bersumber, hubungan konsep hasil extraction, hierarki IEEE dan kemiripan vector mempunyai makna berbeda. UI harus menjelaskan perbedaannya. Jalur seperti Author, publikasi, metode dan dataset hanya ditampilkan sebagai bukti jika relasinya benar-benar mendukung hasil yang diminta.

Graph yang berhubungan dengan query belum tentu mendukung setiap klaim jawaban. Kontrak hasil harus mencatat klaim mana yang ditopang edge tertentu, cap hasil/subgraf, dan kondisi evidence kosong atau sebagian layanan tidak tersedia.

Untuk aksesibilitas, hasil dan jalur bukti harus tersedia sebagai teks/tabel yang dapat digunakan dengan keyboard. Warna graph tidak menjadi satu-satunya pembeda jenis relasi atau status. Chat dan panel bukti memerlukan keadaan loading, kosong, sebagian berhasil, serta gagal yang dapat dipahami pengguna.

## Deployment yang masih perlu keputusan

| Konfigurasi source | Graph | Vector | Status |
|---|---|---|---|
| [Development Compose](docker-compose.yml) | Neo4j 5.26 | Milvus 2.5.6 | Konfigurasi teramati; runtime belum diverifikasi |
| [Production Compose](docker-compose.prod.yml) | Memgraph | Qdrant | Template teramati; kompatibilitas dan konfigurasi backend belum dibuktikan |

Production template mengisi `QDRANT_URI` dan `MILVUS_URI`, sementara [.env.example](.env.example) memilih `YUNESA_VECTOR_BACKEND=milvus`. Resolver GraphRAG memilih Qdrant jika backend eksplisit `qdrant`, atau jika Qdrant URI tersedia tanpa Milvus/Zilliz URI. Karena itu, tujuan template dan pemilihan adapter belum konsisten.

Belum ada keputusan di dokumen ini untuk mengganti stack. ADR deployment harus menetapkan backend yang didukung, kontrak adapter, kompatibilitas query, resource, backup dan hasil uji sebelum template dianggap siap dipakai. Kesamaan protokol Bolt saja tidak membuktikan kesamaan fitur Neo4j dan Memgraph.

## Delta source terhadap target

| Temuan source | Dampak | Perubahan yang harus dispesifikasikan |
|---|---|---|
| Loader paper aktif memakai PostgreSQL; linking menjadi no-op. Pembaca KG mengisi `nip` dari `author_ids`, sementara cleaner dapat menghasilkan Scholar/Scopus ID | Arti ID berbeda antar tahap. Builder mempunyai lookup alternatif, sehingga hasil pemetaan perlu diuji, bukan diasumsikan | Mapping ID ber-namespace ke Author kanonis, peran Lecturer terverifikasi dan kasus konflik identitas |
| Shared hasher menggunakan DOI dengan prefix atau normalized title + tahun; fallback PostgreSQL memakai MD5 DOI/title lowercase | Paper yang sama dapat memperoleh ID berbeda antar jalur | Satu kontrak identitas, alias ID lama dan penanganan DOI yang baru ditemukan |
| Enrichment membuat `metadata_provenance`, tetapi insert metadata PostgreSQL tidak membawa field tersebut | Sumber field hasil enrichment tidak tersedia melalui record DB yang ditulis jalur ini | Persist provenance/snapshot dan hubungan versi sampai graph serta evidence jawaban |
| Load service memfilter paper yang metadata enrichment-nya belum lengkap | Record gagal belum menjadi record database dengan status kesiapan sesuai target | Menyimpan incomplete, alasan kekurangan, retry state dan readiness per tahap |
| Semantic text saat ini dapat berupa judul + TLDR + keywords atau fallback abstract; regex/IEEE juga membaca metadata teks lain | Input extraction berbeda dari keputusan ringkasan tunggal | Satu input summary tervalidasi untuk semua ekstraksi semantik; metadata hanya membentuk struktur |
| Cleaner dapat memaksa profil owner ke daftar author dan menyaring penulis yang tidak cocok ke daftar dosen | Coauthor eksternal dan ketidakpastian authorship tidak dipertahankan sesuai target | Author umum, evidence mapping, unresolved otomatis dan larangan menganggap owner profile sebagai bukti tunggal |
| UI graph ringkas membatasi node/edge dan membuang sebagian properti edge | Diagram belum menjamin traceability klaim sampai source/version | Evidence ID stabil, provenance yang aman untuk UI dan penanda truncation |

Rujukan delta: [paper load](backend/package/yunesa/etl/services/unesa_papers.py), [Postgres client](backend/package/yunesa/etl/clients/postgres_client.py), [shared hasher](backend/package/yunesa/etl/utils/hasher.py), [KG service](backend/package/yunesa/knowledge/services/kg_service.py), [cleaner](backend/package/yunesa/etl/transform/cleaner.py), [semantic text](backend/package/yunesa/knowledge/utils/text_processing.py), [concept extraction](backend/package/yunesa/knowledge/utils/concept_resolver.py), [tool graph payload](backend/package/yunesa/agents/toolkits/kbs/tools.py).

## Risiko implementasi yang harus ditutup

- KG service memanggil simbol melalui package `knowledge` yang belum semuanya diekspor. Uji import dan sample build diperlukan sebelum menganggap pipeline lengkap.
- [KG construction router](backend/server/routers/conskg_router.py) yang diperiksa belum memasang dependency auth pada build/write. Hak akses server untuk operasi ini harus menjadi bagian spec dan pengujian.
- SQL Supabase yang dipertahankan memuat `DROP TABLE ... CASCADE` dan menonaktifkan RLS. File tersebut merupakan artefak skema, belum rencana migrasi database hidup.
- Template Memgraph memiliki healthcheck dengan fallback `exit 0`. Readiness harus memeriksa query dan jalur aplikasi yang benar-benar berhasil.
- Tes unit/integration tersedia, tetapi keberadaannya bukan hasil lulus. Fixture integration memerlukan API hidup dan kredensial; folder backend e2e yang diperiksa baru memiliki fixture.

Risiko ini adalah hasil inspeksi source, bukan laporan kejadian di deployment. Implementasi perlu menghasilkan bukti uji untuk tiap perubahan.

## Verifikasi dan performa

Verifikasi pertama harus memakai fixture kecil dengan Author internal/eksternal, ID profil terverifikasi dan ambigu, DOI kosong/lalu ditemukan, paper incomplete, ringkasan invalid, retry habis, serta evidence graph per jawaban. Fixture dipisahkan dari data pribadi dan layanan scraping nyata.

Uji harus membuktikan bahwa unresolved tidak menjadi verified, incomplete tetap tersimpan, rerun tidak menggandakan record, ringkasan menjadi satu-satunya input semantik, dan setiap hasil dosen memiliki evidence yang dapat ditelusuri. Pengujian integrasi memerlukan lingkungan yang dipilih serta versi adapter yang dicatat.

Latensi, throughput, RAM, biaya scraping/model dan kualitas retrieval belum diukur pada folder baru. SLO, ukuran batch, retry limit dan klaim peningkatan performa ditetapkan setelah pengukuran dengan dataset, kondisi cache dan konfigurasi yang dicatat.
