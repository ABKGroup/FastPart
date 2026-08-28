"""Subprocess entry point for one modern Mt-KaHyPar expert run.

Each expert runs in its own process with its own TBB arena (thread count set
at initialize), so the FastPart controller can run several experts in
parallel without arena contention. Two-sided handling: the engine natively
enforces only UPPER block bounds, so we pass individual target block weights
equal to the evaluator's integer U = floor((1/K + eps)W); the lower side is
the caller's job (repair + AL-FM + the feasibility gate on the pool).

Modes: cold partition, or warm improvement of a given labeling (V-cycles).
Writes one label per line to --out.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("hypergraph")
    ap.add_argument("--out", required=True)
    ap.add_argument("-k", type=int, required=True)
    ap.add_argument("--eps", type=float, required=True, help="absolute pct")
    ap.add_argument("--preset", default="QUALITY")
    ap.add_argument("--config", default=None,
                    help="ini file overriding --preset (sets mode etc.)")
    ap.add_argument("--eps-scale", type=float, default=1.0,
                    help="shrink the engine-relative eps by this factor "
                         "(1/(k-1) makes two-sided feasibility automatic)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--vcycles", type=int, default=0)
    ap.add_argument("--warm", default=None, help="labels file to improve instead of cold start")
    ap.add_argument("--relax", type=float, default=1.0,
                    help="multiply the upper slack by this (relaxed exploration)")
    ap.add_argument("--engine-python", default=None,
                    help="dir containing the built mtkahypar python module")
    a = ap.parse_args()

    eng_dir = a.engine_python or str(Path(__file__).resolve().parent.parent
                                     / "external/mt-kahypar/build/python")
    sys.path.insert(0, eng_dir)
    import mtkahypar

    mtk = mtkahypar.initialize(a.threads)
    mtkahypar.set_seed(a.seed)
    if a.config:
        ctx = mtk.context_from_file(a.config)
    else:
        ctx = mtk.context_from_preset(getattr(mtkahypar.PresetType, a.preset))
    hg = mtk.hypergraph_from_file(a.hypergraph, ctx, mtkahypar.FileFormat.HMETIS)
    W = hg.total_weight()
    slack = (a.eps / 100.0) * a.relax
    U = int(math.floor((1.0 / a.k + slack) * W + 1e-9))
    eps_rel = a.k * slack * a.eps_scale
    ctx.set_partitioning_parameters(a.k, eps_rel, mtkahypar.Objective.CUT)
    scaled_U = min(U, int(math.floor((1.0 + eps_rel) * W / a.k + 1e-9)))
    ctx.set_individual_target_block_weights([scaled_U] * a.k)
    ctx.logging = False
    if a.warm:
        labels = [int(x) for x in open(a.warm).read().split()]
        phg = hg.create_partitioned_hypergraph(ctx, a.k, labels)
        phg.improve_partition(ctx, max(1, a.vcycles))
    else:
        if a.vcycles:
            ctx.num_vcycles = a.vcycles
        phg = hg.partition(ctx)
    out = [phg.block_id(v) for v in range(hg.num_nodes())]
    Path(a.out).write_text("\n".join(map(str, out)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
