"""Subprocess entry for the spectrally seeded global-structure expert
(paper §3.1: "cheap direct or spectrally seeded runs that expose alternative
macro-structure quickly"). Pipeline: low-dim Laplacian embedding + balanced
K-means (spectral.py) -> repair into the window -> warm engine V-cycles.
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
    ap.add_argument("--eps", type=float, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--dims", type=int, default=3)
    ap.add_argument("--vcycles", type=int, default=2)
    a = ap.parse_args()

    pkg_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(pkg_root))
    from fastpart.hgr import read_hgr
    from fastpart.repair import repair
    from fastpart.spectral import kmeans_seed

    hg = read_hgr(a.hypergraph)
    labels = kmeans_seed(hg, a.k, a.eps, dims=a.dims, seed=a.seed)
    if labels is None:
        return 1
    labels = repair(hg, labels, a.k, a.eps)

    sys.path.insert(0, str(pkg_root / "external/mt-kahypar/build/python"))
    import mtkahypar
    mtk = mtkahypar.initialize(a.threads)
    mtkahypar.set_seed(a.seed)
    ctx = mtk.context_from_file(str(pkg_root / "presets/quality_direct.ini"))
    W = hg.total_weight
    U = int(math.floor((1.0 / a.k + a.eps / 100.0) * W + 1e-9))
    ctx.set_partitioning_parameters(a.k, a.k * a.eps / 100.0,
                                    mtkahypar.Objective.CUT)
    ctx.set_individual_target_block_weights([U] * a.k)
    ctx.logging = False
    ehg = mtk.hypergraph_from_file(a.hypergraph, ctx, mtkahypar.FileFormat.HMETIS)
    phg = ehg.create_partitioned_hypergraph(ctx, a.k, labels)
    phg.improve_partition(ctx, max(1, a.vcycles))
    Path(a.out).write_text(
        "\n".join(str(phg.block_id(v)) for v in range(ehg.num_nodes())) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
