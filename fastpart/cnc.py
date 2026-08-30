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


def available_backends() -> list[str]:
    # broad except: a broken install (missing native lib, ABI mismatch) must
    # degrade to "backend unavailable", never take the controller down
    out = []
    try:
        import cplex  # noqa: F401
        out.append("cplex")
    except Exception:  # noqa: BLE001
        pass
    try:
        from ortools.sat.python import cp_model  # noqa: F401
        out.append("ortools")
    except Exception:  # noqa: BLE001
        pass
    return out


def resolve_backend(backend: str) -> str:
    """The backend `auto`/`cplex`/`ortools` resolves to on this machine ("" = none)."""
    have = available_backends()
    if backend == "auto":
        return "cplex" if "cplex" in have else ("ortools" if "ortools" in have else "")
    return backend if backend in have else ""


def _solve(model: dict, backend: str, ilp_time_s: float, workers: int):
    """Dispatch the localized border ILP. Returns {vertex: block} or None.
    workers <= 0 means all cores (same semantics for both backends). Under
    `auto`, a CPLEX failure at solve time (e.g. the Community Edition's model
    size cap, or a license error) falls back to CP-SAT when it is installed."""
    import os
    if workers <= 0:
        workers = os.cpu_count() or 1
    requested = backend
    backend = resolve_backend(backend)
    if not backend:
        return None
    try:
        if backend == "cplex":
            return _solve_cplex(model, ilp_time_s, workers)
        return _solve_cpsat(model, ilp_time_s, workers)
    except Exception:  # noqa: BLE001
        if requested == "auto" and backend == "cplex" and "ortools" in available_backends():
            try:
                return _solve_cpsat(model, ilp_time_s, workers)
            except Exception:  # noqa: BLE001
                return None
        return None


def _solve_cplex(m: dict, ilp_time_s: float, workers: int):
    import cplex
    border, idx, k, base = m["border"], m["idx"], m["k"], m["base"]
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

    # Everything is batched into one variables.add and one linear_constraints.add:
    # per-row calls cost more than the solve itself on a 4000-vertex window
    # (~80k API round-trips), which is what used to overrun the time budget.
    xname = [[f"x{i}_{b}" for b in range(k)] for i in range(len(border))]
    names, types, obj = [], [], []
    for i in range(len(border)):
        names.extend(xname[i])
        types.append("B" * k)
        obj.extend([0.0] * k)
    rows, senses, rhs = [], [], []
    for i in range(len(border)):
        rows.append(cplex.SparsePair(xname[i], [1.0] * k))
        senses.append("E")
        rhs.append(1.0)
    # balance rows with pseudo-vertex offsets
    wts = [float(m["weights"][v]) for v in border]
    for b in range(k):
        bn = [xname[idx[v]][b] for v in border]
        rows.append(cplex.SparsePair(bn, wts))
        senses.append("L")
        rhs.append(float(m["U"] - m["outside"][b]))
        rows.append(cplex.SparsePair(bn, wts))
        senses.append("G")
        rhs.append(float(m["L"] - m["outside"][b]))
    # cut terms for nets touching the border
    for j, (w_e, touch, fixed_blocks) in enumerate(m["nets"]):
        yn = f"y{j}"
        names.append(yn)
        types.append("B")
        obj.append(float(w_e))
        zvars = []
        for b in range(k):
            if b in fixed_blocks:
                continue                  # block b certainly present: constant below
            zn = f"z{j}_{b}"
            zvars.append(zn)
            names.append(zn)
            types.append("B")
            obj.append(0.0)
            for v in touch:
                rows.append(cplex.SparsePair([zn, xname[idx[v]][b]], [1.0, -1.0]))
                senses.append("G")
                rhs.append(0.0)
        # sum z + n_fixed <= 1 + (k-1) * y  =>  net cut iff > 1 block present
        rows.append(cplex.SparsePair(zvars + [yn], [1.0] * len(zvars) + [-(k - 1.0)]))
        senses.append("L")
        rhs.append(1.0 - len(fixed_blocks))
    model.variables.add(names=names, types="".join(types), obj=obj)
    model.linear_constraints.add(lin_expr=rows, senses="".join(senses), rhs=rhs)
    # MIP start: the baseline assignment
    start_ind, start_val = [], []
    for v in border:
        for b in range(k):
            start_ind.append(xname[idx[v]][b])
            start_val.append(1.0 if b == base[v] else 0.0)
    try:
        model.MIP_starts.add(cplex.SparsePair(start_ind, start_val),
                             model.MIP_starts.effort_level.solve_MIP)
    except Exception:  # noqa: BLE001
        pass
    model.solve()
    return {v: max(range(k), key=lambda b: model.solution.get_values(xname[idx[v]][b]))
            for v in border}


def _solve_cpsat(m: dict, ilp_time_s: float, workers: int):
    """Same model on OR-Tools CP-SAT (integer weights; hint = baseline)."""
    from ortools.sat.python import cp_model
    border, idx, k, base = m["border"], m["idx"], m["k"], m["base"]
    md = cp_model.CpModel()
    x = [[md.NewBoolVar(f"x{i}_{b}") for b in range(k)] for i in range(len(border))]
    for i in range(len(border)):
        md.AddExactlyOne(x[i])
    for b in range(k):
        load = sum(int(m["weights"][v]) * x[idx[v]][b] for v in border)
        md.AddLinearConstraint(load, int(m["L"] - m["outside"][b]),
                               int(m["U"] - m["outside"][b]))
    obj = []
    for j, (w_e, touch, fixed_blocks) in enumerate(m["nets"]):
        y = md.NewBoolVar(f"y{j}")
        obj.append(int(w_e) * y)
        zs = []
        for b in range(k):
            if b in fixed_blocks:
                continue
            z = md.NewBoolVar(f"z{j}_{b}")
            zs.append(z)
            for v in touch:
                md.AddImplication(x[idx[v]][b], z)      # z >= x
        md.Add(sum(zs) + len(fixed_blocks) <= 1 + (k - 1) * y)
    md.Minimize(sum(obj))
    for v in border:
        for b in range(k):
            md.AddHint(x[idx[v]][b], 1 if b == base[v] else 0)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(ilp_time_s)
    solver.parameters.num_workers = int(max(1, workers))
    st = solver.Solve(md)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {v: max(range(k), key=lambda b: solver.Value(x[idx[v]][b])) for v in border}


def consensus_and_clean(hg: Hypergraph, candidates: list[list[int]], k: int,
                        eps_pct: float, border_cap: int = 4000,
                        ilp_time_s: float = 60.0, workers: int = 16,
                        backend: str = "auto"):
    """Returns (labels, cut, patched: bool). candidates must all be feasible.
    backend: "auto" (CPLEX if importable, else OR-Tools CP-SAT, else skip),
    "cplex", or "ortools"."""
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
    # their fixed baseline blocks). Backend-agnostic model description first.
    idx = {v: i for i, v in enumerate(border)}
    nets = []                         # (edge_weight, touching border vertices, fixed_blocks)
    for e, ps in enumerate(hg.pins):
        touch = [v for v in ps if v in in_border]
        if not touch:
            continue
        fixed_blocks = {base[v] for v in ps if v not in in_border}
        if len(fixed_blocks) >= 2:
            continue                      # cut regardless of the border choice
        nets.append((hg.edge_weight[e], touch, fixed_blocks))
    model = dict(border=border, idx=idx, k=k, L=L, U=U, outside=outside,
                 nets=nets, base=base, weights=hg.vertex_weight)
    vals = _solve(model, backend, ilp_time_s, workers)
    if vals is None:
        return base, base_cut, False
    patched = list(base)
    for v, b in vals.items():
        patched[v] = b
    pcut = full_cut(hg, patched)
    from .evaluator import is_feasible
    if pcut < base_cut and is_feasible(hg, patched, k, eps_pct):
        return patched, pcut, True
    return base, base_cut, False
