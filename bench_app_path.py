"""The number as the *app* actually produces it, not as an isolated arm.

`bench.py` measures each warm-start construction on its own: no verifier, no
fallback, scored on the paired subset where the arm and the nominal guess both
converged. That is the right way to compare constructions -- but it is not what
`dejasolve.analyse` runs. The app shortlists the k nearest, lets the verifier
*filter* them, ranks the survivors by predicted start error, starts the solve
from the winner with the second-order transfer, and falls back to the nominal
guess when the gate admits nobody.

This script runs that exact path -- `Archive.select` then `Archive.warm_start`,
the same two calls `analyse` makes -- over `bench.py`'s own 200 query cases
(seed 99), so the headline the deck quotes from `results.json` can be checked
against what a person clicking Analyse would see.

    python bench_app_path.py

Writes bench_app_path_results.json. No new physics, no new archive: every
number here is downstream of the same model and the same cases.jsonl bench.py
uses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import dejasolve
import model
import sweep

ARCHIVE = Path("archive/cases.jsonl")
N_QUERIES = 200
SEED = 99


def run(archive_path: Path = ARCHIVE, n: int = N_QUERIES, seed: int = SEED,
        out: Path | None = Path("bench_app_path_results.json")) -> dict:
    arc = dejasolve.Archive(archive_path)
    queries = sweep.sample_cases(n, seed)

    nominal_iters: list[int] = []
    arm_iters: list[int | None] = []
    fell_back = 0
    picked_not_nearest = 0
    orders: dict[str, int] = {}
    refused_rules: dict[str, int] = {}

    for p in queries:
        nom = model.solve(p, x0=model.nominal_start(p))
        nominal_iters.append(nom["iterations"])

        j, dist, ranking, verdict = arc.select(p)
        if not ranking["picked_was_nearest"]:
            picked_not_nearest += 1

        if verdict.admit:
            x0, order = arc.warm_start(j, p)
            orders[order] = orders.get(order, 0) + 1
            r = model.solve(p, x0=x0)
            arm_iters.append(r["iterations"] if r["converged"] else None)
        else:
            fell_back += 1
            refused_rules[verdict.rule] = refused_rules.get(verdict.rule, 0) + 1
            # exactly what analyse() does when the gate refuses every candidate
            arm_iters.append(nom["iterations"] if nom["converged"] else None)

    ok = [x for x in arm_iters if x is not None]
    nom_mean = float(np.mean(nominal_iters))
    arm_mean = float(np.mean(ok))

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "what": "dejasolve.Archive.select + warm_start over bench.py's 200 "
                "queries -- the shipped app path, gate and fallback included",
        "archive": str(archive_path),
        "archive_size": len(arc.records),
        "n_queries": n,
        "seed": seed,
        "nominal": {
            "mean_iterations": nom_mean,
            "total_iterations": int(sum(nominal_iters)),
        },
        "app_warm_arm": {
            "mean_iterations": arm_mean,
            "failures": len(arm_iters) - len(ok),
            "iteration_reduction_vs_nominal_pct": (nom_mean - arm_mean)
            / nom_mean * 100.0,
            "fell_back_to_nominal": fell_back,
            "picked_not_nearest": picked_not_nearest,
            "transfer_orders": orders,
            "gate_refusals_by_rule": refused_rules,
        },
    }

    if out is not None:
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def report(v: dict) -> None:
    a = v["app_warm_arm"]
    print(f"app warm-start path -- {v['n_queries']} queries, seed {v['seed']}, "
          f"archive {v['archive_size']}")
    print(f"  nominal guess              {v['nominal']['mean_iterations']:.3f} "
          f"mean iterations")
    print(f"  app warm arm (gated)       {a['mean_iterations']:.3f} mean "
          f"iterations   {a['failures']} failed to converge")
    print(f"  reduction vs nominal       "
          f"{a['iteration_reduction_vs_nominal_pct']:.1f}%   "
          f"(bench.py 'ranked + 2nd order' arm: 57.2%)")
    print(f"  fell back to nominal       {a['fell_back_to_nominal']} / "
          f"{v['n_queries']}   (gate admitted no candidate)")
    print(f"  pick was not the nearest   {a['picked_not_nearest']} / "
          f"{v['n_queries']}")
    print(f"  transfer orders used       {a['transfer_orders']}")
    if a["gate_refusals_by_rule"]:
        print(f"  gate refusals by rule      {a['gate_refusals_by_rule']}")


if __name__ == "__main__":
    report(run())
