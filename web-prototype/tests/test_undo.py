import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import state  # noqa: E402


class UndoStackTest(unittest.TestCase):
    def setUp(self):
        state.reset()
        state.clear_undo()

    def test_push_pop_roundtrip(self):
        state.nodes["n1"] = {"kind": "bus", "label": "B1", "vn_kv": 20.0}
        state.push_undo({"n1": (100, 200)})

        # Mutasi setelah snapshot
        state.nodes["n1"]["vn_kv"] = 0.4
        state.nodes["n2"] = {"kind": "load", "label": "L1"}

        self.assertEqual(state.undo_depth(), 1)
        snap = state.pop_undo()
        self.assertEqual(state.undo_depth(), 0)
        self.assertIn("n1", snap["nodes"])
        self.assertEqual(snap["nodes"]["n1"]["vn_kv"], 20.0)
        self.assertNotIn("n2", snap["nodes"])
        self.assertEqual(snap["positions"]["n1"], (100, 200))

    def test_limit_caps_history(self):
        for i in range(state.UNDO_LIMIT + 10):
            state.nodes["x"] = {"kind": "bus", "label": f"B{i}"}
            state.push_undo()
        self.assertEqual(state.undo_depth(), state.UNDO_LIMIT)


if __name__ == "__main__":
    unittest.main()
