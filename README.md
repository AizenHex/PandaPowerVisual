# PANDAPOWER VISUALIZATION

Folder ini berisi kode utama aplikasi desktop PySide6/QGraphicsView untuk
visualisasi jaringan listrik dan simulasi power flow pandapower.

## File Utama

```text
legacy_dpg/
|-- demo.py          # Entry point aplikasi dan smoke test power flow
|-- engine.py        # Validasi model, konversi state ke pandapower, run power flow
|-- state.py         # State global node, link, hasil, selection, dan undo
|-- canvas_logic.py  # Helper matematis untuk zoom, pan, bounds, dan spawn node
|-- qt_app.py        # Window utama, toolbar, panel kiri/kanan, validasi, export
|-- qt_canvas.py     # Canvas QGraphicsView, node visual, link, drag port, zoom/pan
|-- qt_model.py      # Adapter GUI-neutral untuk membuat node, link, save/load project
|-- requirements.txt # Dependency untuk menjalankan aplikasi dari folder ini
```

## Menjalankan Dari Folder Ini

```powershell
python -m pip install -r requirements.txt
python demo.py
```

Smoke test power flow tanpa membuka window:

```powershell
python demo.py --smoke-power-flow
```

## Catatan

`README.md` dan `requirements.txt` juga ada di root repo. File di folder ini
dibuat supaya `legacy_dpg/` tetap bisa dibaca sebagai folder aplikasi utama
tanpa harus naik ke root project.
