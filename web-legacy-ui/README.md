# Grid Simulator Legacy Web UI

Versi ini adalah implementasi HTML/CSS/JS yang dipisah dari prototype lama.
Desain node dan panel mengikuti UI legacy, tetapi top panel dibuat ulang menjadi
dua baris supaya menu, shortcut komponen, zoom, status, dan tombol simulasi tidak
berdesakan.

## Menjalankan

```powershell
python .\web-legacy-ui\server.py
```

Lalu buka:

```text
http://127.0.0.1:8765/
```

Server ini memakai `http.server` bawaan Python dan endpoint `/api/simulate`
langsung memanggil `engine.run_pf()` dari repo ini.

## Catatan Alur

- Panel kiri tetap menjadi alur utama untuk tambah komponen, validasi, run power
  flow, muat template, simpan project, dan ekspor hasil.
- Menu atas hanya shortcut tambahan seperti di desain legacy.
- Jika server tidak berjalan dan file HTML dibuka langsung, UI masih bisa tampil,
  tetapi tombol `Run Power Flow` akan jatuh ke mock simulation dari JavaScript.
