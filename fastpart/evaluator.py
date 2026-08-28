"""Golden evaluator: cut-net objective under two-sided absolute balance.

Balance (paper Eq. 2): for every block i,
    (1/K - eps) * W  <=  w_i  <=  (1/K + eps) * W
with integer windows L = ceil((1/K - eps) W), U = floor((1/K + eps) W).
This module is the only authority on legality and reported cut values.
"""

from __future__ import annotations

import math

from .hgr import Hypergraph


def window(hg: Hypergraph, k: int, eps_pct: float) -> tuple[int, int]:
    W = hg.total_weight
    L = int(math.ceil((1.0 / k - eps_pct / 100.0) * W - 1e-9))
    U = int(math.floor((1.0 / k + eps_pct / 100.0) * W + 1e-9))
    return L, U


def block_weights(hg: Hypergraph, labels: list[int], k: int) -> list[int]:
    w = [0] * k
    for v, b in enumerate(labels):
        w[b] += hg.vertex_weight[v]
    return w


def cut(hg: Hypergraph, labels: list[int]) -> int:
    total = 0
    for e, ps in enumerate(hg.pins):
        first = labels[ps[0]]
        for v in ps[1:]:
            if labels[v] != first:
                total += hg.edge_weight[e]
                break
    return total


def is_feasible(hg: Hypergraph, labels: list[int], k: int, eps_pct: float) -> bool:
    L, U = window(hg, k, eps_pct)
    return all(L <= w <= U for w in block_weights(hg, labels, k))


def evaluate(hg: Hypergraph, labels: list[int], k: int, eps_pct: float):
    """Returns (cut, block_weights, feasible)."""
    if len(labels) != hg.n or min(labels) < 0 or max(labels) >= k:
        raise ValueError("labels malformed")
    w = block_weights(hg, labels, k)
    L, U = window(hg, k, eps_pct)
    return cut(hg, labels), w, all(L <= x <= U for x in w)
