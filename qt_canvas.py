"""Qt QGraphicsView canvas for the Grid Simulator.

Connection workflow (draw.io / flowchart style):
  1.  User hovers a node → port dots appear on the left/right edges.
  2.  Click + drag FROM a port dot → rubber-band polyline follows the cursor.
  3.  While dragging, valid target ports on other nodes glow green;
      invalid ones glow red.  Port labels disappear when already connected.
  4.  Release ON a valid port → connection is created (orthogonal wire).
      Release anywhere else → cancelled.
"""
from __future__ import annotations

from math import hypot

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
    QTransform,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
)

import canvas_logic
import qt_model
import state

# qt_canvas hanya mengurus QGraphicsItem/QGraphicsView; aturan model tetap di qt_model.
# state dipakai di sini karena Qt perlu membaca posisi, selection, link, dan waypoint real-time.


# ═══════════════════════════════════════════════════════════════════════════
#  Visual constants
# ═══════════════════════════════════════════════════════════════════════════

NODE_SIZES = {
    "bus":   (170.0, 118.0),
    "gen":   (160.0,  98.0),
    "trafo": (200.0, 116.0),
    "shunt": (170.0,  98.0),
    "load":  (170.0,  98.0),
}

NODE_COLORS = {
    "bus": {
        "title":        QColor(20, 60, 100),
        "title_active": QColor(30, 80, 130),
        "bg":           QColor(20, 25, 35),
        "border":       QColor(100, 190, 255),
    },
    "bus_slack": {
        "title":        QColor(180, 110, 20),
        "title_active": QColor(210, 130, 30),
        "bg":           QColor(35, 30, 20),
        "border":       QColor(255, 180, 50),
    },
    "gen": {
        "title":        QColor(20, 80, 45),
        "title_active": QColor(30, 110, 60),
        "bg":           QColor(20, 30, 25),
        "border":       QColor(80, 220, 120),
    },
    "trafo": {
        "title":        QColor(100, 55, 20),
        "title_active": QColor(130, 75, 30),
        "bg":           QColor(35, 30, 25),
        "border":       QColor(230, 140, 70),
    },
    "load": {
        "title":        QColor(100, 30, 30),
        "title_active": QColor(130, 45, 45),
        "bg":           QColor(35, 25, 25),
        "border":       QColor(230, 100, 100),
    },
    "shunt": {
        "title":        QColor(70, 30, 100),
        "title_active": QColor(90, 45, 130),
        "bg":           QColor(30, 25, 35),
        "border":       QColor(180, 100, 255),
    },
}

TEXT_COLOR         = QColor(222, 222, 222)
MUTED_TEXT         = QColor(140, 140, 140)
GRID_MINOR         = QColor(32, 36, 34)
GRID_MAJOR         = QColor(50, 56, 52)
CANVAS_BG          = QColor(22, 22, 22)

PORT_COLOR         = QColor(255, 230, 70)
PORT_CONNECTED     = QColor(100, 180, 255)   # port already in use
PORT_HOVER_VALID   = QColor(60, 220, 100)
PORT_HOVER_INVALID = QColor(220, 60, 60)
PORT_PENDING       = QColor(255, 160, 30)

LINK_COLOR         = QColor(180, 190, 195)
SELECTED_LINK      = QColor(255, 220, 80)
RUBBER_COLOR       = QColor(100, 180, 255, 190)


# ═══════════════════════════════════════════════════════════════════════════
#  Pure helpers (no Qt parents)
# ═══════════════════════════════════════════════════════════════════════════

def node_color_key(node_tag) -> str:
    nd = state.nodes.get(node_tag, {})
    if nd.get("kind") == "bus" and nd.get("is_slack"):
        return "bus_slack"
    return nd.get("kind", "bus")


def node_title(node_tag) -> str:
    nd = state.nodes.get(node_tag, {})
    kind = nd.get("kind", "")
    label = nd.get("label", "")
    if kind == "bus":
        return f"[SLACK] {label}" if nd.get("is_slack") else f"[BUS] {label}"
    if kind == "gen":
        return f"(G) {label}"
    if kind == "trafo":
        return f"[T] {label}"
    if kind == "load":
        return f"(L) {label}"
    if kind == "shunt":
        return f"(C) {label}"
    return label


def node_lines(node_tag) -> list[str]:
    nd = state.nodes.get(node_tag, {})
    kind = nd.get("kind")
    result = state.last_results.get("nodes", {}).get(node_tag, {})
    if kind == "bus":
        out = [f"Slack {nd['vn_kv']} kV" if nd.get("is_slack") else f"Vn {nd['vn_kv']} kV"]
        if "vm_pu" in result:
            out.append(f"V {result['vm_pu']:.4f} pu")
            out.append(f"∠ {result.get('va_degree', 0.0):.1f}°")
        else:
            out += ["V  —", "∠  —"]
        return out
    if kind == "gen":
        return ["GEN", f"P {nd['p_mw']} MW", f"Q {nd['q_mvar']} MVAr"]
    if kind == "load":
        return ["LOAD", f"P {nd['p_mw']} MW", f"Q {nd['q_mvar']} MVAr"]
    if kind == "shunt":
        return ["SHUNT", f"P {nd.get('p_mw', 0.0)} MW", f"Q {nd['q_mvar']} MVAr"]
    if kind == "trafo":
        return [f"HV {nd['vn_hv_kv']} kV", f"S {nd['sn_mva']} MVA", f"LV {nd['vn_lv_kv']} kV"]
    return []


def port_layout(node_tag) -> list[tuple[str, str, QPointF]]:
    """Return [(attr_key, label, local_pos), ...]"""
    nd = state.nodes.get(node_tag, {})
    kind = nd.get("kind")
    w, h = NODE_SIZES.get(kind, (170.0, 100.0))
    my = 65.0
    # Posisi port harus sejalan dengan role koneksi di qt_model.validate_link().
    if kind == "bus":
        return [
            ("out_attr", "OUT", QPointF(w, my)),
            ("in_attr",  "IN",  QPointF(0.0, my)),
        ]
    if kind == "gen":
        return [("pin", "GEN", QPointF(w, my))]
    if kind in ("load", "shunt"):
        return [("pin", kind.upper(), QPointF(0.0, my))]
    if kind == "trafo":
        return [
            ("hv_pin", "HV", QPointF(0.0, my)),
            ("lv_pin", "LV", QPointF(w, my)),
        ]
    return []


def _port_is_connected(node_tag, attr_key) -> bool:
    """True if the port already has at least one link."""
    nd = state.nodes.get(node_tag, {})
    attr_tag = nd.get(attr_key)
    if attr_tag is None:
        return False
    for fa, ta in state.links.values():
        if fa == attr_tag or ta == attr_tag:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  Orthogonal edge path builder
# ═══════════════════════════════════════════════════════════════════════════

def _ortho_path(start: QPointF, end: QPointF) -> QPainterPath:
    """Build an orthogonal (90° bends) wire path between two port positions."""
    path = QPainterPath(start)
    dx = end.x() - start.x()
    dy = end.y() - start.y()

    if abs(dx) < 1.0:
        # Straight vertical
        path.lineTo(end)
    elif abs(dy) < 1.0:
        # Straight horizontal
        path.lineTo(end)
    else:
        # Three-segment orthogonal path:  horizontal → vertical → horizontal
        mid_x = start.x() + dx * 0.5
        path.lineTo(QPointF(mid_x, start.y()))
        path.lineTo(QPointF(mid_x, end.y()))
        path.lineTo(end)
    return path


def _rubber_band_path(start: QPointF, end: QPointF) -> QPainterPath:
    """Dashed orthogonal rubber band while dragging."""
    return _ortho_path(start, end)


# ═══════════════════════════════════════════════════════════════════════════
#  RubberBandItem – temporary drag line
# ═══════════════════════════════════════════════════════════════════════════

class RubberBandItem(QGraphicsPathItem):
    def __init__(self):
        super().__init__()
        pen = QPen(RUBBER_COLOR, 2.0, Qt.PenStyle.DashLine)
        pen.setDashPattern([6, 4])
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self.setZValue(1000)
        self.hide()

    def show_path(self, start: QPointF, end: QPointF) -> None:
        self.setPath(_rubber_band_path(start, end))
        self.show()

    def hide_path(self) -> None:
        self.setPath(QPainterPath())
        self.hide()


# ═══════════════════════════════════════════════════════════════════════════
#  Orthogonal auto-routing helpers
# ═══════════════════════════════════════════════════════════════════════════

def auto_ortho_waypoints(sx: float, sy: float, ex: float, ey: float):
    """Generate default H-V-H waypoints between two port positions."""
    mid_x = round((sx + ex) / 2.0 / 12.0) * 12.0
    return [(mid_x, sy), (mid_x, ey)]


def _seg_dist(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Distance from point *p* to segment *a*→*b*."""
    ab_x, ab_y = b.x() - a.x(), b.y() - a.y()
    ap_x, ap_y = p.x() - a.x(), p.y() - a.y()
    ab_sq = ab_x ** 2 + ab_y ** 2
    if ab_sq < 1e-6:
        return hypot(ap_x, ap_y)
    t = max(0.0, min(1.0, (ap_x * ab_x + ap_y * ab_y) / ab_sq))
    dx = a.x() + ab_x * t - p.x()
    dy = a.y() + ab_y * t - p.y()
    return hypot(dx, dy)


# ═══════════════════════════════════════════════════════════════════════════
#  SegmentHandleItem – drag handle at midpoint of an orthogonal segment
# ═══════════════════════════════════════════════════════════════════════════

class SegmentHandleItem(QGraphicsItem):
    """Handle at the midpoint of an internal edge segment.

    • Horizontal segment → drag **up / down** (changes Y of both endpoints).
    • Vertical   segment → drag **left / right** (changes X of both endpoints).
    """

    SIZE = 5.0

    def __init__(self, edge_item, wp_left: int, wp_right: int):
        super().__init__()
        self.edge = edge_item
        self.wp_left = wp_left        # index in link_waypoints list
        self.wp_right = wp_right
        self.setZValue(100)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self._hovered = False
        self._is_horizontal = True
        self.reposition()

    # ── helpers ────────────────────────────────────────────────────────

    def _wp_pair(self):
        wps = state.link_waypoints.get(self.edge.link_tag, [])
        if self.wp_left < len(wps) and self.wp_right < len(wps):
            return wps[self.wp_left], wps[self.wp_right]
        return None, None

    def reposition(self):
        p1, p2 = self._wp_pair()
        if p1 is None:
            return
        self.setPos((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        dx, dy = abs(p1[0] - p2[0]), abs(p1[1] - p2[1])
        self._is_horizontal = (dy < dx) if max(dx, dy) > 1.0 else True

    # ── QGraphicsItem overrides ───────────────────────────────────────

    def boundingRect(self) -> QRectF:
        s = self.SIZE + 1
        return QRectF(-s, -s, 2 * s, 2 * s)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = QColor(100, 210, 255) if self._hovered else QColor(70, 160, 220)
        painter.setBrush(QBrush(c))
        painter.setPen(QPen(QColor(20, 24, 28), 1.0))
        s = self.SIZE
        if self._is_horizontal:
            painter.drawRect(QRectF(-s, -s * 0.55, 2 * s, 2 * s * 0.55))
        else:
            painter.drawRect(QRectF(-s * 0.55, -s, 2 * s * 0.55, 2 * s))

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            wps = state.link_waypoints.get(self.edge.link_tag, [])
            if self.wp_left >= len(wps) or self.wp_right >= len(wps):
                return value
            p1, p2 = wps[self.wp_left], wps[self.wp_right]
            # Handle mengubah waypoint langsung di state agar jalur kabel tersimpan di project.
            if self._is_horizontal:
                new_y = round(value.y() / 12.0) * 12.0
                mx = (p1[0] + p2[0]) / 2.0
                wps[self.wp_left]  = (p1[0], new_y)
                wps[self.wp_right] = (p2[0], new_y)
                state.mark_model_dirty()
                self.edge.update_path_only()
                return QPointF(mx, new_y)
            else:
                new_x = round(value.x() / 12.0) * 12.0
                my = (p1[1] + p2[1]) / 2.0
                wps[self.wp_left]  = (new_x, p1[1])
                wps[self.wp_right] = (new_x, p2[1])
                state.mark_model_dirty()
                self.edge.update_path_only()
                return QPointF(new_x, my)
        return super().itemChange(change, value)


# ═══════════════════════════════════════════════════════════════════════════
#  EdgeItem – orthogonal wire with segment handles
# ═══════════════════════════════════════════════════════════════════════════

class EdgeItem(QGraphicsPathItem):
    """Orthogonal wire connecting two ports via waypoints."""

    def __init__(self, link_tag, scene_ref: "GridScene"):
        super().__init__()
        self.link_tag = link_tag
        self.scene_ref = scene_ref
        self.handles: list[SegmentHandleItem] = []
        self.setZValue(-10)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self._ensure_waypoints()
        self.update_path()

    # ── waypoint helpers ──────────────────────────────────────────────

    def _port_positions(self):
        fa, ta = state.links.get(self.link_tag, (None, None))
        s = self.scene_ref.port_scene_pos(fa)
        e = self.scene_ref.port_scene_pos(ta)
        return s, e

    def _ensure_waypoints(self):
        lt = self.link_tag
        if lt in state.link_waypoints and state.link_waypoints[lt]:
            return
        s, e = self._port_positions()
        if s is None or e is None:
            return
        # Waypoint default dibuat sekali supaya user bisa mengedit jalur tanpa di-reset.
        state.link_waypoints[lt] = auto_ortho_waypoints(
            s.x(), s.y(), e.x(), e.y()
        )

    def maintain_port_alignment(self):
        """Keep wp[0].y == start.y and wp[-1].y == end.y so that the first
        and last segments stay perfectly horizontal."""
        lt = self.link_tag
        wps = state.link_waypoints.get(lt)
        if not wps or len(wps) < 2:
            return
        s, e = self._port_positions()
        if s is None or e is None:
            return
        # Saat node digeser, ujung kabel ikut port tetapi lekukan tengah tetap dipertahankan.
        wps[0]  = (wps[0][0],  s.y())
        wps[-1] = (wps[-1][0], e.y())

    def full_points(self):
        """Return [start, *waypoints, end] as list of (x, y) tuples."""
        s, e = self._port_positions()
        if s is None or e is None:
            return []
        pts = [(s.x(), s.y())]
        pts.extend(state.link_waypoints.get(self.link_tag, []))
        pts.append((e.x(), e.y()))
        return pts

    # ── path rendering ────────────────────────────────────────────────

    def update_path(self) -> None:
        self._ensure_waypoints()
        self.maintain_port_alignment()
        pts = self.full_points()
        if len(pts) < 2:
            return
        path = QPainterPath(QPointF(pts[0][0], pts[0][1]))
        for px, py in pts[1:]:
            path.lineTo(QPointF(px, py))
        self.setPath(path)
        self._apply_style()

    def update_path_only(self) -> None:
        """Lightweight path rebuild (no style recalc) – called during drag."""
        pts = self.full_points()
        if len(pts) < 2:
            return
        path = QPainterPath(QPointF(pts[0][0], pts[0][1]))
        for px, py in pts[1:]:
            path.lineTo(QPointF(px, py))
        self.setPath(path)

    def _apply_style(self) -> None:
        result = state.last_results.get("links", {}).get(self.link_tag, {})
        loading = result.get("loading_percent")
        # Warna link memakai hasil power flow agar overload terlihat langsung di canvas.
        if loading is None:
            color = SELECTED_LINK if self.isSelected() else LINK_COLOR
        elif loading < 50:
            color = QColor(80, 220, 100)
        elif loading < 80:
            color = QColor(240, 220, 60)
        elif loading < 100:
            color = QColor(240, 150, 60)
        else:
            color = QColor(230, 80, 80)
        w = 3.0 if self.isSelected() else 2.0
        self.setPen(QPen(color, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                         Qt.PenJoinStyle.RoundJoin))

    # ── segment handles ───────────────────────────────────────────────

    def update_handles(self) -> None:
        for h in self.handles:
            if h.scene():
                self.scene().removeItem(h)
        self.handles.clear()

        if not self.isSelected():
            return

        wps = state.link_waypoints.get(self.link_tag, [])
        N = len(wps)
        if N < 2:
            return

        # Handle hanya muncul saat link dipilih supaya canvas tetap bersih untuk laporan.
        # Internal segments: indices j = 1 .. N-1 in full-points numbering,
        # which maps to waypoints[j-1] → waypoints[j].
        for j in range(1, N):
            wp_l, wp_r = j - 1, j
            p1, p2 = wps[wp_l], wps[wp_r]
            # Skip zero-length segments
            if abs(p1[0] - p2[0]) < 2.0 and abs(p1[1] - p2[1]) < 2.0:
                continue
            # Skip horizontal segments adjacent to ports (would break alignment)
            is_horiz = abs(p1[1] - p2[1]) < abs(p1[0] - p2[0])
            if is_horiz and (j == 1 or j == N - 1):
                continue
            h = SegmentHandleItem(self, wp_l, wp_r)
            self.scene().addItem(h)
            self.handles.append(h)

    # ── double-click: toggle extra bends ──────────────────────────────

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_bends()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _toggle_bends(self) -> None:
        """Toggle between simple 2-waypoint route and 4-waypoint route
        with 3 draggable handles."""
        lt = self.link_tag
        wps = state.link_waypoints.get(lt, [])
        s, e = self._port_positions()
        if s is None or e is None:
            return

        if len(wps) <= 2:
            # Double-click memberi rute ekstra untuk menghindari node yang menutupi kabel.
            # 2 wp → 4 wp  (V segment becomes V-H-V)
            if len(wps) < 2:
                return
            mx = wps[0][0]
            mid_y = round(((s.y() + e.y()) / 2.0) / 12.0) * 12.0
            off_x = round((mx + 48.0) / 12.0) * 12.0
            state.link_waypoints[lt] = [
                (mx, s.y()),
                (mx, mid_y),
                (off_x, mid_y),
                (off_x, e.y()),
            ]
        else:
            # Rute kompleks bisa dikembalikan agar diagram mudah dirapikan.
            # Complex → reset to simple 2 wp
            state.link_waypoints[lt] = auto_ortho_waypoints(
                s.x(), s.y(), e.x(), e.y()
            )

        state.mark_model_dirty()
        state.clear_results()
        self.update_path()
        self.update_handles()

    # ── hit testing ───────────────────────────────────────────────────

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(10.0)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.path())

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._apply_style()
            self.update_handles()
        return super().itemChange(change, value)

# ═══════════════════════════════════════════════════════════════════════════
#  NodeItem
# ═══════════════════════════════════════════════════════════════════════════

PORT_RADIUS     = 6.0
PORT_HIT_RADIUS = 13.0


class NodeItem(QGraphicsObject):
    """Draggable node card. Ports are drawn on paint; hit-testing delegates
    to the scene-level drag system.
    """

    def __init__(self, node_tag, scene_ref: "GridScene"):
        super().__init__()
        self.node_tag = node_tag
        self.scene_ref = scene_ref
        nd = state.nodes[node_tag]
        # Posisi scene adalah world_pos model; zoom/pan murni transform view.
        self.width, self.height = NODE_SIZES.get(nd.get("kind"), (170.0, 100.0))
        self.setPos(QPointF(*nd.get("world_pos", (0.0, 0.0))))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        self._hovered_port: str | None = None   # attr_key being hovered
        self._port_valid: bool = True

    # ── geometry ──────────────────────────────────────────────────────

    def boundingRect(self) -> QRectF:
        # Extend horizontally to accommodate port labels drawn outside
        return QRectF(-70.0, -14.0, self.width + 140.0, self.height + 28.0)

    # ── paint ─────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option, widget=None) -> None:
        nd = state.nodes.get(self.node_tag, {})
        colors = NODE_COLORS[node_color_key(self.node_tag)]
        body   = QRectF(0, 0, self.width, self.height)
        header = QRectF(0, 0, self.width, 28.0)
        border = colors["border"]
        if self.isSelected():
            border = QColor(255, 230, 80)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Body
        painter.setPen(QPen(border, 2.4 if self.isSelected() else 1.6))
        painter.setBrush(QBrush(colors["bg"]))
        painter.drawRoundedRect(body, 6, 6)

        # Title bar
        painter.setPen(Qt.PenStyle.NoPen)
        tc = colors["title_active"] if self.isSelected() else colors["title"]
        painter.setBrush(QBrush(tc))
        painter.drawRoundedRect(header, 6, 6)
        painter.drawRect(QRectF(0, 18, self.width, 10))

        # Title text
        painter.setPen(TEXT_COLOR)
        painter.drawText(QRectF(10, 5, self.width - 20, 20),
                         Qt.AlignmentFlag.AlignVCenter, node_title(self.node_tag))

        # Body text
        painter.setPen(MUTED_TEXT)
        y = 46.0
        for line in node_lines(self.node_tag):
            painter.drawText(QPointF(12, y), line)
            y += 18.0

        # ── ports ─────────────────────────────────────────────────────
        pending = self.scene_ref.pending_attr
        for attr_key, label, local in port_layout(self.node_tag):
            attr_tag = nd.get(attr_key)
            connected = _port_is_connected(self.node_tag, attr_key)
            is_pending = (attr_tag == pending)
            is_hovered = (attr_key == self._hovered_port)

            # Status port dihitung di paint agar feedback drag selalu mengikuti state terbaru.
            # Decide dot colour / radius
            if is_pending:
                dot_col = PORT_PENDING
                r = PORT_RADIUS + 3.0
            elif is_hovered and pending is not None:
                dot_col = PORT_HOVER_VALID if self._port_valid else PORT_HOVER_INVALID
                r = PORT_RADIUS + 3.0
            elif connected:
                dot_col = PORT_CONNECTED
                r = PORT_RADIUS
            else:
                dot_col = PORT_COLOR
                r = PORT_RADIUS

            # Draw dot
            painter.setBrush(QBrush(dot_col))
            painter.setPen(QPen(QColor(20, 20, 18), 1.4))
            painter.drawEllipse(local, r, r)

            # Port label – HIDE when already connected, or for single-port components to keep the layout clean
            if not connected and nd.get("kind") not in ("gen", "load", "shunt"):
                label_w = painter.fontMetrics().horizontalAdvance(label)
                if local.x() <= 1:
                    tx = local.x() - label_w - 8.0
                else:
                    tx = local.x() + 8.0
                painter.setPen(QPen(MUTED_TEXT, 1.0))
                painter.drawText(QPointF(tx, local.y() + 4.0), label)

    # ── port hit-test ─────────────────────────────────────────────────

    def port_at(self, local_pos: QPointF):
        """Return (attr_key, attr_tag) or (None, None)."""
        nd = state.nodes.get(self.node_tag, {})
        for attr_key, _, loc in port_layout(self.node_tag):
            if hypot(local_pos.x() - loc.x(), local_pos.y() - loc.y()) <= PORT_HIT_RADIUS:
                return attr_key, nd.get(attr_key)
        return None, None

    def port_scene_pos(self, attr_tag) -> QPointF | None:
        nd = state.nodes.get(self.node_tag, {})
        for attr_key, _, loc in port_layout(self.node_tag):
            if nd.get(attr_key) == attr_tag:
                return self.mapToScene(loc)
        return None

    # ── hover ─────────────────────────────────────────────────────────

    def hoverMoveEvent(self, event) -> None:
        ak, at = self.port_at(event.pos())
        if ak != self._hovered_port:
            self._hovered_port = ak
            if ak is not None and self.scene_ref.pending_attr is not None:
                # qt_model.add_link(dry_run=True) dipakai sebagai sumber kebenaran validasi hover.
                _, msg = qt_model.add_link(self.scene_ref.pending_attr, at, dry_run=True)
                self._port_valid = (msg == "ok")
            else:
                self._port_valid = True
            self.update()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        if self._hovered_port is not None:
            self._hovered_port = None
            self.update()
        super().hoverLeaveEvent(event)

    # ── movement / selection ──────────────────────────────────────────

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Drag node langsung menulis world_pos agar save/load dan engine memakai posisi sama.
            qt_model.set_node_world_pos(self.node_tag, (value.x(), value.y()))
            self.scene_ref.update_edges_for_node(self.node_tag)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)


# ═══════════════════════════════════════════════════════════════════════════
#  GridScene
# ═══════════════════════════════════════════════════════════════════════════

class GridScene(QGraphicsScene):
    selectionModelChanged = Signal(object, object)
    statusChanged         = Signal(str, bool)
    modelChanged          = Signal()

    def __init__(self):
        super().__init__()
        self.node_items: dict = {}
        self.edge_items: dict = {}
        self.pending_attr = None
        self._rubber = RubberBandItem()
        self.addItem(self._rubber)
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.selectionChanged.connect(self._emit_selection)

    # ── background grid ───────────────────────────────────────────────

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, CANVAS_BG)
        minor, major = 24, 120
        left = int(rect.left()) - int(rect.left()) % minor
        top  = int(rect.top())  - int(rect.top())  % minor
        painter.setPen(QPen(GRID_MINOR, 0))
        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom()); x += minor
        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y); y += minor
        painter.setPen(QPen(GRID_MAJOR, 0))
        x = int(rect.left()) - int(rect.left()) % major
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom()); x += major
        y = int(rect.top()) - int(rect.top()) % major
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y); y += major

    # ── item management ───────────────────────────────────────────────

    def add_node_item(self, node_tag):
        """Membuat item visual untuk node yang sudah ada di state."""
        # Scene membuat item Qt dari node yang sudah dibuat di qt_model/state.
        item = NodeItem(node_tag, self)
        self.node_items[node_tag] = item
        self.addItem(item)
        self.clearSelection()
        item.setSelected(True)
        self.modelChanged.emit()
        return item

    def add_edge_item(self, link_tag):
        """Membuat item visual untuk koneksi yang sudah ada di state.links."""
        # EdgeItem membaca state.links dan state.link_waypoints untuk menggambar saluran.
        item = EdgeItem(link_tag, self)
        self.edge_items[link_tag] = item
        self.addItem(item)
        self.modelChanged.emit()
        return item

    def rebuild_from_state(self):
        """Membangun ulang seluruh scene dari state setelah load atau undo."""
        # Rebuild dipakai setelah undo/load karena tag Qt lama tidak boleh dipakai lagi.
        self.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self.pending_attr = None
        self._rubber = RubberBandItem()
        self.addItem(self._rubber)
        for nt in state.nodes:
            self.add_node_item(nt)
        self.clearSelection()
        for lt in state.links:
            self.add_edge_item(lt)
        self.modelChanged.emit()

    def remove_node_item(self, node_tag):
        item = self.node_items.pop(node_tag, None)
        if item:
            self.removeItem(item)
        for lt in list(self.edge_items):
            if lt not in state.links:
                self.remove_edge_item(lt)
        self.modelChanged.emit()

    def remove_edge_item(self, link_tag):
        item = self.edge_items.pop(link_tag, None)
        if item:
            for h in item.handles:
                if h.scene():
                    self.removeItem(h)
            item.handles.clear()
            self.removeItem(item)
        self.modelChanged.emit()

    def port_scene_pos(self, attr_tag):
        nt = state.attr_to_node.get(attr_tag)
        item = self.node_items.get(nt)
        return item.port_scene_pos(attr_tag) if item else None

    def handle_port_click(self, attr_tag: str) -> None:
        if self.pending_attr is None:
            start = self.port_scene_pos(attr_tag)
            if start is not None:
                self.begin_drag(attr_tag, start)
            return

        src = self.pending_attr
        self.cancel_drag()
        if attr_tag == src:
            return

        # Klik port kedua memakai qt_model.add_link supaya aturan elektro tetap satu sumber.
        link_tag, msg = qt_model.add_link(src, attr_tag)
        if link_tag is None:
            self.statusChanged.emit(msg, True)
        else:
            self.add_edge_item(link_tag)
            self.statusChanged.emit(msg, False)
        self.refresh_all()

    def update_edges_for_node(self, node_tag):
        """Memperbarui semua kabel yang terhubung ke node yang sedang bergerak."""
        # Saat node bergerak, hanya edge yang menyentuh node itu yang perlu dihitung ulang.
        attrs = set(qt_model.attrs_for_node(node_tag))
        for lt, (fa, ta) in state.links.items():
            if fa in attrs or ta in attrs:
                edge = self.edge_items.get(lt)
                if edge:
                    edge.maintain_port_alignment()
                    edge.update_path()

    def refresh_all(self):
        """Mengecat ulang semua node dan link agar visual mengikuti state terbaru."""
        for item in self.node_items.values():
            item.update()
        for edge in self.edge_items.values():
            edge.update_path()

    # ── connection drag (scene-level) ─────────────────────────────────

    def begin_drag(self, attr_tag: str, start_scene: QPointF) -> None:
        """Memulai mode sambung kabel dari satu pin asal."""
        # pending_attr menyimpan pin asal sampai mouse dilepas di target.
        self.pending_attr = attr_tag
        # Rubber band mulai dari port asal dan nanti mengikuti mouse.
        self._rubber.show_path(start_scene, start_scene)
        # Semua view yang menampilkan scene diberi cursor crosshair.
        for view in self.views():
            view.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        # attr_to_node mengubah pin asal menjadi node agar status bisa menyebut label komponen.
        nt = state.attr_to_node.get(attr_tag)
        # Fallback "?" menjaga status tetap aman kalau state tidak lengkap.
        lbl = state.nodes.get(nt, {}).get("label", "?")
        # MainWindow menerima status ini lewat Signal statusChanged.
        self.statusChanged.emit(f"Sambungkan dari {lbl} — lepaskan di port tujuan.", False)
        # Refresh membuat port asal berubah warna menjadi pending.
        self.refresh_all()

    def update_drag(self, scene_pos: QPointF) -> None:
        """Memperbarui garis sementara dan warna port selama user drag koneksi."""
        # Kalau tidak ada drag aktif, mouse move biasa tidak perlu diproses.
        if self.pending_attr is None:
            return
        # Port asal dicari ulang karena node bisa saja bergerak saat state berubah.
        start = self.port_scene_pos(self.pending_attr)
        if start:
            # Garis sementara mengikuti posisi mouse di koordinat scene.
            self._rubber.show_path(start, scene_pos)
        # Update hover highlights on every node
        for item in self.node_items.values():
            # Posisi mouse scene dikonversi ke koordinat lokal node.
            local = item.mapFromScene(scene_pos)
            # port_at mengecek apakah mouse cukup dekat dengan dot port.
            ak, at = item.port_at(local)
            if ak != item._hovered_port:
                # Simpan port hover agar paint() bisa memilih warna dot.
                item._hovered_port = ak
                if ak is not None and self.pending_attr is not None:
                    # Dry-run menjaga preview valid/invalid tanpa membuat link sementara.
                    _, msg = qt_model.add_link(self.pending_attr, at, dry_run=True)
                    # Pesan "ok" artinya target valid menurut qt_model.validate_link().
                    item._port_valid = (msg == "ok")
                else:
                    # Tidak hover port berarti tidak ada error visual.
                    item._port_valid = True
                # Repaint node ini saja supaya feedback drag terasa responsif.
                item.update()

    def finish_drag(self, scene_pos: QPointF) -> None:
        """Menyelesaikan drag koneksi, lalu membuat link atau membatalkannya."""
        # Garis sementara ditutup apapun hasil drop-nya.
        self._rubber.hide_path()
        # Cursor dikembalikan karena mode sambung selesai.
        for view in self.views():
            view.unsetCursor()

        # Find target port under drop position
        target_attr = None
        for item in self.node_items.values():
            # Setiap node dicek karena target bisa berada di node mana pun.
            local = item.mapFromScene(scene_pos)
            _, at = item.port_at(local)
            if at is not None:
                # Ambil pin pertama yang kena radius hit-test.
                target_attr = at
                break

        # Clear all hover states
        for item in self.node_items.values():
            # Hover harus dibersihkan agar dot tidak tertinggal hijau/merah.
            item._hovered_port = None
            item.update()

        # Simpan pin asal lalu kosongkan pending agar state scene tidak menggantung.
        src = self.pending_attr
        self.pending_attr = None

        # Drop kosong atau ke port sendiri berarti user membatalkan koneksi.
        if target_attr is None or target_attr == src:
            self.statusChanged.emit("Koneksi dibatalkan.", False)
            self.refresh_all()
            return

        # Link baru dibuat hanya saat drop berada di port target yang berbeda.
        link_tag, msg = qt_model.add_link(src, target_attr)
        if link_tag is None:
            # Link gagal tetap memberi pesan spesifik dari validate_link().
            self.statusChanged.emit(msg, True)
        else:
            # Link berhasil, maka EdgeItem baru dibuat dari state.links.
            self.add_edge_item(link_tag)
            self.statusChanged.emit(msg, False)
        # Semua node/link direpaint agar port connected dan warna link sinkron.
        self.refresh_all()

    def cancel_drag(self) -> None:
        """Membatalkan mode sambung kabel tanpa mengubah model."""
        self._rubber.hide_path()
        for view in self.views():
            view.unsetCursor()
        for item in self.node_items.values():
            item._hovered_port = None
            item.update()
        self.pending_attr = None
        self.statusChanged.emit("Koneksi dibatalkan.", False)
        self.refresh_all()

    # ── selection helpers ─────────────────────────────────────────────

    def selected_node_tag(self):
        for item in self.selectedItems():
            if isinstance(item, NodeItem):
                return item.node_tag
        return None

    def selected_link_tag(self):
        for item in self.selectedItems():
            if isinstance(item, EdgeItem):
                return item.link_tag
        return None

    def _emit_selection(self):
        nt = self.selected_node_tag()
        lt = None if nt else self.selected_link_tag()
        # State selection dipakai panel properti dan hasil power flow.
        state.selected_node[0] = nt
        state.selected_link[0] = lt
        self.selectionModelChanged.emit(nt, lt)


# ═══════════════════════════════════════════════════════════════════════════
#  GridView — handles ALL mouse input so drag works across nodes
# ═══════════════════════════════════════════════════════════════════════════

class GridView(QGraphicsView):
    zoomChanged = Signal(float)

    def __init__(self, scene: GridScene):
        super().__init__(scene)
        self._zoom        = 1.0
        self._panning     = False
        self._last_pan    = None
        self._dragging    = False      # True while dragging a connection

        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(CANVAS_BG))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    @property
    def zoom(self) -> float:
        return self._zoom

    def _scene(self) -> GridScene:
        return self.scene()

    # ── mouse: press ──────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        """Menentukan apakah klik memulai pan, drag koneksi, atau seleksi biasa."""
        # Middle-button pan
        if event.button() == Qt.MouseButton.MiddleButton:
            # _panning menandai mouse move berikutnya sebagai geser kamera.
            self._panning = True
            # Simpan posisi mouse terakhir untuk menghitung delta pan.
            self._last_pan = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # Klik view diterjemahkan dari koordinat layar ke koordinat scene.
            scene_pos = self.mapToScene(event.position().toPoint())
            # Check if we clicked on a port
            for item in self._scene().node_items.values():
                # Karena port berada di lokal node, scene_pos harus di-map ke item.
                local = item.mapFromScene(scene_pos)
                _, attr_tag = item.port_at(local)
                if attr_tag is not None:
                    # Drag koneksi ditangani di view agar tetap aktif saat kursor keluar node asal.
                    # Start connection drag at the VIEW level
                    # _dragging membuat move/release berikutnya masuk flow koneksi.
                    self._dragging = True
                    self._scene().begin_drag(attr_tag, scene_pos)
                    event.accept()
                    return

        # Default (select / drag node)
        super().mousePressEvent(event)

    # ── mouse: move ───────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:
        """Menggerakkan kamera saat pan atau memperbarui drag koneksi."""
        if self._panning and self._last_pan is not None:
            # delta adalah jarak mouse sejak event sebelumnya.
            delta = event.position() - self._last_pan
            # Update anchor pan untuk frame berikutnya.
            self._last_pan = event.position()
            # Scrollbar QGraphicsView menjadi kamera pan.
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y()))
            event.accept()
            return

        if self._dragging:
            # Saat drag koneksi, mouse move hanya memperbarui rubber band dan hover.
            scene_pos = self.mapToScene(event.position().toPoint())
            self._scene().update_drag(scene_pos)
            event.accept()
            return

        super().mouseMoveEvent(event)

    # ── mouse: release ────────────────────────────────────────────────

    def mouseReleaseEvent(self, event) -> None:
        """Mengakhiri pan atau menyelesaikan drag koneksi."""
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            # Lepas middle mouse menghentikan mode pan.
            self._panning = False
            self._last_pan = None
            self.unsetCursor()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            # Lepas left mouse menjadi momen validasi akhir koneksi.
            scene_pos = self.mapToScene(event.position().toPoint())
            self._scene().finish_drag(scene_pos)
            self._dragging = False
            event.accept()
            return

        super().mouseReleaseEvent(event)

    # ── mouse: right-click cancel ─────────────────────────────────────

    def contextMenuEvent(self, event) -> None:
        if self._dragging:
            self._scene().cancel_drag()
            self._dragging = False
            event.accept()
            return
        super().contextMenuEvent(event)

    # ── wheel: zoom ───────────────────────────────────────────────────

    def wheelEvent(self, event) -> None:
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        self.set_zoom(self._zoom * factor, anchor_under_mouse=True)

    def set_zoom(self, zoom: float, anchor_under_mouse: bool = False) -> None:
        """Mengubah zoom view tanpa mengubah posisi asli node di state."""
        # Clamp mencegah zoom terlalu kecil/besar sampai canvas susah dipakai.
        zoom = max(0.2, min(4.0, float(zoom)))
        # Jika nilai zoom sama, tidak perlu transform ulang.
        if abs(zoom - self._zoom) < 1e-6:
            return
        # QGraphicsView transform dipakai supaya posisi model tidak berubah saat zoom.
        if not anchor_under_mouse:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        # scale memakai rasio zoom baru terhadap zoom lama.
        self.scale(zoom / self._zoom, zoom / self._zoom)
        # _zoom disimpan terpisah agar label UI tidak membaca matrix langsung.
        self._zoom = zoom
        # Signal ini mengupdate label zoom di MainWindow.
        self.zoomChanged.emit(self._zoom)
        if not anchor_under_mouse:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def reset_view(self) -> None:
        """Mengembalikan zoom dan posisi kamera ke kondisi awal."""
        self.resetTransform()
        self._zoom = 1.0
        self.centerOn(0, 0)
        self.zoomChanged.emit(self._zoom)

    def fit_all(self) -> None:
        """Menyesuaikan kamera supaya semua node terlihat di viewport."""
        items = [i for i in self.scene().items() if isinstance(i, NodeItem)]
        if not items:
            return
        # Fit memakai boundingRect node agar semua komponen terlihat dalam satu frame.
        r = QRectF()
        for i in items:
            r = r.united(i.mapToScene(i.boundingRect()).boundingRect())
        r = r.adjusted(-80, -80, 80, 80)
        self.resetTransform()
        self.fitInView(r, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = max(0.2, min(4.0, self.transform().m11()))
        self.zoomChanged.emit(self._zoom)

    def visible_scene_rect(self) -> QRectF:
        return self.mapToScene(self.viewport().rect()).boundingRect()

    def suggest_spawn(self, kind: str):
        """Mencari posisi aman untuk node baru di area canvas yang sedang terlihat."""
        # Spawn memakai canvas_logic agar node baru muncul di area terlihat dan tidak overlap.
        # visible_scene_rect membaca area dunia yang sedang terlihat oleh kamera.
        vis = self.visible_scene_rect()
        # Ukuran node dipakai untuk mengecek overlap dengan node lain.
        size = NODE_SIZES.get(kind, (170, 100))
        existing = []
        for item in self.scene().node_items.values():
            # Existing bounds dibuat dari posisi dan ukuran tiap NodeItem.
            p = item.pos()
            existing.append((p.x(), p.y(), p.x() + item.width, p.y() + item.height))
        # canvas_logic murni math, jadi mudah dites tanpa QApplication.
        return canvas_logic.find_visible_spawn(
            size, existing,
            (vis.left(), vis.top(), vis.right(), vis.bottom()),
            gap=(28, 22), margin=40,
        )
