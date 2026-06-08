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

Run the automated test suite:

```powershell
python -m unittest discover -s tests -v
```

## Exporting Simulation Reports

After a successful `Run Power Flow`, use the `EXPORT REPORT` action in the Qt
toolbar to generate a standalone HTML report. The exported report combines the
current diagram snapshot, network summary, result charts, and bus/branch tables
using the template in `docs/report-template.html`.

## Notes

The project name is written as **PANDAPOWER VISUALIZATION**. The application
still contains a few older Dear PyGUI source files, but the main maintained
interface is the PySide6/Qt implementation.
