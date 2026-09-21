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
them* are the measurement. `python -m dejasolve.ingest --compare` scores every available
backend against the same ground truth, so "the local model is good enough" is a
number rather than a hope.

The system does not depend on any model: with nothing configured, ingest falls
back to `rules` and everything downstream still runs. That is the claim the plan
makes ("if you delete it, the system still works"), enforced in code rather than
asserted on a slide.

    python -m dejasolve.ingest --compare
    OLLAMA_MODEL=qwen2.5:7b python -m dejasolve.ingest --backend ollama data/logs/note-ro.txt
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import casecard
from . import model
from .casecard import CaseCard, normalise_unit, parse_number

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
    # the 18 promoted hardware constants (§0b) -- overrides on
    # model.HARDWARE's defaults, optional the way the seven above are not:
    # a card that states none of these is still complete. English only --
    # unlike the seven above, no fixture states any of these in Romanian, so
    # there is no concrete phrasing to work from yet rather than one guessed.
    "cd": "cd", "discharge coefficient": "cd",
    "orifice discharge coefficient": "cd",
    "r_leak": "R_leak", "pump leakage": "R_leak",
    "pump leakage resistance": "R_leak", "leakage resistance": "R_leak",
    "a_relief_max": "A_relief_max", "relief valve area": "A_relief_max",
    "relief area": "A_relief_max", "relief valve max area": "A_relief_max",
    "relief_band": "relief_band", "relief band": "relief_band",
    "relief valve band": "relief_band",
    "cracking to full open band": "relief_band",
    "d_mot_a": "D_mot_a", "motor a displacement": "D_mot_a",
    "shaft a displacement": "D_mot_a", "displacement a": "D_mot_a",
    "d_mot_b": "D_mot_b", "motor b displacement": "D_mot_b",
    "shaft b displacement": "D_mot_b", "displacement b": "D_mot_b",
    "a_ret_a": "A_ret_a", "return line a": "A_ret_a",
    "return restriction a": "A_ret_a",
    "a_ret_b": "A_ret_b", "return line b": "A_ret_b",
    "return restriction b": "A_ret_b",
    "leak_mot_a": "leak_mot_a", "motor a leakage": "leak_mot_a",
    "cross-port leakage a": "leak_mot_a", "cross port leakage a": "leak_mot_a",
    "leak_mot_b": "leak_mot_b", "motor b leakage": "leak_mot_b",
    "cross-port leakage b": "leak_mot_b", "cross port leakage b": "leak_mot_b",
    "t_coul_a": "t_coul_a", "coulomb friction a": "t_coul_a",
    "kinetic friction a": "t_coul_a", "coulomb torque a": "t_coul_a",
    "t_coul_b": "t_coul_b", "coulomb friction b": "t_coul_b",
    "kinetic friction b": "t_coul_b", "coulomb torque b": "t_coul_b",
    "t_stat_a": "t_stat_a", "breakaway torque a": "t_stat_a",
    "static friction a": "t_stat_a", "stiction a": "t_stat_a",
    "t_stat_b": "t_stat_b", "breakaway torque b": "t_stat_b",
    "static friction b": "t_stat_b", "stiction b": "t_stat_b",
    "w_strib_a": "w_strib_a", "stribeck velocity a": "w_strib_a",
    "stribeck speed a": "w_strib_a",
    "w_strib_b": "w_strib_b", "stribeck velocity b": "w_strib_b",
    "stribeck speed b": "w_strib_b",
    "b_visc_a": "b_visc_a", "viscous drag a": "b_visc_a",
    "viscous friction a": "b_visc_a",
    "b_visc_b": "b_visc_b", "viscous drag b": "b_visc_b",
    "viscous friction b": "b_visc_b",
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
        # The *last* match for a field wins, not the first. A log that states
        # a value and later restates or corrects it -- "actually, make that
        # 62.4" -- kept the superseded one under a first-wins rule; nothing
        # in this format distinguishes an initial value from a correction
        # except which one appears later.
        if canon is None:
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

#: the full set of names a Case Card can carry: the seven required swept
#: parameters plus the eighteen optional hardware overrides (§0b). Defined
#: here, ahead of EXTRACTION_SCHEMA below, because both the schema and
#: `foreign_card`/`ingest_ollama`/`ingest_llm` need the same combined list --
#: `ingest_rules` was always this general (it stores whatever `SYNONYMS` maps
#: a line to, with no gate to `model.PARAM_NAMES`), but the JSON-schema
#: backends' prompt only ever asked for the seven, so the eighteen were
#: unreachable from any artifact regardless of which backend read it.
EXTRACTABLE_FIELDS = model.PARAM_NAMES + tuple(model.HARDWARE.keys())

#: the first number anywhere in a value the model wrote as prose -- an appended
#: unit ("1.6e-05 Nm/(rev/min)^2") or a hedge it copied over from the artifact
#: ("roughly 2 mm2", "call it 890", which the prompt explicitly treats as stated
#: values). Not anchored at the start, because those hedges lead. Being liberal
#: here is safe: a qualitative answer with no digits at all ("the standard fan
#: curves") still yields None, and the guard against a number mined out of prose
#: is `verify_provenance` -- which checks the value against physical bounds and
#: against the artifact text -- not this regex.
_ANY_NUMBER = re.compile(r"[-+]?[.,]?\d[\d.,]*(?:[eE][-+]?\d+)?")


def _coerce_number(value) -> float | None:
    """Read a model's answer for one field as a number, or None if it isn't one.

    Both model backends need this and neither can assume the schema's type was
    honoured: the hosted model may answer null or a string where the schema says
    number, and the local backend now *asks* for strings (see
    `OLLAMA_EXTRACTION_SCHEMA`). Routing through `casecard.parse_number` rather
    than bare `float()` also means the model gets the same decimal-comma
    tolerance the deterministic parser has always had -- "2,4e-05" is a real way
    a Romanian-language artifact writes a number, and the prompt asks the model
    to quote its source, so a comma can reach here verbatim.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return _finite(float(value))
    text = str(value)
    number = parse_number(text)
    if number is not None:
        return _finite(number)
    m = _ANY_NUMBER.search(text)
    return _finite(parse_number(m.group().rstrip(".,"))) if m else None


def _finite(number: float | None) -> float | None:
    """None for nan/inf. A hole the string-valued schema opened: JSON numbers
    cannot be NaN, so `float(value)` never produced one while the schema said
    number -- but `float("NaN")` does, and the prompt's own rule is that a
    placeholder ("####", "NaN", "---") is a *missing* value, not a number."""
    return number if number is not None and math.isfinite(number) else None


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "params": {
            "type": "object",
            "description": "Only the parameters the artifact actually states. "
                           "Omit anything not present; never estimate. The 18 "
                           "hardware fields are optional overrides -- omitting "
                           "one is the default, not a gap to explain.",
            "properties": {
                name: {"type": "number",
                       "description": f"{name} in {casecard.ALL_UNITS[name]}"}
                for name in EXTRACTABLE_FIELDS
            },
            "additionalProperties": False,
        },
        "provenance": {
            "type": "object",
            "description": "For each extracted parameter, the exact substring of "
                           "the artifact it came from, including the original unit.",
            "properties": {name: {"type": "string"} for name in EXTRACTABLE_FIELDS},
            "additionalProperties": False,
        },
        "missing": {
            "type": "array",
            "description": "The 7 required operating parameters the artifact "
                           "states no number for. A qualitative phrase such as "
                           "'the standard fan curves' is NOT a value; a number "
                           "described in words ('roughly 2 mm2') IS one. Never "
                           "list a hardware field here -- absent hardware "
                           "fields simply are not in `params`, they are not "
                           "'missing'.",
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

Extract these 7 required operating parameters, converting to the canonical \
unit given -- every artifact should state all of these, and any it does not \
belongs in `missing`:
{chr(10).join(f'  {n} -- {casecard.CANONICAL_UNITS[n]}' for n in model.PARAM_NAMES)}

The circuit also has 18 optional hardware constants -- properties of the \
physical machine (a discharge coefficient, a breakaway torque, a cross-port \
leakage) rather than of the run being simulated. Almost no artifact states \
any of these; that is normal, not incomplete, and none of them belongs in \
`missing` when absent -- `missing` is only ever the 7 required fields above. \
Extract one only when the artifact states an explicit number for it:
{chr(10).join(f'  {n} -- {casecard.HARDWARE_UNITS[n]}' for n in model.HARDWARE)}

Rules:
- Convert units. m3/h -> L/min, m^2 -> mm^2, g/cm3 -> kg/m^3, Pa -> bar.
- A European decimal comma means a decimal point: "4,5" is 4.5.
- If the artifact does not state one of the 7 required parameters, list it in \
`missing`. Do not estimate, infer from context, or carry a value over from a \
similar case. A qualitative description of a load ("the standard fan curves", \
"sarcina e mica") is not a coefficient -- that parameter is missing.
- But a stated number is still a value when it is hedged or wrapped in \
description. "roughly 2 mm2", "about 55 lpm", "left wide at 11 mm2", "call it \
890", "pe la 70 l/min" all state their parameter -- extract the number and quote \
the phrase. A parameter is missing only when no number is given for it at all: \
words like "barely", "roughly" or "deliberately restrictive" beside a figure \
describe that figure, they do not withdraw it.
- The same rule applies to the 18 hardware constants for whether a stated \
number counts, but they are never "missing": an artifact silent on a hardware \
constant is the overwhelmingly common case, not an incomplete one. Extract a \
hardware constant only when it is unambiguously that constant, never as a \
guess at what a typical machine of this kind would have.
- `provenance` must quote the artifact verbatim, not paraphrase it.
- A corrupted or placeholder value (####, NaN, ---) is missing, not zero."""


def _repair_from_citation(field: str, quote: str) -> float | None:
    """Re-read one field's value from the model's own verbatim citation.

    **For a value the decoder corrupted, not one the model got wrong.** Ollama
    compiles the JSON schema to a grammar, and that grammar applies JSON's
    no-leading-zero rule to a number's *exponent*: having emitted `1.6e-0` there
    is no reachable second digit, so `1.6e-05` cannot be produced at all. The
    decoder truncates it to `1.6e-0` -- 1.6, five orders of magnitude out --
    and `verify_provenance` then correctly rejects it as physically impossible.
    The model had read the value fine and cited it verbatim; the field still came
    back as "not stated in the artifact". Measured on qwen2.5:7b against
    `data/logs/run-bigpump.log` and `data/logs/run-legacy.log`, whose `c_load_a`/`c_load_b`
    are the only fields written with a zero-padded exponent -- and the only ones
    ever lost this way.

    The citation is the repair, because the prompt already requires it to be
    verbatim and `verify_provenance` already checks that it is. So the fix is to
    parse it with the *deterministic* parser -- the same `_LINE`, `parse_number`
    and `normalise_unit` the rules backend uses, including its unit conversion,
    since a citation quotes the artifact's units rather than canonical ones.
    Nothing here trusts the model beyond the quote it is held to anyway.

    Two rejected alternatives, both measured, recorded so neither is retried:

    * Typing the value `string` in the schema sidesteps the number grammar and
      does fix the truncation -- but it roughly triples output length, because
      the model re-emits the unit inside every value ("8e-6 Nm/(rev/min)^2") and
      then over-runs on `provenance`. On `data/logs/note-ro.txt` that turned a clean
      62-second call (415 tokens, `done_reason=stop`) into a 153-second one that
      hit a 1024-token ceiling still generating and returned unparseable JSON.
      A wrong value became a hung request; that is not a trade worth making.
    * A `["number", "string"]` union does nothing at all: the grammar admits
      both branches, and the model still picks `number` and still truncates.
    """
    m = _CITED_VALUE.search(quote)
    if not m:
        return None
    value = parse_number(m.group("value"))
    if value is None:
        return None
    return normalise_unit(value, m.group("unit") or None)[0]


#: the trailing `value unit` of a citation. Deliberately *not* `_LINE`: the model
#: does not reliably quote a whole line. Against `data/logs/run-tidy.log` qwen2.5:7b
#: cited "= 62.4 L/min" -- the fragment after the separator, with no key -- so a
#: `_LINE`-based repair silently never fired and the truncated `c_load` values
#: were dropped exactly as if there had been no repair at all. Anchored at the
#: end so it reads the value, not some earlier number in a prose citation.
_CITED_VALUE = re.compile(
    r"(?P<value>[-+]?[\d.,]+(?:[eE][-+]?\d+)?)\s*"
    r"(?P<unit>[A-Za-zµ°^/³²\d]*(?:/[A-Za-z0-9^()/]+)?)\s*$")


def _same_significand(a: float, b: float) -> bool:
    """Whether two values differ only in their exponent (1.42 vs 1.42e-05).

    The signature of the decoder truncation this repair exists to undo, and the
    guard that keeps the repair from doing anything else. Without it, a citation
    that quotes a whole prose sentence ("ventilul A deschis la 4,5 mm2 iar
    ventilul B la 9 mm2") could hand back the wrong number entirely -- the last
    one in the sentence rather than the field's own. Requiring the digits to
    match means a repair can only ever restore a lost exponent.
    """
    digits = lambda x: re.sub(r"[^0-9]", "", f"{abs(x):.10e}".split("e")[0]).rstrip("0")
    return digits(a) == digits(b)


def foreign_card(text: str, artifact: str, case_id: str,
                 which: str) -> CaseCard | None:
    """A Case Card for an artifact from another domain, or None if it is ours.

    **The domain check belongs to the pipeline, not to one backend.** It used to
    live only in ``ingest_rules``: the two model backends built their CaseCard
    without ``domain`` or ``foreign``, so both defaulted to :data:`casecard.DOMAIN`
    and ``card.foreign_domain`` was always False. Choosing "Ollama only" in the
    UI therefore switched the check off, and the NASTRAN fixture came back with
    ``rho = 2700`` -- the MAT1 aluminium density -- recorded as the hydraulic
    fluid density, which is the precise failure ``casecard.FOREIGN_DOMAINS``
    exists to prevent. A refusal that depends on which extractor the operator
    happened to pick is not a refusal.

    Checked *before* the model is called, for the reason ``ingest_hybrid``
    already checks it there: there is nothing in a structural deck for the
    extractor to find, and asking anyway is how a language model gets talked
    into inventing seven parameters. It also saves a minutes-long inference on
    a file that was never going to produce a Case Card.
    """
    domain, foreign = casecard.detect_domain(text)
    if domain == casecard.DOMAIN:
        return None
    return CaseCard(
        case_id=case_id,
        source={"artifact": artifact,
                "ingested_by": f"{which} (foreign domain, model not asked)",
                "ingested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        params={},
        provenance={},
        missing=[p for p in model.PARAM_NAMES],
        domain=domain,
        foreign=foreign,
    )


def ingest_llm(text: str, artifact: str, case_id: str,
               effort: str = "medium") -> CaseCard:
    """Extract via Claude with a structured-output schema.

    Raises RuntimeError with an actionable message when the SDK or credentials
    are unavailable, so callers can fall back to `rules` rather than crash.
    """
    other = foreign_card(text, artifact, case_id, f"llm:{MODEL_ID}")
    if other is not None:
        return other

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
    # The same coercion `ingest_ollama` does, and for the same reason: the schema
    # says number, a model may still answer null or a string, and an unknown key
    # would have raised KeyError in `verify_provenance` below. None of those are
    # RuntimeError, so they escaped `dejasolve.analyse`'s handler and surfaced as
    # an HTTP 500 instead of a pipeline stage with a reason. A field we cannot
    # read as a number is missing, which is the honest outcome, not zero.
    params: dict[str, float] = {}
    for key, value in (payload.get("params") or {}).items():
        # widened from `model.PARAM_NAMES` -- the schema now offers all 25
        # extractable fields, and a model that used one of the 18 optional
        # hardware constants should not have it silently discarded here.
        if key not in EXTRACTABLE_FIELDS:
            continue
        number = _coerce_number(value)
        if number is not None:
            params[key] = number
    return CaseCard(
        case_id=case_id,
        source={"artifact": artifact, "ingested_by": f"llm:{MODEL_ID}",
                "ingested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "usage": {"input_tokens": response.usage.input_tokens,
                          "output_tokens": response.usage.output_tokens}},
        params=params,
        provenance={k: str(v) for k, v in (payload.get("provenance") or {}).items()
                    if k in EXTRACTABLE_FIELDS},
        missing=[p for p in model.PARAM_NAMES if p not in params],
        notes=str(payload.get("notes", "")),
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
    other = foreign_card(text, artifact, case_id, f"ollama:{name}")
    if other is not None:
        return other

    ok, detail = ollama_available()
    if not ok:
        raise RuntimeError(detail)

    body = json.dumps({
        "model": name,
        "stream": False,
        # Ollama >= 0.5 constrains generation to a JSON schema, the same schema
        # the Claude backend uses -- so both backends are held to one contract.
        # Its number grammar cannot emit a zero-padded exponent; that is repaired
        # from the citation afterwards, see `_repair_from_citation`.
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

    # Every value arrives as a string here by design (`OLLAMA_EXTRACTION_SCHEMA`),
    # and a local model may still answer null or leave a unit attached. Coerce
    # what is coercible and drop the rest -- a field we cannot read as a number
    # is missing, which is the honest outcome, not zero.
    params: dict[str, float] = {}
    for key, value in (data.get("params") or {}).items():
        # widened from `model.PARAM_NAMES` -- see the matching comment in
        # `ingest_llm`.
        if key not in EXTRACTABLE_FIELDS:
            continue
        number = _coerce_number(value)
        if number is not None:
            params[key] = number

    return CaseCard(
        case_id=case_id,
        source={"artifact": artifact, "ingested_by": f"ollama:{name}",
                "ingested_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "local": True},
        params=params,
        provenance={k: str(v) for k, v in (data.get("provenance") or {}).items()
                    if k in EXTRACTABLE_FIELDS},
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
    repaired = []
    # One message per reject path, not one message for all three. The bounds
    # check below and the citation checks fail for unrelated reasons, and until
    # this split they both reported "the cited source text is not in the
    # artifact" -- which sent a real investigation (a decoder mangling
    # `1.6e-05` into `1.6`, see `_string_valued`) looking at the citation, which
    # was verbatim and correct. A validator that names the wrong cause is worse
    # than one that names none.
    why: dict[str, str] = {}
    for field, value in list(card.params.items()):
        quote = card.provenance.get(field, "")

        # 1. Physically impossible values are inventions whatever the citation.
        #    Observed: the model answered "the standard fan curves" with 0.0.
        #    `field` can now be one of the 18 hardware constants too, which
        #    `PARAM_BOUNDS` has never covered -- falls back to
        #    `HARDWARE_BOUNDS`, the counterpart N3 added for exactly this.
        lo, hi = model.PARAM_BOUNDS.get(field) or model.HARDWARE_BOUNDS[field]
        plausible = lambda v: lo / 1000 <= abs(v) <= hi * 1000
        if not plausible(value):
            # Before rejecting: an implausible value whose citation is verbatim
            # and *does* parse to a plausible one is a decoder artifact, not an
            # invention -- the model read the artifact correctly and the grammar
            # mangled the number on the way out. Re-read the citation with the
            # deterministic parser. Narrow on purpose: this only ever runs on a
            # value already headed for rejection, so a healthy extraction can
            # never be rewritten by it.
            fixed = _repair_from_citation(field, quote) if quote else None
            if (fixed is not None and plausible(fixed) and norm(quote) in hay
                    and _same_significand(value, fixed)):
                card.params[field] = value = fixed
                repaired.append(field)
            else:
                dropped.append(field)
                why[field] = (f"{value:g} is far outside any physical range for "
                              f"this parameter ({lo:g} to {hi:g})")
                card.params.pop(field, None)
                card.provenance.pop(field, None)
                continue

        # 2. A citation supports a *number* only if it contains one. Quoting a
        #    qualitative phrase is the model showing it inferred rather than read.
        if not quote:
            reason = "no source was cited"
        elif norm(quote) not in hay:
            reason = "the cited source text is not in the artifact"
        elif not any(c.isdigit() for c in quote):
            reason = "the citation states no number"
        else:
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
        why[field] = f"{reason}, and the value's digits are not in the artifact"
        card.params.pop(field, None)
        card.provenance.pop(field, None)

    if repaired:
        card.notes = (f"{card.notes} [recovered {', '.join(repaired)} from the "
                      f"cited source: the decoder truncated the exponent]").strip()
    if dropped:
        card.missing = [p for p in model.PARAM_NAMES if p not in card.params]
        detail = "; ".join(f"{f} -- {why[f]}" for f in dropped)
        card.notes = f"{card.notes} [dropped {detail}]".strip()
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

    # Hardware constants (§0b) are never "missing" -- they are optional
    # overrides, so the loop above never looks for them. But the model was
    # already called to fill a required field, at no further cost, and if it
    # also found one of the 18 in the same pass, discarding it here would be
    # the same gap N3 closed for the ollama/llm-only backends, reappearing in
    # the one path that reaches the model conditionally. `card.params` is
    # checked first so rules keeps precedence over the model where both
    # found the same field, consistent with "parser first" everywhere else.
    for field in model.HARDWARE:
        if field not in card.params and field in model_side.params:
            card.params[field] = model_side.params[field]
            card.provenance[field] = model_side.provenance.get(field, "")
            filled.append(field)

    card.missing = [p for p in model.PARAM_NAMES if p not in card.params]
    card.source["ingested_by"] = (
        f"rules + {model_side.source['ingested_by']}" if filled
        else f"rules (+{which}, nothing added)")
    card.source["filled_by_model"] = filled
    # Only when the model actually contributed something -- previously
    # unconditional, so a model note about fields it dropped
    # (verify_provenance's "[dropped ...]") could land on the card even when
    # none of those fields, or anything else the model found, ended up in
    # `card.params` at all. A note describing a contribution
    # that was not made is not context, it's noise attributed to the wrong card.
    if model_side.notes and filled:
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
    ap.add_argument("--logs", type=Path, default=Path("data/logs"))
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
