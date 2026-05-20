import os
import sys
import webview
import state
import engine

class Api:
    def simulate(self, payload):
        try:
            state.reset()
            
            # 1. Populate nodes and virtual attributes
            for node in payload.get("nodes", []):
                nid = node["id"]
                kind = node["kind"]
                label = node["label"]
                
                nd = {
                    "kind": kind,
                    "label": label,
                }
                
                # Parameters matching backend keys
                if kind == "bus":
                    nd["vn_kv"] = float(node.get("vn_kv", 0.4))
                    nd["is_slack"] = bool(node.get("is_slack", False))
                    if nd["is_slack"]:
                        nd["vm_pu"] = float(node.get("vm_pu", 1.0))
                        nd["va_degree"] = float(node.get("va_degree", 0.0))
                    
                    # Virtual attributes for connections
                    nd["out_attr"] = f"{nid}_out"
                    nd["in_attr"] = f"{nid}_in"
                    
                    state.attr_to_node[nd["out_attr"]] = nid
                    state.attr_to_node[nd["in_attr"]] = nid
                    state.attr_role[nd["out_attr"]] = "p"
                    state.attr_role[nd["in_attr"]] = "p"
                    
                elif kind == "source":
                    # Map source node to a slack bus in state
                    nd["kind"] = "bus"
                    nd["vn_kv"] = float(node.get("vn_kv", 10.0))
                    nd["is_slack"] = True
                    nd["vm_pu"] = float(node.get("vm_pu", 1.0))
                    nd["va_degree"] = float(node.get("va_degree", 0.0))
                    
                    nd["out_attr"] = f"{nid}_out"
                    nd["in_attr"] = f"{nid}_in"
                    
                    state.attr_to_node[nd["out_attr"]] = nid
                    state.attr_to_node[nd["in_attr"]] = nid
                    state.attr_role[nd["out_attr"]] = "p"
                    state.attr_role[nd["in_attr"]] = "p"
                    
                elif kind in ("load", "gen", "shunt"):
                    nd["p_mw"] = float(node.get("p_mw", 0.0))
                    nd["q_mvar"] = float(node.get("q_mvar", 0.0))
                    nd["pin"] = f"{nid}_pin"
                    
                    state.attr_to_node[nd["pin"]] = nid
                    state.attr_role[nd["pin"]] = "p"
                    
                elif kind == "trafo":
                    nd["sn_mva"] = float(node.get("sn_mva", 0.25))
                    nd["vn_hv_kv"] = float(node.get("vn_hv_kv", 10.0))
                    nd["vn_lv_kv"] = float(node.get("vn_lv_kv", 0.4))
                    nd["vk_percent"] = float(node.get("vk_percent", 4.0))
                    nd["vkr_percent"] = float(node.get("vkr_percent", 1.2))
                    nd["pfe_kw"] = float(node.get("pfe_kw", 0.0))
                    nd["i0_percent"] = float(node.get("i0_percent", 0.0))
                    
                    nd["hv_pin"] = f"{nid}_hv"
                    nd["lv_pin"] = f"{nid}_lv"
                    
                    state.attr_to_node[nd["hv_pin"]] = nid
                    state.attr_to_node[nd["lv_pin"]] = nid
                    state.attr_role[nd["hv_pin"]] = "hv"
                    state.attr_role[nd["lv_pin"]] = "lv"
                
                state.nodes[nid] = nd

            # 2. Populate links
            for link in payload.get("links", []):
                lid = link["id"]
                fn = link["fromNode"]
                fp = link["fromPin"]
                tn = link["toNode"]
                tp = link["toPin"]
                
                # Translate pin names to virtual attributes
                from_nd = state.nodes.get(fn)
                to_nd = state.nodes.get(tn)
                if not from_nd or not to_nd:
                    continue
                
                # Get the actual virtual attribute tag
                fa = None
                if from_nd["kind"] == "bus":
                    fa = f"{fn}_out" if fp.startswith("out") else f"{fn}_in"
                elif from_nd["kind"] in ("load", "gen", "shunt"):
                    fa = f"{fn}_pin"
                elif from_nd["kind"] == "trafo":
                    fa = f"{fn}_hv" if fp == "hv" else f"{fn}_lv"
                    
                ta = None
                if to_nd["kind"] == "bus":
                    ta = f"{tn}_in" if tp.startswith("in") else f"{tn}_out"
                elif to_nd["kind"] in ("load", "gen", "shunt"):
                    ta = f"{tn}_pin"
                elif to_nd["kind"] == "trafo":
                    ta = f"{tn}_hv" if tp == "hv" else f"{tn}_lv"
                
                if fa and ta:
                    state.links[lid] = (fa, ta)
                    
                    # If this is a bus-to-bus line connection, add line_data
                    if from_nd["kind"] == "bus" and to_nd["kind"] == "bus":
                        ld = link.get("line_data", {})
                        state.line_data[lid] = {
                            "label": ld.get("label", f"Line {lid}"),
                            "length_km": float(ld.get("length_km", 0.05)),
                            "r_ohm_per_km": float(ld.get("r_ohm_per_km", 0.225)),
                            "x_ohm_per_km": float(ld.get("x_ohm_per_km", 0.08)),
                            "c_nf_per_km": float(ld.get("c_nf_per_km", 264.0)),
                            "max_i_ka": float(ld.get("max_i_ka", 0.242))
                        }

            # 3. Execute power flow
            ok, msg, net, _, _ = engine.run_pf()
            if ok:
                return {"ok": True, "results": state.last_results}
            else:
                return {"ok": False, "message": msg}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"ok": False, "message": str(e)}

def main():
    # Find absolute path of index.html in web-prototype folder
    base_dir = os.path.dirname(os.path.abspath(__file__))
    html_path = os.path.join(base_dir, "web-prototype", "index.html")
    
    api = Api()
    
    print("Launching Grid Simulator Desktop App...")
    webview.create_window(
        title="Grid Simulator - AutoCAD Interactive SLD",
        url=html_path,
        js_api=api,
        width=1280,
        height=800,
        resizable=True
    )
    webview.start(debug=True)

if __name__ == "__main__":
    main()
