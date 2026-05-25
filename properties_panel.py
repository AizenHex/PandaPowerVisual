"""
Panel kanan untuk inspect dan edit detail node atau line yang dipilih.
"""
import dearpygui.dearpygui as dpg

import state
import components
import visualization


PANEL_TAG = "right_panel"

# Flag global: True bila salah satu input field properti sedang fokus / aktif.
# Dipakai cb_delete_selection di app.py supaya Backspace tidak menghapus node
# saat user sedang mengetik di property panel.
editing_field: list = [False]
editing_item: list = [None]


HELP_TEXT = {
    "bus": [
        ("vn_kv", "tegangan nominal bus (kV)"),
        ("is_slack", "tandai bus ini sebagai Ext Grid / Slack (referensi)"),
        ("vm_pu", "magnitudo tegangan (per-unit) saat slack"),
        ("va_degree", "sudut tegangan (derajat) saat slack"),
    ],
    "gen": [
        ("p_mw", "daya aktif yang diinjeksikan generator (MW, positif=injeksi)"),
        ("q_mvar", "daya reaktif generator (MVAr)"),
    ],
    "load": [
        ("p_mw", "daya aktif beban (MW, positif=konsumsi)"),
        ("q_mvar", "daya reaktif beban (MVAr)"),
    ],
    "shunt": [
        ("p_mw", "rugi aktif shunt (MW)"),
        ("q_mvar", "daya reaktif shunt (MVAr, negatif=kapasitif)"),
    ],
    "trafo": [
        ("sn_mva", "kapasitas daya semu trafo (MVA)"),
        ("vn_hv_kv", "tegangan nominal sisi HV (kV)"),
        ("vn_lv_kv", "tegangan nominal sisi LV (kV)"),
        ("vk_percent", "tegangan hubung-singkat / impedance trafo (%)"),
        ("vkr_percent", "komponen resistif dari vk_percent, mewakili rugi tembaga (%)"),
        ("pfe_kw", "rugi besi / iron loss (kW)"),
        ("i0_percent", "arus magnetisasi tanpa beban (%)"),
    ],
    "line": [
        ("length_km", "panjang saluran (km)"),
        ("r_ohm_per_km", "resistansi per kilometer (ohm/km)"),
        ("x_ohm_per_km", "reaktansi per kilometer (ohm/km)"),
        ("c_nf_per_km", "kapasitansi per kilometer (nF/km)"),
        ("max_i_ka", "arus maksimum yang diizinkan (kA)"),
    ],
}


def _attach_focus_tracker(item, snapshot_cb=None):
    """Pasang handler agar editing_field aktif selagi item difokuskan.

    snapshot_cb (opsional) dipanggil sekali saat field pertama mendapat fokus,
    untuk menyimpan snapshot undo sebelum nilai diedit.
    """
    snapped = {"done": False}

    def on_focus(sender, app_data, user_data):
        editing_field[0] = True
        editing_item[0] = item
        if snapshot_cb and not snapped["done"]:
            snapshot_cb()
            snapped["done"] = True

    def on_deactivate(sender, app_data, user_data):
        editing_field[0] = False
        if editing_item[0] == item:
            editing_item[0] = None
        snapped["done"] = False

    with dpg.item_handler_registry() as reg:
        dpg.add_item_focus_handler(callback=on_focus)
        dpg.add_item_deactivated_handler(callback=on_deactivate)
    dpg.bind_item_handler_registry(item, reg)


# Hook yang di-set oleh app.py untuk menyediakan capture posisi node DPG.
# Default: snapshot tanpa posisi (cocok untuk test/headless).
def _default_snapshot():
    state.push_undo({})


take_snapshot = _default_snapshot

NODE_SPEC_KEYS = {
    "bus": [
        ("vn_kv", "Tegangan nominal", "kV"),
        ("is_slack", "Slack / ext grid", ""),
        ("vm_pu", "Setpoint tegangan slack", "pu"),
        ("va_degree", "Sudut tegangan slack", "deg"),
    ],
    "gen": [
        ("p_mw", "Injeksi daya aktif", "MW"),
        ("q_mvar", "Injeksi daya reaktif", "MVAr"),
    ],
    "load": [
        ("p_mw", "Beban daya aktif", "MW"),
        ("q_mvar", "Beban daya reaktif", "MVAr"),
    ],
    "shunt": [
        ("p_mw", "Rugi aktif", "MW"),
        ("q_mvar", "Injeksi daya reaktif", "MVAr"),
    ],
    "trafo": [
        ("sn_mva", "Kapasitas daya semu", "MVA"),
        ("vn_hv_kv", "Tegangan nominal HV", "kV"),
        ("vn_lv_kv", "Tegangan nominal LV", "kV"),
        ("vk_percent", "Tegangan hubung singkat", "%"),
        ("vkr_percent", "Komponen rugi tembaga", "%"),
        ("pfe_kw", "Rugi besi", "kW"),
        ("i0_percent", "Arus tanpa beban", "%"),
    ],
}

RESULT_LABELS = {
    "vm_pu": ("Tegangan", "pu"),
    "va_degree": ("Sudut", "deg"),
    "p_mw": ("P", "MW"),
    "q_mvar": ("Q", "MVAr"),
    "p_from_mw": ("P dari sisi awal", "MW"),
    "q_from_mvar": ("Q dari sisi awal", "MVAr"),
    "p_to_mw": ("P ke sisi akhir", "MW"),
    "q_to_mvar": ("Q ke sisi akhir", "MVAr"),
    "p_hv_mw": ("P HV", "MW"),
    "q_hv_mvar": ("Q HV", "MVAr"),
    "p_lv_mw": ("P LV", "MW"),
    "q_lv_mvar": ("Q LV", "MVAr"),
    "pl_mw": ("Rugi aktif", "MW"),
    "ql_mvar": ("Rugi reaktif", "MVAr"),
    "i_from_ka": ("Arus sisi awal", "kA"),
    "i_to_ka": ("Arus sisi akhir", "kA"),
    "i_hv_ka": ("Arus HV", "kA"),
    "i_lv_ka": ("Arus LV", "kA"),
    "loading_percent": ("Loading", "%"),
}

KIND_LABELS = {
    "bus": "Bus",
    "gen": "Generator",
    "load": "Beban",
    "shunt": "Shunt",
    "trafo": "Transformer",
    "line": "Saluran",
}

ATTR_LABELS = {
    "out_attr": "Port bus",
    "in_attr": "Port bus",
    "pin": "Pin komponen",
    "hv_pin": "Sisi HV",
    "lv_pin": "Sisi LV",
}

FIELD_META = {
    "label": ("Nama komponen", "", "nama yang tampil di node editor"),
    "vn_kv": ("Tegangan nominal bus", "kV", "samakan dengan level tegangan bus"),
    "is_slack": ("Slack / external grid", "", "satu bus acuan untuk power flow"),
    "vm_pu": ("Setpoint tegangan slack", "pu", "biasanya 1.0 pu"),
    "va_degree": ("Sudut tegangan slack", "deg", "biasanya 0 derajat"),
    "p_mw": ("Daya aktif", "MW", "positif untuk beban/generator sesuai jenis komponen"),
    "q_mvar": ("Daya reaktif", "MVAr", "negatif berarti kapasitif untuk shunt"),
    "sn_mva": ("Kapasitas transformer", "MVA", "rating daya semu transformer"),
    "vn_hv_kv": ("Tegangan sisi HV", "kV", "harus cocok dengan bus sisi tegangan tinggi"),
    "vn_lv_kv": ("Tegangan sisi LV", "kV", "harus cocok dengan bus sisi tegangan rendah"),
    "vk_percent": ("Impedansi hubung singkat", "%", "nilai total impedansi transformer"),
    "vkr_percent": ("Komponen resistif", "%", "harus lebih kecil atau sama dengan vk_percent"),
    "pfe_kw": ("Rugi besi", "kW", "boleh 0 bila data tidak tersedia"),
    "i0_percent": ("Arus tanpa beban", "%", "boleh 0 bila data tidak tersedia"),
    "length_km": ("Panjang saluran", "km", "harus lebih dari 0"),
    "r_ohm_per_km": ("Resistansi per km", "ohm/km", "tidak boleh negatif"),
    "x_ohm_per_km": ("Reaktansi per km", "ohm/km", "tidak boleh negatif"),
    "c_nf_per_km": ("Kapasitansi per km", "nF/km", "boleh 0 untuk pendekatan sederhana"),
    "max_i_ka": ("Arus maksimum", "kA", "dipakai untuk menghitung loading saluran"),
}


def _clear_panel():
    if dpg.does_item_exist(PANEL_TAG):
        for child in dpg.get_item_children(PANEL_TAG, 1) or []:
            dpg.delete_item(child)


def _fmt(value):
    if isinstance(value, bool):
        return "Ya" if value else "Tidak"
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:.2f}"
        if abs(value) >= 1:
            return f"{value:.4f}"
        return f"{value:.6f}"
    return str(value)


def _section(title):
    dpg.add_separator(parent=PANEL_TAG)
    dpg.add_text(title, parent=PANEL_TAG, color=(255, 210, 50))


def _row(label, value, unit="", color=(200, 200, 200)):
    suffix = f" {unit}" if unit else ""
    dpg.add_text(f"{label}: {_fmt(value)}{suffix}",
                 parent=PANEL_TAG, color=color, wrap=250)


def _kind_label(kind):
    return KIND_LABELS.get(kind, kind)


def _field_meta(key):
    return FIELD_META.get(key, (key, "", ""))


def _set_dirty_status():
    if dpg.does_item_exist("txt_status"):
        dpg.set_value("txt_status", "Model berubah. Jalankan Power Flow lagi.")
        dpg.configure_item("txt_status", color=(240, 200, 60))
    # Juga update properties panel jika ada yang dipilih
    if state.selected_node[0] in state.nodes:
        _show_stale_notice()
    elif state.selected_link[0] in state.links:
        _show_stale_notice()


def _show_stale_notice():
    """Re-render selected panel so stale numeric results disappear immediately."""
    if not dpg.does_item_exist(PANEL_TAG):
        return
    selected_link = state.selected_link[0]
    selected_node = state.selected_node[0]
    if selected_link in state.links:
        show_properties(link_tag=selected_link)
    elif selected_node in state.nodes:
        show_properties(selected_node)


def _clear_stale_results():
    state.clear_results()
    if dpg.does_item_exist("txt_results"):
        dpg.set_value("txt_results", "")
    visualization.clear_result_visuals()


def _mark_model_dirty_from_panel():
    state.mark_model_dirty()
    _clear_stale_results()
    _set_dirty_status()


def _make_node_setter(node_tag, key, cast=float, after=None):
    def _cb(sender, app_data):
        nd = state.nodes.get(node_tag)
        if not nd:
            return
        try:
            value = cast(app_data)
        except Exception:
            return
        if nd.get(key) == value:
            return
        nd[key] = value
        if after:
            after(node_tag, key)
        components.refresh_node_visual(node_tag)
        _mark_model_dirty_from_panel()
    return _cb


def _make_line_setter(link_tag, key, cast=float):
    def _cb(sender, app_data):
        data = state.line_data.get(link_tag)
        if not data:
            return
        try:
            value = cast(app_data)
        except Exception:
            return
        if data.get(key) == value:
            return
        data[key] = value
        _mark_model_dirty_from_panel()
    return _cb


def _only_one_slack(node_tag, key):
    nd = state.nodes.get(node_tag)
    if not nd or key != "is_slack" or not nd.get("is_slack"):
        return
    for other_tag, other in state.nodes.items():
        if other_tag != node_tag and other.get("kind") == "bus":
            if other.get("is_slack"):
                other["is_slack"] = False
                components.refresh_node_visual(other_tag)
                state.mark_model_dirty()


def _delete_node_cb(sender, app_data, user_data):
    take_snapshot()
    components.delete_node(user_data)
    _clear_stale_results()
    _set_dirty_status()
    show_properties(None)


def _delete_line_cb(sender, app_data, user_data):
    take_snapshot()
    state.links.pop(user_data, None)
    state.line_data.pop(user_data, None)
    _mark_model_dirty_from_panel()
    if dpg.does_item_exist(user_data):
        dpg.delete_item(user_data)
    show_properties(None)


def _node_attrs(node_tag):
    nd = state.nodes.get(node_tag, {})
    return {
        nd[key]
        for key in ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin")
        if key in nd
    }


def _attr_name(node_tag, attr_tag):
    nd = state.nodes.get(node_tag, {})
    for key in ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin"):
        if nd.get(key) == attr_tag:
            return ATTR_LABELS.get(key, key)
    return "Pin"


def _connection_label(link_tag):
    fa, ta = state.links.get(link_tag, (None, None))
    fn = state.attr_to_node.get(fa)
    tn = state.attr_to_node.get(ta)
    f_label = state.nodes.get(fn, {}).get("label", "?")
    t_label = state.nodes.get(tn, {}).get("label", "?")
    return f"{f_label} <-> {t_label}"


def _connections_for_node(node_tag):
    attrs = _node_attrs(node_tag)
    rows = []
    for link_tag, (fa, ta) in state.links.items():
        if fa not in attrs and ta not in attrs:
            continue
        own_attr = fa if fa in attrs else ta
        other_attr = ta if fa in attrs else fa
        other_node = state.attr_to_node.get(other_attr)
        other = state.nodes.get(other_node, {})
        link_kind = "Saluran" if link_tag in state.line_data else "Koneksi"
        rows.append({
            "kind": link_kind,
            "own_port": _attr_name(node_tag, own_attr),
            "other_label": other.get("label", "?"),
            "other_kind": _kind_label(other.get("kind", "?")),
        })
    return rows


def _component_table_name(kind, is_slack=False):
    if kind == "bus":
        return "bus + ext_grid" if is_slack else "bus"
    if kind == "gen":
        return "sgen"
    if kind == "load":
        return "load"
    return kind


def _connected_to_kind(node_tag, kind):
    for link_tag, (fa, ta) in state.links.items():
        attrs = _node_attrs(node_tag)
        if fa not in attrs and ta not in attrs:
            continue
        other_attr = ta if fa in attrs else fa
        other_node = state.attr_to_node.get(other_attr)
        if state.nodes.get(other_node, {}).get("kind") == kind:
            return True
    return False


def _trafo_roles(node_tag):
    roles = set()
    attrs = _node_attrs(node_tag)
    for _, (fa, ta) in state.links.items():
        if fa in attrs:
            roles.add(state.attr_role.get(fa))
        elif ta in attrs:
            roles.add(state.attr_role.get(ta))
    return roles


def _node_guidance(node_tag):
    nd = state.nodes[node_tag]
    kind = nd["kind"]
    rows = _connections_for_node(node_tag)
    if kind == "bus":
        if not rows:
            return "Belum tersambung. Hubungkan bus ini ke saluran, beban, generator, shunt, atau transformer."
        if nd.get("is_slack"):
            return "Bus ini menjadi acuan tegangan. Pastikan jaringan lain tersambung ke bus ini."
        return "Bus sudah punya koneksi. Pastikan jalurnya tersambung sampai Slack / External Grid."
    if kind in ("gen", "load", "shunt"):
        if not _connected_to_kind(node_tag, "bus"):
            return f"{_kind_label(kind)} harus dihubungkan ke satu bus sebelum power flow."
        return f"{_kind_label(kind)} sudah tersambung ke bus."
    if kind == "trafo":
        roles = _trafo_roles(node_tag)
        missing = []
        if "hv" not in roles:
            missing.append("HV ke bus tegangan tinggi")
        if "lv" not in roles:
            missing.append("LV ke bus tegangan rendah")
        if missing:
            return "Transformer belum lengkap: " + ", ".join(missing) + "."
        return "Transformer sudah punya sisi HV dan LV. Cek nilai tegangan HV/LV agar sesuai bus."
    return "Pilih komponen untuk melihat langkah berikutnya."


def _show_guidance(text, good=False):
    color = (100, 220, 100) if good else (240, 200, 60)
    dpg.add_text(text, parent=PANEL_TAG, color=color, wrap=250)


def _add_float(key, value, callback, label=None, unit=None, hint=None):
    meta_label, meta_unit, meta_hint = _field_meta(key)
    label = label or meta_label
    unit = meta_unit if unit is None else unit
    hint = meta_hint if hint is None else hint
    suffix = f" ({unit})" if unit else ""
    dpg.add_text(f"{label}{suffix}", parent=PANEL_TAG, color=(170, 170, 170))
    if hint:
        dpg.add_text(hint, parent=PANEL_TAG,
                     color=(105, 105, 105), wrap=250)
    item = dpg.add_input_float(default_value=value, width=-1, step=0,
                               parent=PANEL_TAG, callback=callback)
    _attach_focus_tracker(item, snapshot_cb=take_snapshot)
    return item


def _show_help(kind):
    entries = HELP_TEXT.get(kind)
    if not entries:
        return
    header = dpg.add_collapsing_header(
        label="Bantuan field", parent=PANEL_TAG, default_open=False,
    )
    for key, desc in entries:
        label, unit, _ = _field_meta(key)
        suffix = f" ({unit})" if unit else ""
        dpg.add_text(f"{label}{suffix} / {key}",
                     parent=header, color=(255, 210, 50))
        dpg.add_text(f"    {desc}", parent=header,
                     color=(180, 180, 180), wrap=260)


def _show_empty():
    dpg.add_text("PANEL PROPERTI",
                 color=(255, 210, 50), parent=PANEL_TAG, wrap=250)
    dpg.add_text("Pilih node atau saluran untuk mengedit parameternya.",
                 color=(150, 150, 150), parent=PANEL_TAG, wrap=250)
    # Tampilkan ringkasan jaringan saat idle
    bus_count = sum(1 for n in state.nodes.values() if n.get("kind") == "bus")
    gen_count = sum(1 for n in state.nodes.values() if n.get("kind") == "gen")
    load_count = sum(1 for n in state.nodes.values() if n.get("kind") == "load")
    trafo_count = sum(1 for n in state.nodes.values() if n.get("kind") == "trafo")
    shunt_count = sum(1 for n in state.nodes.values() if n.get("kind") == "shunt")
    link_count = len(state.links)
    if bus_count or gen_count or load_count:
        dpg.add_separator(parent=PANEL_TAG)
        dpg.add_text("Ringkasan Jaringan", parent=PANEL_TAG,
                     color=(255, 210, 50))
        dpg.add_text(
            f"Bus: {bus_count}   Generator: {gen_count}\n"
            f"Beban: {load_count}   Trafo: {trafo_count}\n"
            f"Shunt: {shunt_count}   Koneksi: {link_count}",
            parent=PANEL_TAG, color=(170, 170, 170), wrap=250,
        )
        if state.results_are_stale():
            dpg.add_text(
                "Model berubah, jalankan Power Flow lagi.",
                parent=PANEL_TAG, color=(240, 200, 60), wrap=250,
            )
        elif state.last_results.get("nodes"):
            dpg.add_text(
                "Hasil Power Flow tersedia.",
                parent=PANEL_TAG, color=(100, 220, 100), wrap=250,
            )
        dpg.add_separator(parent=PANEL_TAG)
        dpg.add_text("Langkah cepat", parent=PANEL_TAG,
                     color=(255, 210, 50), wrap=250)
        if not state.last_results.get("nodes") or state.results_are_stale():
            dpg.add_text(
                "1. Validasi jaringan\n2. Jalankan Power Flow\n3. Pilih komponen untuk membaca hasil detail",
                parent=PANEL_TAG, color=(170, 170, 170), wrap=250,
            )
        else:
            dpg.add_text(
                "Pilih bus, saluran, atau transformer untuk melihat hasil detail.",
                parent=PANEL_TAG, color=(170, 170, 170), wrap=250,
            )
    else:
        dpg.add_separator(parent=PANEL_TAG)
        dpg.add_text("Mulai dari panel kiri", parent=PANEL_TAG,
                     color=(255, 210, 50), wrap=250)
        dpg.add_text(
            "Gunakan Muat Template untuk contoh siap jalan, atau tambah bus pertama sebagai Slack / External Grid.",
            parent=PANEL_TAG, color=(170, 170, 170), wrap=250,
        )


def _show_result(result):
    _section("Hasil Power Flow Terakhir")
    if state.results_are_stale():
        dpg.add_text("Model diedit setelah simulasi terakhir.",
                     parent=PANEL_TAG, color=(240, 200, 60), wrap=250)
    if not result:
        dpg.add_text("Jalankan Power Flow untuk melihat hasil.",
                     parent=PANEL_TAG, color=(120, 120, 120), wrap=250)
        return

    _row("Pandapower table", result.get("table", "-"))
    _row("Pandapower index", result.get("index", "-"))
    for key, (label, unit) in RESULT_LABELS.items():
        if key in result:
            _row(label, result[key], unit)


def _show_node_specs(node_tag):
    nd = state.nodes[node_tag]
    kind = nd["kind"]
    _section("Spesifikasi")
    _row("Komponen", nd["label"])
    _row("Tipe", _kind_label(kind))
    _row("Pandapower model",
         _component_table_name(kind, nd.get("is_slack", False)))

    mapped = state.pp_element_map.get(node_tag)
    if mapped:
        _row("Tabel hasil terakhir", mapped[0])
        _row("Index hasil terakhir", int(mapped[1]))
    else:
        _row("Tabel hasil terakhir", "belum dibuat")

    for key, label, unit in NODE_SPEC_KEYS.get(kind, []):
        if key in nd:
            _row(label, nd[key], unit)


def _show_node_connections(node_tag):
    _section("Koneksi")
    rows = _connections_for_node(node_tag)
    if not rows:
        dpg.add_text("Belum ada koneksi.",
                     parent=PANEL_TAG, color=(120, 120, 120), wrap=250)
        return
    for row in rows:
        dpg.add_text(
            f"{row['own_port']} -> {row['other_label']} "
            f"({row['other_kind']}, {row['kind']})",
            parent=PANEL_TAG,
            color=(200, 200, 200),
            wrap=250,
        )


def _show_line_specs(link_tag):
    data = state.line_data.get(link_tag)
    _section("Spesifikasi")
    _row("Koneksi", _connection_label(link_tag))
    _row("Tipe", "Saluran")
    if not data:
        _row("Model", "bukan line bus-ke-bus")
        return

    total_r = data["length_km"] * data["r_ohm_per_km"]
    total_x = data["length_km"] * data["x_ohm_per_km"]
    for key, label, unit in [
        ("label", "Nama", ""),
        ("length_km", "Panjang", "km"),
        ("r_ohm_per_km", "Resistansi", "ohm/km"),
        ("x_ohm_per_km", "Reaktansi", "ohm/km"),
        ("c_nf_per_km", "Kapasitansi", "nF/km"),
        ("max_i_ka", "Arus maksimum", "kA"),
    ]:
        _row(label, data[key], unit)
    _row("Total resistansi", total_r, "ohm")
    _row("Total reaktansi", total_x, "ohm")


def _show_line_properties(link_tag):
    state.selected_node[0] = None
    state.selected_link[0] = link_tag
    data = state.line_data.get(link_tag)
    if not data:
        _show_empty()
        return

    dpg.add_text("SALURAN", color=(255, 210, 50), parent=PANEL_TAG)
    dpg.add_text(_connection_label(link_tag), color=(120, 120, 120),
                 parent=PANEL_TAG, wrap=250)
    _show_guidance("Saluran bus-ke-bus memakai panjang, R, X, C, dan batas arus untuk menghitung rugi-rugi serta loading.",
                   good=True)
    dpg.add_separator(parent=PANEL_TAG)

    dpg.add_text("Edit Utama", color=(180, 180, 180), parent=PANEL_TAG)
    dpg.add_text("Nama saluran", parent=PANEL_TAG, color=(170, 170, 170))
    line_name = dpg.add_input_text(
        default_value=data["label"], width=-1, parent=PANEL_TAG,
        callback=_make_line_setter(link_tag, "label", str),
    )
    _attach_focus_tracker(line_name, snapshot_cb=take_snapshot)

    for key in [
        "length_km",
        "r_ohm_per_km",
        "x_ohm_per_km",
        "c_nf_per_km",
        "max_i_ka",
    ]:
        _add_float(key, data[key], _make_line_setter(link_tag, key))

    _show_line_specs(link_tag)
    _show_result(state.last_results.get("links", {}).get(link_tag))

    dpg.add_separator(parent=PANEL_TAG)
    _show_help("line")
    dpg.add_button(label="  Hapus Saluran  ", width=-1,
                   parent=PANEL_TAG,
                   callback=_delete_line_cb, user_data=link_tag)


def _show_node_editors(node_tag):
    nd = state.nodes[node_tag]
    kind = nd["kind"]
    dpg.add_text("Edit Utama", color=(180, 180, 180), parent=PANEL_TAG)

    dpg.add_text("Nama komponen", parent=PANEL_TAG, color=(170, 170, 170))
    dpg.add_text("nama yang tampil di node editor", parent=PANEL_TAG,
                 color=(105, 105, 105), wrap=250)
    name_input = dpg.add_input_text(
        default_value=nd["label"], width=-1, parent=PANEL_TAG,
        callback=_make_node_setter(node_tag, "label", str),
    )
    _attach_focus_tracker(name_input, snapshot_cb=take_snapshot)

    if kind == "bus":
        _add_float("vn_kv", nd["vn_kv"],
                   _make_node_setter(node_tag, "vn_kv"))
        cb_item = dpg.add_checkbox(
            label="Slack / external grid", default_value=nd["is_slack"],
            parent=PANEL_TAG,
            callback=_make_node_setter(
                node_tag, "is_slack", bool, _only_one_slack),
        )
        _attach_focus_tracker(cb_item, snapshot_cb=take_snapshot)
        if nd.get("is_slack"):
            _add_float("vm_pu", nd.get("vm_pu", 1.0),
                       _make_node_setter(node_tag, "vm_pu"))
            _add_float("va_degree", nd.get("va_degree", 0.0),
                       _make_node_setter(node_tag, "va_degree"))
        else:
            dpg.add_text(
                "Setpoint tegangan muncul kalau bus ini dijadikan Slack.",
                parent=PANEL_TAG, color=(105, 105, 105), wrap=250,
            )

    elif kind in ("gen", "load"):
        _add_float("p_mw", nd["p_mw"],
                   _make_node_setter(node_tag, "p_mw"))
        _add_float("q_mvar", nd["q_mvar"],
                   _make_node_setter(node_tag, "q_mvar"))

    elif kind == "shunt":
        _add_float("p_mw", nd.get("p_mw", 0.0),
                   _make_node_setter(node_tag, "p_mw"))
        _add_float("q_mvar", nd["q_mvar"],
                   _make_node_setter(node_tag, "q_mvar"))

    elif kind == "trafo":
        for key in [
            "sn_mva",
            "vn_hv_kv",
            "vn_lv_kv",
            "vk_percent",
            "vkr_percent",
            "pfe_kw",
            "i0_percent",
        ]:
            _add_float(key, nd.get(key, 0.0), _make_node_setter(node_tag, key))


def _show_node_properties(node_tag):
    state.selected_node[0] = node_tag
    state.selected_link[0] = None

    nd = state.nodes[node_tag]
    kind = nd["kind"]

    dpg.add_text(f"{_kind_label(kind).upper()} - {nd['label']}",
                 color=(255, 210, 50), parent=PANEL_TAG, wrap=250)
    _show_guidance(_node_guidance(node_tag), good=bool(_connections_for_node(node_tag)))
    dpg.add_separator(parent=PANEL_TAG)

    _show_node_editors(node_tag)
    _show_node_specs(node_tag)
    _show_node_connections(node_tag)
    _show_result(state.last_results.get("nodes", {}).get(node_tag))

    dpg.add_separator(parent=PANEL_TAG)
    _show_help(kind)
    dpg.add_button(label="  Hapus Komponen  ", width=-1,
                   parent=PANEL_TAG,
                   callback=_delete_node_cb, user_data=node_tag)


def show_properties(node_tag=None, link_tag=None):
    """Render isi panel kanan untuk node atau line terpilih."""
    _clear_panel()

    if link_tag is not None:
        _show_line_properties(link_tag)
        return

    if node_tag is None or node_tag not in state.nodes:
        state.selected_node[0] = None
        state.selected_link[0] = None
        _show_empty()
        return

    _show_node_properties(node_tag)
