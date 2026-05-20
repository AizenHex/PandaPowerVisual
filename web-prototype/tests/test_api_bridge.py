import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main

class ApiBridgeTest(unittest.TestCase):
    def setUp(self):
        self.api = main.Api()

    def test_simulate_radial_network_converges(self):
        # Mirroring the radial template payload from front-end
        payload = {
            "nodes": [
                {
                    "id": "source-1",
                    "kind": "source",
                    "label": "Ext Grid",
                    "vn_kv": 10.0,
                    "is_slack": True,
                    "vm_pu": 1.0,
                    "va_degree": 0.0
                },
                {
                    "id": "trafo-1",
                    "kind": "trafo",
                    "label": "Trafo 10/0.4 kV",
                    "sn_mva": 0.25,
                    "vn_hv_kv": 10.0,
                    "vn_lv_kv": 0.4,
                    "vk_percent": 4.0,
                    "vkr_percent": 1.2,
                    "pfe_kw": 0.0,
                    "i0_percent": 0.0
                },
                {
                    "id": "bus-1",
                    "kind": "bus",
                    "label": "Busbar Utama",
                    "vn_kv": 0.4
                },
                {
                    "id": "bus-2",
                    "kind": "bus",
                    "label": "Busbar 2",
                    "vn_kv": 0.4
                },
                {
                    "id": "load-1",
                    "kind": "load",
                    "label": "Beban 1",
                    "p_mw": 0.03,
                    "q_mvar": 0.01
                }
            ],
            "links": [
                {
                    "id": "link-1",
                    "fromNode": "source-1",
                    "fromPin": "out",
                    "toNode": "trafo-1",
                    "toPin": "hv"
                },
                {
                    "id": "link-2",
                    "fromNode": "trafo-1",
                    "fromPin": "lv",
                    "toNode": "bus-1",
                    "toPin": "in"
                },
                {
                    "id": "link-3",
                    "fromNode": "bus-1",
                    "fromPin": "out",
                    "toNode": "bus-2",
                    "toPin": "in",
                    "line_data": {
                        "label": "Line 1",
                        "length_km": 0.05,
                        "r_ohm_per_km": 0.225,
                        "x_ohm_per_km": 0.08,
                        "c_nf_per_km": 264.0,
                        "max_i_ka": 0.242
                    }
                },
                {
                    "id": "link-4",
                    "fromNode": "bus-2",
                    "fromPin": "out",
                    "toNode": "load-1",
                    "toPin": "pin"
                }
            ]
        }

        res = self.api.simulate(payload)

        self.assertTrue(res["ok"], res.get("message"))
        self.assertIn("results", res)
        results = res["results"]
        
        # Verify buses are solved
        self.assertIn("bus-1", results["nodes"])
        self.assertIn("bus-2", results["nodes"])
        self.assertAlmostEqual(results["nodes"]["bus-1"]["vm_pu"], 1.0, delta=0.05)
        
        # Verify lines are solved
        self.assertIn("link-3", results["links"])
        self.assertIn("loading_percent", results["links"]["link-3"])
        self.assertGreater(results["links"]["link-3"]["loading_percent"], 0)

    def test_simulate_validation_errors_returned(self):
        # Empty network payload
        payload = {"nodes": [], "links": []}
        res = self.api.simulate(payload)
        
        self.assertFalse(res["ok"])
        self.assertIn("Canvas masih kosong", res["message"])

if __name__ == "__main__":
    unittest.main()
