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
        if p.suffix not in (".log", ".txt"):
            continue
        out.append({"name": p.name, "text": p.read_text(encoding="utf-8")})
    return out


@api.post("/api/analyse")
def analyse(req: AnalyseRequest) -> JSONResponse:
    """The whole pipeline. Refusals are 200s with an outcome, not HTTP errors —
    a refusal is a result the caller must read, not a transport failure."""
    if not req.text.strip():
        raise HTTPException(422, "empty artifact")
    trace = dejasolve.analyse(req.text, req.name, archive(), backend=req.backend)
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
