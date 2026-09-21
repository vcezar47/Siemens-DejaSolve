"""Are the *failed* runs worth keeping? A measurement, not an assumption.

An engineer asked for both successful and failed simulations to be in the
archive. The reasoning is good: a run that died is expensive evidence about
where initialisation is hard, and reducing it to a tally throws that away. On
the fold circuit it throws away **more than half the compute** — 165 rejected
runs against 135 kept.

So the runs are now kept (`dejasolve/sweep.py` writes `data/archive/failures.jsonl`,
`fold.sweep_fold` returns its rejects). This file asks the only question that
decides whether that is a feature or a filing cabinet:

    Does being *near a failed run* predict that this case will go badly?

The candidate rule is deliberately the simplest one that could work, and the
same shape as the gate it would join: compare the distance to the nearest
**failed** case against the distance to the nearest **successful** one, in the
same normalised setup space retrieval already uses. If the failures are closer,
warn.

    warn if   d(nearest failed) < d(nearest succeeded)

Two things are measured against it, because "go badly" has two meanings and
they are not the same question:

  * **hard_case**   -- the query's own cold solve never converges. This is the
    engineer's framing: *tell me this run is likely to die.*
  * **bad_transfer** -- naive retrieval from the nearest archived case returns
    no valid answer: it fails, or it converges onto a root the verifier rejects.

The honest outcome is reported either way. Phase 1 already found that setup
distance predicts transfer cost at r = 0.18 — barely at all — and there is no
reason to expect distance to failures to behave better just because the
question is phrased differently. If it does not predict, that is the result,
and `dejasolve/verifier.py` does not gain a rule that sounds sensible and does nothing.

    python -m benchmarks.failure_zone
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from benchmarks import fold
from dejasolve import model
from dejasolve import verifier

#: nothing below this many failures is worth drawing a conclusion from; the base
#: circuit only fails 5 times in 400 and is reported for completeness, not
#: evidence
MIN_FAILURES = 30


def _norm(records: list[dict]) -> np.ndarray:
    return model.normalise(
        np.array([[r["params"][k] for k in model.PARAM_NAMES] for r in records]))


def auc(scores: list[float], labels: list[bool]) -> float | None:
    """P(a random bad case scores above a random good one). 0.5 is a coin flip.

    Written out rather than imported: it is six lines, and the project ships
    four wheels.
    """
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return float(wins / (len(pos) * len(neg)))


def contingency(fires: list[bool], bad: list[bool]) -> dict:
    """What the rule would actually do to an engineer's day."""
    n = len(bad)
    tp = sum(f and b for f, b in zip(fires, bad))
    fp = sum(f and not b for f, b in zip(fires, bad))
    fn = sum((not f) and b for f, b in zip(fires, bad))
    tn = sum((not f) and (not b) for f, b in zip(fires, bad))
    base = sum(bad) / n if n else 0.0
    prec = tp / (tp + fp) if tp + fp else None
    return {
        "n": n,
        "base_rate": base,
        "warned": tp + fp,
        "true_positive": tp, "false_positive": fp,
        "false_negative": fn, "true_negative": tn,
        "precision": prec,
        "recall": tp / (tp + fn) if tp + fn else None,
        # the number that decides it: does warning tell you more than the base
        # rate already did? 1.0 means the rule is worth exactly nothing.
        "lift": (prec / base) if (prec is not None and base) else None,
    }


def evaluate(kept: list[dict], rejected: list[dict], queries: list[dict],
             label: str) -> dict:
    """Score the candidate rule on one circuit."""
    kept_norm = _norm(kept)
    rej_norm = _norm(rejected) if rejected else None
    kept_states = np.array([[r["solution"][k] for k in model.STATE_NAMES]
                            for r in kept])

    rows = []
    for i, p in enumerate(queries):
        q = model.normalise(model.param_vector(p))
        d_ok = np.linalg.norm(kept_norm - q, axis=1)
        j = int(np.argmin(d_ok))
        d_success = float(d_ok[j])
        d_fail = (float(np.linalg.norm(rej_norm - q, axis=1).min())
                  if rej_norm is not None and len(rej_norm) else float("inf"))

        cold = model.solve(p)
        hard_case = not cold["converged"]

        warm = model.solve(p, x0=kept_states[j])
        bad_transfer = not warm["converged"] or not (
            verifier.Verifier.check_solution(warm["x"], p).admit)

        rows.append({
            "case_id": f"{label}-{i:04d}",
            "d_success": d_success, "d_fail": d_fail,
            # positive means the failures are closer -- the rule fires
            "score": d_success - d_fail,
            "fires": bool(d_fail < d_success),
            "hard_case": bool(hard_case),
            "bad_transfer": bool(bad_transfer),
        })

    fires = [r["fires"] for r in rows]
    scores = [r["score"] for r in rows]
    out = {
        "circuit": label,
        "archive": {"succeeded": len(kept), "failed": len(rejected)},
        "n_queries": len(queries),
        "rule": "warn when the nearest failed case is closer than the nearest successful one",
        "fired": sum(fires),
        "underpowered": len(rejected) < MIN_FAILURES,
        "targets": {},
        "cases": rows,
    }
    for target in ("hard_case", "bad_transfer"):
        bad = [r[target] for r in rows]
        out["targets"][target] = {
            **contingency(fires, bad),
            # the threshold-free view, so a null result cannot be blamed on
            # where the cut was placed
            "auc": auc(scores, bad),
            # The confound this experiment exists to rule out: failures cluster
            # where the circuit is hard, and successes are *sparse* in exactly
            # the same places. If `d_success` alone scored as well, the failure
            # archive would be adding nothing the coverage rule does not already
            # see, and the honest conclusion would be "keep the files, skip the
            # rule". Both controls are computed every run so the question cannot
            # quietly stop being asked.
            "controls": {
                "d_success_only": auc([r["d_success"] for r in rows], bad),
                "d_fail_only": auc([-r["d_fail"] for r in rows], bad),
            },
        }
    return out


def run(out: Path, n_archive: int, n_query: int) -> dict:
    results = []

    kept, rejected, stats = fold.sweep_fold(n_archive, seed=11)
    print(f"fold circuit: {stats['kept']} kept, {stats['failed']} never converged, "
          f"{stats['rejected_unstable']} converged but inadmissible")
    results.append(evaluate(kept, rejected, fold.fold_cases(n_query, seed=77),
                            "foldq"))

    # The base circuit, reported because leaving it out would look like a choice.
    # It fails 5 times in 400, which is not enough to conclude anything, and the
    # payload says so rather than letting a reader assume otherwise.
    base_dir = Path("data/archive")
    cases_p, fails_p = base_dir / "cases.jsonl", base_dir / "failures.jsonl"
    if cases_p.exists() and fails_p.exists():
        base_kept = [json.loads(l) for l in cases_p.read_text(encoding="utf-8").splitlines() if l]
        base_fail = [json.loads(l) for l in fails_p.read_text(encoding="utf-8").splitlines() if l]
        from dejasolve.sweep import sample_cases
        results.append(evaluate(base_kept, base_fail,
                                sample_cases(n_query, 99), "query"))

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "min_failures_for_a_conclusion": MIN_FAILURES,
        "results": results,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _pct(v) -> str:
    """A target with no positives has no precision or recall -- say so."""
    return "n/a" if v is None else f"{v:.1%}"


def _num(v, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def report(payload: dict) -> None:
    for r in payload["results"]:
        a = r["archive"]
        print()
        print(f"--- {r['circuit']}: archive {a['succeeded']} succeeded / "
              f"{a['failed']} failed, {r['n_queries']} queries ---")
        if r["underpowered"]:
            print(f"    UNDERPOWERED: {a['failed']} failures is below the "
                  f"{payload['min_failures_for_a_conclusion']} needed to conclude "
                  f"anything. Reported, not relied on.")
        print(f"    rule fired on {r['fired']} / {r['n_queries']} queries")
        for target, t in r["targets"].items():
            print(f"    target = {target}")
            print(f"      base rate                : {t['base_rate']:.1%} "
                  f"({t['true_positive'] + t['false_negative']} of {t['n']})")
            if t["precision"] is None and not t["warned"]:
                print("      rule never fired -- nothing to score")
                continue
            print(f"      P(bad | rule fired)      : {_pct(t['precision'])}")
            print(f"      recall                   : {_pct(t['recall'])}")
            print(f"      lift over the base rate  : {_num(t['lift'])}x"
                  f"   <- 1.00 means worthless")
            c = t["controls"]
            print(f"      AUC (threshold-free)     : {_num(t['auc'], 3)}"
                  f"   <- 0.50 is a coin flip")
            print(f"        control, distance to nearest SUCCESS only : "
                  f"{_num(c['d_success_only'], 3)}"
                  f"   <- what coverage already sees")
            print(f"        control, distance to nearest FAILURE only : "
                  f"{_num(c['d_fail_only'], 3)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("results/failure_zone_results.json"))
    ap.add_argument("--archive", type=int, default=300)
    ap.add_argument("--queries", type=int, default=200)
    args = ap.parse_args()
    report(run(args.out, args.archive, args.queries))
    print()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
