"""Shared, split-aware graph utilities for Q4."""
from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from time import perf_counter
from typing import Iterable

import networkx as nx
import numpy as np
import torch
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[1]


def set_seed(seed: int) -> np.random.Generator:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    return np.random.default_rng(seed)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_nodes(path: Path | None = None) -> list[dict]:
    path = path or ROOT / "data" / "clean" / "node_metadata.csv"
    return [{**row, "node_code": int(row["node_code"]), "is_china": int(row["is_china"])} for row in read_csv(path)]


def load_edges(path: Path | None = None) -> list[dict]:
    path = path or ROOT / "data" / "clean" / "trade_flows.csv"
    return [{**row, "year": int(row["year"]), "reporter_code": int(row["reporter_code"]), "partner_code": int(row["partner_code"]), "trade_value_usd": float(row["trade_value_usd"])} for row in read_csv(path)]


def annual_graph(edges: list[dict], nodes: list[dict], year: int, top_k: int = 6) -> nx.DiGraph:
    """Build one period graph; top-k is selected before any undirected projection."""
    graph = nx.DiGraph(year=year)
    node_codes = [row["node_code"] for row in nodes]
    graph.add_nodes_from(node_codes)
    selected: list[dict] = []
    year_edges = [row for row in edges if row["year"] == year and row["trade_value_usd"] > 0]
    for reporter in node_codes:
        outgoing = [row for row in year_edges if row["reporter_code"] == reporter and row["partner_code"] != reporter]
        selected.extend(sorted(outgoing, key=lambda row: row["trade_value_usd"], reverse=True)[:top_k])
    for row in selected:
        graph.add_edge(row["reporter_code"], row["partner_code"], weight=row["trade_value_usd"])
    if nx.number_of_selfloops(graph):
        raise ValueError(f"self-loop in annual graph {year}")
    return graph


def undirected_graph(graph: nx.DiGraph) -> nx.Graph:
    result = nx.Graph(year=graph.graph.get("year"))
    result.add_nodes_from(graph.nodes)
    for left, right, attributes in graph.edges(data=True):
        if left == right:
            raise ValueError("self-loop cannot enter undirected projection")
        result.add_edge(left, right, weight=result.get_edge_data(left, right, {}).get("weight", 0.0) + float(attributes.get("weight", 0.0)))
    return result


def history_graph(edges: list[dict], nodes: list[dict], end_year: int, top_k: int) -> nx.Graph:
    """Union of annual analysis graphs up to end_year, with summed weights."""
    result = nx.Graph(history_end=end_year)
    result.add_nodes_from(row["node_code"] for row in nodes)
    for year in sorted({row["year"] for row in edges if row["year"] <= end_year}):
        for left, right, attrs in undirected_graph(annual_graph(edges, nodes, year, top_k)).edges(data=True):
            if result.has_edge(left, right):
                result[left][right]["weight"] += attrs["weight"]
            else:
                result.add_edge(left, right, weight=attrs["weight"])
    if nx.number_of_selfloops(result):
        raise ValueError("history graph contains self-loop")
    return result


def edge_pairs(graph: nx.Graph) -> list[tuple[int, int]]:
    return sorted((min(int(left), int(right)), max(int(left), int(right))) for left, right in graph.edges)


def all_pairs(nodes: Iterable[int]) -> list[tuple[int, int]]:
    ordered = sorted(int(node) for node in nodes)
    return [(left, right) for index, left in enumerate(ordered) for right in ordered[index + 1:]]


def sample_equal(values: list[tuple[int, int]], count: int, rng: np.random.Generator) -> list[tuple[int, int]]:
    if count == 0:
        return []
    if len(values) < count:
        raise ValueError(f"only {len(values)} candidate negatives for {count} requested")
    indices = rng.choice(len(values), size=count, replace=False)
    return [values[int(index)] for index in indices]


def future_split(history: nx.Graph, target: nx.Graph, rng: np.random.Generator) -> dict[str, list[tuple[int, int]]]:
    """Label only pairs absent from history: target edges are positives, non-target pairs negatives."""
    history_edges = set(edge_pairs(history))
    target_edges = set(edge_pairs(target))
    positives = sorted(target_edges - history_edges)
    negatives = sorted(set(all_pairs(history.nodes)) - history_edges - target_edges)
    negatives = sample_equal(negatives, len(positives), rng)
    rng.shuffle(positives); rng.shuffle(negatives)
    return {"positive": positives, "negative": negatives}


def future_directed_split(history: nx.DiGraph, target: nx.DiGraph, rng: np.random.Generator) -> dict[str, list[tuple[int, int]]]:
    """Chronological directed trade-edge labels for a target year."""
    history_edges = {(int(left), int(right)) for left, right in history.edges}
    target_edges = {(int(left), int(right)) for left, right in target.edges}
    positives = sorted(target_edges - history_edges)
    all_directed = {(left, right) for left in history.nodes for right in history.nodes if left != right}
    negatives = sorted(all_directed - history_edges - target_edges)
    negatives = sample_equal(negatives, len(positives), rng)
    rng.shuffle(positives); rng.shuffle(negatives)
    return {"positive": positives, "negative": negatives}


def reconstruction_split(history: nx.Graph, rng: np.random.Generator) -> dict[str, list[tuple[int, int]]]:
    """Training labels use only the observed history graph, never a future graph."""
    positives = edge_pairs(history)
    negative_candidates = sorted(set(all_pairs(history.nodes)) - set(positives))
    # Historical union graphs can be denser than one annual graph.  Keep the
    # training labels balanced by subsampling observed positives when needed;
    # the future validation/test labels remain equal by construction.
    count = min(len(positives), len(negative_candidates))
    positives = [positives[int(index)] for index in rng.choice(len(positives), size=count, replace=False)]
    negatives = sample_equal(negative_candidates, count, rng)
    rng.shuffle(positives); rng.shuffle(negatives)
    cut1 = max(1, int(0.8 * len(positives))); cut2 = max(cut1 + 1, int(0.9 * len(positives)))
    return {"train_positive": positives[:cut1], "train_negative": negatives[:cut1], "holdout_positive": positives[cut1:cut2], "holdout_negative": negatives[cut1:cut2]}


def labels_for(pairs: dict[str, list[tuple[int, int]]]) -> tuple[list[tuple[int, int]], np.ndarray]:
    positive = pairs["positive"]; negative = pairs["negative"]
    return positive + negative, np.asarray([1] * len(positive) + [0] * len(negative), dtype=int)


def region_labels(nodes: list[dict]) -> dict[int, str]:
    return {row["node_code"]: row["region"] for row in nodes}


def align_communities(previous: dict[int, int], current: dict[int, int], nodes: list[int]) -> dict[int, int]:
    old_ids = sorted(set(previous.values())); new_ids = sorted(set(current.values()))
    matrix = np.zeros((len(old_ids), len(new_ids)), dtype=int)
    for i, old_id in enumerate(old_ids):
        for j, new_id in enumerate(new_ids):
            matrix[i, j] = sum(previous[node] == old_id and current[node] == new_id for node in nodes)
    rows, cols = linear_sum_assignment(-matrix)
    mapping = {new_ids[col]: old_ids[row] for row, col in zip(rows, cols)}
    next_id = max(old_ids, default=-1) + 1
    for new_id in new_ids:
        mapping.setdefault(new_id, next_id); next_id += 1
    return mapping


def jsonable(value):
    if isinstance(value, dict): return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, (np.integer, np.floating)): return value.item()
    if isinstance(value, Path): return str(value)
    return value


def write_metrics(path: Path, params: dict, metrics: dict, fit_seconds: float, history: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"params": jsonable(params), "metrics": jsonable(metrics), "fit_seconds": float(fit_seconds), "history": jsonable(history)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_plot(figure, path: Path, div_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(path), include_plotlyjs=True, full_html=True, div_id=div_id)


def timed(function, *args, **kwargs):
    start = perf_counter(); value = function(*args, **kwargs); return value, perf_counter() - start

