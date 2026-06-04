"""HTML report builder for power-flow simulation exports."""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

import state


APP_NAME = "PANDAPOWER VISUALIZATION"
TEMPLATE_PATH = Path(__file__).resolve().parent / "docs" / "report-template.html"


def validate_report_ready() -> str | None:
    """Return an error message when report export is not safe."""
    results = state.last_results
    if not results.get("nodes") and not results.get("links"):
        return "Belum ada hasil. Jalankan Run Power Flow dulu."
    if state.results_are_stale():
        return "Hasil sudah tidak sesuai model. Jalankan Run Power Flow lagi sebelum export."
    return None


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value, digits: int = 4, suffix: str = "") -> str:
    return f"{_num(value):.{digits}f}{suffix}"


def _status_for_loading(value: float) -> str:
    if value > 100:
        return "Overload"
    if value >= 80:
        return "Monitor"
    return "Normal"


def _status_for_voltage(value: float) -> str:
    if value < 0.95 or value > 1.05:
        return "Warning"
    return "Normal"


def _status_class(status: str) -> str:
    if status in {"Overload", "Warning"}:
        return "warn" if status == "Warning" else "danger"
    if status == "Monitor":
        return "warn"
    if status == "Slack":
        return "info"
    return "good"


def _node_counts() -> dict:
    counts = {"bus": 0, "line": 0, "trafo": 0, "load": 0}
    for node in state.nodes.values():
        kind = node.get("kind")
        if kind in counts:
            counts[kind] += 1
    counts["line"] = sum(1 for link in state.links if link in state.line_data)
    return counts


def _link_label(link_tag: str) -> str:
    data = state.line_data.get(link_tag, {})
    if data.get("label"):
        return str(data["label"])
    from_attr, to_attr = state.links.get(link_tag, (None, None))
    from_node = state.attr_to_node.get(from_attr)
    to_node = state.attr_to_node.get(to_attr)
    from_label = state.nodes.get(from_node, {}).get("label", "?")
    to_label = state.nodes.get(to_node, {}).get("label", "?")
    return f"{from_label} - {to_label}"


def _branch_rows() -> list[dict]:
    rows = []
    for link_tag, result in state.last_results.get("links", {}).items():
        table = str(result.get("table", "link"))
        p_value = result.get("p_from_mw", result.get("p_hv_mw", 0.0))
        q_value = result.get("q_from_mvar", result.get("q_hv_mvar", 0.0))
        loading = _num(result.get("loading_percent"))
        rows.append({
            "label": _link_label(link_tag),
            "table": table,
            "p_mw": _num(p_value),
            "q_mvar": _num(q_value),
            "loss_kw": _num(result.get("pl_mw")) * 1000,
            "loading_percent": loading,
            "status": _status_for_loading(loading),
        })
    return rows


def _bus_rows() -> list[dict]:
    rows = []
    for node_tag, node in state.nodes.items():
        if node.get("kind") != "bus":
            continue
        result = state.last_results.get("nodes", {}).get(node_tag, {})
        vm_pu = _num(result.get("vm_pu"))
        status = "Slack" if node.get("is_slack") else _status_for_voltage(vm_pu)
        rows.append({
            "label": node.get("label", node_tag),
            "vn_kv": _num(node.get("vn_kv")),
            "vm_pu": vm_pu,
            "va_degree": _num(result.get("va_degree")),
            "status": status,
        })
    return rows


def _engineering_notes(summary: dict) -> list[str]:
    notes = []
    if summary["min_voltage_pu"] and summary["min_voltage_pu"] < 0.95:
        notes.append("Terdapat indikasi undervoltage karena tegangan minimum berada di bawah 0.95 pu.")
    if summary["max_loading_percent"] > 100:
        notes.append("Terdapat komponen overload karena loading maksimum melewati 100%.")
    elif summary["max_loading_percent"] >= 80:
        notes.append("Terdapat komponen yang mendekati batas operasi dan perlu dimonitor.")
    if not notes:
        notes.append("Simulasi berada dalam batas operasi dasar.")
    return notes


def build_report_data(project_name: str = "Grid Simulation") -> dict:
    """Build a GUI-neutral report data snapshot from current state."""
    counts = _node_counts()
    branch_rows = _branch_rows()
    bus_rows = _bus_rows()
    total_load = sum(_num(n.get("p_mw")) for n in state.nodes.values() if n.get("kind") == "load")
    line_loss = sum(row["loss_kw"] for row in branch_rows if row["table"] == "line")
    trafo_loss = sum(row["loss_kw"] for row in branch_rows if row["table"] == "trafo")
    min_voltage = min((row["vm_pu"] for row in bus_rows if row["vm_pu"]), default=0.0)
    max_loading = max((row["loading_percent"] for row in branch_rows), default=0.0)
    grid_power = total_load + ((line_loss + trafo_loss) / 1000)

    summary = {
        "bus_count": counts["bus"],
        "line_count": counts["line"],
        "trafo_count": counts["trafo"],
        "load_count": counts["load"],
        "total_load_mw": total_load,
        "grid_power_mw": grid_power,
        "line_loss_kw": line_loss,
        "trafo_loss_kw": trafo_loss,
        "min_voltage_pu": min_voltage,
        "max_loading_percent": max_loading,
    }
    return {
        "metadata": {
            "app_name": APP_NAME,
            "project_name": project_name,
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "simulation_status": "Konvergen",
            "model_revision": f"r{state.result_revision[0]}",
        },
        "summary": summary,
        "charts": {
            "voltage_profile": [{"label": row["label"], "value": row["vm_pu"]} for row in bus_rows],
            "loading_profile": [{"label": row["label"], "value": row["loading_percent"]} for row in branch_rows],
            "loss_breakdown": {
                "line_loss_kw": line_loss,
                "trafo_loss_kw": trafo_loss,
            },
        },
        "tables": {
            "bus_results": bus_rows,
            "branch_results": branch_rows,
        },
        "notes": _engineering_notes(summary),
    }


def _template_css() -> str:
    print_css = """
    .print-actions {
      display: flex;
      justify-content: flex-end;
      max-width: 1120px;
      margin: 18px auto 0;
      padding: 0 24px;
    }

    .print-actions button {
      border: 1px solid var(--deep);
      border-radius: var(--radius);
      background: var(--deep);
      color: #ffffff;
      cursor: pointer;
      font: 700 13px var(--sans);
      padding: 9px 14px;
    }

    .print-actions button:hover {
      background: var(--blue);
    }

    @media print {
      .print-actions {
        display: none;
      }
    }
    """
    if not TEMPLATE_PATH.exists():
        return "body{font-family:Arial,sans-serif;margin:24px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px}" + print_css
    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    start = text.find("<style>")
    end = text.find("</style>")
    if start == -1 or end == -1:
        return print_css
    return text[start + len("<style>"):end].strip() + print_css


def _bar_rows(items: list[dict], max_value: float, value_suffix: str, warn_at: float | None = None) -> str:
    rows = []
    max_value = max(max_value, 1.0)
    for item in items:
        value = _num(item.get("value"))
        width = max(0, min(100, (value / max_value) * 100))
        cls = "warn" if warn_at is not None and value >= warn_at else ""
        rows.append(
            '<div class="bar-row">'
            f'<span class="bar-label">{escape(str(item.get("label", "-")))}</span>'
            f'<span class="bar-track"><span class="bar-fill {cls}" style="width: {width:.1f}%"></span></span>'
            f'<span class="bar-value">{_fmt(value, 4 if value_suffix == " pu" else 1)}{escape(value_suffix)}</span>'
            "</div>"
        )
    return "\n".join(rows) or '<p class="caption">Tidak ada data.</p>'


def _summary_metric(label: str, value: str, note: str, cls: str = "") -> str:
    class_name = f"metric {cls}".strip()
    return (
        f'<div class="{class_name}">'
        f'<div class="metric-label">{escape(label)}</div>'
        f'<div class="metric-value">{value}</div>'
        f'<div class="metric-note">{escape(note)}</div>'
        "</div>"
    )


def _branch_table(rows: list[dict]) -> str:
    body = []
    for row in rows:
        status = str(row.get("status", "Normal"))
        body.append(
            "<tr>"
            f"<td>{escape(str(row.get('label', '-')))}</td>"
            f"<td>{escape(str(row.get('table', '-')))}</td>"
            f"<td class=\"num\">{_fmt(row.get('p_mw'), 4)} MW</td>"
            f"<td class=\"num\">{_fmt(row.get('q_mvar'), 4)} MVAr</td>"
            f"<td class=\"num\">{_fmt(row.get('loss_kw'), 3)} kW</td>"
            f"<td class=\"num\">{_fmt(row.get('loading_percent'), 1)}%</td>"
            f"<td><span class=\"tag {_status_class(status)}\">{escape(status)}</span></td>"
            "</tr>"
        )
    return "\n".join(body) or '<tr><td colspan="7">Tidak ada data saluran.</td></tr>'


def _bus_table(rows: list[dict]) -> str:
    body = []
    for row in rows:
        status = str(row.get("status", "Normal"))
        body.append(
            "<tr>"
            f"<td>{escape(str(row.get('label', '-')))}</td>"
            f"<td class=\"num\">{_fmt(row.get('vn_kv'), 3)} kV</td>"
            f"<td class=\"num\">{_fmt(row.get('vm_pu'), 4)}</td>"
            f"<td class=\"num\">{_fmt(row.get('va_degree'), 2)} deg</td>"
            f"<td><span class=\"tag {_status_class(status)}\">{escape(status)}</span></td>"
            "</tr>"
        )
    return "\n".join(body) or '<tr><td colspan="5">Tidak ada data bus.</td></tr>'


def render_report_html(data: dict, diagram_src: str) -> str:
    """Render a complete standalone HTML report."""
    css = _template_css()
    metadata = data["metadata"]
    summary = data["summary"]
    charts = data["charts"]
    tables = data["tables"]
    notes = data.get("notes", [])
    max_voltage = max((item["value"] for item in charts["voltage_profile"]), default=1.0)
    max_loading = max((item["value"] for item in charts["loading_profile"]), default=100.0)
    status_class = _status_class(_status_for_loading(summary["max_loading_percent"]))
    voltage_class = "is-warn" if summary["min_voltage_pu"] and summary["min_voltage_pu"] < 0.95 else "is-good"
    loading_class = "is-warn" if summary["max_loading_percent"] >= 80 else "is-good"
    note_html = "<br>".join(escape(str(note)) for note in notes)

    return f"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Laporan Hasil Simulasi Power Flow</title>
  <style>{css}</style>
</head>
<body>
  <div class="print-actions" aria-label="Aksi laporan">
    <button type="button" onclick="window.print()">Print / Save PDF</button>
  </div>
  <main class="report-shell">
    <article class="report">
      <header class="cover-band">
        <div>
          <p class="eyebrow">{escape(str(metadata.get("app_name", APP_NAME)))}</p>
          <h1>Laporan Hasil Simulasi Power Flow</h1>
          <p class="cover-copy">Ringkasan teknis rangkaian, profil tegangan, loading saluran, rugi-rugi, dan catatan validasi dari model jaringan listrik yang disimulasikan.</p>
        </div>
        <aside class="status-card" aria-label="Status simulasi">
          <strong>Status Simulasi</strong>
          <span class="status-pill"><span class="status-dot"></span>{escape(str(metadata.get("simulation_status", "Konvergen")))}</span>
          <div class="metadata-grid">
            <div><span>Project</span>{escape(str(metadata.get("project_name", "Grid Simulation")))}</div>
            <div><span>Export</span>{escape(str(metadata.get("exported_at", "-")))}</div>
            <div><span>Solver</span>pandapower</div>
            <div><span>Revision</span>{escape(str(metadata.get("model_revision", "-")))}</div>
          </div>
        </aside>
      </header>
      <div class="content">
        <section class="section">
          <div class="section-heading"><h2>Ringkasan Jaringan</h2><span class="section-kicker">simulation_summary</span></div>
          <div class="summary-grid">
            {_summary_metric("Buses", str(summary["bus_count"]), "Total bus", "is-info")}
            {_summary_metric("Lines", str(summary["line_count"]), "Total saluran", "is-info")}
            {_summary_metric("Loads", str(summary["load_count"]), "Total beban", "")}
            {_summary_metric("Total Load", f'{_fmt(summary["total_load_mw"], 4)}<span class="metric-unit">MW</span>', "Active demand", "")}
            {_summary_metric("Grid Power", f'{_fmt(summary["grid_power_mw"], 4)}<span class="metric-unit">MW</span>', "External grid supply", "")}
            {_summary_metric("Line Loss", f'{_fmt(summary["line_loss_kw"], 3)}<span class="metric-unit">kW</span>', "Total line losses", "")}
            {_summary_metric("Minimum Voltage", f'{_fmt(summary["min_voltage_pu"], 4)}<span class="metric-unit">pu</span>', "Voltage profile", voltage_class)}
            {_summary_metric("Maximum Loading", f'{_fmt(summary["max_loading_percent"], 1)}<span class="metric-unit">%</span>', "Branch loading", loading_class)}
          </div>
        </section>
        <section class="section">
          <div class="section-heading"><h2>Diagram Rangkaian</h2><span class="section-kicker">diagram_image</span></div>
          <figure>
            <div class="diagram-frame"><img src="{escape(diagram_src, quote=True)}" alt="Diagram rangkaian simulasi"></div>
            <figcaption class="caption">Gambar 1. Diagram rangkaian yang digunakan pada simulasi power flow.</figcaption>
          </figure>
        </section>
        <section class="section">
          <div class="section-heading"><h2>Grafik Hasil Simulasi</h2><span class="section-kicker">charts</span></div>
          <div class="charts-grid">
            <div class="chart-panel"><div class="chart-title"><h3>Voltage Profile</h3><span>pu</span></div>{_bar_rows(charts["voltage_profile"], max_voltage, " pu")}</div>
            <div class="chart-panel"><div class="chart-title"><h3>Line and Transformer Loading</h3><span>%</span></div>{_bar_rows(charts["loading_profile"], max(100.0, max_loading), "%", warn_at=80)}</div>
            <div class="chart-panel wide">
              <div class="chart-title"><h3>Loss Breakdown</h3><span>kW</span></div>
              <div class="loss-bars">
                <div class="loss-block"><b>Line Losses</b><strong>{_fmt(summary["line_loss_kw"], 3)}</strong><span> kW from feeder lines</span></div>
                <div class="loss-block"><b>Transformer Losses</b><strong>{_fmt(summary["trafo_loss_kw"], 3)}</strong><span> kW from transformer model</span></div>
              </div>
            </div>
          </div>
        </section>
        <section class="section">
          <div class="section-heading"><h2>Engineering Notes</h2><span class="section-kicker">rule_based_notes</span></div>
          <div class="notes-grid">
            <div class="note-box"><h3>Kondisi Operasi</h3><p>{note_html}</p></div>
            <div class="validation-box"><h3>Catatan Validasi</h3><p>Model valid, hasil power flow tidak stale, dan snapshot diagram dibuat dari canvas aktif saat laporan diekspor.</p></div>
          </div>
        </section>
        <section class="section">
          <div class="section-heading"><h2>Tabel Hasil Saluran dan Trafo</h2><span class="section-kicker">branch_results</span></div>
          <div class="table-wrap"><table><thead><tr><th>Komponen</th><th>Tipe</th><th class="num">P</th><th class="num">Q</th><th class="num">Loss</th><th class="num">Loading</th><th>Status</th></tr></thead><tbody>{_branch_table(tables["branch_results"])}</tbody></table></div>
        </section>
        <section class="section">
          <div class="section-heading"><h2>Tabel Tegangan Bus</h2><span class="section-kicker">bus_results</span></div>
          <div class="table-wrap"><table><thead><tr><th>Bus</th><th class="num">V Nominal</th><th class="num">V pu</th><th class="num">Angle</th><th>Status</th></tr></thead><tbody>{_bus_table(tables["bus_results"])}</tbody></table></div>
        </section>
        <footer class="footer"><span>{escape(APP_NAME)} - HTML report</span><span>Generated from simulation snapshot</span></footer>
      </div>
    </article>
  </main>
</body>
</html>"""


def write_report(path: Path, diagram_src: str, project_name: str = "Grid Simulation") -> None:
    data = build_report_data(project_name=project_name)
    path.write_text(render_report_html(data, diagram_src), encoding="utf-8")
