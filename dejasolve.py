"""End to end: a messy run artifact in, a verified warm-started solve out.

This is the whole system in one path, and the order matters -- each layer is
allowed to stop the run:

    artifact -> Case Card -> unit sanity -> retrieval -> verifier
             -> warm solve -> admissibility check -> report

It refuses in three distinct ways, and saying which one fired is the point:

  * **incomplete** -- the artifact never stated a parameter. The nearest
    archived case is shown as a *suggestion*, never applied. Auto-filling a
    missing parameter from a neighbour is precisely the silent wrongness the
    rest of the system exists to prevent.
  * **implausible** -- a value survives ingest but is orders of magnitude out,
    which in practice means a unit was misread.
  * **inadmissible transfer** -- retrieval found a case, and the verifier
    refused it.

``analyse()`` is pure: it returns a structured trace and prints nothing, so the
CLI renderer and the HTTP service in ``app.py`` share one implementation instead
of drifting apart.

    python dejasolve.py logs/note-ro.txt
    python dejasolve.py --all
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import model
import verifier
from casecard import CANONICAL_UNITS, CaseCard
import ingest
from ingest import ingest_text

#: plain ASCII on purpose -- the Windows console is cp1252 and box-drawing
#: characters raise UnicodeEncodeError there, which would break the demo
RULE = "-" * 78

#: the five pipeline stages, in order, as the UI and the CLI both present them
STAGES = [
    ("ingest", "Ingest", "artifact -> Case Card"),
    ("plausible", "Units", "physically plausible?"),
    ("retrieve", "Retrieve", "nearest solved case"),
    ("verify", "Verify", "is this transfer legitimate?"),
    ("solve", "Solve", "warm-started initialisation"),
    ("admissible", "Admissible", "is the answer an operating point?"),
]


class Archive:
    """The archive plus the verifier built from it, loaded once."""

    def __init__(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"no archive at {path} -- run `python sweep.py`")
        self.records = [json.loads(l) for l
                        in path.read_text(encoding="utf-8").splitlines() if l]
        params = np.array([[r["params"][k] for k in model.PARAM_NAMES]
                           for r in self.records])
        self.norm = model.normalise(params)
        self.states = np.array([[r["solution"][k] for k in model.STATE_NAMES]
                                for r in self.records])
        self.verifier = verifier.Verifier(self.records)

    def nearest(self, params: dict) -> tuple[int, float]:
        q = model.normalise(model.param_vector(params))
        d = np.linalg.norm(self.norm - q, axis=1)
        j = int(np.argmin(d))
        return j, float(d[j])

    def nearest_on(self, card: CaseCard, fields: list[str]) -> tuple[int, float]:
        """Nearest case using only `fields`, so an incomplete card can still be
        located approximately -- for suggestion purposes only."""
        idx = [model.PARAM_NAMES.index(f) for f in fields]
        lo = np.array([model.PARAM_BOUNDS[k][0] for k in model.PARAM_NAMES])[idx]
        hi = np.array([model.PARAM_BOUNDS[k][1] for k in model.PARAM_NAMES])[idx]
        q = (np.array([card.params[f] for f in fields]) - lo) / (hi - lo)
        d = np.linalg.norm(self.norm[:, idx] - q, axis=1)
        j = int(np.argmin(d))
        return j, float(d[j])


def _stage(sid: str, state: str, headline: str, detail=None) -> dict:
    """state is one of: ok | refused | skipped"""
    title, subtitle = next((t, s) for i, t, s in STAGES if i == sid)
    return {"id": sid, "title": title, "subtitle": subtitle,
            "state": state, "headline": headline, "detail": detail or {}}


def analyse(text: str, name: str, archive: Archive,
            backend: str = "auto") -> dict:
    """Run the full pipeline over one artifact. Pure -- returns a trace."""
    stages: list[dict] = []
    trace = {"artifact": name, "stages": stages, "backend": backend}

    # -- Layer 1: ingest ---------------------------------------------------
    # An unavailable backend is a refusal like any other, not a crash: it gets
    # a stage in the pipeline with a reason the operator can act on, in the same
    # visual language as every other refusal.
    try:
        card = ingest_text(text, name, backend=backend)
    except RuntimeError as exc:
        stages.append(_stage("ingest", "refused", str(exc),
                             {"backend": backend}))
        for sid in ("plausible", "retrieve", "verify", "solve", "admissible"):
            stages.append(_stage(sid, "skipped", "not reached"))
        trace.update(outcome="ingest_unavailable", summary=str(exc),
                     fields=[], card={})
        return trace
    trace["card"] = card.to_dict()
    trace["fields"] = [
        {"name": f, "unit": CANONICAL_UNITS[f],
         "value": card.params.get(f), "raw": card.provenance.get(f, "")}
        for f in model.PARAM_NAMES
    ]
    found = len(card.params)
    stages.append(_stage(
        "ingest", "ok" if found else "refused",
        f"{found} of {len(model.PARAM_NAMES)} parameters read"
        f" by {card.source.get('ingested_by', '?')}",
        {"missing": card.missing, "notes": card.notes}))

    # -- unit sanity -------------------------------------------------------
    problems = card.validate()
    if problems:
        stages.append(_stage("plausible", "refused", problems[0],
                             {"problems": problems}))
        trace["outcome"] = "refused_implausible"
        trace["summary"] = problems[0]
        return trace
    stages.append(_stage("plausible", "ok" if found else "skipped",
                         f"all {found} values are within a physical range" if found
                         else "nothing to check"))

    # -- incomplete: locate, suggest, never apply --------------------------
    if not card.complete:
        known = [f for f in model.PARAM_NAMES if f in card.params]
        suggestion = None
        if known:
            j, dist = archive.nearest_on(card, known)
            nb = archive.records[j]
            suggestion = {
                "case_id": nb["case_id"], "distance": dist,
                "on_fields": len(known),
                "values": {f: nb["params"][f] for f in card.missing},
            }
        # "not read" rather than "not stated": ingest cannot tell a value that is
        # absent from one it failed to parse, and on the English email it is the
        # second -- the areas are there in prose and the model walks past them.
        # The refusal is right either way; only the stronger claim is unsupported.
        stages.append(_stage(
            "retrieve", "refused",
            f"not read from the artifact: {', '.join(card.missing)}",
            {"suggestion": suggestion,
             "note": "A missing parameter is a question for the engineer, not a "
                     "value to borrow -- that is how a wrong answer gets in."}))
        for sid in ("verify", "solve", "admissible"):
            stages.append(_stage(sid, "skipped", "not reached"))
        trace["outcome"] = "refused_incomplete"
        trace["summary"] = f"missing {', '.join(card.missing)}"
        return trace

    # -- Layer 2: retrieval ------------------------------------------------
    j, distance = archive.nearest(card.params)
    source = archive.records[j]
    trace["retrieval"] = {
        "case_id": source["case_id"], "distance": distance,
        "coverage_radius": archive.verifier.coverage_radius,
        "regime": source["regime"], "params": source["params"],
    }
    stages.append(_stage(
        "retrieve", "ok",
        f"{source['case_id']} at distance {distance:.3f}",
        {"coverage_radius": archive.verifier.coverage_radius,
         "regime": source["regime"]}))

    # -- Layer 3a: is the transfer legitimate? -----------------------------
    verdict = archive.verifier.check_transfer(card.params, source, distance)
    trace["verdict"] = {"admit": verdict.admit, "rule": verdict.rule,
                        "reason": verdict.reason}
    stages.append(_stage("verify", "ok" if verdict.admit else "refused",
                         verdict.reason, {"rule": verdict.rule}))

    cold = model.solve(card.params)
    if verdict.admit:
        warm = model.solve(card.params, x0=archive.states[j])
        chosen, label = warm, "warm"
    else:
        warm, chosen, label = None, cold, "cold"

    solve = {"cold_iterations": cold["iterations"],
             "cold_status": cold["status"], "start": label}
    if warm is not None:
        solve.update(warm_iterations=warm["iterations"],
                     warm_status=warm["status"])
        if cold["converged"] and warm["converged"]:
            dx = np.abs(np.array(cold["x"]) - np.array(warm["x"]))
            solve["agreement"] = float(dx.max())
            solve["saved"] = cold["iterations"] - warm["iterations"]
    trace["solve"] = solve

    if not chosen["converged"]:
        stages.append(_stage("solve", "refused",
                             f"{label} start did not converge ({chosen['status']})"))
        stages.append(_stage("admissible", "skipped", "not reached"))
        trace["outcome"] = "no_answer"
        trace["summary"] = f"{label} start did not converge"
        return trace

    if warm is not None and "saved" in solve:
        headline = (f"{solve['cold_iterations']} -> {solve['warm_iterations']} "
                    f"iterations, same answer to {solve['agreement']:.1e}")
    else:
        headline = f"cold start, {cold['iterations']} iterations"
    stages.append(_stage("solve", "ok", headline, solve))

    # -- Layer 3b: is the answer an operating point? -----------------------
    admissible = verifier.Verifier.check_solution(chosen["x"], card.params)
    stages.append(_stage("admissible", "ok" if admissible.admit else "refused",
                         admissible.reason, {"rule": admissible.rule}))

    reg = model.regime(chosen["x"], card.params)
    trace["regime"] = reg
    trace["solution"] = [
        {"name": n, "unit": u, "value": float(v)}
        for n, u, v in zip(model.STATE_NAMES, model.STATE_UNITS, chosen["x"])
    ]
    if not admissible.admit:
        trace["outcome"] = "inadmissible_solution"
        trace["summary"] = admissible.reason
        return trace

    trace["outcome"] = "warm_started" if verdict.admit else "refused_transfer"
    trace["summary"] = headline
    return trace


# --- CLI rendering ----------------------------------------------------------

def render(trace: dict) -> str:
    out = [RULE, f"ARTIFACT  {trace['artifact']}", RULE]
    for f in trace["fields"]:
        if f["value"] is None:
            out.append(f"  {f['name']:11} {'MISSING':>12}")
        else:
            raw = f"   <- {f['raw']!r}" if f["raw"] else ""
            out.append(f"  {f['name']:11} {f['value']:>12.6g} "
                       f"{f['unit']:<16}{raw}")
    for st in trace["stages"]:
        if st["state"] == "skipped":
            continue
        mark = {"ok": "OK    ", "refused": "REFUSE"}[st["state"]]
        out.append(f"\n{mark} {st['title']:<12} {st['headline']}")
        sug = st["detail"].get("suggestion")
        if sug:
            out.append(f"       Closest archived case on the {sug['on_fields']} stated "
                       f"parameters is {sug['case_id']} ({sug['distance']:.2f} away):")
            for k, v in sug["values"].items():
                out.append(f"         {k} = {v:.6g} {CANONICAL_UNITS[k]}")
            out.append(f"       {st['detail']['note']}")
    if trace.get("solution"):
        out.append("")
        for s in trace["solution"]:
            out.append(f"  {s['name']:<8}{s['value']:>12.2f}   {s['unit']}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", nargs="?", type=Path)
    ap.add_argument("--all", action="store_true", help="run every fixture in logs/")
    ap.add_argument("--logs", type=Path, default=Path("logs"))
    ap.add_argument("--archive", type=Path, default=Path("archive/cases.jsonl"))
    ap.add_argument("--backend", default="auto", choices=list(ingest.BACKENDS))
    ap.add_argument("--json", action="store_true", help="emit the trace as JSON")
    args = ap.parse_args()

    try:
        archive = Archive(args.archive)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc))

    targets = (sorted(p for p in args.logs.iterdir() if p.suffix in (".log", ".txt"))
               if args.all else [args.artifact])
    if not targets or targets == [None]:
        ap.error("give an artifact path, or pass --all")

    traces = [analyse(p.read_text(encoding="utf-8"), p.name, archive, args.backend)
              for p in targets]

    if args.json:
        print(json.dumps(traces if args.all else traces[0], indent=2))
        return

    for t in traces:
        print(render(t))
        print()

    if args.all:
        print(RULE)
        print("SUMMARY")
        for t in traces:
            print(f"  {t['artifact']:22} {t['outcome']:<22} {t['summary']}")


if __name__ == "__main__":
    main()
