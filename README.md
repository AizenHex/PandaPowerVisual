# Grid Simulator

Simulator jaringan listrik yang tersedia dalam tiga versi terpisah. Setiap versi berdiri mandiri di dalam foldernya masing-masing.

---

## Struktur Proyek

```
grid-simulator/
│
├── web-prototype/          # Versi 1: Desktop App (pywebview + SVG UI)
│   ├── index.html          # UI SVG AutoCAD-style
│   ├── app.js              # Logika frontend
│   ├── styles.css
│   ├── main.py             # Launcher desktop (pywebview)
│   ├── engine.py           # Backend simulator pandapower
│   ├── state.py            # State global simulator
│   └── tests/              # Unit test versi ini
│
├── web-legacy-ui/          # Versi 2: Legacy Web UI (HTTP server + HTML/CSS/JS)
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   ├── server.py           # Server HTTP lokal (localhost:8765)
│   ├── engine.py           # Backend simulator pandapower
│   ├── state.py            # State global simulator
│   └── tests/              # Unit test versi ini
│
├── legacy_dpg/             # Versi 3: Dear PyGui Desktop App
│   ├── app.py              # Aplikasi utama DearPyGui
│   ├── demo.py             # Entry point
│   ├── components.py
│   ├── engine.py
│   ├── state.py
│   ├── properties_panel.py
│   ├── visualization.py
│   └── tests/              # Unit test versi ini
│
└── v2-worktree/            # Git worktree untuk branch v2-improve
    └── ...                 # (sama seperti struktur root, branch terpisah)
```

---

## Menjalankan Masing-masing Versi

### Versi 1 — `web-prototype` (Desktop App pywebview + SVG)

```powershell
python -m pip install pywebview pandapower
python web-prototype/main.py
```

### Versi 2 — `web-legacy-ui` (Web Server Lokal)

```powershell
python -m pip install pandapower
python web-legacy-ui/server.py
# Buka browser ke http://127.0.0.1:8765/
```

### Versi 3 — `legacy_dpg` (Dear PyGui Desktop)

```powershell
python -m pip install dearpygui pandapower
python legacy_dpg/demo.py
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

### Test untuk `legacy_dpg`

```powershell
python -m unittest discover -s legacy_dpg/tests -v
```

---

## Tentang `v2-worktree`

Folder `v2-worktree/` adalah **Git Worktree** untuk branch `v2-improve`. Ini memungkinkan pengembangan branch tersebut di folder tersendiri tanpa perlu berpindah branch di direktori utama.

```powershell
# Untuk masuk dan bekerja di v2-improve:
cd v2-worktree
git status  # branch: v2-improve
```
