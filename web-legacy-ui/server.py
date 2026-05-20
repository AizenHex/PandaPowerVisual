"""Small local server for the legacy HTML/CSS/JS Grid Simulator UI."""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

WEB_DIR = Path(__file__).resolve().parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import engine
import state


def _float(data: dict, key: str, default: float = 0.0) -> float:
    try:
        value = data.get(key, default)
        if value is None:
            value = default
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _register_attr(node_id: str, attr: str, role: str) -> None:
    state.attr_to_node[attr] = node_id
    state.attr_role[attr] = role


def _pin_attr(node_id: str, pin_name: str) -> str | None:
    node = state.nodes.get(node_id)
    if not node:
        return None

    kind = node.get("kind")
    if kind == "bus":
        return node["out_attr"] if pin_name.startswith("out") else node["in_attr"]
    if kind in {"load", "gen", "shunt"}:
        return node["pin"]
    if kind == "trafo":
        return node["hv_pin"] if pin_name == "hv" else node["lv_pin"]
    return None


def load_payload(payload: dict) -> None:
    """Load a front-end JSON payload into the shared headless simulator state."""
    state.reset()
    state.clear_undo()

    for node in payload.get("nodes", []):
        node_id = str(node["id"])
        frontend_kind = str(node["kind"])
        kind = "bus" if frontend_kind == "source" else frontend_kind

        data = {
            "kind": kind,
            "label": str(node.get("label") or node_id),
        }

        if kind == "bus":
            data.update(
                {
                    "vn_kv": _float(node, "vn_kv", 10.0 if frontend_kind == "source" else 0.4),
                    "is_slack": frontend_kind == "source" or bool(node.get("is_slack", False)),
                    "vm_pu": _float(node, "vm_pu", 1.0),
                    "va_degree": _float(node, "va_degree", 0.0),
                    "out_attr": f"{node_id}_out",
                    "in_attr": f"{node_id}_in",
                }
            )
            _register_attr(node_id, data["out_attr"], "p")
            _register_attr(node_id, data["in_attr"], "p")

        elif kind in {"load", "gen", "shunt"}:
            data.update(
                {
                    "p_mw": _float(node, "p_mw", 0.0),
                    "q_mvar": _float(node, "q_mvar", 0.0),
                    "pin": f"{node_id}_pin",
                }
            )
            _register_attr(node_id, data["pin"], "p")

        elif kind == "trafo":
            data.update(
                {
                    "sn_mva": _float(node, "sn_mva", 0.25),
                    "vn_hv_kv": _float(node, "vn_hv_kv", 10.0),
                    "vn_lv_kv": _float(node, "vn_lv_kv", 0.4),
                    "vk_percent": _float(node, "vk_percent", 4.0),
                    "vkr_percent": _float(node, "vkr_percent", 1.2),
                    "pfe_kw": _float(node, "pfe_kw", 0.0),
                    "i0_percent": _float(node, "i0_percent", 0.0),
                    "hv_pin": f"{node_id}_hv",
                    "lv_pin": f"{node_id}_lv",
                }
            )
            _register_attr(node_id, data["hv_pin"], "hv")
            _register_attr(node_id, data["lv_pin"], "lv")
        else:
            continue

        state.nodes[node_id] = data

    for link in payload.get("links", []):
        link_id = str(link["id"])
        from_node = str(link["fromNode"])
        to_node = str(link["toNode"])
        from_attr = _pin_attr(from_node, str(link.get("fromPin", "pin")))
        to_attr = _pin_attr(to_node, str(link.get("toPin", "pin")))
        if not from_attr or not to_attr:
            continue

        state.links[link_id] = (from_attr, to_attr)

        from_kind = state.nodes.get(from_node, {}).get("kind")
        to_kind = state.nodes.get(to_node, {}).get("kind")
        if from_kind == "bus" and to_kind == "bus":
            raw_line = link.get("line_data") or {}
            defaults = state.LINE_DEFAULTS
            state.line_data[link_id] = {
                "label": raw_line.get("label") or defaults["label"],
                "length_km": _float(raw_line, "length_km", defaults["length_km"]),
                "r_ohm_per_km": _float(raw_line, "r_ohm_per_km", defaults["r_ohm_per_km"]),
                "x_ohm_per_km": _float(raw_line, "x_ohm_per_km", defaults["x_ohm_per_km"]),
                "c_nf_per_km": _float(raw_line, "c_nf_per_km", defaults["c_nf_per_km"]),
                "max_i_ka": _float(raw_line, "max_i_ka", defaults["max_i_ka"]),
            }


def simulate_payload(payload: dict) -> dict:
    try:
        load_payload(payload)
        ok, message, _net, _node_map, _line_map = engine.run_pf()
        if ok:
            return {"ok": True, "results": state.last_results}
        return {"ok": False, "message": message}
    except Exception as exc:  # pragma: no cover - defensive API boundary
        return {"ok": False, "message": str(exc)}


class Handler(SimpleHTTPRequestHandler):
    server_version = "GridSimulatorWeb/1.0"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/simulate":
            self._send_json(404, {"ok": False, "message": "Endpoint tidak ditemukan."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            self._send_json(400, {"ok": False, "message": "Payload JSON tidak valid."})
            return

        self._send_json(200, simulate_payload(payload))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        request_path = unquote(parsed.path)
        if request_path in {"/", "/index.html"}:
            file_path = WEB_DIR / "index.html"
        else:
            file_path = (WEB_DIR / request_path.lstrip("/")).resolve()
            if WEB_DIR not in file_path.parents:
                self.send_error(403)
                return

        if not file_path.is_file():
            self.send_error(404)
            return

        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        if file_path.suffix in {".html", ".css", ".js"}:
            content_type += "; charset=utf-8"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args) -> None:
        print(f"[web-legacy-ui] {self.address_string()} - {format % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Grid Simulator web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Grid Simulator web UI running at {url}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")


if __name__ == "__main__":
    main()
