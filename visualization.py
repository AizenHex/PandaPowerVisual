"""
Visualisasi hasil power flow: tegangan bus, warna link, dan tabel hasil line.
"""
import dearpygui.dearpygui as dpg

import state


def _loading_color(pct: float):
    if pct < 50:
        return (80, 220, 100, 255)
    if pct < 80:
        return (240, 220, 60, 255)
    if pct < 100:
        return (240, 150, 60, 255)
    return (230, 80, 80, 255)


def _voltage_color(vm_pu: float):
    if 0.95 <= vm_pu <= 1.05:
        return (80, 220, 100)
    if 0.90 <= vm_pu <= 1.10:
        return (240, 200, 60)
    return (230, 80, 80)


def update_node_results(net, node_to_pidx):
    """Tulis V (pu) pada tiap bus dan warnai sesuai batas umum tegangan."""
    for nt, pidx in node_to_pidx.items():
        nd = state.nodes.get(nt)
        if not nd or nd["kind"] != "bus":
            continue
        try:
            vm = float(net.res_bus.at[pidx, "vm_pu"])
            va = float(net.res_bus.at[pidx, "va_degree"])
        except Exception:
            continue
        if dpg.does_item_exist(nd["res_tag"]):
            dpg.set_value(nd["res_tag"], f"V {vm:.4f} pu\nva {va:.1f} deg")
            dpg.configure_item(nd["res_tag"], color=_voltage_color(vm))


def clear_result_visuals():
    """Kosongkan visual hasil lama agar tidak terbaca sebagai hasil aktif."""
    for nd in state.nodes.values():
        res_tag = nd.get("res_tag")
        if res_tag and dpg.does_item_exist(res_tag):
            dpg.set_value(res_tag, "V --\nva --")
            dpg.configure_item(res_tag, color=(160, 160, 160))
    render_line_table([])


def update_line_results(net, line_map):
    """Warnai link berdasarkan loading_percent dan kembalikan data tabel."""
    rows = []
    seen_rows = set()
    for lt, (kind, idx) in line_map.items():
        try:
            if kind == "line":
                result = net.res_line.loc[idx]
                table = net.line.loc[idx]
                loading = float(result["loading_percent"])
                p_from = float(result["p_from_mw"])
                q_from = float(result["q_from_mvar"])
                loss_kw = float(result["pl_mw"]) * 1000
                name = table["name"]
            else:
                result = net.res_trafo.loc[idx]
                table = net.trafo.loc[idx]
                loading = float(result["loading_percent"])
                p_from = float(result["p_hv_mw"])
                q_from = float(result["q_hv_mvar"])
                loss_kw = float(result["pl_mw"]) * 1000
                name = table["name"]
        except (KeyError, ValueError, TypeError):
            continue

        color = _loading_color(loading)
        if dpg.does_item_exist(lt):
            try:
                dpg.configure_item(lt, color=color)
            except Exception:
                pass
        row_key = (kind, int(idx))
        if row_key in seen_rows:
            continue
        seen_rows.add(row_key)
        rows.append({
            "name": str(name),
            "kind": kind,
            "p_mw": p_from,
            "q_mvar": q_from,
            "loss_kw": loss_kw,
            "loading": loading,
            "direction": "->" if p_from >= 0 else "<-",
        })
    return rows


def render_line_table(rows):
    """Render tabel ringkasan line/trafo di panel hasil bawah."""
    if not dpg.does_item_exist("tbl_lines"):
        return

    for child in dpg.get_item_children("tbl_lines", 1) or []:
        dpg.delete_item(child)

    for row in rows:
        with dpg.table_row(parent="tbl_lines"):
            dpg.add_text(row["name"])
            dpg.add_text(row["kind"])
            dpg.add_text(f"{row['p_mw']:+.4f} MW {row['direction']}")
            dpg.add_text(f"{row['q_mvar']:+.4f} MVAr")
            dpg.add_text(f"{row['loss_kw']:.3f} kW")
            col = _loading_color(row["loading"])
            text = dpg.add_text(f"{row['loading']:5.1f} %")
            dpg.configure_item(text, color=col[:3])
