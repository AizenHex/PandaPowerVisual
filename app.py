"""
Aplikasi utama Grid Simulator.

UI memakai Dear PyGui, sedangkan perhitungan aliran daya memakai pandapower.
"""
import json
import csv
import sys
from pathlib import Path

import dearpygui.dearpygui as dpg

import state
import components
import engine
import visualization
import properties_panel


def _app_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_BASE_DIR = _app_base_dir()
PROJECT_PATH = APP_BASE_DIR / "grid_project.json"
EXPORT_DIR = APP_BASE_DIR / "exports"
ATTR_KEYS = ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin")
PROJECT_NODE_KINDS = {"bus", "gen", "trafo", "shunt", "load"}
PROJECT_ATTRS_BY_KIND = {
    "bus": {"out_attr", "in_attr"},
    "gen": {"pin"},
    "load": {"pin"},
    "shunt": {"pin"},
    "trafo": {"hv_pin", "lv_pin"},
}
SIDEBAR_TAG = "left_sidebar"
CENTER_PANEL_TAG = "center_panel"
CANVAS_PANEL_TAG = "canvas_panel"
RESULTS_PANEL_TAG = "results_panel"
TOOLBAR_TAG = "top_toolbar"
BODY_TAG = "main_body"
LEFT_WIDTH = 230
RIGHT_WIDTH = 340
MIN_CENTER_WIDTH = 520
TOOLBAR_HEIGHT = 74
node_zoom_theme_tag: list = [None]
NODE_SLOT_X = 320
NODE_SLOT_Y = 190
NODE_MIN_DX = 260
NODE_MIN_DY = 150
NODE_GAP_X = 28
NODE_GAP_Y = 22
NODE_TEXT_W = 8
NODE_LINE_H = 21
NODE_KIND_MIN_SIZE = {
    "bus": (150, 112),
    "gen": (150, 92),
    "trafo": (190, 112),
    "shunt": (165, 92),
    "load": (165, 92),
}

# Flags layout
left_visible: list = [True]
right_visible: list = [True]

# Zoom state
zoom_level: list = [1.0]
ZOOM_MIN = 0.3
ZOOM_MAX = 3.0
ZOOM_STEP = 1.2


def _selection_items(items):
    result = []
    for item in items or []:
        if isinstance(item, (list, tuple)):
            result.extend(item)
        else:
            result.append(item)
    return result


def _set_status(msg, error=False, warn=False):
    if warn:
        col = (240, 200, 60)
    elif error:
        col = (230, 80, 80)
    else:
        col = (100, 220, 100)
    if dpg.does_item_exist("txt_status"):
        dpg.set_value("txt_status", msg)
        dpg.configure_item("txt_status", color=col)


def _apply_layout():
    if not dpg.is_viewport_ok():
        return
    width = dpg.get_viewport_client_width()
    left_w = LEFT_WIDTH if left_visible[0] else 0
    right_w = RIGHT_WIDTH if right_visible[0] else 0
    center_width = max(MIN_CENTER_WIDTH, width - left_w - right_w - 38)
    if dpg.does_item_exist(SIDEBAR_TAG):
        dpg.configure_item(SIDEBAR_TAG, show=left_visible[0], width=LEFT_WIDTH)
    if dpg.does_item_exist(CENTER_PANEL_TAG):
        dpg.configure_item(CENTER_PANEL_TAG, width=center_width)
    if dpg.does_item_exist(properties_panel.PANEL_TAG):
        dpg.configure_item(properties_panel.PANEL_TAG,
                           show=right_visible[0], width=RIGHT_WIDTH)
    # Sinkronkan label toggle button
    if dpg.does_item_exist("btn_toggle_left"):
        dpg.configure_item("btn_toggle_left",
                           label="Hide Panel" if left_visible[0] else "Show Panel")
    if dpg.does_item_exist("btn_toggle_right"):
        dpg.configure_item("btn_toggle_right",
                           label="Hide Props" if right_visible[0] else "Show Props")
    if dpg.does_item_exist("menu_toggle_left"):
        dpg.set_value("menu_toggle_left", left_visible[0])
    if dpg.does_item_exist("menu_toggle_right"):
        dpg.set_value("menu_toggle_right", right_visible[0])


def _on_viewport_resize(sender, app_data):
    _apply_layout()


def _clear_results():
    state.clear_results()
    if dpg.does_item_exist("txt_results"):
        dpg.set_value("txt_results", "")
    visualization.clear_result_visuals()


def _delete_link(link_tag):
    state.links.pop(link_tag, None)
    state.line_data.pop(link_tag, None)
    state.mark_model_dirty()
    _clear_results()
    if dpg.does_item_exist(link_tag):
        dpg.delete_item(link_tag)


def _editor_field_is_active():
    focused = dpg.get_focused_item()
    if not focused or not dpg.does_item_exist(focused):
        return False
    try:
        item_type = str(dpg.get_item_type(focused))
    except Exception:
        return False
    return any(
        name in item_type
        for name in ("mvInput", "mvDrag", "mvSlider")
    )


def _property_editor_is_active():
    editing_item = getattr(properties_panel, "editing_item", [None])[0]
    if editing_item and dpg.does_item_exist(editing_item):
        try:
            if dpg.is_item_focused(editing_item) or dpg.is_item_active(editing_item):
                return True
        except Exception:
            pass
    if properties_panel.editing_field[0] and _editor_field_is_active():
        return True
    properties_panel.editing_field[0] = False
    if hasattr(properties_panel, "editing_item"):
        properties_panel.editing_item[0] = None
    return False


def _selected_canvas_nodes():
    if not dpg.does_item_exist("ne_canvas"):
        return []
    return [
        node_tag for node_tag in _selection_items(dpg.get_selected_nodes("ne_canvas"))
        if node_tag in state.nodes
    ]


def _selected_canvas_links():
    if not dpg.does_item_exist("ne_canvas"):
        return []
    return [
        link_tag for link_tag in _selection_items(dpg.get_selected_links("ne_canvas"))
        if link_tag in state.links
    ]


def _current_deletable_selection():
    selected_links = _selected_canvas_links()
    selected_nodes = _selected_canvas_nodes()

    if not selected_links and not selected_nodes:
        if state.selected_link[0] in state.links:
            selected_links = [state.selected_link[0]]
        elif state.selected_node[0] in state.nodes:
            selected_nodes = [state.selected_node[0]]

    return selected_links, selected_nodes


def _sync_canvas_selection():
    selected_links = _selected_canvas_links()
    for link_tag in selected_links:
        if link_tag in state.line_data:
            if state.selected_link[0] != link_tag:
                properties_panel.show_properties(link_tag=link_tag)
            return

    selected_nodes = _selected_canvas_nodes()
    if selected_nodes:
        node_tag = selected_nodes[-1]
        if state.selected_node[0] != node_tag:
            properties_panel.show_properties(node_tag)
        return

    if state.selected_node[0] not in state.nodes and state.selected_link[0] not in state.links:
        properties_panel.show_properties(None)


def _delete_canvas_selection(selected_links=None, selected_nodes=None):
    if selected_links is None or selected_nodes is None:
        selected_links, selected_nodes = _current_deletable_selection()
    if not selected_links and not selected_nodes:
        return False

    for link_tag in selected_links:
        _delete_link(link_tag)
    for node_tag in selected_nodes:
        components.delete_node(node_tag)

    _clear_results()
    if dpg.does_item_exist("ne_canvas"):
        dpg.clear_selected_links("ne_canvas")
        dpg.clear_selected_nodes("ne_canvas")
    properties_panel.show_properties(None)
    _set_status("Komponen terpilih dihapus.")
    return True


def cb_delete_selection(sender=None, app_data=None):
    # Cek dulu flag fokus yang dilaporkan properties_panel (cara robust),
    # baru fallback ke heuristic item-type.
    if _property_editor_is_active() or _editor_field_is_active():
        return
    selected_links, selected_nodes = _current_deletable_selection()
    if not selected_links and not selected_nodes:
        return
    _snapshot()
    _delete_canvas_selection(selected_links, selected_nodes)


def _capture_positions():
    out = {}
    for node_tag in state.nodes:
        if dpg.does_item_exist(node_tag):
            try:
                out[node_tag] = tuple(dpg.get_item_pos(node_tag))
            except Exception:
                pass
    return out


def _snapshot():
    state.push_undo(_capture_positions())


def _node_for_attr(attr_tag):
    return state.attr_to_node.get(attr_tag)


def _kind_for_attr(attr_tag):
    node_tag = _node_for_attr(attr_tag)
    return state.nodes.get(node_tag, {}).get("kind")


def _link_endpoint_labels(link_tag):
    fa, ta = state.links.get(link_tag, (None, None))
    fn = state.attr_to_node.get(fa)
    tn = state.attr_to_node.get(ta)
    f_label = state.nodes.get(fn, {}).get("label", "?")
    t_label = state.nodes.get(tn, {}).get("label", "?")
    return f_label, t_label


def _attr_ref(attr_tag, node_ids):
    node_tag = state.attr_to_node.get(attr_tag)
    nd = state.nodes.get(node_tag, {})
    for key in ATTR_KEYS:
        if nd.get(key) == attr_tag:
            return {"node": node_ids[node_tag], "attr": key}
    return None


def _is_single_terminal_attr(attr_tag):
    node_tag = _node_for_attr(attr_tag)
    nd = state.nodes.get(node_tag)
    if not nd:
        return False
    if nd["kind"] in ("gen", "load", "shunt"):
        return True
    if nd["kind"] == "trafo":
        return attr_tag in (nd.get("hv_pin"), nd.get("lv_pin"))
    return False


def _validate_link(from_attr, to_attr):
    fn = _node_for_attr(from_attr)
    tn = _node_for_attr(to_attr)
    if not fn or not tn:
        return False, "Pin tidak dikenal.", None
    if fn == tn:
        return False, "Tidak bisa menghubungkan pin dalam node yang sama.", None

    for lt, (fa, ta) in state.links.items():
        if (fa == from_attr and ta == to_attr) or (fa == to_attr and ta == from_attr):
            return False, "Koneksi ini sudah ada.", None

    fk = _kind_for_attr(from_attr)
    tk = _kind_for_attr(to_attr)
    kinds = {fk, tk}

    for attr in (from_attr, to_attr):
        if _is_single_terminal_attr(attr) and state.link_touches_attr(attr):
            return False, "Pin komponen itu sudah terhubung.", None

    if fk == "bus" and tk == "bus":
        from_is_out = (state.nodes[fn]["out_attr"] == from_attr)
        to_is_out = (state.nodes[tn]["out_attr"] == to_attr)
        if from_is_out != to_is_out:
            return True, "", "line"
        return False, "Koneksi bus-ke-bus harus menghubungkan Output dan Input.", None

    if "bus" in kinds and (kinds & {"gen", "load", "shunt"}):
        bus_node = fn if fk == "bus" else tn
        bus_attr = from_attr if fk == "bus" else to_attr
        comp_kind = tk if fk == "bus" else fk
        if comp_kind == "gen":
            if bus_attr == state.nodes[bus_node]["in_attr"]:
                return True, "", "component"
            return False, "Generator harus dihubungkan ke input bus.", None
        elif comp_kind in ("load", "shunt"):
            if bus_attr == state.nodes[bus_node]["out_attr"]:
                return True, "", "component"
            label = "Beban" if comp_kind == "load" else "Shunt"
            return False, f"{label} harus dihubungkan ke output bus.", None

    if "bus" in kinds and "trafo" in kinds:
        trafo_attr = from_attr if fk == "trafo" else to_attr
        bus_node = fn if fk == "bus" else tn
        bus_attr = from_attr if fk == "bus" else to_attr
        role = state.attr_role.get(trafo_attr)
        if role == "hv":
            if bus_attr == state.nodes[bus_node]["out_attr"]:
                return True, "", "trafo"
            return False, "Transformer HV harus dihubungkan ke output bus.", None
        elif role == "lv":
            if bus_attr == state.nodes[bus_node]["in_attr"]:
                return True, "", "trafo"
            return False, "Transformer LV harus dihubungkan ke input bus.", None
        return False, "Trafo harus memakai pin HV atau LV.", None

    return False, "Koneksi tidak valid untuk model pandapower.", None


def _add_link(from_attr, to_attr, line_values=None):
    ok, msg, link_kind = _validate_link(from_attr, to_attr)
    if not ok:
        _set_status(msg, error=True)
        return None

    link_tag = dpg.add_node_link(from_attr, to_attr, parent="ne_canvas")
    state.links[link_tag] = (from_attr, to_attr)
    if link_kind == "line":
        state.line_data[link_tag] = state.make_line_data(**(line_values or {}))
    state.mark_model_dirty()
    _clear_results()
    return link_tag


# Callbacks node editor
def cb_link(sender, app_data):
    from_attr, to_attr = app_data
    ok, msg, _ = _validate_link(from_attr, to_attr)
    if not ok:
        _set_status(msg, error=True)
        return
    _snapshot()
    link_tag = _add_link(from_attr, to_attr)
    if link_tag is not None:
        _set_status("Koneksi ditambahkan.")


def cb_delink(sender, app_data):
    link_tag = app_data[0] if isinstance(app_data, (list, tuple)) else app_data
    if link_tag not in state.links:
        return
    _snapshot()
    _delete_link(link_tag)
    if state.selected_link[0] == link_tag:
        properties_panel.show_properties(None)


# Sidebar callbacks
def _new_node_pos(kind="bus"):
    """Tempatkan node baru pada slot kosong agar tidak menabrak node lama."""
    existing_tags = [tag for tag in state.nodes if dpg.does_item_exist(tag)]
    existing = _node_positions(existing_tags)
    if not existing:
        return (80, 70)

    for row in range(12):
        for col in range(5):
            candidate = (80 + col * NODE_SLOT_X, 70 + row * NODE_SLOT_Y)
            if not _candidate_overlaps_existing(kind, candidate, existing_tags):
                return candidate

    right_edges = [_node_bounds(tag)[2] for tag in existing_tags]
    min_y = min(y for _, y in existing)
    return (max(right_edges, default=80) + NODE_GAP_X, min_y)


def _activate_new_node(node_tag, component_label):
    _clear_results()
    if dpg.does_item_exist("ne_canvas"):
        dpg.clear_selected_links("ne_canvas")
        dpg.clear_selected_nodes("ne_canvas")
    _resolve_node_collisions()
    properties_panel.show_properties(node_tag)
    _set_status(f"{component_label} ditambahkan.")


def cb_add_bus():
    _snapshot()
    buses = [v for v in state.nodes.values() if v["kind"] == "bus"]
    is_first_bus = not buses
    vn_kv = 20.0 if is_first_bus else 0.4
    # Label None lets create_bus_node use next_id("bus") for unique naming.
    node_tag = components.create_bus_node(
        label="Ext Grid" if is_first_bus else None,
        vn_kv=vn_kv,
        is_slack=is_first_bus,
        pos=_new_node_pos("bus"),
    )
    _activate_new_node(node_tag, "Bus")


def cb_add_gen():
    _snapshot()
    node_tag = components.create_gen_node(pos=_new_node_pos("gen"))
    _activate_new_node(node_tag, "Generator")


def cb_add_trafo():
    _snapshot()
    node_tag = components.create_trafo_node(pos=_new_node_pos("trafo"))
    _activate_new_node(node_tag, "Transformer")


def cb_add_shunt():
    _snapshot()
    node_tag = components.create_shunt_node(pos=_new_node_pos("shunt"))
    _activate_new_node(node_tag, "Shunt")


def cb_add_load():
    _snapshot()
    node_tag = components.create_load_node(pos=_new_node_pos("load"))
    _activate_new_node(node_tag, "Beban")


def _clear_canvas(status_msg="Canvas dikosongkan."):
    for lt in list(state.links.keys()):
        if dpg.does_item_exist(lt):
            dpg.delete_item(lt)
    for nt in list(state.nodes.keys()):
        if dpg.does_item_exist(nt):
            dpg.delete_item(nt)
    state.reset()
    properties_panel.show_properties(None)
    _clear_results()
    if status_msg:
        _set_status(status_msg)


def cb_clear():
    _snapshot()
    _clear_canvas()


def _confirm_action(title, message, on_confirm):
    """Tampilkan popup konfirmasi sebelum aksi destruktif."""
    popup_tag = dpg.generate_uuid()

    def _yes(s, a, u):
        dpg.delete_item(popup_tag)
        on_confirm()

    def _no(s, a, u):
        dpg.delete_item(popup_tag)

    with dpg.window(
        label=title, modal=True, tag=popup_tag,
        width=360, height=130, no_resize=True,
        no_close=True,
        pos=[
            dpg.get_viewport_client_width() // 2 - 180,
            dpg.get_viewport_client_height() // 2 - 65,
        ],
    ):
        dpg.add_text(message, wrap=340, color=(240, 220, 150))
        dpg.add_separator()
        with dpg.group(horizontal=True):
            dpg.add_button(label="  Ya, lanjutkan  ", callback=_yes, width=160)
            dpg.add_button(label="  Batal  ", callback=_no, width=160)


def _do_new_project():
    cb_clear()
    _set_status("Project baru siap.")


def cb_new_project():
    if state.nodes:
        _confirm_action(
            "Project Baru",
            "Semua komponen akan dihapus. Lanjutkan?",
            _do_new_project,
        )
    else:
        _do_new_project()


def _do_load_template():
    _snapshot()
    _clear_canvas(status_msg=None)
    _populate_demo()
    _resolve_node_collisions()
    properties_panel.show_properties(None)
    if dpg.is_viewport_ok():
        cb_zoom_fit()
        _resolve_node_collisions()
    _set_status("Template Four Load Branch dimuat.")


def cb_load_template():
    if state.nodes:
        _confirm_action(
            "Muat Template",
            "Semua komponen akan diganti dengan template. Lanjutkan?",
            _do_load_template,
        )
    else:
        _do_load_template()


def cb_validate_network():
    errors, warnings = engine.validate_model()
    if errors:
        _clear_results()
    lines = []
    if errors:
        lines.append("KESALAHAN")
        lines.extend(f"- {item}" for item in errors)
    if warnings:
        if lines:
            lines.append("")
        lines.append("PERINGATAN")
        lines.extend(f"- {item}" for item in warnings)
    if not lines:
        lines.append("Jaringan valid. Siap menjalankan Power Flow.")
    dpg.set_value("txt_results", "\n".join(lines))
    _set_status(
        "Jaringan belum valid." if errors else "Jaringan valid.",
        error=bool(errors),
    )


def _csv_write(path, rows):
    fieldnames = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def cb_export_results():
    node_results = state.last_results.get("nodes", {})
    link_results = state.last_results.get("links", {})
    if not node_results and not link_results:
        _set_status("Belum ada hasil. Jalankan Run Power Flow dulu.", error=True)
        return
    if state.results_are_stale():
        _set_status(
            "Hasil sudah tidak sesuai model. Jalankan Run Power Flow lagi sebelum export.",
            error=True,
        )
        return

    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        node_rows = []
        for node_tag, result in node_results.items():
            nd = state.nodes.get(node_tag, {})
            node_rows.append({
                "component": nd.get("label", str(node_tag)),
                "kind": nd.get("kind", ""),
                **result,
            })

        link_rows = []
        for link_tag, result in link_results.items():
            from_label, to_label = _link_endpoint_labels(link_tag)
            line = state.line_data.get(link_tag, {})
            link_rows.append({
                "component": line.get("label", f"{from_label} - {to_label}"),
                "from": from_label,
                "to": to_label,
                **result,
            })

        if node_rows:
            _csv_write(EXPORT_DIR / "node_results.csv", node_rows)
        if link_rows:
            _csv_write(EXPORT_DIR / "link_results.csv", link_rows)
        (EXPORT_DIR / "project_snapshot.json").write_text(
            json.dumps(_snapshot_model(), indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        _set_status(f"Gagal export hasil: {exc}", error=True)
        return
    _set_status("Hasil diekspor ke folder exports/")


def _node_snapshot(node_tag, node_id):
    nd = state.nodes[node_tag]
    item = {
        "id": node_id,
        "kind": nd["kind"],
        "label": nd["label"],
        "pos": dpg.get_item_pos(node_tag) if dpg.does_item_exist(node_tag) else [0, 0],
    }
    for key in [
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
    ]:
        if key in nd:
            item[key] = nd[key]
    return item


def _snapshot_model():
    node_ids = {node_tag: f"n{i}" for i, node_tag in enumerate(state.nodes)}
    nodes = [
        _node_snapshot(node_tag, node_id)
        for node_tag, node_id in node_ids.items()
    ]
    links = []
    for link_tag, (from_attr, to_attr) in state.links.items():
        from_ref = _attr_ref(from_attr, node_ids)
        to_ref = _attr_ref(to_attr, node_ids)
        if not from_ref or not to_ref:
            continue
        item = {"from": from_ref, "to": to_ref}
        if link_tag in state.line_data:
            item["line_data"] = dict(state.line_data[link_tag])
        links.append(item)
    return {"version": 1, "nodes": nodes, "links": links}


def cb_save_project():
    try:
        PROJECT_PATH.write_text(
            json.dumps(_snapshot_model(), indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        _set_status(f"Gagal menyimpan project: {exc}", error=True)
        return
    _set_status(f"Project disimpan: {PROJECT_PATH.name}")


def _create_node_from_snapshot(item):
    kind = item["kind"]
    pos = tuple(item.get("pos", (200, 200)))
    if kind == "bus":
        return components.create_bus_node(
            item.get("label"),
            vn_kv=item.get("vn_kv", 20.0),
            is_slack=item.get("is_slack", False),
            vm_pu=item.get("vm_pu", 1.0),
            va_degree=item.get("va_degree", 0.0),
            pos=pos,
        )
    if kind == "gen":
        return components.create_gen_node(
            item.get("label"),
            p_mw=item.get("p_mw", 1.0),
            q_mvar=item.get("q_mvar", 0.0),
            pos=pos,
        )
    if kind == "trafo":
        return components.create_trafo_node(
            item.get("label"),
            sn_mva=item.get("sn_mva", 10.0),
            vn_hv_kv=item.get("vn_hv_kv", 110.0),
            vn_lv_kv=item.get("vn_lv_kv", 20.0),
            vk_percent=item.get("vk_percent", 6.0),
            vkr_percent=item.get("vkr_percent", 0.5),
            pfe_kw=item.get("pfe_kw", 0.0),
            i0_percent=item.get("i0_percent", 0.0),
            pos=pos,
        )
    if kind == "shunt":
        return components.create_shunt_node(
            item.get("label"),
            p_mw=item.get("p_mw", 0.0),
            q_mvar=item.get("q_mvar", -1.0),
            pos=pos,
        )
    if kind == "load":
        return components.create_load_node(
            item.get("label"),
            p_mw=item.get("p_mw", 0.5),
            q_mvar=item.get("q_mvar", 0.1),
            pos=pos,
        )
    return None


def _validate_project_payload(data):
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
            allowed_attrs = PROJECT_ATTRS_BY_KIND.get(node_kinds.get(node_id), set())
            if attr not in allowed_attrs:
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
                return (
                    f"link ke-{index} memakai pin {attr} node {node_id} "
                    "yang sudah terhubung."
                )
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
            if comp_kind == "gen":
                # Generator pin is output, must connect to bus in_attr (input)
                valid_link = (bus_attr == "in_attr")
            elif comp_kind in ("load", "shunt"):
                # Load/shunt pin is input, must connect to bus out_attr (output)
                valid_link = (bus_attr == "out_attr")
        elif "bus" in kinds and "trafo" in kinds:
            trafo_attr = from_attr if from_kind == "trafo" else to_attr
            bus_attr = to_attr if from_kind == "trafo" else from_attr
            if trafo_attr == "hv_pin":
                # Trafo HV is input, must connect to bus out_attr (output)
                valid_link = (bus_attr == "out_attr")
            elif trafo_attr == "lv_pin":
                # Trafo LV is output, must connect to bus in_attr (input)
                valid_link = (bus_attr == "in_attr")
        if not valid_link:
            return f"link ke-{index} punya kombinasi koneksi yang tidak valid."
        if "line_data" in item and not isinstance(item["line_data"], dict):
            return f"link ke-{index} punya line_data tidak valid."

    return None


def cb_load_project():
    if not PROJECT_PATH.exists():
        _set_status(f"File belum ada: {PROJECT_PATH.name}", error=True)
        return
    try:
        data = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _set_status(f"Gagal membaca project: {exc}", error=True)
        return
    problem = _validate_project_payload(data)
    if problem:
        _set_status(f"Project tidak valid: {problem}", error=True)
        return

    _snapshot()
    _clear_canvas(status_msg=None)
    node_map = {}
    for item in data.get("nodes", []):
        node_tag = _create_node_from_snapshot(item)
        if node_tag is not None:
            node_map[item["id"]] = node_tag

    for item in data.get("links", []):
        from_node = node_map.get(item["from"]["node"])
        to_node = node_map.get(item["to"]["node"])
        if from_node is None or to_node is None:
            _set_status("Project gagal dimuat: node link tidak ditemukan.", error=True)
            return
        if from_node not in state.nodes or to_node not in state.nodes:
            _set_status("Project gagal dimuat: node link tidak valid.", error=True)
            return
        from_attr = state.nodes[from_node].get(item["from"]["attr"])
        to_attr = state.nodes[to_node].get(item["to"]["attr"])
        if from_attr and to_attr:
            if _add_link(from_attr, to_attr, item.get("line_data")) is None:
                _set_status("Project gagal dimuat: ada link yang tidak valid.", error=True)
                return

    properties_panel.show_properties(None)
    _resolve_node_collisions()
    _set_status(f"Project dimuat: {PROJECT_PATH.name}")


def cb_edit_selected_line():
    selected = _selected_canvas_links()
    for link_tag in selected:
        if link_tag in state.line_data:
            properties_panel.show_properties(link_tag=link_tag)
            _set_status("Line dipilih.")
            return
    _set_status("Pilih koneksi bus-ke-bus terlebih dahulu.", error=True)


def _summary_text(net, line_rows):
    line_loss_kw = net.res_line["pl_mw"].sum() * 1000 if len(net.line) else 0.0
    trafo_loss_kw = (
        net.res_trafo["pl_mw"].sum() * 1000 if len(net.trafo) else 0.0
    )
    total_load = net.load["p_mw"].sum() if len(net.load) else 0.0
    total_gen = net.sgen["p_mw"].sum() if len(net.sgen) else 0.0
    grid_p = (
        net.res_ext_grid["p_mw"].sum() if len(net.res_ext_grid) else 0.0
    )
    min_vm = net.res_bus["vm_pu"].min() if len(net.res_bus) else 0.0
    max_loading = max((row["loading"] for row in line_rows), default=0.0)

    return "\n".join([
        f"  Buses       : {len(net.bus)}",
        f"  Lines       : {len(net.line)}",
        f"  Trafos      : {len(net.trafo)}",
        f"  Loads       : {len(net.load)}",
        f"  Load P      : {total_load:.4f} MW",
        f"  SGen P      : {total_gen:.4f} MW",
        f"  Grid P      : {grid_p:.4f} MW",
        f"  Loss Line   : {line_loss_kw:.3f} kW",
        f"  Loss Trafo  : {trafo_loss_kw:.3f} kW",
        f"  V min       : {min_vm:.4f} pu",
        f"  Max loading : {max_loading:.1f} %",
    ])


def cb_run_pf():
    ok, msg, net, n2p, lmap = engine.run_pf()
    if not ok:
        _clear_results()
        if dpg.does_item_exist("txt_results"):
            dpg.set_value("txt_results", "KESALAHAN\n- " + msg.replace(" | ", "\n- "))
        _set_status(msg, error=True)
        return

    visualization.update_node_results(net, n2p)
    rows = visualization.update_line_results(net, lmap)
    _resolve_node_collisions()
    visualization.render_line_table(rows)
    dpg.set_value("txt_results", _summary_text(net, rows))
    if state.selected_link[0] is not None and state.selected_link[0] in state.links:
        properties_panel.show_properties(link_tag=state.selected_link[0])
    elif state.selected_node[0] is not None and state.selected_node[0] in state.nodes:
        properties_panel.show_properties(state.selected_node[0])
    _set_status("Konvergen", error=False)


def _rebuild_from_snapshot(snap):
    """Bersihkan canvas dan rebuild dari snapshot undo."""
    # Bersihkan DPG items
    for lt in list(state.links.keys()):
        if dpg.does_item_exist(lt):
            dpg.delete_item(lt)
    for nt in list(state.nodes.keys()):
        if dpg.does_item_exist(nt):
            dpg.delete_item(nt)
    state.reset()

    nodes_data = snap.get("nodes", {})
    links_data = snap.get("links", {})
    line_data = snap.get("line_data", {})
    positions = snap.get("positions", {})
    counters = snap.get("counters", {})

    # Mapping old node_tag -> new node_tag (DPG id baru saat dibuat ulang)
    new_node_by_old = {}
    # Mapping old attr_tag -> new attr_tag, lewat (new_node, role_key)
    old_attr_to_old_node = snap.get("attr_to_node", {})

    for old_tag, nd in nodes_data.items():
        kind = nd["kind"]
        pos = positions.get(old_tag, (200, 200))
        item = {
            "kind": kind,
            "label": nd.get("label"),
            "pos": tuple(pos),
        }
        for k in ("vn_kv", "is_slack", "vm_pu", "va_degree", "p_mw", "q_mvar",
                  "sn_mva", "vn_hv_kv", "vn_lv_kv", "vk_percent",
                  "vkr_percent", "pfe_kw", "i0_percent"):
            if k in nd:
                item[k] = nd[k]
        new_tag = _create_node_from_snapshot({**item, "id": old_tag})
        if new_tag is not None:
            new_node_by_old[old_tag] = new_tag

    # Re-create links: petakan old attr -> new attr lewat role key
    attr_key_lookup = {}
    for old_node, nd in nodes_data.items():
        for key in ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin"):
            if key in nd:
                attr_key_lookup[nd[key]] = (old_node, key)

    for old_link, (fa, ta) in links_data.items():
        f_old_node, f_key = attr_key_lookup.get(fa, (None, None))
        t_old_node, t_key = attr_key_lookup.get(ta, (None, None))
        if f_old_node is None or t_old_node is None:
            continue
        f_new = new_node_by_old.get(f_old_node)
        t_new = new_node_by_old.get(t_old_node)
        if f_new is None or t_new is None:
            continue
        from_attr = state.nodes[f_new].get(f_key)
        to_attr = state.nodes[t_new].get(t_key)
        if not from_attr or not to_attr:
            continue
        _add_link(from_attr, to_attr, line_data.get(old_link))

    # Restore counters di akhir setelah semua create_* selesai.
    for k, v in counters.items():
        state._counters[k] = v

    properties_panel.show_properties(None)
    _clear_results()
    _resolve_node_collisions()


def cb_undo(sender=None, app_data=None):
    # Jangan undo saat user sedang mengetik di properti
    if _property_editor_is_active():
        return
    snap = state.pop_undo()
    if snap is None:
        _set_status("Tidak ada langkah untuk di-undo.", error=True)
        return
    _rebuild_from_snapshot(snap)
    _set_status("Undo.")


def _key_press(sender, app_data):
    # Ctrl shortcuts: Z = undo, +/= zoom in, - zoom out, 0 zoom reset.
    try:
        ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
    except Exception:
        ctrl = False
    if not ctrl:
        return
    key = app_data
    if key == dpg.mvKey_Z:
        cb_undo()
    elif key in (dpg.mvKey_Plus, dpg.mvKey_NumPadEqual, dpg.mvKey_Add):
        cb_zoom_in()
    elif key in (dpg.mvKey_Minus, dpg.mvKey_Subtract):
        cb_zoom_out()
    elif key == dpg.mvKey_0:
        cb_zoom_reset()


def _mouse_wheel(sender, app_data):
    try:
        ctrl = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
    except Exception:
        ctrl = False
    if not ctrl:
        return
    if app_data > 0:
        cb_zoom_in()
    elif app_data < 0:
        cb_zoom_out()


_drag_start_positions = {}


def _mouse_click(sender, app_data):
    if state.nodes:
        _drag_start_positions.clear()
        _drag_start_positions.update(_capture_positions())


def _snap_node_positions():
    """Snap all node positions to a 20-pixel grid."""
    changed = False
    for node_tag in state.nodes:
        if dpg.does_item_exist(node_tag):
            try:
                x, y = dpg.get_item_pos(node_tag)
                snapped_x = round(x / 20.0) * 20.0
                snapped_y = round(y / 20.0) * 20.0
                if abs(x - snapped_x) > 0.1 or abs(y - snapped_y) > 0.1:
                    dpg.set_item_pos(node_tag, [snapped_x, snapped_y])
                    changed = True
            except Exception:
                pass
    return changed


def cb_auto_align(sender=None, app_data=None):
    """Align all nodes automatically and snap them to the grid."""
    if state.nodes:
        drag_start = _capture_positions()
        any_moved = _resolve_node_collisions()
        snapped = _snap_node_positions()
        if any_moved or snapped:
            state.push_undo(drag_start)
            _set_status("Komponen dirapikan otomatis.")


def _mouse_release(sender=None, app_data=None):
    if state.nodes:
        curr_pos = _capture_positions()
        snapped = _snap_node_positions()
        if snapped:
            curr_pos = _capture_positions()
            
        collisions_resolved = _resolve_node_collisions()
        if collisions_resolved:
            _snap_node_positions()
            curr_pos = _capture_positions()
            
        changed = False
        for node_tag, pos in curr_pos.items():
            old_pos = _drag_start_positions.get(node_tag)
            if old_pos is None or abs(old_pos[0] - pos[0]) > 0.1 or abs(old_pos[1] - pos[1]) > 0.1:
                changed = True
                break
        
        if changed and _drag_start_positions:
            state.push_undo(_drag_start_positions)
            _set_status("Posisi komponen disesuaikan.")
            _drag_start_positions.clear()


def _fmt_zoom():
    return f"{int(round(zoom_level[0] * 100))}%"


def _apply_node_zoom_theme():
    if not dpg.does_item_exist("ne_canvas"):
        return
    scale = zoom_level[0]
    
    show_details = (scale >= 0.75)
    for nd in state.nodes.values():
        for key in ("info_tag", "res_tag"):
            tag = nd.get(key)
            if tag and dpg.does_item_exist(tag):
                try:
                    dpg.configure_item(tag, show=show_details)
                except Exception:
                    pass

    if node_zoom_theme_tag[0] and dpg.does_item_exist(node_zoom_theme_tag[0]):
        dpg.delete_item(node_zoom_theme_tag[0])
    node_zoom_theme_tag[0] = dpg.generate_uuid()
    with dpg.theme(tag=node_zoom_theme_tag[0]):
        with dpg.theme_component(dpg.mvNodeEditor):
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_GridSpacing,
                max(10, int(32 * scale)),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_NodePadding,
                max(4, int(8 * scale)),
                max(3, int(6 * scale)),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_LinkThickness,
                max(1, int(2 * scale)),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_PinCircleRadius,
                max(3, int(4 * scale)),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_PinHoverRadius,
                max(5, int(8 * scale)),
                category=dpg.mvThemeCat_Nodes,
            )
            dpg.add_theme_style(
                dpg.mvNodeStyleVar_NodeBorderThickness,
                max(1, int(2 * scale)),
                category=dpg.mvThemeCat_Nodes,
            )
    dpg.bind_item_theme("ne_canvas", node_zoom_theme_tag[0])


def _update_zoom_ui():
    if dpg.does_item_exist("txt_zoom"):
        dpg.set_value("txt_zoom", _fmt_zoom())
    if dpg.does_item_exist("menu_zoom_label"):
        dpg.configure_item("menu_zoom_label", label=f"Zoom: {_fmt_zoom()}")
    _apply_node_zoom_theme()


def _node_positions(node_tags=None):
    tags = node_tags or state.nodes.keys()
    positions = []
    for node_tag in tags:
        if dpg.does_item_exist(node_tag):
            try:
                x, y = dpg.get_item_pos(node_tag)
                positions.append((float(x), float(y)))
            except Exception:
                pass
    return positions


def _node_spacing():
    scale = max(0.75, min(1.6, zoom_level[0]))
    return int(NODE_MIN_DX * scale), int(NODE_MIN_DY * scale)


def _split_text_lines(value):
    if value is None:
        return []
    return [line for line in str(value).splitlines() if line]


def _fallback_node_lines(kind, label=""):
    lines = [label] if label else []
    if kind == "bus":
        lines.extend(["Vn 0.4 kV", "V --", "va --", "IN"])
    elif kind == "gen":
        lines.extend(["GEN", "P 1.0 MW", "Q 0.0 MVAr"])
    elif kind == "trafo":
        lines.extend(["HV 110.0 kV", "S 10.0 MVA", "110.0/20.0 kV", "LV 20.0 kV"])
    elif kind == "shunt":
        lines.extend(["SHUNT", "P 0.0 MW", "Q -1.0 MVAr"])
    elif kind == "load":
        lines.extend(["LOAD", "P 0.5 MW", "Q 0.1 MVAr"])
    return lines


def _node_visible_lines(node_tag=None, kind=None):
    nd = state.nodes.get(node_tag, {}) if node_tag is not None else {}
    kind = kind or nd.get("kind", "bus")
    
    # Semantic zoom: if zoomed out significantly, hide auxiliary text lines
    is_zoomed_out = (zoom_level[0] < 0.75)
    if is_zoomed_out:
        return [nd.get("label", kind.upper())]

    lines = _fallback_node_lines(kind, nd.get("label", ""))
    for key in ("info_tag", "res_tag"):
        tag = nd.get(key)
        if tag and dpg.does_item_exist(tag):
            try:
                # Only include lines if the tag is shown
                if dpg.get_item_configuration(tag).get("show", True):
                    value_lines = _split_text_lines(dpg.get_value(tag))
                else:
                    value_lines = []
            except Exception:
                value_lines = []
            if value_lines:
                lines.extend(value_lines)
    return lines


def _estimated_node_size(node_tag=None, kind=None):
    nd = state.nodes.get(node_tag, {}) if node_tag is not None else {}
    kind = kind or nd.get("kind", "bus")
    min_w, min_h = NODE_KIND_MIN_SIZE.get(kind, (160, 100))
    lines = _node_visible_lines(node_tag, kind)
    max_len = max((len(line) for line in lines), default=12)
    line_count = max(len(lines), 2)
    scale = zoom_level[0]
    width = int(max(min_w, max_len * NODE_TEXT_W + 58) * scale)
    height = int(max(min_h, line_count * NODE_LINE_H + 34) * scale)
    return width, height


def _node_size(node_tag):
    fallback_w, fallback_h = _estimated_node_size(node_tag)
    if dpg.does_item_exist(node_tag):
        try:
            width, height = dpg.get_item_rect_size(node_tag)
        except Exception:
            width, height = 0, 0
        if width > 20 and height > 20:
            return max(float(width), fallback_w), max(float(height), fallback_h)
    return float(fallback_w), float(fallback_h)


def _candidate_size(kind):
    width, height = _estimated_node_size(kind=kind)
    return float(width), float(height)


def _node_bounds(node_tag, pos=None):
    if pos is None:
        pos = dpg.get_item_pos(node_tag)
    x, y = float(pos[0]), float(pos[1])
    width, height = _node_size(node_tag)
    return (x, y, x + width, y + height)


def _candidate_bounds(kind, pos):
    x, y = float(pos[0]), float(pos[1])
    width, height = _candidate_size(kind)
    return (x, y, x + width, y + height)


def _bounds_overlap(bounds_a, bounds_b, gap_x=NODE_GAP_X, gap_y=NODE_GAP_Y):
    return not (
        bounds_a[2] + gap_x <= bounds_b[0]
        or bounds_b[2] + gap_x <= bounds_a[0]
        or bounds_a[3] + gap_y <= bounds_b[1]
        or bounds_b[3] + gap_y <= bounds_a[1]
    )


def _nodes_overlap(tag_a, tag_b, pos_a=None, pos_b=None):
    return _bounds_overlap(
        _node_bounds(tag_a, pos_a),
        _node_bounds(tag_b, pos_b),
    )


def _candidate_overlaps_existing(kind, candidate, existing_tags):
    candidate_bounds = _candidate_bounds(kind, candidate)
    return any(
        _bounds_overlap(candidate_bounds, _node_bounds(tag))
        for tag in existing_tags
        if dpg.does_item_exist(tag)
    )


def _collision_row_limits(positions):
    row_left = min((pos[0] for pos in positions.values()), default=80.0)
    row_left = max(40.0, row_left)
    canvas_width = 0
    if dpg.does_item_exist(CANVAS_PANEL_TAG):
        try:
            canvas_width = dpg.get_item_width(CANVAS_PANEL_TAG)
        except Exception:
            canvas_width = 0
    usable_width = max(float(canvas_width) - 160.0, 900.0)
    return row_left, row_left + usable_width


def _vertical_ranges_overlap(y, height, bounds, gap_y=NODE_GAP_Y):
    return not (y + height + gap_y <= bounds[1] or bounds[3] + gap_y <= y)


def _find_open_collision_position(tag, preferred, placed_bounds, row_left, row_right):
    width, height = _node_size(tag)
    preferred_x, preferred_y = preferred

    def is_free(x, y):
        bounds = (x, y, x + width, y + height)
        if bounds[2] > row_right:
            return False
        return all(not _bounds_overlap(bounds, other) for other in placed_bounds.values())

    if is_free(preferred_x, preferred_y):
        return preferred_x, preferred_y

    rows = {preferred_y}
    rows.update(bounds[1] for bounds in placed_bounds.values())
    rows = sorted(rows, key=lambda row: (abs(row - preferred_y), row))

    max_bottom = max((bounds[3] for bounds in placed_bounds.values()), default=preferred_y)
    row_step = max(height + NODE_GAP_Y, NODE_MIN_DY)
    rows.extend(max_bottom + NODE_GAP_Y + row_step * i for i in range(len(placed_bounds) + 2))

    for y in rows:
        x_values = {row_left}
        if abs(y - preferred_y) < 1e-6:
            x_values.add(preferred_x)
        for bounds in placed_bounds.values():
            if _vertical_ranges_overlap(y, height, bounds):
                x_values.add(bounds[2] + NODE_GAP_X)
        for x in sorted(x_values):
            if x < row_left:
                continue
            if is_free(x, y):
                return x, y

    return row_left, max_bottom + NODE_GAP_Y


def _resolve_node_collisions():
    """Geser node yang overlap memakai ukuran node aktual/fallback."""
    tags = [tag for tag in state.nodes if dpg.does_item_exist(tag)]
    if len(tags) < 2:
        return False
    positions = {}
    for tag in tags:
        try:
            x, y = dpg.get_item_pos(tag)
            positions[tag] = [float(x), float(y)]
        except Exception:
            continue

    changed = False
    row_left, row_right = _collision_row_limits(positions)
    placed_bounds = {}
    for tag in tags:
        if tag not in positions:
            continue
        original = tuple(positions[tag])
        x, y = _find_open_collision_position(
            tag,
            original,
            placed_bounds,
            row_left,
            row_right,
        )
        if (x, y) != original:
            positions[tag] = [x, y]
            try:
                dpg.set_item_pos(tag, [x, y])
                changed = True
            except Exception:
                pass
        placed_bounds[tag] = _node_bounds(tag, (x, y))
    return changed


def _zoom_anchor():
    selected = _selected_canvas_nodes()
    positions = _node_positions(selected) or _node_positions()
    if not positions:
        return (0.0, 0.0)
    min_x = min(x for x, _ in positions)
    max_x = max(x for x, _ in positions)
    min_y = min(y for _, y in positions)
    max_y = max(y for _, y in positions)
    return ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)


def _apply_zoom(new_zoom, anchor=None):
    new_zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
    ratio = new_zoom / zoom_level[0]
    if abs(ratio - 1.0) < 1e-6:
        return
    anchor_x, anchor_y = anchor or _zoom_anchor()
    for node_tag in state.nodes:
        if dpg.does_item_exist(node_tag):
            try:
                x, y = dpg.get_item_pos(node_tag)
                dpg.set_item_pos(
                    node_tag,
                    [
                        anchor_x + (x - anchor_x) * ratio,
                        anchor_y + (y - anchor_y) * ratio,
                    ],
                )
            except Exception:
                pass
    zoom_level[0] = new_zoom
    _update_zoom_ui()
    _resolve_node_collisions()
    _set_status(f"Zoom: {_fmt_zoom()}")


def cb_zoom_in():
    _apply_zoom(zoom_level[0] * ZOOM_STEP)


def cb_zoom_out():
    _apply_zoom(zoom_level[0] / ZOOM_STEP)


def cb_zoom_reset():
    _apply_zoom(1.0)


def cb_zoom_fit():
    positions = _node_positions()
    if not positions:
        _set_status("Belum ada komponen untuk di-fit.", error=True)
        return

    min_x = min(x for x, _ in positions)
    max_x = max(x for x, _ in positions)
    min_y = min(y for _, y in positions)
    max_y = max(y for _, y in positions)
    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)

    canvas_w = max(dpg.get_item_width(CANVAS_PANEL_TAG) - 180, 320)
    canvas_h = max(dpg.get_item_height(CANVAS_PANEL_TAG) - 140, 240)
    target_zoom = max(
        ZOOM_MIN,
        min(ZOOM_MAX, min(canvas_w / width, canvas_h / height, 1.0)),
    )
    anchor = ((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
    _apply_zoom(target_zoom, anchor=anchor)

    new_positions = _node_positions()
    if not new_positions:
        return
    shift_x = 80 - min(x for x, _ in new_positions)
    shift_y = 50 - min(y for _, y in new_positions)
    for node_tag in state.nodes:
        if dpg.does_item_exist(node_tag):
            try:
                x, y = dpg.get_item_pos(node_tag)
                dpg.set_item_pos(node_tag, [x + shift_x, y + shift_y])
            except Exception:
                pass
    _resolve_node_collisions()
    _set_status(f"Fit view: {_fmt_zoom()}")


def cb_toggle_left():
    left_visible[0] = not left_visible[0]
    _apply_layout()


def cb_toggle_right():
    right_visible[0] = not right_visible[0]
    _apply_layout()


def cb_menu_toggle_left(sender, app_data=None):
    left_visible[0] = bool(app_data)
    _apply_layout()


def cb_menu_toggle_right(sender, app_data=None):
    right_visible[0] = bool(app_data)
    _apply_layout()


# Build UI
def build_ui():
    with dpg.handler_registry(tag="global_handlers"):
            dpg.add_key_press_handler(dpg.mvKey_Back, callback=cb_delete_selection)
            dpg.add_key_press_handler(dpg.mvKey_Delete, callback=cb_delete_selection)
            dpg.add_key_press_handler(callback=_key_press)
            dpg.add_mouse_wheel_handler(callback=_mouse_wheel)
            dpg.add_mouse_click_handler(callback=_mouse_click)
            dpg.add_mouse_release_handler(callback=_mouse_release)

    with dpg.window(tag="w_main", no_title_bar=True, no_move=True,
                    no_resize=True):
        with dpg.child_window(height=TOOLBAR_HEIGHT, border=True,
                              tag=TOOLBAR_TAG, width=-1):
            with dpg.menu_bar():
                with dpg.menu(label="KOMPONEN"):
                    dpg.add_menu_item(label="Tambah Bus", callback=cb_add_bus)
                    dpg.add_menu_item(label="Tambah Generator", callback=cb_add_gen)
                    dpg.add_menu_item(label="Tambah Transformer", callback=cb_add_trafo)
                    dpg.add_menu_item(label="Tambah Shunt", callback=cb_add_shunt)
                    dpg.add_menu_item(label="Tambah Beban", callback=cb_add_load)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Edit Saluran Terpilih",
                                     callback=cb_edit_selected_line)

                with dpg.menu(label="BERKAS"):
                    dpg.add_menu_item(label="Project Baru", callback=cb_new_project)
                    dpg.add_menu_item(label="Muat Template", callback=cb_load_template)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Simpan Project", callback=cb_save_project)
                    dpg.add_menu_item(label="Muat Project", callback=cb_load_project)
                    dpg.add_menu_item(label="Ekspor Hasil", callback=cb_export_results)

                with dpg.menu(label="EDIT"):
                    dpg.add_menu_item(label="Undo", shortcut="Ctrl+Z", callback=cb_undo)

                with dpg.menu(label="TAMPILAN"):
                    dpg.add_menu_item(
                        label="Panel Kiri",
                        tag="menu_toggle_left",
                        check=True,
                        default_value=True,
                        callback=cb_menu_toggle_left,
                    )
                    dpg.add_menu_item(
                        label="Panel Properti",
                        tag="menu_toggle_right",
                        check=True,
                        default_value=True,
                        callback=cb_menu_toggle_right,
                    )
                    dpg.add_separator()
                    dpg.add_menu_item(label="Perbesar", shortcut="Ctrl++",
                                     callback=cb_zoom_in)
                    dpg.add_menu_item(label="Perkecil", shortcut="Ctrl+-",
                                     callback=cb_zoom_out)
                    dpg.add_menu_item(label="Reset Zoom", shortcut="Ctrl+0",
                                     callback=cb_zoom_reset)
                    dpg.add_menu_item(label="Sesuaikan Tampilan",
                                     callback=cb_zoom_fit)
                    dpg.add_menu_item(label="Zoom: 100%",
                                     tag="menu_zoom_label", enabled=False)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Hide Panel", tag="btn_toggle_left",
                               callback=cb_toggle_left, width=94)
                dpg.add_button(label="Hide Props", tag="btn_toggle_right",
                               callback=cb_toggle_right, width=90)
                dpg.add_text(" ", color=(50, 50, 50))
                dpg.add_text("Komponen", color=(180, 180, 180))
                dpg.add_button(label="Bus", callback=cb_add_bus, width=58)
                dpg.add_button(label="Gen", callback=cb_add_gen, width=58)
                dpg.add_button(label="Trafo", callback=cb_add_trafo, width=68)
                dpg.add_button(label="Shunt", callback=cb_add_shunt, width=68)
                dpg.add_button(label="Beban", callback=cb_add_load, width=70)
                dpg.add_text(" ", color=(50, 50, 50))
                dpg.add_button(label="Undo", callback=cb_undo, width=52)
                dpg.add_text(" ", color=(50, 50, 50))
                dpg.add_button(label="-", callback=cb_zoom_out, width=26)
                dpg.add_text("100%", tag="txt_zoom", color=(255, 210, 50))
                dpg.add_button(label="+", callback=cb_zoom_in, width=26)
                dpg.add_button(label="Reset", callback=cb_zoom_reset, width=50)
                dpg.add_button(label="Fit", callback=cb_zoom_fit, width=36)
                dpg.add_text(" ", color=(50, 50, 50))
                dpg.add_button(label="Auto-Align", callback=cb_auto_align, width=90)
                dpg.add_text(" ", color=(50, 50, 50))
                dpg.add_button(label="Run Power Flow",
                               callback=cb_run_pf, width=190)
                dpg.add_button(label="Validasi",
                               callback=cb_validate_network, width=80)
                dpg.add_text(" ", color=(50, 50, 50))
                dpg.add_text("Siap", tag="txt_status",
                             color=(130, 130, 130))

        with dpg.group(horizontal=True, tag=BODY_TAG):

            with dpg.child_window(width=LEFT_WIDTH, border=True,
                                  tag=SIDEBAR_TAG):
                dpg.add_text("Analisis", color=(180, 180, 180))
                dpg.add_button(label="  Validasi Jaringan", width=-1,
                               callback=cb_validate_network)
                dpg.add_button(label="  Jalankan Power Flow", width=-1,
                               callback=cb_run_pf)
                dpg.add_button(label="  Edit Saluran Dipilih", width=-1,
                               callback=cb_edit_selected_line)
                dpg.add_text("", tag="txt_results", wrap=215)
                dpg.add_separator()

                dpg.add_text("Project", color=(180, 180, 180))
                dpg.add_button(label="  Project Baru", width=-1,
                               callback=cb_new_project)
                dpg.add_button(label="  Muat Template", width=-1,
                               callback=cb_load_template)
                dpg.add_button(label="  Simpan Project", width=-1,
                               callback=cb_save_project)
                dpg.add_button(label="  Muat Project", width=-1,
                               callback=cb_load_project)
                dpg.add_button(label="  Ekspor Hasil", width=-1,
                               callback=cb_export_results)
                dpg.add_separator()

                dpg.add_button(label="  Undo (Ctrl+Z)", width=-1,
                               callback=cb_undo)

            with dpg.child_window(width=900, border=False,
                                  tag=CENTER_PANEL_TAG):
                with dpg.child_window(border=False, height=-190,
                                      width=-1, tag=CANVAS_PANEL_TAG):
                    with dpg.node_editor(
                        tag="ne_canvas",
                        callback=cb_link,
                        delink_callback=cb_delink,
                        minimap=True,
                        minimap_location=dpg.mvNodeMiniMap_Location_BottomRight,
                    ):
                        pass
                with dpg.child_window(border=True, height=-1, width=-1,
                                      tag=RESULTS_PANEL_TAG):
                    dpg.add_text("Hasil Saluran / Trafo",
                                 color=(180, 180, 180))
                    with dpg.table(tag="tbl_lines", header_row=True,
                                   resizable=True, borders_innerH=True,
                                   borders_outerH=True, borders_innerV=True,
                                   borders_outerV=True):
                        dpg.add_table_column(label="Nama")
                        dpg.add_table_column(label="Tipe")
                        dpg.add_table_column(label="Daya aktif")
                        dpg.add_table_column(label="Daya reaktif")
                        dpg.add_table_column(label="Rugi-rugi")
                        dpg.add_table_column(label="Pembebanan")

            with dpg.child_window(width=RIGHT_WIDTH, border=True,
                                  tag=properties_panel.PANEL_TAG):
                pass

    _update_zoom_ui()
    properties_panel.show_properties(None)


def _populate_demo():
    """Jaringan radial mirip Four Load Branch: grid, trafo, 4 line, 4 load."""
    b0 = components.create_bus_node("Ext Grid", vn_kv=10.0, is_slack=True,
                                    pos=(60, 300))
    t0 = components.create_trafo_node(
        "Trafo 10/0.4 kV", sn_mva=0.25, vn_hv_kv=10.0, vn_lv_kv=0.4,
        vk_percent=4.0, vkr_percent=1.2, pos=(310, 300),
    )
    b1 = components.create_bus_node("Bus 1", vn_kv=0.4, pos=(590, 300))
    b2 = components.create_bus_node("Bus 2", vn_kv=0.4, pos=(860, 80))
    b3 = components.create_bus_node("Bus 3", vn_kv=0.4, pos=(860, 230))
    b4 = components.create_bus_node("Bus 4", vn_kv=0.4, pos=(860, 380))
    b5 = components.create_bus_node("Bus 5", vn_kv=0.4, pos=(860, 530))

    _add_link(state.nodes[b0]["out_attr"], state.nodes[t0]["hv_pin"])
    _add_link(state.nodes[t0]["lv_pin"], state.nodes[b1]["in_attr"])

    line_values = {
        "length_km": 0.05,
        "r_ohm_per_km": 0.225,
        "x_ohm_per_km": 0.08,
        "c_nf_per_km": 264.0,
        "max_i_ka": 0.242,
    }
    for i, (from_bus, to_bus) in enumerate([
        (b1, b2),
        (b2, b3),
        (b3, b4),
        (b4, b5),
    ], start=1):
        _add_link(
            state.nodes[from_bus]["out_attr"],
            state.nodes[to_bus]["in_attr"],
            {**line_values, "label": f"Line {i}"},
        )

    for i, (bus, pos) in enumerate([
        (b2, (1210, 80)),
        (b3, (1210, 230)),
        (b4, (1210, 380)),
        (b5, (1210, 530)),
    ], start=1):
        load = components.create_load_node(
            label=f"Load {i}", p_mw=0.03, q_mvar=0.01, pos=pos,
        )
        _add_link(state.nodes[bus]["out_attr"], state.nodes[load]["pin"])


def main():
    dpg.create_context()
    # Hubungkan capture posisi ke properties_panel agar snapshot pre-edit
    # juga mengingat posisi node di canvas.
    properties_panel.take_snapshot = _snapshot
    build_ui()
    _set_status("Siap. Tambahkan komponen untuk mulai.")

    dpg.create_viewport(
        title="Grid Simulator",
        width=1480, height=820,
        min_width=900, min_height=560,
    )
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("w_main", True)
    dpg.set_viewport_resize_callback(_on_viewport_resize)
    _apply_layout()
    while dpg.is_dearpygui_running():
        _sync_canvas_selection()
        dpg.render_dearpygui_frame()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
