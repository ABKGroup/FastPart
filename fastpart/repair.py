"""Balance repair: drive a labeling into the two-sided window [L, U].

The spec's small-K path "repairs balance at the end of each pass"; repair is a
correctness step, not a quality step (the surrounding refinement owns quality).
Strategy: while some block is over U or under L, bulk-move the cheapest
boundary vertices (by exact cut gain) from the heaviest offender toward the
lightest, falling back to interior vertices when the boundary is exhausted.
"""

from __future__ import annotations

from .evaluator import window
from .hgr import Hypergraph


def incidence(hg: Hypergraph) -> list[list[int]]:
    inc: list[list[int]] = [[] for _ in range(hg.n)]
    for e, ps in enumerate(hg.pins):
        for v in ps:
            inc[v].append(e)
    return inc


def repair(hg: Hypergraph, labels: list[int], k: int, eps_pct: float,
           inc: list[list[int]] | None = None, max_rounds: int | None = None) -> list[int]:
    L, U = window(hg, k, eps_pct)
    w = [0] * k
    for v, b in enumerate(labels):
        w[b] += hg.vertex_weight[v]
    if all(L <= x <= U for x in w):
        return labels
    if inc is None:
        inc = incidence(hg)
    pin = [[0] * k for _ in range(hg.m)]
    for e, ps in enumerate(hg.pins):
        for v in ps:
            pin[e][labels[v]] += 1

    def gain(v: int, a: int, b: int) -> int:
        g = 0
        for e in inc[v]:
            c = pin[e]
            spans = sum(1 for x in c if x > 0)
            after = spans - (1 if c[a] == 1 else 0) + (1 if c[b] == 0 else 0)
            g += hg.edge_weight[e] * ((1 if spans > 1 else 0) - (1 if after > 1 else 0))
        return g

    def apply(v: int, b: int) -> None:
        a = labels[v]
        for e in inc[v]:
            pin[e][a] -= 1
            pin[e][b] += 1
        w[a] -= hg.vertex_weight[v]
        w[b] += hg.vertex_weight[v]
        labels[v] = b

    rounds = max_rounds if max_rounds is not None else 6 * k
    for _ in range(rounds):
        if max(w) <= U and min(w) >= L:
            break
        over = max(range(k), key=lambda b: w[b])
        under = min(range(k), key=lambda b: w[b])
        need = max(w[over] - U, L - w[under], 1)
        boundary = set()
        for e, c in enumerate(pin):
            if sum(1 for x in c if x > 0) > 1:
                for v in hg.pins[e]:
                    if labels[v] == over:
                        boundary.add(v)
        cand = sorted(boundary, key=lambda v: -gain(v, over, under))
        if not cand:
            cand = [v for v in range(hg.n) if labels[v] == over]
        moved = 0
        for v in cand:
            if moved >= need:
                break
            apply(v, under)
            moved += hg.vertex_weight[v]
    return labels
