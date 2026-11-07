# Q4. China financial and trade networks

## Executive summary

This project studies a directed annual trade network induced by China and 20 partners selected from the 2023 China import-plus-export ranking. The committed snapshot covers 2014–2023 and contains 21 nodes and 4,160 positive reported export rows. Approach 1 is descriptive: it reports graph statistics, Kruskal minimum spanning forests, Louvain communities, PageRank, weighted degree, weighted betweenness, resolution sensitivity, and aligned community migration. Approach 2 is a future-edge task: the 2021 annual graph is used to select node2vec hyperparameters on 2022 edge formation, then the selected configuration is refit on the 2022 annual graph and evaluated once on 2023 edge formation.

The final configuration was selected by validation AUC only, with average precision as a tie-break. It was (p=0.5,q=1,d=16), with validation AUC 0.806 and AP 0.808. On the untouched 2023 test pairs, node2vec plus a learned bilinear scorer obtains AUC 0.592 and AP 0.614. The corresponding test AUCs are 0.469 for common neighbors, 0.487 for Adamic–Adar, and 0.408 for preferential attachment. The test score is therefore an independent acceptance result, rather than the largest number observed in the parameter sweep.

## Data and reproducibility

The data source is the keyless UN Comtrade preview API specified by the assignment. `data/fetch.py` has an offline default: `python data/fetch.py --seed 42` reads only the committed clean files, validates their SHA-256 checksums against `data/metadata.json`, checks the node count and year coverage, and rejects self-loops. Network retrieval is opt-in through `python data/fetch.py --refresh --seed 42`. This makes the first command in `README.md` work on a disconnected machine.

The edge definition is

\[
T_{ij,t}=\text{primaryValue}_{ij,t},
\]

where (T_{ij,t}) is the reported export value from reporter (i) to partner (j) in year (t), measured in USD. The node set is fixed across all years using the anchor-year (2023) China total import-plus-export ranking. For each reporter and year, the analysis graph retains the ten largest positive export edges. This rule is specified before the experiments and is applied identically to all years. The raw induced clean snapshot remains available for audit; top-(k) is an analysis construction rule, not a claim that smaller reported flows are zero.

The repository uses Python 3.13, `uv`, pinned dependencies, a committed `uv.lock`, and local ignored caches. All Plotly figures embed JavaScript and use deterministic div IDs. The canonical clean-clone command is:

```bash
export UV_CACHE_DIR="$PWD/.cache/uv"
uv sync --locked --python 3.13
uv run --locked python data/fetch.py --seed 42
uv run --locked python code/approach1_q4.py --seed 42 --top-k 10
uv run --locked python code/approach2_q4.py --seed 42 --top-k 10
uv run --locked python code/compare.py
```

## Approach 1: network analytics

For each year, the directed graph contains all 21 fixed nodes and the selected directed trade edges. The undirected projection sums reciprocal flows:

\[
W_{ij,t}=T_{ij,t}+T_{ji,t}.
\]

The graph statistics include directed and undirected edge counts and densities, mean undirected degree, a log–log degree-frequency slope, assortativity, connected components, isolated nodes, and self-loop counts. All statistics are reported without silently dropping isolated nodes.

For the Kruskal minimum spanning forest, positive trade weights are mapped to the distance

\[
d_{ij}=\frac{1}{\log(1+W_{ij})}.
\]

The code stores this distance explicitly and reports forest components, total distance, and the diameter of the largest connected component. Betweenness uses the same explicit `distance` attribute. Louvain maximizes weighted modularity,

\[
Q=\frac{1}{2m}\sum_{ij}\left(A_{ij}-\frac{k_i k_j}{2m}\right)\mathbf 1(c_i=c_j),
\]

with resolution values (0.5,1.0,1.5). PageRank uses damping (0.85). Because country nodes do not have stock-industry labels, region is reported only as a transparent proxy for community comparison; it is never described as ground-truth industry.

For consecutive years, communities are aligned with a maximum-overlap Hungarian assignment before the changed-share and contingency matrix are computed. This avoids the label-switching problem and the greedy many-to-one mapping in the earlier implementation.

### Descriptive results

| Year | Directed edges | Undirected edges | Components | Communities | Modularity | MST diameter |
|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 210 | 143 | 1 | 4 | 0.225 | 5 |
| 2021 | 210 | 147 | 1 | 4 | 0.181 | 6 |
| 2022 | 200 | 138 | 1 | 4 | 0.187 | 6 |
| 2023 | 200 | 139 | 1 | 3 | 0.194 | 6 |

All ten years and the complete resolution sweep are in `results/approach1/q4/metrics.json`. The self-loop audit reports zero self-loops. The annual evolution figure is `results/approach1/q4/network_evolution.html`.

## Approach 2: node2vec and future link prediction

### Chronological protocol

The prediction task is future **directed** edge formation. An ordered pair is positive in target year (t+1) if it is an annual top-(k) export edge in (t+1) and absent in the history year (t). A negative pair is absent from both the history and target graphs. The negative sample is equal in size to the positive sample and is fixed once per evaluation stage.

There are two chronological stages:

| Stage | Training graph for walks and baselines | Target year | Positive / negative pairs |
|---|---|---:|---:|
| Validation | 2021 annual graph only | 2022 | 14 / 14 |
| Final test | 2022 annual graph only | 2023 | 14 / 14 |

Every hyperparameter configuration sees the same validation pairs. The test pairs are never used by random walks, negative sampling, the bilinear scorer, baselines, or selection. After selection, exactly one final configuration is run on the 2023 target. The resulting `metrics.json` contains an explicit split manifest and a leakage audit.

### Embedding and scorer

For previous node (t), current node (v), and candidate next node (x), node2vec uses

\[
\alpha_{pq}(t,x)=
\begin{cases}
1/p,&x=t,\\
1,&(t,x)\in E,\\
1/q,&\text{otherwise}.
\end{cases}
\]

This transition factor is multiplied by the observed undirected training-graph weight. Walk contexts use window two. The PyTorch skip-gram objective is

\[
\log\sigma(z_v^\top c_u)+\sum_{r=1}^{5}\log\sigma(-z_v^\top c_{n_r}),
\]

with five uniformly sampled negative contexts. The directed future score is

\[
s(u,v)=\sigma(z_u^\top Wz_v),
\]

where (W) is fitted only on balanced reconstruction labels made from the relevant history graph. The test-year target is never passed into the training functions. Common-neighbor, Adamic–Adar, and preferential-attachment scores also receive only the annual history graph.

The validation sweep covers (p,q\in\{0.5,1,2\}) and dimensions ({8,16,32,64}), 36 configurations. The best validation configurations were:

| Configuration | Validation AUC | Validation AP |
|---|---:|---:|
| (p=0.5,q=1,d=16) | **0.806** | **0.808** |
| (p=2,q=2,d=64) | 0.786 | 0.740 |
| (p=0.5,q=2,d=64) | 0.786 | 0.724 |
| (p=0.5,q=2,d=16) | 0.781 | 0.763 |
| (p=1,q=2,d=8) | 0.776 | 0.821 |

The validation sweep figure is `results/approach2/q4/validation_sweep.html`.

### Untouched 2023 test

| Method | AUC | Average precision |
|---|---:|---:|
| Node2vec + bilinear scorer | **0.592** | **0.614** |
| Adamic–Adar | 0.487 | 0.477 |
| Common neighbors | 0.469 | 0.469 |
| Preferential attachment | 0.408 | 0.451 |

The learned score beats all three heuristics on this small final test. The gap is materially smaller than the validation score, which is exactly why the validation result is not presented as final performance. The comparison figure is `results/comparison.html`.

Embedding clusters are compared descriptively with final-history Louvain communities and the region proxy. For the selected configuration, ARI versus Louvain is 0.189 and NMI is 0.248; ARI versus the region proxy is -0.008 and NMI is 0.303. These are exploratory structure comparisons, not evidence that region is an industry ground truth.

## Leakage and offline audit

The four previously identified failures were addressed as follows:

1. **Test information entering training:** node2vec walks, reconstruction labels, bilinear fitting, and baselines are constructed from the 2021 graph for validation and the 2022 graph for test. The 2023 target appears only in the final evaluation function.
2. **Test set used for selection:** selection is maximum validation AUC with AP tie-break. The test configuration is fixed before test scoring, and the metrics record `test_used_for_selection: false`.
3. **SESSION integrity:** `SESSION.md` records the actual work chronology, prompts, tool commands, outputs, commits, and review corrections. It does not invent an approved-agent identity or claim a transcript that was not exported by that agent. If the instructor requires an exact OpenCode/OpenChamber export, the group must append the export generated by that approved session.
4. **Offline reproduction:** the README starts with `data/fetch.py` in verification mode. It reads committed files and metadata, checks hashes, and never calls the network unless `--refresh` is explicitly passed.

## Limitations

The Comtrade preview endpoint reports a selected induced network, not a reconciled world trade matrix. The top-ten rule improves the number of future changes available for evaluation but changes the task to formation of major reported relationships. The final test contains 14 positive and 14 negative directed pairs, so uncertainty is substantial; repeated target years or a larger partner universe would improve it. The embedding uses the undirected projection for walks while the target is directed, a deliberate compromise that should be tested against a directed embedding in future work. Region labels are descriptive proxies, not stock-industry labels. Finally, annual observations do not model within-year trade dynamics or causality.

## Division of work

The terminal workflow implemented the snapshot verifier, graph construction, leakage-safe chronological split, estimators, baselines, metrics, figures, and reproducibility commands. The group selected the trade network, reviewed the top-ten construction and chronological task, and remains responsible for checking the equations, interpreting results, adding group names and student IDs, and approving the final submission.

