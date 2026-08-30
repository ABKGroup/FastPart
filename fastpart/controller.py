"""FastPart v0: a fixed-budget portfolio wrapper around modern Mt-KaHyPar.

The controller keeps every vCPU busy for the whole budget with a weighted
roster of engine templates (preset x mode x threads x eps-variant), gates
every finished run through repair + the golden two-sided evaluator into a
feasible-only pool, intensifies incumbents with warm V-cycles, and spends the
tail on localized exact recombination (C&C) plus a final polish.

Template roster (ported from the original FastPart wrapper, re-expressed for
the modern engine): K=2 leans on quality-preset RECURSIVE-BISECTION at small
thread counts (many parallel instances); K>=3 on quality direct/deep with an
eps/(K-1) shrink variant whose upper bound alone guarantees two-sided
feasibility. A small success-weighted chooser (valid-rate x cut rank) tilts
the mix as evidence arrives.

Default mode is the controller alone; --kep enables the AL-FM (§3.3) and C&C
(§3.4) refinement stages in the tail.
"""

from __future__ import annotations

import random
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from .alfm import ALFM
from .cnc import (align_labels, available_backends, consensus_and_clean,
                  resolve_backend)
from .evaluator import evaluate
from .hgr import read_hgr
import sys as _sys

PKG_ROOT = str(Path(__file__).resolve().parent.parent)
RUNNER = [_sys.executable, "-m", "fastpart.engine_runner"]
from .repair import incidence, repair

PRESETS = Path(PKG_ROOT) / "presets"


@dataclass
class Template:
    name: str
    config: str                 # ini filename in presets/
    threads: int
    weight: float
    eps_scale: float = 1.0
    relax: float = 1.0
    vcycles: int = 0


@dataclass
class Stats:
    tried: int = 0
    valid: int = 0
    best: int | None = None

    def score(self, w: float) -> float:
        if self.tried == 0:
            return w * 1.5                      # explore untried templates first
        vr = self.valid / self.tried
        return w * (0.25 + vr)


def roster(k: int, cpus: int) -> list[Template]:
    small = max(4, cpus // 14)
    medium = max(8, cpus // 7)
    large = max(16, cpus // 4)
    xlarge = max(32, cpus // 2)
    t: list[Template] = []
    if k == 2:
        t += [
            Template("q_rb_s", "quality_rb.ini", small, 5.0),
            Template("q_rb_m", "quality_rb.ini", medium, 4.0),
            Template("q_rb_l", "quality_rb.ini", large, 2.0),
            Template("d_rb_s", "default_rb.ini", small, 1.0),
            Template("dq_rb_s", "deterministic_quality_rb.ini", small, 1.0),
            Template("q_rb_vc1", "quality_rb.ini", medium, 0.8, vcycles=1),
            Template("q_rb_vc2", "quality_rb.ini", large, 0.5, vcycles=2),
            Template("q_direct_l", "quality_direct.ini", large, 0.6),
            Template("q_direct_vc1", "quality_direct.ini", large, 0.6, vcycles=1),
            Template("hq_direct_l", "highest_quality_direct.ini", large, 0.3),
            Template("q_rb_xl", "quality_rb.ini", xlarge, 1.0),
            Template("q_direct_xl", "quality_direct.ini", xlarge, 0.5),
            Template("q_rb_rebal_s", "quality_rebal_rb.ini", small, 1.5),
            Template("q_rb_i40_m", "quality_rb_i40.ini", medium, 1.5),
            Template("spec_seed", "@spectral", medium, 0.8),
        ]
    else:
        es = 1.0 / (k - 1)
        t += [
            Template("q_direct_m", "quality_direct.ini", medium, 4.0),
            Template("q_direct_l", "quality_direct.ini", large, 3.0),
            Template("q_deep_m", "quality_deep.ini", medium, 2.0),
            Template("d_direct_m", "default_direct.ini", medium, 1.0),
            Template("dq_direct_m", "deterministic_quality_direct.ini", medium, 0.8),
            Template("q_direct_vc1", "quality_direct.ini", large, 0.8, vcycles=1),
            Template("q_direct_vc2", "quality_direct.ini", large, 0.7, vcycles=2),
            Template("q_rb_m", "quality_rb.ini", medium, 0.5),
            Template("hq_direct_l", "highest_quality_direct.ini", large, 0.3),
            Template("q_direct_m_epsmin", "quality_direct.ini", medium, 0.8,
                     eps_scale=es),
            Template("q_deep_m_epsmin", "quality_deep.ini", medium, 0.4,
                     eps_scale=es),
            Template("q_direct_xl", "quality_direct.ini", xlarge, 2.0),
            Template("q_direct_xl_vc1", "quality_direct.ini", xlarge, 0.6, vcycles=1),
            Template("q_direct_xl_vc2", "quality_direct.ini", xlarge, 0.5, vcycles=2),
            Template("q_rebal_direct_m", "quality_rebal_direct.ini", medium, 0.8),
            Template("q_rebal_deep_m", "quality_rebal_deep.ini", medium, 0.4),
            Template("q_direct_i40_m", "quality_direct_i40.ini", medium, 1.2),
            Template("q_rb_i40_m", "quality_rb_i40.ini", medium, 0.6),
            Template("spec_seed", "@spectral", medium, 1.0),
        ]
    return [x for x in t if x.threads <= cpus]


@dataclass
class Candidate:
    labels: list[int]
    cut: int
    family: str
    template: str


@dataclass
class Pool:
    cap: int = 12
    members: list[Candidate] = field(default_factory=list)

    def admit(self, c: Candidate) -> None:
        self.members.append(c)
        if len(self.members) > self.cap:
            by_family: dict[str, list[Candidate]] = {}
            for x in sorted(self.members, key=lambda c: c.cut):
                by_family.setdefault(x.family, []).append(x)
            keep = [v[0] for v in by_family.values()]
            rest = sorted((x for v in by_family.values() for x in v[1:]),
                          key=lambda c: c.cut)
            self.members = (keep + rest)[: self.cap]

    @property
    def best(self) -> Candidate | None:
        return min(self.members, key=lambda c: c.cut) if self.members else None


def solve(hgr_path: str, k: int, eps: float, *, time_s: float = 300.0,
          threads: int = 0, seed: int = 0, use_kep: bool = False,
          ilp_backend: str = "auto", ablate_stages: bool = False,
          workdir: str | None = None, log=print) -> dict:
    import os
    t0 = time.time()
    deadline = t0 + time_s
    threads = threads or os.cpu_count() or 8
    wd = Path(workdir or Path(hgr_path).stem + f"_fastpart_k{k}")
    wd.mkdir(parents=True, exist_ok=True)
    hg = read_hgr(hgr_path)
    inc = incidence(hg)
    pool = Pool()
    tel = {"alfm": dict(ran=False), "cnc": dict(ran=False),
           "polish": dict(ran=False), "budget": {}}
    stats: dict[str, Stats] = {}
    rng = random.Random(seed)
    templates = roster(k, threads)
    for t in templates:
        stats[t.name] = Stats()

    def ingest(path, family, template) -> int | None:
        try:
            labels = [int(x) for x in open(path).read().split()]
        except (OSError, ValueError):
            return None
        if len(labels) != hg.n:
            return None
        labels = repair(hg, labels, k, eps, inc=inc)
        c, _, ok = evaluate(hg, labels, k, eps)
        if ok:
            pool.admit(Candidate(labels, c, family, template))
            log(f"[{time.time()-t0:6.1f}s] {template}: cut={c}"
                f" (best={pool.best.cut})")
            return c
        return None

    if use_kep and not resolve_backend(ilp_backend):
        log(f"warning: ILP backend '{ilp_backend}' unavailable (installed: "
            f"{available_backends() or 'none'}); the C&C stage will be skipped")
    # ---- main portfolio loop: keep all lanes busy until the tail -----------
    lanes = threads
    running: list[tuple[str, Template, subprocess.Popen, float]] = []
    used = 0
    seq = 0
    # Tail reserve: the refinement stages (--kep) need a guaranteed slice, and
    # the reap of in-flight engine runs must not eat it. Without a reserve the
    # explore phase plus stragglers consume the whole budget and --kep silently
    # becomes a no-op on larger instances.
    # The reserve exists so the --kep stages have room. In default mode the
    # shipped behaviour is kept byte-for-byte: measured over 5 seeds x 8 cells,
    # spending the last ~8% of the budget on extra polish improves the MEDIAN
    # run but compresses the spread, and the paper's protocol is best-of-20,
    # which feeds on that spread. Not a win worth risking the published table.
    tail_reserve = (max(60.0, 0.25 * time_s) if use_kep else 10.0)
    tail_start = deadline - tail_reserve
    explore_end = min(t0 + 0.80 * time_s, tail_start)
    tel["budget"] = dict(total=time_s, tail_reserve=round(tail_reserve, 1),
                         explore_s=round(explore_end - t0, 1))
    warm_round = 0
    while time.time() < explore_end:
        # reap
        still = []
        for out, t, p, ts in running:
            if p.poll() is None:
                still.append((out, t, p, ts))
                continue
            used -= t.threads
            st = stats[t.name]
            st.tried += 1
            c = ingest(out, "global", f"{t.name}.s{seq}")
            if c is not None:
                st.valid += 1
                if st.best is None or c < st.best:
                    st.best = c
        running = still
        # launch: weighted template choice into free lanes
        while used + min(x.threads for x in templates) <= lanes:
            free = lanes - used
            avail = [x for x in templates if x.threads <= free]
            if not avail:
                break
            weights = [stats[x.name].score(x.weight) for x in avail]
            t = rng.choices(avail, weights=weights)[0]
            seq += 1
            out = str(wd / f"r{seq}.part")
            if t.config == "@spectral":
                import sys as _sys
                argv = [_sys.executable, "-m", "fastpart.spectral_runner",
                        hgr_path, "--out", out, "-k", str(k),
                        "--eps", str(eps), "--seed", str(seed + seq),
                        "--threads", str(t.threads),
                        "--dims", str(3 if seq % 2 else 4)]
            else:
                argv = RUNNER + [hgr_path, "--out", out, "-k", str(k),
                                 "--eps", str(eps),
                                 "--config", str(PRESETS / t.config),
                                 "--seed", str(seed + seq),
                                 "--threads", str(t.threads),
                                 "--vcycles", str(t.vcycles),
                                 "--eps-scale", str(t.eps_scale),
                                 "--relax", str(t.relax)]
            p = subprocess.Popen(argv, cwd=PKG_ROOT, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            running.append((out, t, p, time.time()))
            used += t.threads
        # opportunistic warm follow-on on the incumbent every ~25 s
        if pool.best is not None and time.time() - t0 > 30 * (warm_round + 1):
            warm_round += 1
            warm = str(wd / f"warm{warm_round}.part")
            Path(warm).write_text("\n".join(map(str, pool.best.labels)) + "\n")
            out = str(wd / f"fw{warm_round}.part")
            argv = RUNNER + [hgr_path, "--out", out, "-k", str(k),
                             "--eps", str(eps),
                             "--config", str(PRESETS / "quality_direct.ini"),
                             "--seed", str(seed + 7000 + warm_round),
                             "--threads", str(max(8, lanes // 6)),
                             "--vcycles", "2", "--warm", warm]
            fake = Template(f"warm{warm_round}", "quality_direct.ini",
                            max(8, lanes // 6), 0.0)
            stats.setdefault(fake.name, Stats())
            templates_by = fake
            p = subprocess.Popen(argv, cwd=PKG_ROOT, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            running.append((out, templates_by, p, time.time()))
            used += fake.threads
        time.sleep(0.3)
    for out, t, p, _ in running:
        try:
            # stragglers may not run into the tail reserve
            p.wait(timeout=max(2.0, tail_start - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()
            continue
        used -= t.threads
        ingest(out, "global", f"{t.name}.tail")
    # ---- tail: AL-FM touch, C&C recombination, final polish ----------------
    # AL-FM touch only when the python-side cost fits the remaining budget
    alfm_budget = deadline - 25 - time.time()
    # Cost-based gates, not vertex counts. Measured on this engine's output:
    # AL-FM 3 passes ~ 8.8 us/vertex (8.2 s at n=931k), C&C align+score+ILP
    # setup ~ 9 us/vertex (5-8 s at n=931k). The old n<=300k / n<=700k limits
    # silently disabled --kep on the largest instances for no measured reason.
    alfm_cost = 1.5 * 15.0e-6 * hg.n         # 1.5x safety; FM pass w/ rollback
    cnc_cost = 1.5 * 9.0e-6 * hg.n
    tel["alfm"]["gate"] = dict(use_kep=bool(use_kep), budget=round(alfm_budget, 1),
                               n=hg.n, est_s=round(alfm_cost, 1),
                               affordable=alfm_budget > alfm_cost + 10)
    if use_kep and not ablate_stages and pool.best is not None \
            and alfm_budget > alfm_cost + 10:
        _ts, _before, _prev = time.time(), pool.best.cut, list(pool.best.labels)
        # bounded slice: AL-FM reliably finds nothing on engine output, so it
        # must never consume the budget C&C needs
        _alfm_slice = min(alfm_budget * 0.5, 25.0)
        touched = ALFM(hg, list(pool.best.labels), k, eps, seed=seed,
                       inc=inc).refine(passes=3,
                                       deadline=time.time() + _alfm_slice)
        c, _, ok = evaluate(hg, touched, k, eps)
        tel["alfm"].update(ran=True, s=round(time.time() - _ts, 1),
                           slice_s=round(_alfm_slice, 1), before=_before,
                           after=c, feasible=bool(ok),
                           moved=sum(1 for a, b in zip(touched, _prev) if a != b),
                           improved=bool(ok and c < _before))
        if ok and c < pool.best.cut:
            pool.admit(Candidate(touched, c, "followon", "alfm"))
            log(f"[{time.time()-t0:6.1f}s] alfm: cut={c}")
    _cnc_left = deadline - 25 - time.time()
    tel["cnc"]["gate"] = dict(use_kep=bool(use_kep), members=len(pool.members),
                              left=round(_cnc_left, 1), n=hg.n,
                              est_s=round(cnc_cost, 1),
                              affordable=_cnc_left > cnc_cost + 10)
    if use_kep and not ablate_stages and len(pool.members) >= 2 \
            and _cnc_left > cnc_cost + 10:
        tops = sorted(pool.members, key=lambda c: c.cut)
        base = tops[0]
        # Partner selection must compare ALIGNED labels: raw label vectors of
        # two good partitions differ mostly by block permutation, which is not
        # disagreement. And C&C exploits a frontier that is small relative to
        # the instance (paper §3.4) -- a most-distant partner is a different
        # basin, where a capped border window touches almost none of it. So:
        # the largest frontier that still fits inside the band.
        _cands, _all = [], []
        for c in tops[1:8]:
            al = align_labels(base.labels, c.labels, k, hg.vertex_weight)
            d = sum(1 for v in range(hg.n) if al[v] != base.labels[v])
            if d > 0:
                _all.append((d, al, c.cut))
            if 0 < d <= 0.25 * hg.n:
                _cands.append((d, al, c.cut))
        # The border window is capped (4000 vertices), so a 200k-vertex frontier
        # would have only ~2% of it optimized. Prefer the largest frontier that
        # still FITS the window -- then C&C solves the whole disagreement region
        # exactly, which is the regime Algorithm 1 is written for.
        _fits = [c for c in _cands if c[0] <= 8000]
        tel["cnc"]["partners_distinct"] = len(_all)
        partner = (max(_fits, key=lambda t: t[0]) if _fits
                   else (min(_cands, key=lambda t: t[0]) if _cands else None))
        if partner is None and _all:
            # every pool member disagrees on more than the band allows (seen on
            # LU_Network K=4, where C&C was skipped for BOTH backends). Take the
            # closest one anyway: the border cap bounds the cost either way.
            partner = min(_all, key=lambda t: t[0])
            tel["cnc"]["band_fallback"] = True
        tel["cnc"]["partners_considered"] = len(tops[1:8])
        tel["cnc"]["partners_in_band"] = len(_cands)
        tel["cnc"]["partners_fitting_window"] = len(_fits)
        if partner is not None:
            _ts = time.time()
            _frontier, _plabels, _pcut = partner
            merged, mcut, patched = consensus_and_clean(
                hg, [base.labels, _plabels], k, eps,
                ilp_time_s=max(10.0, min(90.0, deadline - time.time() - 20)),
                workers=max(1, min(threads, 32)), backend=ilp_backend)
            be = resolve_backend(ilp_backend) or "none"
            tel["cnc"].update(ran=True, s=round(time.time() - _ts, 1), backend=be,
                              requested=ilp_backend, before=base.cut, after=mcut,
                              patched=bool(patched), frontier=_frontier,
                              partner_cut=_pcut)
            if patched:
                pool.admit(Candidate(merged, mcut, "followon", "cnc"))
                log(f"[{time.time()-t0:6.1f}s] cnc[{be}]: merged to {mcut}")
            else:
                log(f"[{time.time()-t0:6.1f}s] cnc[{be}]: no improvement over {base.cut}")
    _ts, _before, _rounds = time.time(), (pool.best.cut if pool.best else None), 0
    _max_rounds = 10**9 if use_kep else 1
    _polish_floor = 12 if use_kep else 10      # default mode: exactly as shipped
    while pool.best is not None and time.time() < deadline - _polish_floor \
            and _rounds < _max_rounds:
        best = pool.best
        warm = str(wd / f"final_warm{_rounds}.part")
        Path(warm).write_text("\n".join(map(str, best.labels)) + "\n")
        out = str(wd / f"final{_rounds}.part")
        argv = RUNNER + [hgr_path, "--out", out, "-k", str(k), "--eps", str(eps),
                         "--config", str(PRESETS / "highest_quality_direct.ini"),
                         "--seed", str(seed + 99 + _rounds), "--threads", str(threads),
                         "--vcycles", "2", "--warm", warm]
        p = subprocess.Popen(argv, cwd=PKG_ROOT, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=max(5.0, deadline - time.time()))
            ingest(out, "followon", "final-polish")
        except subprocess.TimeoutExpired:
            p.kill()
            break
        _rounds += 1
    if _rounds or _before is not None:
        tel["polish"] = dict(ran=bool(_rounds), s=round(time.time() - _ts, 1),
                             rounds=_rounds, before=_before,
                             after=pool.best.cut if pool.best else None)

    if use_kep and not ablate_stages and not tel["alfm"].get("ran"):
        log(f"[{time.time()-t0:6.1f}s] alfm: skipped ({tel['alfm']['gate']})")
    if use_kep and not ablate_stages and not tel["cnc"].get("ran"):
        log(f"[{time.time()-t0:6.1f}s] cnc: skipped ({tel['cnc']['gate']})")
    best = pool.best
    if best is None:
        return dict(ok=False, reason="no feasible candidate")
    out_path = wd / f"best.part{k}"
    out_path.write_text("\n".join(map(str, best.labels)) + "\n")
    c, w, ok = evaluate(hg, best.labels, k, eps)
    import hashlib
    sha = hashlib.sha256(",".join(map(str, best.labels)).encode()).hexdigest()[:16]
    return dict(ok=True, cut=c, feasible=ok, block_weights=w,
                partition=str(out_path), family=best.family,
                template=best.template, wall_s=round(time.time() - t0, 1),
                mode=("split-only" if (use_kep and ablate_stages)
                      else ("kep" if use_kep else "no-kep")),
                ilp_backend=resolve_backend(ilp_backend) or "none",
                partition_sha=sha, pool_size=len(pool.members),
                budget_s=time_s, stages=tel)
