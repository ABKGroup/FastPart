"""fastpart CLI.

    python -m fastpart.cli INSTANCE.hgr K [--eps 2] [--time 300] [--no-kep]
"""

from __future__ import annotations

import argparse
import json


def main() -> int:
    # Own a process group and tear the whole tree down on TERM/INT: engine
    # children must never outlive the controller (survivors poison later runs).
    import os
    import signal

    try:
        os.setpgrp()
    except OSError:
        pass

    def _die(_sig, _frm):
        try:
            os.killpg(0, signal.SIGKILL)
        except OSError:
            os._exit(1)

    signal.signal(signal.SIGTERM, _die)
    signal.signal(signal.SIGINT, _die)

    ap = argparse.ArgumentParser(prog="fastpart")
    ap.add_argument("hypergraph")
    ap.add_argument("k", type=int)
    ap.add_argument("--eps", type=float, default=2.0,
                    help="two-sided absolute imbalance in percent (default 2)")
    ap.add_argument("--time", type=float, default=300.0)
    ap.add_argument("--threads", type=int, default=0, help="0 = all vCPUs")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--out-json", default=None)
    a = ap.parse_args()

    from .controller import solve
    res = solve(a.hypergraph, a.k, a.eps, time_s=a.time, threads=a.threads,
                seed=a.seed, workdir=a.workdir)
    print(json.dumps(res, indent=1))
    if a.out_json:
        with open(a.out_json, "w") as f:
            json.dump(res, f, indent=1)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
