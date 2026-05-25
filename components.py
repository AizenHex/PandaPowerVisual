"""
Factory untuk membuat node komponen di node editor Dear PyGui.
Setiap factory mendaftarkan node ke state.nodes dengan field "kind".
"""
import dearpygui.dearpygui as dpg

import state


_node_themes = {}

def get_node_theme(kind, is_slack=False):
    theme_key = f"{kind}_slack" if (kind == "bus" and is_slack) else kind
    
    # If any cached theme doesn't exist, the DPG context has been recreated. Clear cache.
    for k, tag in list(_node_themes.items()):
        if not dpg.does_item_exist(tag):
            _node_themes.clear()
            break

    if theme_key in _node_themes and dpg.does_item_exist(_node_themes[theme_key]):
        return _node_themes[theme_key]

    theme_tag = dpg.generate_uuid()
    with dpg.theme(tag=theme_tag):
        with dpg.theme_component(dpg.mvNode):
            if kind == "bus":
                if is_slack:
                    # Emas (Slack)
                    title_bg = (180, 110, 20)
                    title_active = (210, 130, 30)
                    bg = (35, 30, 20)
                    border = (255, 180, 50)
                    border_thickness = 3.0
                else:
                    # Biru (Normal Bus)
                    title_bg = (20, 60, 100)
                    title_active = (30, 80, 130)
                    bg = (20, 25, 35)
                    border = (100, 190, 255)
                    border_thickness = 2.0
                rounding = 4.0
            elif kind == "gen":
                # Hijau
                title_bg = (20, 80, 45)
                title_active = (30, 110, 60)
                bg = (20, 30, 25)
                border = (80, 220, 120)
                border_thickness = 2.0
                rounding = 12.0
            elif kind == "trafo":
                # Tembaga
                title_bg = (100, 55, 20)
                title_active = (130, 75, 30)
                bg = (35, 30, 25)
                border = (230, 140, 70)
                border_thickness = 2.0
                rounding = 6.0
            elif kind == "load":
                # Merah
                title_bg = (100, 30, 30)
                title_active = (130, 45, 45)
                bg = (35, 25, 25)
                border = (230, 100, 100)
                border_thickness = 2.0
                rounding = 6.0
            elif kind == "shunt":
                # Ungu
                title_bg = (70, 30, 100)
                title_active = (90, 45, 130)
                bg = (30, 25, 35)
                border = (180, 100, 255)
                border_thickness = 2.0
                rounding = 2.0
            else:
                title_bg = (50, 50, 50)
                title_active = (70, 70, 70)
                bg = (30, 30, 30)
                border = (150, 150, 150)
                border_thickness = 1.0
                rounding = 4.0

            dpg.add_theme_color(dpg.mvNodeCol_TitleBar, title_bg, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_TitleBarHovered, title_active, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_TitleBarSelected, title_active, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_NodeBackground, bg, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_NodeBackgroundHovered, bg, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_NodeBackgroundSelected, bg, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_color(dpg.mvNodeCol_NodeOutline, border, category=dpg.mvThemeCat_Nodes)
            
            dpg.add_theme_style(dpg.mvNodeStyleVar_NodeCornerRounding, rounding, category=dpg.mvThemeCat_Nodes)
            dpg.add_theme_style(dpg.mvNodeStyleVar_NodeBorderThickness, border_thickness, category=dpg.mvThemeCat_Nodes)

    _node_themes[theme_key] = theme_tag
    return theme_tag


def bind_node_theme(node_tag, kind, is_slack=False):
    theme = get_node_theme(kind, is_slack)
    dpg.bind_item_theme(node_tag, theme)



def _register_handler(node_tag):
    """Pasang item handler agar klik pada node memicu seleksi."""
    with dpg.item_handler_registry() as h:
        dpg.add_item_clicked_handler(callback=_on_node_clicked,
                                     user_data=node_tag)
    dpg.bind_item_handler_registry(node_tag, h)
    return h


def _on_node_clicked(sender, app_data, user_data):
    # Lazy import untuk hindari circular
    import properties_panel
    properties_panel.show_properties(user_data)


def _node_info_text(nd):
    kind = nd["kind"]
    if kind == "bus":
        prefix = "Slack " if nd["is_slack"] else "Vn "
        return f"{prefix}{nd['vn_kv']} kV"
    if kind == "gen":
        return f"P {nd['p_mw']} MW\nQ {nd['q_mvar']} MVAr"
    if kind == "trafo":
        return f"S {nd['sn_mva']} MVA\n{nd['vn_hv_kv']}/{nd['vn_lv_kv']} kV"
    if kind == "shunt":
        return f"P {nd['p_mw']} MW\nQ {nd['q_mvar']} MVAr"
    if kind == "load":
        return f"P {nd['p_mw']} MW\nQ {nd['q_mvar']} MVAr"
    return ""


def refresh_node_visual(node_tag):
    nd = state.nodes.get(node_tag)
    if not nd:
        return
    kind = nd["kind"]
    if dpg.does_item_exist(node_tag):
        if kind == "bus":
            title = f"[SLACK] {nd['label']}" if nd["is_slack"] else f"[BUS] {nd['label']}"
        elif kind == "gen":
            title = f"(G) {nd['label']}"
        elif kind == "trafo":
            title = f"[T] {nd['label']}"
        elif kind == "load":
            title = f"(L) {nd['label']}"
        elif kind == "shunt":
            title = f"(C) {nd['label']}"
        else:
            title = nd["label"]
        dpg.configure_item(node_tag, label=title)
        bind_node_theme(node_tag, kind, nd.get("is_slack", False))

    info_tag = nd.get("info_tag")
    if info_tag and dpg.does_item_exist(info_tag):
        dpg.set_value(info_tag, _node_info_text(nd))
        if nd["kind"] == "bus":
            color = (255, 180, 50) if nd["is_slack"] else (100, 190, 255)
            dpg.configure_item(info_tag, color=color)


# ── Bus ────────────────────────────────────────────────────────────────────────
def create_bus_node(label=None, vn_kv=20.0, is_slack=False, vm_pu=1.0,
                    va_degree=0.0, pos=(200, 200)):
    bid = state.next_id("bus")
    lbl = label or f"Bus {bid}"
    out_attr = dpg.generate_uuid()
    in_attr = dpg.generate_uuid()
    res_tag = dpg.generate_uuid()
    info_tag = dpg.generate_uuid()

    with dpg.node(label=lbl, parent="ne_canvas", pos=list(pos)) as node_tag:
        with dpg.node_attribute(tag=out_attr,
                                attribute_type=dpg.mvNode_Attr_Output):
            dpg.add_text("", tag=info_tag)
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text("V --\nva --", tag=res_tag, color=(160, 160, 160))
        with dpg.node_attribute(tag=in_attr,
                                attribute_type=dpg.mvNode_Attr_Input):
            dpg.add_text("IN", color=(120, 120, 120))

    state.nodes[node_tag] = {
        "kind": "bus",
        "label": lbl,
        "vn_kv": vn_kv,
        "is_slack": is_slack,
        "vm_pu": vm_pu,
        "va_degree": va_degree,
        "out_attr": out_attr,
        "in_attr": in_attr,
        "info_tag": info_tag,
        "res_tag": res_tag,
    }
    state.attr_to_node[out_attr] = node_tag
    state.attr_to_node[in_attr] = node_tag
    state.attr_role[out_attr] = "p"
    state.attr_role[in_attr] = "p"
    h = _register_handler(node_tag)
    state.nodes[node_tag]["handler_registry"] = h
    refresh_node_visual(node_tag)
    state.mark_model_dirty()
    return node_tag


# ── Generator / Static Generator ───────────────────────────────────────────────
def create_gen_node(label=None, p_mw=1.0, q_mvar=0.0, pos=(200, 200)):
    gid = state.next_id("gen")
    lbl = label or f"Gen {gid}"
    pin = dpg.generate_uuid()
    info_tag = dpg.generate_uuid()

    with dpg.node(label=lbl, parent="ne_canvas", pos=list(pos)) as node_tag:
        with dpg.node_attribute(tag=pin,
                                attribute_type=dpg.mvNode_Attr_Output):
            dpg.add_text("GEN", color=(120, 230, 130))
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text("", tag=info_tag, color=(200, 200, 200))

    state.nodes[node_tag] = {
        "kind": "gen",
        "label": lbl,
        "p_mw": p_mw,
        "q_mvar": q_mvar,
        "pin": pin,
        "info_tag": info_tag,
    }
    state.attr_to_node[pin] = node_tag
    state.attr_role[pin] = "p"
    h = _register_handler(node_tag)
    state.nodes[node_tag]["handler_registry"] = h
    refresh_node_visual(node_tag)
    state.mark_model_dirty()
    return node_tag


# ── Trafo (dua port: HV & LV) ──────────────────────────────────────────────────
def create_trafo_node(label=None, sn_mva=10.0, vn_hv_kv=110.0, vn_lv_kv=20.0,
                      vk_percent=6.0, vkr_percent=0.5, pfe_kw=0.0,
                      i0_percent=0.0, pos=(200, 200)):
    tid = state.next_id("trafo")
    lbl = label or f"Trafo {tid}"
    hv_pin = dpg.generate_uuid()
    lv_pin = dpg.generate_uuid()
    info_tag = dpg.generate_uuid()

    with dpg.node(label=lbl, parent="ne_canvas", pos=list(pos)) as node_tag:
        with dpg.node_attribute(tag=hv_pin,
                                attribute_type=dpg.mvNode_Attr_Input):
            dpg.add_text(f"HV {vn_hv_kv} kV", color=(230, 160, 80))
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text("", tag=info_tag, color=(200, 200, 200))
        with dpg.node_attribute(tag=lv_pin,
                                attribute_type=dpg.mvNode_Attr_Output):
            dpg.add_text(f"LV {vn_lv_kv} kV", color=(230, 160, 80))

    state.nodes[node_tag] = {
        "kind": "trafo",
        "label": lbl,
        "sn_mva": sn_mva,
        "vn_hv_kv": vn_hv_kv,
        "vn_lv_kv": vn_lv_kv,
        "vk_percent": vk_percent,
        "vkr_percent": vkr_percent,
        "pfe_kw": pfe_kw,
        "i0_percent": i0_percent,
        "hv_pin": hv_pin,
        "lv_pin": lv_pin,
        "info_tag": info_tag,
    }
    state.attr_to_node[hv_pin] = node_tag
    state.attr_to_node[lv_pin] = node_tag
    state.attr_role[hv_pin] = "hv"
    state.attr_role[lv_pin] = "lv"
    h = _register_handler(node_tag)
    state.nodes[node_tag]["handler_registry"] = h
    refresh_node_visual(node_tag)
    state.mark_model_dirty()
    return node_tag


# ── Shunt kapasitor ────────────────────────────────────────────────────────────
def create_shunt_node(label=None, p_mw=0.0, q_mvar=-1.0, pos=(200, 200)):
    sid = state.next_id("shunt")
    lbl = label or f"Shunt {sid}"
    pin = dpg.generate_uuid()
    info_tag = dpg.generate_uuid()

    with dpg.node(label=lbl, parent="ne_canvas", pos=list(pos)) as node_tag:
        with dpg.node_attribute(tag=pin,
                                attribute_type=dpg.mvNode_Attr_Input):
            dpg.add_text("SHUNT", color=(200, 130, 230))
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text("", tag=info_tag, color=(200, 200, 200))

    state.nodes[node_tag] = {
        "kind": "shunt",
        "label": lbl,
        "p_mw": p_mw,
        "q_mvar": q_mvar,
        "pin": pin,
        "info_tag": info_tag,
    }
    state.attr_to_node[pin] = node_tag
    state.attr_role[pin] = "p"
    h = _register_handler(node_tag)
    state.nodes[node_tag]["handler_registry"] = h
    refresh_node_visual(node_tag)
    state.mark_model_dirty()
    return node_tag


# ── Load (terpisah dari Bus) ───────────────────────────────────────────────────
def create_load_node(label=None, p_mw=0.5, q_mvar=0.1, pos=(200, 200)):
    lid = state.next_id("load")
    lbl = label or f"Load {lid}"
    pin = dpg.generate_uuid()
    info_tag = dpg.generate_uuid()

    with dpg.node(label=lbl, parent="ne_canvas", pos=list(pos)) as node_tag:
        with dpg.node_attribute(tag=pin,
                                attribute_type=dpg.mvNode_Attr_Input):
            dpg.add_text("LOAD", color=(230, 110, 110))
        with dpg.node_attribute(attribute_type=dpg.mvNode_Attr_Static):
            dpg.add_text("", tag=info_tag, color=(200, 200, 200))

    state.nodes[node_tag] = {
        "kind": "load",
        "label": lbl,
        "p_mw": p_mw,
        "q_mvar": q_mvar,
        "pin": pin,
        "info_tag": info_tag,
    }
    state.attr_to_node[pin] = node_tag
    state.attr_role[pin] = "p"
    h = _register_handler(node_tag)
    state.nodes[node_tag]["handler_registry"] = h
    refresh_node_visual(node_tag)
    state.mark_model_dirty()
    return node_tag


# ── Hapus node ─────────────────────────────────────────────────────────────────
def delete_node(node_tag):
    if node_tag not in state.nodes:
        return
    nd = state.nodes[node_tag]
    # Kumpulkan semua attr milik node ini
    attrs = []
    for k in ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin"):
        if k in nd:
            attrs.append(nd[k])
    # Hapus link yang menyentuh attr tersebut
    for lt, (fa, ta) in list(state.links.items()):
        if fa in attrs or ta in attrs:
            if dpg.does_item_exist(lt):
                dpg.delete_item(lt)
            state.links.pop(lt, None)
            state.line_data.pop(lt, None)
            state.mark_model_dirty()
    for a in attrs:
        state.attr_to_node.pop(a, None)
        state.attr_role.pop(a, None)
    if dpg.does_item_exist(node_tag):
        dpg.delete_item(node_tag)
    h = nd.get("handler_registry")
    if h and dpg.does_item_exist(h):
        dpg.delete_item(h)
    state.nodes.pop(node_tag, None)
    state.pp_element_map.pop(node_tag, None)
    state.mark_model_dirty()
    if state.selected_node[0] == node_tag:
        state.selected_node[0] = None
    if state.selected_link[0] not in state.links:
        state.selected_link[0] = None
