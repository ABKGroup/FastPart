"""Spectral seeding for the DirectSeed arm (paper §3.2): a low-dimensional
embedding followed by K-means-style clustering at the coarsest level, exposing
macro-structure that recursive splitting may never visit.

Implementation: star-expansion Laplacian (spoke weight w/(|e|-1)), LOBPCG for
the d smallest nontrivial eigenvectors with a Jacobi preconditioner, then
balanced K-means over the embedding (size-capped assignment so the seed lands
near the window before repair)."""

from __future__ import annotations

import numpy as np

from .evaluator import window
from .hgr import Hypergraph


def embedding(hg: Hypergraph, dims: int = 3, iters: int = 120, seed: int = 0):
    from scipy import sparse
    from scipy.sparse.linalg import lobpcg

    rows, cols, vals = [], [], []
    aux = 0
    for e, ps in enumerate(hg.pins):
        m = len(ps)
        if m < 2:
            continue
        if m == 2:
            rows.append(ps[0]); cols.append(ps[1]); vals.append(float(hg.edge_weight[e]))
        else:
            c = hg.n + aux
            aux += 1
            spoke = float(hg.edge_weight[e]) / (m - 1)
            for v in ps:
                rows.append(v); cols.append(c); vals.append(spoke)
    N = hg.n + aux
    A = sparse.coo_matrix((vals + vals, (rows + cols, cols + rows)), shape=(N, N)).tocsr()
    deg = np.asarray(A.sum(axis=1)).ravel()
    Lap = sparse.diags(deg) - A
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((N, dims))
    ones = np.ones((N, 1))
    M = sparse.diags(1.0 / np.maximum(deg, 1e-9))
    try:
        _vals, vecs = lobpcg(Lap, X, M=M, Y=ones, maxiter=iters, tol=1e-5,
                             largest=False)
    except Exception:
        return None
    return vecs[:hg.n]


def kmeans_seed(hg: Hypergraph, k: int, eps_pct: float, dims: int = 3,
                seed: int = 0) -> list[int] | None:
    """Balanced K-means over the spectral embedding: greedy capped assignment
    by distance to the nearest centroid, Lloyd-style recentering."""
    emb = embedding(hg, dims=dims, seed=seed)
    if emb is None:
        return None
    rng = np.random.default_rng(seed + 1)
    n = hg.n
    _, U = window(hg, k, eps_pct)
    cap = U
    centers = emb[rng.choice(n, size=k, replace=False)]
    labels = np.zeros(n, dtype=np.int64)
    for _ in range(6):
        d = ((emb[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        pref = np.argsort(d.min(axis=1) - d.max(axis=1))     # most decided first
        load = [0] * k
        for v in pref:
            for b in np.argsort(d[v]):
                if load[b] + hg.vertex_weight[v] <= cap:
                    labels[v] = b
                    load[b] += hg.vertex_weight[v]
                    break
            else:
                b = int(np.argmin(load))
                labels[v] = b
                load[b] += hg.vertex_weight[v]
        for b in range(k):
            sel = labels == b
            if sel.any():
                centers[b] = emb[sel].mean(axis=0)
    return labels.tolist()
