# PANDAPOWER VISUALIZATION

PANDAPOWER VISUALIZATION adalah simulator visual jaringan listrik berbasis
pandapower. Versi desktop aktif saat ini berada di `legacy_dpg/` dan
menggunakan PySide6/QGraphicsView untuk menggambar node, saluran, dan hasil
power flow.

---

## Struktur Proyek

```text
grid-simulator/
|
+-- web-prototype/          # Versi 1: Desktop app pywebview + SVG UI
|   +-- index.html          # UI SVG AutoCAD-style
|   +-- app.js              # Logika frontend
|   +-- styles.css
|   +-- main.py             # Launcher desktop pywebview
|   +-- engine.py           # Backend simulator pandapower
|   +-- state.py            # State global simulator
|   +-- tests/              # Unit test versi ini
|
+-- web-legacy-ui/          # Versi 2: Web lokal HTML/CSS/JS
|   +-- index.html
|   +-- app.js
|   +-- styles.css
|   +-- server.py           # Server HTTP lokal di localhost:8765
|   +-- engine.py           # Backend simulator pandapower
|   +-- state.py            # State global simulator
|   +-- tests/              # Unit test versi ini
|
+-- legacy_dpg/             # Versi 3 aktif: PySide6/QGraphicsView desktop
|   +-- demo.py             # Entry point aplikasi Qt
|   +-- qt_app.py           # Shell aplikasi, toolbar, panel, action
|   +-- qt_canvas.py        # Canvas QGraphicsView, node, link, zoom/pan
|   +-- qt_model.py         # Adapter state/model GUI-neutral
|   +-- canvas_logic.py     # Helper posisi, zoom, dan anti-overlap
|   +-- engine.py           # Konversi state ke pandapower dan run power flow
|   +-- state.py            # State global aplikasi
|   +-- tests/              # Test aktif untuk PySide/model/canvas
|   +-- .ARSIP/             # Arsip shell Dear PyGui lama
|
+-- v2-worktree/            # Git worktree untuk branch v2-improve
    +-- ...
```

---

## Menjalankan Aplikasi

### Versi 1: `web-prototype`

```powershell
python -m pip install pywebview pandapower
python web-prototype/main.py
```

### Versi 2: `web-legacy-ui`

```powershell
python -m pip install pandapower
python web-legacy-ui/server.py
# Buka browser ke http://127.0.0.1:8765/
```

### Versi 3 aktif: `legacy_dpg` PySide6

```powershell
python -m pip install -r requirements.txt
python legacy_dpg/demo.py
```

Smoke test power flow tanpa membuka window:

```powershell
python legacy_dpg/demo.py --smoke-power-flow
```

---

## Menjalankan Unit Test

### Test untuk `web-prototype`

```powershell
python -m unittest discover -s web-prototype/tests -v
```

### Test untuk `web-legacy-ui`

```powershell
python -m unittest discover -s web-legacy-ui/tests -v
```

### Test aktif untuk `legacy_dpg`

```powershell
cd legacy_dpg
$env:QT_QPA_PLATFORM="offscreen"
python -m unittest tests.test_canvas_logic tests.test_qt_model tests.test_qt_canvas -v
```

Catatan: `tests/test_ui_smoke.py` masih mengacu ke shell Dear PyGui lama, jadi
tidak dipakai untuk verifikasi jalur PySide6 aktif.

---

## Tentang `v2-worktree`

Folder `v2-worktree/` adalah Git worktree untuk branch `v2-improve`. Ini
memungkinkan pengembangan branch tersebut di folder tersendiri tanpa perlu
berpindah branch di direktori utama.

```powershell
cd v2-worktree
git status
```
