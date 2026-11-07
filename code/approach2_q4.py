"""Q4B: node2vec future-edge prediction with strict chronological isolation."""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import networkx as nx
import numpy as np
import plotly.graph_objects as go
import torch
from rich.console import Console
from rich.table import Table
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, average_precision_score, normalized_mutual_info_score, roc_auc_score

from common import ROOT, annual_graph, future_directed_split, load_edges, load_nodes, reconstruction_split, save_plot, set_seed, undirected_graph, write_metrics


def biased_walk(graph: nx.Graph, start: int, length: int, p: float, q: float, rng: np.random.Generator) -> list[int]:
    walk = [start]
    while len(walk) < length:
        current = walk[-1]; neighbors = sorted(graph.neighbors(current))
        if not neighbors: break
        weights = []
        previous = walk[-2] if len(walk) > 1 else None
        for neighbor in neighbors:
            bias = 1.0 if previous is None else (1.0 / p if neighbor == previous else 1.0 if graph.has_edge(previous, neighbor) else 1.0 / q)
            weights.append(max(float(graph[current][neighbor].get("weight", 1.0)), 1e-12) * bias)
        probabilities = np.asarray(weights, dtype=float); probabilities /= probabilities.sum()
        walk.append(int(rng.choice(neighbors, p=probabilities)))
    return walk


def walk_pairs(graph: nx.Graph, p: float, q: float, rng: np.random.Generator, walks_per_node: int, length: int, window: int) -> list[tuple[int, int]]:
    nodes = sorted(graph.nodes); pairs = []
    for _ in range(walks_per_node):
        order = list(nodes); rng.shuffle(order)
        for start in order:
            walk = biased_walk(graph, int(start), length, p, q, rng)
            for center, source in enumerate(walk):
                for offset in range(1, window + 1):
                    for position in (center - offset, center + offset):
                        if 0 <= position < len(walk): pairs.append((source, walk[position]))
    return pairs


def train_skipgram(pairs: list[tuple[int, int]], nodes: list[int], dimension: int, seed: int, epochs: int, negative_count: int) -> np.ndarray:
    if not pairs: raise ValueError("training graph produced no walk contexts")
    torch.manual_seed(seed); index = {node: i for i, node in enumerate(nodes)}
    sources = torch.tensor([index[left] for left, _ in pairs], dtype=torch.long); targets = torch.tensor([index[right] for _, right in pairs], dtype=torch.long)
    embedding = torch.nn.Embedding(len(nodes), dimension); context = torch.nn.Embedding(len(nodes), dimension)
    torch.nn.init.xavier_uniform_(embedding.weight); torch.nn.init.zeros_(context.weight)
    optimizer = torch.optim.Adam([*embedding.parameters(), *context.parameters()], lr=0.03); generator = torch.Generator().manual_seed(seed + 11)
    history = []
    for _ in range(epochs):
        order = torch.randperm(len(sources), generator=generator); losses = []
        for start in range(0, len(order), 512):
            batch = order[start:start + 512]; source_vector = embedding(sources[batch]); target_vector = context(targets[batch])
            positive = (source_vector * target_vector).sum(dim=1); negative_targets = torch.randint(len(nodes), (len(batch), negative_count), generator=generator)
            negative = torch.einsum("bd,bnd->bn", source_vector, context(negative_targets)); loss = -torch.nn.functional.logsigmoid(positive).mean() - torch.nn.functional.logsigmoid(-negative).mean()
            optimizer.zero_grad(); loss.backward(); optimizer.step(); losses.append(float(loss.detach()))
        history.append(float(np.mean(losses)))
    return embedding.weight.detach().cpu().numpy(), history


def fit_bilinear(embeddings: np.ndarray, nodes: list[int], history: nx.Graph, seed: int) -> tuple[np.ndarray, dict]:
    rng = np.random.default_rng(seed); labels = reconstruction_split(history, rng); positive = labels["train_positive"]; negative = labels["train_negative"]; pairs = positive + negative
    index = {node: i for i, node in enumerate(nodes)}; left = torch.tensor([index[a] for a, _ in pairs]); right = torch.tensor([index[b] for _, b in pairs]); y = torch.tensor([1.0] * len(positive) + [0.0] * len(negative))
    matrix = torch.nn.Parameter(torch.eye(embeddings.shape[1])); tensor = torch.tensor(embeddings, dtype=torch.float32); optimizer = torch.optim.Adam([matrix], lr=0.05)
    losses = []
    for _ in range(160):
        score = torch.einsum("bi,ij,bj->b", tensor[left], matrix, tensor[right]); loss = torch.nn.functional.binary_cross_entropy_with_logits(score, y); optimizer.zero_grad(); loss.backward(); optimizer.step(); losses.append(float(loss.detach()))
    return matrix.detach().numpy(), {"epochs": 160, "initial_loss": losses[0], "final_loss": losses[-1], "training_positive": len(positive), "training_negative": len(negative)}


def scores(embeddings: np.ndarray, matrix: np.ndarray, nodes: list[int], pairs: list[tuple[int, int]]) -> np.ndarray:
    index = {node: i for i, node in enumerate(nodes)}; output = []
    for left, right in pairs:
        raw = embeddings[index[left]] @ matrix @ embeddings[index[right]]; output.append(float(1.0 / (1.0 + math.exp(-float(np.clip(raw, -50, 50))))))
    return np.asarray(output)


def evaluate(pairs: dict[str, list[tuple[int, int]]], values: np.ndarray) -> dict[str, float]:
    labels = np.asarray([1] * len(pairs["positive"]) + [0] * len(pairs["negative"])); return {"auc": float(roc_auc_score(labels, values)), "average_precision": float(average_precision_score(labels, values)), "positive_count": len(pairs["positive"]), "negative_count": len(pairs["negative"])}


def heuristic_scores(graph: nx.Graph, pairs: list[tuple[int, int]], method: str) -> np.ndarray:
    if method == "common_neighbors": values = {(a, b): len(list(nx.common_neighbors(graph, a, b))) for a, b in pairs}
    elif method == "adamic_adar": values = {(a, b): score for a, b, score in nx.adamic_adar_index(graph, pairs)}
    else: values = {(a, b): score for a, b, score in nx.preferential_attachment(graph, pairs)}
    return np.asarray([float(values.get(pair, 0.0)) for pair in pairs])


def fit_and_evaluate(history: nx.Graph, history_directed: nx.DiGraph, future: dict[str, list[tuple[int, int]]], nodes: list[int], p: float, q: float, dimension: int, seed: int, args: argparse.Namespace) -> dict:
    rng = np.random.default_rng(seed); pairs = future["positive"] + future["negative"]
    contexts = walk_pairs(history, p, q, rng, args.walks_per_node, args.walk_length, args.window); embeddings, loss_history = train_skipgram(contexts, nodes, dimension, seed, args.epochs, args.negative_count); matrix, bilinear_history = fit_bilinear(embeddings, nodes, history, seed + 19)
    learned = evaluate(future, scores(embeddings, matrix, nodes, pairs)); baselines = {name: evaluate(future, heuristic_scores(history, pairs, name)) for name in ["common_neighbors", "adamic_adar", "preferential_attachment"]}
    return {"learned": learned, "baselines": baselines, "future_split": {"positive": future["positive"], "negative": future["negative"]}, "training_graph": {"history_end": history.graph.get("year"), "nodes": history.number_of_nodes(), "undirected_edges": history.number_of_edges(), "directed_edges": history_directed.number_of_edges()}, "training": {"walk_contexts": len(contexts), "p": p, "q": q, "dimension": dimension, "skipgram_loss": loss_history, "bilinear": bilinear_history}}


def cluster_agreement(embeddings: np.ndarray, history: nx.Graph, nodes: list[dict], seed: int) -> dict:
    groups = nx.community.louvain_communities(history, weight="weight", seed=seed); louvain = {node: i for i, group in enumerate(sorted(groups, key=lambda group: min(group))) for node in group}; order = [row["node_code"] for row in nodes]; k = max(2, len(groups)); labels = KMeans(n_clusters=k, random_state=seed, n_init=10).fit_predict(embeddings)
    regions = {row["node_code"]: row["region"] for row in nodes}; region_ids = {name: i for i, name in enumerate(sorted(set(regions.values())))}
    return {"kmeans_k": k, "ari_vs_louvain": float(adjusted_rand_score([louvain[node] for node in order], labels)), "nmi_vs_louvain": float(normalized_mutual_info_score([louvain[node] for node in order], labels)), "ari_vs_region_proxy": float(adjusted_rand_score([region_ids[regions[node]] for node in order], labels)), "nmi_vs_region_proxy": float(normalized_mutual_info_score([region_ids[regions[node]] for node in order], labels))}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--seed", type=int, default=42); parser.add_argument("--top-k", type=int, default=10); parser.add_argument("--dimensions", default="8,16,32,64"); parser.add_argument("--p-values", default="0.5,1,2"); parser.add_argument("--q-values", default="0.5,1,2"); parser.add_argument("--epochs", type=int, default=5); parser.add_argument("--walks-per-node", type=int, default=8); parser.add_argument("--walk-length", type=int, default=20); parser.add_argument("--window", type=int, default=2); parser.add_argument("--negative-count", type=int, default=5); parser.add_argument("--out", type=Path, default=ROOT / "results" / "approach2" / "q4"); args = parser.parse_args(); set_seed(args.seed); started = time.perf_counter()
    nodes_meta = load_nodes(); node_order = sorted(row["node_code"] for row in nodes_meta); edges = load_edges(); history_validation_directed = annual_graph(edges, nodes_meta, 2021, args.top_k); target_validation_directed = annual_graph(edges, nodes_meta, 2022, args.top_k); history_test_directed = annual_graph(edges, nodes_meta, 2022, args.top_k); target_test_directed = annual_graph(edges, nodes_meta, 2023, args.top_k); history_validation = undirected_graph(history_validation_directed); history_test = undirected_graph(history_test_directed); validation_future = future_directed_split(history_validation_directed, target_validation_directed, np.random.default_rng(args.seed + 2022)); test_future = future_directed_split(history_test_directed, target_test_directed, np.random.default_rng(args.seed + 2023))
    dimensions = [int(value) for value in args.dimensions.split(",")]; p_values = [float(value) for value in args.p_values.split(",")]; q_values = [float(value) for value in args.q_values.split(",")]
    validation_sweep = {}; validation_rows = []
    for p in p_values:
        for q in q_values:
            for dimension in dimensions:
                key = f"p={p:g},q={q:g},d={dimension}"; result = fit_and_evaluate(history_validation, history_validation_directed, validation_future, node_order, p, q, dimension, args.seed + dimension + int(p * 100) + int(q * 1000), args); validation_sweep[key] = {"validation": result["learned"], "baselines": result["baselines"], "training": result["training"]}; validation_rows.append((result["learned"]["auc"], result["learned"]["average_precision"], p, q, dimension))
    selected = max(validation_rows, key=lambda item: (item[0], item[1])); selected_config = {"p": selected[2], "q": selected[3], "dimension": selected[4], "selection_rule": "maximum validation AUC, AP as tie-break; test metrics not inspected"}
    final = fit_and_evaluate(history_test, history_test_directed, test_future, node_order, selected[2], selected[3], selected[4], args.seed + 9000, args)
    contexts = walk_pairs(history_test, selected[2], selected[3], np.random.default_rng(args.seed + 9000), args.walks_per_node, args.walk_length, args.window); embeddings, _ = train_skipgram(contexts, node_order, selected[4], args.seed + 9000, args.epochs, args.negative_count); final["cluster_agreement"] = cluster_agreement(embeddings, history_test, nodes_meta, args.seed)
    ordered = sorted(validation_sweep.items(), key=lambda item: item[1]["validation"]["auc"], reverse=True); top = ordered[:12]
    figure = go.Figure([go.Bar(x=[key for key, _ in top], y=[item["validation"]["auc"] for _, item in top], name="validation AUC")]); figure.update_layout(title="Q4B validation sweep (selection only)", xaxis_title="Configuration", yaxis_title="Validation AUC")
    save_plot(figure, args.out / "validation_sweep.html", "q4b_validation_sweep")
    metrics = {"task": {"type": "future_directed_trade_edge_formation", "validation_target_year": 2022, "test_target_year": 2023, "candidate_negatives": "ordered pairs absent from history and target; equal to positives"}, "chronology": {"validation_history_year": 2021, "test_history_year": 2022, "test_is_untouched": True}, "split_manifest": {"validation": validation_future, "test": test_future}, "selected_configuration": selected_config, "validation_sweep": validation_sweep, "test": final, "leakage_audit": {"walk_graph_validation": "2021 annual graph only", "walk_graph_test": "2022 annual graph only", "baseline_graph_validation": "2021 annual graph only", "baseline_graph_test": "2022 annual graph only", "parameter_selection_metric": "validation_auc", "test_used_for_selection": False, "same_validation_pairs_for_all_configurations": True}}
    write_metrics(args.out / "metrics.json", {"seed": args.seed, "top_k": args.top_k, "dimensions": dimensions, "p_values": p_values, "q_values": q_values, "epochs": args.epochs}, metrics, time.perf_counter() - started, {"validation_top": [{"configuration": key, "auc": item["validation"]["auc"]} for key, item in top], "selected_configuration": selected_config})
    table = Table(title="Q4B future-edge prediction"); [table.add_column(column) for column in ["Stage", "Learned AUC", "CN", "AA", "PA"]]; table.add_row("Validation", f"{selected[0]:.3f}", "—", "—", "—"); table.add_row("2023 test", f"{final['learned']['auc']:.3f}", f"{final['baselines']['common_neighbors']['auc']:.3f}", f"{final['baselines']['adamic_adar']['auc']:.3f}", f"{final['baselines']['preferential_attachment']['auc']:.3f}"); Console().print(table)


if __name__ == "__main__": main()

