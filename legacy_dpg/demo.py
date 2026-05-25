"""
PANDAPOWER VISUALIZATION entry point.

The current UI shell uses PySide6/QGraphicsView. Dear PyGui files have been
archived under .ARSIP for reference.
"""
import sys

from qt_app import main


def smoke_power_flow() -> int:
    # Smoke test memakai modul aktif PySide: qt_model untuk state, engine untuk pandapower.
    import engine
    import qt_model
    import state

    # Template kecil dibuat tanpa membuka window agar packaging/test bisa cek power flow.
    qt_model.reset_model(clear_undo=True)
    with qt_model.suspend_undo():
        b0 = qt_model.create_node("bus", (60, 300), label="Ext Grid", vn_kv=10.0, is_slack=True)
        t0 = qt_model.create_node(
            "trafo",
            (310, 300),
            label="Trafo 10/0.4",
            sn_mva=0.25,
            vn_hv_kv=10.0,
            vn_lv_kv=0.4,
            vk_percent=4.0,
            vkr_percent=1.2,
        )
        b1 = qt_model.create_node("bus", (590, 300), label="Bus 1", vn_kv=0.4)
        b2 = qt_model.create_node("bus", (860, 80), label="Bus 2", vn_kv=0.4)
        load = qt_model.create_node("load", (1210, 80), label="Load 1", p_mw=0.03, q_mvar=0.01)
        qt_model.add_link(state.nodes[b0]["out_attr"], state.nodes[t0]["hv_pin"])
        qt_model.add_link(state.nodes[t0]["lv_pin"], state.nodes[b1]["in_attr"])
        qt_model.add_link(
            state.nodes[b1]["out_attr"],
            state.nodes[b2]["in_attr"],
            {
                "label": "Line 1",
                "length_km": 0.05,
                "r_ohm_per_km": 0.225,
                "x_ohm_per_km": 0.08,
                "c_nf_per_km": 264.0,
                "max_i_ka": 0.242,
            },
        )
        qt_model.add_link(state.nodes[b2]["out_attr"], state.nodes[load]["pin"])

    ok, _msg, _net, _n2p, _lmap = engine.run_pf()
    return 0 if ok else 1


if __name__ == "__main__":
    if "--smoke-power-flow" in sys.argv:
        raise SystemExit(smoke_power_flow())
    raise SystemExit(main())
