"""PySide6 / QGraphicsView Grid Simulator shell.

UI features
-----------
* **Tabbed ribbon (gaya AutoCAD)** – tab BERANDA/KOMPONEN/ANALISIS/EKSPOR/
  TAMPILAN berisi grup tombol berlabel dengan aksen warna per kategori.
* **Properties panel** – Unity-style collapsible/accordion sections with
  clear visual separation, clickable ▶/▼ headers.
* **Result panel** – kartu statistik + tab tabel saluran/trafo, tegangan bus,
  dan log analisis.
* **Connection workflow** – drag from port is handled by GridView in
  qt_canvas.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QPropertyAnimation, QEasingCurve, QEvent, QTimer
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

import engine
import qt_model
import report_export
import state
from qt_canvas import GridScene, GridView

# qt_app mengikat UI PySide ke model: engine tetap headless, qt_model menjaga state.
# GridScene/GridView diimpor dari qt_canvas agar logika mouse tidak bercampur di MainWindow.


# ═══════════════════════════════════════════════════════════════════════════
#  Design tokens
# ═══════════════════════════════════════════════════════════════════════════

RIGHT_WIDTH = 310

# Palette
BG_0       = "#111111"   # deepest background
BG_1       = "#171717"   # panel / dock bg
BG_2       = "#1e1e1e"   # card / header bg
BG_3       = "#252525"   # button / input bg
BORDER_0   = "#222222"
BORDER_1   = "#2e2e2e"
BORDER_2   = "#3a3a3a"
TEXT_0     = "#e0e0e0"
TEXT_1     = "#bbbbbb"
TEXT_2     = "#808080"
TEXT_3     = "#555555"

ACCENT     = "#ffd24a"    # gold
ACCENT_DIM = "#9e8530"
BLUE       = "#5ba0d0"
GREEN      = "#4ac078"
RED        = "#e05050"
ORANGE     = "#e09050"
PURPLE     = "#a070e0"
WARN       = "#f0c83c"

# Component brand colours (match node card palette)
COMP_COLORS = {
    "bus":   "#64beff",
    "gen":   "#50dc78",
    "trafo": "#e68c46",
    "shunt": "#b464ff",
    "load":  "#e06464",
}

FIELD_META = {
    "label":         ("Nama",                     "",     "nama yang tampil di node"),
    "vn_kv":         ("Tegangan nominal",          "kV",   "level tegangan bus"),
    "is_slack":      ("Slack / ext grid",           "",     "satu bus acuan power flow"),
    "vm_pu":         ("Setpoint tegangan",          "pu",   "biasanya 1.0"),
    "va_degree":     ("Sudut tegangan",             "°",    "biasanya 0°"),
    "p_mw":          ("Daya aktif P",               "MW",   ""),
    "q_mvar":        ("Daya reaktif Q",             "MVAr", ""),
    "sn_mva":        ("Kapasitas",                  "MVA",  "rating daya semu"),
    "vn_hv_kv":      ("Tegangan HV",                "kV",   "sisi tegangan tinggi"),
    "vn_lv_kv":      ("Tegangan LV",                "kV",   "sisi tegangan rendah"),
    "vk_percent":    ("Impedansi Vk",               "%",    "impedansi hubung singkat"),
    "vkr_percent":   ("Komponen resistif Vkr",      "%",    "≤ Vk"),
    "pfe_kw":        ("Rugi besi",                  "kW",   "boleh 0"),
    "i0_percent":    ("Arus tanpa beban",           "%",    "boleh 0"),
    "length_km":     ("Panjang saluran",            "km",   ""),
    "r_ohm_per_km":  ("Resistansi R",               "Ω/km", ""),
    "x_ohm_per_km":  ("Reaktansi X",                "Ω/km", ""),
    "c_nf_per_km":   ("Kapasitansi C",              "nF/km",""),
    "max_i_ka":      ("Arus maksimum",              "kA",   "batas loading"),
}

RESULT_LABELS = {
    "vm_pu":          ("Tegangan",     "pu"),
    "va_degree":      ("Sudut",        "°"),
    "p_mw":           ("P",            "MW"),
    "q_mvar":         ("Q",            "MVAr"),
    "p_from_mw":      ("P →",         "MW"),
    "q_from_mvar":    ("Q →",         "MVAr"),
    "p_to_mw":        ("P ←",         "MW"),
    "q_to_mvar":      ("Q ←",         "MVAr"),
    "p_hv_mw":        ("P HV",        "MW"),
    "q_hv_mvar":      ("Q HV",        "MVAr"),
    "p_lv_mw":        ("P LV",        "MW"),
    "q_lv_mvar":      ("Q LV",        "MVAr"),
    "pl_mw":          ("Rugi P",      "MW"),
    "ql_mvar":        ("Rugi Q",      "MVAr"),
    "i_from_ka":      ("I →",         "kA"),
    "i_to_ka":        ("I ←",         "kA"),
    "i_hv_ka":        ("I HV",        "kA"),
    "i_lv_ka":        ("I LV",        "kA"),
    "loading_percent":("Loading",     "%"),
}

KIND_LABELS = {
    "bus": "Bus", "gen": "Generator", "trafo": "Transformer",
    "shunt": "Shunt", "load": "Beban", "line": "Saluran",
}

# ═══════════════════════════════════════════════════════════════════════════
#  Dark palette + global stylesheet
# ═══════════════════════════════════════════════════════════════════════════

def apply_dark_palette(app: QApplication) -> None:
    font = QFont("Consolas", 10)
    font.setFamilies(["Consolas", "Cascadia Mono", "Courier New", "monospace"])
    app.setFont(font)

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(BG_0))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(TEXT_0))
    pal.setColor(QPalette.ColorRole.Base,            QColor(BG_1))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(BG_2))
    pal.setColor(QPalette.ColorRole.ToolTipBase,     QColor(BG_2))
    pal.setColor(QPalette.ColorRole.ToolTipText,     QColor(TEXT_0))
    pal.setColor(QPalette.ColorRole.Text,            QColor(TEXT_0))
    pal.setColor(QPalette.ColorRole.Button,          QColor(BG_3))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(TEXT_0))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor(55, 85, 115))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)

    app.setStyleSheet(f"""
        /* ─── Base ───────────────────────────────────────────────────── */
        QMainWindow, QWidget {{
            background: {BG_0};
            color: {TEXT_0};
            font-family: Consolas, "Cascadia Mono", monospace;
            font-size: 10pt;
        }}

        /* ─── Toolbar (ribbon) ───────────────────────────────────────── */
        QToolBar {{
            background: {BG_1};
            border: none;
            border-bottom: 2px solid {BORDER_2};
            spacing: 0; padding: 0;
        }}

        /* ─── Buttons ────────────────────────────────────────────────── */
        QPushButton {{
            background: {BG_3};
            border: 1px solid {BORDER_2};
            border-radius: 3px;
            padding: 5px 12px;
            min-height: 20px;
            color: {TEXT_1};
        }}
        QPushButton:hover {{ background: #2c2c2c; border-color: #505050; }}
        QPushButton:pressed {{ background: #1e3a50; border-color: {BLUE}; }}

        /* danger */
        QPushButton[danger="true"] {{
            background: #2a1515;
            border: 1px solid {RED};
            color: {RED};
            font-weight: 600;
        }}
        QPushButton[danger="true"]:hover {{ background: #3a1a1a; }}

        /* ─── Ribbon button ──────────────────────────────────────────── */
        QPushButton[ribbonBtn="true"] {{
            background: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 5px 10px;
            min-height: 24px;
            color: {TEXT_1};
            font-size: 10pt;
        }}
        QPushButton[ribbonBtn="true"]:hover {{
            background: #2a2a2a;
            border-color: {BORDER_2};
            color: #ffffff;
        }}
        QPushButton[ribbonBtn="true"]:pressed {{
            background: #1e3555;
            border-color: {BLUE};
        }}
        QPushButton[ribbonBtn="true"]:checked {{
            background: #1e3555;
            border: 1px solid {BLUE};
            color: {BLUE};
        }}
        QPushButton[ribbonBtn="true"]:checked:hover {{
            background: #25426b;
            border-color: #79bce8;
            color: #ffffff;
        }}

        /* ─── Inputs ─────────────────────────────────────────────────── */
        QLineEdit, QDoubleSpinBox, QTextEdit {{
            background: {BG_0};
            border: 1px solid {BORDER_2};
            border-radius: 3px;
            padding: 4px 8px;
            selection-background-color: #2d5070;
            color: {TEXT_0};
        }}
        QLineEdit:focus, QDoubleSpinBox:focus {{
            border-color: {BLUE};
        }}
        QComboBox {{
            background: {BG_0};
            border: 1px solid {BORDER_2};
            border-radius: 3px;
            padding: 4px 8px;
            color: {TEXT_0};
        }}
        QComboBox:focus {{ border-color: {BLUE}; }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QComboBox QAbstractItemView {{
            background: {BG_2};
            border: 1px solid {BORDER_2};
            selection-background-color: #2d5070;
            color: {TEXT_0};
        }}
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            width: 16px; border: none; background: {BG_3};
        }}

        /* ─── Checkbox ───────────────────────────────────────────────── */
        QCheckBox {{ spacing: 8px; color: {TEXT_0}; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px;
            border: 1px solid {BORDER_2};
            background: {BG_0};
            border-radius: 3px;
        }}
        QCheckBox::indicator:checked {{
            background: {BLUE};
            border-color: {BLUE};
        }}

        /* ─── Dock ───────────────────────────────────────────────────── */
        QDockWidget {{
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
            color: {ACCENT};
            font-weight: 600;
        }}
        QDockWidget::title {{
            background: {BG_1};
            padding: 6px 10px;
            border-bottom: 1px solid {BORDER_0};
            text-align: left;
        }}

        /* ─── Scroll ─────────────────────────────────────────────────── */
        QScrollArea {{ border: none; background: {BG_1}; }}
        QScrollBar:vertical {{
            background: {BG_0}; width: 7px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: #333; min-height: 24px; border-radius: 3px;
        }}
        QScrollBar::handle:vertical:hover {{ background: #484848; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

        /* ─── Table ──────────────────────────────────────────────────── */
        QTableWidget {{
            gridline-color: {BORDER_0};
            background: {BG_0};
            alternate-background-color: {BG_1};
            selection-background-color: #2d5070;
        }}
        QHeaderView::section {{
            background: {BG_2};
            border: 1px solid {BORDER_0};
            padding: 4px;
            color: {TEXT_2};
        }}

        QSplitter::handle {{ background: {BORDER_0}; height: 2px; }}

        /* ─── Ribbon tabs (gaya AutoCAD) ─────────────────────────────── */
        QPushButton[ribbonTab="true"] {{
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            border-radius: 0;
            padding: 4px 16px;
            color: {TEXT_2};
            font-size: 9pt;
            font-weight: 600;
            letter-spacing: 1px;
        }}
        QPushButton[ribbonTab="true"]:hover {{
            color: {TEXT_0};
            background: #1c1c1c;
        }}
        QPushButton[ribbonTab="true"]:checked {{
            color: {ACCENT};
            border-bottom: 2px solid {ACCENT};
            background: {BG_2};
        }}

        /* ─── Bottom result tabs ─────────────────────────────────────── */
        QTabWidget::pane {{
            border: 1px solid {BORDER_0};
            background: {BG_0};
        }}
        QTabBar::tab {{
            background: {BG_1};
            color: {TEXT_2};
            border: 1px solid {BORDER_0};
            border-bottom: none;
            padding: 5px 14px;
            font-size: 9pt;
            letter-spacing: 0.5px;
        }}
        QTabBar::tab:hover {{ color: {TEXT_0}; }}
        QTabBar::tab:selected {{
            background: {BG_0};
            color: {ACCENT};
            border-top: 2px solid {ACCENT};
        }}

        /* ─── QMenu ──────────────────────────────────────────────────── */
        QMenu {{
            background-color: {BG_2};
            border: 1px solid {BORDER_2};
            border-radius: 4px;
            padding: 4px 0px;
        }}
        QMenu::item {{
            padding: 6px 28px 6px 28px;
            background-color: transparent;
            color: {TEXT_1};
        }}
        QMenu::item:selected {{
            background-color: #2d5070;
            color: #ffffff;
        }}
        QMenu::indicator {{
            width: 10px;
            height: 10px;
            border-radius: 2px;
            border: 1px solid {BORDER_2};
            background-color: {BG_0};
            left: 8px;
        }}
        QMenu::indicator:checked {{
            background-color: {BLUE};
            border-color: {BLUE};
        }}
        QPushButton::menu-indicator {{
            image: none;
        }}
    """)


# ═══════════════════════════════════════════════════════════════════════════
#  Widget helpers
# ═══════════════════════════════════════════════════════════════════════════

def _section_header_lbl(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f"""
        color: {ACCENT};
        font-weight: 700;
        font-size: 9pt;
        letter-spacing: 1.5px;
    """)
    return lbl


def _muted(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {TEXT_3}; font-size: 9pt; padding: 2px 0;")
    return lbl


def _guidance(text: str, ok: bool = False) -> QLabel:
    col = GREEN if ok else WARN
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {col}; font-size: 9pt; padding: 2px 0;")
    return lbl


def _field_lbl(key: str) -> QLabel:
    name, unit, _ = FIELD_META.get(key, (key, "", ""))
    t = f"{name} ({unit})" if unit else name
    lbl = QLabel(t)
    lbl.setStyleSheet(f"color: {TEXT_2}; font-size: 9pt;")
    return lbl


def _h_sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {BORDER_0}; border: none;")
    return f


def _v_sep_ribbon() -> QFrame:
    """Ribbon group separator with 3D etched appearance."""
    f = QFrame()
    f.setFrameShape(QFrame.Shape.VLine)
    f.setFixedWidth(2)
    f.setStyleSheet(f"""
        background: transparent;
        border-left: 1px solid #141414;
        border-right: 1px solid #2a2a2a;
        max-width: 2px;
    """)
    f.setFixedHeight(40)
    return f


def _fmt(value) -> str:
    if isinstance(value, bool):
        return "Ya" if value else "Tidak"
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:.2f}"
        if abs(value) >= 1:
            return f"{value:.4f}"
        return f"{value:.6f}"
    return str(value)


# ═══════════════════════════════════════════════════════════════════════════
#  Toast Notification — Floating pop-up
# ═══════════════════════════════════════════════════════════════════════════

class Toast(QFrame):
    def __init__(self, parent: QWidget, text: str, level: str = "success"):
        super().__init__(parent)
        self.level = level
        
        # Level colors
        if level == "error":
            border_color = RED
            bg_color = "#2a1515"
            text_color = RED
        elif level == "warn":
            border_color = WARN
            bg_color = "#252010"
            text_color = WARN
        else:
            border_color = GREEN
            bg_color = "#152515"
            text_color = GREEN
            
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
            QLabel {{
                border: none;
                background: transparent;
                color: {text_color};
                font-family: Consolas, "Cascadia Mono", monospace;
                font-size: 10pt;
                font-weight: bold;
            }}
        """)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        
        self.adjustSize()
        self.update_position()
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)
        
        self.anim_in = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_in.setDuration(250)
        self.anim_in.setStartValue(0.0)
        self.anim_in.setEndValue(1.0)
        
        self.anim_out = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim_out.setDuration(400)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)
        self.anim_out.finished.connect(self.close_and_destroy)
        
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fade_out)
        
        self.show()
        self.anim_in.start()
        self.timer.start(3000)
        
        if parent:
            parent.installEventFilter(self)

    def update_position(self):
        if not self.parentWidget():
            return
        pw = self.parentWidget().width()
        w = self.width()
        x = (pw - w) // 2
        y = 20
        self.move(x, y)

    def eventFilter(self, obj, event):
        if obj == self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.update_position()
        return super().eventFilter(obj, event)

    def fade_out(self):
        self.anim_out.start()

    def close_and_destroy(self):
        self.close()
        self.deleteLater()


# ═══════════════════════════════════════════════════════════════════════════
#  CollapsibleSection — Unity Inspector style
# ═══════════════════════════════════════════════════════════════════════════

class CollapsibleSection(QWidget):
    """A clickable header that toggles visibility of its content area.

    Visual design:
      ┌──────────────────────────────────┐
      │ ▼  SECTION TITLE                 │  ← dark header, accent left border
      ├──────────────────────────────────┤
      │  (content widgets)               │  ← BG_1 background
      └──────────────────────────────────┘
    """

    def __init__(self, title: str, accent_color: str = ACCENT,
                 collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._collapsed = collapsed
        self._accent = accent_color
        self._title_text = title.upper()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header button ─────────────────────────────────────────────
        self._header = QPushButton()
        self._header.setFixedHeight(28)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_header_text()
        self._header.setStyleSheet(f"""
            QPushButton {{
                background: {BG_2};
                border: none;
                border-left: 3px solid {accent_color};
                border-bottom: 1px solid {BORDER_0};
                text-align: left;
                padding-left: 10px;
                color: {accent_color};
                font-weight: 700;
                font-size: 9pt;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background: #242424;
            }}
        """)
        self._header.clicked.connect(self.toggle)
        root.addWidget(self._header)

        # ── Content area ──────────────────────────────────────────────
        self._content = QWidget()
        self._content.setStyleSheet(f"background: {BG_1};")
        self._inner = QVBoxLayout(self._content)
        self._inner.setContentsMargins(12, 8, 12, 10)
        self._inner.setSpacing(5)
        root.addWidget(self._content)

        if collapsed:
            self._content.setVisible(False)

    @property
    def inner(self) -> QVBoxLayout:
        return self._inner

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._update_header_text()

    def _update_header_text(self) -> None:
        arrow = "▶" if self._collapsed else "▼"
        self._header.setText(f" {arrow}   {self._title_text}")


# ═══════════════════════════════════════════════════════════════════════════
#  RibbonGroup — toolbar button cluster with label
# ═══════════════════════════════════════════════════════════════════════════

class RibbonGroup(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 3, 6, 2)
        outer.setSpacing(1)

        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(3)
        outer.addLayout(self._row)

        lbl = QLabel(label.upper())
        lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lbl.setStyleSheet(f"color: {TEXT_3}; font-size: 7pt; letter-spacing: 1.5px;")
        outer.addWidget(lbl)

    def add_btn(self, text: str, callback, *, color: str = "", bold: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setProperty("ribbonBtn", True)
        if color:
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {color}; font-weight: {'700' if bold else '500'};
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 5px 10px;
                    min-height: 24px;
                }}
                QPushButton:hover {{
                    background: {color}18;
                    border-color: {color}40;
                    color: {color};
                }}
                QPushButton:pressed {{
                    background: {color}30;
                }}
            """)
        else:
            btn.setProperty("ribbonBtn", True)
        btn.clicked.connect(callback)
        self._row.addWidget(btn)
        return btn

    def add_widget(self, w: QWidget):
        self._row.addWidget(w)


# ═══════════════════════════════════════════════════════════════════════════
#  StatChip — kartu ringkasan kecil di panel hasil
# ═══════════════════════════════════════════════════════════════════════════

class StatChip(QFrame):
    """Kartu kecil berisi satu angka penting (status, rugi, V min, loading)."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {BG_2};
                border: 1px solid {BORDER_1};
                border-radius: 4px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        lo = QVBoxLayout(self)
        lo.setContentsMargins(12, 6, 12, 6)
        lo.setSpacing(1)
        self._value = QLabel("—")
        self._value.setStyleSheet(
            f"color: {TEXT_0}; font-size: 11pt; font-weight: 700;")
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(
            f"color: {TEXT_3}; font-size: 7pt; letter-spacing: 1.2px;")
        lo.addWidget(self._value)
        lo.addWidget(title_lbl)

    def set_value(self, text: str, color: str = TEXT_0) -> None:
        self._value.setText(text)
        self._value.setStyleSheet(
            f"color: {color}; font-size: 11pt; font-weight: 700;")

    def reset(self) -> None:
        self.set_value("—", TEXT_3)


ABOUT_COMPONENTS = {
    "bus": {
        "title": "Tentang Bus",
        "description": "Busbar (Bus) adalah titik koneksi fisik di mana berbagai komponen (generator, beban, trafo, saluran) terhubung secara paralel.",
        "fields": [
            ("Nama", "Nama unik untuk mengidentifikasi bus ini."),
            ("Tegangan nominal", "Tegangan operasional dasar sistem (dalam kV). Nilai tipikal: 150 kV atau 500 kV untuk transmisi, 20 kV untuk distribusi, dan 0.4 kV (380V) untuk tegangan rendah konsumen."),
            ("Slack / external grid", "Menentukan bus ini sebagai referensi utama tegangan dan sudut fasa (V-theta) untuk seluruh jaringan. Harus ada tepat satu slack bus dalam jaringan."),
            ("Setpoint tegangan", "Target tegangan acuan pada slack bus dalam satuan per-unit (pu). Nilai normal: 0.95 s.d. 1.05 pu."),
            ("Sudut tegangan", "Sudut fasa acuan tegangan pada slack bus, biasanya diatur ke 0.0 derajat."),
        ]
    },
    "gen": {
        "title": "Tentang Generator",
        "description": "Generator mensuplai daya aktif (P) dan daya reaktif (Q) ke dalam sistem kelistrikan.",
        "fields": [
            ("Nama", "Nama unik untuk mengidentifikasi generator ini."),
            ("Daya aktif P", "Daya nyata yang diproduksi oleh generator (dalam MW). Nilai positif menyuplai daya ke jaringan."),
            ("Daya reaktif Q", "Daya pendukung tegangan yang dihasilkan/diserap oleh generator (dalam MVAr). Nilai positif untuk menyuplai Q, negatif untuk menyerap Q. Hanya dipakai pada mode PQ."),
            ("Kontrol tegangan (PV)", "Mode PV membuat generator menjaga tegangan bus pada setpoint (pu); Q dihitung otomatis oleh power flow. Mode PQ (default) memakai P dan Q tetap."),
            ("Setpoint tegangan", "Target tegangan bus saat mode PV aktif, dalam per-unit. Nilai normal: 0.95 s.d. 1.05 pu."),
            ("Kapasitas", "Rating daya semu generator (MVA), dipakai juga oleh analisis hubung singkat."),
        ]
    },
    "trafo": {
        "title": "Tentang Trafo",
        "description": "Transformator (Trafo) digunakan untuk menaikkan atau menurunkan tegangan AC antara dua level tegangan nominal yang berbeda.",
        "fields": [
            ("Nama", "Nama unik untuk mengidentifikasi transformator ini."),
            ("Kapasitas", "Kapasitas daya semu maksimum trafo (dalam MVA)."),
            ("Tegangan HV", "Tegangan nominal pada sisi tegangan tinggi (High Voltage) dalam kV. Harus sesuai dengan tegangan nominal bus HV."),
            ("Tegangan LV", "Tegangan nominal pada sisi tegangan rendah (Low Voltage) dalam kV. Harus sesuai dengan tegangan nominal bus LV."),
            ("Impedansi Vk", "Tegangan hubung singkat dalam persen (%). Menunjukkan reaktansi bocor trafo. Nilai tipikal: 4% s.d. 12%."),
            ("Komponen resistif Vkr", "Rugi-rugi tembaga akibat resistansi lilitan dalam persen (%). Nilai harus selalu lebih kecil atau sama dengan Vk."),
            ("Rugi besi", "Rugi daya aktif pada inti trafo saat tanpa beban (dalam kW). Nilai tipikal: sangat kecil atau 0 untuk ideal."),
            ("Arus tanpa beban", "Arus magnetisasi trafo dalam persen (%) terhadap arus nominal. Nilai tipikal: 0.1% s.d. 1.0%."),
        ]
    },
    "load": {
        "title": "Tentang Beban",
        "description": "Beban (Load) mewakili konsumsi daya aktif dan reaktif oleh konsumen listrik (industri, rumah tangga, dll.).",
        "fields": [
            ("Nama", "Nama unik untuk mengidentifikasi beban ini."),
            ("Daya aktif P", "Konsumsi daya nyata oleh beban (dalam MW). Nilai positif menyerap daya aktif dari sistem."),
            ("Daya reaktif Q", "Konsumsi daya reaktif oleh beban (dalam MVAr). Beban induktif (seperti motor listrik) menyerap Q positif."),
        ]
    },
    "shunt": {
        "title": "Tentang Shunt",
        "description": "Kompensator Shunt (misal kapasitor bank atau reaktor) digunakan untuk mengontrol profil tegangan dan mengompensasi daya reaktif.",
        "fields": [
            ("Nama", "Nama unik untuk mengidentifikasi shunt ini."),
            ("Daya aktif P", "Rugi daya aktif pada shunt (dalam MW). Biasanya bernilai 0 (ideal)."),
            ("Daya reaktif Q", "Daya reaktif shunt (dalam MVAr). Nilai negatif berarti shunt bertindak sebagai kapasitor (menyuplai Q untuk menaikkan tegangan). Nilai positif bertindak sebagai reaktor (menyerap Q untuk menurunkan tegangan)."),
        ]
    },
    "line": {
        "title": "Tentang Saluran",
        "description": "Saluran (Line) adalah kabel transmisi/distribusi listrik yang menghubungkan dua bus pada level tegangan yang sama.",
        "fields": [
            ("Nama", "Nama unik untuk mengidentifikasi saluran ini."),
            ("Panjang saluran", "Panjang fisik saluran kabel/kawat udara dalam kilometer (km)."),
            ("Resistansi R", "Resistansi kawat per kilometer (dalam Ω/km). Menyebabkan rugi-rugi panas (I²R)."),
            ("Reaktansi X", "Reaktansi induktif kawat per kilometer (dalam Ω/km). Bergantung pada konfigurasi geometri kawat."),
            ("Kapasitansi C", "Kapasitansi pengisian saluran terhadap tanah per kilometer (dalam nF/km). Memproduksi daya reaktif."),
            ("Arus maksimum", "Batas hantar arus kontinu maksimum saluran (dalam kA) sebelum kabel mengalami overheating."),
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════
#  PropertiesPanel
# ═══════════════════════════════════════════════════════════════════════════

class PropertiesPanel(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main = main_window
        self.editing_field = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.show_empty()

    # ── layout plumbing ───────────────────────────────────────────────

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add(self, w: QWidget) -> None:
        self._layout.addWidget(w)

    def _gap(self, px: int = 3) -> None:
        g = QWidget()
        g.setFixedHeight(px)
        g.setStyleSheet(f"background: {BG_0};")
        self._add(g)

    # ── section factory ───────────────────────────────────────────────

    def _section(self, title: str, accent: str = ACCENT,
                 collapsed: bool = False) -> CollapsibleSection:
        sec = CollapsibleSection(title, accent_color=accent, collapsed=collapsed)
        self._add(sec)
        self._gap(2)
        return sec

    # ── field helpers ─────────────────────────────────────────────────

    def _add_field(self, layout: QVBoxLayout, key: str, widget: QWidget) -> None:
        layout.addWidget(_field_lbl(key))
        if isinstance(widget, (QLineEdit, QDoubleSpinBox)):
            # Flag editing mencegah Backspace/Delete menghapus node saat user mengetik nilai.
            widget.setMinimumWidth(0)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            widget.focusInEvent  = self._wrap_fi(widget.focusInEvent)
            widget.focusOutEvent = self._wrap_fo(widget.focusOutEvent)
        layout.addWidget(widget)

    def _wrap_fi(self, orig):
        def h(ev):
            self.editing_field = True; return orig(ev)
        return h

    def _wrap_fo(self, orig):
        def h(ev):
            self.editing_field = False; return orig(ev)
        return h

    @staticmethod
    def _spin(value: float = 0.0) -> QDoubleSpinBox:
        s = QDoubleSpinBox()
        s.setRange(-1_000_000, 1_000_000)
        s.setDecimals(6)
        s.setValue(value)
        return s

    # ── spec grid ─────────────────────────────────────────────────────

    def _spec_grid(self, layout: QVBoxLayout,
                   rows: list[tuple[str, object, str]]) -> None:
        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 0, 4)
        grid.setVerticalSpacing(4)
        grid.setHorizontalSpacing(12)
        grid.setColumnStretch(1, 1)
        for i, (label, val, unit) in enumerate(rows):
            kl = QLabel(label)
            kl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            kl.setStyleSheet(f"color: {TEXT_3}; font-size: 9pt;")
            vt = _fmt(val) if not isinstance(val, str) else val
            suf = f"  {unit}" if unit else ""
            vl = QLabel(f"{vt}{suf}")
            vl.setWordWrap(True)
            vl.setStyleSheet(f"color: {TEXT_0}; font-size: 9pt;")
            grid.addWidget(kl, i, 0)
            grid.addWidget(vl, i, 1)
        layout.addLayout(grid)

    # ── connection badges ─────────────────────────────────────────────

    def _conn_badge(self, layout: QVBoxLayout, text: str) -> None:
        lbl = QLabel(f"  {text}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"""
            background: #152535;
            border: 1px solid #1e3a55;
            border-left: 3px solid {BLUE};
            border-radius: 3px;
            padding: 4px 8px;
            color: {BLUE};
            font-size: 9pt;
        """)
        layout.addWidget(lbl)

    def _add_about_section(self, kind: str) -> None:
        info = ABOUT_COMPONENTS.get(kind)
        if not info:
            return
        
        sec = self._section("Tentang Komponen", accent=TEXT_1, collapsed=True)
        
        desc_lbl = QLabel(info["description"])
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {TEXT_1}; font-size: 9pt; padding-bottom: 6px;")
        sec.inner.addWidget(desc_lbl)
        
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"background-color: {BORDER_2}; max-height: 1px; margin: 4px 0;")
        sec.inner.addWidget(sep)
        
        for label, desc in info["fields"]:
            # Section ini ditulis untuk pembaca laporan, jadi istilah elektro dijelaskan ringkas.
            field_wrap = QWidget()
            field_wrap.setStyleSheet("background: transparent;")
            fw_layout = QVBoxLayout(field_wrap)
            fw_layout.setContentsMargins(0, 4, 0, 4)
            fw_layout.setSpacing(2)
            
            lbl_title = QLabel(f"• {label}")
            lbl_title.setStyleSheet(f"color: {ACCENT}; font-weight: bold; font-size: 9pt;")
            
            lbl_desc = QLabel(desc)
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet(f"color: {TEXT_0}; font-size: 8.5pt; padding-left: 10px;")
            
            fw_layout.addWidget(lbl_title)
            fw_layout.addWidget(lbl_desc)
            
            sec.inner.addWidget(field_wrap)

    # ══════════════════════════════════════════════════════════════════
    #  Public show methods
    # ══════════════════════════════════════════════════════════════════

    def show_empty(self) -> None:
        self._clear()
        self._gap(6)
        counts = {}
        for nd in state.nodes.values():
            k = nd.get("kind")
            counts[k] = counts.get(k, 0) + 1

        if not state.nodes:
            # Panel kosong tetap memberi langkah pertama agar user tidak mencari menu tersembunyi.
            sec = self._section("Mulai", accent=GREEN)
            sec.inner.addWidget(_muted(
                "Tambah Bus pertama dari toolbar,\n"
                "atau muat template jaringan contoh."
            ))
        else:
            # Ringkasan jaringan mengambil state langsung agar selalu sinkron dengan canvas.
            sec = self._section("Ringkasan Jaringan", accent=BLUE)
            self._spec_grid(sec.inner, [
                ("Bus",       str(counts.get("bus", 0)),   ""),
                ("Generator", str(counts.get("gen", 0)),   ""),
                ("Beban",     str(counts.get("load", 0)),  ""),
                ("Trafo",     str(counts.get("trafo", 0)), ""),
                ("Shunt",     str(counts.get("shunt", 0)), ""),
                ("Koneksi",   str(len(state.links)),        ""),
            ])
            if state.results_are_stale():
                sec.inner.addWidget(_guidance("Model berubah — jalankan Power Flow lagi."))
            elif state.last_results.get("nodes"):
                sec.inner.addWidget(_guidance("Hasil Power Flow tersedia.", ok=True))

        tips = self._section("Tips", accent=TEXT_3, collapsed=True)
        tips.inner.addWidget(_muted(
            "▸  Drag dari port kuning ke port tujuan\n"
            "▸  Klik kanan saat drag untuk batal\n"
            "▸  Scroll untuk zoom, middle-click untuk pan\n"
            "▸  Del / Backspace untuk hapus seleksi"
        ))
        self._layout.addStretch(1)

    def show_node(self, node_tag) -> None:
        nd = state.nodes.get(node_tag)
        if not nd:
            self.show_empty(); return
        self._clear()
        self._gap(4)
        kind = nd["kind"]
        accent = COMP_COLORS.get(kind, ACCENT)
        conns = self._conns_for_node(node_tag)

        # ── Status ────────────────────────────────────────────────────
        sec_status = self._section(
            f"{KIND_LABELS.get(kind, kind).upper()} — {nd['label']}",
            accent=accent,
        )
        sec_status.inner.addWidget(
            _guidance(self._node_guidance(node_tag), ok=bool(conns))
        )

        # ── Edit ──────────────────────────────────────────────────────
        sec_edit = self._section("Edit", accent=accent)
        name = QLineEdit(nd["label"])
        # Semua field edit menulis lewat _set_node agar hasil power flow lama dihapus.
        name.editingFinished.connect(
            lambda: self._set_node(node_tag, "label", name.text()))
        self._add_field(sec_edit.inner, "label", name)

        if kind == "bus":
            sp = self._spin(float(nd.get("vn_kv", 0)))
            sp.valueChanged.connect(lambda v: self._set_node(node_tag, "vn_kv", float(v)))
            self._add_field(sec_edit.inner, "vn_kv", sp)

            cb = QCheckBox("Slack / external grid")
            cb.setChecked(bool(nd.get("is_slack")))
            # Rerender dibutuhkan karena slack menampilkan field vm_pu dan va_degree tambahan.
            cb.toggled.connect(
                lambda v: self._set_node(node_tag, "is_slack", bool(v), rerender=True))
            sec_edit.inner.addSpacing(4)
            sec_edit.inner.addWidget(cb)

            if nd.get("is_slack"):
                for key in ("vm_pu", "va_degree"):
                    sp = self._spin(float(nd.get(key, 0)))
                    sp.valueChanged.connect(
                        lambda v, k=key: self._set_node(node_tag, k, float(v)))
                    self._add_field(sec_edit.inner, key, sp)

        elif kind == "gen":
            is_pv = nd.get("ctrl_mode") == "pv"
            sp = self._spin(float(nd.get("p_mw", 0)))
            sp.valueChanged.connect(
                lambda v: self._set_node(node_tag, "p_mw", float(v)))
            self._add_field(sec_edit.inner, "p_mw", sp)

            cb = QCheckBox("Kontrol tegangan (mode PV)")
            cb.setChecked(is_pv)
            cb.setToolTip("PV: Q diatur otomatis untuk menahan tegangan setpoint.\n"
                          "PQ: P dan Q tetap (static generator).")
            # Rerender karena mode menentukan field Q atau Vm yang tampil.
            cb.toggled.connect(
                lambda v: self._set_node(node_tag, "ctrl_mode",
                                         "pv" if v else "pq", rerender=True))
            sec_edit.inner.addSpacing(4)
            sec_edit.inner.addWidget(cb)

            if is_pv:
                sp = self._spin(float(nd.get("vm_pu", 1.0)))
                sp.valueChanged.connect(
                    lambda v: self._set_node(node_tag, "vm_pu", float(v)))
                self._add_field(sec_edit.inner, "vm_pu", sp)
            else:
                sp = self._spin(float(nd.get("q_mvar", 0)))
                sp.valueChanged.connect(
                    lambda v: self._set_node(node_tag, "q_mvar", float(v)))
                self._add_field(sec_edit.inner, "q_mvar", sp)

            sp = self._spin(float(nd.get("sn_mva", 1.0)))
            sp.valueChanged.connect(
                lambda v: self._set_node(node_tag, "sn_mva", float(v)))
            self._add_field(sec_edit.inner, "sn_mva", sp)

        elif kind in ("load", "shunt"):
            for key in ("p_mw", "q_mvar"):
                sp = self._spin(float(nd.get(key, 0)))
                sp.valueChanged.connect(
                    lambda v, k=key: self._set_node(node_tag, k, float(v)))
                self._add_field(sec_edit.inner, key, sp)

        elif kind == "trafo":
            for key in ("sn_mva", "vn_hv_kv", "vn_lv_kv",
                        "vk_percent", "vkr_percent", "pfe_kw", "i0_percent"):
                sp = self._spin(float(nd.get(key, 0)))
                sp.valueChanged.connect(
                    lambda v, k=key: self._set_node(node_tag, k, float(v)))
                self._add_field(sec_edit.inner, key, sp)

        # ── Koneksi ───────────────────────────────────────────────────
        sec_conn = self._section("Koneksi", accent=BLUE)
        if not conns:
            sec_conn.inner.addWidget(_muted("Belum ada koneksi."))
        else:
            for c in conns:
                self._conn_badge(sec_conn.inner, c)

        # ── Spesifikasi ──────────────────────────────────────────────
        sec_spec = self._section("Spesifikasi", accent=TEXT_3, collapsed=True)
        spec_rows = [
            ("Tipe",    KIND_LABELS.get(kind, kind), ""),
        ]
        mapped = state.pp_element_map.get(node_tag)
        if mapped:
            # Mapping pandapower membantu menjelaskan tabel hasil mana yang sedang dilihat.
            spec_rows += [("Tabel", mapped[0], ""), ("Index", str(int(mapped[1])), "")]
        self._spec_grid(sec_spec.inner, spec_rows)

        # ── Hasil ─────────────────────────────────────────────────────
        sec_res = self._section("Hasil Power Flow", accent=GREEN, collapsed=True)
        result = state.last_results.get("nodes", {}).get(node_tag)
        if state.results_are_stale():
            # Hasil lama tidak disembunyikan diam-diam; panel memberi alasan harus run ulang.
            sec_res.inner.addWidget(_guidance("Model diedit — jalankan ulang."))
        if not result:
            sec_res.inner.addWidget(_muted("Belum ada hasil."))
        else:
            rows = []
            for k, (label, unit) in RESULT_LABELS.items():
                if k in result:
                    rows.append((label, result[k], unit))
            self._spec_grid(sec_res.inner, rows)
        
        self._add_about_section(kind)

        # ── Hapus ─────────────────────────────────────────────────────
        self._gap(10)
        btn = QPushButton(f"HAPUS {KIND_LABELS.get(kind, 'Komponen').upper()}")
        btn.setProperty("danger", True)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.clicked.connect(lambda: self.main.delete_node(node_tag))
        wrap = QWidget()
        wrap.setStyleSheet(f"background: {BG_1};")
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(12, 4, 12, 8)
        wl.addWidget(btn)
        self._add(wrap)

        self._layout.addStretch(1)

    def show_link(self, link_tag) -> None:
        if link_tag not in state.links:
            self.show_empty(); return
        self._clear()
        self._gap(4)
        is_line = link_tag in state.line_data

        # Link bus-ke-bus punya data saluran; koneksi trafo/non-line hanya relasi visual.
        sec_hdr = self._section(
            "SALURAN" if is_line else "KONEKSI",
            accent=ORANGE if is_line else BLUE,
        )
        sec_hdr.inner.addWidget(_muted(self._link_label(link_tag)))

        if is_line:
            sec_hdr.inner.addWidget(_guidance(
                "Saluran bus↔bus — R, X, C dipakai hitung rugi & loading.", ok=True))

            sec_edit = self._section("Edit", accent=ORANGE)
            data = state.line_data[link_tag]
            name = QLineEdit(data.get("label", "Line"))
            # Field line menulis ke state.line_data karena engine membacanya saat build_pp_network().
            name.editingFinished.connect(
                lambda: self._set_line(link_tag, "label", name.text()))
            self._add_field(sec_edit.inner, "label", name)

            # Preset tipe kabel dari standard types pandapower (NAYY, NA2XS2Y, dst).
            preset_lbl = QLabel("Preset tipe kabel (pandapower)")
            preset_lbl.setStyleSheet(f"color: {TEXT_2}; font-size: 9pt;")
            sec_edit.inner.addWidget(preset_lbl)
            combo = QComboBox()
            combo.addItem("— Manual —")
            std_types = engine.line_std_types()
            combo.addItems(sorted(std_types))
            current = data.get("std_type", "")
            if current in std_types:
                combo.setCurrentText(current)
            combo.currentTextChanged.connect(
                lambda name_: self._apply_line_std_type(link_tag, name_))
            sec_edit.inner.addWidget(combo)

            self._line_spins = {}
            for key in ("length_km", "r_ohm_per_km", "x_ohm_per_km",
                        "c_nf_per_km", "max_i_ka"):
                sp = self._spin(float(data.get(key, 0)))
                sp.valueChanged.connect(
                    lambda v, k=key: self._set_line(link_tag, k, float(v)))
                self._add_field(sec_edit.inner, key, sp)
                self._line_spins[key] = sp

            sec_spec = self._section("Detail Saluran", accent=TEXT_3, collapsed=True)
            total_r = data["length_km"] * data["r_ohm_per_km"]
            total_x = data["length_km"] * data["x_ohm_per_km"]
            self._spec_grid(sec_spec.inner, [
                ("Nama",     data.get("label", "Line"), ""),
                ("Panjang",  data["length_km"],          "km"),
                ("R/km",     data["r_ohm_per_km"],       "Ω/km"),
                ("X/km",     data["x_ohm_per_km"],       "Ω/km"),
                ("C/km",     data["c_nf_per_km"],        "nF/km"),
                ("I maks",   data["max_i_ka"],           "kA"),
                ("Rtotal",   total_r,                    "Ω"),
                ("Xtotal",   total_x,                    "Ω"),
            ])

            sec_res = self._section("Hasil Power Flow", accent=GREEN, collapsed=True)
            result = state.last_results.get("links", {}).get(link_tag)
            if state.results_are_stale():
                sec_res.inner.addWidget(_guidance("Model diedit — jalankan ulang."))
            if not result:
                sec_res.inner.addWidget(_muted("Belum ada hasil."))
            else:
                rows = []
                for k, (label, unit) in RESULT_LABELS.items():
                    if k in result:
                        rows.append((label, result[k], unit))
                self._spec_grid(sec_res.inner, rows)
            
            self._add_about_section("line")

            self._gap(10)
            btn = QPushButton("HAPUS SALURAN")
            btn.setProperty("danger", True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda: self.main.delete_link(link_tag))
            wrap = QWidget()
            wrap.setStyleSheet(f"background: {BG_1};")
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(12, 4, 12, 8)
            wl.addWidget(btn)
            self._add(wrap)

        self._layout.addStretch(1)

    # ── state mutations ───────────────────────────────────────────────

    def _set_node(self, tag, key, val, rerender=False):
        # qt_model.set_node_value menjaga rule khusus seperti hanya satu slack bus aktif.
        qt_model.set_node_value(tag, key, val)
        self.main.canvas_scene.refresh_all()
        self.main.clear_results(keep_analysis=False)
        if rerender:
            self.show_node(tag)
        self.main.set_status("Model diedit.", warn=True)

    def _apply_line_std_type(self, tag, name: str) -> None:
        """Mengisi parameter saluran dari standard type pandapower terpilih."""
        if tag not in state.line_data:
            return
        params = engine.line_std_types().get(name)
        if not params:
            # Pilihan "Manual" hanya melepas penanda preset tanpa mengubah angka.
            state.line_data[tag].pop("std_type", None)
            return
        state.line_data[tag].update(params)
        state.line_data[tag]["std_type"] = name
        # Spinbox di panel diisi ulang agar angka preset langsung terlihat.
        for key, sp in getattr(self, "_line_spins", {}).items():
            if key in params:
                sp.blockSignals(True)
                sp.setValue(params[key])
                sp.blockSignals(False)
        state.mark_model_dirty()
        self.main.clear_results(keep_analysis=False)
        self.main.canvas_scene.refresh_all()
        self.main.set_status(f"Preset {name} diterapkan.")

    def _set_line(self, tag, key, val):
        if tag not in state.line_data:
            return
        # Perubahan parameter saluran membatalkan hasil lama karena loading/rugi berubah.
        state.line_data[tag][key] = val
        if key in ("r_ohm_per_km", "x_ohm_per_km", "c_nf_per_km", "max_i_ka"):
            # Edit manual berarti parameter tidak lagi sesuai preset.
            state.line_data[tag].pop("std_type", None)
        state.mark_model_dirty()
        self.main.clear_results(keep_analysis=False)
        self.main.canvas_scene.refresh_all()
        self.main.set_status("Saluran diedit.", warn=True)

    # ── helpers ───────────────────────────────────────────────────────

    def _node_guidance(self, nt) -> str:
        nd = state.nodes[nt]
        kind = nd["kind"]
        c = self._conns_for_node(nt)
        if kind == "bus":
            if not c:
                return "Belum tersambung.  Drag port kuning → port tujuan."
            if nd.get("is_slack"):
                return "Bus acuan aktif.  Pastikan jaringan terhubung."
            return "Bus sudah terhubung."
        if kind in ("gen", "load", "shunt") and not c:
            return f"{KIND_LABELS[kind]} harus dihubungkan ke bus."
        if kind == "trafo" and len(c) < 2:
            return "Transformer butuh koneksi HV dan LV."
        return "Komponen terhubung ✓"

    def _conns_for_node(self, nt) -> list[str]:
        nd = state.nodes.get(nt, {})
        # qt_model.attrs_for_node dipakai agar panel tidak perlu tahu nama semua pin.
        attrs = set(qt_model.attrs_for_node(nt))
        out = []
        for lt, (fa, ta) in state.links.items():
            if fa not in attrs and ta not in attrs:
                continue
            own  = fa if fa in attrs else ta
            other = ta if fa in attrs else fa
            on   = state.attr_to_node.get(other)
            ond  = state.nodes.get(on, {})
            role = "Saluran" if lt in state.line_data else "Koneksi"
            out.append(
                f"{self._attr_name(nd, own)} → {ond.get('label','?')} "
                f"({KIND_LABELS.get(ond.get('kind'),'?')}, {role})"
            )
        return out

    def _attr_name(self, nd, attr_tag) -> str:
        for k, lbl in (("out_attr","OUT"), ("in_attr","IN"),
                       ("pin","PIN"), ("hv_pin","HV"), ("lv_pin","LV")):
            if nd.get(k) == attr_tag:
                return lbl
        return "?"

    def _link_label(self, lt) -> str:
        fa, ta = state.links.get(lt, (None, None))
        fn = state.attr_to_node.get(fa)
        tn = state.attr_to_node.get(ta)
        return (f"{state.nodes.get(fn, {}).get('label','?')}  ↔  "
                f"{state.nodes.get(tn, {}).get('label','?')}")


# ═══════════════════════════════════════════════════════════════════════════
#  MainWindow
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PANDAPOWER VISUALIZATION")
        self.resize(1520, 860)
        self.active_toast  = None
        self.status_label  = QLabel("")
        # Reset awal membuat test dan launch manual selalu mulai dari state kosong.
        qt_model.reset_model(clear_undo=True)

        self.canvas_scene = GridScene()
        self.canvas_view  = GridView(self.canvas_scene)
        # Signal Qt menjaga MainWindow sebagai koordinator, bukan pemilik logika canvas.
        self.canvas_scene.selectionModelChanged.connect(self.on_selection_changed)
        self.canvas_scene.statusChanged.connect(self.set_status)
        self.canvas_scene.modelChanged.connect(self.on_model_changed)
        self.canvas_view.zoomChanged.connect(self.update_zoom_label)



        self.zoom_label = QLabel("100%")
        self.zoom_label.setStyleSheet(f"""
            color: {ACCENT}; min-width: 48px;
            font-weight: bold; font-size: 10pt;
        """)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.analysis_log = QTextEdit()
        self.analysis_log.setReadOnly(True)
        self.analysis_log.setPlainText("Jalankan Validasi atau Power Flow.")

        self.results_table = QTableWidget(0, 6)
        self.bus_table     = QTableWidget(0, 5)
        self.properties    = PropertiesPanel(self)
        self.right_dock    = None
        self._build_ui()
        self.status_label.setStyleSheet(f"color: {TEXT_1}; padding: 2px 8px;")
        self.statusBar().addPermanentWidget(self.status_label, 1)
        self.properties.show_empty()

    # ── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_toolbar()
        self._build_right()

        for table, headers in (
            (self.results_table,
             ["Nama", "Tipe", "Daya aktif", "Daya reaktif", "Rugi-rugi", "Loading"]),
            (self.bus_table,
             ["Bus", "Vn (kV)", "V (pu)", "Sudut (°)", "Status"]),
        ):
            table.setHorizontalHeaderLabels(headers)
            hdr = table.horizontalHeader()
            hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            hdr.setMinimumSectionSize(72)
            table.verticalHeader().setVisible(False)
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.bottom_panel = self._build_bottom()

        splitter = QSplitter(Qt.Orientation.Vertical)
        # Splitter memberi canvas ruang utama tetapi hasil analisis tetap terlihat.
        splitter.addWidget(self.canvas_view)
        splitter.addWidget(self.bottom_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([560, 250])
        self.setCentralWidget(splitter)

    # ── bottom result panel ───────────────────────────────────────────

    def _build_bottom(self) -> QWidget:
        """Panel hasil: baris kartu statistik + tab tabel/log."""
        bottom = QWidget()
        bottom.setStyleSheet(f"background: {BG_1};")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(6)

        # Kartu statistik membuat angka kunci terbaca sekilas tanpa membuka tab.
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.chip_status  = StatChip("Status")
        self.chip_loss    = StatChip("Total rugi")
        self.chip_vmin    = StatChip("V minimum")
        self.chip_loading = StatChip("Loading maks")
        for chip in (self.chip_status, self.chip_loss,
                     self.chip_vmin, self.chip_loading):
            chips.addWidget(chip)
        chips.addStretch(1)
        bl.addLayout(chips)
        self._reset_stat_chips()

        self.result_tabs = QTabWidget()
        self.result_tabs.addTab(self.results_table, "Saluran / Trafo")
        self.result_tabs.addTab(self.bus_table, "Tegangan Bus")
        self.result_tabs.addTab(self.analysis_log, "Log Analisis")
        bl.addWidget(self.result_tabs, 1)
        return bottom

    def _reset_stat_chips(self) -> None:
        for chip in (self.chip_status, self.chip_loss,
                     self.chip_vmin, self.chip_loading):
            chip.reset()
        self.chip_status.set_value("Belum dijalankan", TEXT_2)

    # ── ribbon toolbar ────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        """Ribbon bertab gaya AutoCAD: baris tab di atas, grup tombol di bawah."""
        tb = QToolBar("Ribbon")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setFixedHeight(92)
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)

        ribbon = QWidget()
        ribbon.setObjectName("ribbonContainer")
        ribbon.setStyleSheet(f"""
            QWidget#ribbonContainer {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {BG_2}, stop:1 {BG_1});
                border-bottom: 2px solid {BORDER_2};
            }}
        """)
        outer = QVBoxLayout(ribbon)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── baris tab ─────────────────────────────────────────────────
        tab_row = QWidget()
        tab_row.setStyleSheet(f"background: {BG_0}; border-bottom: 1px solid {BORDER_1};")
        trl = QHBoxLayout(tab_row)
        trl.setContentsMargins(8, 0, 8, 0)
        trl.setSpacing(0)

        self._ribbon_stack = QStackedWidget()
        self._ribbon_tabs: list[QPushButton] = []

        pages = [
            ("BERANDA",  self._ribbon_page_home()),
            ("KOMPONEN", self._ribbon_page_components()),
            ("ANALISIS", self._ribbon_page_analysis()),
            ("EKSPOR",   self._ribbon_page_export()),
            ("TAMPILAN", self._ribbon_page_view()),
        ]
        for idx, (title, page) in enumerate(pages):
            btn = QPushButton(title)
            btn.setProperty("ribbonTab", True)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=idx: self._select_ribbon_tab(i))
            trl.addWidget(btn)
            self._ribbon_tabs.append(btn)
            self._ribbon_stack.addWidget(page)
        trl.addStretch(1)

        outer.addWidget(tab_row)
        outer.addWidget(self._ribbon_stack, 1)
        self._select_ribbon_tab(0)

        tb.addWidget(ribbon)

    def _select_ribbon_tab(self, index: int) -> None:
        self._ribbon_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._ribbon_tabs):
            btn.setChecked(i == index)

    @staticmethod
    def _ribbon_page() -> tuple[QWidget, QHBoxLayout]:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lo = QHBoxLayout(page)
        lo.setContentsMargins(8, 0, 8, 0)
        lo.setSpacing(0)
        return page, lo

    def _ribbon_page_home(self) -> QWidget:
        page, rl = self._ribbon_page()
        g = RibbonGroup("Project")
        g.add_btn("BARU",   self.new_project)
        g.add_btn("BUKA",   self.load_project)
        g.add_btn("SIMPAN", self.save_project)
        rl.addWidget(g)
        rl.addWidget(_v_sep_ribbon())

        g = RibbonGroup("Edit")
        g.add_btn("UNDO", self.undo)
        g.add_btn("REDO", self.redo)
        rl.addWidget(g)
        rl.addWidget(_v_sep_ribbon())

        g = RibbonGroup("Analisis")
        g.add_btn("RUN POWER FLOW", self.run_power_flow, color=GREEN, bold=True)
        g.add_btn("VALIDASI", self.validate_network, color=BLUE)
        rl.addWidget(g)
        rl.addWidget(_v_sep_ribbon())

        g = RibbonGroup("Zoom")
        g.add_btn("OUT", lambda: self.canvas_view.set_zoom(self.canvas_view.zoom / 1.2))
        g.add_widget(self.zoom_label)
        g.add_btn("IN", lambda: self.canvas_view.set_zoom(self.canvas_view.zoom * 1.2))
        g.add_btn("FIT", self.canvas_view.fit_all)
        rl.addWidget(g)
        rl.addStretch(1)
        return page

    def _ribbon_page_components(self) -> QWidget:
        page, rl = self._ribbon_page()
        g = RibbonGroup("Tambah Komponen")
        for label, kind in [("BUS", "bus"), ("GEN", "gen"), ("TRAFO", "trafo"),
                            ("SHUNT", "shunt"), ("BEBAN", "load")]:
            # Tombol komponen memanggil add_component agar spawn selalu memakai area terlihat.
            g.add_btn(label, lambda _=False, k=kind: self.add_component(k),
                      color=COMP_COLORS[kind])
        rl.addWidget(g)
        rl.addWidget(_v_sep_ribbon())

        g = RibbonGroup("Canvas")
        g.add_btn("MUAT TEMPLATE", self.load_template)
        g.add_btn("KOSONGKAN", self.request_clear_canvas, color=RED)
        rl.addWidget(g)
        rl.addStretch(1)
        return page

    def _ribbon_page_analysis(self) -> QWidget:
        page, rl = self._ribbon_page()
        g = RibbonGroup("Simulasi")
        g.add_btn("RUN POWER FLOW", self.run_power_flow, color=GREEN, bold=True)
        g.add_btn("VALIDASI JARINGAN", self.validate_network, color=BLUE)
        rl.addWidget(g)
        rl.addWidget(_v_sep_ribbon())

        g = RibbonGroup("Seleksi")
        g.add_btn("EDIT SALURAN", self.edit_selected_line)
        rl.addWidget(g)
        rl.addStretch(1)
        return page

    def _ribbon_page_export(self) -> QWidget:
        page, rl = self._ribbon_page()
        g = RibbonGroup("Gambar & Laporan")
        g.add_btn("EXPORT PNG", self.export_canvas_image, color=PURPLE)
        g.add_btn("EXPORT LAPORAN HTML", self.export_report, color=ACCENT)
        rl.addWidget(g)
        rl.addWidget(_v_sep_ribbon())

        g = RibbonGroup("Data")
        g.add_btn("HASIL CSV", self.export_results)
        g.add_btn("PANDAPOWER JSON", self.export_pandapower_json)
        rl.addWidget(g)
        rl.addStretch(1)
        return page

    def _ribbon_page_view(self) -> QWidget:
        page, rl = self._ribbon_page()
        g = RibbonGroup("Panel")
        self._btn_toggle_right = g.add_btn("PANEL PROPERTI", self.toggle_right)
        self._btn_toggle_right.setCheckable(True)
        self._btn_toggle_right.setChecked(True)
        self._btn_toggle_bottom = g.add_btn("PANEL HASIL", self.toggle_bottom)
        self._btn_toggle_bottom.setCheckable(True)
        self._btn_toggle_bottom.setChecked(True)
        rl.addWidget(g)
        rl.addWidget(_v_sep_ribbon())

        g = RibbonGroup("Kamera")
        g.add_btn("RESET VIEW", self.canvas_view.reset_view)
        g.add_btn("FIT SEMUA", self.canvas_view.fit_all)
        rl.addWidget(g)
        rl.addStretch(1)
        return page

    # ── right panel ───────────────────────────────────────────────────

    def _build_right(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.properties)

        self.right_dock = QDockWidget("Panel Properti", self)
        self.right_dock.setObjectName("rightDock")
        self.right_dock.setWidget(scroll)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)
        self.right_dock.setMinimumWidth(RIGHT_WIDTH)
        self.resizeDocks([self.right_dock], [RIGHT_WIDTH], Qt.Orientation.Horizontal)
        self.right_dock.visibilityChanged.connect(self._btn_toggle_right.setChecked)

    # ── toggles ───────────────────────────────────────────────────────

    def toggle_right(self) -> None:
        self.right_dock.setVisible(self._btn_toggle_right.isChecked())

    def toggle_bottom(self) -> None:
        self.bottom_panel.setVisible(self._btn_toggle_bottom.isChecked())

    # ── canvas actions ────────────────────────────────────────────────

    def set_analysis_text(self, text: str) -> None:
        self.analysis_log.setPlainText(text or "Jalankan Validasi atau Power Flow.")

    def edit_selected_line(self) -> None:
        lt = self.canvas_scene.selected_link_tag()
        if lt and lt in state.line_data:
            state.selected_link[0] = lt
            state.selected_node[0] = None
            self.properties.show_link(lt)
            self.set_status("Line dipilih.")
            return
        self.set_status("Pilih koneksi bus-ke-bus dulu.", error=True)

    def undo(self) -> None:
        """Mengembalikan model ke snapshot terakhir dari undo stack."""
        # Jangan undo saat user sedang mengetik agar Ctrl+Z field tidak mengubah canvas.
        if self.properties.editing_field:
            return
        # Ambil snapshot terakhir dari state._undo_stack.
        snap = state.pop_undo()
        if snap is None:
            self.set_status("Tidak ada undo.", error=True); return
        # Kondisi sekarang disimpan dulu ke redo stack agar undo bisa dibatalkan.
        state.push_redo_snapshot()
        # qt_model memulihkan state, lalu scene Qt dibangun ulang dari state tersebut.
        qt_model.restore_undo_snapshot(snap)
        # Item Qt lama dibuang dan dibuat ulang dari state hasil undo.
        self.canvas_scene.rebuild_from_state()
        # Hasil power flow lama tidak relevan setelah undo.
        self.clear_results()
        # Panel dikosongkan karena selection lama mungkin sudah hilang.
        self.properties.show_empty()
        self.set_status("Undo.")

    def redo(self) -> None:
        """Menerapkan kembali snapshot yang dibatalkan oleh undo terakhir."""
        if self.properties.editing_field:
            return
        snap = state.pop_redo()
        if snap is None:
            self.set_status("Tidak ada redo.", error=True); return
        # Kondisi sekarang masuk undo stack tanpa menghapus sisa redo.
        state.push_undo_for_redo()
        qt_model.restore_undo_snapshot(snap)
        self.canvas_scene.rebuild_from_state()
        self.clear_results()
        self.properties.show_empty()
        self.set_status("Redo.")

    def add_component(self, kind: str) -> None:
        """Menambahkan komponen baru ke model dan menampilkannya di canvas."""
        # GridView.suggest_spawn memakai canvas_logic agar node baru tidak muncul di luar layar.
        pos = self.canvas_view.suggest_spawn(kind)
        # qt_model.create_node membuat data elektro, pin, attr_role, dan undo snapshot.
        nt = qt_model.create_node(kind, pos)
        # Scene hanya menggambar item dari tag node yang sudah masuk state.
        self.canvas_scene.add_node_item(nt)
        # Tambah komponen membatalkan hasil analisis sebelumnya.
        self.clear_results()
        # Status memberi feedback langsung ke user dan toast.
        self.set_status(f"{KIND_LABELS.get(kind, kind)} ditambahkan.")

    def delete_node(self, nt) -> None:
        """Menghapus node terpilih dari model dan scene."""
        # qt_model.delete_node ikut membersihkan link yang menempel pada node.
        if qt_model.delete_node(nt):
            self.canvas_scene.remove_node_item(nt)
            self.properties.show_empty()
            self.set_status("Komponen dihapus.")

    def delete_link(self, lt) -> None:
        """Menghapus link terpilih dari model dan scene."""
        # Delete link lewat qt_model agar line_data dan waypoint ikut terhapus.
        if qt_model.delete_link(lt):
            self.canvas_scene.remove_edge_item(lt)
            self.properties.show_empty()
            self.set_status("Saluran dihapus.")

    def delete_selection(self) -> None:
        """Menghapus item yang sedang dipilih, baik node maupun link."""
        if self.properties.editing_field:
            return
        nt = self.canvas_scene.selected_node_tag()
        lt = self.canvas_scene.selected_link_tag()
        if nt:
            self.delete_node(nt)
        elif lt:
            self.delete_link(lt)

    def keyPressEvent(self, event) -> None:
        """Menangani shortcut keyboard untuk delete, undo, dan zoom."""
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selection(); return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.key() == Qt.Key.Key_Z:
                # Ctrl+Shift+Z adalah alias redo yang umum di editor lain.
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.redo(); return
                self.undo(); return
            if event.key() == Qt.Key.Key_Y:
                self.redo(); return
            if event.key() == Qt.Key.Key_S:
                self.save_project(); return
            if event.key() == Qt.Key.Key_O:
                self.load_project(); return
            if event.key() == Qt.Key.Key_N:
                self.new_project(); return
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.canvas_view.set_zoom(self.canvas_view.zoom * 1.2); return
            if event.key() == Qt.Key.Key_Minus:
                self.canvas_view.set_zoom(self.canvas_view.zoom / 1.2); return
            if event.key() == Qt.Key.Key_0:
                self.canvas_view.reset_view(); return
        super().keyPressEvent(event)

    def on_selection_changed(self, nt, lt) -> None:
        """Memperbarui panel kanan saat pilihan canvas berubah."""
        if nt:
            self.properties.show_node(nt)
        elif lt:
            self.properties.show_link(lt)
        else:
            self.properties.show_empty()

    def on_model_changed(self) -> None:
        if not state.selected_node[0] and not state.selected_link[0]:
            self.properties.show_empty()

    def clear_results(self, keep_analysis: bool = True) -> None:
        """Menghapus hasil analisis lama dari state, tabel, dan canvas."""
        # Bersihkan hasil global yang dipakai canvas dan properties panel.
        state.clear_results()
        # keep_analysis False dipakai ketika edit parameter, supaya log lama ikut hilang.
        if not keep_analysis:
            self.analysis_log.setPlainText("Jalankan Validasi atau Power Flow.")
        # Tabel bawah dikosongkan karena row lama sudah tidak sesuai model.
        self.results_table.setRowCount(0)
        self.bus_table.setRowCount(0)
        self._reset_stat_chips()
        # Repaint canvas agar warna hasil/loading ikut hilang.
        self.canvas_scene.refresh_all()

    # ── power flow / validate ─────────────────────────────────────────

    def validate_network(self) -> None:
        """Menjalankan validasi model dan menampilkan error/peringatan ke UI."""
        # engine.validate_model tidak menyentuh GUI; MainWindow hanya memformat pesannya.
        errors, warnings = engine.validate_model()
        # Kalau ada error, hasil power flow lama tidak boleh dipercaya.
        if errors:
            self.clear_results()
        # lines adalah isi panel log validasi kiri.
        lines = []
        if errors:
            lines.append("KESALAHAN")
            # Error dibuat bullet agar mudah dipindah ke laporan.
            lines.extend(f"  • {e}" for e in errors)
        if warnings:
            if lines: lines.append("")
            lines.append("PERINGATAN")
            # Warning tetap tampil walau jaringan masih bisa dianalisis.
            lines.extend(f"  • {w}" for w in warnings)
        if not lines:
            # Tidak ada error/warning berarti model siap untuk run power flow.
            lines.append("✓  Jaringan valid.  Siap Power Flow.")
        self.set_analysis_text("\n".join(lines))
        # Tab log dibuka langsung supaya hasil validasi tidak terlewat.
        self.result_tabs.setCurrentWidget(self.analysis_log)
        # Status bar/toast membedakan error dengan warna.
        self.set_status("Jaringan belum valid." if errors else "Jaringan valid.",
                        error=bool(errors))

    def run_power_flow(self) -> None:
        """Menjalankan simulasi power flow dan menampilkan hasilnya di UI."""
        # engine.run_pf membangun net pandapower dan menyimpan hasil ke state.last_results.
        # ok adalah status berhasil/gagal, msg adalah pesan untuk user.
        # net adalah object pandapower yang berisi tabel hasil.
        # _n2p dan _lmap tidak dipakai di UI ini karena engine sudah menyimpan mapping ke state.
        ok, msg, net, _n2p, _lmap = engine.run_pf()
        # Jika gagal, UI menampilkan pesan dari engine dan membersihkan hasil lama.
        if not ok:
            # Hapus tabel/warna hasil lama agar user tidak membaca hasil yang salah.
            self.clear_results()
            # Ubah separator " | " menjadi bullet baris baru supaya error mudah dibaca.
            self.set_analysis_text("KESALAHAN\n  • " + msg.replace(" | ", "\n  • "))
            self.chip_status.set_value("Gagal", RED)
            # Log error langsung ditampilkan agar user tidak mencari tab.
            self.result_tabs.setCurrentWidget(self.analysis_log)
            # Tampilkan pesan gagal di status bar dan toast merah.
            self.set_status(msg, error=True)
            # Stop di sini karena tidak ada hasil yang bisa dirender.
            return
        # Hasil link/trafo diubah ke format tabel bawah.
        rows = self._line_result_rows()
        # Tabel bawah diisi dari rows hasil ringkasan.
        self._render_rows(rows)
        self._render_bus_rows()
        # Summary mengambil angka total dari object net pandapower.
        self.set_analysis_text(self._summary(net, rows))
        self._update_stat_chips(net, rows)
        # Jika user sedang memilih node, panel kanan ikut refresh menampilkan hasil terbaru.
        if state.selected_node[0]:
            # show_node membaca state.last_results untuk komponen terpilih.
            self.properties.show_node(state.selected_node[0])
        elif state.selected_link[0]:
            # Link terpilih juga perlu refresh supaya loading/rugi muncul.
            self.properties.show_link(state.selected_link[0])
        # Status sukses ditampilkan setelah semua UI hasil selesai diperbarui.
        self.set_status("Konvergen")

    def _line_result_rows(self) -> list[dict]:
        """Meringkas hasil link/trafo menjadi baris tabel bawah."""
        # rows akan berisi dict sederhana yang cocok untuk QTableWidget.
        rows = []
        # state.last_results["links"] diisi oleh engine._collect_results().
        for lt, res in state.last_results.get("links", {}).items():
            # Tabel bawah diringkas dari hasil link agar pembaca cepat melihat loading/rugi.
            # Ambil dua pin ujung link dari state.links.
            fa, ta = state.links.get(lt, (None, None))
            # Ubah pin menjadi node pemilik untuk mencari label komponen.
            fn, tn = state.attr_to_node.get(fa), state.attr_to_node.get(ta)
            # line_data hanya ada untuk saluran bus-ke-bus.
            ld = state.line_data.get(lt, {})
            # Nama tabel memakai label line kalau ada; jika tidak, pakai label dua node.
            name = ld.get("label") or (
                f"{state.nodes.get(fn,{}).get('label','?')} - "
                f"{state.nodes.get(tn,{}).get('label','?')}")
            # Line memakai p_from_mw, trafo memakai p_hv_mw sebagai arah awal.
            p   = res.get("p_from_mw", res.get("p_hv_mw", 0.0))
            # Line memakai q_from_mvar, trafo memakai q_hv_mvar sebagai arah awal.
            q   = res.get("q_from_mvar", res.get("q_hv_mvar", 0.0))
            # pl_mw dikali 1000 supaya tampil dalam kW.
            loss = float(res.get("pl_mw", 0.0)) * 1000
            # Dict ini dipakai _render_rows untuk mengisi kolom tabel.
            rows.append({
                "name": name, "kind": res.get("table", "link"),
                "p_mw": p, "q_mvar": q, "loss_kw": loss,
                "loading": res.get("loading_percent", 0.0),
                # Panah kanan berarti P bernilai positif dari sisi awal.
                "direction": "→" if p >= 0 else "←",
            })
        # Return rows agar fungsi render tidak perlu tahu detail state.
        return rows

    def _render_rows(self, rows: list[dict]) -> None:
        self.results_table.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            vals = [
                row["name"], row["kind"],
                f"{row['p_mw']:+.4f} MW {row['direction']}",
                f"{row['q_mvar']:+.4f} MVAr",
                f"{row['loss_kw']:.3f} kW",
                f"{row['loading']:5.1f} %",
            ]
            for ci, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if ci == 5:
                    # Tingkatan warna sama dengan warna kabel di canvas.
                    loading = row["loading"]
                    if loading < 50:
                        c = QColor(80, 220, 100)
                    elif loading < 80:
                        c = QColor(240, 220, 60)
                    elif loading < 100:
                        c = QColor(240, 150, 60)
                    else:
                        c = QColor(230, 80, 80)
                    item.setForeground(c)
                self.results_table.setItem(ri, ci, item)

    def _render_bus_rows(self) -> None:
        """Mengisi tab Tegangan Bus dari hasil power flow terakhir."""
        rows = []
        for nt, res in state.last_results.get("nodes", {}).items():
            nd = state.nodes.get(nt, {})
            if nd.get("kind") != "bus" or "vm_pu" not in res:
                continue
            rows.append((nd.get("label", "?"), float(nd.get("vn_kv", 0.0)),
                         res["vm_pu"], res.get("va_degree", 0.0)))
        self.bus_table.setRowCount(len(rows))
        for ri, (label, vn, vm, va) in enumerate(rows):
            if 0.95 <= vm <= 1.05:
                status, col = "Normal", QColor(80, 220, 100)
            elif 0.90 <= vm <= 1.10:
                status, col = "Waspada", QColor(240, 200, 60)
            else:
                status, col = "Kritis", QColor(230, 80, 80)
            vals = [label, f"{vn:.2f}", f"{vm:.4f}", f"{va:+.2f}", status]
            for ci, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if ci >= 2:
                    item.setForeground(col)
                self.bus_table.setItem(ri, ci, item)

    def _update_stat_chips(self, net, rows) -> None:
        """Memperbarui kartu statistik dari hasil run terakhir."""
        ll = net.res_line["pl_mw"].sum() * 1000 if len(net.line) else 0
        tl = net.res_trafo["pl_mw"].sum() * 1000 if len(net.trafo) else 0
        mv = net.res_bus["vm_pu"].min() if len(net.res_bus) else 0
        ml = max((r["loading"] for r in rows), default=0)
        self.chip_status.set_value("Konvergen", GREEN)
        self.chip_loss.set_value(f"{ll + tl:.3f} kW")
        v_col = GREEN if 0.95 <= mv <= 1.05 else (WARN if 0.90 <= mv else RED)
        self.chip_vmin.set_value(f"{mv:.4f} pu", v_col)
        l_col = GREEN if ml < 50 else (WARN if ml < 80 else RED)
        self.chip_loading.set_value(f"{ml:.1f} %", l_col)

    def _summary(self, net, rows) -> str:
        """Membuat ringkasan total jaringan dari hasil pandapower."""
        # Ringkasan memakai tabel pandapower asli untuk angka total jaringan.
        ll = net.res_line["pl_mw"].sum() * 1000 if len(net.line) else 0
        tl = net.res_trafo["pl_mw"].sum() * 1000 if len(net.trafo) else 0
        lp = net.load["p_mw"].sum() if len(net.load) else 0
        # Generator PQ ada di tabel sgen, generator PV ada di tabel gen.
        gp = net.sgen["p_mw"].sum() if len(net.sgen) else 0
        gp += net.res_gen["p_mw"].sum() if len(net.gen) else 0
        ep = net.res_ext_grid["p_mw"].sum() if len(net.res_ext_grid) else 0
        mv = net.res_bus["vm_pu"].min() if len(net.res_bus) else 0
        ml = max((r["loading"] for r in rows), default=0)
        return "\n".join([
            f"  Buses       : {len(net.bus)}",
            f"  Lines       : {len(net.line)}",
            f"  Trafos      : {len(net.trafo)}",
            f"  Loads       : {len(net.load)}",
            f"  Load P      : {lp:.4f} MW",
            f"  SGen P      : {gp:.4f} MW",
            f"  Grid P      : {ep:.4f} MW",
            f"  Loss Line   : {ll:.3f} kW",
            f"  Loss Trafo  : {tl:.3f} kW",
            f"  V min       : {mv:.4f} pu",
            f"  Max loading : {ml:.1f} %",
        ])

    # ── project I/O ───────────────────────────────────────────────────

    def new_project(self) -> None:
        """Memulai project kosong setelah konfirmasi jika canvas tidak kosong."""
        if state.nodes and not self._confirm("Project Baru", "Semua komponen akan dihapus?"):
            return
        self._clear_canvas()

    def _clear_canvas(self) -> None:
        """Mengosongkan model dan scene tanpa menghapus undo stack."""
        if state.nodes:
            # Clear canvas tetap bisa di-undo karena snapshot disimpan sebelum reset.
            qt_model.push_undo_snapshot()
        qt_model.clear_model(clear_undo_stack=False)
        self.canvas_scene.rebuild_from_state()
        self.clear_results()
        self.properties.show_empty()
        self.set_status("Canvas dikosongkan.")

    def request_clear_canvas(self) -> None:
        """Meminta konfirmasi user sebelum canvas dikosongkan."""
        if state.nodes and not self._confirm("Kosongkan Canvas", "Semua komponen dihapus?"):
            return
        self._clear_canvas()

    def load_template(self) -> None:
        """Memuat template jaringan contoh ke canvas."""
        # Kalau canvas berisi model, user diminta konfirmasi sebelum diganti.
        if state.nodes and not self._confirm("Muat Template", "Ganti dengan template?"):
            return
        # Snapshot disimpan agar template bisa di-undo.
        if state.nodes:
            qt_model.push_undo_snapshot()
        # State dikosongkan, tetapi undo stack tidak dihapus.
        qt_model.clear_model(clear_undo_stack=False)
        # suspend_undo membuat template dianggap satu operasi, bukan banyak node/link.
        with qt_model.suspend_undo():
            # _populate_demo mengisi bus, trafo, line, dan load contoh.
            self._populate_demo()
        # Scene Qt dibangun ulang dari state template.
        self.canvas_scene.rebuild_from_state()
        # Kamera di-fit agar semua komponen template langsung terlihat.
        self.canvas_view.fit_all()
        # Template baru belum punya hasil power flow.
        self.clear_results()
        self.set_status("Template dimuat.")

    def populate_demo_model(self) -> None:
        """Mengisi model demo untuk test tanpa dialog UI."""
        qt_model.clear_model(clear_undo_stack=False)
        with qt_model.suspend_undo():
            self._populate_demo()

    def _populate_demo(self):
        """Membuat jaringan contoh berisi slack bus, trafo, feeder, dan beban."""
        # Template sengaja memakai beban kecil agar jaringan 0.4 kV contoh konvergen.
        b0 = qt_model.create_node("bus",  (60,300),  label="Ext Grid", vn_kv=10.0, is_slack=True)
        t0 = qt_model.create_node("trafo",(310,300), label="Trafo 10/0.4",
                                   sn_mva=0.25, vn_hv_kv=10.0, vn_lv_kv=0.4,
                                   vk_percent=4.0, vkr_percent=1.2)
        b1 = qt_model.create_node("bus",  (590,300), label="Bus 1", vn_kv=0.4)
        b2 = qt_model.create_node("bus",  (860, 80), label="Bus 2", vn_kv=0.4)
        b3 = qt_model.create_node("bus",  (860,230), label="Bus 3", vn_kv=0.4)
        b4 = qt_model.create_node("bus",  (860,380), label="Bus 4", vn_kv=0.4)
        b5 = qt_model.create_node("bus",  (860,530), label="Bus 5", vn_kv=0.4)
        qt_model.add_link(state.nodes[b0]["out_attr"], state.nodes[t0]["hv_pin"])
        qt_model.add_link(state.nodes[t0]["lv_pin"],   state.nodes[b1]["in_attr"])
        lv = {"length_km":0.05, "r_ohm_per_km":0.225,
              "x_ohm_per_km":0.08, "c_nf_per_km":264.0, "max_i_ka":0.242}
        for i, (f, t) in enumerate([(b1,b2),(b2,b3),(b3,b4),(b4,b5)], 1):
            qt_model.add_link(state.nodes[f]["out_attr"], state.nodes[t]["in_attr"],
                              {**lv, "label": f"Line {i}"})
        for i, (bus, pos) in enumerate(
            [(b2,(1210,80)),(b3,(1210,230)),(b4,(1210,380)),(b5,(1210,530))], 1):
            ld = qt_model.create_node("load", pos, label=f"Load {i}", p_mw=0.03, q_mvar=0.01)
            qt_model.add_link(state.nodes[bus]["out_attr"], state.nodes[ld]["pin"])

    def save_project(self) -> None:
        """Membuka dialog simpan dan menulis project ke JSON."""
        # Dialog save memakai path default dari qt_model.PROJECT_PATH.
        p, _ = QFileDialog.getSaveFileName(self, "Simpan", str(qt_model.PROJECT_PATH), "JSON (*.json)")
        # Jika user Cancel, tidak ada file yang perlu ditulis.
        if not p: return
        try:
            # qt_model.save_project menyimpan node, link, line_data, dan waypoint.
            # Path(p) mengubah string dari dialog menjadi object Path.
            qt_model.save_project(Path(p))
        except OSError as e:
            # OSError menangkap gagal tulis, misalnya permission/path tidak valid.
            self.set_status(f"Gagal: {e}", error=True); return
        # Jika sukses, status cukup menampilkan nama file.
        self.set_status(f"Disimpan: {Path(p).name}")

    def load_project(self) -> None:
        """Membuka dialog file dan memuat project JSON ke canvas."""
        # Dialog ini memilih JSON project yang akan dimuat.
        p, _ = QFileDialog.getOpenFileName(self, "Muat", str(qt_model.PROJECT_PATH), "JSON (*.json)")
        # Jika user Cancel, tidak ada perubahan pada canvas.
        if not p: return
        # Snapshot model lama disimpan agar load bisa di-undo.
        if state.nodes:
            qt_model.push_undo_snapshot()
        try:
            # Load memakai validasi qt_model agar file rusak tidak merusak state aktif.
            with qt_model.suspend_undo():
                # qt_model.load_project mengembalikan None jika valid, atau string error.
                problem = qt_model.load_project(Path(p))
        except (OSError, ValueError) as e:
            # OSError untuk gagal baca, ValueError untuk JSON yang tidak bisa diparse.
            self.set_status(f"Gagal: {e}", error=True); return
        # problem adalah pesan validasi payload, bukan exception Python.
        if problem:
            self.set_status(f"Tidak valid: {problem}", error=True); return
        # Setelah state baru masuk, scene Qt harus dibuat ulang.
        self.canvas_scene.rebuild_from_state()
        # Kamera langsung menampilkan seluruh project.
        self.canvas_view.fit_all()
        # Hasil lama dari project sebelumnya dibuang.
        self.clear_results()
        # Panel kanan kembali kosong sampai user memilih node/link.
        self.properties.show_empty()
        # Status sukses menampilkan nama file yang berhasil dimuat.
        self.set_status(f"Dimuat: {Path(p).name}")

    def export_results(self) -> None:
        """Mengekspor hasil power flow terakhir ke folder exports."""
        # Export hanya tersedia setelah run_power_flow mengisi state.last_results.
        if not qt_model.export_results():
            self.set_status("Belum ada hasil.", error=True); return
        self.set_status("Diekspor ke exports/")

    def export_pandapower_json(self) -> None:
        """Mengekspor model aktif sebagai file JSON pandapower (pp.to_json)."""
        default_path = qt_model.EXPORT_DIR / "pandapower_net.json"
        path, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Network Pandapower", str(default_path),
            "Pandapower JSON (*.json);;All Files (*)")
        if not path:
            return
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        problem = engine.export_pandapower_json(Path(path))
        if problem:
            self.set_status(problem, error=True)
            return
        self.set_status(f"Network pandapower disimpan: {Path(path).name}")

    def export_report(self) -> None:
        """Mengekspor laporan HTML lengkap dari hasil power flow terakhir."""
        problem = report_export.validate_report_ready()
        if problem:
            self.set_status(problem, error=True)
            return
        default_path = qt_model.EXPORT_DIR / "simulation_report.html"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Laporan Simulasi", str(default_path),
            "HTML Files (*.html);;All Files (*)")
        if not path:
            return
        report_path = Path(path)
        diagram_path = report_path.with_name(f"{report_path.stem}_diagram.png")
        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            if not self._render_canvas_image(diagram_path):
                self.set_status("Canvas kosong.", error=True)
                return
            report_export.write_report(report_path, diagram_path.name, project_name=report_path.stem)
        except OSError as exc:
            self.set_status(f"Gagal export laporan: {exc}", error=True)
            return
        self.set_status(f"Laporan disimpan: {report_path.name}")

    # ── status ────────────────────────────────────────────────────────

    def set_status(self, text: str, error: bool = False, warn: bool = False) -> None:
        """Menampilkan pesan status di status bar dan toast canvas."""
        # Status bar memberi jejak tetap, toast memberi feedback singkat di dekat canvas.
        if hasattr(self, "status_label"):
            self.status_label.setText(text)
        if hasattr(self, "active_toast") and self.active_toast:
            try:
                self.active_toast.close_and_destroy()
            except Exception:
                pass
            self.active_toast = None

        if hasattr(self, "canvas_view") and self.canvas_view:
            level = "error" if error else "warn" if warn else "success"
            self.active_toast = Toast(self.canvas_view, text, level)

    # ── export ────────────────────────────────────────────────────────

    def export_canvas_image(self) -> None:
        """Menyimpan gambar canvas saat ini ke file PNG."""
        # Buka dialog save file agar user memilih lokasi dan nama PNG.
        path, _ = QFileDialog.getSaveFileName(
            # self berarti dialog ini dimiliki oleh window utama.
            self, "Export Gambar Canvas", "grid_diagram.png",
            # Filter ini membatasi pilihan utama ke file PNG.
            "PNG Files (*.png);;All Files (*)")
        # Jika user menekan Cancel, path kosong dan fungsi berhenti.
        if not path:
            return
        if not self._render_canvas_image(Path(path)):
            self.set_status("Canvas kosong.", error=True)
            return
        # Status sukses menampilkan nama file, bukan path penuh, agar ringkas.
        self.set_status(f"Disimpan: {Path(path).name}")

    def _render_canvas_image(self, path: Path) -> bool:
        """Merender scene aktif ke PNG dan mengembalikan False jika canvas kosong."""
        # Selection dibersihkan supaya border seleksi tidak ikut tersimpan di gambar.
        self.canvas_scene.clearSelection()
        # Export canvas memakai render scene langsung agar output sama dengan yang terlihat.
        # itemsBoundingRect mengambil area semua item di scene.
        # adjusted memberi margin 50 px supaya node/kabel tidak mepet tepi gambar.
        rect = self.canvas_scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        # Kalau rect kosong berarti tidak ada item yang bisa diekspor.
        if rect.isEmpty():
            return False
        # QImage diimport lokal karena hanya dipakai saat export PNG.
        from PySide6.QtGui import QImage
        # scale 2.0 membuat gambar 2x lebih tajam dari ukuran scene asli.
        scale = 2.0
        # Lebar gambar adalah lebar area scene dikali scale.
        w = int(rect.width() * scale)
        # Tinggi gambar adalah tinggi area scene dikali scale.
        h = int(rect.height() * scale)
        # QImage adalah kanvas bitmap tempat scene Qt akan digambar.
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        # Background diisi warna gelap agar transparansi tidak menjadi hitam acak.
        image.fill(QColor(22, 22, 22))
        # QPainter diimport lokal karena hanya dibutuhkan untuk menggambar ke QImage.
        from PySide6.QtGui import QPainter as _P
        # Painter diarahkan ke image, bukan ke layar.
        painter = _P(image)
        # Antialiasing membuat garis dan rounded corner lebih halus.
        painter.setRenderHint(_P.RenderHint.Antialiasing)
        # QRectF diimport lokal untuk membuat target rectangle render.
        from PySide6.QtCore import QRectF as _RF
        # render menggambar isi scene dari rect sumber ke area gambar ukuran w x h.
        self.canvas_scene.render(painter, _RF(0, 0, w, h), rect)
        # Painter harus ditutup sebelum image disimpan supaya buffer selesai ditulis.
        painter.end()
        # Simpan bitmap ke path yang dipilih user.
        return image.save(str(path))

    def update_zoom_label(self, z: float) -> None:
        self.zoom_label.setText(f"{int(round(z * 100))}%")

    def _confirm(self, title, msg) -> bool:
        return QMessageBox.question(self, title, msg) == QMessageBox.StandardButton.Yes


# ═══════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_dark_palette(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
