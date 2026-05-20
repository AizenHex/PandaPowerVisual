"""
Konverter state -> pandapower network, plus runner power flow.
Tidak menyentuh GUI sama sekali agar dapat diuji secara headless.
"""
import pandapower as pp

import state


def _attrs_of(node_tag):
    nd = state.nodes.get(node_tag, {})
    return {
        nd[key]
        for key in ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin")
        if key in nd
    }


def _connected_links(node_tag):
    attrs = _attrs_of(node_tag)
    for link_tag, (fa, ta) in state.links.items():
        if fa in attrs or ta in attrs:
            yield link_tag, fa, ta


def _reachable_from_slack(slack_node_tags):
    adjacency = {node_tag: set() for node_tag in state.nodes}
    for fa, ta in state.links.values():
        fn = state.attr_to_node.get(fa)
        tn = state.attr_to_node.get(ta)
        if not fn or not tn or fn == tn:
            continue
        adjacency.setdefault(fn, set()).add(tn)
        adjacency.setdefault(tn, set()).add(fn)

    seen = set()
    stack = list(slack_node_tags)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, set()) - seen)
    return seen


def _has_bus_neighbor(node_tag):
    for other, _, _ in _neighbors_of(node_tag):
        if state.nodes.get(other, {}).get("kind") == "bus":
            return True
    return False


def _num(data, key, default=0.0):
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return None


def _require_number(errors, label, data, key):
    value = _num(data, key)
    if value is None:
        errors.append(f"{label} punya {key} yang bukan angka.")
    return value


def validate_model():
    """Return (errors, warnings) for the current editor state."""
    errors = []
    warnings = []
    bus_nodes = [
        (nt, nd) for nt, nd in state.nodes.items() if nd.get("kind") == "bus"
    ]
    slack_nodes = [(nt, nd) for nt, nd in bus_nodes if nd.get("is_slack")]

    if not state.nodes:
        errors.append("Canvas masih kosong.")
        return errors, warnings
    if len(bus_nodes) < 2:
        errors.append("Butuh minimal 2 bus untuk power flow.")
    if not slack_nodes:
        errors.append("Tidak ada Slack Bus / External Grid.")
    if len(slack_nodes) > 1:
        warnings.append("Ada lebih dari satu Slack Bus.")
    if not state.links:
        errors.append("Belum ada koneksi antar komponen.")

    for link_tag, (fa, ta) in state.links.items():
        fn = state.attr_to_node.get(fa)
        tn = state.attr_to_node.get(ta)
        if not fn or not tn:
            errors.append(f"Link {link_tag} punya pin yang tidak valid.")
            continue
        fk = state.nodes.get(fn, {}).get("kind")
        tk = state.nodes.get(tn, {}).get("kind")
        if fk == "bus" and tk == "bus":
            data = state.line_data.get(link_tag) or dict(state.LINE_DEFAULTS)
            line_label = data.get("label", "Line")
            fnd = state.nodes.get(fn)
            tnd = state.nodes.get(tn)
            if fnd and tnd:
                v1 = _num(fnd, "vn_kv")
                v2 = _num(tnd, "vn_kv")
                if v1 is not None and v2 is not None and v1 != v2:
                    errors.append(
                        f"{line_label} menghubungkan bus dengan tegangan nominal berbeda: "
                        f"{fnd['label']} ({v1} kV) dan {tnd['label']} ({v2} kV)."
                    )
            for key in ("length_km", "max_i_ka"):
                value = _require_number(errors, line_label, data, key)
                if value is not None and value <= 0:
                    errors.append(f"{line_label} punya {key} <= 0.")
            for key in ("r_ohm_per_km", "x_ohm_per_km", "c_nf_per_km"):
                value = _require_number(errors, line_label, data, key)
                if value is not None and value < 0:
                    errors.append(f"{line_label} punya {key} < 0.")
            r_value = _num(data, "r_ohm_per_km")
            x_value = _num(data, "x_ohm_per_km")
            if r_value is not None and x_value is not None and r_value == 0 and x_value == 0:
                errors.append(f"{line_label} punya R dan X sama-sama 0.")
            continue
        if "bus" in {fk, tk} and ({fk, tk} & {"gen", "load", "shunt", "trafo"}):
            continue
        errors.append(
            f"Koneksi antara {state.nodes[fn]['label']} dan "
            f"{state.nodes[tn]['label']} tidak didukung."
        )

    for nt, nd in state.nodes.items():
        kind = nd.get("kind")
        if kind == "bus":
            vn_kv = _require_number(errors, nd["label"], nd, "vn_kv")
            if vn_kv is not None and vn_kv <= 0:
                errors.append(f"{nd['label']} punya vn_kv <= 0.")
            if nd.get("is_slack"):
                vm_pu = _num(nd, "vm_pu", 1.0)
                if vm_pu is None:
                    errors.append(f"{nd['label']} punya vm_pu yang bukan angka.")
                if vm_pu is not None and not 0.8 <= vm_pu <= 1.2:
                    errors.append(
                        f"{nd['label']} punya vm_pu slack di luar 0.8-1.2 pu."
                    )
            if not list(_connected_links(nt)):
                warnings.append(f"{nd['label']} belum terhubung.")
        elif kind == "gen":
            p_mw = _require_number(errors, nd["label"], nd, "p_mw")
            if p_mw is not None and p_mw < 0:
                errors.append(f"{nd['label']} punya p_mw generator < 0.")
            _require_number(errors, nd["label"], nd, "q_mvar")
            if not _has_bus_neighbor(nt):
                errors.append(f"{nd['label']} belum terhubung ke bus.")
        elif kind == "load":
            p_mw = _require_number(errors, nd["label"], nd, "p_mw")
            if p_mw is not None and p_mw < 0:
                errors.append(f"{nd['label']} punya p_mw load < 0.")
            _require_number(errors, nd["label"], nd, "q_mvar")
            if not _has_bus_neighbor(nt):
                errors.append(f"{nd['label']} belum terhubung ke bus.")
        elif kind == "shunt":
            p_mw = _require_number(errors, nd["label"], nd, "p_mw")
            if p_mw is not None and p_mw < 0:
                errors.append(f"{nd['label']} punya p_mw shunt < 0.")
            _require_number(errors, nd["label"], nd, "q_mvar")
            if not _has_bus_neighbor(nt):
                errors.append(f"{nd['label']} belum terhubung ke bus.")
        elif kind == "trafo":
            hv_bus = lv_bus = None
            for other, my_role, _ in _neighbors_of(nt):
                if state.nodes.get(other, {}).get("kind") != "bus":
                    continue
                if my_role == "hv":
                    hv_bus = other
                elif my_role == "lv":
                    lv_bus = other
            if hv_bus is None:
                errors.append(f"{nd['label']} belum punya koneksi HV ke bus.")
            if lv_bus is None:
                errors.append(f"{nd['label']} belum punya koneksi LV ke bus.")
            if hv_bus is not None and hv_bus == lv_bus:
                errors.append(f"{nd['label']} HV dan LV terhubung ke bus yang sama.")
            for key in ("sn_mva", "vn_hv_kv", "vn_lv_kv"):
                value = _require_number(errors, nd["label"], nd, key)
                if value is not None and value <= 0:
                    errors.append(f"{nd['label']} punya {key} <= 0.")
            vn_hv_kv = _num(nd, "vn_hv_kv")
            vn_lv_kv = _num(nd, "vn_lv_kv")
            if vn_hv_kv is not None and vn_lv_kv is not None and vn_hv_kv <= vn_lv_kv:
                errors.append(f"{nd['label']} punya vn_hv_kv <= vn_lv_kv.")
            if hv_bus is not None and lv_bus is not None:
                hv_bus_node = state.nodes.get(hv_bus)
                lv_bus_node = state.nodes.get(lv_bus)
                if hv_bus_node and lv_bus_node:
                    vn_hv_bus = _num(hv_bus_node, "vn_kv")
                    vn_lv_bus = _num(lv_bus_node, "vn_kv")
                    if vn_hv_bus is not None and vn_lv_bus is not None and vn_hv_bus <= vn_lv_bus:
                        errors.append(
                            f"{nd['label']} terhubung ke bus HV ({hv_bus_node['label']}: {vn_hv_bus} kV) "
                            f"yang tegangannya tidak lebih tinggi dari bus LV ({lv_bus_node['label']}: {vn_lv_bus} kV)."
                        )
                    if vn_hv_bus is not None and vn_hv_kv is not None and vn_hv_bus != vn_hv_kv:
                        warnings.append(
                            f"Tegangan nominal HV {nd['label']} ({vn_hv_kv} kV) tidak cocok dengan "
                            f"tegangan bus {hv_bus_node['label']} ({vn_hv_bus} kV)."
                        )
                    if vn_lv_bus is not None and vn_lv_kv is not None and vn_lv_bus != vn_lv_kv:
                        warnings.append(
                            f"Tegangan nominal LV {nd['label']} ({vn_lv_kv} kV) tidak cocok dengan "
                            f"tegangan bus {lv_bus_node['label']} ({vn_lv_bus} kV)."
                        )
            vk_percent = _require_number(errors, nd["label"], nd, "vk_percent")
            if vk_percent is not None and vk_percent <= 0:
                errors.append(f"{nd['label']} punya vk_percent <= 0.")
            vkr_percent = _require_number(errors, nd["label"], nd, "vkr_percent")
            if vkr_percent is not None and vkr_percent < 0:
                errors.append(f"{nd['label']} punya vkr_percent < 0.")
            if (
                vk_percent is not None
                and vkr_percent is not None
                and vkr_percent > vk_percent
            ):
                errors.append(f"{nd['label']} punya vkr_percent > vk_percent.")
            for key in ("pfe_kw", "i0_percent"):
                value = _require_number(errors, nd["label"], nd, key)
                if value is not None and value < 0:
                    errors.append(f"{nd['label']} punya {key} < 0.")

    if slack_nodes:
        reachable = _reachable_from_slack([nt for nt, _ in slack_nodes])
        for nt, nd in bus_nodes:
            if nt not in reachable:
                errors.append(
                    f"{nd['label']} tidak terhubung ke Slack Bus / External Grid."
                )

    return errors, warnings


def _result_row(table, idx, fields):
    row = {}
    for field in fields:
        if field in table.columns:
            try:
                value = table.at[idx, field]
                row[field] = float(value)
            except (KeyError, ValueError, TypeError):
                pass
    return row


def _collect_results(net, node_to_pidx, line_map):
    node_results = {}
    link_results = {}

    for nt, pidx in node_to_pidx.items():
        node_results[nt] = {
            "table": "bus",
            "index": int(pidx),
            **_result_row(net.res_bus, pidx, [
                "vm_pu",
                "va_degree",
                "p_mw",
                "q_mvar",
            ]),
        }

    for nt, (table_name, idx) in state.pp_element_map.items():
        if table_name == "load":
            result_table = net.res_load
            fields = ["p_mw", "q_mvar"]
        elif table_name == "sgen":
            result_table = net.res_sgen
            fields = ["p_mw", "q_mvar"]
        elif table_name == "shunt":
            result_table = net.res_shunt
            fields = ["p_mw", "q_mvar", "vm_pu"]
        elif table_name == "trafo":
            result_table = net.res_trafo
            fields = [
                "p_hv_mw",
                "q_hv_mvar",
                "p_lv_mw",
                "q_lv_mvar",
                "pl_mw",
                "ql_mvar",
                "i_hv_ka",
                "i_lv_ka",
                "loading_percent",
            ]
        else:
            continue
        node_results[nt] = {
            "table": table_name,
            "index": int(idx),
            **_result_row(result_table, idx, fields),
        }

    for lt, (table_name, idx) in line_map.items():
        if table_name == "line":
            result_table = net.res_line
            fields = [
                "p_from_mw",
                "q_from_mvar",
                "p_to_mw",
                "q_to_mvar",
                "pl_mw",
                "ql_mvar",
                "i_from_ka",
                "i_to_ka",
                "loading_percent",
            ]
        elif table_name == "trafo":
            result_table = net.res_trafo
            fields = [
                "p_hv_mw",
                "q_hv_mvar",
                "p_lv_mw",
                "q_lv_mvar",
                "pl_mw",
                "ql_mvar",
                "i_hv_ka",
                "i_lv_ka",
                "loading_percent",
            ]
        else:
            continue
        link_results[lt] = {
            "table": table_name,
            "index": int(idx),
            **_result_row(result_table, idx, fields),
        }

    return {"nodes": node_results, "links": link_results}


def _invalid_result_reason(net):
    checks = [
        ("tegangan bus", net.res_bus.get("vm_pu")),
        ("loading line", net.res_line.get("loading_percent")),
        ("loading trafo", net.res_trafo.get("loading_percent")),
    ]
    for label, series in checks:
        if series is not None and len(series) and series.isna().any():
            return f"{label} berisi NaN"
    return None


def _neighbors_of(node_tag):
    """Yield (other_node_tag, role_on_self, role_on_other) untuk tiap link."""
    nd = state.nodes[node_tag]
    my_attrs = {nd[k] for k in ("out_attr", "in_attr", "pin", "hv_pin",
                                "lv_pin") if k in nd}
    for lt, (fa, ta) in state.links.items():
        if fa in my_attrs:
            other = state.attr_to_node.get(ta)
            if other and other != node_tag:
                yield other, state.attr_role.get(fa), state.attr_role.get(ta)
        elif ta in my_attrs:
            other = state.attr_to_node.get(fa)
            if other and other != node_tag:
                yield other, state.attr_role.get(ta), state.attr_role.get(fa)


def _find_bus_for(node_tag, node_to_pidx):
    """Cari bus index pandapower terdekat dari node non-bus (gen/load/shunt)."""
    for other, _, _ in _neighbors_of(node_tag):
        ond = state.nodes.get(other)
        if ond and ond["kind"] == "bus":
            return node_to_pidx.get(other)
    return None


def build_pp_network():
    """Bangun pandapower net dari state. Return (net, node_to_pidx, line_map).

    line_map: link_tag -> ("line"|"trafo", index_di_net)
    """
    net = pp.create_empty_network()
    node_to_pidx: dict = {}
    line_map: dict = {}
    state.pp_element_map.clear()

    # 1. Bus
    for nt, nd in state.nodes.items():
        if nd["kind"] == "bus":
            pidx = pp.create_bus(net, vn_kv=nd["vn_kv"], name=nd["label"])
            node_to_pidx[nt] = pidx
            state.pp_element_map[nt] = ("bus", pidx)
            if nd["is_slack"]:
                pp.create_ext_grid(
                    net, bus=pidx,
                    vm_pu=nd.get("vm_pu", 1.0),
                    va_degree=nd.get("va_degree", 0.0),
                    name=f"{nd['label']} Grid",
                )

    # 2. Generator, Load, Shunt: cari bus tetangga
    for nt, nd in state.nodes.items():
        kind = nd["kind"]
        if kind == "gen":
            b = _find_bus_for(nt, node_to_pidx)
            if b is not None:
                idx = pp.create_sgen(net, bus=b, p_mw=nd["p_mw"],
                                     q_mvar=nd["q_mvar"], name=nd["label"])
                state.pp_element_map[nt] = ("sgen", idx)
        elif kind == "load":
            b = _find_bus_for(nt, node_to_pidx)
            if b is not None:
                idx = pp.create_load(net, bus=b, p_mw=nd["p_mw"],
                                     q_mvar=nd["q_mvar"], name=nd["label"])
                state.pp_element_map[nt] = ("load", idx)
        elif kind == "shunt":
            b = _find_bus_for(nt, node_to_pidx)
            if b is not None:
                idx = pp.create_shunt(net, bus=b, p_mw=nd.get("p_mw", 0.0),
                                      q_mvar=nd["q_mvar"], name=nd["label"])
                state.pp_element_map[nt] = ("shunt", idx)

    # 3. Trafo: butuh dua bus (HV-side neighbor & LV-side neighbor)
    for nt, nd in state.nodes.items():
        if nd["kind"] != "trafo":
            continue
        hv_bus = lv_bus = None
        for other, my_role, _ in _neighbors_of(nt):
            ond = state.nodes.get(other)
            if not ond or ond["kind"] != "bus":
                continue
            if my_role == "hv" and hv_bus is None:
                hv_bus = node_to_pidx.get(other)
            elif my_role == "lv" and lv_bus is None:
                lv_bus = node_to_pidx.get(other)
        if hv_bus is not None and lv_bus is not None:
            tidx = pp.create_transformer_from_parameters(
                net, hv_bus=hv_bus, lv_bus=lv_bus,
                sn_mva=nd["sn_mva"],
                vn_hv_kv=nd["vn_hv_kv"], vn_lv_kv=nd["vn_lv_kv"],
                vk_percent=nd["vk_percent"],
                vkr_percent=nd["vkr_percent"],
                pfe_kw=nd.get("pfe_kw", 0.0),
                i0_percent=nd.get("i0_percent", 0.0),
                name=nd["label"],
            )
            state.pp_element_map[nt] = ("trafo", tidx)
            # Cari link yang melibatkan trafo ini untuk pemetaan visual
            my_attrs = {nd["hv_pin"], nd["lv_pin"]}
            for lt, (fa, ta) in state.links.items():
                if fa in my_attrs or ta in my_attrs:
                    line_map[lt] = ("trafo", tidx)

    # 4. Line: bus-to-bus langsung
    for lt, (fa, ta) in state.links.items():
        fn = state.attr_to_node.get(fa)
        tn = state.attr_to_node.get(ta)
        if not fn or not tn or fn == tn:
            continue
        fnd = state.nodes.get(fn)
        tnd = state.nodes.get(tn)
        if not (fnd and tnd and fnd["kind"] == "bus" and tnd["kind"] == "bus"):
            continue
        b1, b2 = node_to_pidx[fn], node_to_pidx[tn]
        data = state.line_data.get(lt) or dict(state.LINE_DEFAULTS)
        lidx = pp.create_line_from_parameters(
            net, from_bus=b1, to_bus=b2,
            length_km=data["length_km"],
            r_ohm_per_km=data["r_ohm_per_km"],
            x_ohm_per_km=data["x_ohm_per_km"],
            c_nf_per_km=data["c_nf_per_km"],
            max_i_ka=data["max_i_ka"],
            name=data.get("label") or f"L{b1}-{b2}",
        )
        line_map[lt] = ("line", lidx)

    return net, node_to_pidx, line_map


def run_pf():
    """Build + run. Return (ok, message, net, node_to_pidx, line_map)."""
    errors, warnings = validate_model()
    if errors:
        state.clear_results()
        return False, " | ".join(errors[:3]), None, {}, {}

    net, n2p, lmap = build_pp_network()
    if len(net.line) == 0 and len(net.trafo) == 0:
        return False, "Tidak ada koneksi valid.", None, {}, {}

    try:
        pp.runpp(net, numba=False)
    except Exception as exc:
        state.clear_results()
        return False, f"Gagal: {exc}", None, {}, {}

    invalid_reason = _invalid_result_reason(net)
    if invalid_reason:
        state.clear_results()
        return (
            False,
            "Hasil power flow tidak valid: "
            f"{invalid_reason}. Pastikan semua bus tersambung ke Slack Bus.",
            None,
            {},
            {},
        )

    state.store_results(_collect_results(net, n2p, lmap))
    return True, "Konvergen", net, n2p, lmap
