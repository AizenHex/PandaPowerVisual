import importlib.util
import sys
import unittest
from pathlib import Path

# server.py is in the parent directory of this tests/ folder (web-legacy-ui/)
ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "server.py"

spec = importlib.util.spec_from_file_location("web_legacy_server", SERVER_PATH)
web_legacy_server = importlib.util.module_from_spec(spec)
sys.modules["web_legacy_server"] = web_legacy_server
spec.loader.exec_module(web_legacy_server)


class WebLegacyServerTest(unittest.TestCase):
    def test_simulate_payload_converges_with_source_to_trafo_template(self):
        payload = {
            "nodes": [
                {
                    "id": "source-1",
                    "kind": "source",
                    "label": "Ext Grid",
                    "vn_kv": 10.0,
                    "is_slack": True,
                    "vm_pu": 1.0,
                    "va_degree": 0.0,
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
                    "i0_percent": 0.0,
                },
                {"id": "bus-1", "kind": "bus", "label": "Busbar Utama", "vn_kv": 0.4},
                {"id": "bus-2", "kind": "bus", "label": "Busbar 2", "vn_kv": 0.4},
                {"id": "load-1", "kind": "load", "label": "Beban 1", "p_mw": 0.03, "q_mvar": 0.01},
            ],
            "links": [
                {"id": "link-1", "fromNode": "source-1", "fromPin": "out", "toNode": "trafo-1", "toPin": "hv"},
                {"id": "link-2", "fromNode": "trafo-1", "fromPin": "lv", "toNode": "bus-1", "toPin": "in"},
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
                        "max_i_ka": 0.242,
                    },
                },
                {"id": "link-4", "fromNode": "bus-2", "fromPin": "out", "toNode": "load-1", "toPin": "pin"},
            ],
        }

        response = web_legacy_server.simulate_payload(payload)

        self.assertTrue(response["ok"], response.get("message"))
        self.assertIn("bus-1", response["results"]["nodes"])
        self.assertIn("link-3", response["results"]["links"])

    def test_simulate_payload_returns_validation_error(self):
        response = web_legacy_server.simulate_payload({"nodes": [], "links": []})

        self.assertFalse(response["ok"])
        self.assertIn("Canvas masih kosong", response["message"])


if __name__ == "__main__":
    unittest.main()
