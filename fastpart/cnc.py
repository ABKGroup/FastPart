"""Consensus-and-Clean (paper §3.4, Algorithm 1).

Combine two or more strong candidates: keep the lowest-cut candidate as the
baseline, align the others to it by the best label permutation, score vertices
by aligned disagreement, propagate that score to 1-hop neighbors, and form a
capped border window from the highest-priority vertices. Solve a localized
balanced ILP over ONLY the border: every block contributes a pseudo-vertex
whose fixed weight equals the outside-of-border mass already assigned to it,
so global two-sided balance is preserved without a full-instance ILP. Adopt
the patch iff it is feasible and strictly lowers the cut; otherwise return the
better original candidate unchanged.
"""

from __future__ import annotations

from .evaluator import cut as full_cut
from .evaluator import window
from .hgr import Hypergraph


def align_labels(base: list[int], other: list[int], k: int,
                 weights: list[int]) -> list[int]:
    """Best label permutation of `other` onto `base` (greedy max-overlap;
    exact Hungarian is unnecessary at K <= 8)."""
    ov = [[0] * k for _ in range(k)]
    for v, b in enumerate(other):
        ov[b][base[v]] += weights[v]
    perm, used = [-1] * k, set()
    for b in sorted(range(k), key=lambda b: -max(ov[b])):
        tgt = max((a for a in range(k) if a not in used), key=lambda a: ov[b][a])
        perm[b] = tgt
        used.add(tgt)
    return [perm[x] for x in other]


def consensus_and_clean(hg: Hypergraph, candidates: list[list[int]], k: int,
                        eps_pct: float, border_cap: int = 4000,
                        ilp_time_s: float = 60.0, workers: int = 16):
    """Returns (labels, cut, patched: bool). candidates must all be feasible."""
    scored = sorted(((full_cut(hg, c), c) for c in candidates), key=lambda t: t[0])
    base_cut, base = scored[0]
    others = [align_labels(base, c, k, hg.vertex_weight) for _, c in scored[1:]]
    if not others:
        return base, base_cut, False

    # disagreement score + 1-hop propagation
    score = [0.0] * hg.n
    for other in others:
        for v in range(hg.n):
            if other[v] != base[v]:
                score[v] += 1.0
    adj_bump = [0.0] * hg.n
    for e, ps in enumerate(hg.pins):
        if len(ps) > 64:
            continue
        s = sum(score[v] for v in ps)
        if s > 0:
            bump = s / len(ps)
            for v in ps:
                adj_bump[v] += bump
    for v in range(hg.n):
        score[v] += 0.5 * adj_bump[v]

    order = sorted((v for v in range(hg.n) if score[v] > 0),
                   key=lambda v: -score[v])
    border = order[:border_cap]
    if not border:
        return base, base_cut, False
    in_border = set(border)

    # pseudo-vertex masses: fixed outside-of-border weight per block
    L, U = window(hg, k, eps_pct)
    outside = [0] * k
    for v in range(hg.n):
        if v not in in_border:
            outside[base[v]] += hg.vertex_weight[v]

    # localized ILP: choose block for each border vertex; nets touching the
    # border pay their weight if they span > 1 block (outside pins contribute
    # their fixed baseline blocks).
    try:
        import cplex
    except ImportError:
        return base, base_cut, False
    idx = {v: i for i, v in enumerate(border)}
    model = cplex.Cplex()
    model.set_log_stream(None)
    model.set_results_stream(None)
    model.set_warning_stream(None)
    model.parameters.timelimit.set(ilp_time_s)
    model.parameters.threads.set(workers)
    # CPLEX's wall limit is advisory during presolve on big models; the
    # deterministic limit is honored strictly (ticks ~ ms on this class)
    model.parameters.dettimelimit.set(ilp_time_s * 1000.0)
    model.objective.set_sense(model.objective.sense.minimize)

    xname = [[f"x{i}_{b}" for b in range(k)] for i in range(len(border))]
    for i in range(len(border)):
        model.variables.add(names=xname[i], types="B" * k, obj=[0.0] * k)
        model.linear_constraints.add(
            lin_expr=[cplex.SparsePair(xname[i], [1.0] * k)], senses="E", rhs=[1.0])
    # balance rows with pseudo-vertex offsets
    for b in range(k):
        names = [xname[idx[v]][b] for v in border]
        wts = [float(hg.vertex_weight[v]) for v in border]
        model.linear_constraints.add(
            lin_expr=[cplex.SparsePair(names, wts)], senses="L",
            rhs=[float(U - outside[b])])
        model.linear_constraints.add(
            lin_expr=[cplex.SparsePair(names, wts)], senses="G",
            rhs=[float(L - outside[b])])
    # cut terms for nets touching the border
    y_count = 0
    for e, ps in enumerate(hg.pins):
        touch = [v for v in ps if v in in_border]
        if not touch:
            continue
        fixed_blocks = {base[v] for v in ps if v not in in_border}
        if len(fixed_blocks) >= 2:
            continue                      # cut regardless of the border choice
        yn = f"y{y_count}"
        y_count += 1
        model.variables.add(names=[yn], types="B", obj=[float(hg.edge_weight[e])])
        blocks = set(range(k)) if not fixed_blocks else None
        for b in range(k):
            zn = f"z{yn}_{b}"
            present_fixed = 1.0 if b in fixed_blocks else 0.0
            if present_fixed:
                # block b certainly present; z_b = 1 handled via constant below
                continue
            model.variables.add(names=[zn], types="B", obj=[0.0])
            for v in touch:
                model.linear_constraints.add(
                    lin_expr=[cplex.SparsePair([zn, xname[idx[v]][b]], [1.0, -1.0])],
                    senses="G", rhs=[0.0])
        zvars = [f"z{yn}_{b}" for b in range(k) if b not in fixed_blocks]
        n_fixed = len(fixed_blocks)
        # sum z + n_fixed <= 1 + (k-1) * y   =>  net cut iff >1 block present
        model.linear_constraints.add(
            lin_expr=[cplex.SparsePair(zvars + [yn], [1.0] * len(zvars) + [-(k - 1.0)])],
            senses="L", rhs=[1.0 - n_fixed])
    # MIP start: the baseline assignment
    start_ind, start_val = [], []
    for v in border:
        for b in range(k):
            start_ind.append(xname[idx[v]][b])
            start_val.append(1.0 if b == base[v] else 0.0)
    try:
        model.MIP_starts.add(cplex.SparsePair(start_ind, start_val),
                             model.MIP_starts.effort_level.solve_MIP)
    except Exception:
        pass
    try:
        model.solve()
        vals = {v: max(range(k), key=lambda b: model.solution.get_values(
            xname[idx[v]][b])) for v in border}
    except Exception:
        return base, base_cut, False
    patched = list(base)
    for v, b in vals.items():
        patched[v] = b
    pcut = full_cut(hg, patched)
    from .evaluator import is_feasible
    if pcut < base_cut and is_feasible(hg, patched, k, eps_pct):
        return patched, pcut, True
    return base, base_cut, False
