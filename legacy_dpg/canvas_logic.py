"""Pure canvas transform and placement helpers.

Dear PyGui owns rendering and link editing, but this module owns the math:
world coordinates are stable model positions, screen coordinates are render
positions after zoom and pan.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


Point = tuple[float, float]
Size = tuple[float, float]
Bounds = tuple[float, float, float, float]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rect_from_pos_size(pos: Point, size: Size) -> Bounds:
    x, y = float(pos[0]), float(pos[1])
    width, height = max(1.0, float(size[0])), max(1.0, float(size[1]))
    return (x, y, x + width, y + height)


def union_bounds(bounds: Iterable[Bounds]) -> Bounds | None:
    items = list(bounds)
    if not items:
        return None
    return (
        min(item[0] for item in items),
        min(item[1] for item in items),
        max(item[2] for item in items),
        max(item[3] for item in items),
    )


def bounds_overlap(
    first: Bounds,
    second: Bounds,
    gap: Size = (0.0, 0.0),
) -> bool:
    gap_x, gap_y = float(gap[0]), float(gap[1])
    return not (
        first[2] + gap_x <= second[0]
        or second[2] + gap_x <= first[0]
        or first[3] + gap_y <= second[1]
        or second[3] + gap_y <= first[1]
    )


def rect_contains(rect: Bounds, bounds: Bounds) -> bool:
    return (
        bounds[0] >= rect[0]
        and bounds[1] >= rect[1]
        and bounds[2] <= rect[2]
        and bounds[3] <= rect[3]
    )


@dataclass
class CanvasView:
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    zoom_min: float = 0.3
    zoom_max: float = 3.0

    def reset(self) -> None:
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def world_to_screen(self, point: Point) -> Point:
        x, y = float(point[0]), float(point[1])
        return (x * self.zoom + self.pan_x, y * self.zoom + self.pan_y)

    def screen_to_world(self, point: Point) -> Point:
        x, y = float(point[0]), float(point[1])
        return ((x - self.pan_x) / self.zoom, (y - self.pan_y) / self.zoom)

    def pan_by(self, dx: float, dy: float) -> None:
        self.pan_x += float(dx)
        self.pan_y += float(dy)

    def zoom_to(
        self,
        new_zoom: float,
        viewport_size: Size,
        anchor_screen: Point | None = None,
    ) -> None:
        width, height = _safe_size(viewport_size)
        if anchor_screen is None:
            anchor_screen = (width / 2.0, height / 2.0)
        anchor_world = self.screen_to_world(anchor_screen)
        self.zoom = _clamp(float(new_zoom), self.zoom_min, self.zoom_max)
        self.pan_x = float(anchor_screen[0]) - anchor_world[0] * self.zoom
        self.pan_y = float(anchor_screen[1]) - anchor_world[1] * self.zoom

    def visible_world_rect(self, viewport_size: Size) -> Bounds:
        width, height = _safe_size(viewport_size)
        left, top = self.screen_to_world((0.0, 0.0))
        right, bottom = self.screen_to_world((width, height))
        return (
            min(left, right),
            min(top, bottom),
            max(left, right),
            max(top, bottom),
        )

    def fit_bounds(
        self,
        bounds: Bounds,
        viewport_size: Size,
        margin: float = 48.0,
    ) -> None:
        width, height = _safe_size(viewport_size)
        left, top, right, bottom = bounds
        world_w = max(1.0, float(right) - float(left))
        world_h = max(1.0, float(bottom) - float(top))
        usable_w = max(1.0, width - margin * 2.0)
        usable_h = max(1.0, height - margin * 2.0)
        self.zoom = _clamp(min(usable_w / world_w, usable_h / world_h), self.zoom_min, self.zoom_max)
        self.pan_x = margin - float(left) * self.zoom
        self.pan_y = margin - float(top) * self.zoom


def _safe_size(size: Size) -> Size:
    width = max(1.0, float(size[0]))
    height = max(1.0, float(size[1]))
    return width, height


def _candidate_is_free(
    pos: Point,
    size: Size,
    existing_bounds: Sequence[Bounds],
    search_rect: Bounds,
    gap: Size,
) -> bool:
    bounds = rect_from_pos_size(pos, size)
    if not rect_contains(search_rect, bounds):
        return False
    return all(not bounds_overlap(bounds, other, gap) for other in existing_bounds)


def find_visible_spawn(
    size: Size,
    existing_bounds: Sequence[Bounds],
    visible_rect: Bounds,
    gap: Size = (28.0, 22.0),
    margin: float = 40.0,
) -> Point:
    """Find a non-overlapping position inside the visible world rectangle.

    If the visible area is too crowded, return a clamped visible position anyway
    so the new component never appears lost off-screen.
    """
    width, height = max(1.0, float(size[0])), max(1.0, float(size[1]))
    gap_x, gap_y = max(0.0, float(gap[0])), max(0.0, float(gap[1]))
    left, top, right, bottom = visible_rect
    if right <= left or bottom <= top:
        return (80.0, 70.0)

    min_x = float(left) + margin
    min_y = float(top) + margin
    max_x = max(min_x, float(right) - width)
    max_y = max(min_y, float(bottom) - height)
    search_rect = (float(left), float(top), float(right), float(bottom))
    step_x = max(width + gap_x, 40.0)
    step_y = max(height + gap_y, 40.0)

    rows = {min_y}
    y = min_y
    while y <= max_y + 0.001:
        rows.add(y)
        y += step_y
    for bounds in existing_bounds:
        for candidate_y in (bounds[1], bounds[3] + gap_y):
            if min_y <= candidate_y <= max_y:
                rows.add(float(candidate_y))

    for y in sorted(rows):
        x_values = {min_x}
        x = min_x
        while x <= max_x + 0.001:
            x_values.add(x)
            x += step_x
        for bounds in existing_bounds:
            vertical_overlap = not (
                y + height + gap_y <= bounds[1]
                or bounds[3] + gap_y <= y
            )
            if vertical_overlap:
                after = bounds[2] + gap_x
                before = bounds[0] - gap_x - width
                if min_x <= after <= max_x:
                    x_values.add(float(after))
                if min_x <= before <= max_x:
                    x_values.add(float(before))
        for x in sorted(x_values):
            candidate = (x, y)
            if _candidate_is_free(candidate, (width, height), existing_bounds, search_rect, gap):
                return candidate

    return (_clamp(min_x, float(left), max_x), _clamp(min_y, float(top), max_y))


def find_open_position(
    preferred: Point,
    size: Size,
    existing_bounds: Sequence[Bounds],
    row_left: float,
    row_right: float,
    gap: Size = (28.0, 22.0),
) -> Point:
    """Collision helper used by auto-placement/auto-align, not by free drag."""
    width, height = max(1.0, float(size[0])), max(1.0, float(size[1]))
    gap_x, gap_y = max(0.0, float(gap[0])), max(0.0, float(gap[1]))
    preferred_x, preferred_y = float(preferred[0]), float(preferred[1])
    search_rect = (
        float(row_left),
        min(preferred_y, *(bounds[1] for bounds in existing_bounds)) if existing_bounds else preferred_y,
        float(row_right),
        max(preferred_y + height, *(bounds[3] for bounds in existing_bounds)) + (height + gap_y) * (len(existing_bounds) + 2),
    )

    if _candidate_is_free((preferred_x, preferred_y), (width, height), existing_bounds, search_rect, gap):
        return (preferred_x, preferred_y)

    rows = {preferred_y}
    rows.update(bounds[1] for bounds in existing_bounds)
    max_bottom = max((bounds[3] for bounds in existing_bounds), default=preferred_y)
    row_step = max(height + gap_y, 40.0)
    rows.update(max_bottom + gap_y + row_step * i for i in range(len(existing_bounds) + 2))

    for y in sorted(rows, key=lambda row: (abs(row - preferred_y), row)):
        x_values = {float(row_left), preferred_x}
        for bounds in existing_bounds:
            vertical_overlap = not (
                y + height + gap_y <= bounds[1]
                or bounds[3] + gap_y <= y
            )
            if vertical_overlap:
                x_values.add(bounds[2] + gap_x)
        for x in sorted(x_values):
            if x < row_left:
                continue
            if _candidate_is_free((x, y), (width, height), existing_bounds, search_rect, gap):
                return (x, y)

    return (float(row_left), max_bottom + gap_y)
