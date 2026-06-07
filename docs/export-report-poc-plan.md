# Export Laporan Simulasi - Proof of Concept Plan

## Tujuan

Membuat fitur export laporan otomatis yang menggabungkan diagram rangkaian dan hasil simulasi power flow menjadi satu dokumen rapi. Fitur ini ditujukan untuk laporan praktikum, dokumentasi proyek, dan presentasi hasil simulasi.

## Status Implementasi Saat Ini

PoC **Export Report HTML** sudah masuk ke aplikasi utama.

Yang sudah tersedia di repo saat ini:

- `qt_app.py` sudah punya aksi `EXPORT REPORT`.
- Export laporan menghasilkan file HTML dan file PNG diagram pendamping di folder yang sama.
- `report_export.py` sudah membangun HTML report dari `state.last_results` dan template `docs/report-template.html`.
- Export menolak kondisi tanpa hasil power flow atau hasil yang sudah stale.
- Tombol `Print / Save PDF` sudah tersedia di HTML agar user bisa menyimpan PDF lewat browser.

Yang masih belum ada:

- Smoke test headless khusus untuk jalur report export.
- Export PDF native langsung dari aplikasi.
- Test otomatis untuk struktur `report_data` dan section penting pada HTML.

## Asumsi

- Aplikasi utama yang dikembangkan adalah versi PySide6/Qt, bukan Dear PyGUI lama.
- Simulasi memakai hasil dari `engine.run_pf()` dan `state.last_results`.
- Laporan hanya boleh dibuat jika hasil power flow tersedia dan belum stale.
- Export rangkaian memakai canvas yang sudah terlihat di UI.
- PoC fokus pada laporan sekali klik, bukan editor laporan lengkap.
- Format final paling praktis untuk PoC adalah HTML rapi, lalu opsi PDF bisa ditambahkan setelahnya.

## Success Criteria

- User dapat menjalankan power flow, lalu klik satu tombol untuk export laporan.
- Laporan berisi diagram rangkaian, ringkasan jaringan, grafik ringkas, tabel bus, tabel beban/generator/shunt, tabel line/trafo, dan catatan status simulasi.
- Jika hasil belum ada atau sudah stale, aplikasi menolak export dengan pesan jelas.
- File laporan bisa dibuka tanpa aplikasi, minimal sebagai `.html`.
- Struktur data laporan mudah dites tanpa membuka GUI.

## Kondisi Saat Ini

Aplikasi sekarang sudah melewati tahap pondasi dan sudah memiliki implementasi PoC pertama. Komponen yang relevan saat ini:

- `qt_app.py` punya tombol `EXPORT PNG` untuk menyimpan gambar canvas.
- `qt_app.py` punya tombol `EKSPOR HASIL` untuk export hasil power flow ke CSV/snapshot.
- `qt_app.py` punya tombol `EXPORT REPORT` untuk membuat laporan HTML lengkap.
- `qt_model.export_results()` sudah menulis `node_results.csv`, `link_results.csv`, dan `project_snapshot.json`.
- `engine._collect_results()` sudah memetakan hasil pandapower kembali ke node/link UI.
- `qt_app._summary()` sudah membuat ringkasan total jaringan untuk panel analisis.
- `report_export.build_report_data()` sudah mengubah state aktif menjadi struktur data laporan yang netral terhadap GUI.

Gap utamanya sekarang bukan lagi "belum ada laporan", tetapi verifikasi otomatis dan opsi format lanjutan.

## Rekomendasi PoC

Status rekomendasi ini sudah **tereksekusi** sebagai baseline implementasi.

Bangun fitur **Export Report HTML** terlebih dahulu.

Alasannya:

- HTML mudah dibuat tanpa dependency berat.
- Bisa memuat gambar, tabel, warna status, dan layout laporan.
- Bisa dibuka langsung di browser.
- Lebih aman untuk PoC dibanding PDF, karena PDF sering butuh dependency tambahan.
- Setelah format HTML matang, PDF bisa dibuat dari HTML memakai tool tambahan jika dibutuhkan.

PDF tetap masuk roadmap, tetapi bukan target pertama.

## Arah Desain Visual

Desain laporan HTML harus terasa seperti **technical engineering report**, bukan halaman web biasa. Target tampilannya: bersih, presisi, mudah dipindai, dan cukup formal untuk laporan praktikum.

Prinsip desain:

- Gunakan layout dokumen dengan lebar baca stabil, misalnya `960px` sampai `1120px`.
- Gunakan background terang dan netral agar siap dicetak.
- Hindari efek dekoratif berlebihan seperti gradient besar, glassmorphism, atau kartu bertumpuk.
- Pakai aksen warna teknis seperlunya:
  - Hijau untuk normal.
  - Kuning untuk warning.
  - Merah untuk overload/error.
  - Biru gelap atau teal sebagai aksen identitas teknik.
- Pakai tabel yang padat tapi rapi, dengan garis halus dan alignment angka rata kanan.
- Angka penting harus langsung terlihat lewat summary tiles kecil, bukan hanya paragraf.
- Bagian diagram rangkaian harus menjadi visual utama laporan.

Konsep tampilan:

```text
Header laporan + metadata simulasi
Summary tiles: buses, load, loss, Vmin, max loading
Diagram rangkaian besar
Grafik ringkas: voltage profile, loading chart, loss breakdown
Tabel hasil detail
Catatan validasi dan snapshot metadata
```

Laporan harus enak dibaca di browser, tetapi juga tetap rapi saat dicetak atau disimpan sebagai PDF dari browser.

## Pendekatan yang Dipertimbangkan

### Opsi 1 - HTML Report

Membuat file `.html` berisi laporan lengkap.

Kelebihan:

- Dependency minimal.
- Cepat dibuat.
- Mudah dirapikan dengan CSS.
- Mudah dicek secara visual.

Kekurangan:

- Bukan format final yang paling formal untuk dikumpulkan.
- User perlu browser untuk membuka.

Status: sudah dipakai untuk PoC saat ini.

### Opsi 2 - PDF Langsung dari Qt

Menggambar laporan langsung ke PDF memakai Qt print/PDF APIs.

Kelebihan:

- Output langsung PDF.
- Cocok untuk laporan formal.

Kekurangan:

- Layout tabel lebih sulit.
- Lebih rawan hasil berantakan.
- Butuh lebih banyak effort untuk styling.

Rekomendasi: tetap menjadi tahap kedua setelah struktur HTML benar-benar stabil.

### Opsi 3 - DOCX Report

Membuat laporan Word `.docx`.

Kelebihan:

- Mudah diedit setelah export.
- Cocok untuk laporan praktikum.

Kekurangan:

- Butuh dependency tambahan seperti `python-docx`.
- Styling tabel dan gambar perlu diuji lagi.

Rekomendasi: tetap opsional jika laporan memang perlu diedit manual.

## Struktur Laporan

### 1. Header

Isi:

- Judul: `Laporan Hasil Simulasi Power Flow`
- Nama aplikasi: `PANDAPOWER VISUALIZATION`
- Waktu export
- Status simulasi: `Konvergen`

### 2. Ringkasan Jaringan

Isi:

- Jumlah bus
- Jumlah line
- Jumlah trafo
- Jumlah load
- Total beban aktif
- Total generator
- Daya dari external grid
- Rugi-rugi line
- Rugi-rugi trafo
- Tegangan minimum
- Loading maksimum

Bagian ini mengambil data dari ringkasan yang sekarang sudah dibuat di `qt_app._summary()`, tetapi sebaiknya nanti dipindah menjadi fungsi data murni agar bisa dipakai UI dan report.

Tampilan:

- Gunakan 6 sampai 8 summary tiles.
- Tile paling penting:
  - `Total Load`
  - `Grid Power`
  - `Line Loss`
  - `Trafo Loss`
  - `Minimum Voltage`
  - `Maximum Loading`
- Tile `Maximum Loading` diberi warna status sesuai ambang batas.

### 3. Diagram Rangkaian

Isi:

- Gambar canvas yang diexport otomatis.
- Caption singkat, misalnya `Gambar 1. Diagram rangkaian simulasi`.

Catatan desain:

- Jangan memasukkan border seleksi.
- Gunakan background konsisten.
- Gunakan margin agar node dan kabel tidak terpotong.

### 4. Tabel Komponen

Isi:

- Bus: label, tegangan nominal, slack, hasil `vm_pu`, `va_degree`.
- Load: label, `p_mw`, `q_mvar`, hasil konsumsi.
- Generator: label, `p_mw`, `q_mvar`.
- Trafo: label, kapasitas, tegangan HV/LV, loading, losses.
- Line: label, from, to, panjang, R, X, arus maksimum.

Tujuannya bukan menampilkan semua kolom pandapower, tetapi hanya kolom yang relevan untuk laporan mahasiswa.

### 5. Tabel Hasil Simulasi

Isi:

- Hasil bus: tegangan pu dan sudut.
- Hasil line: P, Q, rugi-rugi, loading.
- Hasil trafo: P/Q sisi HV-LV, rugi-rugi, loading.
- Hasil load/generator/shunt jika tersedia.

Tabel line/trafo perlu menonjolkan kondisi kritis:

- Loading < 80%: normal.
- Loading 80-100%: warning.
- Loading > 100%: overload.

### 6. Grafik Ringkas

Grafik perlu ada, tetapi tetap sederhana dan relevan. Untuk PoC, grafik sebaiknya dibuat tanpa dependency JavaScript eksternal supaya file HTML tetap mandiri.

Grafik yang direkomendasikan:

1. **Voltage Profile**
   - Bentuk: horizontal bar chart.
   - Data: `vm_pu` setiap bus.
   - Tujuan: melihat bus mana yang mengalami tegangan terendah.
   - Ambang visual:
     - Normal: 0.95 sampai 1.05 pu.
     - Warning: di luar rentang normal.

2. **Line and Transformer Loading**
   - Bentuk: horizontal bar chart.
   - Data: `loading_percent` dari line dan trafo.
   - Tujuan: melihat komponen paling terbebani.
   - Ambang visual:
     - < 80% normal.
     - 80-100% warning.
     - > 100% overload.

3. **Loss Breakdown**
   - Bentuk: simple comparison bar.
   - Data: total rugi-rugi line dan trafo.
   - Tujuan: membedakan sumber rugi-rugi jaringan.

4. **Power Balance**
   - Bentuk: compact metric comparison, bukan chart besar.
   - Data: total load, total generator, external grid power, total losses.
   - Tujuan: memberi gambaran neraca daya tanpa memenuhi laporan.

Implementasi PoC:

- Chart dibuat dengan HTML/CSS bar chart.
- Tidak perlu Chart.js pada tahap awal.
- Jika nanti butuh grafik lebih kompleks, Chart.js bisa dipertimbangkan sebagai tahap lanjutan.

### 7. Engineering Notes

Tambahkan bagian pendek berjudul `Engineering Notes`.

Isi dibuat dari aturan sederhana:

- Jika `V min < 0.95 pu`, tulis bahwa ada indikasi undervoltage.
- Jika `Max loading > 100%`, tulis bahwa ada komponen overload.
- Jika `Max loading` antara 80% dan 100%, tulis bahwa ada komponen mendekati batas.
- Jika semua normal, tulis bahwa simulasi berada dalam batas operasi dasar.

Bagian ini bukan AI-generated text. Cukup rule-based agar stabil, bisa dites, dan tidak menambah dependency.

### 8. Catatan Validasi

Isi:

- Model valid.
- Hasil power flow belum stale.
- Jika ada warning validasi, tampilkan di bagian catatan.

Untuk PoC, bagian ini bisa sederhana dulu.

## Data Flow

1. User menyusun rangkaian di canvas.
2. User menjalankan `Run Power Flow`.
3. `engine.run_pf()` membangun pandapower net dan mengisi `state.last_results`.
4. User klik `Export Report`.
5. Aplikasi memeriksa:
   - `state.last_results` tidak kosong.
   - `state.results_are_stale()` bernilai false.
   - canvas tidak kosong.
6. Aplikasi membuat snapshot diagram PNG sementara.
7. Aplikasi membangun data laporan dari state, hasil power flow, dan ringkasan net terakhir.
8. Aplikasi menulis file HTML ke folder export pilihan user.

## Struktur Data Report yang Dibutuhkan

Report builder sebaiknya menerima data terstruktur seperti ini:

```text
report_data
|-- metadata
|   |-- app_name
|   |-- exported_at
|   |-- simulation_status
|-- summary
|   |-- bus_count
|   |-- line_count
|   |-- trafo_count
|   |-- load_count
|   |-- total_load_mw
|   |-- grid_power_mw
|   |-- line_loss_kw
|   |-- trafo_loss_kw
|   |-- min_voltage_pu
|   |-- max_loading_percent
|-- diagram
|   |-- image_path
|   |-- caption
|-- charts
|   |-- voltage_profile
|   |-- loading_profile
|   |-- loss_breakdown
|-- tables
|   |-- buses
|   |-- components
|   |-- branches
|   |-- results
|-- notes
```

Dengan struktur ini, `report_export.py` tidak perlu tahu detail Qt. Ia hanya mengubah data menjadi HTML.

## Batasan PoC

PoC tidak perlu:

- Template laporan yang bisa diedit user.
- Export multi-format sekaligus.
- Cover page kompleks.
- Perhitungan tambahan di luar hasil pandapower yang sudah ada.
- Penyimpanan riwayat laporan.

PoC tetap perlu grafik, tetapi grafiknya sederhana dan berbasis HTML/CSS.

## Perubahan Kode yang Kemungkinan Dibutuhkan

Rencana file:

- `qt_app.py`
  - Tambah tombol `EXPORT REPORT`.
  - Tambah dialog save file.
  - Tambah helper render canvas ke image tanpa duplikasi berlebihan dari `export_canvas_image()`.

- `qt_model.py`
  - Tambah fungsi pengumpul data laporan yang tidak bergantung ke Qt.
  - Rapikan export hasil agar CSV dan report bisa memakai sumber data yang sama.

- `report_export.py`
  - File baru untuk membangun HTML report.
  - Input berupa data laporan terstruktur dan path gambar.
  - Output berupa file `.html`.
  - Memuat CSS internal untuk layout, summary tiles, tabel, dan chart bar.

- `tests/`
  - Test data report dari state sederhana.
  - Test HTML mengandung section penting.
  - Test export ditolak saat hasil stale atau kosong.

## Risiko

- `qt_app._summary()` sekarang bergantung pada object `net` yang hanya hidup saat `run_power_flow()`. Kalau laporan butuh ringkasan setelah beberapa waktu, data ringkasan perlu disimpan dalam state atau dihitung ulang dari `state.last_results`.
- Export PDF langsung bisa memperlambat PoC. Lebih baik validasi isi dan layout lewat HTML dulu.
- Jika canvas besar, gambar laporan bisa terlalu besar. PoC perlu batas lebar gambar di CSS.
- Data hasil tiap jenis komponen tidak seragam. Report builder harus punya formatter per jenis komponen.

## Tahapan Implementasi yang Disarankan

### Tahap 1 - Data Report

Status: selesai untuk PoC saat ini.

Target:

- Membuat struktur data laporan dari state dan hasil simulasi.
- Belum membuat HTML.

Verifikasi:

- Test headless bisa membuat data report dari template kecil.
- Data report memuat ringkasan, komponen, dan hasil.

### Tahap 2 - HTML Report

Status: selesai untuk PoC saat ini.

Target:

- Membuat `report_export.py`.
- Menghasilkan HTML dengan layout rapi.
- Membuat CSS report yang siap dibaca dan dicetak.
- Membuat chart sederhana untuk voltage, loading, dan losses.

Verifikasi:

- File HTML berisi header, ringkasan, diagram, dan tabel hasil.
- File HTML berisi grafik ringkas yang datanya sesuai hasil simulasi.
- HTML tetap terbaca tanpa asset eksternal.

### Tahap 3 - Integrasi UI

Status: selesai untuk PoC saat ini.

Target:

- Tambah tombol `EXPORT REPORT`.
- Dialog memilih lokasi file.
- Canvas otomatis dirender ke gambar report.

Verifikasi:

- Setelah power flow sukses, export menghasilkan HTML.
- Jika belum run power flow, tombol memberi error.
- Jika model berubah setelah run power flow, export ditolak.

### Tahap 4 - PDF Optional

Status: belum dikerjakan.

Target:

- Tambah export PDF jika HTML sudah stabil.

Pilihan:

- PDF dari Qt print engine.
- PDF dari HTML dengan dependency tambahan.
- DOCX jika kebutuhan laporan praktikum lebih kuat daripada PDF.

## Rekomendasi Final

Pertahankan **Export Report HTML** sebagai baseline yang sudah jalan, lalu prioritaskan verifikasi otomatis sebelum menambah format baru.

Nama fitur di UI:

- Tombol: `EXPORT REPORT`
- Dialog default: `simulation_report.html`
- Folder default: `exports/`

Urutan lanjut yang paling aman:

1. Tambah smoke test atau test headless untuk `build_report_data()` dan HTML output.
2. Rapikan coverage data jika ada jenis komponen/hasil yang belum terwakili.
3. Baru pertimbangkan PDF native atau DOCX bila kebutuhan distribusi memang nyata.

## Standar Kualitas Visual

Laporan dianggap cukup rapi jika memenuhi ini:

- Header terlihat seperti dokumen resmi, bukan halaman demo.
- Summary tiles bisa menjelaskan kondisi jaringan dalam 10 detik.
- Diagram rangkaian tampil besar dan tidak terpotong.
- Grafik loading langsung menunjukkan komponen paling kritis.
- Tabel hasil tetap terbaca meski banyak angka.
- Warna status konsisten di summary, chart, dan tabel.
- Saat browser print ke PDF, layout tidak pecah.
