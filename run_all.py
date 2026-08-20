"""Regenerate every number and figure in the deck, from scratch, in one command.

    python run_all.py

Nothing in the presentation should be a number I typed by hand — this is the
command that has to reproduce all of them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bench
import fold
import ingest
import make_logs
import plot_convergence
import surrogate
import sweep

ARCHIVE = Path("archive")
RESULTS = Path("results.json")
FIGURE = Path("figs/convergence.png")
FOLD_RESULTS = Path("fold_results.json")
FOLD_FIGURE = Path("figs/verifier.png")
SURROGATE_RESULTS = Path("surrogate_results.json")
SURROGATE_FOLD_RESULTS = Path("surrogate_fold_results.json")


def main(score_models: bool = False) -> int:
    print("=" * 62)
    print("PHASE 1 -- cold vs warm start on the base circuit")
    print("=" * 62)
    sweep.run_sweep(n=400, seed=1, out_dir=ARCHIVE)
    bench.run_bench(ARCHIVE / "cases.jsonl", n_queries=200, seed=99, out=RESULTS)
    import json
    plot_convergence.draw(json.loads(RESULTS.read_text(encoding="utf-8")), FIGURE)

    print()
    print("=" * 62)
    print("PHASE 1b -- the other source of a warm start: a predicted state")
    print("=" * 62)
    # Deliberately after bench: it cross-checks its shared arms against
    # results.json, which is how two files reporting the same quantity are kept
    # from drifting into two different numbers on two different slides.
    surrogate.report(
        surrogate.run(ARCHIVE / "cases.jsonl", n_queries=200, seed=99,
                      out=SURROGATE_RESULTS),
        surrogate.check_against_bench(
            json.loads(SURROGATE_RESULTS.read_text(encoding="utf-8")), RESULTS))

    print()
    print("=" * 62)
    print("PHASE 2 -- the verifier, on the fold circuit")
    print("=" * 62)
    # The prediction arm on the same circuit, first: it is the experiment that
    # decides whether gating a *predicted* start is safety or merely cost, and
    # it shares fold.py's archive and query seeds so the two sit side by side.
    surrogate.report_fold(
        surrogate.run_fold(n_archive=300, n_query=200, out=SURROGATE_FOLD_RESULTS))
    print()
    fold.run(n_archive=300, n_query=200, out=FOLD_RESULTS, fig=FOLD_FIGURE)

    print()
    print("=" * 62)
    print("PHASE 3 -- ingest: messy artifacts into Case Cards")
    print("=" * 62)
    make_logs.main()
    # The parser alone is scored by default so this stays a seconds-long
    # command. A model backend costs minutes per prose artifact, which is a
    # deliberate opt-in rather than a surprise in the reproducer.
    backends = ["rules"]
    if score_models:
        if ingest.ollama_available()[0]:
            backends += ["ollama", "hybrid"]
        if ingest.credentials_available():
            backends.append("llm")
        if backends == ["rules"]:
            print("\n--score-models asked for, but no model backend is "
                  "reachable -- scoring the parser only.")
    else:
        print("\nscoring the parser only (seconds). Add --score-models to "
              "score ollama/hybrid too -- minutes per prose artifact.")
    ingest.report(ingest.compare(Path("logs"), backends),
                  Path("logs/ground_truth.json"))

    import json as _json
    print()
    print(f"phase-1 summary hash: "
          f"{bench.summary_hash(_json.loads(RESULTS.read_text(encoding='utf-8')))}")
    print("\nall artifacts regenerated.")
    print("End-to-end demo:  python dejasolve.py --all")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--score-models", action="store_true",
                    help="also score the ollama/hybrid (and Claude) ingest "
                         "backends -- slow: minutes per prose artifact")
    sys.exit(main(ap.parse_args().score_models))
