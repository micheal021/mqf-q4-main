"""Compare Q4A descriptive structure and Q4B untouched future-test scores."""
from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go
from rich.console import Console
from rich.table import Table

from common import ROOT, save_plot


def main() -> None:
    a_path = ROOT / "results" / "approach1" / "q4" / "metrics.json"; b_path = ROOT / "results" / "approach2" / "q4" / "metrics.json"
    if not a_path.exists() or not b_path.exists(): raise FileNotFoundError("run both approaches before compare.py")
    a = json.loads(a_path.read_text(encoding="utf-8")); b = json.loads(b_path.read_text(encoding="utf-8")); am = a["metrics"]; bm = b["metrics"]
    test = bm["test"]; rows = [("node2vec", test["learned"]["auc"], test["learned"]["average_precision"])] + [(name, value["auc"], value["average_precision"]) for name, value in test["baselines"].items()]
    rows.sort(key=lambda row: (row[1], row[2]), reverse=True)
    console = Console(); table = Table(title="Q4 untouched 2023 future-edge test")
    for column in ["Rank", "Method", "AUC", "Average precision"]: table.add_column(column)
    for rank, (method, auc, average_precision) in enumerate(rows, 1): table.add_row(str(rank), method, f"{auc:.3f}", f"{average_precision:.3f}")
    console.print(table)
    summary = Table(title="Q4A latest-year descriptive check"); [summary.add_column(column) for column in ["Year", "Directed edges", "Undirected edges", "Components", "Modularity", "MST diameter"]]
    latest = am["per_year"][str(max(am["years"]))]; summary.add_row(str(max(am["years"])), str(latest["directed_edges"]), str(latest["undirected_edges"]), str(latest["connected_components"]), f"{latest['communities']['modularity']:.3f}", str(latest["mst"]["largest_component_diameter"])); console.print(summary)
    figure = go.Figure([go.Bar(x=[row[0] for row in rows], y=[row[1] for row in rows], text=[f"{row[1]:.3f}" for row in rows], textposition="auto")]); figure.update_layout(title="Untouched 2023 directed future-edge test", xaxis_title="Method", yaxis_title="AUC")
    save_plot(figure, ROOT / "results" / "comparison.html", "q4_comparison")


if __name__ == "__main__": main()

