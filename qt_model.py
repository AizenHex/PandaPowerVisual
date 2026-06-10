"""GUI-neutral model helpers for the Qt Grid Simulator shell."""
from __future__ import annotations

import copy
import csv
import json
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import state

# qt_model menjadi pintu mutasi state dari UI Qt, supaya canvas dan panel tidak
# perlu menulis struktur global secara langsung.


_undo_enabled = True


@contextmanager
def suspend_undo():
    # Dipakai saat load/template agar operasi massal tidak memenuhi undo stack.
    global _undo_enabled
    previous = _undo_enabled
    _undo_enabled = False
    try:
        yield
    finally:
        _undo_enabled = previous


ATTR_KEYS = ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin")
PROJECT_NODE_KINDS = {"bus", "gen", "trafo", "shunt", "load"}
# Mapping ini harus sama dengan port yang digambar di qt_canvas.port_layout().
PROJECT_ATTRS_BY_KIND = {
    "bus": {"out_attr", "in_attr"},
    "gen": {"pin"},
    "load": {"pin"},
    "shunt": {"pin"},
    "trafo": {"hv_pin", "lv_pin"},
}


def app_base_dir() -> Path:
    # Saat dibundle jadi exe, project/export mengikuti folder executable.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_BASE_DIR = app_base_dir()
PROJECT_PATH = APP_BASE_DIR / "grid_project.json"
EXPORT_DIR = APP_BASE_DIR / "exports"


def new_tag(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def reset_model(clear_undo: bool = False) -> None:
    state.reset()
    if clear_undo:
        state.clear_undo()


def push_undo_snapshot() -> None:
    # Semua callback UI lewat fungsi ini agar Ctrl+Z memulihkan model utuh.
    if _undo_enabled:
        state.push_undo()


def restore_undo_snapshot(snap: dict) -> None:
    # Snapshot dipulihkan ke state global, lalu scene Qt dibangun ulang oleh caller.
    state.nodes.clear()
    state.nodes.update(copy.deepcopy(snap.get("nodes", {})))
    state.links.clear()
    state.links.update(copy.deepcopy(snap.get("links", {})))
    state.line_data.clear()
    state.line_data.update(copy.deepcopy(snap.get("line_data", {})))
    state.link_waypoints.clear()
    state.link_waypoints.update(copy.deepcopy(snap.get("link_waypoints", {})))
    state.attr_to_node.clear()
    state.attr_to_node.update(copy.deepcopy(snap.get("attr_to_node", {})))
    state.attr_role.clear()
    state.attr_role.update(copy.deepcopy(snap.get("attr_role", {})))
    state.pp_element_map.clear()
    for key, value in snap.get("counters", {}).items():
        state._counters[key] = value
    state.selected_node[0] = None
    state.selected_link[0] = None
    state.clear_results()
    state.mark_model_dirty()


def attrs_for_node(node_tag) -> list:
    nd = state.nodes.get(node_tag, {})
    return [nd[key] for key in ATTR_KEYS if key in nd]


def node_for_attr(attr_tag):
    return state.attr_to_node.get(attr_tag)


def kind_for_attr(attr_tag):
    node_tag = node_for_attr(attr_tag)
    return state.nodes.get(node_tag, {}).get("kind")


def is_single_terminal_attr(attr_tag) -> bool:
    node_tag = node_for_attr(attr_tag)
    nd = state.nodes.get(node_tag)
    if not nd:
        return False
    if nd["kind"] in ("gen", "load", "shunt"):
        return True
    if nd["kind"] == "trafo":
        return attr_tag in (nd.get("hv_pin"), nd.get("lv_pin"))
    return False


def default_node_values(kind: str, label: str | None = None) -> dict:
    if kind == "bus":
        bus_id = state.next_id("bus")
        # Bus pertama otomatis menjadi slack agar contoh paling sederhana langsung valid.
        is_first_bus = not any(nd.get("kind") == "bus" for nd in state.nodes.values())
        return {
            "label": label or ("Ext Grid" if is_first_bus else f"Bus {bus_id}"),
            "vn_kv": 20.0 if is_first_bus else 0.4,
            "is_slack": is_first_bus,
            "vm_pu": 1.0,
            "va_degree": 0.0,
        }
    if kind == "gen":
        return {
            "label": label or f"Gen {state.next_id('gen')}",
            "p_mw": 1.0,
            "q_mvar": 0.0,
            # ctrl_mode "pq" = static generator; "pv" = kontrol tegangan (create_gen).
            "ctrl_mode": "pq",
            "vm_pu": 1.0,
            "sn_mva": 1.0,
        }
    if kind == "trafo":
        return {
            "label": label or f"Trafo {state.next_id('trafo')}",
            "sn_mva": 10.0,
            "vn_hv_kv": 110.0,
            "vn_lv_kv": 20.0,
            "vk_percent": 6.0,
            "vkr_percent": 0.5,
            "pfe_kw": 0.0,
            "i0_percent": 0.0,
        }
    if kind == "shunt":
        return {"label": label or f"Shunt {state.next_id('shunt')}", "p_mw": 0.0, "q_mvar": -1.0}
    if kind == "load":
        return {"label": label or f"Load {state.next_id('load')}", "p_mw": 0.5, "q_mvar": 0.1}
    raise ValueError(f"Unknown component kind: {kind}")


def _register_attr(node_tag, attr_key: str, role: str) -> str:
    # attr_tag adalah ID pin; engine memakai role ini untuk membedakan HV/LV trafo.
    attr_tag = new_tag(f"attr_{attr_key}")
    state.nodes[node_tag][attr_key] = attr_tag
    state.attr_to_node[attr_tag] = node_tag
    state.attr_role[attr_tag] = role
    return attr_tag


def create_node(kind: str, world_pos=(80.0, 70.0), label: str | None = None, **overrides):
    """Membuat satu komponen baru beserta posisi, parameter default, dan pin koneksinya."""
    # kind dicek dulu supaya UI tidak bisa membuat tipe komponen liar.
    if kind not in PROJECT_NODE_KINDS:
        raise ValueError(f"Unknown component kind: {kind}")
    # Node dibuat lewat adapter ini supaya posisi, default elektro, pin, dan undo sinkron.
    push_undo_snapshot()
    # node_tag adalah ID runtime yang dipakai state, canvas, dan properties panel.
    node_tag = new_tag(f"node_{kind}")
    # data dasar berisi tipe, posisi canvas, dan default parameter elektro.
    data = {
        "kind": kind,
        "world_pos": (float(world_pos[0]), float(world_pos[1])),
        **default_node_values(kind, label),
    }
    # overrides dipakai template/load project untuk mengganti default tanpa kode khusus.
    data.update(overrides)
    # Setelah masuk state.nodes, canvas bisa membuat NodeItem dari tag ini.
    state.nodes[node_tag] = data

    # Bus punya dua port agar arah saluran bisa dibaca OUT ke IN.
    if kind == "bus":
        _register_attr(node_tag, "out_attr", "p")
        _register_attr(node_tag, "in_attr", "p")
    # Komponen satu-terminal cukup satu pin karena hanya menempel ke bus.
    elif kind in ("gen", "load", "shunt"):
        _register_attr(node_tag, "pin", "p")
    # Trafo butuh dua pin berbeda agar engine tahu sisi tegangan tinggi/rendah.
    elif kind == "trafo":
        _register_attr(node_tag, "hv_pin", "hv")
        _register_attr(node_tag, "lv_pin", "lv")

    # Dirty revision membuat hasil power flow lama dianggap tidak berlaku.
    state.mark_model_dirty()
    # Caller butuh tag ini untuk membuat item Qt dan memilih node baru.
    return node_tag


def set_node_world_pos(node_tag, world_pos) -> None:
    """Menyimpan posisi dunia node setelah user menggeser kartu di canvas."""
    if node_tag in state.nodes:
        state.nodes[node_tag]["world_pos"] = (float(world_pos[0]), float(world_pos[1]))


def set_node_value(node_tag, key: str, value) -> None:
    """Mengubah satu nilai properti node dari panel kanan."""
    nd = state.nodes.get(node_tag)
    if not nd:
        return
    nd[key] = value
    if key == "is_slack" and value:
        # Pandapower butuh satu acuan utama, jadi UI menonaktifkan slack bus lain.
        for other_tag, other in state.nodes.items():
            if other_tag != node_tag and other.get("kind") == "bus" and other.get("is_slack"):
                other["is_slack"] = False
    state.mark_model_dirty()
    state.clear_results()


def validate_link(from_attr, to_attr):
    """Memeriksa apakah dua pin boleh disambungkan menurut aturan model listrik."""
    # Validasi koneksi ditaruh di model agar hover canvas dan load project memakai aturan sama.
    # from_attr dan to_attr adalah ID pin, bukan ID node.
    fn = node_for_attr(from_attr)
    tn = node_for_attr(to_attr)
    # Kalau pin tidak terdaftar, koneksi tidak boleh dibuat.
    if not fn or not tn:
        return False, "Pin tidak dikenal.", None
    # Satu node tidak boleh disambungkan ke dirinya sendiri.
    if fn == tn:
        return False, "Tidak bisa menghubungkan pin dalam node yang sama.", None

    # Cegah duplikasi link, termasuk kalau arah from/to tertukar.
    for fa, ta in state.links.values():
        if (fa == from_attr and ta == to_attr) or (fa == to_attr and ta == from_attr):
            return False, "Koneksi ini sudah ada.", None

    # fk/tk dipakai untuk membaca jenis node di dua ujung koneksi.
    fk = kind_for_attr(from_attr)
    tk = kind_for_attr(to_attr)
    # Set memudahkan pengecekan "ada bus + ada load/gen/trafo".
    kinds = {fk, tk}

    for attr in (from_attr, to_attr):
        # Gen/load/shunt dan tiap sisi trafo hanya boleh punya satu koneksi fisik.
        if is_single_terminal_attr(attr) and state.link_touches_attr(attr):
            return False, "Pin komponen itu sudah terhubung.", None

    if fk == "bus" and tk == "bus":
        # Bus-ke-bus menjadi line pandapower, jadi harus melewati port OUT ke IN.
        # from_is_out True berarti pin pertama adalah output bus.
        from_is_out = state.nodes[fn]["out_attr"] == from_attr
        # to_is_out True berarti pin kedua juga output, sehingga tidak boleh jika sama.
        to_is_out = state.nodes[tn]["out_attr"] == to_attr
        # XOR sederhana: OUT-IN atau IN-OUT valid, OUT-OUT/IN-IN tidak valid.
        if from_is_out != to_is_out:
            return True, "", "line"
        return False, "Koneksi bus-ke-bus harus menghubungkan Output dan Input.", None

    if "bus" in kinds and (kinds & {"gen", "load", "shunt"}):
        # Arah port menjaga semantik sumber masuk ke bus, beban/shunt keluar dari bus.
        # bus_node menyimpan node bus meski user drag dari arah mana pun.
        bus_node = fn if fk == "bus" else tn
        # bus_attr adalah pin bus yang sedang dipakai koneksi.
        bus_attr = from_attr if fk == "bus" else to_attr
        # comp_kind adalah jenis komponen non-bus di ujung lain.
        comp_kind = tk if fk == "bus" else fk
        if comp_kind == "gen":
            # Generator masuk ke bus, jadi harus menempel di input bus.
            if bus_attr == state.nodes[bus_node]["in_attr"]:
                return True, "", "component"
            return False, "Generator harus dihubungkan ke input bus.", None
        if comp_kind in ("load", "shunt"):
            # Beban dan shunt diambil dari bus, jadi harus menempel di output bus.
            if bus_attr == state.nodes[bus_node]["out_attr"]:
                return True, "", "component"
            label = "Beban" if comp_kind == "load" else "Shunt"
            return False, f"{label} harus dihubungkan ke output bus.", None

    if "bus" in kinds and "trafo" in kinds:
        # Role HV/LV disimpan di state.attr_role agar engine bisa memilih sisi trafo.
        # trafo_attr harus menunjuk hv_pin atau lv_pin.
        trafo_attr = from_attr if fk == "trafo" else to_attr
        # bus_node adalah bus yang tersambung ke sisi trafo tersebut.
        bus_node = fn if fk == "bus" else tn
        # bus_attr menentukan apakah sisi trafo masuk ke input atau output bus.
        bus_attr = from_attr if fk == "bus" else to_attr
        # role berisi "hv" atau "lv" dari _register_attr().
        role = state.attr_role.get(trafo_attr)
        if role == "hv":
            # Sisi HV dianggap berasal dari bus tegangan tinggi, memakai output bus.
            if bus_attr == state.nodes[bus_node]["out_attr"]:
                return True, "", "trafo"
            return False, "Transformer HV harus dihubungkan ke output bus.", None
        if role == "lv":
            # Sisi LV masuk ke bus tegangan rendah, memakai input bus.
            if bus_attr == state.nodes[bus_node]["in_attr"]:
                return True, "", "trafo"
            return False, "Transformer LV harus dihubungkan ke input bus.", None
        return False, "Trafo harus memakai pin HV atau LV.", None

    return False, "Koneksi tidak valid untuk model pandapower.", None


def add_link(from_attr, to_attr, line_values=None, dry_run: bool = False):
    """Create a link between two attrs.

    If *dry_run* is True, only validate without creating anything.
    Returns ("ok", "ok") when valid, or (None, msg) when invalid.
    """
    # validate_link mengembalikan jenis link agar add_link tahu perlu line_data atau tidak.
    ok, msg, link_kind = validate_link(from_attr, to_attr)
    # Jika tidak valid, caller mendapat pesan yang sama untuk status bar/hover.
    if not ok:
        return None, msg
    if dry_run:
        # Dry-run dipakai hover canvas untuk warna valid/invalid tanpa mengubah model.
        return "ok", "ok"
    # Link sungguhan harus bisa di-undo.
    push_undo_snapshot()
    # link_tag adalah ID runtime untuk state.links dan EdgeItem.
    link_tag = new_tag("link")
    # state.links hanya menyimpan pasangan pin; detail node dicari lewat attr_to_node.
    state.links[link_tag] = (from_attr, to_attr)
    if link_kind == "line":
        # Hanya bus-ke-bus yang butuh parameter saluran listrik.
        state.line_data[link_tag] = state.make_line_data(**(line_values or {}))
    # Model berubah, maka hasil lama tidak aman dipakai.
    state.mark_model_dirty()
    state.clear_results()
    # Pesan ini langsung dipakai MainWindow/GridScene untuk status UI.
    return link_tag, "Koneksi ditambahkan."


def delete_link(link_tag) -> bool:
    """Menghapus satu koneksi dan data salurannya dari state."""
    if link_tag not in state.links:
        return False
    push_undo_snapshot()
    state.links.pop(link_tag, None)
    state.line_data.pop(link_tag, None)
    state.link_waypoints.pop(link_tag, None)
    if state.selected_link[0] == link_tag:
        state.selected_link[0] = None
    state.mark_model_dirty()
    state.clear_results()
    return True


def delete_node(node_tag) -> bool:
    """Menghapus node beserta semua koneksi yang menempel pada node tersebut."""
    if node_tag not in state.nodes:
        return False
    push_undo_snapshot()
    attrs = set(attrs_for_node(node_tag))
    # Link yang menyentuh node dihapus dulu agar tidak ada attr yatim di state.links.
    for link_tag, (fa, ta) in list(state.links.items()):
        if fa in attrs or ta in attrs:
            delete_link(link_tag)
    for attr in attrs:
        state.attr_to_node.pop(attr, None)
        state.attr_role.pop(attr, None)
    state.nodes.pop(node_tag, None)
    state.pp_element_map.pop(node_tag, None)
    if state.selected_node[0] == node_tag:
        state.selected_node[0] = None
    if state.selected_link[0] not in state.links:
        state.selected_link[0] = None
    state.mark_model_dirty()
    state.clear_results()
    return True


def clear_model(clear_undo_stack: bool = True) -> None:
    state.reset()
    if clear_undo_stack:
        state.clear_undo()


def attr_ref(attr_tag, node_ids):
    node_tag = state.attr_to_node.get(attr_tag)
    nd = state.nodes.get(node_tag, {})
    for key in ATTR_KEYS:
        if nd.get(key) == attr_tag:
            return {"node": node_ids[node_tag], "attr": key}
    return None


def snapshot_model() -> dict:
    """Mengubah state runtime menjadi payload JSON project yang stabil."""
    # File project memakai id stabil n0, n1, ... agar tidak menyimpan UUID runtime.
    node_ids = {node_tag: f"n{i}" for i, node_tag in enumerate(state.nodes)}
    nodes = []
    for node_tag, node_id in node_ids.items():
        nd = state.nodes[node_tag]
        item = {
            "id": node_id,
            "kind": nd["kind"],
            "label": nd["label"],
            "pos": list(nd.get("world_pos", (0.0, 0.0))),
        }
        for key in (
            "vn_kv",
            "is_slack",
            "vm_pu",
            "va_degree",
            "p_mw",
            "q_mvar",
            "sn_mva",
            "vn_hv_kv",
            "vn_lv_kv",
            "vk_percent",
            "vkr_percent",
            "pfe_kw",
            "i0_percent",
            "ctrl_mode",
        ):
            if key in nd:
                item[key] = nd[key]
        nodes.append(item)

    links = []
    for link_tag, (from_attr, to_attr) in state.links.items():
        # Link disimpan sebagai referensi node+attr supaya aman saat tag runtime berubah.
        from_ref = attr_ref(from_attr, node_ids)
        to_ref = attr_ref(to_attr, node_ids)
        if not from_ref or not to_ref:
            continue
        item = {"from": from_ref, "to": to_ref}
        if link_tag in state.line_data:
            item["line_data"] = dict(state.line_data[link_tag])
        if link_tag in state.link_waypoints and state.link_waypoints[link_tag]:
            item["waypoints"] = [list(pt) for pt in state.link_waypoints[link_tag]]
        links.append(item)
    return {"version": 1, "nodes": nodes, "links": links}


def validate_project_payload(data) -> str | None:
    """Memvalidasi struktur file project sebelum dimuat ke state."""
    # Validasi JSON dilakukan sebelum clear_model agar file rusak tidak menghapus canvas aktif.
    if not isinstance(data, dict):
        return "format utama harus berupa object JSON."
    nodes = data.get("nodes")
    links = data.get("links", [])
    if not isinstance(nodes, list):
        return "field nodes harus berupa list."
    if not isinstance(links, list):
        return "field links harus berupa list."

    node_ids = set()
    node_kinds = {}
    for index, item in enumerate(nodes, start=1):
        if not isinstance(item, dict):
            return f"node ke-{index} bukan object."
        node_id = item.get("id")
        if not isinstance(node_id, str) or not node_id:
            return f"node ke-{index} tidak punya id valid."
        if node_id in node_ids:
            return f"id node duplikat: {node_id}."
        node_ids.add(node_id)
        kind = item.get("kind")
        if kind not in PROJECT_NODE_KINDS:
            return f"node {node_id} punya kind tidak dikenal: {kind}."
        node_kinds[node_id] = kind
        pos = item.get("pos")
        if pos is not None:
            if not isinstance(pos, (list, tuple)) or len(pos) != 2:
                return f"node {node_id} punya posisi tidak valid."
            try:
                float(pos[0])
                float(pos[1])
            except (TypeError, ValueError):
                return f"node {node_id} punya posisi bukan angka."

    touched_single_attrs = {}
    for index, item in enumerate(links, start=1):
        # Aturan import sengaja menyamai validate_link(), termasuk pin single-terminal.
        if not isinstance(item, dict):
            return f"link ke-{index} bukan object."
        refs = []
        for endpoint in ("from", "to"):
            ref = item.get(endpoint)
            if not isinstance(ref, dict):
                return f"link ke-{index} tidak punya endpoint {endpoint} valid."
            node_id = ref.get("node")
            attr = ref.get("attr")
            if node_id not in node_ids:
                return f"link ke-{index} mengarah ke node tidak dikenal: {node_id}."
            if attr not in ATTR_KEYS:
                return f"link ke-{index} punya attr tidak dikenal: {attr}."
            allowed = PROJECT_ATTRS_BY_KIND.get(node_kinds.get(node_id), set())
            if attr not in allowed:
                return f"link ke-{index} memakai attr {attr} yang tidak cocok untuk node {node_id}."
            refs.append((node_id, attr, node_kinds[node_id]))
        (from_node, from_attr, from_kind), (to_node, to_attr, to_kind) = refs
        if from_node == to_node:
            return f"link ke-{index} menghubungkan node yang sama."
        for node_id, attr, kind in refs:
            is_single = (
                (kind in {"gen", "load", "shunt"} and attr == "pin")
                or (kind == "trafo" and attr in {"hv_pin", "lv_pin"})
            )
            if not is_single:
                continue
            key = (node_id, attr)
            if key in touched_single_attrs:
                return f"link ke-{index} memakai pin {attr} node {node_id} yang sudah terhubung."
            touched_single_attrs[key] = index
        kinds = {from_kind, to_kind}
        valid_link = False
        if from_kind == "bus" and to_kind == "bus":
            valid_link = (
                (from_attr == "out_attr" and to_attr == "in_attr")
                or (from_attr == "in_attr" and to_attr == "out_attr")
            )
        elif "bus" in kinds and (kinds & {"gen", "load", "shunt"}):
            bus_attr = from_attr if from_kind == "bus" else to_attr
            comp_kind = to_kind if from_kind == "bus" else from_kind
            valid_link = (
                (comp_kind == "gen" and bus_attr == "in_attr")
                or (comp_kind in {"load", "shunt"} and bus_attr == "out_attr")
            )
        elif "bus" in kinds and "trafo" in kinds:
            trafo_attr = from_attr if from_kind == "trafo" else to_attr
            bus_attr = to_attr if from_kind == "trafo" else from_attr
            valid_link = (
                (trafo_attr == "hv_pin" and bus_attr == "out_attr")
                or (trafo_attr == "lv_pin" and bus_attr == "in_attr")
            )
        if not valid_link:
            return f"link ke-{index} punya kombinasi koneksi yang tidak valid."
        if "line_data" in item and not isinstance(item["line_data"], dict):
            return f"link ke-{index} punya line_data tidak valid."
        if "waypoints" in item:
            pts = item["waypoints"]
            if not isinstance(pts, list):
                return f"link ke-{index} memiliki field waypoints yang bukan list."
            for pt_idx, pt in enumerate(pts, start=1):
                if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                    return f"link ke-{index} memiliki waypoint ke-{pt_idx} yang tidak valid."
                try:
                    float(pt[0])
                    float(pt[1])
                except (TypeError, ValueError):
                    return f"link ke-{index} memiliki waypoint ke-{pt_idx} bukan angka."
    return None


def load_project_payload(data) -> str | None:
    """Memuat payload project valid ke state runtime baru."""
    # Payload dicek dulu tanpa mengubah canvas.
    problem = validate_project_payload(data)
    # Jika problem berisi teks, caller bisa menampilkannya sebagai error.
    if problem:
        return problem
    # Setelah payload aman, model lama baru diganti dengan node/link hasil load.
    clear_model(clear_undo_stack=False)
    # node_map menerjemahkan ID file project ke tag runtime baru.
    node_map = {}
    for item in data.get("nodes", []):
        # kind menentukan default parameter yang perlu dibuat ulang.
        kind = item["kind"]
        # pos disimpan sebagai world coordinate, bukan posisi layar hasil zoom.
        pos = tuple(item.get("pos", (80.0, 70.0)))
        # overrides berisi parameter elektro dari file project.
        overrides = {
            key: value
            for key, value in item.items()
            if key not in {"id", "kind", "label", "pos"}
        }
        # create_node membuat tag baru, pin baru, dan attr_role baru.
        node_map[item["id"]] = create_node(kind, pos, label=item.get("label"), **overrides)
    for item in data.get("links", []):
        # Endpoint file project dikonversi dari id lama ke tag runtime baru.
        from_node = node_map.get(item["from"]["node"])
        to_node = node_map.get(item["to"]["node"])
        # Nama attr seperti out_attr/hv_pin dipakai untuk mengambil pin aktual.
        from_attr = state.nodes[from_node].get(item["from"]["attr"])
        to_attr = state.nodes[to_node].get(item["to"]["attr"])
        # add_link tetap dipakai agar aturan koneksi konsisten dengan drag UI.
        link_tag, msg = add_link(from_attr, to_attr, item.get("line_data"))
        if link_tag is None:
            return msg
        if "waypoints" in item:
            # Waypoint visual ikut disimpan agar jalur kabel manual tidak hilang saat load.
            state.link_waypoints[link_tag] = [tuple(pt) for pt in item["waypoints"]]
    state.clear_results()
    return None


def save_project(path: Path = PROJECT_PATH) -> None:
    """Menyimpan project aktif ke file JSON."""
    path.write_text(json.dumps(snapshot_model(), indent=2), encoding="utf-8")


def load_project(path: Path = PROJECT_PATH) -> str | None:
    """Membaca file JSON project lalu memuatnya ke state."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return load_project_payload(data)


def csv_write(path: Path, rows: list[dict]) -> None:
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_results(path: Path = EXPORT_DIR) -> bool:
    """Mengekspor hasil power flow terakhir ke CSV dan snapshot JSON."""
    node_results = state.last_results.get("nodes", {})
    link_results = state.last_results.get("links", {})
    if not node_results and not link_results:
        return False
    # Export hanya memakai hasil terakhir dari engine, lalu menyertakan snapshot project.
    path.mkdir(exist_ok=True)
    node_rows = []
    for node_tag, result in node_results.items():
        nd = state.nodes.get(node_tag, {})
        node_rows.append({"component": nd.get("label", str(node_tag)), "kind": nd.get("kind", ""), **result})
    link_rows = []
    for link_tag, result in link_results.items():
        fa, ta = state.links.get(link_tag, (None, None))
        fn = state.attr_to_node.get(fa)
        tn = state.attr_to_node.get(ta)
        line = state.line_data.get(link_tag, {})
        link_rows.append({
            "component": line.get("label", "Koneksi"),
            "from": state.nodes.get(fn, {}).get("label", "?"),
            "to": state.nodes.get(tn, {}).get("label", "?"),
            **result,
        })
    if node_rows:
        csv_write(path / "node_results.csv", node_rows)
    if link_rows:
        csv_write(path / "link_results.csv", link_rows)
    (path / "project_snapshot.json").write_text(json.dumps(snapshot_model(), indent=2), encoding="utf-8")
    return True
