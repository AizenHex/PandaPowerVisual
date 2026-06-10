"""
State global aplikasi Grid Simulator.
Semua dict shared (nodes, links, attr index, seleksi) hidup di sini agar
modul lain dapat mengaksesnya tanpa circular import.
"""
import copy

# node_tag -> dict data komponen. Selalu punya key "kind" untuk membedakan
# jenis node. Kind yang didukung: "bus", "gen", "trafo", "shunt", "load".
nodes: dict = {}

# link_tag -> (from_attr, to_attr)
links: dict = {}

# link_tag -> parameter saluran listrik untuk koneksi bus-to-bus.
line_data: dict = {}

# link_tag -> list[tuple[float, float]] (manual line waypoint coordinates)
link_waypoints: dict = {}

LINE_DEFAULTS = {
    "label": "Line",
    "length_km": 0.05,
    "r_ohm_per_km": 0.225,
    "x_ohm_per_km": 0.08,
    "c_nf_per_km": 264.0,
    "max_i_ka": 0.242,
}

# attr_tag -> node_tag (membantu mencari pemilik dari sebuah pin)
attr_to_node: dict = {}

# attr_tag -> nama port logis ("p" untuk port tunggal, "hv"/"lv" untuk trafo)
attr_role: dict = {}

# node_tag -> ("bus"|"load"|"sgen"|"shunt"|"trafo", index_di_pandapower)
pp_element_map: dict = {}

# Snapshot hasil power-flow terakhir agar panel properti bisa menampilkan
# detail hasil saat komponen diklik.
last_results: dict = {"nodes": {}, "links": {}}
model_revision: list = [0]
result_revision: list = [-1]

# Counter id per kind
_counters: dict = {
    "bus": 0,
    "gen": 0,
    "trafo": 0,
    "shunt": 0,
    "load": 0,
    "line": 0,
}

# Node yang sedang dipilih (None bila tidak ada)
selected_node: list = [None]
selected_link: list = [None]


def next_id(kind: str) -> int:
    _counters[kind] = _counters.get(kind, 0) + 1
    return _counters[kind]


def make_line_data(**overrides) -> dict:
    data = dict(LINE_DEFAULTS)
    line_id = next_id("line")
    data["label"] = f"Line {line_id}"
    data.update(overrides)
    return data


def mark_model_dirty():
    model_revision[0] += 1


def store_results(results: dict):
    last_results.clear()
    last_results.update(results)
    result_revision[0] = model_revision[0]


def clear_results():
    last_results.clear()
    last_results.update({"nodes": {}, "links": {}})
    result_revision[0] = -1


def results_are_stale() -> bool:
    return result_revision[0] != model_revision[0]


def link_touches_attr(attr_tag, exclude_link=None) -> bool:
    for lt, (fa, ta) in links.items():
        if lt == exclude_link:
            continue
        if attr_tag in (fa, ta):
            return True
    return False


# ── Undo stack ────────────────────────────────────────────────────────────────
# Setiap entry: dict {"nodes":..., "links":..., "line_data":..., "positions":...}
# Positions disimpan terpisah karena posisi node hidup di DPG, bukan di state.
_undo_stack: list = []
_redo_stack: list = []
UNDO_LIMIT = 30


def snapshot_state(positions: dict | None = None) -> dict:
    """Buat snapshot lengkap model untuk undo/redo."""
    return {
        "nodes": copy.deepcopy(nodes),
        "links": copy.deepcopy(links),
        "line_data": copy.deepcopy(line_data),
        "link_waypoints": copy.deepcopy(link_waypoints),
        "attr_to_node": copy.deepcopy(attr_to_node),
        "attr_role": copy.deepcopy(attr_role),
        "counters": copy.deepcopy(_counters),
        "positions": dict(positions) if positions else {},
    }


def push_undo(positions: dict | None = None):
    """Simpan snapshot dari nodes/links/line_data + positions opsional."""
    _undo_stack.append(snapshot_state(positions))
    if len(_undo_stack) > UNDO_LIMIT:
        del _undo_stack[: len(_undo_stack) - UNDO_LIMIT]
    # Aksi baru membuat cabang sejarah baru, jadi redo lama tidak berlaku lagi.
    _redo_stack.clear()


def pop_undo():
    if not _undo_stack:
        return None
    return _undo_stack.pop()


def push_redo_snapshot(positions: dict | None = None):
    """Simpan kondisi sekarang ke redo stack (dipanggil sebelum undo dipulihkan)."""
    _redo_stack.append(snapshot_state(positions))
    if len(_redo_stack) > UNDO_LIMIT:
        del _redo_stack[: len(_redo_stack) - UNDO_LIMIT]


def pop_redo():
    if not _redo_stack:
        return None
    return _redo_stack.pop()


def push_undo_for_redo(positions: dict | None = None):
    """Simpan kondisi sekarang ke undo stack tanpa menghapus redo stack."""
    _undo_stack.append(snapshot_state(positions))
    if len(_undo_stack) > UNDO_LIMIT:
        del _undo_stack[: len(_undo_stack) - UNDO_LIMIT]


def clear_undo():
    _undo_stack.clear()
    _redo_stack.clear()


def undo_depth() -> int:
    return len(_undo_stack)


def redo_depth() -> int:
    return len(_redo_stack)


def reset():
    nodes.clear()
    links.clear()
    line_data.clear()
    link_waypoints.clear()
    pp_element_map.clear()
    attr_to_node.clear()
    attr_role.clear()
    clear_results()
    for k in _counters:
        _counters[k] = 0
    model_revision[0] = 0
    selected_node[0] = None
    selected_link[0] = None
    # Catatan: undo stack TIDAK ikut di-clear di sini supaya operasi seperti
    # "Load Template" yang memanggil reset() di tengah jalan tetap bisa di-undo.
    # Gunakan clear_undo() eksplisit bila perlu reset penuh.
