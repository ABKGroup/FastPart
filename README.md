# FastPart — shipped source

The FastPart hypergraph partitioner: a fixed-budget portfolio controller over
a pinned, unpatched upstream Mt-KaHyPar, with optional refinement stages.

## Build and run

```bash
bash scripts/setup_mtkahypar.sh          # clones + builds the pinned engine (6271a58) with its Python module
python3 -m fastpart.cli design.hgr K --eps 2 --time 300          # default mode
python3 -m fastpart.cli design.hgr K --eps 2 --time 600 --kep    # with refinement stages
```

`--eps` is the absolute two-sided imbalance in percent (K=4, ε=2 → every block
holds 23–27 % of the total weight). All vCPUs are used by default
(`--threads N` to limit). Requires Python 3.10+, numpy, scipy. The CPLEX Python
API is optional: without it the recombination stage returns the better
original candidate.

## Modes and budgets

| Mode | What runs | Suggested `--time` |
|---|---|---|
| default | the portfolio controller: engine templates, warm follow-ons, feasible-only pool | 300 s |
| `--kep` | the controller plus the AL-FM and Consensus-and-Clean refinement stages in the tail | **600 s** (≈2× default) |

The refinement stages need room to work: at the default budget they often only
reproduce the controller's incumbent, while at roughly twice the budget they
have produced the best result on some cells. Use the default mode for
budget-bound runs and `--kep` when quality per instance matters more than
wall-clock.

## Results

Titan23, ε = 2 %, K = 2/3/4, default mode, 300 s runs on 112 vCPUs, a median
of 3 seeds per cell, against the published FastPart table (best of 20 seeds):
52 of 66 cells at or below the published cut, geometric-mean ratio 1.0027.
Every cut is re-scored from the written partition by the independent
evaluator (cut-net objective, two-sided absolute balance).

## Layout

    fastpart/controller.py     roster, scheduler, pool, three stages
    fastpart/engine_runner.py  one engine run per subprocess
    fastpart/spectral*.py      spectral-seed template
    fastpart/cnc.py            recombination stage
    fastpart/alfm.py           AL-FM refinement stage
    fastpart/repair.py, evaluator.py, hgr.py
    presets/                   engine presets (stock upstream + mode/rebalancer variants)
    scripts/setup_mtkahypar.sh pinned upstream engine build
