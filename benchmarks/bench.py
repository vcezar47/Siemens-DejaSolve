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

    python -m dejasolve.sweep && python -m benchmarks.bench
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from dejasolve import model
from dejasolve.sweep import sample_cases

#: which state entries are pressures (bar) and which are speeds (rev/min) --
#: agreement is reported per unit rather than as one meaningless max-norm
PRESSURE_IDX = [0, 1, 2, 4, 5]
SPEED_IDX = [3, 6]

#: how many candidates the `ranked` arm scores. Five because `benchmarks/agent_select.py`
#: measured the selection ceiling at that depth, so the two are comparable --
#: and because the point being made is about the *ranking signal*, not about
#: retrieving more.
K_RANKED = 5

#: the arms in report order. `cold` and `nominal` are the two baselines;
#: everything after them is a way of spending the archive.
ARMS = ("cold", "nominal", "warm", "first_order", "ranked", "second_order", "simplex")


def load_archive(path: Path) -> tuple[list[dict], np.ndarray, np.ndarray]:
    if not path.exists():
        raise SystemExit(f"no archive at {path} -- run `python -m dejasolve.sweep` first")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not records:
        raise SystemExit(f"archive at {path} is empty")
    params = np.array([[r["params"][k] for k in model.PARAM_NAMES] for r in records])
    states = np.array([[r["solution"][k] for k in model.STATE_NAMES] for r in records])
    return records, model.normalise(params), states


def sensitivities(records: list[dict]) -> list[np.ndarray | None]:
    """The per-card solution tangents, as written by `dejasolve/sweep.py`.

    An archive built before sensitivities existed simply has none, and every
    arm that uses them degrades to the verbatim transfer rather than failing --
    the same rule the rest of the pipeline follows for a missing field.
    """
    out: list[np.ndarray | None] = []
    for r in records:
        s = r.get("sensitivity")
        out.append(None if s is None else np.asarray(s, dtype=float))
    return out


def hessians(records: list[dict]) -> list[np.ndarray | None]:
    """The per-card solution Hessians (curvature tensors), as written by `dejasolve/sweep.py`."""
    out: list[np.ndarray | None] = []
    for r in records:
        h = r.get("hessian")
        out.append(None if h is None else np.asarray(h, dtype=float))
    return out


def nearest_k(query: dict, archive_norm: np.ndarray, k: int) -> np.ndarray:
    """Indices of the k nearest archive cases, nearest first."""
    v = model.normalise(model.param_vector(query))
    d = np.linalg.norm(archive_norm - v, axis=1)
    return np.argsort(d)[:k]


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
    sens = sensitivities(records)
    hess = hessians(records)
    queries = sample_cases(n_queries, seed)

    def timed(p: dict, x0):
        """Solve and return (result, wall_ms). Every arm is timed identically,
        because a timing difference between arms that came from how they were
        measured rather than from what they did would be the whole result."""
        t0 = time.perf_counter()
        r = model.solve(p, x0=x0, jac_mode=jac_mode, fd_step=fd_step)
        return r, (time.perf_counter() - t0) * 1e3

    def arm(r, ms):
        return {"converged": r["converged"], "status": r["status"],
                "iterations": r["iterations"],
                "residual_inf": r["residual_inf"], "wall_ms": ms}

    cases = []
    for i, p in enumerate(queries):
        j, dist = nearest(p, archive_norm)

        cold, cold_ms = timed(p, None)
        nom, nom_ms = timed(p, model.nominal_start(p))
        warm, warm_ms = timed(p, archive_states[j])

        # first-order: the same retrieved card, but walked toward the query
        # along the tangent it recorded. Same candidate as `warm` on purpose --
        # this arm isolates the *transfer*, changing nothing about retrieval.
        fo, fo_ms = timed(p, model.transfer_start(
            archive_states[j], sens[j], records[j]["params"], p))

        # ranked: the same transfer, but the candidate is chosen by which card
        # predicts the smallest start error rather than by which is nearest.
        # Retrieval and transfer are the two separable halves, so they get one
        # arm each and the table shows what each is worth on its own.
        cand = nearest_k(p, archive_norm, K_RANKED)
        pick = min(cand, key=lambda c: model.predicted_start_error(
            sens[c], records[c]["params"], p))
        rk, rk_ms = timed(p, model.transfer_start(
            archive_states[pick], sens[pick], records[pick]["params"], p))

        # second-order: the ranked candidate pick, but using the solution Hessian
        # to add curvature correction ½ Δp^T H Δp
        so, so_ms = timed(p, model.transfer_start_second_order(
            archive_states[pick], sens[pick], hess[pick], records[pick]["params"], p))

        # simplex: inverse-distance weighted combination of top k candidates'
        # first-order transfers
        v_query = model.normalise(model.param_vector(p))
        cands_data = []
        for c in cand:
            d_norm = float(np.linalg.norm(archive_norm[c] - v_query))
            cands_data.append((archive_states[c], sens[c], records[c]["params"], d_norm))
        sx, sx_ms = timed(p, model.transfer_start_simplex(cands_data, p))

        entry = {
            "case_id": f"query-{i:04d}",
            "params": {k: float(v) for k, v in p.items()},
            "neighbour_id": records[j]["case_id"],
            "neighbour_distance": dist,
            "ranked_id": records[int(pick)]["case_id"],
            "ranked_was_nearest": bool(int(pick) == j),
            "cold": arm(cold, cold_ms),
            "nominal": arm(nom, nom_ms),
            "warm": arm(warm, warm_ms),
            "first_order": arm(fo, fo_ms),
            "ranked": arm(rk, rk_ms),
            "second_order": arm(so, so_ms),
            "simplex": arm(sx, sx_ms),
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
            # and the same check again for the constructed arms that construct a
            # start rather than reusing one.
            for name, r in (("first_order", fo), ("ranked", rk),
                            ("second_order", so), ("simplex", sx)):
                if r["converged"]:
                    d = np.abs(np.array(cold["x"]) - np.array(r["x"]))
                    entry["agreement"][f"max_dp_bar_{name}"] = float(d[PRESSURE_IDX].max())
                    entry["agreement"][f"max_dw_rpm_{name}"] = float(d[SPEED_IDX].max())
        entry["_hist"] = {"cold": cold["history"], "nominal": nom["history"],
                          "warm": warm["history"], "first_order": fo["history"],
                          "ranked": rk["history"], "second_order": so["history"],
                          "simplex": sx["history"]}
        entry["_x"] = {"cold": cold["x"], "nominal": nom["x"], "warm": warm["x"],
                       "first_order": fo["x"], "ranked": rk["x"],
                       "second_order": so["x"], "simplex": sx["x"]}
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


def arm_vs_nominal(cases: list[dict], name: str) -> dict:
    """One constructed arm, scored against the nominal guess.

    Paired the same way `warm_vs_nominal` is -- only the cases where both this
    arm and nominal converged -- because a reduction computed over a different
    set of cases from its baseline is not a reduction.

    `agreement` is against the *cold* solve rather than against nominal: cold
    is the arm with no opinion about where the answer should be, so it is the
    right thing to ask "did constructing a start change what we found?".
    """
    n = len(cases)
    ok = [c for c in cases if c[name]["converged"]]
    both = [c for c in cases if c["nominal"]["converged"] and c[name]["converged"]]
    it = np.array([c[name]["iterations"] for c in both])
    ni = np.array([c["nominal"]["iterations"] for c in both])
    dp = np.array([c["agreement"][f"max_dp_bar_{name}"] for c in cases
                   if f"max_dp_bar_{name}" in c.get("agreement", {})])
    dw = np.array([c["agreement"][f"max_dw_rpm_{name}"] for c in cases
                   if f"max_dw_rpm_{name}" in c.get("agreement", {})])
    return {
        "failures": n - len(ok),
        "mean_iterations": float(it.mean()) if len(it) else None,
        "median_iterations": float(np.median(it)) if len(it) else None,
        "total_iterations": int(it.sum()),
        "total_wall_ms": float(sum(c[name]["wall_ms"] for c in cases)),
        "n_compared": len(both),
        "iteration_reduction_vs_nominal_pct": (
            float(100 * (1 - it.sum() / ni.sum())) if ni.sum() else None),
        "iteration_reduction_vs_warm_pct": _vs_warm(cases, name),
        "rescued": sum(1 for c in cases if c[name]["converged"]
                       and not c["nominal"]["converged"]),
        "broken": sum(1 for c in cases if c["nominal"]["converged"]
                      and not c[name]["converged"]),
        "agreement": {
            "n_compared": len(dp),
            "max_dp_bar": float(dp.max()) if len(dp) else None,
            "max_dw_rpm": float(dw.max()) if len(dw) else None,
            "n_disagreeing": (int(np.sum((dp > 1e-6) | (dw > 1e-6)))
                              if len(dp) else 0),
        },
    }


def _vs_warm(cases: list[dict], name: str) -> float | None:
    """The same arm against today's verbatim transfer, on their shared cases."""
    both = [c for c in cases if c["warm"]["converged"] and c[name]["converged"]]
    if not both:
        return None
    w = sum(c["warm"]["iterations"] for c in both)
    a = sum(c[name]["iterations"] for c in both)
    return float(100 * (1 - a / w)) if w else None


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
        #: The two arms that build a start instead of reusing one. Kept in
        #: their own block, and deliberately *outside* everything
        #: `summary_hash` covers: the cold/nominal/warm numbers are the frozen
        #: Phase 1 result and adding an arm must not move them by so much as a
        #: rounding. If it ever does, something reached back into the baseline.
        "constructed": {
            name: arm_vs_nominal(cases, name)
            for name in ("first_order", "ranked", "second_order", "simplex")
        },
        "ranked_picked_the_nearest": sum(
            1 for c in cases if c.get("ranked_was_nearest")),
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

    fo = s["constructed"]["first_order"]
    rk = s["constructed"]["ranked"]
    so = s["constructed"]["second_order"]
    sx = s["constructed"]["simplex"]

    print(f"\narchive {archive_size} cases \u00b7 {n} fresh query cases\n")
    print(f"{'':22} {'cold (flat)':>12} {'nominal':>12} {'warm':>12} "
          f"{'+1st order':>12} {'+ranked':>12} {'+2nd order':>12} {'+simplex':>12}")
    row = lambda label, key, fmt=None: print(
        f"{label:22} " + " ".join(
            f"{(num(a[key], fmt) if fmt else a[key]):>12}"
            for a in (c, m, w, fo, rk, so, sx)))
    row("failed to converge", "failures")
    row("mean iterations", "mean_iterations", ".1f")
    row("median iterations", "median_iterations", ".0f")
    row("total iterations", "total_iterations")
    print(f"{'total wall time (ms)':22} " + " ".join(
        f"{a['total_wall_ms']:>12.0f}" for a in (c, m, w, fo, rk, so, sx)))

    print(f"\n  vs the flat start  {s['iteration_reduction_pct']:>6.0f}% fewer "
          f"iterations, {s['rescued']} rescued, {s['broken']} broken")
    print(f"  vs nominal         {num(vn['iteration_reduction_pct'], '6.0f')}% fewer "
          f"iterations, {vn['rescued']} rescued, {vn['broken']} broken"
          f"   <- the number that has to hold up")

    # The arms that construct a start. Reported against nominal (the honest
    # baseline) and against warm (what they actually have to beat to be worth
    # the bytes they add to every Case Card).
    print(f"\n  transferring constructed starts instead of verbatim:")
    for label, a in (("  1-NN + sensitivity", fo),
                     (f"  ranked over k={K_RANKED}", rk),
                     (f"  ranked + 2nd order", so),
                     (f"  simplex over k={K_RANKED}", sx)):
        print(f"  {label:24} "
              f"{num(a['iteration_reduction_vs_nominal_pct'], '6.1f')}% vs nominal, "
              f"{num(a['iteration_reduction_vs_warm_pct'], '5.1f')}% vs warm, "
              f"{a['rescued']} rescued, {a['broken']} broken")
        ag = a["agreement"]
        if ag["n_compared"]:
            print(f"  {'':24} same answer on {ag['n_compared']}: max dp "
                  f"{ag['max_dp_bar']:.1e} bar, max dw {ag['max_dw_rpm']:.1e} "
                  f"rev/min ({ag['n_disagreeing']} disagreeing)")
    print(f"  the ranker chose the nearest card "
          f"{s['ranked_picked_the_nearest']}/{n} times")

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
    ap.add_argument("--archive", type=Path, default=Path("data/archive/cases.jsonl"))
    ap.add_argument("--n", type=int, default=200, help="fresh query cases")
    ap.add_argument("--seed", type=int, default=99, help="must differ from the sweep seed")
    ap.add_argument("--out", type=Path, default=Path("results/results.json"))
    ap.add_argument("--jac", choices=["analytic", "fd"], default="analytic")
    ap.add_argument("--fd-step", type=float, default=model.FD_STEP)
    ap.add_argument("--no-sensitivity", action="store_true")
    args = ap.parse_args()
    run_bench(args.archive, args.n, args.seed, args.out,
              jac_mode=args.jac, fd_step=args.fd_step,
              sensitivity=not args.no_sensitivity)


if __name__ == "__main__":
    main()
