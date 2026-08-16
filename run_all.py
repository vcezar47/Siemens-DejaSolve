"""Regenerate every number and figure in the deck, from scratch, in one command.

    python run_all.py

Nothing in the presentation should be a number I typed by hand — this is the
command that has to reproduce all of them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bench
import plot_convergence
import sweep

ARCHIVE = Path("archive")
RESULTS = Path("results.json")
FIGURE = Path("figs/convergence.png")


def main() -> int:
    sweep.run_sweep(n=400, seed=1, out_dir=ARCHIVE)
    bench.run_bench(ARCHIVE / "cases.jsonl", n_queries=200, seed=99, out=RESULTS)
    import json
    plot_convergence.draw(json.loads(RESULTS.read_text(encoding="utf-8")), FIGURE)
    print("\nall artifacts regenerated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
