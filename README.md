# Grid Simulator

Aplikasi simulator jaringan listrik berbasis Dear PyGui dan pandapower.

## Menjalankan Aplikasi

```powershell
python -m pip install -r requirements.txt
python demo.py
```

Saat dibuka, aplikasi mulai dari project kosong. Aksi utama tersedia di panel
kiri agar tidak bergantung pada menu atas. Gunakan `New Project` untuk
membersihkan workspace, atau `Load Template` bila ingin memakai template radial
mirip Four Load Branch:

- 1 external grid / slack bus
- 1 transformer 10/0.4 kV
- 4 line
- 4 load

Klik `Validate Network` untuk memeriksa kelengkapan rangkaian, lalu `Run Power
Flow` untuk menjalankan aliran daya.

## Interaksi Utama

- Tambahkan komponen dari panel kiri: `Tambah Bus`, `Tambah Generator`,
  `Tambah Transformer`, `Tambah Shunt`, dan `Tambah Load`. Menu atas tetap
  tersedia sebagai shortcut tambahan.
- Jalankan alur utama dari panel kiri bagian `Analisis`: `Validasi Jaringan`,
  `Jalankan Power Flow`, dan `Edit Saluran Dipilih`.
- Klik node untuk mengedit nama dan parameter komponennya. Panel kanan juga
  menampilkan spesifikasi detail, koneksi, dan hasil power-flow terakhir.
- Hubungkan bus ke bus untuk membuat line.
- Pilih link bus-to-bus di node editor, lalu klik `Edit Selected Line` untuk
  mengedit parameter saluran dan melihat hasil aliran dayanya.
- Hubungkan load, generator, dan shunt ke bus.
- Hubungkan transformer melalui pin HV dan LV.
- Gunakan `Save Project` dan `Load Project` untuk menyimpan atau memuat
  `grid_project.json` di folder aplikasi.
- Gunakan `Export Results` setelah simulasi untuk menulis `node_results.csv`,
  `link_results.csv`, dan `project_snapshot.json` ke folder `exports`.

## Test Headless

```powershell
python -m unittest discover -s tests -v
```

Test fokus pada konversi state aplikasi ke network pandapower dan validasi
kasus dasar tanpa membuka GUI.

## Build `.exe` dengan CMake

```powershell
cmake -S . -B cmake-build
cmake --build cmake-build
```

Output default:

```powershell
.\cmake-build\dist\GridSimulator.exe
```

Build ini memakai virtual environment lokal di `cmake-build\.venv` dan
PyInstaller. Secara default executable dibuat sebagai satu file `.exe` tanpa
console window. Jika ingin mode folder, jalankan konfigurasi seperti ini:

```powershell
cmake -S . -B cmake-build -DGRID_SIMULATOR_ONEFILE=OFF
cmake --build cmake-build
```
