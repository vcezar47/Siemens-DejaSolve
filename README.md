# Déjà Solve

Warm-start a solver's initialisation from the physically-nearest case it has
already solved, instead of starting from zero every time.

Siemens Summer School 2026 · domain: *Digital Twins & Platforms*

- [DEJA_SOLVE_PLAN.md](DEJA_SOLVE_PLAN.md) — the plan, the pitch and the presentation notes
- [phases/](phases/) — what was actually built in each phase, and what was rejected

## Reproduce every number

```bash
python run_all.py
```

Writes `archive/cases.jsonl`, `results.json` and `figs/convergence.png`.
Runs in a few seconds. No number in the deck is typed by hand — if it is not in
`results.json`, it does not go on a slide.

It ends by printing the **Phase 1 summary hash** — `2bdd767bfe02fd5d` — over the
quotable part of `results.json`, skipping timings and the timestamp so it is
stable across runs and machines. If that string changes, a number on a slide
changed with it. Ingest is scored on the parser alone by default; add
`--score-models` to score the local model too (minutes per prose artifact).

Requires Python 3.11+, numpy and matplotlib (`pip install -r requirements.txt`).

## What is here

| file | what it does |
|---|---|
| `model.py` | The physics: a hydraulic manifold driving two motors against Stribeck friction. 7 nonlinear equations, analytic Jacobian, damped Newton, dynamic stability |
| `sweep.py` | Runs a 400-case parameter sweep and keeps what converged — this is the archive |
| `bench.py` | On 200 *fresh* cases: solve cold, retrieve the nearest archived case, solve warm. Writes `results.json` |
| `verifier.py` | Layer 3: decides whether reusing a case is legitimate, and whether the answer is an operating point at all |
| `fold.py` | The circuit variant where a warm start *can* be silently wrong, and the naive-vs-verified experiment |
| `casecard.py` | Layer 1's output record: canonical units, quoted provenance, explicit absence |
| `ingest.py` | Turns a run artifact into a Case Card — deterministic parser, a local model via Ollama, or Claude, all behind one interface |
| `make_logs.py` | Five messy artifacts with exact ground truth |
| `dejasolve.py` | The pipeline: `analyse()` returns a structured trace; the CLI and the service both render it |
| `app.py` + `static/index.html` | **The demo UI** — FastAPI service, single self-contained page |
| `plot_convergence.py` | Draws the Phase 1 figure from `results.json` |
| `run_all.py` | All of it, in order |

## The UI

```bash
python app.py
```

Then open <http://127.0.0.1:8000>. Pick one of the five artifacts (or drop a file
onto the box), press **Analyse**, and the six pipeline stages resolve in order —
ingest, units, retrieve, verify, solve, admissible — each with its own verdict.
The headline is the number: **8 → 4 Newton iterations, same answer to 2.3e-13**.

It is a **service with a page attached**, not a notebook app: the page is a
client of `POST /api/analyse`, which is the same endpoint a Study Manager sweep
would call. `GET /api/health`, `GET /api/samples`, and OpenAPI docs at `/docs`
come with it. No secrets needed, and nothing leaves the machine: the page offers
the parser, the local model, and the hybrid of the two. Hosted Claude stays a
valid backend for the API and the CLI but is deliberately absent from the page —
an option that contradicts "your run data stays on your network" is the one
thing on screen an engineer would ask about. With no model reachable at all,
ingest falls back to the parser and the demo still runs.

## The end-to-end run (CLI)

```bash
python dejasolve.py --all
```

Five artifacts — a tidy solver log, an older banner log in SI units, a truncated
log, an English email, a Romanian note — go through ingest, retrieval, the
verifier, a warm solve, and an admissibility check:

```
run-tidy.log      warm_started         8 -> 4 iterations, from sweep-0212
run-legacy.log    warm_started         8 -> 4 iterations, from sweep-0125
run-truncated.log refused_incomplete   missing p_crack
```

The refusals are the interesting half. A missing parameter is named, the nearest
archived case is located on the parameters that *were* stated, its value is shown
— and **not applied**. A misread unit (`7.8 m2` → 7.8e+06 mm²) is caught as
implausible before it reaches retrieval.

**Ingest accuracy** (5 artifacts, 35 fields, scored against ground truth;
inventing a value counts as a miss):

| | parser | local model | **hybrid** |
|---|---|---|---|
| machine logs (3) | **21/21** | 15/21 | **21/21** |
| prose (English email, Romanian note) | 2/14 | **12/14** | **12/14** |
| total | 23/35 | 27/35 | **33/35 (94%)** |
| invented | 0 | 0 | **0** |

The two fail on *disjoint* inputs — the parser is perfect on machine logs and
scores 0/7 on the Romanian note; the model is the reverse. So the default
backend runs the parser first and calls a model only for the fields it could not
fill. A well-formed log never reaches the model and returns in 1.6 s.

**Ingest has its own verifier.** The local model initially invented 3 values —
answering *"the standard fan curves"* with `c_load = 0.0`. A citation now
supports a number only if it contains a digit, values outside the physical
envelope are dropped, and a missing citation is accepted only when the value's
digits are in the artifact. That took inventions to zero *and* raised the score.

```bash
python ingest.py --compare        # scores every available backend
```

> Runs locally by default (`qwen2.5:7b` via Ollama) — nothing leaves the machine,
> and no internet is needed. The Claude backend is written but **untested** here.
> On a 4 GB GPU a prose artifact takes 1–3 minutes; machine logs are unaffected.

## The model

```
pump ──┬───────────────────────────── relief valve ──> tank
       │
      [p1]  manifold
       ├─ valve_a ─[p2a]─ MOTOR a ─[p3a]─ return ─> tank
       └─ valve_b ─[p2b]─ MOTOR b ─[p3b]─ return ─> tank
```

Unknowns are `[p1, p2a, p3a, w_a, p2b, p3b, w_b]` — five pressures and two
shaft speeds. Steady state is a 7×7 nonlinear system: flow balance at each
node, torque balance at each shaft. That is the *initialisation problem*, and
warm-starting it does not change the physics of the case — only the guess
handed to Newton.

It is hard for two ordinary reasons: turbulent orifice flow whose slope blows
up as Δp → 0, and Stribeck friction, whose decaying branch has negative slope
and narrows the basin of attraction around the operating point.

Swept per case: pump delivery, both valve areas, both load coefficients, relief
cracking pressure, fluid density.

## Result

400-case archive, 200 fresh query cases, 1-nearest-neighbour retrieval on the
normalised setup vector. Same residual, same Jacobian, same tolerance — the
only thing that differs is the starting guess.

| | cold start | warm start |
|---|---|---|
| mean Newton iterations | 8.3 | 4.9 |
| total iterations | 1631 | 953 |
| runs that never converged | 4 / 200 | 0 / 200 |

**42% fewer iterations**, every cold-start failure rescued, and the answers
agree to 4e-08 bar and 3e-08 rev/min across all 196 cases where both converged.

### One caveat worth stating out loud

The failure count depends on how good the solver's Jacobian is, so `bench.py`
reports that sensitivity instead of choosing a flattering setting:

| solver Jacobian | cold failures | warm failures |
|---|---|---|
| exact analytic | 4 / 200 | 0 / 200 |
| finite difference, `sqrt(eps)` step | 2 / 200 | 0 / 200 |
| finite difference, coarse step | 45 / 200 | 0 / 200 |

The headline uses the **analytic** Jacobian on purpose: it is the best case for
the cold baseline, so the advantage measured against it is real. The iteration
saving is stable at ~42% in all three.

## The verifier (Phase 2)

A converged answer can still be wrong. The steady state is the equilibrium of a
dynamic system, and a root on the Stribeck downslope is **dynamically
unstable** — it satisfies the equations to 1e-8 and no machine can sit there.
Newton cannot tell; the eigenvalues can.

The base circuit above has a *unique* root everywhere in its envelope — checked
with a 16-seed multi-start over all 400 cases, not assumed. So it cannot
demonstrate that failure mode. `fold.py` builds the same equations around a
smaller motor (5 cm³/rev), where the operating point falls into the Stribeck
fold and the torque balance picks up three roots.

200 fresh cases on that circuit:

| | naive retrieval | verified |
|---|---|---|
| valid operating point | 147 | **200** |
| **unstable root (silently wrong)** | **4** | **0** |
| no answer | 49 | **0** |
| total Newton iterations | 1571 | 2130 |

**4 silently wrong answers → 0, for +36% solver work.** The gate is built from
physics rather than a distance threshold, because setup distance turned out to
predict transfer cost with r = 0.18 — barely at all.

## Not done yet

Phase 4 is Docker and the AWS architecture slide. The container needs no
secrets — the full demo runs on the deterministic ingest backend.

The Streamlit/FastAPI UI was deliberately deferred: it could not be tested here,
and shipping it alongside the untested LLM path would have put two unverified
components in a live demo. It is a thin shell over `dejasolve.run()`, which
already returns a structured outcome.
