import json
import sys
import tempfile
import unittest
from pathlib import Path

import dearpygui.dearpygui as dpg


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import state  # noqa: E402


UNSUPPORTED_UI_CHARS = {
    "\u26a1",
    "\u2714",
    "\u25c0",
    "\u25b6",
    "\u2212",
    "\u2192",
    "\u2194",
    "\u22a5",
    "\u25bc",
    "\u26a0",
    "\u2705",
}


class UiSmokeTest(unittest.TestCase):
    def setUp(self):
        app.zoom_level[0] = 1.0
        state.reset()
        state.clear_undo()
        dpg.create_context()
        app.build_ui()

    def tearDown(self):
        dpg.destroy_context()
        state.reset()
        state.clear_undo()

    def panel_text_values(self, item=None):
        item = item or properties_panel_tag()
        values = []
        children = dpg.get_item_children(item) or {}
        child_groups = children.values() if isinstance(children, dict) else [children]
        for group in child_groups:
            for child in group or []:
                try:
                    value = dpg.get_value(child)
                except Exception:
                    value = None
                if isinstance(value, str):
                    values.append(value)
                values.extend(self.panel_text_values(child))
        return values

    def item_labels_and_text(self, item="w_main"):
        values = []
        if dpg.does_item_exist(item):
            label = dpg.get_item_label(item)
            if isinstance(label, str):
                values.append(label)
            try:
                value = dpg.get_value(item)
            except Exception:
                value = None
            if isinstance(value, str):
                values.append(value)
            children = dpg.get_item_children(item) or {}
            child_groups = children.values() if isinstance(children, dict) else [children]
            for group in child_groups:
                for child in group or []:
                    values.extend(self.item_labels_and_text(child))
        return values

    def nodes_are_spaced(self):
        tags = list(state.nodes)
        for index, first in enumerate(tags):
            for second in tags[index + 1:]:
                if app._nodes_overlap(first, second):
                    return False
        return True

    def test_main_panels_exist(self):
        for tag in [
            app.SIDEBAR_TAG,
            app.TOOLBAR_TAG,
            app.CENTER_PANEL_TAG,
            properties_panel_tag(),
        ]:
            self.assertTrue(dpg.does_item_exist(tag), tag)

    def test_visible_ui_text_uses_supported_ascii_controls(self):
        text = "\n".join(self.item_labels_and_text())
        bad_chars = sorted(UNSUPPORTED_UI_CHARS & set(text))
        self.assertEqual(bad_chars, [])
        for expected in [
            "Hide Panel",
            "Hide Props",
            "Run Power Flow",
            "Validasi Jaringan",
            "Edit Saluran Dipilih",
        ]:
            self.assertIn(expected, text)

    def test_component_actions_live_in_toolbar_not_left_panel(self):
        toolbar_text = "\n".join(self.item_labels_and_text(app.TOOLBAR_TAG))
        sidebar_text = "\n".join(self.item_labels_and_text(app.SIDEBAR_TAG))

        for expected in ["Bus", "Gen", "Trafo", "Shunt", "Beban"]:
            self.assertIn(expected, toolbar_text)
        for removed in [
            "Tambah Bus",
            "Tambah Generator",
            "Tambah Transformer",
            "Tambah Shunt",
            "Tambah Beban",
            "Komponen",
        ]:
            self.assertNotIn(removed, sidebar_text)
        self.assertIn("Analisis", sidebar_text)
        self.assertIn("Project", sidebar_text)

    def test_add_component_callbacks_select_new_node(self):
        callbacks = [
            (app.cb_add_bus, "bus", "Bus ditambahkan."),
            (app.cb_add_gen, "gen", "Generator ditambahkan."),
            (app.cb_add_trafo, "trafo", "Transformer ditambahkan."),
            (app.cb_add_shunt, "shunt", "Shunt ditambahkan."),
            (app.cb_add_load, "load", "Beban ditambahkan."),
        ]

        for callback, kind, status in callbacks:
            callback()
            selected = state.selected_node[0]
            self.assertIsNotNone(selected)
            self.assertEqual(state.nodes[selected]["kind"], kind)
            self.assertEqual(dpg.get_value("txt_status"), status)

    def test_delete_without_selection_does_not_push_undo(self):
        app.cb_delete_selection()

        self.assertEqual(state.undo_depth(), 0)
        self.assertEqual(dpg.get_value("txt_status"), "Siap")

    def test_delete_selected_node_clears_stale_results(self):
        app.cb_add_bus()
        selected = state.selected_node[0]
        state.store_results({"nodes": {selected: {"vm_pu": 1.0}}, "links": {}})
        dpg.set_value("txt_results", "old result")

        app.cb_delete_selection()

        self.assertNotIn(selected, state.nodes)
        self.assertEqual(state.last_results, {"nodes": {}, "links": {}})
        self.assertEqual(dpg.get_value("txt_results"), "")
        self.assertEqual(dpg.get_value("txt_status"), "Komponen terpilih dihapus.")

    def test_stale_editing_flag_does_not_block_backspace_delete(self):
        app.cb_add_bus()
        selected = state.selected_node[0]
        app.properties_panel.editing_field[0] = True
        app.properties_panel.editing_item[0] = 999999

        app.cb_delete_selection()

        self.assertNotIn(selected, state.nodes)
        self.assertFalse(app.properties_panel.editing_field[0])
        self.assertIsNone(app.properties_panel.editing_item[0])

    def test_invalid_link_does_not_push_empty_undo_step(self):
        app.cb_add_load()
        first = state.selected_node[0]
        app.cb_add_load()
        second = state.selected_node[0]
        before = state.undo_depth()

        app.cb_link(None, (state.nodes[first]["pin"], state.nodes[second]["pin"]))

        self.assertEqual(state.undo_depth(), before)
        self.assertEqual(state.links, {})
        self.assertIn("Koneksi tidak valid", dpg.get_value("txt_status"))

    def test_zoom_changes_node_spacing_and_binds_node_theme(self):
        app.cb_add_bus()
        first = state.selected_node[0]
        app.cb_add_bus()
        second = state.selected_node[0]
        x1, _ = dpg.get_item_pos(first)
        x2, _ = dpg.get_item_pos(second)
        before_distance = abs(x2 - x1)

        app.cb_zoom_in()

        new_x1, _ = dpg.get_item_pos(first)
        new_x2, _ = dpg.get_item_pos(second)
        self.assertGreater(abs(new_x2 - new_x1), before_distance)
        self.assertEqual(dpg.get_value("txt_zoom"), "120%")
        self.assertEqual(dpg.get_item_theme("ne_canvas"), app.node_zoom_theme_tag[0])

    def test_new_components_spawn_without_colliding_slots(self):
        callbacks = [
            app.cb_add_bus,
            app.cb_add_gen,
            app.cb_add_trafo,
            app.cb_add_shunt,
            app.cb_add_load,
            app.cb_add_bus,
            app.cb_add_gen,
            app.cb_add_load,
        ]
        for callback in callbacks:
            callback()

        self.assertTrue(self.nodes_are_spaced())

    def test_mouse_release_repels_dragged_overlap(self):
        app.cb_add_bus()
        first = state.selected_node[0]
        app.cb_add_load()
        second = state.selected_node[0]
        dpg.set_item_pos(second, dpg.get_item_pos(first))

        self.assertTrue(app._nodes_overlap(first, second))

        app._mouse_release()

        self.assertFalse(app._nodes_overlap(first, second))

    def test_collision_resolver_wraps_crowded_overlaps_to_new_rows(self):
        for _ in range(10):
            app.cb_add_load()
        for node_tag in state.nodes:
            dpg.set_item_pos(node_tag, [90, 80])

        app._resolve_node_collisions()

        y_positions = [round(dpg.get_item_pos(node_tag)[1], 1) for node_tag in state.nodes]
        self.assertTrue(self.nodes_are_spaced())
        self.assertGreater(max(y_positions), min(y_positions))

    def test_zoom_out_compacts_layout_without_creating_overlap(self):
        app.cb_add_bus()
        first = state.selected_node[0]
        app.cb_add_bus()
        second = state.selected_node[0]
        dpg.set_item_pos(first, [100, 100])
        dpg.set_item_pos(second, [700, 100])
        before_distance = abs(dpg.get_item_pos(second)[0] - dpg.get_item_pos(first)[0])

        app.cb_zoom_out()

        after_distance = abs(dpg.get_item_pos(second)[0] - dpg.get_item_pos(first)[0])
        self.assertLess(after_distance, before_distance)
        self.assertTrue(self.nodes_are_spaced())

    def test_power_flow_result_layout_resolves_node_overlap(self):
        app._populate_demo()
        tags = list(state.nodes)
        for index, node_tag in enumerate(tags):
            dpg.set_item_pos(node_tag, [120 + index * 20, 100])

        app.cb_run_pf()

        self.assertEqual(dpg.get_value("txt_status"), "Konvergen")
        self.assertTrue(self.nodes_are_spaced())
        panel_text = "\n".join(self.item_labels_and_text("ne_canvas"))
        self.assertIn("va", panel_text)
        self.assertNotIn("ang=", panel_text)

    def test_project_payload_rejects_duplicate_single_terminal_pin(self):
        payload = {
            "version": 1,
            "nodes": [
                {"id": "b1", "kind": "bus", "label": "Bus 1"},
                {"id": "b2", "kind": "bus", "label": "Bus 2"},
                {"id": "l1", "kind": "load", "label": "Load 1"},
            ],
            "links": [
                {"from": {"node": "b1", "attr": "out_attr"},
                 "to": {"node": "l1", "attr": "pin"}},
                {"from": {"node": "b2", "attr": "out_attr"},
                 "to": {"node": "l1", "attr": "pin"}},
            ],
        }

        problem = app._validate_project_payload(payload)

        self.assertIn("sudah terhubung", problem)

    def test_load_invalid_project_reports_error_without_clearing_canvas(self):
        app.cb_add_bus()
        existing_nodes = set(state.nodes)
        old_path = app.PROJECT_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            bad_path = Path(tmpdir) / "bad_project.json"
            bad_path.write_text(
                json.dumps({"version": 1, "nodes": [{"id": "n0"}], "links": []}),
                encoding="utf-8",
            )
            app.PROJECT_PATH = bad_path
            try:
                app.cb_load_project()
            finally:
                app.PROJECT_PATH = old_path

        self.assertEqual(set(state.nodes), existing_nodes)
        self.assertIn("Project tidak valid", dpg.get_value("txt_status"))

    def test_save_project_reports_filesystem_error(self):
        app.cb_add_bus()
        old_path = app.PROJECT_PATH

        with tempfile.TemporaryDirectory() as tmpdir:
            app.PROJECT_PATH = Path(tmpdir)
            try:
                app.cb_save_project()
            finally:
                app.PROJECT_PATH = old_path

        self.assertIn("Gagal menyimpan project", dpg.get_value("txt_status"))

    def test_property_edit_clears_rendered_power_flow_result(self):
        app.cb_add_bus()
        app.cb_add_bus()
        selected = state.selected_node[0]
        state.store_results({
            "nodes": {
                selected: {
                    "table": "bus",
                    "index": 0,
                    "vm_pu": 0.9876,
                },
            },
            "links": {},
        })
        dpg.set_value("txt_results", "old summary")
        app.properties_panel.show_properties(selected)
        self.assertIn("0.987600", "\n".join(self.panel_text_values()))

        app.properties_panel._make_node_setter(selected, "vn_kv")(None, 0.42)
        panel_text = "\n".join(self.panel_text_values())

        self.assertEqual(state.last_results, {"nodes": {}, "links": {}})
        self.assertEqual(dpg.get_value("txt_results"), "")
        self.assertNotIn("0.987600", panel_text)
        self.assertIn("Jalankan Power Flow", panel_text)


def properties_panel_tag():
    return app.properties_panel.PANEL_TAG


if __name__ == "__main__":
    unittest.main()
