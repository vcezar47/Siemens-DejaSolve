"""The second source of a warm start: a *predicted* state instead of a recalled one.

Phase 1 measures retrieval — hand the solver the converged state of the nearest
case somebody already solved. This measures the other arm of §3's "two sources,
one verifier": fit a cheap model to the archive, ask it to *predict* the answer
for a case nobody has solved, and hand that to the solver instead.

**This is the PhysicsAI arrow, at laptop scale.** PhysicsAI trains on historical
simulation data and predicts a full field "up to 1000x faster than traditional
solver simulations", after which its documented workflow says *"optionally
validate with a full solver run"* — and that validation run starts from zero.
The prediction is discarded. The claim of this project is that it should be the
solver's starting guess instead. This file is that claim, measured.

The surrogate is a **quadratic response surface**: normalise the 7 setup
parameters, expand to 36 polynomial features, ridge-fit 7 outputs. Deliberately
the simplest surrogate there is, and deliberately not a good one:

  * it must be *fast and slightly wrong*, because being slightly wrong is the
    whole demonstration — an approximate state is a bad final answer for exactly
    the reason it is a good starting guess;
  * it must not be a lookup in disguise. A k-nearest-neighbour regressor would
    just be retrieval wearing a different hat, and comparing retrieval against
    itself would prove nothing;
  * it must not add a dependency. Nothing here needs scikit-learn, and the
    image is small on purpose.

**Separate file, separate results, on purpose.** `benchmarks/bench.py` owns the headline
number and `summary_hash` enumerates its three arms by name; adding a fourth
there would move `830da3e6a4480676` and every document that quotes it. This
follows `benchmarks/fold.py` instead: its own experiment, its own JSON, quotable on its own.
The queries are `sample_cases(200, 99)` — byte-identical to the benchmark's — so
the arms are directly comparable to `results.json` and the overlap is asserted
at the end of the run rather than assumed.

**What the verifier does here is the interesting part.** A predicted state has
no *source case*, so gate 1 (`check_transfer`) does not apply — there is no
neighbouring case whose regime can be compared. Gate 2 does apply, and pointing
it at the *prediction* rather than at a converged answer asks a different and
useful question: **is this even a legal state to start from?** A surrogate that
predicts cavitating pressures is about to hand Newton a guess from outside the
model's validity. Same rules, same code, new target.

Whether that pre-filter actually pays is measured, not assumed — see the
`verified` arm here, and `--fold` for the circuit where the answer is different.

**On the base circuit the pre-filter is worth nothing**, because that circuit has
a unique root everywhere and a bad start can only cost iterations. `--fold` runs
the same experiment on the circuit where the starting guess selects *which* of
three roots Newton finds, and there an unverified prediction is ten times more
dangerous than an unverified retrieval. A third arm there (`post_only`) exists
to stop the flattering conclusion being drawn: the pre-filter is a cost
mechanism, and safety comes from the gate on the *answer*.

    python -m benchmarks.surrogate            # the base circuit: what a prediction is worth
    python -m benchmarks.surrogate --fold     # the fold circuit: what it costs unverified
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from benchmarks import fold
from dejasolve import model
from dejasolve import verifier
from benchmarks.bench import PRESSURE_IDX, SPEED_IDX, load_archive, nearest
from dejasolve.sweep import sample_cases

#: Tikhonov weight on the non-constant features. Small: the fit is
#: over-determined (395 rows, 36 columns) and the ridge is here to keep the
#: normal equations well conditioned, not to regularise for generalisation.
RIDGE = 1e-6


class ResponseSurface:
    """Quadratic response surface: 7 setup parameters -> 7 converged states.

    Fitted on normalised inputs and standardised outputs, because the outputs
    span two units and three orders of magnitude (a pressure in bar and a shaft
    speed in rev/min), and an unstandardised least-squares fit would spend all
    its accuracy on the speeds.
    """

    def __init__(self, ridge: float = RIDGE):
        self.ridge = ridge
        self.coef_: np.ndarray | None = None

    @staticmethod
    def _features(norm: np.ndarray) -> np.ndarray:
        """[1, x_i, x_i*x_j for i <= j] -- 1 + 7 + 28 = 36 columns."""
        norm = np.atleast_2d(norm)
        n, d = norm.shape
        cols = [np.ones((n, 1)), norm]
        cols += [(norm[:, i:i + 1] * norm[:, j:j + 1])
                 for i in range(d) for j in range(i, d)]
        return np.hstack(cols)

    def fit(self, params: np.ndarray, states: np.ndarray) -> "ResponseSurface":
        f = self._features(model.normalise(params))
        self.mu_, self.sd_ = states.mean(axis=0), states.std(axis=0)
        self.sd_[self.sd_ == 0] = 1.0
        y = (states - self.mu_) / self.sd_

        # ridge on everything except the intercept column
        reg = np.eye(f.shape[1]) * self.ridge
        reg[0, 0] = 0.0
        self.coef_ = np.linalg.solve(f.T @ f + reg, f.T @ y)
        self.n_features_ = f.shape[1]
        self.train_rmse_ = float(np.sqrt(((self.predict_raw(params) - states) ** 2).mean()))
        return self

    def predict_raw(self, params: np.ndarray) -> np.ndarray:
        f = self._features(model.normalise(np.atleast_2d(params)))
        return f @ self.coef_ * self.sd_ + self.mu_

    def predict(self, p: dict) -> np.ndarray:
        """The predicted state for one case, as the solver would take it."""
        return self.predict_raw(model.param_vector(p))[0]


# --- the fold circuit: where a starting guess selects the answer ------------

#: the escalation ladder a guarded policy walks, mirroring fold.guarded_transfer
#: so the two experiments are comparable rather than merely similar
MULTISTART = (600.0, 15.0, 1500.0)


def _resolve(p: dict, attempts: list[tuple[str, np.ndarray]]) -> dict:
    """Walk the ladder, checking each converged answer; take the first legal one.

    This is `fold.guarded_transfer` with the archive swapped for a prediction:
    the gate before differs (a prediction has no source case), the gate after is
    identical, and so is the escalation.
    """
    spent, trail = 0, []
    for label, x0 in attempts:
        r = model.solve(p, x0=x0)
        spent += r["iterations"]
        if not r["converged"]:
            trail.append(f"{label}: {r['status']}")
            continue
        vs = verifier.Verifier.check_solution(r["x"], p)
        trail.append(f"{label}: {vs}")
        if vs.admit:
            return {"converged": True, "resolved_by": label, "admissible": True,
                    "iterations_total": spent, "x": list(r["x"]), "trail": trail}
    return {"converged": False, "resolved_by": None, "admissible": False,
            "iterations_total": spent, "x": None, "trail": trail}


def _tally(cases: list[dict], key: str, field: str) -> dict:
    out: dict = {}
    for c in cases:
        out[c[key][field]] = out.get(c[key][field], 0) + 1
    return out


def run_fold(n_archive: int, n_query: int, out: Path) -> dict:
    """Does a *predicted* start land on impossible answers, and is that caught?

    §6e left this open on purpose. On the base circuit the prediction gate fires
    15 times in 200 and is worth 4 Newton iterations -- because that circuit has
    a unique root everywhere, so a bad start can only cost, never mislead. The
    fold circuit is the one where the starting guess decides *which* of three
    roots Newton finds, and the middle one is dynamically unstable. This is the
    circuit on which the question is worth asking.

    Three policies, and the third exists only to isolate what the pre-filter is
    worth:

      * ``naive``     -- start from the prediction, accept whatever comes back.
        The surrogate equivalent of today's behaviour, and the arm that can be
        *silently wrong*.
      * ``guarded``   -- refuse an illegal predicted state before using it,
        check the answer after, escalate rather than lie.
      * ``post_only`` -- no pre-filter; check the answer and escalate. If this
        reaches zero wrong answers too, then the pre-filter buys cost and not
        safety, and the honest thing is to say so.

    Same archive seed and same query seed as ``fold.run``, so the numbers sit
    directly beside the retrieval result rather than merely near it.
    """
    records, stats = fold.build_archive(n_archive, seed=11)
    params = np.array([[r["params"][k] for k in model.PARAM_NAMES] for r in records])
    states = np.array([[r["solution"][k] for k in model.STATE_NAMES] for r in records])
    surrogate = ResponseSurface().fit(params, states)

    queries = fold.fold_cases(n_query, seed=77)
    cases = []
    for i, p in enumerate(queries):
        pred = surrogate.predict(p)
        pre = verifier.Verifier.check_solution(pred, p)
        ladder = [("nominal", model.nominal_start(p))] + [
            ("multistart", np.array([150.0, 100.0, 20.0, w, 100.0, 20.0, w]))
            for w in MULTISTART]

        naive = model.solve(p, x0=pred)
        naive_state = "failed"
        if naive["converged"]:
            naive_state = ("ok" if verifier.Verifier.check_solution(naive["x"], p).admit
                           else "wrong")

        guarded = _resolve(p, ([("predicted", pred)] if pre.admit else []) + ladder)
        post_only = _resolve(p, [("predicted", pred)] + ladder)

        cases.append({
            "case_id": f"foldq-{i:04d}",
            "prediction": {
                "residual_inf": float(np.abs(model.residual(pred, p)).max()),
                "admissible": bool(pre.admit), "rule": pre.rule,
            },
            "naive": {"state": naive_state, "iterations": naive["iterations"]},
            "guarded": {k: guarded[k] for k in
                        ("converged", "resolved_by", "iterations_total")},
            "post_only": {k: post_only[k] for k in
                          ("converged", "resolved_by", "iterations_total")},
        })

    bad_pred = [c for c in cases if not c["prediction"]["admissible"]]
    by_rule: dict = {}
    for c in bad_pred:
        by_rule[c["prediction"]["rule"]] = by_rule.get(c["prediction"]["rule"], 0) + 1
    residuals = np.array([c["prediction"]["residual_inf"] for c in cases])

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "circuit": {"D_mot_cm3_per_rev": fold.D_FOLD,
                    "note": "the Stribeck fold: three roots, the middle one unstable"},
        "archive": stats,
        "n_queries": n_query,
        "surrogate": {"kind": "quadratic response surface (ridge least squares)",
                      "features": surrogate.n_features_,
                      "train_rmse": surrogate.train_rmse_},
        "prediction_quality": {
            "solver_tolerance": model.TOL,
            "median_residual_inf": float(np.median(residuals)),
            "max_residual_inf": float(residuals.max()),
            "inadmissible_predictions": len(bad_pred),
            "by_rule": by_rule,
        },
        "naive": _tally(cases, "naive", "state"),
        "guarded": {
            "resolved": sum(c["guarded"]["converged"] for c in cases),
            "unresolved": sum(not c["guarded"]["converged"] for c in cases),
            "total_iterations": sum(c["guarded"]["iterations_total"] for c in cases),
            "resolved_by": _tally(cases, "guarded", "resolved_by"),
        },
        "post_only": {
            "resolved": sum(c["post_only"]["converged"] for c in cases),
            "unresolved": sum(not c["post_only"]["converged"] for c in cases),
            "total_iterations": sum(c["post_only"]["iterations_total"] for c in cases),
            "resolved_by": _tally(cases, "post_only", "resolved_by"),
        },
        "cases": cases,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def report_fold(payload: dict) -> None:
    q, a = payload["prediction_quality"], payload["archive"]
    print()
    print(f"fold circuit ({payload['circuit']['D_mot_cm3_per_rev']:g} cm3/rev motor): "
          f"archive {a['kept']}/{a['n']} kept, "
          f"{a['rejected_unstable']} rejected as dynamically unstable")
    print(f"prediction residual: median {q['median_residual_inf']:.3g}, "
          f"worst {q['max_residual_inf']:.3g}  "
          f"(the solver stops at {q['solver_tolerance']:g})")
    print(f"predicted states that are not legal: "
          f"{q['inadmissible_predictions']} / {payload['n_queries']}"
          + (f"  {q['by_rule']}" if q["by_rule"] else ""))

    n = payload["naive"]
    print()
    print("naive -- start from the prediction, accept what comes back:")
    print(f"  valid operating point           : {n.get('ok', 0)}")
    print(f"  UNSTABLE ROOT (silently wrong)  : {n.get('wrong', 0)}")
    print(f"  no answer                       : {n.get('failed', 0)}")

    for name, blurb in (("guarded", "pre-filter the prediction, gate the answer, escalate"),
                        ("post_only", "no pre-filter; gate the answer, escalate")):
        g = payload[name]
        print()
        print(f"{name} -- {blurb}:")
        print(f"  valid operating point           : {g['resolved']}")
        print(f"  unresolved                      : {g['unresolved']}")
        print(f"  total Newton iterations         : {g['total_iterations']}")
        print(f"  resolved by                     : {g['resolved_by']}")


def _arm(entries: list[dict], key: str) -> dict:
    """Summarise one starting-guess arm the way benchmarks/bench.py reports its three."""
    conv = [e[key] for e in entries if e[key]["converged"]]
    return {
        "converged": len(conv),
        "failed": len(entries) - len(conv),
        "total_iterations": int(sum(e["iterations"] for e in conv)),
        "mean_iterations": (float(np.mean([e["iterations"] for e in conv]))
                            if conv else None),
    }


def run(archive_path: Path, n_queries: int, seed: int, out: Path) -> dict:
    records, archive_norm, archive_states = load_archive(archive_path)
    archive_params = np.array([[r["params"][k] for k in model.PARAM_NAMES]
                               for r in records])

    t0 = time.perf_counter()
    surrogate = ResponseSurface().fit(archive_params, archive_states)
    fit_ms = (time.perf_counter() - t0) * 1e3

    v = verifier.Verifier(records)
    queries = sample_cases(n_queries, seed)

    cases: list[dict] = []
    predict_ms: list[float] = []
    for i, p in enumerate(queries):
        t0 = time.perf_counter()
        pred = surrogate.predict(p)
        predict_ms.append((time.perf_counter() - t0) * 1e3)

        # How wrong is the prediction *as an answer*? This is the "approximate,
        # no guarantee" row of the deck's Act 2 table, as a number rather than
        # an adjective: the solver stops at 1e-8, so anything far above that is
        # a state that satisfies nothing.
        pred_residual = float(np.abs(model.residual(pred, p)).max())

        # Gate 2, pointed at the prediction: is this a legal state at all?
        verdict = verifier.Verifier.check_solution(pred, p)

        j, dist = nearest(p, archive_norm)
        cold = model.solve(p)
        nom = model.solve(p, x0=model.nominal_start(p))
        warm = model.solve(p, x0=archive_states[j])
        predicted = model.solve(p, x0=pred)
        # the verified arm declines an illegal starting state and takes the
        # nominal guess instead -- the same fallback a refused transfer takes
        verified = predicted if verdict.admit else nom

        entry = {
            "case_id": f"query-{i:04d}",
            "prediction": {
                "residual_inf": pred_residual,
                "admissible": bool(verdict.admit),
                "rule": verdict.rule,
                "reason": verdict.reason,
            },
            "neighbour_distance": dist,
        }
        for name, r in (("cold", cold), ("nominal", nom), ("warm", warm),
                        ("predicted", predicted), ("verified", verified)):
            entry[name] = {"converged": r["converged"], "status": r["status"],
                           "iterations": r["iterations"],
                           "residual_inf": r["residual_inf"]}

        # A different starting guess must not change the answer. Same check the
        # benchmark makes, for the same reason: if it moves, it is a bug.
        if cold["converged"] and predicted["converged"]:
            dx = np.abs(np.array(cold["x"]) - np.array(predicted["x"]))
            entry["agreement"] = {
                "max_dp_bar": float(dx[PRESSURE_IDX].max()),
                "max_dw_rpm": float(dx[SPEED_IDX].max()),
            }
        cases.append(entry)

    inadmissible = [c for c in cases if not c["prediction"]["admissible"]]
    by_rule: dict[str, int] = {}
    for c in inadmissible:
        by_rule[c["prediction"]["rule"]] = by_rule.get(c["prediction"]["rule"], 0) + 1

    residuals = np.array([c["prediction"]["residual_inf"] for c in cases])
    agreements = [c["agreement"] for c in cases if "agreement" in c]

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "archive_size": len(records),
        "n_queries": n_queries,
        "seed": seed,
        "surrogate": {
            "kind": "quadratic response surface (ridge least squares)",
            "features": surrogate.n_features_,
            "ridge": surrogate.ridge,
            "train_rmse": surrogate.train_rmse_,
            "fit_ms": fit_ms,
            "median_predict_ms": float(np.median(predict_ms)),
        },
        "prediction_quality": {
            "solver_tolerance": model.TOL,
            "median_residual_inf": float(np.median(residuals)),
            "min_residual_inf": float(residuals.min()),
            "max_residual_inf": float(residuals.max()),
            "n_below_solver_tolerance": int((residuals <= model.TOL).sum()),
        },
        "admissibility": {
            "checked": len(cases),
            "inadmissible_predictions": len(inadmissible),
            "by_rule": by_rule,
        },
        "arms": {name: _arm(cases, name) for name in
                 ("cold", "nominal", "warm", "predicted", "verified")},
        "agreement_vs_cold": {
            "compared": len(agreements),
            "max_dp_bar": max((a["max_dp_bar"] for a in agreements), default=None),
            "max_dw_rpm": max((a["max_dw_rpm"] for a in agreements), default=None),
        },
        "cases": cases,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def check_against_bench(payload: dict, results_path: Path) -> str:
    """The nominal and warm arms here must match results.json exactly.

    Same seed, same sampler, same solver — so any disagreement means one of the
    two files was generated from different code, which is the failure mode that
    quietly puts two different numbers for the same thing on two slides.
    """
    if not results_path.exists():
        return "results.json not present -- skipped"
    bench = json.loads(results_path.read_text(encoding="utf-8"))
    if "cases" not in bench:
        return "results.json has no per-case records -- skipped"
    mine = {c["case_id"]: c for c in payload["cases"]}
    mismatches = []
    for b in bench["cases"]:
        m = mine.get(b["case_id"])
        if not m:
            continue
        for arm in ("cold", "nominal", "warm"):
            if arm in b and b[arm]["iterations"] != m[arm]["iterations"]:
                mismatches.append(f"{b['case_id']}/{arm}")
    return ("all shared arms agree with results.json" if not mismatches
            else f"MISMATCH vs results.json on {len(mismatches)}: {mismatches[:5]}")


def report(payload: dict, bench_note: str) -> None:
    s, q = payload["surrogate"], payload["prediction_quality"]
    print(f"\nsurrogate: {s['kind']}, {s['features']} features, "
          f"fitted on {payload['archive_size']} archived cases in {s['fit_ms']:.0f} ms")
    print(f"prediction cost: {s['median_predict_ms']*1000:.0f} us (median)\n")

    print("Is the prediction an answer?  (the solver stops at "
          f"{q['solver_tolerance']:g})")
    print(f"  residual of the predicted state: median {q['median_residual_inf']:.3g}, "
          f"worst {q['max_residual_inf']:.3g}")
    print(f"  predictions that were actually solutions: "
          f"{q['n_below_solver_tolerance']} / {payload['n_queries']}")

    a = payload["admissibility"]
    print(f"\nGate 2 applied to the prediction itself: "
          f"{a['inadmissible_predictions']} / {a['checked']} are not legal states"
          + (f"  {a['by_rule']}" if a["by_rule"] else ""))

    print(f"\n{'arm':<12}{'converged':>11}{'failed':>8}{'total iters':>13}{'mean':>8}")
    for name, arm in payload["arms"].items():
        mean = f"{arm['mean_iterations']:.2f}" if arm["mean_iterations"] else "-"
        print(f"{name:<12}{arm['converged']:>11}{arm['failed']:>8}"
              f"{arm['total_iterations']:>13}{mean:>8}")

    ag = payload["agreement_vs_cold"]
    if ag["compared"]:
        print(f"\nsame answer as the cold solve on all {ag['compared']} compared cases: "
              f"max {ag['max_dp_bar']:.1e} bar, {ag['max_dw_rpm']:.1e} rev/min")
    print(f"cross-check: {bench_note}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=Path("data/archive/cases.jsonl"))
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--seed", type=int, default=99,
                    help="must match benchmarks/bench.py for the arms to be comparable")
    ap.add_argument("--out", type=Path, default=Path("results/surrogate_results.json"))
    ap.add_argument("--results", type=Path, default=Path("results/results.json"))
    ap.add_argument("--fold", action="store_true",
                    help="run the fold-circuit experiment instead: does a "
                         "predicted start land on unstable roots?")
    ap.add_argument("--fold-out", type=Path,
                    default=Path("results/surrogate_fold_results.json"))
    ap.add_argument("--fold-archive", type=int, default=300)
    args = ap.parse_args()

    if args.fold:
        payload = run_fold(args.fold_archive, args.queries, args.fold_out)
        report_fold(payload)
        print()
        print(f"wrote {args.fold_out}")
        return 0

    payload = run(args.archive, args.queries, args.seed, args.out)
    report(payload, check_against_bench(payload, args.results))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
