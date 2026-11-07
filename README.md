# MQF Advanced Programming — Q4
This repository studies a China-partner annual trade network with classical analytics and leakage-safe node2vec future-edge prediction.
From the repository root, use Python 3.13 and run: `export UV_CACHE_DIR="$PWD/.cache/uv"; uv sync --locked --python 3.13 && uv run --locked python data/fetch.py --seed 42 && uv run --locked python code/approach1_q4.py --seed 42 --top-k 10 && uv run --locked python code/approach2_q4.py --seed 42 --top-k 10 && uv run --locked python code/compare.py`.
The first data command is offline and verifies committed snapshots; use `python data/fetch.py --refresh` only for an explicit network refresh.

