# MQF Advanced Programming project contract

## Objective

Complete both Q4 approaches for an annual China-partner trade network. Approach 1 reports graph statistics, Kruskal minimum spanning trees, Louvain communities, centralities, resolution sensitivity, and temporal community migration. Approach 2 implements node2vec with PyTorch and evaluates future trade-edge formation using chronological train/validation/test targets. The group owns mathematical choices and interpretation; every model decision must be selected without looking at the final test year.

## Environment and commands

Use Python 3.13 and `uv`, with dependencies pinned in `pyproject.toml` and `uv.lock`. From the repository root:

```sh
export UV_CACHE_DIR="$PWD/.cache/uv"
uv sync --locked --python 3.13
uv run --locked python data/fetch.py --seed 42
uv run --locked python code/approach1_q4.py --seed 42 --top-k 6
uv run --locked python code/approach2_q4.py --seed 42 --top-k 6
uv run --locked python code/compare.py
```

The first data command is offline and verifies the committed snapshot. Network retrieval is explicit only with `python data/fetch.py --refresh`.

## Data and experiments

The committed snapshot covers 2014–2023 and records source, retrieval date, schema, and SHA-256 hashes in `data/metadata.json`. The default seed is 42. Approach 1 is descriptive by year. Approach 2 uses 2014–2021 history to select hyperparameters against 2022 validation formation, then refits the selected configuration on 2014–2022 history and evaluates once on 2023 formation. Random walks, graph features, negative samples, bilinear fitting, and heuristic baselines receive only their training-history graph. The test year is never used for training or parameter selection.

Each approach accepts `argparse` options and writes `results/approachN/q4/metrics.json` with `{params, metrics, fit_seconds, history}`. Plotly HTML figures embed JavaScript and use deterministic IDs. The comparison script reads all metrics files and writes `results/comparison.html`.

## Session and Git rules

All writes and caches stay inside the repository. Credentials never enter files. Destructive actions require explicit approval in the session. Validate clean data before analysis, preserve split manifests, and commit each completed milestone with conventional prefixes such as `data:`, `feat:`, `exp:`, and `report:`. The session record must preserve the actual prompts, responses, commands, decisions, and outputs; redact secrets without inventing another agent identity. Tag the reviewed final commit `submission`.
