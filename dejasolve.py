"""End to end: a messy run artifact in, a verified warm-started solve out.

This is the whole system in one path, and the order matters -- each layer is
allowed to stop the run:

    artifact -> Case Card -> unit sanity -> retrieval -> verifier
             -> warm solve -> admissibility check -> report

Nothing here ends in a bare refusal. Asked whether the system should refuse
when unsure or warn and let them decide, the two engineers interviewed on
19 Aug chose the second: *generate a report and give out a warning, and leave
it up to the engineer to proceed with the simulation or not.* So every path
produces a ``report`` -- and stopping comes in two tiers, because "warn about
everything" is its own kind of useless:

  * **warned** -- a *risk*. The verifier estimated, before any solve, that this
    transfer is not legitimate. It says why, does not use the archive, and
    offers an override: the engineer may accept the risk and warm-start anyway,
    which is recorded in the audit trail with their name and their reason.
  * **blocked** -- a *fact*, where there is nothing for an engineer to decide:
      - **incomplete** -- the artifact never stated a parameter. The nearest
        archived case is shown as a *suggestion*, never applied. Auto-filling a
        missing parameter from a neighbour is precisely the silent wrongness
        the rest of the system exists to prevent.
      - **implausible** -- a value survives ingest but is orders of magnitude
        out, which in practice means a unit was misread.
      - **inadmissible** -- the converged root is not an operating point. This
        one is measured after the solve, not estimated before it.

The line is *the engineer decides what to do with a risk; the system decides
what is a fact*, and it falls exactly where the verifier's two gates already
sat. See ``verifier.py``.

Simulation is a departmental activity, not one engineer's -- so an override is
attributed. ``operator`` and ``basis`` travel with the request and land in
``trace["audit"]``.

``analyse()`` is pure: it returns a structured trace and prints nothing, so the
CLI renderer and the HTTP service in ``app.py`` share one implementation instead
of drifting apart.

    python dejasolve.py logs/note-ro.txt
    python dejasolve.py --all
"""

from __future__ import annotations

import argparse
import getpass
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import model
import verifier
import casecard
from casecard import CANONICAL_UNITS, CaseCard
import ingest
from ingest import ingest_text

#: plain ASCII on purpose -- the Windows console is cp1252 and box-drawing
#: characters raise UnicodeEncodeError there, which would break the demo
RULE = "-" * 78

#: what counts as a run artifact. `.dat` is here because a Simcenter 3D
#: export is a Nastran deck, and the demo has to be able to feed the
#: pipeline one in order to show it being refused.
ARTIFACT_SUFFIXES = (".log", ".txt", ".dat", ".bdf")

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
    """The archive plus the verifier built from it, loaded once.

    Two files, because a run that failed has no converged state to hand over and
    a record without one would be a landmine in every consumer of `records`. The
    failures are loaded anyway: they are half of what the archive knows, and an
    engineer asked for them to be kept (§0b). Nothing in the warm-start path
    reads them -- `failure_zone.py` measured whether proximity to a failure
    predicts a bad *transfer* and it barely does, so they are reported as
    context and never used as a gate.
    """

    def __init__(self, path: Path):
        if not path.exists():
            raise FileNotFoundError(f"no archive at {path} -- run `python sweep.py`")
        self.records = [json.loads(l) for l
                        in path.read_text(encoding="utf-8").splitlines() if l]
        fail_path = path.with_name("failures.jsonl")
        self.failures = ([json.loads(l) for l
                          in fail_path.read_text(encoding="utf-8").splitlines() if l]
                         if fail_path.exists() else [])
        self.failure_modes: dict[str, int] = {}
        for f in self.failures:
            self.failure_modes[f["status"]] = self.failure_modes.get(f["status"], 0) + 1
        self.failure_norm = (model.normalise(
            np.array([[f["params"][k] for k in model.PARAM_NAMES]
                      for f in self.failures])) if self.failures else None)
        params = np.array([[r["params"][k] for k in model.PARAM_NAMES]
                           for r in self.records])
        self.norm = model.normalise(params)
        self.states = np.array([[r["solution"][k] for k in model.STATE_NAMES]
                                for r in self.records])
        #: dx*/dp per card, when the sweep recorded one. `None` for a singular
        #: Jacobian, and `None` for every card in an archive written before
        #: sensitivities existed -- `model.transfer_start` degrades to the
        #: verbatim state in both cases, so an old archive still works.
        self.sensitivity = [
            None if r.get("sensitivity") is None
            else np.asarray(r["sensitivity"], dtype=float) for r in self.records]
        self.verifier = verifier.Verifier(self.records)
        #: what kind of model this archive holds. Every record in it came
        #: through the same Case Card schema, so the archive inherits its
        #: domain -- and a query from a different one has nothing to retrieve.
        self.domain = casecard.DOMAIN

    def nearest(self, params: dict) -> tuple[int, float]:
        q = model.normalise(model.param_vector(params))
        d = np.linalg.norm(self.norm - q, axis=1)
        j = int(np.argmin(d))
        return j, float(d[j])

    def warm_start(self, j: int, params: dict) -> tuple[np.ndarray, bool]:
        """The start to hand Newton for query `params`, from archive case `j`.

        First-order when the card carries a tangent, verbatim when it does not.
        Returns the flag too, because the report says which one it used -- a
        demo that quietly switches transfer order is the failure mode this
        project is about.
        """
        s = self.sensitivity[j]
        x0 = model.transfer_start(self.states[j], s, self.records[j]["params"],
                                  params)
        return x0, s is not None

    def nearest_failure(self, params: dict) -> dict | None:
        """The closest run that *died*, as context -- never as a decision.

        Reported because an engineer asked to see the failed runs, and stated as
        two distances rather than as a prediction: on this circuit there are 5
        failures in 400 and `failure_zone.py` calls that underpowered. A
        confident-sounding warning built on five data points would be exactly
        the kind of thing the rest of this system exists to refuse.
        """
        if self.failure_norm is None:
            return None
        q = model.normalise(model.param_vector(params))
        d = np.linalg.norm(self.failure_norm - q, axis=1)
        j = int(np.argmin(d))
        return {"case_id": self.failures[j]["case_id"],
                "status": self.failures[j]["status"],
                "distance": float(d[j]),
                "archive_failures": len(self.failures)}

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


#: how a verifier severity presents as a pipeline stage
SEVERITY_STATE = {"ok": "ok", "warn": "warned", "block": "blocked"}


def _report(trace: dict, severity: str, rule: str, reason: str,
            consequence: str, override_available: bool = False) -> dict:
    """The report the engineer reads -- built on every path, including clean ones.

    `consequence` is the half that makes a warning actionable: not just what is
    wrong, but what the system did about it and what happens if they do nothing.
    """
    prior = trace.get("report", {})
    trace["report"] = {
        "severity": severity, "rule": rule, "reason": reason,
        "consequence": consequence,
        "override_available": override_available,
        # a later, more severe report must not erase the fact that a human
        # already took responsibility for getting here
        "override_applied": prior.get("override_applied", False),
    }
    return trace["report"]


def _audit(trace: dict, action: str, **fields) -> dict:
    """Append to the audit trail. Who decided what, when, and on what basis."""
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "action": action, **fields}
    trace.setdefault("audit", []).append(entry)
    return entry


def _stage(sid: str, state: str, headline: str, detail=None) -> dict:
    """state is one of: ok | warned | blocked | skipped"""
    title, subtitle = next((t, s) for i, t, s in STAGES if i == sid)
    return {"id": sid, "title": title, "subtitle": subtitle,
            "state": state, "headline": headline, "detail": detail or {}}


def analyse(text: str, name: str, archive: Archive,
            backend: str = "auto", override: bool = False,
            operator: str | None = None, basis: str | None = None) -> dict:
    """Run the full pipeline over one artifact. Pure -- returns a trace.

    `override` accepts a WARN verdict and warm-starts anyway. It cannot force a
    blocked one, and it is never the default: the engineer asks for it, and
    `operator`/`basis` record who asked and why.
    """
    stages: list[dict] = []
    trace = {"artifact": name, "stages": stages, "backend": backend,
             "operator": operator or "unattributed", "audit": []}

    # -- Layer 1: ingest ---------------------------------------------------
    # An unavailable backend is a refusal like any other, not a crash: it gets
    # a stage in the pipeline with a reason the operator can act on, in the same
    # visual language as every other refusal.
    try:
        card = ingest_text(text, name, backend=backend)
    except RuntimeError as exc:
        stages.append(_stage("ingest", "blocked", str(exc),
                             {"backend": backend}))
        for sid in ("plausible", "retrieve", "verify", "solve", "admissible"):
            stages.append(_stage(sid, "skipped", "not reached"))
        trace.update(outcome="ingest_unavailable", summary=str(exc),
                     fields=[], card={})
        _report(trace, "block", "backend", str(exc),
                "nothing was read, so no starting state was proposed -- this is "
                "a configuration fault, not a judgement about the physics")
        return trace
    trace["card"] = card.to_dict()
    trace["fields"] = [
        {"name": f, "unit": CANONICAL_UNITS[f],
         "value": card.params.get(f), "raw": card.provenance.get(f, "")}
        for f in model.PARAM_NAMES
    ]
    found = len(card.params)
    foreign_label = casecard.FOREIGN_DOMAINS.get(card.domain, {}).get(
        "label", card.domain)
    if card.foreign_domain:
        # Ingest did not fail here -- it succeeded at the only thing that was
        # available to succeed at. Marking this stage as blocked would say the
        # parser broke, when what happened is that it correctly identified an
        # artifact whose fields do not exist in this schema.
        stages.append(_stage(
            "ingest", "ok",
            f"{foreign_label} recognised -- {len(card.foreign)} facts read, "
            f"none of them this schema's",
            {"foreign": card.foreign, "domain": card.domain}))
    else:
        stages.append(_stage(
            "ingest", "ok" if found else "blocked",
            f"{found} of {len(model.PARAM_NAMES)} parameters read"
            f" by {card.source.get('ingested_by', '?')}",
            {"missing": card.missing, "notes": card.notes}))

    # -- is this even the right kind of model? -----------------------------
    # Before the unit gate on purpose: a value's plausibility is judged against
    # a schema, and if the schema does not apply then "off by orders of
    # magnitude" is the wrong complaint. An aluminium density is not a badly
    # scaled fluid density; it is a number from another problem.
    if card.foreign_domain:
        label = foreign_label
        stages.append(_stage("plausible", "skipped",
                             "not this schema's units"))
        stages.append(_stage(
            "retrieve", "blocked",
            f"this is a {label}, not a {casecard.DOMAIN} case",
            # the facts belong to the Ingest stage that read them; this stage
            # carries only the decision and what it was decided against
            {"domain": card.domain, "archive_domain": archive.domain}))
        for sid in ("verify", "solve", "admissible"):
            stages.append(_stage(sid, "skipped", "not reached"))
        trace["outcome"] = "foreign_domain"
        trace["summary"] = f"{label}; nothing in this archive applies to it"
        _report(trace, "block", "domain",
                f"the artifact is a {label}; this archive holds "
                f"{casecard.DOMAIN} cases",
                "the three layers are solver-agnostic but the Case Card schema "
                "is not, and a state cannot be transferred between physics that "
                "do not share unknowns. Reading this file is Layer 1 working; "
                "using it would need the field-transfer adapter, which is not "
                "built")
        return trace

    # -- unit sanity -------------------------------------------------------
    problems = card.validate()
    if problems:
        stages.append(_stage("plausible", "blocked", problems[0],
                             {"problems": problems}))
        trace["outcome"] = "refused_implausible"
        trace["summary"] = problems[0]
        _report(trace, "block", "implausible", problems[0],
                "a value this far out is a misread unit, not a risky transfer -- "
                "the artifact has to be corrected; nothing here is overridable")
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
            "retrieve", "blocked",
            f"not read from the artifact: {', '.join(card.missing)}",
            {"suggestion": suggestion,
             "note": "A missing parameter is a question for the engineer, not a "
                     "value to borrow -- that is how a wrong answer gets in."}))
        for sid in ("verify", "solve", "admissible"):
            stages.append(_stage(sid, "skipped", "not reached"))
        trace["outcome"] = "refused_incomplete"
        trace["summary"] = f"missing {', '.join(card.missing)}"
        _report(trace, "block", "incomplete",
                f"not read from the artifact: {', '.join(card.missing)}",
                "there is no risk here to weigh up -- the value has to come from "
                "an engineer. The nearest case is shown for context and is not "
                "applied")
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
         "regime": source["regime"],
         "indexed_on": len(model.PARAM_NAMES),
         "nearest_failure": archive.nearest_failure(card.params)}))

    # -- Layer 3a: is the transfer legitimate? -----------------------------
    verdict = archive.verifier.check_transfer(card.params, source, distance)
    # An override accepts a *risk*, so it can only move a WARN verdict. A block
    # is a statement of fact and there is no flag that argues with one.
    overridden = bool(override and verdict.overridable and not verdict.admit)
    accepted = verdict.admit or overridden
    trace["verdict"] = {"admit": verdict.admit, "rule": verdict.rule,
                        "reason": verdict.reason, "severity": verdict.severity,
                        "overridable": verdict.overridable,
                        "overridden": overridden}

    who = trace["operator"]
    if overridden:
        _audit(trace, "override", rule=verdict.rule, reason=verdict.reason,
               operator=who, basis=basis or "not stated")
        verify_state, verify_head = "warned", f"{verdict.reason} -- overridden by {who}"
    else:
        verify_state = SEVERITY_STATE[verdict.severity]
        verify_head = verdict.reason
    stages.append(_stage("verify", verify_state, verify_head,
                         {"rule": verdict.rule, "severity": verdict.severity,
                          "overridable": verdict.overridable,
                          "overridden": overridden,
                          "basis": basis if overridden else None}))

    if verdict.admit:
        _report(trace, "ok", verdict.rule, verdict.reason,
                "the archived state is used as the initial guess")
    elif overridden:
        rep = _report(trace, "warn", verdict.rule, verdict.reason,
                      f"warning accepted by {who}; the archived state is used as "
                      f"the initial guess regardless. The answer is still checked "
                      f"against the admissibility gate below")
        rep["override_applied"] = True
    elif verdict.overridable:
        _report(trace, "warn", verdict.rule, verdict.reason,
                "the archive is not used: the solver starts from the nominal "
                "guess built from this case's own parameters, so refusing costs "
                "nothing. Override to warm-start anyway",
                override_available=True)
    else:
        _report(trace, "block", verdict.rule, verdict.reason,
                "a state from different hardware solves different equations -- "
                "there is no judgement to make here, so no override is offered")

    cold = model.solve(card.params, record_path=True)
    # The flat cold start is the weakest baseline there is, so the demo quotes
    # the same comparison bench.py does: a nominal guess built from this card's
    # own parameters, no archive involved. If the archive only beats the flat
    # start, it has not earned the stage it is standing on.
    nom = model.solve(card.params, x0=model.nominal_start(card.params),
                      record_path=True)
    if accepted:
        # The retrieved card is not just a state -- it also recorded how its
        # answer moves with the case parameters, so the start is walked from
        # the neighbour's operating point toward this one before Newton sees
        # it. Same candidate, same gate, same answer; fewer iterations.
        x0, first_order = archive.warm_start(j, card.params)
        warm = model.solve(card.params, x0=x0, record_path=True)
        chosen, label = warm, "warm"
    else:
        # A warning the engineer left standing should not cost them anything.
        # The archive stays unused; the fallback is simply the best guess that
        # does not involve it. Cold remains the last resort if nominal fails --
        # and this is what makes the warning cheap enough to be worth reading.
        warm = None
        first_order = False
        chosen, label = ((nom, "nominal") if nom["converged"]
                         else (cold, "cold"))

    solve = {"cold_iterations": cold["iterations"],
             "cold_status": cold["status"],
             "nominal_iterations": nom["iterations"],
             "nominal_status": nom["status"],
             "start": label}
    if warm is not None:
        solve.update(warm_iterations=warm["iterations"],
                     warm_status=warm["status"],
                     #: which transfer order was used. Stated rather than
                     #: implied: an archive without tangents still warm-starts,
                     #: just not as well, and the report should not let those
                     #: two look like the same run.
                     transfer="first_order" if first_order else "verbatim")
        if cold["converged"] and warm["converged"]:
            dx = np.abs(np.array(cold["x"]) - np.array(warm["x"]))
            solve["agreement"] = float(dx.max())
            solve["saved"] = cold["iterations"] - warm["iterations"]
        if nom["converged"] and warm["converged"]:
            dn = np.abs(np.array(nom["x"]) - np.array(warm["x"]))
            solve["agreement_vs_nominal"] = float(dn.max())
            solve["saved_vs_nominal"] = nom["iterations"] - warm["iterations"]
    # What follows is for the geometry view, and it is the same data the stages
    # above already computed -- no extra solve, no second retrieval. Without it
    # the page can only ever draw the fixture `viz.py` shipped, and the case the
    # operator just analysed would sit in a panel that ignores it.
    if chosen["converged"]:
        solve["solution"] = {k: float(v)
                             for k, v in zip(model.STATE_NAMES, chosen["x"])}
        # the relief valve's state is part of the answer, not of the setup, so
        # the drawing of this case cannot be derived from the Case Card alone
        solve["regime"] = model.regime(chosen["x"], card.params)
    solve["paths"] = {
        name: [[float(v) for v in row] for row in arm["path"]]
        for name, arm in (("cold", cold), ("nominal", nom), ("warm", warm))
        if arm is not None
    }
    trace["solve"] = solve
    trace["retrieval"]["solution"] = {
        k: float(v) for k, v in zip(model.STATE_NAMES, archive.states[j])}

    if not chosen["converged"]:
        stages.append(_stage("solve", "blocked",
                             f"{label} start did not converge ({chosen['status']})"))
        stages.append(_stage("admissible", "skipped", "not reached"))
        trace["outcome"] = "no_answer"
        trace["summary"] = f"{label} start did not converge"
        _report(trace, "block", "no_answer",
                f"the {label} start did not converge ({chosen['status']})",
                "there is no answer to report on, warned or otherwise")
        return trace

    if warm is not None and "saved" in solve:
        base = (f"{solve['cold_iterations']} cold / {solve['nominal_iterations']} nominal"
                if nom["converged"] else f"{solve['cold_iterations']} cold")
        headline = (f"{base} -> {solve['warm_iterations']} warm iterations, "
                    f"same answer to {solve['agreement']:.1e}")
    elif label == "nominal":
        headline = (f"nominal guess, {nom['iterations']} iterations "
                    f"(archive not used -- warned, not overridden)")
    else:
        headline = f"cold start, {cold['iterations']} iterations"
    stages.append(_stage("solve", "ok", headline, solve))

    # -- Layer 3b: is the answer an operating point? -----------------------
    admissible = verifier.Verifier.check_solution(chosen["x"], card.params)
    stages.append(_stage("admissible",
                         "ok" if admissible.admit else SEVERITY_STATE[admissible.severity],
                         admissible.reason,
                         {"rule": admissible.rule, "severity": admissible.severity}))

    reg = model.regime(chosen["x"], card.params)
    trace["regime"] = reg
    trace["solution"] = [
        {"name": n, "unit": u, "value": float(v)}
        for n, u, v in zip(model.STATE_NAMES, model.STATE_UNITS, chosen["x"])
    ]
    if not admissible.admit:
        trace["outcome"] = "inadmissible_solution"
        trace["summary"] = admissible.reason
        # This is measured, not estimated, so it outranks whatever gate 1 said --
        # including an override, which _report deliberately remembers.
        _report(trace, "block", admissible.rule, admissible.reason,
                "the answer is reported in full so it can be inspected, but it is "
                "not an operating point and must not be used as one")
        if overridden:
            # exactly the sequence an audit trail exists for
            _audit(trace, "inadmissible_after_override", rule=admissible.rule,
                   reason=admissible.reason, operator=who)
        return trace

    # not "refused": the engineer was warned and left the warning standing
    trace["outcome"] = ("warm_started_override" if overridden
                        else "warm_started" if verdict.admit
                        else "warned_not_used")
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
        mark = {"ok": "OK    ", "warned": "WARN  ", "blocked": "BLOCK "}[st["state"]]
        out.append(f"\n{mark} {st['title']:<12} {st['headline']}")
        sug = st["detail"].get("suggestion")
        foreign = st["detail"].get("foreign")
        if foreign:
            for k, val in foreign.items():
                out.append(f"       {k:26} {val}")
        nf = st["detail"].get("nearest_failure")
        if nf:
            out.append(f"       indexed on {st['detail']['indexed_on']} parameters; "
                       f"nearest of {nf['archive_failures']} failed runs is "
                       f"{nf['case_id']} ({nf['distance']:.2f} away, {nf['status']})")
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

    # The report is the deliverable the engineers asked for, so it is printed
    # even when everything passed -- a report that only appears on bad news is
    # one nobody learns to read.
    rep = trace.get("report")
    if rep:
        out.append("")
        out.append(f"REPORT  [{rep['severity'].upper()}] {rep['reason']}")
        out.append(f"        {rep['consequence']}.")
        if rep["override_available"]:
            out.append("        This is a warning, not a block -- re-run with "
                       "--override to proceed anyway.")
    for a in trace.get("audit", []):
        out.append(f"AUDIT   {a['at']}  {a['action']}  by {a.get('operator', '?')}"
                   f"  [{a.get('rule', '-')}]  basis: {a.get('basis', '-')}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", nargs="?", type=Path)
    ap.add_argument("--all", action="store_true", help="run every fixture in logs/")
    ap.add_argument("--logs", type=Path, default=Path("logs"))
    ap.add_argument("--archive", type=Path, default=Path("archive/cases.jsonl"))
    ap.add_argument("--backend", default="auto", choices=list(ingest.BACKENDS))
    ap.add_argument("--override", action="store_true",
                    help="accept a WARN verdict and warm-start anyway "
                         "(cannot force a BLOCK)")
    ap.add_argument("--operator", default=getpass.getuser(),
                    help="who is accepting the risk -- goes in the audit trail")
    ap.add_argument("--basis", default=None,
                    help="why, in one line -- goes in the audit trail too")
    ap.add_argument("--json", action="store_true", help="emit the trace as JSON")
    args = ap.parse_args()

    try:
        archive = Archive(args.archive)
    except FileNotFoundError as exc:
        raise SystemExit(str(exc))

    targets = (sorted(p for p in args.logs.iterdir() if p.suffix in ARTIFACT_SUFFIXES)
               if args.all else [args.artifact])
    if not targets or targets == [None]:
        ap.error("give an artifact path, or pass --all")

    traces = [analyse(p.read_text(encoding="utf-8"), p.name, archive, args.backend,
                      override=args.override, operator=args.operator,
                      basis=args.basis)
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
