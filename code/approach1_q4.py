"""Q4A: annual trade-network analytics with explicit verification."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import networkx as nx
import numpy as np
import plotly.graph_objects as go
from rich.console import Console
from rich.table import Table
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

from common import ROOT, align_communities, annual_graph, history_graph, load_edges, load_nodes, region_labels, save_plot, set_seed, undirected_graph, write_metrics


def statistics(directed: nx.DiGraph, undirected: nx.Graph) -> dict:
    degree = np.asarray([value for _, value in undirected.degree()], dtype=float)
    positive = degree[degree > 0]
    slope = None
    if len(positive) > 1 and len(np.unique(positive)) > 1:
        values, counts = np.unique(positive, return_counts=True)
        slope = float(np.polyfit(np.log(values), np.log(counts), 1)[0])
    assortativity = nx.degree_assortativity_coefficient(undirected) if undirected.number_of_edges() else np.nan
    return {"nodes": directed.number_of_nodes(), "directed_edges": directed.number_of_edges(), "undirected_edges": undirected.number_of_edges(), "directed_density": float(nx.density(directed)), "undirected_density": float(nx.density(undirected)), "mean_degree": float(degree.mean()), "degree_loglog_slope": slope, "assortativity": None if not np.isfinite(assortativity) else float(assortativity), "connected_components": nx.number_connected_components(undirected), "isolated_nodes": int(sum(undirected.degree(node) == 0 for node in undirected)), "self_loops_directed": int(nx.number_of_selfloops(directed)), "self_loops_undirected": int(nx.number_of_selfloops(undirected))}


def metric_mst(graph: nx.Graph) -> dict:
    metric = nx.Graph(); metric.add_nodes_from(graph.nodes)
    for left, right, attrs in graph.edges(data=True):
        metric.add_edge(left, right, distance=1.0 / np.log1p(max(float(attrs.get("weight", 0.0)), 1e-12)))
    forest = nx.minimum_spanning_tree(metric, weight="distance", algorithm="kruskal")
    components = list(nx.connected_components(forest))
    largest = max(components, key=len, default=set())
    component_graph = forest.subgraph(largest)
    return {"forest_edges": forest.number_of_edges(), "forest_components": len(components), "largest_component_nodes": len(largest), "largest_component_diameter": int(nx.diameter(component_graph)) if len(largest) > 1 else 0, "total_distance": float(sum(attrs["distance"] for _, _, attrs in forest.edges(data=True)))}


def communities(graph: nx.Graph, nodes: list[dict], resolution: float, seed: int) -> tuple[dict, dict]:
    groups = nx.community.louvain_communities(graph, weight="weight", resolution=resolution, seed=seed)
    labels = {node: index for index, group in enumerate(sorted(groups, key=lambda group: min(group)) ) for node in group}
    order = sorted(graph.nodes)
    region_map = region_labels(nodes); region_ids = {name: i for i, name in enumerate(sorted(set(region_map.values())))}
    region_vector = [region_ids.get(region_map.get(node, "Other"), -1) for node in order]
    label_vector = [labels[node] for node in order]
    return {"resolution": resolution, "community_count": len(groups), "modularity": float(nx.community.modularity(graph, groups, weight="weight")), "ari_vs_region_proxy": float(adjusted_rand_score(region_vector, label_vector)), "nmi_vs_region_proxy": float(normalized_mutual_info_score(region_vector, label_vector))}, labels


def centrality(graph: nx.DiGraph, undirected: nx.Graph) -> dict:
    metric = nx.Graph(); metric.add_nodes_from(undirected.nodes)
    for left, right, attrs in undirected.edges(data=True): metric.add_edge(left, right, distance=1.0 / np.log1p(max(float(attrs["weight"]), 1e-12)))
    return {"pagerank": sorted(nx.pagerank(graph, weight="weight").items(), key=lambda item: item[1], reverse=True)[:10], "betweenness": sorted(nx.betweenness_centrality(metric, weight="distance").items(), key=lambda item: item[1], reverse=True)[:10], "weighted_degree": sorted(undirected.degree(weight="weight"), key=lambda item: item[1], reverse=True)[:10]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--resolutions", default="0.5,1.0,1.5")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "approach1" / "q4")
    args = parser.parse_args(); set_seed(args.seed); started = time.perf_counter()
    nodes = load_nodes(); edges = load_edges(); years = sorted({row["year"] for row in edges}); resolution_values = [float(value) for value in args.resolutions.split(",")]
    per_year: dict[str, dict] = {}; labels_by_year: dict[int, dict[int, int]] = {}
    for year in years:
        directed = annual_graph(edges, nodes, year, args.top_k); undirected = undirected_graph(directed)
        summary = statistics(directed, undirected); summary["mst"] = metric_mst(undirected); summary["centrality"] = centrality(directed, undirected)
        selected, labels = communities(undirected, nodes, args.resolution, args.seed); labels_by_year[year] = labels
        summary["communities"] = selected
        summary["resolution_sweep"] = {str(resolution): communities(undirected, nodes, resolution, args.seed)[0] for resolution in resolution_values}
        per_year[str(year)] = summary
    migration = {}
    ordered_nodes = sorted(row["node_code"] for row in nodes)
    for previous, current in zip(years, years[1:]):
        mapping = align_communities(labels_by_year[previous], labels_by_year[current], ordered_nodes)
        aligned = {node: mapping[label] for node, label in labels_by_year[current].items()}
        old = [labels_by_year[previous][node] for node in ordered_nodes]; new = [aligned[node] for node in ordered_nodes]
        migration[f"{previous}->{current}"] = {"changed_share": float(np.mean(np.asarray(old) != np.asarray(new))), "ari": float(adjusted_rand_score(old, new)), "contingency": [[sum(a == old_id and b == new_id for a, b in zip(old, new)) for new_id in sorted(set(new))] for old_id in sorted(set(old))]}
    figure = go.Figure([go.Scatter(x=years, y=[per_year[str(year)]["communities"]["modularity"] for year in years], mode="lines+markers", name="Louvain modularity"), go.Scatter(x=years, y=[per_year[str(year)]["mst"]["largest_component_diameter"] for year in years], mode="lines+markers", name="MST diameter", yaxis="y2")])
    figure.update_layout(title="Annual trade-network structure", xaxis_title="Year", yaxis_title="Modularity", yaxis2={"title": "MST diameter", "overlaying": "y", "side": "right"})
    save_plot(figure, args.out / "network_evolution.html", "q4a_network_evolution")
    metrics = {"years": years, "construction": {"top_k_exports_per_reporter": args.top_k, "undirected_weight": "sum of reciprocal directed exports", "mst_distance": "1/log(1+trade_value_usd)"}, "per_year": per_year, "community_migration": migration, "verification": {"self_loops_total": sum(item["self_loops_directed"] + item["self_loops_undirected"] for item in per_year.values()), "isolated_nodes_reported": True, "betweenness_distance_attribute": True, "migration_alignment": "Hungarian maximum-overlap alignment"}}
    write_metrics(args.out / "metrics.json", {"seed": args.seed, "top_k": args.top_k, "resolutions": resolution_values}, metrics, time.perf_counter() - started, {"years": years})
    table = Table(title="Q4A network analytics"); [table.add_column(column) for column in ["Year", "Nodes", "Edges", "Components", "Communities", "Modularity"]]
    for year in years:
        item = per_year[str(year)]; table.add_row(str(year), str(item["nodes"]), str(item["undirected_edges"]), str(item["connected_components"]), str(item["communities"]["community_count"]), f"{item['communities']['modularity']:.3f}")
    Console().print(table)


if __name__ == "__main__": main()

