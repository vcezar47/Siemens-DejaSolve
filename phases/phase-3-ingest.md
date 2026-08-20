# Phase 3 — Ingest and the end-to-end run

**Planned:** Fri 21 – Sun 23 Aug 2026 · **Gate met:** Mon 17 Aug, ahead of schedule
**Gate:** an end-to-end run from a messy log file → ✅ `python dejasolve.py --all`

## What was built

| file | role |
|---|---|
| [`../casecard.py`](../casecard.py) | The Case Card: canonical units, provenance, explicit absence, plausibility check |
| [`../ingest.py`](../ingest.py) | Layer 1, two backends (`rules`, `llm`) behind one interface, plus the accuracy measurement |
| [`../make_logs.py`](../make_logs.py) | Five run artifacts with exact ground truth |
| [`../dejasolve.py`](../dejasolve.py) | The whole system in one path: artifact → Case Card → retrieval → verifier → warm solve → admissibility |

## The measurement that justifies Layer 1

The plan claims an LLM belongs in the architecture for exactly one job:
unstructured → structured on ingest. That claim is now measured rather than
asserted. Five artifacts, 35 fields, scored against ground truth — a field
counts as correct only if it is within 1% **or** was correctly reported missing:

| artifact | style | rules backend |
|---|---|---|
| `run-tidy.log` | machine-written key/value | **7/7** |
| `run-legacy.log` | banner log, SI + mixed units | **7/7** |
| `run-truncated.log` | truncated, `####` in a value | **7/7** |
| `note-email.txt` | English prose email | **2/7** |
| `note-ro.txt` | Romanian prose, decimal comma | **0/7** |
| | | **23/35 (66%), 0 invented** |

**On machine-written logs the deterministic parser needs no LLM at all** — it
handles `4.0908 m3/h → 68.18 L/min`, `7.800e-06 m2 → 7.8 mm^2`,
`0.874 g/cm3 → 874 kg/m^3`, and correctly reports the corrupted `p_crack = ####`
as missing rather than parsing it as zero.

**On prose it recovers 2 of 14 fields.** That gap is the argument for the LLM,
and it is the honest form of the plan's Q&A answer: *"if you delete it, the
system still works — it just needs clean metadata, which is the assumption that
fails in practice."* Now there is a number attached to "fails in practice".

Note the 2/7 on the email is not partial parsing — the parser extracts nothing
from prose and scores 2 only because the email genuinely does not state the two
load coefficients, and reporting them missing is the correct answer.

## Never invent a value

Every backend is scored on **invented** fields as well as correct ones, and both
are currently zero. This is the ingest-layer version of the whole project's
thesis: a Case Card that guesses a plausible number is worse than one that says
it does not know, because the guess propagates into the archive and every future
retrieval that touches it.

The fixtures make this concrete. `note-email.txt` says *"the standard fan curves
on both shafts"* and `note-ro.txt` says *"sarcina pe arborele A e mica"* — those
are descriptions of a load, not coefficients. The LLM prompt states the rule
explicitly (*"a qualitative description of a load is not a coefficient — that
parameter is missing"*), and the schema has a `missing` array so the model has
somewhere to put the answer "not stated" rather than being forced to emit a
number.

## Three ways to refuse, and saying which

`dejasolve.py` stops the run at three different layers, and the distinction is
the product:

| refusal | trigger | what the operator sees |
|---|---|---|
| `implausible` | a value survives ingest but is orders of magnitude out | *"A_valve_a = 7.8e+06 mm^2 is off by orders of magnitude (sweep range 0.6 to 12) -- likely a unit error"* |
| `incomplete` | the artifact never stated a parameter | names the missing fields, locates the nearest archived case on the parameters that *were* stated, shows what that case used — **and does not apply it** |
| `inadmissible transfer` | retrieval found a case, the verifier refused it | the verifier's one-line reason, then a cold-start fallback |

The incomplete path is the one worth demonstrating. For `run-truncated.log` it
reports that `p_crack` is missing, finds `sweep-0260` 0.24 away on the six stated
parameters, shows that case used `p_crack = 253.9 bar`, and then refuses to use
it: *"A missing parameter is a question for the engineer, not a value to borrow
-- that is how a wrong answer gets in."* Auto-filling there would be the exact
silent wrongness Phase 2 exists to prevent, arriving through the front door.

## End-to-end result

```
run-tidy.log      warm_started         8 -> 4 iterations, from sweep-0212
run-legacy.log    warm_started         8 -> 4 iterations, from sweep-0125
run-truncated.log refused_incomplete   missing p_crack
note-email.txt    refused_incomplete   (rules backend cannot read prose)
note-ro.txt       refused_incomplete   (rules backend cannot read prose)
```

A messy artifact goes in; a verified, warm-started, admissibility-checked answer
comes out, with every step explained in plain English. Same answer as the cold
solve to 2.3e-13, in half the iterations.

## Local models: measured, and the result changed the design

A local model was added (`ollama` backend, `qwen2.5:7b`, models stored on E:)
after the question came up of whether a hosted API was the right dependency.
**The argument for it is not cost** — the hosted calls here are fractions of a
cent. It is **confidentiality**: run artifacts are customer simulation data, and
"it never leaves your network" is an answer an engineer can take to a manager.
It also makes the demo work with no internet. See the new Q&A entry in plan §9.

The first measurement was a surprise and is the most useful result in this phase:

| artifact | rules | ollama 7b (first run) |
|---|---|---|
| note-ro.txt (Romanian prose) | 0/7 | **7/7** |
| run-legacy.log | **7/7** | 4/7 |
| run-tidy.log | **7/7** | 5/7 |
| run-truncated.log | **7/7** | 4/7 **+1 invented** |
| note-email.txt | 2/7 | 3/7 **+2 invented** |
| **total** | **23/35, 0 invented** | **23/35, 3 invented** |

**Identical totals, opposite strengths, and the local model invented 3 values.**
Neither backend is better; they fail on *disjoint inputs*. That forced two
changes:

### 1. Hybrid ingest — parser first, model only for the gaps

The parser is perfect and instant on machine logs; the model is the only thing
that can read prose. So run the parser first and call the model only for the
fields it could not fill. A well-formed log **never reaches the model at all**,
which is also what makes the demo fast: `run-tidy.log` went from ~3 minutes to
**1.6 seconds**.

### 2. An anti-invention check — Layer 1 gets its own verifier

Inventing a value is this project's own failure mode appearing in ingest, so it
gets the same treatment as everywhere else: verify, don't trust. Looking at what
the model actually produced showed two distinct problems:

```
c_load_a = 0.0    cited: 'the standard fan curves'   <- real quote, invented number
Q_nom    = 55.0   cited: ''                          <- correct value, no citation
```

So the rule cannot be "quote must match" (drops the correct values) or "quote
must exist" (passes the invented ones). What works, and is fully deterministic:

- a value outside a generous multiple of the physical envelope is dropped
  (`c_load = 0.0` is not a reading of anything);
- a citation supports a number only if the citation **contains a digit** —
  quoting a qualitative phrase is the model showing it inferred rather than read;
- a missing citation is not proof of invention: accept if the value's own digits
  appear in the artifact.

A model can talk its way past an instruction. It cannot talk its way past this.

### Final measurement

| artifact | rules | ollama | **hybrid** |
|---|---|---|---|
| note-email.txt | 2/7 | 5/7 | **5/7** |
| note-ro.txt | 0/7 | 7/7 | **7/7** |
| run-legacy.log | **7/7** | 5/7 | **7/7** |
| run-tidy.log | **7/7** | 5/7 | **7/7** |
| run-truncated.log | **7/7** | 5/7 | **7/7** |
| **total** | 23/35 (66%) | 27/35 (77%) | **33/35 (94%)** |
| **invented** | 0 | **0** | **0** |

The anti-invention check took `ollama` from 3 invented values to **0** and *also*
raised its score (21→27), because the same check stopped it discarding correct
values that simply lacked a citation.

The two remaining misses are the valve areas in the English email, which the
model did not read. That is a reading failure, not a fabrication — and the
system reports them missing rather than guessing.

**End to end from the Romanian note:** ingest 7/7 via `rules + ollama:qwen2.5:7b`
→ retrieve `sweep-0256` → verifier admits → **8 → 4 iterations, same answer to
2.8e-14** → stable operating point.

### The speed caveat, stated plainly

The demo machine has an RTX 3050 with **4 GB VRAM**; `qwen2.5:7b` at Q4 needs
~4.7 GB, so Ollama offloads only **12 of 29 layers** to the GPU and the rest runs
on CPU. A prose artifact costs **~1–3 minutes**. Machine logs are unaffected
(the hybrid path never calls the model). For the live demo, either run the prose
case ahead of time, or demo the instant path and show the prose result as a
recorded number. A 3B model would fit entirely in VRAM and be far faster, at some
cost in unit-conversion accuracy — untested, and worth measuring if the live
prose demo matters.

## The Claude path is written but UNTESTED

**State this plainly rather than letting it be discovered.** This machine has no
`anthropic` SDK, no `ANTHROPIC_API_KEY`, and no `ant` CLI, so the `llm` backend
has never executed. What exists is written against the current API:
`claude-opus-5`, structured outputs via `output_config.format` with a strict JSON
schema, `effort: medium`, refusal handling on `stop_reason`, and usage recorded
into the Case Card's provenance.

Two consequences, both deliberate:

1. **`auto` is the default backend** and falls back to `rules` when credentials
   are absent, printing why. The pipeline never hard-depends on the network —
   which also means the Phase 4 container has no required secret.
2. **The comparison table degrades honestly** — with no credentials it scores the
   rules backend only and says so, rather than silently reporting one column.

Before the LLM column can go on a slide: `pip install anthropic`, set a key, then
`python ingest.py --compare`. Until that runs, **the LLM numbers do not exist and
must not be quoted.**

## The UI — FastAPI, not Streamlit

Built the same day, once it turned out **FastAPI 0.136 and uvicorn 0.46 were
already installed** on this machine. That removed the objection that had
deferred it: Streamlit would have been an untestable second unknown next to the
untested LLM path, but FastAPI could be run and driven here.

`python app.py` → <http://127.0.0.1:8000>.

**Why a service and not a notebook-style app**, in the order the reasons matter:

1. **The pitch is a platform.** The project is registered under *Digital Twins &
   Platforms* and slide 8 is "why it's a platform". What a platform exposes is an
   API. `POST /api/analyse` is the same endpoint a Study Manager sweep would
   call; the page is a client of it. A Streamlit script with widgets would have
   quietly contradicted the pitch.
2. **It maps onto the Phase 4 architecture slide** 1:1 — a container behind an
   HTTP endpoint, which is what ECS/Batch actually runs.
3. **The image stays small** — uvicorn plus one HTML file, not Streamlit's
   ~50-package tree.
4. **No build step, no CDN, no npm.** Inline CSS and vanilla JS in a single
   file, so it works on a conference-room machine with no internet.

### The refactor that made it honest

`dejasolve.py` previously printed as it computed, so a service would have had to
re-implement the pipeline and immediately start drifting from the CLI. It was
split into:

- `analyse()` — **pure**, returns a structured trace of six stages, prints nothing
- `render()` — the CLI's text view of that trace
- `app.py` — the HTTP view of the same trace

One implementation, two front ends. `--json` on the CLI emits the raw trace.

### What the page shows

Six stages resolve in order with their own verdicts, and **the refusals are
styled as first-class outcomes rather than errors** — which is the whole thesis
of the project rendered in CSS. For `run-truncated.log` the Retrieve stage turns
red, names the missing `p_crack`, shows that the nearest case on the six stated
parameters (`sweep-0260`, 0.24 away) used 253.941 bar, and prints the refusal
line underneath. Downstream stages grey out as `skipped` rather than vanishing,
so the audience sees exactly where the pipeline stopped.

Verified in a real browser, not just asserted: happy path renders `8 → 4` with
`same answer to 2.3e-13` and six green stages; `run-truncated.log` renders
ok/skipped/refused/skipped/skipped/skipped with the suggestion block; `note-ro`
renders seven `NOT STATED IN ARTIFACT` rows.

One thing that fix surfaced: with zero parameters extracted, the Units stage was
reporting "ok — every value is within a physical range", vacuously passing a
check on an empty set. It now reports `skipped — nothing to check`. Small, but
it is exactly the kind of detail an engineer in the audience notices.

### Still deferred

Nothing else. If the demo machine has no Python, that is a Phase 4 (container)
problem, not a UI one.

## What Phase 4 inherits

- No required secrets: the container runs the full demo on the `rules` backend.
- `pip install -r requirements.txt` still covers everything (`anthropic` is
  optional and imported lazily inside `ingest_llm`).
- `run_all.py` now regenerates the fixtures too, so a clean machine has `logs/`
  before `dejasolve.py --all` is run.
- **Console encoding was a real bug, not a cosmetic one.** A box-drawing
  character in the report crashed the demo with `UnicodeEncodeError` on the
  Windows cp1252 console. All printed output is now ASCII, and there is an AST
  check in the phase history that catches a regression. Worth re-running before
  the demo on whatever machine it will be presented from.

## Superseded after Phase 1's third arm

The demo output recorded above (`8 -> 4 iterations`) is the flat-start
comparison. After the nominal baseline was added to Phase 1 — see
[*A third arm*](phase-1-the-number.md#a-third-arm-the-nominal-baseline) —
`dejasolve.py` and the web headline report all three:

```
run-tidy.log      warm_started    8 cold / 7 nominal -> 4 warm iterations
```

The pipeline, the refusals and the Case Card work are unchanged; only the
number the demo quotes is wider. **One open item:** when the verifier refuses
the transfer, the fallback is still the flat cold start (8 iterations) even
though the nominal guess (7) is available for free and involves no archive.
The headline now says so out loud rather than hiding it, but the fallback
itself has not been switched — it changes Act 3's behaviour, so it is a
deliberate decision rather than a tidy-up.

---

## Addendum — 20 Aug: a Case Card is a record *of a kind of model*

Driven by §0b, where the engineers asked for something general and talked mostly about Simcenter 3D. A
seventh fixture, `logs/part-bracket.log`, is an NX Nastran solver log with a bulk-data echo — a real artifact
shape from a domain this project does not solve.

**What was added**

- `casecard.DOMAIN` and `FOREIGN_DOMAINS`: a Case Card now records *which kind of model* produced it, detected
  by marker count (`GRID`, `CQUAD4`, `PSHELL`, `MAT1`, `BEGIN BULK`, …) rather than by file extension.
- `detect_domain()` also reads what is legible — solution sequence, title, modulus, Poisson ratio, thickness,
  element counts — so a refusal can be *specific*. "This is a 3D structural deck, 6 nodes, linear static" and
  "I could not read your file" are different sentences, and only one tells an engineer what to do next.
- A domain gate in `dejasolve.analyse()`, placed **before the unit check**. Plausibility is judged against a
  schema; if the schema does not apply, "off by orders of magnitude" is the wrong complaint.
- `ingest_hybrid` returns early on a foreign artifact: no model is called, because there is nothing to extract
  and asking anyway is how one gets talked into inventing seven fields.

**The finding worth quoting.** The log's banner reads `Density ....: 2.70E-09 tonne/mm^3`, and `SYNONYMS` maps
`density` onto `rho`. Without the domain check the Case Card records aluminium as the hydraulic fluid density.
The card now reports it instead:

    would_have_been_mismapped   rho <- 2.70E-09 tonne/mm^3

**One collision, and no synonym was added to manufacture it.** This schema has seven fields and exactly one
shares a name with anything in a structural log. The general claim is not "there is one collision" — it is
that field names are domain-scoped and the count grows with the schema, which is why this matters more at the
hundreds of parameters phase 1c is about. The unit gate would have caught *this* value by luck; it would not
have caught one that looked plausible.

**The Ingest stage stays green.** Ingest did not fail — it succeeded at the only thing available to succeed
at. Marking it blocked would have said the parser broke, when what happened is that it correctly identified an
artifact whose fields do not exist here.

**Re-verified 20 Aug, after these changes.** `python ingest.py --compare` with the local model reachable
reproduces the Phase 3 table exactly — rules 23/35, ollama 27/35, **hybrid 33/35 (94%)**, and **0 invented on
all three**. That last figure is the one that mattered here: `ingest_rules` and `ingest_hybrid` were both
edited for the domain gate, and the ingest verifier still holds. It is also the first execution of the model
path since 17 Aug, so the number on the slide is measured rather than remembered.

**Not scored.** Like `run-bigpump.log`, it carries `scored=False`, so the ingest accuracy figure is still
5 artifacts / 35 fields / 23 for the parser. It exists for the gate, not for the parser.

**Rejected**

- **Adding a "material density" synonym so the collision would fire.** Introducing the bug in order to
  demonstrate catching it. The fixture uses the wording that genuinely collides with the table as it stands.
- **Marking Ingest as failed on a foreign artifact.** It would blame the wrong component.
- **Anything that implies 3D support.** No mesh is read, no field is mapped, nothing structural is solved. The
  transfer adapter is the next-steps item, and the demo shows the boundary rather than crossing it.
