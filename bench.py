"""THE NUMBER: cold start vs retrieval warm start, on cases never solved before.

Three arms, because one baseline is not enough to make the claim honestly:

  1. **cold** -- the flat start, every node at tank and every shaft at rest;
  2. **nominal** -- a guess built from the case setup alone (``model.nominal_start``),
     no archive and no solve. This is what a competent tool defaults to;
  3. **warm** -- the nearest archive case's converged state.

The flat start is the weakest defensible baseline, and warm-start results
measured only against it are the thing WARP (arXiv:2605.05728) criticises the
literature for: the win is inflated by a baseline nobody would ship. So the
headline is reported against *both*. If warm only beats cold, this project is a
demonstration; if it also beats nominal, it is a result.

Same residual, same Jacobian, same tolerance, same solver across all three. The
only difference is the starting guess, so any difference in the *answer* would
be a bug and any difference in cost is the result.

    python sweep.py && python bench.py
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import model
from sweep import sample_cases

#: which state entries are pressures (bar) and which are speeds (rev/min) --
#: agreement is reported per unit rather than as one meaningless max-norm
PRESSURE_IDX = [0, 1, 2, 4, 5]
SPEED_IDX = [3, 6]


def load_archive(path: Path) -> tuple[list[dict], np.ndarray, np.ndarray]:
    if not path.exists():
        raise SystemExit(f"no archive at {path} -- run `python sweep.py` first")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not records:
        raise SystemExit(f"archive at {path} is empty")
    params = np.array([[r["params"][k] for k in model.PARAM_NAMES] for r in records])
    states = np.array([[r["solution"][k] for k in model.STATE_NAMES] for r in records])
    return records, model.normalise(params), states


def nearest(query: dict, archive_norm: np.ndarray) -> tuple[int, float]:
    """Plain Euclidean nearest neighbour in the normalised setup space.

    Deliberately the simplest thing that can work: Phase 1 has to show that the
    *idea* pays off before Phase 2 spends effort on a better index or on the
    physics-aware verifier that decides whether the neighbour is admissible.
    """
    v = model.normalise(model.param_vector(query))
    d = np.linalg.norm(archive_norm - v, axis=1)
    j = int(np.argmin(d))
    return j, float(d[j])


#: Jacobian settings the sensitivity sweep reports. The headline result uses
#: the analytic Jacobian because it is the *best case for the cold baseline*;
#: the finite-difference rows show what happens in a solver whose components
#: do not all supply derivatives.
JAC_MODES = [
    ("analytic", None, "exact analytic Jacobian"),
    ("fd", 1.49e-8, "finite difference, sqrt(eps) step"),
    ("fd", 1e-6, "finite difference, coarse step"),
]


def run_bench(archive_path: Path, n_queries: int, seed: int, out: Path,
              jac_mode: str = "analytic", fd_step: float = model.FD_STEP,
              sensitivity: bool = True) -> dict:
    records, archive_norm, archive_states = load_archive(archive_path)
    queries = sample_cases(n_queries, seed)

    cases = []
    for i, p in enumerate(queries):
        j, dist = nearest(p, archive_norm)

        t0 = time.perf_counter()
        cold = model.solve(p, jac_mode=jac_mode, fd_step=fd_step)
        cold_ms = (time.perf_counter() - t0) * 1e3

        t0 = time.perf_counter()
        nom = model.solve(p, x0=model.nominal_start(p),
                          jac_mode=jac_mode, fd_step=fd_step)
        nom_ms = (time.perf_counter() - t0) * 1e3

        t0 = time.perf_counter()
        warm = model.solve(p, x0=archive_states[j], jac_mode=jac_mode, fd_step=fd_step)
        warm_ms = (time.perf_counter() - t0) * 1e3

        entry = {
            "case_id": f"query-{i:04d}",
            "params": {k: float(v) for k, v in p.items()},
            "neighbour_id": records[j]["case_id"],
            "neighbour_distance": dist,
            "cold": {"converged": cold["converged"], "status": cold["status"],
                     "iterations": cold["iterations"],
                     "residual_inf": cold["residual_inf"], "wall_ms": cold_ms},
            "nominal": {"converged": nom["converged"], "status": nom["status"],
                        "iterations": nom["iterations"],
                        "residual_inf": nom["residual_inf"], "wall_ms": nom_ms},
            "warm": {"converged": warm["converged"], "status": warm["status"],
                     "iterations": warm["iterations"],
                     "residual_inf": warm["residual_inf"], "wall_ms": warm_ms},
        }
        if cold["converged"] and warm["converged"]:
            dx = np.abs(np.array(cold["x"]) - np.array(warm["x"]))
            entry["agreement"] = {
                "max_dp_bar": float(dx[PRESSURE_IDX].max()),
                "max_dw_rpm": float(dx[SPEED_IDX].max()),
            }
            if nom["converged"]:
                # a third starting guess that lands somewhere else is the same
                # bug as a warm start that does -- check it the same way
                dn = np.abs(np.array(cold["x"]) - np.array(nom["x"]))
                entry["agreement"]["max_dp_bar_nominal"] = float(dn[PRESSURE_IDX].max())
                entry["agreement"]["max_dw_rpm_nominal"] = float(dn[SPEED_IDX].max())
        entry["_hist"] = {"cold": cold["history"], "nominal": nom["history"],
                          "warm": warm["history"]}
        entry["_x"] = {"cold": cold["x"], "nominal": nom["x"], "warm": warm["x"]}
        cases.append(entry)

    summary = summarise(cases)
    exemplars = pick_exemplars(cases)

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "archive": str(archive_path),
            "archive_size": len(records),
            "n_queries": n_queries,
            "query_seed": seed,
            "tol": model.TOL,
            "max_iter": model.MAX_ITER,
            "jac_mode": jac_mode,
            "fd_step": fd_step if jac_mode == "fd" else None,
            "retrieval": "euclidean 1-NN on min-max normalised setup vector",
        },
        "summary": summary,
        "exemplars": exemplars,
        "cases": [{k: v for k, v in c.items() if not k.startswith("_")} for c in cases],
    }
    report(summary, len(records), n_queries, out)

    if sensitivity:
        payload["jacobian_sensitivity"] = run_sensitivity(
            queries, archive_norm, archive_states)

    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n  -> {out}")
    return payload


def summary_hash(payload: dict) -> str:
    """A short digest of the Phase 1 result, for "did anything move?".

    Deliberately over a *subset*: timings and the generation timestamp change on
    every run, and the archive path changes with the OS separator, so hashing
    the whole file would report a difference on every machine and prove nothing.
    What is left is exactly what a slide would quote.

    The recipe lives here rather than in a shell command because a
    reproducibility claim nobody can re-run is not a check.
    """
    import hashlib

    s = payload["summary"]
    core = {
        "config": {k: v for k, v in payload["config"].items() if k != "archive"},
        "cold": {k: v for k, v in s["cold"].items() if not k.endswith("_ms")},
        "nominal": {k: v for k, v in s["nominal"].items() if not k.endswith("_ms")},
        "warm": {k: v for k, v in s["warm"].items() if not k.endswith("_ms")},
        **{k: s[k] for k in ("n_queries", "rescued", "broken",
                             "iteration_reduction_pct", "warm_vs_nominal",
                             "agreement", "neighbour_distance")},
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def run_sensitivity(queries, archive_norm, archive_states) -> list[dict]:
    """How much of the result depends on how good the solver's Jacobian is.

    Reported because it changes the conclusion: with an exact Jacobian the
    cold baseline rarely fails outright and the win is iteration count; with a
    coarse finite-difference Jacobian the cold baseline fails often and the win
    is that those runs finish at all. Both are honest, so both are shown.

    The nominal baseline travels with them, because the interesting question is
    not whether a bad Jacobian hurts the flat start -- it obviously does -- but
    whether the archive still buys anything once the baseline is competent.
    """
    rows = []
    print("\njacobian sensitivity (same cases, same archive, same tolerance)")
    print(f"  {'solver Jacobian':32} {'cold':>9} {'nom':>9} {'warm':>9} "
          f"{'cold it':>8} {'nom it':>8} {'warm it':>8}")
    for mode, step, label in JAC_MODES:
        kw = {"jac_mode": mode}
        if step is not None:
            kw["fd_step"] = step
        cold_fail = nom_fail = warm_fail = 0
        ci, wi = [], []
        ni, wni = [], []
        for i, p in enumerate(queries):
            j, _ = nearest(p, archive_norm)
            c = model.solve(p, **kw)
            m = model.solve(p, x0=model.nominal_start(p), **kw)
            w = model.solve(p, x0=archive_states[j], **kw)
            cold_fail += not c["converged"]
            nom_fail += not m["converged"]
            warm_fail += not w["converged"]
            if c["converged"] and w["converged"]:
                ci.append(c["iterations"])
                wi.append(w["iterations"])
            if m["converged"] and w["converged"]:
                ni.append(m["iterations"])
                wni.append(w["iterations"])
        row = {
            "label": label, "jac_mode": mode, "fd_step": step,
            "n": len(queries),
            "cold_failures": int(cold_fail),
            "nominal_failures": int(nom_fail),
            "warm_failures": int(warm_fail),
            "cold_mean_iterations": float(np.mean(ci)),
            "nominal_mean_iterations": float(np.mean(ni)) if ni else None,
            "warm_mean_iterations": float(np.mean(wi)),
            "iteration_reduction_pct": float(100 * (1 - np.sum(wi) / np.sum(ci))),
            "iteration_reduction_vs_nominal_pct": (
                float(100 * (1 - np.sum(wni) / np.sum(ni))) if np.sum(ni) else None),
        }
        rows.append(row)
        nom_it = f"{np.mean(ni):>8.1f}" if ni else f"{'--':>8}"
        print(f"  {label:32} {cold_fail:>6}/{len(queries):<2} {nom_fail:>6}/{len(queries):<2} "
              f"{warm_fail:>6}/{len(queries):<2} "
              f"{np.mean(ci):>8.1f} {nom_it} {np.mean(wi):>8.1f}")
    return rows


def summarise(cases: list[dict]) -> dict:
    cold_ok = [c for c in cases if c["cold"]["converged"]]
    warm_ok = [c for c in cases if c["warm"]["converged"]]
    nom_ok = [c for c in cases if c["nominal"]["converged"]]
    both = [c for c in cases if c["cold"]["converged"] and c["warm"]["converged"]]
    #: the warm-vs-nominal comparison needs its own paired subset -- the cases
    #: where the two arms being compared both converged, same rule as `both`
    both_nom = [c for c in cases
                if c["nominal"]["converged"] and c["warm"]["converged"]]

    ci = np.array([c["cold"]["iterations"] for c in both])
    wi = np.array([c["warm"]["iterations"] for c in both])
    dp = np.array([c["agreement"]["max_dp_bar"] for c in both])
    dw = np.array([c["agreement"]["max_dw_rpm"] for c in both])

    ni = np.array([c["nominal"]["iterations"] for c in both_nom])
    wni = np.array([c["warm"]["iterations"] for c in both_nom])
    dpn = np.array([c["agreement"]["max_dp_bar_nominal"] for c in both
                    if "max_dp_bar_nominal" in c["agreement"]])
    dwn = np.array([c["agreement"]["max_dw_rpm_nominal"] for c in both
                    if "max_dw_rpm_nominal" in c["agreement"]])

    def modes(arm: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in cases:
            if not c[arm]["converged"]:
                out[c[arm]["status"]] = out.get(c[arm]["status"], 0) + 1
        return out

    cold_modes = modes("cold")

    n = len(cases)
    return {
        "n_queries": n,
        "cold": {
            "failures": n - len(cold_ok),
            "failure_rate": (n - len(cold_ok)) / n,
            "failure_modes": cold_modes,
            "mean_iterations": float(ci.mean()),
            "median_iterations": float(np.median(ci)),
            "total_iterations": int(ci.sum()),
            "total_wall_ms": float(sum(c["cold"]["wall_ms"] for c in cases)),
        },
        "warm": {
            "failures": n - len(warm_ok),
            "failure_rate": (n - len(warm_ok)) / n,
            "mean_iterations": float(wi.mean()),
            "median_iterations": float(np.median(wi)),
            "total_iterations": int(wi.sum()),
            "total_wall_ms": float(sum(c["warm"]["wall_ms"] for c in cases)),
        },
        "nominal": {
            "failures": n - len(nom_ok),
            "failure_rate": (n - len(nom_ok)) / n,
            "failure_modes": modes("nominal"),
            "mean_iterations": float(ni.mean()) if len(ni) else None,
            "median_iterations": float(np.median(ni)) if len(ni) else None,
            "total_iterations": int(ni.sum()),
            "total_wall_ms": float(sum(c["nominal"]["wall_ms"] for c in cases)),
        },
        #: the honest headline. Beating the flat start is table stakes; this is
        #: the number that says whether the archive earns its place.
        "warm_vs_nominal": {
            "n_compared": len(both_nom),
            "nominal_mean_iterations": float(ni.mean()) if len(ni) else None,
            "warm_mean_iterations": float(wni.mean()) if len(wni) else None,
            "iteration_reduction_pct": (
                float(100 * (1 - wni.sum() / ni.sum())) if ni.sum() else None),
            "rescued": sum(1 for c in cases if c["warm"]["converged"]
                           and not c["nominal"]["converged"]),
            "broken": sum(1 for c in cases if c["nominal"]["converged"]
                          and not c["warm"]["converged"]),
            "agreement": {
                "n_compared": len(dpn),
                "max_dp_bar": float(dpn.max()) if len(dpn) else None,
                "max_dw_rpm": float(dwn.max()) if len(dwn) else None,
                "n_disagreeing": (int(np.sum((dpn > 1e-6) | (dwn > 1e-6)))
                                  if len(dpn) else 0),
            },
        },
        "rescued": sum(1 for c in cases
                       if c["warm"]["converged"] and not c["cold"]["converged"]),
        "broken": sum(1 for c in cases
                      if c["cold"]["converged"] and not c["warm"]["converged"]),
        "iteration_reduction_pct": float(100 * (1 - wi.sum() / ci.sum())),
        "agreement": {
            "n_compared": len(both),
            "max_dp_bar": float(dp.max()),
            "max_dw_rpm": float(dw.max()),
            "n_disagreeing": int(np.sum((dp > 1e-6) | (dw > 1e-6))),
        },
        "neighbour_distance": {
            "mean": float(np.mean([c["neighbour_distance"] for c in cases])),
            "max": float(np.max([c["neighbour_distance"] for c in cases])),
        },
    }


def pick_exemplars(cases: list[dict]) -> dict:
    """Two cases worth plotting: a typical speed-up, and a rescued failure."""
    ex = {}
    both = [c for c in cases if c["cold"]["converged"] and c["warm"]["converged"]]
    if both:
        best = max(both, key=lambda c: c["cold"]["iterations"] - c["warm"]["iterations"])
        ex["speedup"] = _exemplar(best)
    rescued = [c for c in cases if c["warm"]["converged"] and not c["cold"]["converged"]]
    if rescued:
        ex["rescued"] = _exemplar(min(rescued, key=lambda c: c["neighbour_distance"]))
    return ex


def _exemplar(c: dict) -> dict:
    e = {k: v for k, v in c.items() if not k.startswith("_")}
    e["history"] = c["_hist"]
    e["final_state"] = {
        "cold": dict(zip(model.STATE_NAMES, c["_x"]["cold"])),
        "nominal": dict(zip(model.STATE_NAMES, c["_x"]["nominal"])),
        "warm": dict(zip(model.STATE_NAMES, c["_x"]["warm"])),
    }
    return e


def report(s: dict, archive_size: int, n: int, out: Path) -> None:
    c, m, w = s["cold"], s["nominal"], s["warm"]
    vn = s["warm_vs_nominal"]

    def num(v, fmt=".1f"):
        return "--" if v is None else format(v, fmt)

    print(f"\narchive {archive_size} cases \u00b7 {n} fresh query cases\n")
    print(f"{'':22} {'cold (flat)':>12} {'nominal':>12} {'warm':>12}")
    print(f"{'failed to converge':22} {c['failures']:>12} {m['failures']:>12} "
          f"{w['failures']:>12}")
    print(f"{'mean iterations':22} {num(c['mean_iterations']):>12} "
          f"{num(m['mean_iterations']):>12} {num(w['mean_iterations']):>12}")
    print(f"{'median iterations':22} {num(c['median_iterations'], '.0f'):>12} "
          f"{num(m['median_iterations'], '.0f'):>12} "
          f"{num(w['median_iterations'], '.0f'):>12}")
    print(f"{'total iterations':22} {c['total_iterations']:>12} "
          f"{m['total_iterations']:>12} {w['total_iterations']:>12}")
    print(f"{'total wall time (ms)':22} {c['total_wall_ms']:>12.0f} "
          f"{m['total_wall_ms']:>12.0f} {w['total_wall_ms']:>12.0f}")

    print(f"\n  vs the flat start  {s['iteration_reduction_pct']:>6.0f}% fewer "
          f"iterations, {s['rescued']} rescued, {s['broken']} broken")
    print(f"  vs nominal         {num(vn['iteration_reduction_pct'], '6.0f')}% fewer "
          f"iterations, {vn['rescued']} rescued, {vn['broken']} broken"
          f"   <- the number that has to hold up")

    a = s["agreement"]
    print(f"\n  same answer on all {a['n_compared']} compared cases: "
          f"max dp {a['max_dp_bar']:.1e} bar, max dw {a['max_dw_rpm']:.1e} rev/min "
          f"({a['n_disagreeing']} disagreeing)")
    an = vn["agreement"]
    if an["n_compared"]:
        print(f"  nominal lands on the same answer on {an['n_compared']}: "
              f"max dp {an['max_dp_bar']:.1e} bar, "
              f"max dw {an['max_dw_rpm']:.1e} rev/min "
              f"({an['n_disagreeing']} disagreeing)")
    print(f"  cold failure modes:    {c['failure_modes']}")
    print(f"  nominal failure modes: {m['failure_modes']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=Path("archive/cases.jsonl"))
    ap.add_argument("--n", type=int, default=200, help="fresh query cases")
    ap.add_argument("--seed", type=int, default=99, help="must differ from the sweep seed")
    ap.add_argument("--out", type=Path, default=Path("results.json"))
    ap.add_argument("--jac", choices=["analytic", "fd"], default="analytic")
    ap.add_argument("--fd-step", type=float, default=model.FD_STEP)
    ap.add_argument("--no-sensitivity", action="store_true")
    args = ap.parse_args()
    run_bench(args.archive, args.n, args.seed, args.out,
              jac_mode=args.jac, fd_step=args.fd_step,
              sensitivity=not args.no_sensitivity)


if __name__ == "__main__":
    main()
