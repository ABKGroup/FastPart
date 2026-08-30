"""Consensus-and-Clean backend tests: both ILP backends must find the same patch."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastpart import cnc
from fastpart.evaluator import evaluate
from fastpart.hgr import Hypergraph


def path8():
    # path 0-1-2-3-4-5-6-7, K=2, eps=25% -> window [2,6]
    pins = [[i, i + 1] for i in range(7)]
    return Hypergraph(n=8, m=7, pins=pins, edge_weight=[1] * 7, vertex_weight=[1] * 8)


# two tied cut=3 candidates whose disagreement frontier admits a cut=1 fix
A = [0, 0, 0, 1, 0, 1, 1, 1]
B = [0, 0, 1, 0, 0, 1, 1, 1]


@pytest.mark.parametrize("backend", cnc.available_backends() or ["none"])
def test_backend_finds_the_patch(backend):
    if backend == "none":
        pytest.skip("no ILP backend installed")
    hg = path8()
    labels, cut, patched = cnc.consensus_and_clean(hg, [A, B], 2, 25.0, ilp_time_s=10,
                                                   backend=backend)
    c, w, ok = evaluate(hg, labels, 2, 25.0)
    assert patched and cut == 1 and c == 1 and ok


def test_missing_backend_returns_base_unchanged(monkeypatch):
    hg = path8()
    monkeypatch.setattr(cnc, "available_backends", lambda: [])
    labels, cut, patched = cnc.consensus_and_clean(hg, [A, B], 2, 25.0, backend="auto")
    assert not patched and cut == 3 and labels == A


def test_auto_falls_back_to_cpsat_when_cplex_fails_at_solve(monkeypatch):
    if "ortools" not in cnc.available_backends():
        pytest.skip("ortools not installed")
    hg = path8()
    monkeypatch.setattr(cnc, "available_backends", lambda: ["cplex", "ortools"])

    def boom(*_a, **_k):
        raise RuntimeError("CPXERR_RESTRICTED_VERSION: model too large for Community Edition")
    monkeypatch.setattr(cnc, "_solve_cplex", boom)
    labels, cut, patched = cnc.consensus_and_clean(hg, [A, B], 2, 25.0, ilp_time_s=10,
                                                   backend="auto")
    assert patched and cut == 1                      # CP-SAT rescued the stage


def test_explicit_cplex_does_not_silently_switch_backend(monkeypatch):
    hg = path8()
    monkeypatch.setattr(cnc, "available_backends", lambda: ["cplex", "ortools"])
    monkeypatch.setattr(cnc, "_solve_cplex", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    labels, cut, patched = cnc.consensus_and_clean(hg, [A, B], 2, 25.0, backend="cplex")
    assert not patched and cut == 3                 # explicit request: no fallback
