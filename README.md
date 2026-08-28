# FastPart v0 — the optimal Mt-KaHyPar controller (KEP-free)

This branch is the **KEP-free FastPart**: the fixed-budget portfolio controller
of the ICCAD paper (§3.1), rebuilt from the paper's description on top of an
**unpatched, pinned upstream Mt-KaHyPar**. It answers a simple question
honestly: how much of FastPart's published quality is the controller plus a
well-tuned engine, before any bespoke expert is added?

**1,122 lines of Python. Zero engine patches. 30 edited lines across stock
preset files.** Everything the engine does, it does with its own upstream
code.

## What is in the controller

Paper §3.1, clause by clause:

| Paper | Here |
|---|---|
| Global-structure experts: "cheap direct or spectrally seeded runs" | a roster of stock engine templates — preset (`default`/`quality`/`highest_quality`/`deterministic_quality`) × mode (`direct`/`rb`/`deep`) × thread slice × ε-variant × V-cycles — plus one lightweight spectral-seed template (Laplacian embedding + balanced K-means, then engine V-cycles) |
| Short follow-on experts | warm-start V-cycle refinement of the pool incumbents |
| Exploration / intensification / recombination | the three stages, ~50/30/20 of the budget |
| Public pool 𝒫 (feasible only) + repair queue ℛ | the golden evaluator gates every admit; one relaxed probe per run enters ℛ and is repaired or dropped |
| Provenance-aware downselection | best per family first, then round-robin by cut rank |
| Deterministic execution policy | fixed roster, seeds, budget slices per (H, K, ε, T, threads) |
| Recombination stage | Consensus-and-Clean (paper §3.4, Algorithm 1): localized border-window ILP with pseudo-vertices; **CPLEX optional** — without it the stage returns the better original candidate, exactly as the paper specifies |

The KEP expert (§3.2) is deliberately absent. A three-pass AL-FM touch (§3.3)
runs on the incumbent in the tail as a small refinement; on the benchmark
board it has never produced the winning candidate.

Two-sided balance (paper Eq. 2) is enforced without any engine patch: the
engine receives exact per-block integer ceilings through its stock
`set_individual_target_block_weights` API; a K≥3 template shrinks the engine's
relative ε to ε/(K−1) so its upper bound alone implies the lower bound; the
lower bound is otherwise restored by a cut-aware repair, and the evaluator is
the only authority on legality.

## Build and run

```bash
bash scripts/setup_mtkahypar.sh          # clones + builds pinned upstream engine
python3 -m fastpart.cli design.hgr 4 --eps 2 --time 300
```

`--eps` is the absolute two-sided imbalance in percent (K=4, ε=2 → every block
holds 23–27 % of the weight). Uses all vCPUs by default (`--threads N` to
limit). Requires Python 3.10+, numpy, scipy; CPLEX Python API optional.

## Results — Titan23, ε = 2 %, K = 2/3/4, against the published FastPart table

One 300 s run per seed on 112 vCPUs, 3 seeds per cell (median; the published
table is best-of-20). Cut-net objective, two-sided absolute balance, every cut
re-scored from the written partition by the independent evaluator.

| | at/below published | above | geomean cut / published |
|---|---:|---:|---:|
| **66 cells** | **52** | **14** | **1.0027** |

Of the 14 above, 9 are within 2.4 % (best-of-20 territory: 1–7 cuts on
SLAM_spheric, mes_noc, bitonic_mesh, LU_Network, bitcoin_miner, des90,
stereo_vision at K=4). Three are structural — `directrf` K=2 (630 vs 490),
`openCV` K=4, `stap_qrd` K=3 — and are the cells the paper's KEP expert exists
for. A single 5-minute run of this controller lands, on average, within 0.3 %
of a table that was assembled from 20 seeds per cell.

## Layout

    fastpart/controller.py     roster, scheduler, pool, three stages
    fastpart/engine_runner.py  one engine run per subprocess (own TBB arena)
    fastpart/spectral*.py      spectral-seed template
    fastpart/cnc.py            recombination (Algorithm 1)
    fastpart/alfm.py           AL-FM tail touch (Eqs. 5–7)
    fastpart/repair.py, evaluator.py, hgr.py
    presets/                   stock upstream presets, mode/rebalancer variants
    scripts/setup_mtkahypar.sh pinned upstream build (6271a58, Feb 2026)
