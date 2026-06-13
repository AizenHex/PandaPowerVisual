# PANDAPOWER VISUALIZATION

PANDAPOWER VISUALIZATION is a desktop application for drawing an electrical
network and running a pandapower power-flow simulation from the visual model.

The current version uses PySide6 and `QGraphicsView` for the interactive canvas.
The main goal of this project is to make the relationship between buses, loads,
generators, transformers, external grids, and lines easier to inspect in a
student report or classroom demonstration.

## Main Files

```text
.
|-- demo.py              # Application entry point and smoke-test runner
|-- engine.py            # Model validation, pandapower network builder, power-flow runner
|-- state.py             # Shared application state for nodes, links, results, selection, and undo
|-- canvas_logic.py      # Math helpers for zooming, panning, bounds, and node placement
|-- qt_app.py            # Main window, toolbar, side panels, validation, import/export actions
|-- qt_canvas.py         # QGraphicsView canvas, visual nodes, links, dragging, zooming, and panning
|-- qt_model.py          # GUI-neutral adapter for node/link creation, save/load, and export logic
|-- report_export.py     # HTML report builder for simulation snapshots
|-- docs/report-template.html  # Base HTML/CSS template for exported reports
|-- CMakeLists.txt       # CMake entry point for building the packaged executable with PyInstaller
|-- requirements.txt     # Python dependencies required to run the application
```

## Installation

Install the required dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Running the Application

Start the desktop application:

```powershell
python demo.py
```

Run the smoke test without opening the window:

```powershell
python demo.py --smoke-power-flow
```

Tracked verification in this branch is centered on the headless smoke check
above.

## Building the Windows Executable

The repository ships a CMake-based packaging flow that creates a PyInstaller
build from `demo.py` and includes the HTML report template.

```powershell
cmake -S . -B cmake-build
cmake --build cmake-build --target grid-simulator-exe --config Release
```

## Exporting Simulation Reports

After a successful `Run Power Flow`, use the `EXPORT REPORT` action in the Qt
toolbar to generate a standalone HTML report. The exported report combines the
current diagram snapshot, network summary, result charts, and bus/branch tables
using the template in `docs/report-template.html`.

## Analysis Features

* **Power flow** (`pp.runpp`) with per-component results, loading colours on
  the canvas, and voltage-band colouring on every bus card
  (green 0.95-1.05 pu, yellow 0.90-1.10 pu, red outside).
* **Generator control modes** - each generator can run as a static PQ source
  (`pp.create_sgen`) or as a voltage-controlled PV machine (`pp.create_gen`)
  with an adjustable voltage setpoint.
* **Line standard types** - bus-to-bus lines can load R/X/C/Imax presets from
  the pandapower standard-type library (NAYY, NA2XS2Y, overhead lines, ...).
* **Pandapower JSON export** - `EKSPOR PANDAPOWER` writes the network with
  `pp.to_json` so it can be re-opened in plain pandapower scripts.

## User Interface

* **Tabbed ribbon** (AutoCAD style) - BERANDA, KOMPONEN, ANALISIS, EKSPOR,
  and TAMPILAN tabs group every action into labelled button clusters.
* **Flexible wires** (draw.io style) - wires have a wide hit area, highlight
  on hover, and any segment can be dragged directly. Dragging a segment next
  to a port automatically inserts a bend so the connection stays attached.
  Wires follow their components when nodes are moved.
* **Result panel** - stat cards (status, total loss, minimum voltage, maximum
  loading) above tabbed tables for branch results, bus voltages, and the
  validation log. Validation and errors switch to the log tab automatically.

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Ctrl+S` / `Ctrl+O` / `Ctrl+N` | Save / Open / New project |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom in / out / reset |
| `Del` / `Backspace` | Delete selection |

## Notes

The project name is written as **PANDAPOWER VISUALIZATION**. The application
still contains a few older Dear PyGUI source files, but the main maintained
interface is the PySide6/Qt implementation. A local `tests/` directory may
exist in developer worktrees for extra verification, but it is not part of the
tracked branch contents today.
