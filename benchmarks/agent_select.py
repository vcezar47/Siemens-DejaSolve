"""Can anything rank the candidates better than distance can?

`experiments/topk.py` found that walking deeper into the archive **by distance** does not
pay. That is a statement about the ordering, not about depth — and this project
already knows distance is a weak signal: setup distance predicts transfer cost
at r = 0.18 (§6b). So the open question is whether a *better ordering* of the
same k candidates pays, and a selection agent is the obvious thing to try.

**The ceiling is measured before the model is.** Solving every candidate gives
the pick a perfect ranker would have made, which bounds what any ranker — a
model, a heuristic, anything — could possibly win. If the oracle barely beats
distance there is no headroom, the question is settled, and no result about a
particular model can change it. Running an hour of GPU to discover that would be
the wrong order of operations.

Three arms, and the third is the point:

  * **distance**  -- today's behaviour: nearest gate-admitted candidate.
  * **agent**     -- a local model reads the query and the k candidates, each as
    its setup parameters plus its *recorded regime* (relief valve open, and
    whether each shaft is stuck, on the Stribeck branch, or viscous), and picks
    one. Regime compatibility is exactly what the physics gate computes, so this
    asks whether a model can infer what the rules encode.
  * **oracle**    -- the best gate-admitted candidate, chosen by solving all of
    them. Not achievable; it is the bound.

The verifier keeps its veto in every arm. **The agent proposes, the verifier
disposes** — a model is never permitted to admit a transfer the physics rules
refuse, so the worst a bad ranking can do is cost iterations.

    python -m benchmarks.agent_select                 # the ceiling, no model, fast
    python -m benchmarks.agent_select --model granite4
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from benchmarks import fold
from dejasolve import ingest
from dejasolve import model
from dejasolve import verifier
from benchmarks.bench import load_archive
from dejasolve.sweep import sample_cases

#: how many candidates the ranker gets to choose between. Small on purpose: a
#: shortlist a human would look at, and a prompt that fits comfortably.
K = 5


def shortlist(p: dict, norm: np.ndarray, records: list[dict],
              v: verifier.Verifier, k: int) -> list[dict]:
    """The k nearest, each with the gate's verdict already attached.

    The gate runs first and its answer travels with the candidate, so no arm can
    quietly admit a transfer the physics rules refuse -- including the agent.
    """
    q = model.normalise(model.param_vector(p))
    d = np.linalg.norm(norm - q, axis=1)
    out = []
    for rank, j in enumerate(np.argsort(d)[:k]):
        j = int(j)
        verdict = v.check_transfer(p, records[j], float(d[j]))
        out.append({"rank": rank + 1, "index": j, "distance": float(d[j]),
                    "admitted": bool(verdict.admit), "gate": verdict.rule,
                    "params": records[j]["params"],
                    "regime": records[j]["regime"]})
    return out


def solve_from(p: dict, states: np.ndarray, j: int) -> dict:
    r = model.solve(p, x0=states[j])
    ok = r["converged"] and verifier.Verifier.check_solution(r["x"], p).admit
    return {"iterations": r["iterations"], "converged": r["converged"],
            "admissible": bool(ok), "x": r["x"]}


def nominal(p: dict) -> dict:
    r = model.solve(p, x0=model.nominal_start(p))
    ok = r["converged"] and verifier.Verifier.check_solution(r["x"], p).admit
    return {"iterations": r["iterations"], "converged": r["converged"],
            "admissible": bool(ok), "x": r["x"]}


def evaluate_ceiling(records: list[dict], states: np.ndarray, norm: np.ndarray,
                     queries: list[dict], label: str, k: int) -> dict:
    """Distance against the best possible pick. No model involved."""
    v = verifier.Verifier(records)
    rows = []
    for p in queries:
        cands = shortlist(p, norm, records, v, k)
        admitted = [c for c in cands if c["admitted"]]
        if not admitted:
            nom = nominal(p)
            rows.append({"any_admitted": False, "distance": nom, "oracle": nom,
                         "distance_rank": None, "oracle_rank": None,
                         "shortlist": cands})
            continue
        solved = {c["rank"]: solve_from(p, states, c["index"]) for c in admitted}
        # the oracle prefers a *valid* answer first and a cheap one second: a
        # faster route to an inadmissible root is not a better pick
        best = min(solved, key=lambda r: (not solved[r]["admissible"],
                                          solved[r]["iterations"]))
        rows.append({"any_admitted": True,
                     "distance": solved[admitted[0]["rank"]],
                     "oracle": solved[best],
                     "distance_rank": admitted[0]["rank"], "oracle_rank": best,
                     "shortlist": cands})

    def arm(key: str) -> dict:
        got = [r[key] for r in rows]
        return {"mean_iterations": float(np.mean([g["iterations"] for g in got])),
                "total_iterations": int(sum(g["iterations"] for g in got)),
                "inadmissible": sum(1 for g in got if not g["admissible"])}

    same = sum(1 for r in rows
               if r["any_admitted"] and r["distance_rank"] == r["oracle_rank"])
    n_adm = sum(1 for r in rows if r["any_admitted"])
    return {
        "circuit": label, "k": k, "n_queries": len(rows),
        "queries_with_an_admitted_candidate": n_adm,
        "distance_already_optimal": same,
        "headroom_iterations": arm("distance")["total_iterations"]
                               - arm("oracle")["total_iterations"],
        "arms": {"distance": arm("distance"), "oracle": arm("oracle")},
        "rows": rows,
    }


def base_circuit(archive_path: Path, n_query: int, seed: int, k: int) -> dict:
    records, norm, states = load_archive(archive_path)
    return evaluate_ceiling(records, states, norm,
                            sample_cases(n_query, seed), "base", k)


def fold_circuit(n_archive: int, n_query: int, k: int) -> dict:
    records, _rej, stats = fold.sweep_fold(n_archive, seed=11)
    norm = model.normalise(
        np.array([[r["params"][kk] for kk in model.PARAM_NAMES] for r in records]))
    states = np.array([[r["solution"][kk] for kk in model.STATE_NAMES]
                       for r in records])
    out = evaluate_ceiling(records, states, norm,
                           fold.fold_cases(n_query, seed=77), "fold", k)
    out["archive"] = stats
    return out


def random_floor(result: dict, states: np.ndarray, queries: list[dict],
                 seed: int = 3) -> dict:
    """Pick uniformly among the admitted candidates. The floor, not a baseline.

    Without it, "the agent scored between distance and oracle" is unreadable:
    a ranker that contributes nothing at all still lands somewhere on that
    scale. This says where *nothing* lands, so the model's number can be
    compared against having no opinion rather than only against having the best
    possible one.
    """
    rng = np.random.default_rng(seed)
    picked = []
    for row, p in zip(result["rows"], queries):
        if not row["any_admitted"]:
            picked.append(row["distance"])
            continue
        adm = [c for c in row["shortlist"] if c["admitted"]]
        j = adm[int(rng.integers(len(adm)))]["index"]
        picked.append(solve_from(p, states, j))
    return {"total_iterations": int(sum(g["iterations"] for g in picked)),
            "mean_iterations": float(np.mean([g["iterations"] for g in picked])),
            "inadmissible": sum(1 for g in picked if not g["admissible"])}


def sensitivity_arms(result: dict, states: np.ndarray, queries: list[dict],
                     records: list[dict]) -> dict:
    """The two arms that use what the archived card knows about its own slope.

    Every arm above transfers the chosen state **verbatim**, which is why they
    all land on top of each other: they differ only in *which* answer to copy,
    and copying is the part that costs the iterations. That makes this file's
    original conclusion -- "nothing beats distance" -- true of the arms it had
    and false in general, so the arms that break it belong here rather than in
    a footnote somewhere else.

    Reported as two arms because they are two separate claims:

      * **first_order** -- distance picks the candidate, exactly as today, and
        only the *transfer* changes. Isolates what the tangent alone is worth.
      * **sensitivity** -- the tangent also does the *ranking*, by predicted
        start error. Isolates what it is worth as a ranking signal, on top.

    The second is the one that matters for this file's question. Distance asks
    "how different is this case?"; predicted start error asks "how far will
    this card's answer actually move over that difference" -- which is the
    question the ranking was always a proxy for. A card sitting right at its
    relief valve's cracking point moves a great deal over a small parameter
    step; a card far from it barely moves at all. Distance cannot see that.
    """
    def transferred(p: dict, j: int) -> dict:
        s = records[j].get("sensitivity")
        r = model.solve(p, x0=model.transfer_start(
            states[j], None if s is None else np.asarray(s, dtype=float),
            records[j]["params"], p))
        ok = r["converged"] and verifier.Verifier.check_solution(r["x"], p).admit
        return {"iterations": r["iterations"], "converged": r["converged"],
                "admissible": bool(ok), "x": r["x"]}

    def score(c: dict, p: dict) -> float:
        s = records[c["index"]].get("sensitivity")
        return model.predicted_start_error(
            None if s is None else np.asarray(s, dtype=float),
            records[c["index"]]["params"], p)

    picks: dict[str, list] = {"first_order": [], "sensitivity": []}
    chose_nearest = 0
    for row, p in zip(result["rows"], queries):
        if not row["any_admitted"]:
            picks["first_order"].append(row["distance"])
            picks["sensitivity"].append(row["distance"])
            continue
        adm = [c for c in row["shortlist"] if c["admitted"]]
        picks["first_order"].append(transferred(p, adm[0]["index"]))
        best = min(adm, key=lambda c: score(c, p))
        chose_nearest += int(best["index"] == adm[0]["index"])
        picks["sensitivity"].append(transferred(p, best["index"]))

    out = {name: {
        "total_iterations": int(sum(g["iterations"] for g in got)),
        "mean_iterations": float(np.mean([g["iterations"] for g in got])),
        "inadmissible": sum(1 for g in got if not g["admissible"]),
    } for name, got in picks.items()}
    out["sensitivity"]["agreed_with_distance"] = chose_nearest
    return out


def physics_rank(result: dict, states: np.ndarray, queries: list[dict]) -> dict:
    """Rank the admitted candidates by *estimated regime match*, not by distance.

    The obvious remaining candidate, and the project's own thesis applied one
    layer up. `verifier.estimate_regime` already predicts, in closed form and
    without solving, whether this query's shafts can break away and whether its
    relief valve must open. Every archived case *records* the regime it actually
    settled into. So rank by agreement between the two and break ties on
    distance.

    Costs no solve and no model: it is the same arithmetic the gate already does
    to decide admission, reused to decide order.
    """
    picked = []
    for row, p in zip(result["rows"], queries):
        if not row["any_admitted"]:
            picked.append(row["distance"])
            continue
        est = verifier.estimate_regime(p)
        adm = [c for c in row["shortlist"] if c["admitted"]]

        def score(c: dict) -> tuple:
            reg = c["regime"]
            agree = 0
            for shaft in ("a", "b"):
                spinning = reg.get(f"shaft_{shaft}") != "stuck"
                agree += int(spinning == est["can_break_away"])
            agree += int(bool(reg.get("relief_open")) == est["relief_must_open"])
            return (-agree, c["distance"])      # most agreement, then nearest

        best = min(adm, key=score)
        picked.append(solve_from(p, states, best["index"]))
    return {"total_iterations": int(sum(g["iterations"] for g in picked)),
            "mean_iterations": float(np.mean([g["iterations"] for g in picked])),
            "inadmissible": sum(1 for g in picked if not g["admissible"])}


def report_ceiling(payload: dict) -> None:
    for r in payload["results"]:
        a = r["arms"]
        print()
        print(f"--- {r['circuit']} circuit, {r['n_queries']} queries, k={r['k']} ---")
        print(f"  queries with any admitted candidate : "
              f"{r['queries_with_an_admitted_candidate']}")
        print(f"  distance already picked the best    : "
              f"{r['distance_already_optimal']} / "
              f"{r['queries_with_an_admitted_candidate']}")
        print(f"  {'arm':<10}{'mean iters':>12}{'total':>9}{'inadmissible':>14}")
        for name in ("distance", "oracle"):
            print(f"  {name:<10}{a[name]['mean_iterations']:>12.2f}"
                  f"{a[name]['total_iterations']:>9}{a[name]['inadmissible']:>14}")
        if "physics" in r:
            ph = r["physics"]
            print(f"  {'physics':<10}{ph['mean_iterations']:>12.2f}"
                  f"{ph['total_iterations']:>9}{ph['inadmissible']:>14}"
                  f"   <- ranked by estimated regime")
        if "random" in r:
            rr = r["random"]
            print(f"  {'random':<10}{rr['mean_iterations']:>12.2f}"
                  f"{rr['total_iterations']:>9}{rr['inadmissible']:>14}"
                  f"   <- picking with no opinion")
        pct = (100.0 * r["headroom_iterations"]
               / max(a["distance"]["total_iterations"], 1))
        print(f"  headroom for ANY ranker             : "
              f"{r['headroom_iterations']} iterations ({pct:.1f}%)")

        # Printed under the headroom line on purpose: these two arms are not
        # inside it. The ceiling above is the ceiling on *choosing* among
        # verbatim transfers, and these change what a transfer is, so they are
        # allowed to sit below a bound that was never about them.
        if "sensitivity_arms" in r:
            sa = r["sensitivity_arms"]
            print(f"\n  the bound above is on picking a state to copy. "
                  f"Not copying it:")
            print(f"  {'arm':<14}{'mean iters':>12}{'total':>9}{'inadmissible':>14}")
            print(f"  {'first_order':<14}{sa['first_order']['mean_iterations']:>12.2f}"
                  f"{sa['first_order']['total_iterations']:>9}"
                  f"{sa['first_order']['inadmissible']:>14}"
                  f"   <- distance picks, tangent transfers")
            se = sa["sensitivity"]
            print(f"  {'sensitivity':<14}{se['mean_iterations']:>12.2f}"
                  f"{se['total_iterations']:>9}{se['inadmissible']:>14}"
                  f"   <- tangent also ranks")
            print(f"  ranked the nearest candidate first in "
                  f"{se['agreed_with_distance']}/"
                  f"{r['queries_with_an_admitted_candidate']} queries")


# --- the model arm ----------------------------------------------------------

#: Deliberately terse. A 3.4B model given a wall of prose picks the first option
#: every time; the structure is what makes the choice possible at all.
PROMPT = """You choose which past simulation to reuse as the starting guess for a new one.

The circuit is a hydraulic manifold: a pump feeds two branches through metering
valves, each driving a motor against a quadratic load through Stribeck friction.
A past run is a good starting point when it settles into the SAME REGIME as the
new case -- the same shafts turning or stuck, the relief valve open or shut.

NEW CASE (not yet solved, so its regime is unknown):
{query}

CANDIDATES, each already solved, with the regime it settled into:
{candidates}

Which candidate's regime is the new case most likely to share?
Answer with one number from 1 to {k} and nothing else."""


def _fmt_params(p: dict) -> str:
    return "  " + "  ".join(f"{k}={p[k]:.4g}" for k in model.PARAM_NAMES)


def _fmt_regime(r: dict) -> str:
    return (f"  relief valve {'OPEN' if r.get('relief_open') else 'shut'}"
            f", shaft a {r.get('shaft_a', '?')}"
            f", shaft b {r.get('shaft_b', '?')}")


def build_prompt(p: dict, admitted: list[dict]) -> str:
    lines = []
    for n, c in enumerate(admitted, 1):
        lines.append(f"[{n}]\n{_fmt_params(c['params'])}\n{_fmt_regime(c['regime'])}")
    return PROMPT.format(query=_fmt_params(p), candidates="\n".join(lines),
                         k=len(admitted))


def ask_model(prompt: str, name: str, timeout: int = 180) -> tuple[int | None, str]:
    """One ranking call. Returns (1-based choice or None, raw reply).

    Temperature 0 and a fixed seed: a ranking that changes between runs is not a
    result, and the whole point of the arm is to be compared against a
    deterministic baseline.
    """
    import urllib.error
    import urllib.request

    body = json.dumps({
        "model": name, "prompt": prompt, "stream": False,
        "options": {"temperature": 0.0, "seed": 7, "num_predict": 8},
    }).encode()
    req = urllib.request.Request(f"{ingest.OLLAMA_URL}/api/generate", body,
                                 {"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = json.load(r).get("response", "")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return None, f"<error: {exc}>"
    m = re.search(r"\d+", raw)
    return (int(m.group()) if m else None), raw.strip()


def run_agent_arm(result: dict, states: np.ndarray, queries: list[dict],
                  name: str, limit: int | None) -> dict:
    """Let the model pick among the *admitted* candidates, and score the pick.

    It only ever sees candidates the gate already admitted, so the model cannot
    authorise a transfer the physics rules refuse. The worst a bad ranking costs
    is iterations -- which is the entire safety argument for putting a model
    here at all.
    """
    rows = result["rows"]
    n = len(rows) if limit is None else min(limit, len(rows))
    picked, parse_fail, same_as_distance = [], 0, 0

    for i in range(n):
        row, p = rows[i], queries[i]
        if not row["any_admitted"]:
            picked.append(row["distance"])
            continue
        admitted = [c for c in row["shortlist"] if c["admitted"]]
        choice, _raw = ask_model(build_prompt(p, admitted), name)
        if choice is None or not (1 <= choice <= len(admitted)):
            parse_fail += 1
            choice = 1                      # fall back to the distance ordering
        if admitted[choice - 1]["rank"] == row["distance_rank"]:
            same_as_distance += 1
        picked.append(solve_from(p, states, admitted[choice - 1]["index"]))

    return {
        "model": name, "n_scored": n, "parse_failures": parse_fail,
        "agreed_with_distance": same_as_distance,
        "mean_iterations": float(np.mean([g["iterations"] for g in picked])),
        "total_iterations": int(sum(g["iterations"] for g in picked)),
        "inadmissible": sum(1 for g in picked if not g["admissible"]),
        # the two references over the same subset, so the comparison is exact
        "distance_total": int(sum(r["distance"]["iterations"] for r in rows[:n])),
        "oracle_total": int(sum(r["oracle"]["iterations"] for r in rows[:n])),
        "distance_inadmissible": sum(1 for r in rows[:n]
                                     if not r["distance"]["admissible"]),
        "oracle_inadmissible": sum(1 for r in rows[:n]
                                   if not r["oracle"]["admissible"]),
    }


def report_agent(rows: list[dict]) -> None:
    for a in rows:
        span = max(a["distance_total"] - a["oracle_total"], 1)
        won = a["distance_total"] - a["total_iterations"]
        print()
        print(f"--- {a['circuit']}: {a['model']} over {a['n_scored']} queries ---")
        print(f"  {'arm':<10}{'total iters':>13}{'inadmissible':>14}")
        print(f"  {'distance':<10}{a['distance_total']:>13}"
              f"{a['distance_inadmissible']:>14}")
        print(f"  {'agent':<10}{a['total_iterations']:>13}{a['inadmissible']:>14}")
        print(f"  {'oracle':<10}{a['oracle_total']:>13}{a['oracle_inadmissible']:>14}")
        print(f"  agreed with distance : {a['agreed_with_distance']}/{a['n_scored']}"
              f"   parse failures: {a['parse_failures']}")
        print(f"  captured {100.0 * won / span:.0f}% of the available headroom")

def run_deterministic(archive_path: Path, n_query: int, seed: int,
                      n_fold_archive: int, k: int, out: Path | None) -> dict:
    """Ceiling, floor and the physics ranker. No model, no GPU, reproducible.

    Split out so `run_all.py` can regenerate the deterministic part while the
    model arm stays opt-in: an inference run is minutes of GPU and its result
    depends on which models happen to be pulled, neither of which belongs in a
    reproducer that has to work on a clean machine.
    """
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "k": k,
        "results": [base_circuit(archive_path, n_query, seed, k),
                    fold_circuit(n_fold_archive, n_query, k)],
    }
    qs = {"base": sample_cases(n_query, seed),
          "fold": fold.fold_cases(n_query, seed=77)}
    base_records, _bn, base_states = load_archive(archive_path)
    st = {"base": base_states}
    recs, _rej, _stats = fold.sweep_fold(n_fold_archive, seed=11)
    st["fold"] = np.array([[r["solution"][kk] for kk in model.STATE_NAMES]
                           for r in recs])
    rc = {"base": base_records, "fold": recs}
    for r in payload["results"]:
        c = r["circuit"]
        r["random"] = random_floor(r, st[c], qs[c])
        r["physics"] = physics_rank(r, st[c], qs[c])
        r["sensitivity_arms"] = sensitivity_arms(r, st[c], qs[c], rc[c])

    if out is not None:
        # the per-query shortlists are what the model arm consumes; they are
        # large, so they stay out of the summary file
        slim = json.loads(json.dumps(payload))
        for r in slim["results"]:
            r.pop("rows", None)
        out.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=Path("data/archive/cases.jsonl"))
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--seed", type=int, default=99)
    ap.add_argument("--fold-archive", type=int, default=300)
    ap.add_argument("-k", type=int, default=K)
    ap.add_argument("--out", type=Path, default=Path("results/agent_select_results.json"))
    ap.add_argument("--model", default=None,
                    help="run the model arm too, e.g. granite4 or qwen2.5:7b")
    ap.add_argument("--limit", type=int, default=None,
                    help="score only the first N queries -- for the slow model")
    ap.add_argument("--model-out", type=Path,
                    default=Path("results/agent_model_results.json"))
    args = ap.parse_args()

    payload = run_deterministic(args.archive, args.queries, args.seed,
                                args.fold_archive, args.k, args.out)
    report_ceiling(payload)

    agent_rows = []
    if args.model:
        qs = {"base": sample_cases(args.queries, args.seed),
              "fold": fold.fold_cases(args.queries, seed=77)}
        st = {"base": load_archive(args.archive)[2]}
        _fr, _rej, _stats = fold.sweep_fold(args.fold_archive, seed=11)
        st["fold"] = np.array([[r["solution"][k] for k in model.STATE_NAMES]
                               for r in _fr])
        for r in payload["results"]:
            a = run_agent_arm(r, st[r["circuit"]], qs[r["circuit"]],
                              args.model, args.limit)
            a["circuit"] = r["circuit"]
            agent_rows.append(a)
        report_agent(agent_rows)

    if agent_rows:
        # Its own file, because `run_all.py` regenerates the deterministic arms
        # and would otherwise erase a model run that costs minutes of GPU and
        # cannot be reproduced on a machine without the model pulled.
        args.model_out.write_text(json.dumps({
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": args.model, "k": args.k, "arms": agent_rows,
        }, indent=2), encoding="utf-8")
        print(f"wrote {args.model_out}")
    print()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
