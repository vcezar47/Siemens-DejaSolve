"""HTTP service + demo UI for Déjà Solve.

A service rather than a notebook-style app on purpose: the pitch is a platform,
and the thing a platform exposes is an API. The page in ``static/index.html`` is
a client of that API, not a wrapper around a script — so the same endpoint the
demo calls is the one a Study Manager sweep would call, and it maps directly
onto the Phase 4 architecture slide.

    python app.py                 # http://127.0.0.1:8000
    uvicorn app:api --reload      # during development

No secrets required, and no traffic leaves the machine: ingest runs the
deterministic parser and a local model, and falls back to the parser alone if
no model is reachable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

import dejasolve
import ingest
import model

#: resolved against this file, not the working directory -- a service should
#: start correctly whatever directory it was launched from
ROOT = Path(__file__).resolve().parent
ARCHIVE_PATH = ROOT / "archive" / "cases.jsonl"
STATIC = ROOT / "static"
LOGS = ROOT / "logs"

api = FastAPI(title="Déjà Solve", version="0.3.0",
              description="Find the physically-nearest solved case, verify that "
                          "reusing it is legitimate, warm-start the solver.")

_archive: dejasolve.Archive | None = None


def archive() -> dejasolve.Archive:
    """Loaded once, on first use — the sweep is 400 cases, not a database."""
    global _archive
    if _archive is None:
        try:
            _archive = dejasolve.Archive(ARCHIVE_PATH)
        except FileNotFoundError as exc:
            raise HTTPException(503, str(exc)) from exc
    return _archive


class AnalyseRequest(BaseModel):
    text: str = Field(..., description="the raw run artifact")
    name: str = Field("pasted-artifact.log", description="filename, for the record")
    #: built from ingest.BACKENDS rather than written out -- a hardcoded list
    #: here silently 422s any backend added later, which is how `hybrid` came
    #: to be unreachable from the page while working everywhere else
    backend: str = Field("auto", pattern=f"^({'|'.join(ingest.BACKENDS)})$")
    #: an override accepts a WARN verdict and warm-starts anyway. It cannot
    #: force a BLOCK, so it is safe to expose: the worst it can do is use a
    #: starting guess the verifier advised against, and the admissibility gate
    #: still runs on the answer.
    override: bool = Field(False, description="accept a WARN verdict and proceed")
    operator: str | None = Field(None, max_length=120,
                                 description="who is accepting the risk")
    basis: str | None = Field(None, max_length=500,
                              description="why -- recorded in the audit trail")


@api.get("/", response_class=HTMLResponse)
def index() -> str:
    page = STATIC / "index.html"
    if not page.exists():
        raise HTTPException(500, f"missing {page}")
    return page.read_text(encoding="utf-8")


@api.get("/api/health")
def health() -> dict:
    """Enough for a container healthcheck, and it states what ingest can do.

    `llm` (hosted Claude) stays a valid backend for /api/analyse and the CLI but
    is deliberately absent here: the demo's claim is that run data never leaves
    the network, and an option contradicting that -- greyed out or not -- is the
    one thing on screen an engineer will ask about.
    """
    ok = ARCHIVE_PATH.exists()
    ollama_ok, ollama_detail = ingest.ollama_available()
    return {
        "ok": ok,
        "archive": str(ARCHIVE_PATH),
        "archive_size": len(archive().records) if ok else 0,
        # The archive is two things now. Reporting only the solved half is how
        # the page ended up describing an archive that had changed underneath
        # it: an engineer asked for the failed runs to be kept, they are, and a
        # health endpoint that says "395 cases" is quietly incomplete.
        "archive_failed": len(archive().failures) if ok else 0,
        "failure_modes": archive().failure_modes if ok else {},
        "parameters": list(model.PARAM_NAMES),
        "backends": {
            "hybrid": {"available": ollama_ok or ingest.credentials_available(),
                       "detail": "parser first, model only for what it misses",
                       "local": ollama_ok},
            "rules": {"available": True, "detail": "deterministic parser, instant",
                      "local": True},
            "ollama": {"available": ollama_ok, "detail": ollama_detail,
                       "local": True},
        },
    }


@api.get("/api/samples")
def samples() -> list[dict]:
    """The fixture artifacts, so the demo is one click rather than one paste."""
    if not LOGS.exists():
        return []
    out = []
    for p in sorted(LOGS.iterdir()):
        if p.suffix not in dejasolve.ARTIFACT_SUFFIXES:
            continue
        out.append({"name": p.name, "text": p.read_text(encoding="utf-8")})
    return out


#: the measured artifacts, and the headline each one contributes. Read from
#: disk on every request rather than cached: they are regenerated by
#: `run_all.py` while the service may be running, and a page showing yesterday's
#: numbers next to today's pipeline is exactly the kind of quiet inconsistency
#: this project spends its time refusing.
EVIDENCE_FILES = {
    "phase1": ROOT / "results.json",
    "surrogate": ROOT / "surrogate_results.json",
    "surrogate_fold": ROOT / "surrogate_fold_results.json",
    "fold": ROOT / "fold_results.json",
    "failure_zone": ROOT / "failure_zone_results.json",
    "dimensionality": ROOT / "dimensionality_results.json",
}


def _load(name: str) -> dict | None:
    path = EVIDENCE_FILES[name]
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


@api.get("/api/evidence")
def evidence() -> dict:
    """The measured results, for the page to render beside the live pipeline.

    **Everything here was measured offline by `python run_all.py`** — none of it
    is something the service does per request, and the page labels it that way.
    Serving it anyway is the difference between a demo that claims a number and
    one that shows it: the same page that runs the pipeline can show the
    evidence the pipeline's design rests on, without a terminal and a PNG viewer
    open beside it.

    Missing files are reported as missing rather than faked, so a fresh clone
    that has not run the reproducer says so on screen.
    """
    out: dict = {"reproduce": "python run_all.py", "sections": {}}

    p1 = _load("phase1")
    if p1:
        s = p1["summary"]
        # bench.py averages like-for-like: only the cases where *every* arm
        # converged, because the flat start fails on four of them and a mean
        # that quietly drops those flatters it. surrogate.py averages over all
        # 200. Both are defensible and they differ in the second decimal, so
        # the basis is computed here and shown on the card -- two numbers for
        # the same arm with no explanation is how a deck loses an audience.
        basis = sum(1 for c in p1["cases"]
                    if all(c[a]["converged"] for a in ("cold", "nominal", "warm")))
        out["sections"]["phase1"] = {
            "title": "Retrieval warm start", "n": s["n_queries"],
            "basis": f"mean over the {basis} cases where every arm converged",
            "generated_utc": p1.get("generated_utc"),
            "arms": [{"label": k, "mean": s[k]["mean_iterations"],
                      "total": s[k]["total_iterations"],
                      "failures": s[k]["failures"]}
                     for k in ("cold", "nominal", "warm")],
        }

    sur = _load("surrogate")
    if sur:
        out["sections"]["surrogate"] = {
            "title": "Predicted warm start", "n": sur["n_queries"],
            "basis": "mean over the cases each arm converged on",
            "residual_median": sur["prediction_quality"]["median_residual_inf"],
            "solver_tolerance": sur["prediction_quality"]["solver_tolerance"],
            "were_solutions": sur["prediction_quality"]["n_below_solver_tolerance"],
            "arms": [{"label": k, "mean": v["mean_iterations"],
                      "total": v["total_iterations"], "failures": v["failed"]}
                     for k, v in sur["arms"].items()],
        }

    sf, fo = _load("surrogate_fold"), _load("fold")
    if sf and fo:
        out["sections"]["fold"] = {
            "title": "The same circuit, unverified",
            "n": sf["n_queries"],
            "rows": [
                {"label": "valid operating point",
                 "retrieval": fo["outcomes"]["naive_ok"],
                 "prediction": sf["naive"].get("ok", 0)},
                {"label": "unstable root, silently wrong", "alarm": True,
                 "retrieval": fo["outcomes"]["naive_wrong"],
                 "prediction": sf["naive"].get("wrong", 0)},
                {"label": "no answer at all",
                 "retrieval": fo["outcomes"]["naive_failed"],
                 "prediction": sf["naive"].get("failed", 0)},
                {"label": "verified: silently wrong", "good": True,
                 "retrieval": 0, "prediction": sf["guarded"]["unresolved"]},
            ],
        }

    fz = _load("failure_zone")
    if fz:
        fold_row = next((r for r in fz["results"] if r["circuit"] == "foldq"), None)
        if fold_row:
            t = fold_row["targets"]["hard_case"]
            bt = fold_row["targets"]["bad_transfer"]
            out["sections"]["failures"] = {
                "title": "Are the failed runs worth keeping?",
                "archive": fold_row["archive"],
                "auc_hard_case": t["auc"], "auc_bad_transfer": bt["auc"],
                "auc_control": t["controls"]["d_success_only"],
                "base_rate": t["base_rate"], "precision": t["precision"],
                "verdict": "advisory, not a gate rule",
            }

    dim = _load("dimensionality")
    if dim:
        out["sections"]["dimensionality"] = {
            "title": "When the Case Card has hundreds of parameters",
            "n": dim["n_queries"],
            "nominal": dim["reference"]["nominal"]["mean_iterations"],
            "warm_physics": dim["reference"]["warm_physics"]["mean_iterations"],
            "points": [{"width": r["recorded_parameters"],
                        "mean": r["warm_all"]["mean_iterations"],
                        "same_pick": r["same_neighbour_as_physics"],
                        "admitted": r["gate_verdicts"].get("ok", 0),
                        "contrast": r["relative_contrast"]}
                       for r in dim["by_dimension"]],
        }

    out["missing"] = [k for k, v in EVIDENCE_FILES.items() if not v.exists()]
    return out


@api.post("/api/analyse")
def analyse(req: AnalyseRequest) -> JSONResponse:
    """The whole pipeline. Refusals are 200s with an outcome, not HTTP errors —
    a refusal is a result the caller must read, not a transport failure.

    Every response carries a `report` (severity, reason, consequence) and, where
    a human took responsibility for a warning, an `audit` trail. That is the
    shape the interviewed engineers asked for: warn and report, then let the
    engineer decide — rather than refuse silently on their behalf.
    """
    if not req.text.strip():
        raise HTTPException(422, "empty artifact")
    trace = dejasolve.analyse(req.text, req.name, archive(), backend=req.backend,
                              override=req.override, operator=req.operator,
                              basis=req.basis)
    return JSONResponse(trace)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    import uvicorn
    if not ARCHIVE_PATH.exists():
        print(f"warning: no archive at {ARCHIVE_PATH} — run `python run_all.py` first")
    print(f"Déjà Solve UI  ->  http://{args.host}:{args.port}")
    uvicorn.run(api, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
