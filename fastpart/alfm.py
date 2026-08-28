"""AL-FM: Augmented-Lagrangian FM refinement (paper §3.3).

Hard-feasibility FM rejects any move that temporarily violates balance. AL-FM
replaces that wall with the AL objective

    L(S, lam, rho) = cut(S) + sum_i lam_i * v(V_i) + (rho/2) * sum_i v(V_i)^2

where v(V_i) = max(0, w_i - U, L - w_i) is the two-sided violation magnitude
of block i (unit weight dimension here). Moves are scored by the exact change
Delta L (Eq. 6): only the two incident blocks change, so bookkeeping is local.
After each pass, dual ascent   lam_i <- max(0, lam_i + rho * v(V_i))   raises
the price of persistent violations; rho rises when violations persist or QoR
stalls and decays after a feasible streak. Each pass alternates exploratory
AL-scored moves with a repair step back to feasibility, and AL state is local
to the candidate (deterministic under a fixed policy).
"""

from __future__ import annotations

import random

from .evaluator import window
from .hgr import Hypergraph
from .repair import incidence, repair


def _violation(w: int, L: int, U: int) -> int:
    return max(0, w - U, L - w)


class ALFM:
    # Dual/penalty schedule calibrated to the original KEP refiner
    # (rho in [0.05, 4.0], x1.7 growth on violation/stall, /1.3 decay after a
    # 3-pass zero-violation streak, multiplier decay x0.9 while feasible).
    RHO_MIN, RHO_MAX = 0.05, 4.0
    RHO_GROWTH, RHO_DECAY = 1.7, 1.3
    LAMBDA_DECAY = 0.9
    ZERO_STREAK_TARGET = 3

    def __init__(self, hg: Hypergraph, labels: list[int], k: int, eps_pct: float,
                 rho0: float = 0.1, seed: int = 0,
                 inc: list[list[int]] | None = None):
        self.hg = hg
        self.k = k
        self.L, self.U = window(hg, k, eps_pct)
        self.eps_pct = eps_pct
        self.labels = labels
        self.rng = random.Random(seed)
        self.inc = inc if inc is not None else incidence(hg)
        self.pin = [[0] * k for _ in range(hg.m)]
        for e, ps in enumerate(hg.pins):
            for v in ps:
                self.pin[e][labels[v]] += 1
        self.w = [0] * k
        for v, b in enumerate(labels):
            self.w[b] += hg.vertex_weight[v]
        self.lam = [0.0] * k
        self.rho = rho0
        self.feasible_streak = 0
        self.prev_cut = None

    # -- objective pieces ------------------------------------------------------
    def _cut_gain(self, v: int, a: int, b: int) -> int:
        g = 0
        for e in self.inc[v]:
            c = self.pin[e]
            spans = sum(1 for x in c if x > 0)
            after = spans - (1 if c[a] == 1 else 0) + (1 if c[b] == 0 else 0)
            g += self.hg.edge_weight[e] * ((1 if spans > 1 else 0)
                                           - (1 if after > 1 else 0))
        return g

    def _al_penalty(self, block: int, w: int) -> float:
        v = _violation(w, self.L, self.U)
        return self.lam[block] * v + 0.5 * self.rho * v * v

    def _delta_L(self, v: int, a: int, b: int) -> float:
        """Change in the AL objective for moving v: a -> b (Eq. 6). Negative is
        an improvement (we minimize L)."""
        wv = self.hg.vertex_weight[v]
        d_pen = (self._al_penalty(a, self.w[a] - wv) + self._al_penalty(b, self.w[b] + wv)
                 - self._al_penalty(a, self.w[a]) - self._al_penalty(b, self.w[b]))
        return -self._cut_gain(v, a, b) + d_pen

    def _apply(self, v: int, b: int) -> None:
        a = self.labels[v]
        for e in self.inc[v]:
            self.pin[e][a] -= 1
            self.pin[e][b] += 1
        self.w[a] -= self.hg.vertex_weight[v]
        self.w[b] += self.hg.vertex_weight[v]
        self.labels[v] = b

    def _boundary(self) -> list[int]:
        out = set()
        for e, c in enumerate(self.pin):
            if sum(1 for x in c if x > 0) > 1:
                out.update(self.hg.pins[e])
        return list(out)

    # -- one exploratory pass + dual update -----------------------------------
    def run_pass(self, exploration_box: float = 0.0) -> int:
        """One AL-scored FM sweep over the boundary. `exploration_box` widens
        the hard drift limit (fraction of window width a block may leave the
        window during the pass; the AL price still applies inside it)."""
        span = self.U - self.L
        drift = int(exploration_box * span)
        moved = 0
        order = self._boundary()
        self.rng.shuffle(order)
        for v in order:
            a = self.labels[v]
            best_b, best_d = -1, -1e-12
            wv = self.hg.vertex_weight[v]
            for b in range(self.k):
                if b == a:
                    continue
                # hard drift limit: never move outside [L-drift, U+drift]
                if self.w[b] + wv > self.U + drift or self.w[a] - wv < self.L - drift:
                    continue
                d = self._delta_L(v, a, b)
                if d < best_d:
                    best_b, best_d = b, d
            if best_b >= 0:
                self._apply(v, best_b)
                moved += 1
        # dual ascent (Eq. 7) + adaptive rho
        viol = [_violation(self.w[i], self.L, self.U) for i in range(self.k)]
        for i in range(self.k):
            self.lam[i] = max(0.0, self.lam[i] + self.rho * viol[i])
        from .evaluator import cut as _cut
        cur = _cut(self.hg, self.labels)
        stalled = self.prev_cut is not None and cur >= self.prev_cut
        self.prev_cut = cur
        if max(viol) > 0 or stalled:
            self.rho = min(self.rho * self.RHO_GROWTH, self.RHO_MAX)
            self.feasible_streak = 0
        else:
            for i in range(self.k):
                self.lam[i] *= self.LAMBDA_DECAY
            self.feasible_streak += 1
            if self.feasible_streak >= self.ZERO_STREAK_TARGET:
                self.rho = max(self.rho / self.RHO_DECAY, self.RHO_MIN)
                self.feasible_streak = 0
        return moved

    def refine(self, passes: int = 8, exploration_box: float = 0.25,
               deadline: float | None = None) -> list[int]:
        """Alternate exploratory AL passes (shrinking drift box) with repair,
        per the spec: 'each pass alternates between exploratory FM moves under
        the AL objective and a repair step that brings the candidate back to
        feasibility'."""
        import time as _time
        for p in range(passes):
            if deadline is not None and _time.time() > deadline:
                break
            box = exploration_box * max(0.0, 1.0 - p / max(1, passes - 1))
            moved = self.run_pass(exploration_box=box)
            if _violation(max(self.w), self.L, self.U) or _violation(min(self.w), self.L, self.U):
                repair(self.hg, self.labels, self.k, self.eps_pct, inc=self.inc)
                # rebuild pin/w after repair mutated labels in place
                self.pin = [[0] * self.k for _ in range(self.hg.m)]
                for e, ps in enumerate(self.hg.pins):
                    for v in ps:
                        self.pin[e][self.labels[v]] += 1
                self.w = [0] * self.k
                for v, b in enumerate(self.labels):
                    self.w[b] += self.hg.vertex_weight[v]
            if moved == 0:
                break
        repair(self.hg, self.labels, self.k, self.eps_pct, inc=self.inc)
        return self.labels
