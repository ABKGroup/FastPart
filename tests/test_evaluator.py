"""Tiny sanity tests for the evaluator + repair (run: python3 -m pytest tests)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastpart.hgr import Hypergraph
from fastpart.evaluator import evaluate, window
from fastpart.repair import repair


def toy():
    # 6 vertices, 4 nets; net weights 1
    pins = [[0, 1], [1, 2], [3, 4], [4, 5]]
    return Hypergraph(n=6, m=4, pins=pins, edge_weight=[1] * 4, vertex_weight=[1] * 6)


def test_window_two_sided():
    hg = toy()
    L, U = window(hg, 2, 10.0)          # (0.5 +- 0.1) * 6 = [2.4, 3.6] -> [3, 3]
    assert (L, U) == (3, 3)


def test_evaluate_cut_and_feasibility():
    hg = toy()
    cut, w, ok = evaluate(hg, [0, 0, 0, 1, 1, 1], 2, 10.0)
    assert cut == 0 and w == [3, 3] and ok


def test_repair_restores_window():
    hg = toy()
    lab = repair(hg, [0, 0, 0, 0, 0, 1], 2, 10.0)
    _, w, ok = evaluate(hg, lab, 2, 10.0)
    assert ok and w == [3, 3]
