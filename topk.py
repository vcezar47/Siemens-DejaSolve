"""Walk the archive before abandoning it: k candidates instead of one.

Retrieval today is `argmin` — one candidate, and if the verifier refuses it the
archive is abandoned and the solver falls back to the nominal guess. That is a
strange policy on inspection: the gate refusing the *nearest* case says nothing
about the second nearest, and on the fold circuit the gate refuses **69 of 200**
transfers. Every one of those threw away an archive that may well have held an
admissible case two rows down.

§3 promised a retrieval layer that decides *which* past run to start from. One
`argmin` is a thin version of that. This measures the obvious thicker version:

    take the k nearest, ask the verifier about each in order,
    start from the first one it admits, and fall back to nominal only
    when it admits none

Deterministic, no model involved. It is the substrate a selection agent would
need anyway -- you cannot rank candidates you never retrieved -- so it is worth
knowing what it is worth on its own first.

Measured on both circuits, because they answer different questions:

  * **base** -- the gate almost never refuses (1 case in 200), so this should be
    worth approximately nothing, and saying so is the point.
  * **fold** -- the gate refuses 69 in 200, *and* the starting guess selects
    which of three roots Newton finds. So a deeper candidate is not only a
    cheaper start, it is a different answer, and the two must be reported
    separately.

    python topk.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import fold
import model
import verifier
from bench import PRESSURE_IDX, SPEED_IDX, load_archive
from sweep import sample_cases

#: how deep to walk. 1 is today's behaviour and is included so every row of the
#: table is comparable against it rather than against a remembered number.
DEPTHS = (1, 2, 3, 5, 10, 25)


def resolve(p: dict, order: np.ndarray, dists: np.ndarray, records: list[dict],
            states: np.ndarray, v: verifier.Verifier, k: int) -> dict:
    """First gate-admitted candidate among the k nearest, else the nominal guess."""
    for rank in range(min(k, len(order))):
        j = int(order[rank])
        verdict = v.check_transfer(p, records[j], float(dists[j]))
        if verdict.admit:
            r = model.solve(p, x0=states[j])
            return {"source": "archive", "rank": rank + 1, "case": j,
                    "gate": verdict.rule, "iterations": r["iterations"],
                    "converged": r["converged"], "x": r["x"],
                    "admissible": bool(r["converged"] and
                                       verifier.Verifier.check_solution(r["x"], p).admit)}
    r = model.solve(p, x0=model.nominal_start(p))
    return {"source": "nominal", "rank": None, "case": None, "gate": "refused_all",
            "iterations": r["iterations"], "converged": r["converged"], "x": r["x"],
            "admissible": bool(r["converged"] and
                               verifier.Verifier.check_solution(r["x"], p).admit)}


def resolve_escalating(p: dict, order: np.ndarray, dists: np.ndarray,
                       records: list[dict], states: np.ndarray,
                       v: verifier.Verifier, k: int) -> dict:
    """The other way to spend k candidates, and the one that could actually win.

    `resolve` uses depth for *selection*: the first candidate gate 1 admits, and
    if its answer turns out inadmissible that is simply the answer. This uses
    depth for *escalation* instead -- when the converged answer is rejected by
    gate 2, try the next archived candidate before giving up on the archive.

    It is the policy `fold.guarded_transfer` implements with one candidate and a
    ladder of archive-free fallbacks; here the ladder starts inside the archive.
    Cost is counted across every attempt, because an escalation that needs four
    solves has spent four solves.
    """
    spent = 0
    for rank in range(min(k, len(order))):
        j = int(order[rank])
        if not v.check_transfer(p, records[j], float(dists[j])).admit:
            continue
        r = model.solve(p, x0=states[j])
        spent += r["iterations"]
        if r["converged"] and verifier.Verifier.check_solution(r["x"], p).admit:
            return {"source": "archive", "rank": rank + 1, "iterations": spent,
                    "converged": True, "x": r["x"], "admissible": True}
    r = model.solve(p, x0=model.nominal_start(p))
    spent += r["iterations"]
    ok = r["converged"] and verifier.Verifier.check_solution(r["x"], p).admit
    return {"source": "nominal", "rank": None, "iterations": spent,
            "converged": r["converged"], "x": r["x"], "admissible": bool(ok)}


def evaluate(records: list[dict], states: np.ndarray, norm: np.ndarray,
             queries: list[dict], label: str) -> dict:
    v = verifier.Verifier(records)
    rows, esc = [], []
    for p in queries:
        q = model.normalise(model.param_vector(p))
        d = np.linalg.norm(norm - q, axis=1)
        order = np.argsort(d)
        rows.append({k: resolve(p, order, d, records, states, v, k)
                     for k in DEPTHS})
        esc.append({k: resolve_escalating(p, order, d, records, states, v, k)
                    for k in DEPTHS})

    base = [r[1] for r in rows]
    out = {"circuit": label, "n_queries": len(rows), "depths": {}}
    for k in DEPTHS:
        got = [r[k] for r in rows]
        from_archive = [g for g in got if g["source"] == "archive"]
        # A deeper candidate is a different starting guess, so on a circuit with
        # more than one root it can be a different *answer*. Reported separately
        # from the cost, because a cheaper wrong answer is not an improvement.
        moved = 0
        for b, g in zip(base, got):
            if b["converged"] and g["converged"]:
                dx = np.abs(np.array(b["x"]) - np.array(g["x"]))
                if dx[PRESSURE_IDX].max() > 1e-3 or dx[SPEED_IDX].max() > 1e-1:
                    moved += 1
        out["depths"][k] = {
            "used_archive": len(from_archive),
            "fell_back_to_nominal": len(got) - len(from_archive),
            "deepest_rank_used": max((g["rank"] for g in from_archive), default=0),
            "total_iterations": int(sum(g["iterations"] for g in got
                                        if g["converged"])),
            "mean_iterations": float(np.mean([g["iterations"] for g in got
                                              if g["converged"]])),
            "not_converged": sum(1 for g in got if not g["converged"]),
            "inadmissible": sum(1 for g in got if g["converged"]
                                and not g["admissible"]),
            "answer_differs_from_k1": moved,
        }
    out["escalating"] = {
        k: {
            "used_archive": sum(1 for e in esc if e[k]["source"] == "archive"),
            "total_iterations": int(sum(e[k]["iterations"] for e in esc)),
            "mean_iterations": float(np.mean([e[k]["iterations"] for e in esc])),
            "inadmissible": sum(1 for e in esc if not e[k]["admissible"]),
        } for k in DEPTHS
    }
    return out


def base_circuit(archive_path: Path, n_query: int, seed: int) -> dict:
    records, norm, states = load_archive(archive_path)
    return evaluate(records, states, norm, sample_cases(n_query, seed), "base")


def fold_circuit(n_archive: int, n_query: int) -> dict:
    records, _rejected, stats = fold.sweep_fold(n_archive, seed=11)
    norm = model.normalise(
        np.array([[r["params"][k] for k in model.PARAM_NAMES] for r in records]))
    states = np.array([[r["solution"][k] for k in model.STATE_NAMES]
                       for r in records])
    out = evaluate(records, states, norm,
                   fold.fold_cases(n_query, seed=77), "fold")
    out["archive"] = stats
    return out


def report(payload: dict) -> None:
    for r in payload["results"]:
        print()
        print(f"--- {r['circuit']} circuit, {r['n_queries']} queries ---")
        print(f"{'k':>4}{'used archive':>14}{'-> nominal':>12}{'deepest':>9}"
              f"{'mean iters':>12}{'inadmissible':>14}{'answer moved':>14}")
        for k, d in r["depths"].items():
            print(f"{k:>4}{d['used_archive']:>14}{d['fell_back_to_nominal']:>12}"
                  f"{d['deepest_rank_used']:>9}{d['mean_iterations']:>12.2f}"
                  f"{d['inadmissible']:>14}{d['answer_differs_from_k1']:>14}")
        print(f"  escalating on a rejected answer instead of selecting on gate 1:")
        print(f"  {'k':>4}{'used archive':>14}{'mean iters':>12}{'inadmissible':>14}")
        for k, e in r["escalating"].items():
            print(f"  {k:>4}{e['used_archive']:>14}{e['mean_iterations']:>12.2f}"
                  f"{e['inadmissible']:>14}")


def run(out: Path, archive_path: Path, n_query: int, seed: int,
        n_fold_archive: int) -> dict:
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "depths": list(DEPTHS),
        "results": [base_circuit(archive_path, n_query, seed),
                    fold_circuit(n_fold_archive, n_query)],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=Path("archive/cases.jsonl"))
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--fold-archive", type=int, default=300)
    ap.add_argument("--out", type=Path, default=Path("topk_results.json"))
    args = ap.parse_args()
    report(run(args.out, args.archive, args.queries, args.seed,
               args.fold_archive))
    print()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
