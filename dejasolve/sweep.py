"""Build the archive: run a parameter sweep and keep what converged.

This is the Study-Manager-style sweep that a team would run overnight. Each
case is solved from the default cold guess, exactly as a tool would today.
Cases that converge become archive records — proto Case Cards holding the
setup, the converged state and the operating regime. Cases that fail are
counted and dropped, because an archive holds successful runs.

    python -m dejasolve.sweep                 # 400 cases -> data/archive/cases.jsonl
    python -m dejasolve.sweep --n 800 --seed 7
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import model


def latin_hypercube(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """Stratified sample in the unit cube — better coverage than plain uniform
    for the same number of expensive runs, which is why sweeps use it."""
    u = np.empty((n, d))
    for j in range(d):
        u[:, j] = (rng.permutation(n) + rng.random(n)) / n
    return u


def sample_cases(n: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    u = latin_hypercube(n, len(model.PARAM_NAMES), rng)
    lo = np.array([model.PARAM_BOUNDS[k][0] for k in model.PARAM_NAMES])
    hi = np.array([model.PARAM_BOUNDS[k][1] for k in model.PARAM_NAMES])
    scaled = lo + u * (hi - lo)
    return [dict(zip(model.PARAM_NAMES, row)) for row in scaled]


def sensitivity_of(x, p: dict) -> list[list[float]] | None:
    """The solution's tangent in parameter space, or None if there isn't one.

    A singular Jacobian at a converged solution is rare but not a crash: the
    case is still solved and still worth archiving, it just cannot say how its
    answer moves. Recording that as an explicit `null` keeps the distinction
    between "no tangent" and "zero tangent", which are very different claims.
    """
    try:
        return model.solution_sensitivity(x, p).tolist()
    except np.linalg.LinAlgError:
        return None


def hessian_of(x, p: dict) -> list[list[list[float]]] | None:
    """The solution's curvature in parameter space, or None.

    Computed by central-differencing the first-order sensitivity over each
    parameter direction.  Costs ~14 perturbed solves per card, but runs once
    offline and adds ~50 ms per card.  A card whose hessian is ``null`` still
    transfers first-order; the second-order correction simply does not apply.
    """
    H = model.solution_hessian(x, p)
    return None if H is None else H.tolist()


def run_sweep(n: int, seed: int, out_dir: Path) -> dict:
    cases = sample_cases(n, seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    records, failures = [], []
    t_start = time.perf_counter()
    for i, p in enumerate(cases):
        t0 = time.perf_counter()
        res = model.solve(p)
        wall_ms = (time.perf_counter() - t0) * 1e3
        case_id = f"sweep-{i:04d}"

        if res["converged"]:
            records.append({
                "case_id": case_id,
                "params": {k: float(v) for k, v in p.items()},
                "solution": dict(zip(model.STATE_NAMES, res["x"])),
                "regime": model.regime(res["x"], p),
                #: dx*/dp at this solution -- what makes the transfer
                #: first-order instead of verbatim. Stored rather than
                #: recomputed on load because retrieval has to work without
                #: the model: once the archive is a database rather than a
                #: file, the service answering a query holds Case Cards, not
                #: a residual it can differentiate.
                #: `null` when the Jacobian is singular here -- a solved case
                #: with no usable tangent is still a usable case, and
                #: `model.transfer_start` falls back to the verbatim state.
                "sensitivity": sensitivity_of(res["x"], p),
                "hessian": hessian_of(res["x"], p),
                "solve": {
                    "start": "cold",
                    "status": res["status"],
                    "iterations": res["iterations"],
                    "residual_inf": res["residual_inf"],
                    "wall_ms": wall_ms,
                },
            })
        else:
            # Kept, not counted. An engineer asked for the failures to be in
            # the archive too, and they were right: a run that died is expensive
            # evidence about *where* initialisation is hard, and reducing it to
            # a tally throws that away. What it is actually worth is measured in
            # `benchmarks/failure_zone.py` rather than assumed here.
            failures.append({"case_id": case_id, "status": res["status"],
                             "params": {k: float(v) for k, v in p.items()},
                             "iterations": res["iterations"],
                             "residual_inf": res["residual_inf"],
                             "wall_ms": wall_ms})

    wall_s = time.perf_counter() - t_start
    iters = np.array([r["solve"]["iterations"] for r in records])

    with (out_dir / "cases.jsonl").open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    # A separate file rather than a flag on cases.jsonl: everything downstream
    # reads the archive expecting a converged `solution` on every line, and a
    # record without one would be a landmine in every consumer.
    with (out_dir / "failures.jsonl").open("w", encoding="utf-8") as fh:
        for rec in failures:
            print(json.dumps(rec), file=fh)

    status_counts: dict[str, int] = {}
    for f in failures:
        status_counts[f["status"]] = status_counts.get(f["status"], 0) + 1

    summary = {
        "n_cases": n,
        "seed": seed,
        "converged": len(records),
        "failed": len(failures),
        "failure_rate": len(failures) / n,
        "failure_modes": status_counts,
        "iterations": {
            "mean": float(iters.mean()),
            "median": float(np.median(iters)),
            "p90": float(np.percentile(iters, 90)),
            "max": int(iters.max()),
            "total": int(iters.sum()),
        },
        "wall_s": wall_s,
        "relief_open_share": float(np.mean([r["regime"]["relief_open"] for r in records])),
        "with_sensitivity": sum(1 for r in records if r["sensitivity"] is not None),
        "with_hessian": sum(1 for r in records if r["hessian"] is not None),
    }
    (out_dir / "sweep_summary.json").write_text(json.dumps(summary, indent=2),
                                                encoding="utf-8")

    print(f"sweep: {n} cases in {wall_s:.1f}s")
    print(f"  converged {len(records)}  failed {len(failures)} "
          f"({100 * summary['failure_rate']:.1f}%)  {status_counts}")
    print(f"  cold iterations: mean {iters.mean():.1f}  median "
          f"{np.median(iters):.0f}  max {iters.max()}")
    print(f"  relief valve open in {100 * summary['relief_open_share']:.0f}% of the archive")
    print(f"  solution sensitivity recorded on {summary['with_sensitivity']}"
          f"/{len(records)} cards")
    print(f"  solution hessian recorded on {summary['with_hessian']}"
          f"/{len(records)} cards")
    print(f"  -> {out_dir / 'cases.jsonl'}  ({len(failures)} failures -> "
          f"{out_dir / 'failures.jsonl'})")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=400, help="number of sweep cases")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("data/archive"))
    args = ap.parse_args()
    run_sweep(args.n, args.seed, args.out)


if __name__ == "__main__":
    main()
