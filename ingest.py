"""Layer 1 — turn a run artifact into a Case Card.

Three backends behind one interface:

**rules** — a deterministic parser: synonym table, unit conversion, number
parsing. No network, no key, no cost. It handles machine-written logs well and
prose not at all, which is the honest shape of the problem.

**ollama** — a local model over the Ollama HTTP API, constrained to the same
JSON schema. Nothing leaves the machine. The argument for it is not cost (the
hosted calls here are fractions of a cent) but **confidentiality**: run
artifacts are customer simulation data, and "it never leaves your network" is
an answer an engineer can take to their manager. It also makes the demo work
with no internet.

**llm** — Claude Opus 5 with a structured-output schema, for the quality ceiling.

The point of keeping all three is not redundancy — it is that the *gaps between
them* are the measurement. `python ingest.py --compare` scores every available
backend against the same ground truth, so "the local model is good enough" is a
number rather than a hope.

The system does not depend on any model: with nothing configured, ingest falls
back to `rules` and everything downstream still runs. That is the claim the plan
makes ("if you delete it, the system still works"), enforced in code rather than
asserted on a slide.

    python ingest.py --compare
    OLLAMA_MODEL=qwen2.5:7b python ingest.py --backend ollama logs/note-ro.txt
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import casecard
import model
from casecard import CaseCard, normalise_unit, parse_number

MODEL_ID = "claude-opus-5"

#: how each parameter can appear in the wild -> canonical name
SYNONYMS: dict[str, str] = {
    "q_nom": "Q_nom", "qnom": "Q_nom", "flow": "Q_nom", "pump flow": "Q_nom",
    "pump nominal delivery": "Q_nom", "nominal delivery": "Q_nom",
    "pump delivery": "Q_nom", "debit": "Q_nom", "debitul pompei": "Q_nom",
    "a_valve_a": "A_valve_a", "avalvea": "A_valve_a",
    "metering valve a, orifice area": "A_valve_a",
    "metering valve a": "A_valve_a", "valve a area": "A_valve_a",
    "a_valve_b": "A_valve_b", "avalveb": "A_valve_b",
    "metering valve b, orifice area": "A_valve_b",
    "metering valve b": "A_valve_b", "valve b area": "A_valve_b",
    "c_load_a": "c_load_a", "cloada": "c_load_a",
    "shaft a quadratic load coeff": "c_load_a", "load coeff a": "c_load_a",
    "c_load_b": "c_load_b", "cloadb": "c_load_b",
    "shaft b quadratic load coeff": "c_load_b", "load coeff b": "c_load_b",
    "p_crack": "p_crack", "pcrack": "p_crack",
    "relief cracking setting": "p_crack", "relief setting": "p_crack",
    "cracking pressure": "p_crack", "relief": "p_crack",
    "rho": "rho", "density": "rho", "working fluid density": "rho",
    "fluid density": "rho", "densitate": "rho", "densitatea": "rho",
}

#: `key <separator> value <unit>` -- tolerates dot-leaders and ASCII banners
_LINE = re.compile(
    r"^\s*(?P<key>[A-Za-z][A-Za-z0-9 _,()/^-]*?)\s*[.\s]*[:=]\s*"
    r"(?P<value>[-+]?[\d.,]+(?:[eE][-+]?\d+)?)\s*"
    r"(?P<unit>[A-Za-zµ°^/³²\d]*(?:/[A-Za-z0-9^()/]+)?)\s*$")


# --- backend: rules ---------------------------------------------------------

def ingest_rules(text: str, artifact: str, case_id: str) -> CaseCard:
    """Deterministic key/value extraction with unit normalisation."""
    params: dict[str, float] = {}
    provenance: dict[str, str] = {}

    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        key = re.sub(r"[.\s]+$", "", m.group("key").strip().lower())
        canon = SYNONYMS.get(key) or SYNONYMS.get(key.replace(" ", ""))
        if canon is None or canon in params:
            continue
        value = parse_number(m.group("value"))
        if value is None:
            continue
        unit = m.group("unit") or None
        value, raw_unit = normalise_unit(value, unit)
        params[canon] = value
        provenance[canon] = f"{m.group('value')} {raw_unit or ''}".strip()

    domain, foreign = casecard.detect_domain(text)
    if domain != casecard.DOMAIN:
        # The matches are the point, not an accident. A NASTRAN deck states a
        # material density; SYNONYMS maps "density" onto `rho`; without the
        # domain check the card would record aluminium as the hydraulic fluid.
        # So they are recorded as *what would have been mis-mapped* and the
        # params are left empty -- nothing in this schema applies to this file.
        if params:
            foreign["would_have_been_mismapped"] = ", ".join(
                f"{k} <- {provenance[k]}" for k in sorted(params))
        params, provenance = {}, {}

    return CaseCard(
        case_id=case_id,
        source={"artifact": artifact, "ingested_by": "rules",
                "ingested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        params=params,
        provenance=provenance,
        missing=[p for p in model.PARAM_NAMES if p not in params],
        domain=domain,
        foreign=foreign,
    )


# --- backend: llm -----------------------------------------------------------

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "params": {
            "type": "object",
            "description": "Only the parameters the artifact actually states. "
                           "Omit anything not present; never estimate.",
            "properties": {
                name: {"type": "number",
                       "description": f"{name} in {casecard.CANONICAL_UNITS[name]}"}
                for name in model.PARAM_NAMES
            },
            "additionalProperties": False,
        },
        "provenance": {
            "type": "object",
            "description": "For each extracted parameter, the exact substring of "
                           "the artifact it came from, including the original unit.",
            "properties": {name: {"type": "string"} for name in model.PARAM_NAMES},
            "additionalProperties": False,
        },
        "missing": {
            "type": "array",
            "description": "Parameters the artifact states no number for. A "
                           "qualitative phrase such as 'the standard fan curves' "
                           "is NOT a value; a number described in words "
                           "('roughly 2 mm2') IS one.",
            "items": {"type": "string", "enum": list(model.PARAM_NAMES)},
        },
        "notes": {
            "type": "string",
            "description": "One sentence on what the artifact says happened, in English.",
        },
    },
    "required": ["params", "provenance", "missing", "notes"],
    "additionalProperties": False,
}

SYSTEM = f"""You extract simulation setup parameters from run artifacts of a \
hydraulic manifold model. Artifacts are heterogeneous: machine-written solver \
logs, older banner-style logs, and free-text notes or emails written by \
engineers in English or Romanian.

Extract these parameters, converting to the canonical unit given:
{chr(10).join(f'  {n} -- {casecard.CANONICAL_UNITS[n]}' for n in model.PARAM_NAMES)}

Rules:
- Convert units. m3/h -> L/min, m^2 -> mm^2, g/cm3 -> kg/m^3, Pa -> bar.
- A European decimal comma means a decimal point: "4,5" is 4.5.
- If the artifact does not state a parameter, list it in `missing`. Do not \
estimate, infer from context, or carry a value over from a similar case. A \
qualitative description of a load ("the standard fan curves", "sarcina e mica") \
is not a coefficient -- that parameter is missing.
- But a stated number is still a value when it is hedged or wrapped in \
description. "roughly 2 mm2", "about 55 lpm", "left wide at 11 mm2", "call it \
890", "pe la 70 l/min" all state their parameter -- extract the number and quote \
the phrase. A parameter is missing only when no number is given for it at all: \
words like "barely", "roughly" or "deliberately restrictive" beside a figure \
describe that figure, they do not withdraw it.
- `provenance` must quote the artifact verbatim, not paraphrase it.
- A corrupted or placeholder value (####, NaN, ---) is missing, not zero."""


def ingest_llm(text: str, artifact: str, case_id: str,
               effort: str = "medium") -> CaseCard:
    """Extract via Claude with a structured-output schema.

    Raises RuntimeError with an actionable message when the SDK or credentials
    are unavailable, so callers can fall back to `rules` rather than crash.
    """
    try:
        import anthropic
    except ImportError as exc:                                  # pragma: no cover
        raise RuntimeError(
            "the anthropic SDK is not installed -- `pip install anthropic`, "
            "or use --backend rules") from exc

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL_ID,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": effort,
                           "format": {"type": "json_schema",
                                      "schema": EXTRACTION_SCHEMA}},
            messages=[{"role": "user",
                       "content": f"<artifact name={artifact!r}>\n{text}\n</artifact>"}],
        )
    except Exception as exc:                                    # pragma: no cover
        raise RuntimeError(f"Claude call failed: {exc}") from exc

    if response.stop_reason == "refusal":                       # pragma: no cover
        raise RuntimeError("the request was declined by safety classifiers")

    payload = json.loads(next(b.text for b in response.content if b.type == "text"))
    params = {k: float(v) for k, v in payload.get("params", {}).items()}
    return CaseCard(
        case_id=case_id,
        source={"artifact": artifact, "ingested_by": f"llm:{MODEL_ID}",
                "ingested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "usage": {"input_tokens": response.usage.input_tokens,
                          "output_tokens": response.usage.output_tokens}},
        params=params,
        provenance=payload.get("provenance", {}),
        missing=[p for p in model.PARAM_NAMES if p not in params],
        notes=payload.get("notes", ""),
    )


# --- backend: ollama (local, private, free) ---------------------------------
#
# The architectural argument for this backend is not cost -- the Claude calls
# here are fractions of a cent. It is **confidentiality**: run artifacts are
# customer simulation data, and "nothing leaves your network" is an answer an
# engineer can take to their manager. It also makes the demo work with no
# internet at all, which matters in a conference room.
#
# Whether a small local model is *good enough* at this particular job is an
# empirical question -- unit-conversion arithmetic and strict JSON are exactly
# what small models are weakest at -- so `--compare` scores it against the same
# ground truth as everything else rather than taking it on faith.

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


def ollama_available() -> tuple[bool, str]:
    """(reachable, detail). Also reports whether the configured model is pulled."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            tags = json.load(r)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return False, f"no Ollama server at {OLLAMA_URL} ({exc})"
    names = [m["name"] for m in tags.get("models", [])]
    if OLLAMA_MODEL not in names and OLLAMA_MODEL.split(":")[0] not in \
            [n.split(":")[0] for n in names]:
        return False, (f"Ollama is running but '{OLLAMA_MODEL}' is not pulled "
                       f"(have: {', '.join(names) or 'nothing'}) -- "
                       f"run `ollama pull {OLLAMA_MODEL}`")
    return True, f"{OLLAMA_MODEL} via {OLLAMA_URL}"


def ingest_ollama(text: str, artifact: str, case_id: str,
                  model_name: str | None = None) -> CaseCard:
    """Extract with a local model, using Ollama's JSON-schema structured output."""
    import urllib.error
    import urllib.request

    name = model_name or OLLAMA_MODEL
    ok, detail = ollama_available()
    if not ok:
        raise RuntimeError(detail)

    body = json.dumps({
        "model": name,
        "stream": False,
        # Ollama >= 0.5 constrains generation to a JSON schema, the same schema
        # the Claude backend uses -- so both backends are held to one contract.
        "format": EXTRACTION_SCHEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",
             "content": f"<artifact name={artifact!r}>\n{text}\n</artifact>"},
        ],
    }).encode()

    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"content-type": "application/json"})
    try:
        # 280s, not 180 -- CPU-only inference (the AWS deployment's Ollama
        # instance has no GPU, quota-blocked on this account) lands close to
        # 180s on a prose artifact, close enough that it was a coin flip
        # whether this raised before the model actually finished. Margin is
        # kept under the ALB's own 300s idle timeout so a genuine failure
        # still surfaces as this function's RuntimeError -- a real pipeline
        # stage -- rather than a bare gateway timeout with no context.
        with urllib.request.urlopen(req, timeout=280) as r:
            payload = json.load(r)
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Ollama call failed: {exc}") from exc

    content = payload.get("message", {}).get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{name} did not return valid JSON ({exc}); "
            f"first 200 chars: {content[:200]!r}") from exc

    # A local model may emit nulls or strings where the schema says number.
    # Coerce what is coercible and drop the rest -- a field we cannot read as a
    # number is missing, which is the honest outcome, not zero.
    params: dict[str, float] = {}
    for key, value in (data.get("params") or {}).items():
        if key not in model.PARAM_NAMES or value is None:
            continue
        try:
            params[key] = float(value)
        except (TypeError, ValueError):
            continue

    return CaseCard(
        case_id=case_id,
        source={"artifact": artifact, "ingested_by": f"ollama:{name}",
                "ingested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "local": True},
        params=params,
        provenance={k: str(v) for k, v in (data.get("provenance") or {}).items()
                    if k in model.PARAM_NAMES},
        missing=[p for p in model.PARAM_NAMES if p not in params],
        notes=str(data.get("notes", "")),
    )


# --- dispatch ---------------------------------------------------------------

def credentials_available() -> bool:
    """Whether the llm backend has any chance of working."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or (Path.home() / ".config" / "anthropic" / "credentials").exists())


# --- anti-invention: verify the model's own citation ------------------------

def verify_provenance(card: CaseCard, text: str) -> list[str]:
    """Drop any field whose quoted source cannot be found in the artifact.

    Measured need, not a precaution: qwen2.5:7b invented 3 values across the
    fixture set — supplying numbers for parameters the artifact never stated.
    That is the project's own failure mode (a confident wrong value) appearing
    in Layer 1, so Layer 1 gets its own verifier.

    The check is deterministic and free: the prompt already demands verbatim
    provenance, so a citation that does not appear in the source text is a
    fabrication and the field goes back to `missing`. A model cannot talk its
    way past this the way it can talk its way past an instruction.
    """
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.lower()).strip()

    def digits(s: str) -> str:
        return re.sub(r"[^0-9]", "", s)

    hay = norm(text)
    hay_digits = digits(text)
    dropped = []
    for field, value in list(card.params.items()):
        quote = card.provenance.get(field, "")

        # 1. Physically impossible values are inventions whatever the citation.
        #    Observed: the model answered "the standard fan curves" with 0.0.
        lo, hi = model.PARAM_BOUNDS[field]
        if not (lo / 1000 <= abs(value) <= hi * 1000):
            dropped.append(field)
            card.params.pop(field, None)
            card.provenance.pop(field, None)
            continue

        # 2. A citation supports a *number* only if it contains one. Quoting a
        #    qualitative phrase is the model showing it inferred rather than read.
        if quote and norm(quote) in hay and any(c.isdigit() for c in quote):
            continue

        # 3. No citation is not proof of invention -- the model sometimes reads
        #    correctly and simply omits the quote. Accept when the value's own
        #    digits are in the artifact (covers unit-converted values too, since
        #    those are only reachable via a cited source that did contain them).
        forms = {f"{value:g}", f"{value:.10g}", str(value)}
        if float(value).is_integer():
            forms.add(str(int(value)))
        if any(digits(f) and digits(f) in hay_digits for f in forms):
            continue

        dropped.append(field)
        card.params.pop(field, None)
        card.provenance.pop(field, None)

    if dropped:
        card.missing = [p for p in model.PARAM_NAMES if p not in card.params]
        card.notes = (f"{card.notes} [dropped {', '.join(dropped)}: the cited "
                      f"source text is not in the artifact]").strip()
    return dropped


BACKENDS = ("auto", "rules", "ollama", "llm", "hybrid")


def ingest_text(text: str, name: str, backend: str = "auto") -> CaseCard:
    """Ingest artifact *content*.

    `auto` prefers a local model, then Claude, then the deterministic parser --
    local first because it keeps run data on the network, and because it costs
    nothing to try. An explicitly named backend is never silently substituted:
    it either runs or raises, so a measurement always says which one produced it.

    Text rather than a path, because the UI posts pasted content that never
    touches the filesystem — and because the CLI and the service must go through
    one implementation, or they drift.
    """
    case_id = f"ingest-{Path(name).stem}"

    def model_card(which: str) -> CaseCard:
        card = (ingest_ollama if which == "ollama" else ingest_llm)(
            text, name, case_id)
        verify_provenance(card, text)
        return card

    if backend in ("ollama", "llm"):
        return model_card(backend)
    if backend == "rules":
        return ingest_rules(text, name, case_id)
    if backend == "hybrid":
        return ingest_hybrid(text, name, case_id, _first_model_backend())

    # auto == hybrid when a model is reachable, rules otherwise
    which = _first_model_backend()
    if which is None:
        return ingest_rules(text, name, case_id)
    try:
        return ingest_hybrid(text, name, case_id, which)
    except RuntimeError as exc:
        print(f"  [{which} unavailable: {exc}; falling back to rules]")
        return ingest_rules(text, name, case_id)


def _first_model_backend() -> str | None:
    """Local first: it keeps run data on the machine and costs nothing."""
    if ollama_available()[0]:
        return "ollama"
    if credentials_available():
        return "llm"
    return None


def ingest_hybrid(text: str, name: str, case_id: str,
                  which: str | None = None) -> CaseCard:
    """Deterministic parser first, model only for what it could not read.

    The measurement forced this. On machine-written logs the parser scores 7/7
    and the local model 4-5/7; on prose the parser scores 0-2/7 and the model
    7/7. Neither is better — they fail on disjoint inputs, so the right answer
    is to use each where it wins.

    It is also what makes the demo fast: a well-formed log never reaches the
    model at all, so it returns instantly, and only genuinely messy artifacts
    pay for inference.
    """
    card = ingest_rules(text, name, case_id)
    if card.complete:
        card.source["ingested_by"] = "rules (complete, model not needed)"
        return card
    if card.foreign_domain:
        # A foreign artifact never reaches the model. There is nothing for it to
        # extract -- the fields do not exist in this file -- and asking anyway is
        # how a language model gets talked into inventing seven of them.
        card.source["ingested_by"] = "rules (foreign domain, model not asked)"
        return card

    which = which or _first_model_backend()
    if which is None:
        return card

    model_side = (ingest_ollama if which == "ollama" else ingest_llm)(
        text, name, case_id)
    verify_provenance(model_side, text)

    filled = []
    for field in card.missing:
        if field in model_side.params:
            card.params[field] = model_side.params[field]
            card.provenance[field] = model_side.provenance.get(field, "")
            filled.append(field)

    card.missing = [p for p in model.PARAM_NAMES if p not in card.params]
    card.source["ingested_by"] = (
        f"rules + {model_side.source['ingested_by']}" if filled
        else f"rules (+{which}, nothing added)")
    card.source["filled_by_model"] = filled
    if model_side.notes:
        card.notes = model_side.notes
    return card


def ingest(path: Path, backend: str = "auto") -> CaseCard:
    """Ingest one artifact from disk."""
    return ingest_text(path.read_text(encoding="utf-8"), path.name, backend)


# --- the measurement --------------------------------------------------------

def compare(log_dir: Path, backends: list[str]) -> dict:
    """Score each backend against ground truth, per artifact.

    A field counts as correct only if it is within 1% of the true value; a field
    the artifact never stated counts as correct only if the backend *reported it
    missing*. Inventing a plausible number is scored as a miss, not a partial
    credit — a confidently wrong Case Card is worse than an incomplete one.
    """
    truth = json.loads((log_dir / "ground_truth.json").read_text(encoding="utf-8"))
    results: dict[str, dict] = {b: {"correct": 0, "total": 0, "invented": 0,
                                    "per_file": {}} for b in backends}

    for name, expected in sorted(truth.items()):
        path = log_dir / name
        for backend in backends:
            try:
                card = ingest(path, backend=backend)
            except RuntimeError as exc:
                results[backend]["per_file"][name] = f"unavailable ({exc})"
                continue
            got, want = card.params, expected["params"]
            hits = invented = 0
            for field in model.PARAM_NAMES:
                if field in want:
                    v = got.get(field)
                    hits += v is not None and abs(v - want[field]) <= abs(want[field]) * 0.01
                else:
                    if field in got:
                        invented += 1
                    else:
                        hits += 1
            n = len(model.PARAM_NAMES)
            results[backend]["correct"] += hits
            results[backend]["total"] += n
            results[backend]["invented"] += invented
            results[backend]["per_file"][name] = {
                "correct": hits, "of": n, "invented": invented,
                "unit_errors": card.validate()}
    return results


def report(results: dict, truth_path: Path) -> None:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    names = sorted(truth)
    backends = list(results)
    print(f"\n{'artifact':22}" + "".join(f"{b:>16}" for b in backends))
    for name in names:
        row = f"{name:22}"
        for b in backends:
            cell = results[b]["per_file"].get(name)
            if isinstance(cell, str):
                row += f"{'n/a':>16}"
            else:
                mark = f"{cell['correct']}/{cell['of']}"
                if cell["invented"]:
                    mark += f" +{cell['invented']}!"
                row += f"{mark:>16}"
        print(row)
    totals = "".join(f"{f'{results[b]['correct']}/{results[b]['total']}':>16}"
                     for b in backends)
    print(f"{'total':22}{totals}")
    for b in backends:
        r = results[b]
        if r["total"]:
            print(f"\n  {b}: {r['correct']}/{r['total']} fields "
                  f"({100 * r['correct'] / r['total']:.0f}%), "
                  f"{r['invented']} invented")
    print("\n  '+N!' = fields the backend supplied that the artifact never stated.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", nargs="?", type=Path, help="one file to ingest")
    ap.add_argument("--backend", default="auto", choices=list(BACKENDS))
    ap.add_argument("--logs", type=Path, default=Path("logs"))
    ap.add_argument("--compare", action="store_true",
                    help="score every backend against ground truth")
    args = ap.parse_args()

    if args.compare:
        backends = ["rules"] + (["ollama", "hybrid"] if ollama_available()[0] else []) + (["llm"] if credentials_available() and not ollama_available()[0] else [])
        if len(backends) == 1:
            print("no Anthropic credentials found -- scoring the rules backend only.")
            print("set ANTHROPIC_API_KEY (or run `ant auth login`) to score the LLM.")
        report(compare(args.logs, backends), args.logs / "ground_truth.json")
        return

    if not args.artifact:
        ap.error("give an artifact path, or pass --compare")
    card = ingest(args.artifact, backend=args.backend)
    print(card.summary())
    for problem in card.validate():
        print(f"  ! {problem}")


if __name__ == "__main__":
    main()
