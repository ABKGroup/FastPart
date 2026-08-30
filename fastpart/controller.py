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
from .cnc import available_backends, consensus_and_clean, resolve_backend
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
          ilp_backend: str = "auto",
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
    explore_end = t0 + 0.80 * time_s
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
            p.wait(timeout=max(2.0, deadline - 10 - time.time()))
        except subprocess.TimeoutExpired:
            p.kill()
            continue
        used -= t.threads
        ingest(out, "global", f"{t.name}.tail")
    # ---- tail: AL-FM touch, C&C recombination, final polish ----------------
    # AL-FM touch only when the python-side cost fits the remaining budget
    alfm_budget = deadline - 25 - time.time()
    if use_kep and pool.best is not None and alfm_budget > 20 and hg.n <= 300_000:
        touched = ALFM(hg, list(pool.best.labels), k, eps, seed=seed,
                       inc=inc).refine(passes=3,
                                       deadline=time.time() + alfm_budget)
        c, _, ok = evaluate(hg, touched, k, eps)
        if ok and c < pool.best.cut:
            pool.admit(Candidate(touched, c, "followon", "alfm"))
            log(f"[{time.time()-t0:6.1f}s] alfm: cut={c}")
    if use_kep and len(pool.members) >= 2 and time.time() < deadline - 25 and hg.n <= 700_000:
        tops = sorted(pool.members, key=lambda c: c.cut)
        base = tops[0]
        partner = max(tops[1:5], key=lambda c: sum(
            1 for v in range(hg.n) if c.labels[v] != base.labels[v]),
            default=None)
        if partner is not None:
            merged, mcut, patched = consensus_and_clean(
                hg, [base.labels, partner.labels], k, eps,
                ilp_time_s=max(10.0, min(90.0, deadline - time.time() - 8)),
                workers=max(1, min(threads, 32)), backend=ilp_backend)
            be = resolve_backend(ilp_backend) or "none"
            if patched:
                pool.admit(Candidate(merged, mcut, "followon", "cnc"))
                log(f"[{time.time()-t0:6.1f}s] cnc[{be}]: merged to {mcut}")
            else:
                log(f"[{time.time()-t0:6.1f}s] cnc[{be}]: no improvement over {base.cut}")
    best = pool.best
    if best is not None and time.time() < deadline - 10:
        warm = str(wd / "final_warm.part")
        Path(warm).write_text("\n".join(map(str, best.labels)) + "\n")
        out = str(wd / "final.part")
        argv = RUNNER + [hgr_path, "--out", out, "-k", str(k), "--eps", str(eps),
                         "--config", str(PRESETS / "highest_quality_direct.ini"),
                         "--seed", str(seed + 99), "--threads", str(threads),
                         "--vcycles", "2", "--warm", warm]
        p = subprocess.Popen(argv, cwd=PKG_ROOT, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        try:
            p.wait(timeout=max(5.0, deadline - time.time()))
            ingest(out, "followon", "final-polish")
        except subprocess.TimeoutExpired:
            p.kill()

    best = pool.best
    if best is None:
        return dict(ok=False, reason="no feasible candidate")
    out_path = wd / f"best.part{k}"
    out_path.write_text("\n".join(map(str, best.labels)) + "\n")
    c, w, ok = evaluate(hg, best.labels, k, eps)
    return dict(ok=True, cut=c, feasible=ok, block_weights=w,
                partition=str(out_path), family=best.family,
                template=best.template, wall_s=round(time.time() - t0, 1),
                mode="kep" if use_kep else "no-kep")
