import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import engine  # noqa: E402
import state  # noqa: E402


def add_bus(name, vn_kv, is_slack=False):
    node = name.lower().replace(" ", "_")
    out_attr = f"{node}_out"
    in_attr = f"{node}_in"
    state.nodes[node] = {
        "kind": "bus",
        "label": name,
        "vn_kv": vn_kv,
        "is_slack": is_slack,
        "out_attr": out_attr,
        "in_attr": in_attr,
    }
    state.attr_to_node[out_attr] = node
    state.attr_to_node[in_attr] = node
    state.attr_role[out_attr] = "p"
    state.attr_role[in_attr] = "p"
    return node


def add_gen(name, p_mw=0.03, q_mvar=0.01):
    node = name.lower().replace(" ", "_")
    pin = f"{node}_pin"
    state.nodes[node] = {
        "kind": "gen",
        "label": name,
        "p_mw": p_mw,
        "q_mvar": q_mvar,
        "pin": pin,
    }
    state.attr_to_node[pin] = node
    state.attr_role[pin] = "p"
    return node


def add_load(name, p_mw=0.03, q_mvar=0.01):
    node = name.lower().replace(" ", "_")
    pin = f"{node}_pin"
    state.nodes[node] = {
        "kind": "load",
        "label": name,
        "p_mw": p_mw,
        "q_mvar": q_mvar,
        "pin": pin,
    }
    state.attr_to_node[pin] = node
    state.attr_role[pin] = "p"
    return node


def add_trafo(name, **overrides):
    node = name.lower().replace(" ", "_")
    hv_pin = f"{node}_hv"
    lv_pin = f"{node}_lv"
    data = {
        "kind": "trafo",
        "label": name,
        "sn_mva": 0.25,
        "vn_hv_kv": 10.0,
        "vn_lv_kv": 0.4,
        "vk_percent": 4.0,
        "vkr_percent": 1.2,
        "hv_pin": hv_pin,
        "lv_pin": lv_pin,
    }
    data.update(overrides)
    state.nodes[node] = data
    state.attr_to_node[hv_pin] = node
    state.attr_to_node[lv_pin] = node
    state.attr_role[hv_pin] = "hv"
    state.attr_role[lv_pin] = "lv"
    return node


def add_link(name, from_node, from_key, to_node, to_key, line_data=None):
    from_attr = state.nodes[from_node][from_key]
    to_attr = state.nodes[to_node][to_key]
    state.links[name] = (from_attr, to_attr)
    if line_data:
        state.line_data[name] = state.make_line_data(**line_data)


class EngineTest(unittest.TestCase):
    def setUp(self):
        state.reset()

    def test_four_load_branch_like_network_converges(self):
        b0 = add_bus("Ext Grid", 10.0, is_slack=True)
        tr = add_trafo("Trafo")
        b1 = add_bus("Bus 1", 0.4)
        buses = [add_bus(f"Bus {i}", 0.4) for i in range(2, 6)]

        add_link("grid_trafo", b0, "out_attr", tr, "hv_pin")
        add_link("trafo_bus", tr, "lv_pin", b1, "in_attr")
        line_data = {
            "length_km": 0.05,
            "r_ohm_per_km": 0.225,
            "x_ohm_per_km": 0.08,
            "c_nf_per_km": 264.0,
            "max_i_ka": 0.242,
        }
        previous = b1
        for idx, bus in enumerate(buses, start=1):
            add_link(f"line_{idx}", previous, "out_attr", bus, "in_attr",
                     {**line_data, "label": f"Line {idx}"})
            load = add_load(f"Load {idx}")
            add_link(f"load_{idx}", bus, "out_attr", load, "pin")
            previous = bus

        ok, msg, net, _, line_map = engine.run_pf()

        self.assertTrue(ok, msg)
        self.assertEqual(len(net.bus), 6)
        self.assertEqual(len(net.line), 4)
        self.assertEqual(len(net.load), 4)
        self.assertEqual(len(net.trafo), 1)
        self.assertEqual(len([v for v in line_map.values() if v[0] == "line"]), 4)
        self.assertGreater(float(net.res_bus.vm_pu.min()), 0.90)

    def test_rejects_network_without_slack_bus(self):
        b0 = add_bus("Bus 0", 20.0)
        b1 = add_bus("Bus 1", 20.0)
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Line 1"})

        ok, msg, *_ = engine.run_pf()

        self.assertFalse(ok)
        self.assertEqual(msg, "Tidak ada Slack Bus / External Grid.")

    def test_rejects_bus_island_without_slack_bus(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        b1 = add_bus("Bus 1", 20.0)
        b2 = add_bus("Bus 2", 20.0)
        b3 = add_bus("Bus 3", 20.0)
        add_link("grid_line", b0, "out_attr", b1, "in_attr",
                 {"label": "Grid Line"})
        add_link("island_line", b2, "out_attr", b3, "in_attr",
                 {"label": "Island Line"})

        errors, _ = engine.validate_model()
        ok, msg, *_ = engine.run_pf()

        self.assertIn(
            "Bus 2 tidak terhubung ke Slack Bus / External Grid.",
            errors,
        )
        self.assertFalse(ok)
        self.assertIn("tidak terhubung ke Slack Bus", msg)

    def test_validate_flags_floating_bus(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        b1 = add_bus("Bus 1", 20.0)
        floating = add_bus("Bus Floating", 20.0)
        add_link("grid_line", b0, "out_attr", b1, "in_attr",
                 {"label": "Grid Line"})

        errors, _ = engine.validate_model()

        self.assertTrue(any(
            "Bus Floating tidak terhubung ke Slack Bus" in e for e in errors
        ), errors)
        # silence unused-var lint
        _ = floating

    def test_validate_no_slack_message_consistent_with_run_pf(self):
        b0 = add_bus("Bus 0", 20.0)
        b1 = add_bus("Bus 1", 20.0)
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Line 1"})

        errors, _ = engine.validate_model()
        ok, msg, *_ = engine.run_pf()

        self.assertIn("Tidak ada Slack Bus / External Grid.", errors)
        self.assertFalse(ok)
        self.assertIn("Tidak ada Slack Bus / External Grid.", msg)

    def test_snapshot_roundtrip_preserves_topology(self):
        # Roundtrip the pure-state portion of save/load: serialize current
        # state.nodes / state.links to a JSON-friendly dict, reset, then
        # reconstruct and re-run power flow. Mirrors the data model used by
        # cb_save_project / cb_load_project, minus the DPG UI bits.
        import json as _json

        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        b1 = add_bus("Bus 1", 20.0)
        ld = add_load("Load 1", p_mw=0.05, q_mvar=0.02)
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Custom Line", "length_km": 1.2})
        add_link("load", b1, "out_attr", ld, "pin")

        node_ids = {nt: f"n{i}" for i, nt in enumerate(state.nodes)}
        snapshot = {
            "nodes": [
                {"id": node_ids[nt], **{k: v for k, v in nd.items()
                                        if k not in (
                                            "out_attr", "in_attr", "pin",
                                            "hv_pin", "lv_pin")}}
                for nt, nd in state.nodes.items()
            ],
            "links": [],
        }
        # Map attr -> (node_id, role-key)
        attr_keys = ("out_attr", "in_attr", "pin", "hv_pin", "lv_pin")
        attr_lookup = {}
        for nt, nd in state.nodes.items():
            for k in attr_keys:
                if k in nd:
                    attr_lookup[nd[k]] = (node_ids[nt], k)
        for lt, (fa, ta) in state.links.items():
            entry = {
                "from": {"node": attr_lookup[fa][0],
                         "attr": attr_lookup[fa][1]},
                "to": {"node": attr_lookup[ta][0],
                       "attr": attr_lookup[ta][1]},
            }
            if lt in state.line_data:
                entry["line_data"] = dict(state.line_data[lt])
            snapshot["links"].append(entry)

        # Make sure it's JSON-serializable
        blob = _json.dumps(snapshot)
        snapshot = _json.loads(blob)

        state.reset()
        # Rehydrate
        id_to_tag = {}
        for item in snapshot["nodes"]:
            kind = item["kind"]
            tag = item["id"]
            nd = {k: v for k, v in item.items() if k != "id"}
            if kind == "bus":
                nd["out_attr"] = f"{tag}_out"
                nd["in_attr"] = f"{tag}_in"
                state.attr_to_node[nd["out_attr"]] = tag
                state.attr_to_node[nd["in_attr"]] = tag
                state.attr_role[nd["out_attr"]] = "p"
                state.attr_role[nd["in_attr"]] = "p"
            elif kind == "load":
                nd["pin"] = f"{tag}_pin"
                state.attr_to_node[nd["pin"]] = tag
                state.attr_role[nd["pin"]] = "p"
            state.nodes[tag] = nd
            id_to_tag[tag] = tag

        for i, link in enumerate(snapshot["links"]):
            fn = id_to_tag[link["from"]["node"]]
            tn = id_to_tag[link["to"]["node"]]
            fa = state.nodes[fn][link["from"]["attr"]]
            ta = state.nodes[tn][link["to"]["attr"]]
            lt = f"rl_{i}"
            state.links[lt] = (fa, ta)
            if "line_data" in link:
                state.line_data[lt] = dict(link["line_data"])

        ok, msg, net, *_ = engine.run_pf()
        self.assertTrue(ok, msg)
        self.assertEqual(len(net.bus), 2)
        self.assertEqual(len(net.line), 1)
        self.assertEqual(len(net.load), 1)
        self.assertAlmostEqual(float(net.line.at[0, "length_km"]), 1.2)

    def test_line_parameters_are_used(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        b1 = add_bus("Bus 1", 20.0)
        add_load("Load 1")
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Custom Line", "length_km": 2.5})
        add_link("load", b1, "out_attr", "load_1", "pin")

        ok, msg, net, *_ = engine.run_pf()

        self.assertTrue(ok, msg)
        self.assertEqual(net.line.at[0, "name"], "Custom Line")
        self.assertAlmostEqual(float(net.line.at[0, "length_km"]), 2.5)

    def test_validate_rejects_invalid_line_parameters(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        b1 = add_bus("Bus 1", 20.0)
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Bad Line", "length_km": 0.0})

        errors, _ = engine.validate_model()

        self.assertIn("Bad Line punya length_km <= 0.", errors)

    def test_validate_rejects_invalid_trafo_impedance(self):
        b0 = add_bus("Ext Grid", 10.0, is_slack=True)
        tr = add_trafo("Bad Trafo", vk_percent=4.0, vkr_percent=5.0)
        b1 = add_bus("Bus 1", 0.4)
        add_link("hv", b0, "out_attr", tr, "hv_pin")
        add_link("lv", tr, "lv_pin", b1, "in_attr")

        errors, _ = engine.validate_model()

        self.assertIn("Bad Trafo punya vkr_percent > vk_percent.", errors)

    def test_validate_rejects_negative_load_and_generator_power(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        b1 = add_bus("Bus 1", 20.0)
        load = add_load("Bad Load", p_mw=-0.1)
        gen = add_gen("Bad Gen", p_mw=-0.1)
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Line 1"})
        add_link("load", b1, "out_attr", load, "pin")
        add_link("gen", b1, "out_attr", gen, "pin")

        errors, _ = engine.validate_model()

        self.assertIn("Bad Load punya p_mw load < 0.", errors)
        self.assertIn("Bad Gen punya p_mw generator < 0.", errors)

    def test_validate_rejects_unreasonable_slack_voltage(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        state.nodes[b0]["vm_pu"] = 1.35
        b1 = add_bus("Bus 1", 20.0)
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Line 1"})

        errors, _ = engine.validate_model()

        self.assertIn("Ext Grid punya vm_pu slack di luar 0.8-1.2 pu.", errors)

    def test_validate_rejects_line_connecting_different_nominal_voltages(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        b1 = add_bus("Bus 1", 10.0)
        add_link("line", b0, "out_attr", b1, "in_attr",
                 {"label": "Mismatched Line"})

        errors, _ = engine.validate_model()
        self.assertTrue(any("Mismatched Line menghubungkan bus dengan tegangan nominal berbeda" in e for e in errors), errors)

    def test_validate_rejects_trafo_invalid_winding_voltages(self):
        b0 = add_bus("Ext Grid", 10.0, is_slack=True)
        tr = add_trafo("Bad Trafo Voltages", vn_hv_kv=10.0, vn_lv_kv=20.0) # HV <= LV is invalid
        b1 = add_bus("Bus 1", 20.0)
        add_link("hv", b0, "out_attr", tr, "hv_pin")
        add_link("lv", tr, "lv_pin", b1, "in_attr")

        errors, _ = engine.validate_model()
        self.assertIn("Bad Trafo Voltages punya vn_hv_kv <= vn_lv_kv.", errors)

    def test_validate_rejects_trafo_invalid_side_connection_voltages(self):
        b0 = add_bus("Ext Grid", 0.4, is_slack=True) # Ext Grid is 0.4kV
        tr = add_trafo("Step Up Trafo", vn_hv_kv=10.0, vn_lv_kv=0.4)
        b1 = add_bus("Bus 1", 10.0) # Connected to LV pin but is 10.0kV
        # Connect HV pin of transformer to 0.4kV bus, and LV pin to 10.0kV bus
        add_link("hv", b0, "out_attr", tr, "hv_pin")
        add_link("lv", tr, "lv_pin", b1, "in_attr")

        errors, _ = engine.validate_model()
        self.assertTrue(any("terhubung ke bus HV (Ext Grid: 0.4 kV) yang tegangannya tidak lebih tinggi dari bus LV" in e for e in errors), errors)

    def test_validate_warns_on_trafo_param_mismatch(self):
        b0 = add_bus("Ext Grid", 20.0, is_slack=True)
        tr = add_trafo("Mismatched Param Trafo", vn_hv_kv=10.0, vn_lv_kv=0.4) # Params are 10/0.4
        b1 = add_bus("Bus 1", 0.4)
        add_link("hv", b0, "out_attr", tr, "hv_pin") # Connected to 20kV instead of 10kV
        add_link("lv", tr, "lv_pin", b1, "in_attr")

        _, warnings = engine.validate_model()
        self.assertTrue(any("Tegangan nominal HV Mismatched Param Trafo (10.0 kV) tidak cocok dengan tegangan bus Ext Grid (20.0 kV)" in w for w in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
