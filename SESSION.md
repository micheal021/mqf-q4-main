# Q4 session record

This file is the actual repository-production record for the session recorded in this workspace. It is written in the Markdown style used by the reference repository. It includes the user directions, assistant decisions, commands, outputs, review corrections, and commit milestones that can be verified against Git. It is not an invented OpenCode/OpenChamber export; the actual approved-agent export must be appended by the group if the instructor requires that exact export format. Secrets and token material are omitted.

## Session metadata

- Date: 2026-11-07, Asia/Shanghai
- Repository: `mqf-q4-main`
- Remote: private GitHub repository under `micheal021`
- Default seed: `42`
- Python target: `3.13`
- Working root: `/Users/xzmini40/Desktop/smy-mqf/mqf-q4-main`
- Destructive operation: the user explicitly requested deletion of the newly created prior Q4 directory; its local directory was removed. GitHub deletion of that prior remote was blocked because the account token lacks the `delete_repo` scope; it was not used for this rebuild.

## Turn 1 — user direction

User asked to inspect the public Cassidy Q2 repository, redo Q4 according to the assignment, and prioritize four review findings: test edges entering training, selecting parameters on test AUC, an inadequate SESSION, and a broken offline reproduction path.

Assistant response: read the assignment specification and the existing Q4 repository; confirmed that the existing code used the full graph for walks and baselines, selected by test AUC, had a milestone summary rather than a complete session export, and called the network from the first README command.

Commands executed:

```text
sed -n '1,520p' /Users/xzmini40/Desktop/smy-mqf/report(1).md
git status --short --branch
git log --oneline --decorate -12
find . -maxdepth 4 -type f
rg -n 'fetch|offline|train|valid|test|AUC|SESSION|edge|negative'
```

The public Cassidy clone was attempted but the GitHub connection timed out. The local `mqf-q2-main` reference repository was then read directly. Its structure informed this repo's short README, `uv run --locked` command, metadata layout, and session format.

## Turn 2 — explicit reset request

User requested that the just-created Q4 work be deleted and rebuilt, while preserving `mqf-q2-main` as the Cassidy reference.

Actions:

```text
gh repo delete micheal021/ap26-q4-trade-network-final --yes
```

GitHub returned HTTP 403 because the current token lacks `delete_repo`. The user-owned local directory was removed with an explicit Python `shutil.rmtree` call. The old `ap26-q4-trade-network` repository and Cassidy's `mqf-q2-main` directory were preserved.

## Milestone 1 — new contract and remote

Created `mqf-q4-main/AGENTS.md` before adding code. The contract fixes the chronological protocol, offline-first fetch behavior, metrics schema, cache policy, and commit discipline.

Commands:

```text
git init -b main
git add AGENTS.md
git commit -m 'chore: add Q4 project contract'
gh repo create micheal021/mqf-q4-main --private
git remote add origin git@github.com-micheal021:micheal021/mqf-q4-main.git
git push -u origin main
```

Commit: `5424c1c chore: add Q4 project contract`.

## Milestone 2 — offline snapshot

Added `.gitignore`, `README.md`, `pyproject.toml`, `uv.lock`, `data/fetch.py`, `data/metadata.json`, and committed clean trade and node snapshots. `fetch.py` now verifies by default and only accesses Comtrade under `--refresh`. The verifier checks SHA-256, row count, CSV columns, year coverage, node count, and self-loops.

Observed offline verification:

```json
{"seed": 42, "offline": true, "years": [2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023], "nodes": 21, "flow_rows": 4160, "artifacts_verified": 2}
```

Commit: `8ccee23 data: add offline-first Comtrade snapshot and verifier`.

## Milestone 3 — implementation and first review

Implemented `code/common.py`, `code/approach1_q4.py`, and `code/approach2_q4.py`.

The first smoke test exposed two implementation issues:

1. A `code/__init__.py` package marker shadowed Python's standard-library `code` module while importing PyTorch. It was removed and committed as `2c75108 chore: remove stdlib-shadowing package marker`.
2. The cumulative history graph could contain fewer non-edges than observed edges. Training-only reconstruction labels now subsample observed positives to keep training labels balanced; this uses no future graph.

The first approach-2 design was then reviewed for methodological fairness. It was changed from an undirected cumulative-history target with configuration-specific negative samples to a directed annual future-edge task with fixed evaluation pairs. All configurations now see exactly the same validation pairs.

Commit: `ac409dc feat: implement leakage-safe Q4 analytics and future links`.

## Milestone 4 — fixed split and formal experiment

The validation and test pair manifests are generated once before the hyperparameter loop. The 36 configurations use the same 2022 validation pairs. The configuration is selected by validation AUC, AP as a tie-break; only then is the selected configuration evaluated on 2023.

The default top-k construction was set to 10 before the final run. With top-10 directed annual edges, both validation and test have 14 positive and 14 negative ordered pairs. The formal commands were:

```text
/Users/xzmini40/Desktop/ap26-q4-trade-network/.venv/bin/python code/approach1_q4.py --seed 42 --top-k 10
/Users/xzmini40/Desktop/ap26-q4-trade-network/.venv/bin/python code/approach2_q4.py --seed 42 --top-k 10 --dimensions 8,16,32,64 --p-values 0.5,1,2 --q-values 0.5,1,2 --epochs 5 --walks-per-node 8 --walk-length 20 --window 2 --negative-count 5
/Users/xzmini40/Desktop/ap26-q4-trade-network/.venv/bin/python code/compare.py
```

Formal output:

```text
Validation learned AUC: 0.806
2023 test learned AUC: 0.592
2023 test CN AUC: 0.469
2023 test AA AUC: 0.487
2023 test PA AUC: 0.408
```

The selected validation configuration is `p=0.5,q=1,d=16`. It was selected before reading the test metrics.

## Final verification checklist

- [x] `AGENTS.md` was committed before code.
- [x] `README.md` is concise and contains one clean-clone command.
- [x] `data/fetch.py` is offline by default; `--refresh` is explicit.
- [x] Metadata records source, date, schema, row counts, bytes, and SHA-256.
- [x] Q4A covers ten years and reports graph statistics, MST, Louvain, centrality, resolution, and migration.
- [x] Q4B uses 2021→2022 validation and 2022→2023 test chronology.
- [x] Walks, baselines, reconstruction scorer, and parameter choice do not use the test year.
- [x] Validation/test pairs are fixed before the hyperparameter sweep.
- [x] Metrics use `{params, metrics, fit_seconds, history}`.
- [x] Plotly files are self-contained and deterministic.
- [x] `compare.py` reads both metrics files and ranks only the untouched test results.
- [x] Multiple milestone commits are pushed to `origin/main`.
- [ ] Exact approved-agent session export: must be generated by the group from the approved OpenCode/OpenChamber session if required; this record does not fabricate that export.

