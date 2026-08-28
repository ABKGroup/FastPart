"""hMETIS-format hypergraph reader.

Format: first line `num_hyperedges num_vertices [fmt]`; fmt in {0,1,10,11}
(1 = hyperedge weights, 10 = vertex weights, 11 = both). Hyperedge lines list
1-based pin ids (optionally preceded by a weight); then one weight line per
vertex when vertex weights are present. Comment lines start with '%'.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hypergraph:
    n: int                      # vertices
    m: int                      # hyperedges
    pins: list[list[int]]       # 0-based pin lists, one per hyperedge
    edge_weight: list[int]
    vertex_weight: list[int]

    @property
    def total_weight(self) -> int:
        return sum(self.vertex_weight)


def read_hgr(path: str) -> Hypergraph:
    with open(path) as f:
        lines = [ln for ln in (raw.strip() for raw in f) if ln and not ln.startswith("%")]
    head = lines[0].split()
    m, n = int(head[0]), int(head[1])
    fmt = head[2] if len(head) > 2 else "0"
    has_ew = fmt in ("1", "11")
    has_vw = fmt in ("10", "11")
    pins: list[list[int]] = []
    ew: list[int] = []
    for ln in lines[1:1 + m]:
        parts = ln.split()
        if has_ew:
            ew.append(int(parts[0]))
            parts = parts[1:]
        else:
            ew.append(1)
        pins.append([int(x) - 1 for x in parts])
    if has_vw:
        vw = [int(lines[1 + m + v].split()[0]) for v in range(n)]
    else:
        vw = [1] * n
    return Hypergraph(n=n, m=m, pins=pins, edge_weight=ew, vertex_weight=vw)
