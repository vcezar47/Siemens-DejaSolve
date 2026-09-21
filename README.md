# Déjà Solve

Warm-start a solver's initialisation from the physically-nearest case it has
already solved, instead of starting from zero every time — and check, before and
after the solve, that reusing that case was legitimate.

Siemens Summer School 2026 · domain: *Digital Twins & Platforms* · **finished and presented**

Four layers: **ingest** (a messy run artifact becomes a structured Case Card),
**retrieve** (the best of the nearest solved cases, walked toward the new setup
along the solution manifold), **verify** (physics-based gates that warn or block
with a reason, before *and* after the solve), and **runtime** (Docker, with an
AWS build behind switches that default to off).

## At a glance

Everything below is reproducible from the repo — see [Reproduce every number](#reproduce-every-number).

| | |
|---|---|
| **Newton iterations** (200 fresh cases, 395-case archive) | 8.3 cold → 7.1 nominal → **3.0 warm** |
| **vs a competent nominal guess** | **57% fewer** (63% fewer than a flat start, on total iterations) |
| **Runs that never converged** | 4 / 200 cold → **0 / 200** warm |
| **Answer** | identical to 4e-08 bar / 4e-08 rev/min — the warm start changes the guess, never the physics |
| **The app as shipped** (shortlist → gate → rank → second-order) | 3.04 mean iterations, 57.3%, 0 failures |
| **Fold circuit: silently wrong answers** | 4 → **0**, for +1% solver work |
| **Ingest** (5 artifacts, 35 fields) | **35 / 35**, 0 invented values |
| **Archive** | 395 solved + 5 failed runs — the failures are kept on purpose |

**The claim this project tested hardest is its own speed number.** A hand-derived
per-branch initialiser (no archive, no solve) reaches 2.70 iterations on the base
circuit and beats retrieval there; retrieval's case is that it needs no
derivation and applies to a circuit it has never seen. See
[The baseline that beats the archive](#the-baseline-that-beats-the-archive).

- [DEJA_SOLVE_PLAN.md](docs/DEJA_SOLVE_PLAN.md) — the plan, the pitch and the presentation notes
- [phases/](docs/phases/) — what was actually built in each phase, and what was rejected
- [docs/architecture.md](docs/architecture.md) — the two services that exist, what each layer becomes at scale, and what is not built
- [docs/aws-deployment-plan.md](docs/aws-deployment-plan.md) — the CloudFormation build of the "at scale" row
- [docs/known-bugs.md](docs/known-bugs.md) — the bug sweep of the app, with what was fixed and what was declined

## Reproduce every number

```bash
python run_all.py
```

Writes the archive to `data/archive/` (`cases.jsonl`, `failures.jsonl`), every
result file to `results/` (`results.json`, `surrogate_results.json`,
`fold_results.json`, `failure_zone_results.json`, `dimensionality_results.json`,
`wide_sweep_results.json`, …) and the figures to `results/figs/`.
Runs in about half a minute. No number in the deck is typed by hand — if it is not
in `results/results.json`, it does not go on a slide.

It ends by printing the **Phase 1 summary hash** — `830da3e6a4480676` — over the
quotable part of `results.json`, skipping timings and the timestamp so it is
stable across runs and machines. If that string changes, a number on a slide
changed with it. Ingest is scored on the parser alone by default; add
`--score-models` to score the local model too (minutes per prose artifact).

Requires Python 3.11+, numpy and matplotlib (`pip install -r requirements.txt`).
`python -m benchmarks.selftest` runs alone in seconds — the analytic Jacobian and `∂F/∂p`
against central differences (worst relative error 3e-08), the solution Hessian's
symmetry, and a check that hardware defaults change nothing. 5 / 5 pass.

Not in `run_all.py`, so not covered by the hash: `experiments/bench_app_path.py`, `experiments/geometry.py`,
`experiments/manifold.py`, `experiments/coupled.py` and `python -m benchmarks.agent_select --model ...`.

## Project layout

```
README.md  Dockerfile  docker-compose.yml  requirements.txt
run_all.py  app.py       entry points: reproduce every number · start the demo UI

dejasolve/               the product
  model.py casecard.py verifier.py ingest.py sweep.py pipeline.py
  service.py static/     the FastAPI service and the page it serves
  cloud/                 Aurora retrieval, SQS ingest worker, archive sync (all off by default)
benchmarks/              everything run_all.py runs: bench, surrogate, fold, dimensionality,
                         failure_zone, wide_sweep, agent_select, selftest, viz, make_logs, plots
experiments/             built and measured, not in run_all.py: geometry, manifold, coupled,
                         topk, bench_app_path
results/                 every generated *.json, and figs/
data/                    archive/ (the solved and failed runs) and logs/ (the seven test artifacts)
docs/                    architecture, AWS plan, known bugs, the plan, phases/, presentation/
infra/cloudformation/    the AWS templates
```

Run modules from the repository root: `python -m dejasolve --all`,
`python -m benchmarks.bench`, `python -m experiments.topk`. Only `run_all.py` and
`app.py` are run as scripts.

## What is here, file by file

| file | what it does |
|---|---|
| `dejasolve/model.py` | The physics: a hydraulic manifold driving two motors against Stribeck friction. 7 nonlinear equations, analytic Jacobian, damped Newton, dynamic stability |
| `dejasolve/sweep.py` | Runs a 400-case parameter sweep. What converged becomes the archive; what failed is kept too, in `data/archive/failures.jsonl` |
| `benchmarks/bench.py` | On 200 *fresh* cases: solve from a flat start, a nominal guess, the nearest archived case verbatim, and the same case transferred first-order, ranked, second-order (`model.solution_hessian`, `model.transfer_start_second_order`) and by simplex. Writes `results/results.json` |
| `experiments/bench_app_path.py` | The number as the *app* produces it — `Archive.select` then `Archive.warm_start`, gate and fallback included — over `benchmarks/bench.py`'s own 200 queries. Writes `results/bench_app_path_results.json`. Not in `run_all.py` |
| `benchmarks/surrogate.py` | The *other* source of a warm start: a quadratic response surface fitted to the archive, predicting a state instead of recalling one. The PhysicsAI arrow, at laptop scale |
| `benchmarks/dimensionality.py` | What happens to retrieval when the Case Card carries hundreds of parameters instead of 7 — and which gate stops working |
| `benchmarks/failure_zone.py` | Are the failed runs worth keeping? Tests whether proximity to a failure predicts anything — with the controls that decide whether it is real |
| `benchmarks/selftest.py` | The invariants everything rests on: the analytic Jacobian against central differences, and hardware defaults that must change nothing |
| `benchmarks/wide_sweep.py` | The same measurement on 25 real parameters and six machine variants — where the hardware rule finally becomes reachable |
| `experiments/topk.py`, `benchmarks/agent_select.py` | Two claims measured and declined: walking deeper into the archive by distance, and letting a model (or a physics heuristic) choose among the candidates. See *Claims tested and declined* |
| `experiments/geometry.py`, `experiments/manifold.py`, `experiments/coupled.py` | Harder circuits, none of them shipped: pipe geometry (12 unknowns), an N-branch manifold (up to 32 unknowns), and a shared-return circuit with a bistable band. Where the scaling claim and the decomposed baseline were tested. Not in `run_all.py` |
| `benchmarks/viz.py` | Projection data for the 3D views — the archive, a matched pair, and the Newton race. Cross-checks its iteration counts against `results.json` and refuses to write if they disagree |
| `dejasolve/verifier.py` | Layer 3: decides whether reusing a case is legitimate, and whether the answer is an operating point at all. Verdicts carry a severity — a *risk* the engineer may override, or a *fact* they may not |
| `benchmarks/fold.py` | The circuit variant where a warm start *can* be silently wrong, and the naive-vs-verified experiment |
| `dejasolve/casecard.py` | Layer 1's output record: canonical units, quoted provenance, explicit absence |
| `dejasolve/ingest.py` | Turns a run artifact into a Case Card — deterministic parser, a local model via Ollama, or Claude, all behind one interface |
| `benchmarks/make_logs.py` | Seven messy artifacts — five with exact ground truth, plus two built to trip the verifier |
| `dejasolve/pipeline.py` | The pipeline: `analyse()` returns a structured trace; the CLI and the service both render it. Retrieval is `Archive.select` — shortlist the 5 nearest, filter by the verifier, rank the survivors by predicted start error — and the start is transferred second-order |
| `dejasolve/service.py` + `dejasolve/static/` | **The demo UI** — FastAPI service and the page: `index.html` (markup), `app.css`, `app.js`, and a vendored three.js for the WebGL machine view. Nothing is fetched from a CDN, so it runs offline |
| `dejasolve/cloud/archive_aurora.py`, `dejasolve/cloud/sync_archive_to_aurora.py`, `dejasolve/cloud/ingest_worker.py`, `infra/cloudformation/` | The "at scale" build: Aurora + pgvector retrieval, an SQS ingest worker, and the CloudFormation templates. Every one is gated behind an environment variable that defaults to off — see [Runtime](#runtime-docker-and-the-aws-build) |
| `benchmarks/plot_convergence.py` | Draws the Phase 1 figure from `results.json` |
| `run_all.py` | All of it, in order |

## The UI

```bash
python app.py
```

Then open <http://127.0.0.1:8000>. Pick one of the seven artifacts (or drop a file
onto the box), press **Analyse**, and the six pipeline stages resolve in order —
ingest, units, retrieve, verify, solve, admissible — each with its own verdict.
A stage that warns is amber and a stage that blocks is red, because those are
different statements. The header badge reads **395 solved · 5 failed**, because
the archive is two things now, and Retrieve names the nearest *failed* run
alongside the chosen solved one — as two distances, never as a verdict. Retrieve
also says how the pick was made: the best of the 5 nearest that passed the gate,
and which case it beat if that was not the nearest. Under the headline sits the
**report**: what happened, what it means, and — when the verdict is a warning — a
name field, a reason field and **Warm-start anyway**. Accepting a warning appends
to the audit trail shown at the bottom of the page.
The headline is the number, against both baselines: **8 cold / 7 nominal → 3 warm Newton iterations, same answer to 2.3e-13** — the warm start is transferred second-order (§ Result), not verbatim, and the report names which transfer order it used.

Alongside the pipeline there is a **3D view**, three.js and vendored: the archive's
solved states projected to three dimensions, the query beside the case retrieval
chose, and a race between the three starts — plus a **Newton convergence studio**
that steps the real solver iterates across the 3D machine model. Every iterate it
draws is the solver's own (an earlier version interpolated the path; that was bug
C1 in [docs/known-bugs.md](docs/known-bugs.md) and is fixed).

An **Evidence** panel used to sit below the pipeline — the measured results,
the three arms, the surrogate arms, the fold circuit's 4-vs-40, the
failure-archive AUC, the dimensionality chart, and the 25-parameter sweep,
read live from the result JSONs by `GET /api/evidence`. It has been pulled
off the live page: a demo showing curated offline benchmark numbers next to a
live pipeline read as more decided than the work deserved. The same
CSS/HTML/JS is kept intact in
[docs/presentation/evidence-section.html](docs/presentation/evidence-section.html) for
reuse in the deck, and `GET /api/evidence` still serves the data behind it.

It is a **service with a page attached**, not a notebook app: the page is a
client of `POST /api/analyse`, which is the same endpoint a Study Manager sweep
would call. `GET /api/health`, `GET /api/samples`, `GET /api/evidence`, and OpenAPI docs at `/docs`
come with it. No secrets needed, and nothing leaves the machine: the page offers
the parser, the local model, and the hybrid of the two. Hosted Claude stays a
valid backend for the API and the CLI but is deliberately absent from the page —
an option that contradicts "your run data stays on your network" is the one
thing on screen an engineer would ask about. With no model reachable at all,
ingest falls back to the parser and the demo still runs.

## The end-to-end run (CLI)

```bash
python -m dejasolve --all
```

Seven artifacts — a tidy solver log, an older banner log in SI units, an oversized
pump, a truncated log, a structural NX Nastran log, an English email, a Romanian
note — go through ingest, retrieval, the verifier, a warm solve, and an
admissibility check. With `--backend rules` (parser only, no model needed):

```
run-tidy.log      warm_started         8 cold / 7 nominal -> 2 warm iterations
run-legacy.log    warm_started         8 cold / 7 nominal -> 3 warm iterations
run-bigpump.log   warned_not_used      nominal guess, 7 iterations (archive not used)
run-truncated.log refused_incomplete   missing p_crack
part-bracket.log  foreign_domain       3D structural FE; nothing in this archive applies
note-email.txt    refused_incomplete   (parser alone cannot read prose — the hybrid backend can)
note-ro.txt       refused_incomplete   (as above)
```

The half that does not warm-start is the interesting half — and it stops in two
different ways, on one rule: **the engineer decides what to do with a risk; the
system decides what is a fact.**

**Warned** is a risk. The verifier estimated, before any solve, that the transfer
is not legitimate — the 118 L/min pump in `run-bigpump.log` is bigger than
anything the archive was swept over. It says so, does not use the archive, falls
back to the nominal guess so the warning costs nothing, and offers an override:

```bash
python -m dejasolve data/logs/run-bigpump.log --override --operator you --basis "why"
```

`10 cold / 7 nominal -> 3 warm iterations, same answer to 3.2e-09` — and the
acceptance is recorded, with a name, a reason and a timestamp, in the trace's
audit trail. Here the warning was conservative and the override paid off. That is
the argument *for* warning rather than refusing; what makes it safe is that the
admissibility gate still runs on the result, so an engineer can accept a risky
*start* and still cannot be handed an impossible *answer*.

**Blocked** is a fact, and no flag argues with one. `part-bracket.log` is a
Simcenter 3D / NX Nastran solver log — a different kind of model entirely. Layer 1
reads it (SOL 101, the title, modulus, thickness, element counts) and the stage is
green, because ingest did not fail; the domain gate then stops it at Retrieve,
*before* the unit check, because plausibility is judged against a schema and this
one does not apply.

That artifact earns its place on one line. Its banner reads
`Density ....: 2.70E-09 tonne/mm^3`, and the parser's synonym table maps `density`
onto `rho` — so without a domain check the Case Card records **aluminium as the
hydraulic fluid density**. It reports the near miss instead:

```
would_have_been_mismapped   rho <- 2.70E-09 tonne/mm^3
```

One collision, because this schema has seven fields and one of them shares a name
with a structural log — and no synonym was added to manufacture it. Field names
are domain-scoped, and the count grows with the schema. Nothing here solves,
reads or maps a 3D field: the transfer adapter is the next-steps item, and this
is the boundary being shown rather than crossed.
 A missing hydraulic parameter is named,
the nearest archived case is located on the parameters that *were* stated, its
value is shown — and **not applied**. A misread unit (`7.8 m2` → 7.8e+06 mm²) is
caught as implausible before it reaches retrieval. A converged root on the
friction downslope is reported in full and refused as an operating point.

Every path — including the clean one — ends in a **report**: severity, reason,
and what the system did about it.

**Ingest accuracy** (5 artifacts, 35 fields, scored against ground truth;
inventing a value counts as a miss). `run-bigpump.log` is deliberately *not*
scored — it exists to exercise the verifier, and padding the parser's score with
an easy machine log would move this number for a reason unrelated to ingest:

| | parser | local model | **hybrid** |
|---|---|---|---|
| machine logs (3) | **21/21** | 15/21 | **21/21** |
| prose (English email, Romanian note) | 2/14 | **14/14** | **14/14** |
| total | 23/35 | 29/35 | **35/35 (100%)** |
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

It then caught something that was not the model's fault at all. Ollama compiles
the JSON schema to a grammar that applies JSON's no-leading-zero rule to a
number's *exponent*, so `1.6e-05` cannot be emitted — it truncates to `1.6e-0`,
five orders of magnitude out. The model had read the value correctly and quoted
it verbatim; the bounds check rejected it, and the field surfaced as *"not stated
in the artifact"*. Because the citation is verbatim and already verified, it is
also the repair: an out-of-bounds value whose quote re-parses — through the same
unit conversion the parser uses — to a plausible number *with the same
significand* is restored rather than dropped. That last condition is what keeps
the repair honest; it can only ever put back a lost exponent, never substitute a
different number. `c_load_a` and `c_load_b` are the only fields in the fixtures
written with a zero-padded exponent, and were the only ones ever lost this way.

```bash
python -m dejasolve.ingest --compare        # scores every available backend
```

> Runs locally by default (`qwen2.5:7b` via Ollama) — nothing leaves the machine,
> and no internet is needed. The Claude backend is written but **untested** here.
> On a 4 GB GPU a prose artifact takes 1–3 minutes; machine logs are unaffected.

### Before the demo: check the model is actually reachable

The prose artifacts (`note-ro.txt`, `note-email.txt`) are the half of the demo
that needs the model — the deterministic parser scores 0/7 on the Romanian note.
Without it the pipeline still runs and refuses honestly, but the 100% hybrid
result cannot be shown.

```bash
curl http://127.0.0.1:11434/api/tags     # must list qwen2.5:7b
```

If it lists other models but not `qwen2.5:7b`, **do not re-pull it** — check
where Ollama is reading from before downloading 4.7 GB again:

```bash
ollama pull qwen2.5:7b                   # only if the blobs are genuinely absent
```

**The trap, and it cost an hour to pin down:** if the models live somewhere
other than the default store, `OLLAMA_MODELS` must reach the *server process*.
The **tray app does not pass it through** — setting the variable at Windows User
scope, or exporting it in the shell that launches `ollama app.exe`, both leave
the server reading the default directory. The model sits on disk, complete, and
invisible. Restarting the tray app does not help, and neither does signing out.

What works is running the server yourself, so it inherits the variable directly:

```powershell
$env:OLLAMA_MODELS = "E:\ollama\models"; & "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
```

**That terminal window *is* the server — closing it stops Ollama.** Start it
before the demo and leave it alone. Kill any tray-app instance first, or the port
is already taken.

Newer Ollama builds expose a model-location field in the tray app's settings; if
yours has one, set it there instead and this stops being a per-session ritual.

Two reasons this is worth the paragraph: it fails *silently* — `auto` degrades to
the parser and the prose artifacts simply refuse, which looks like a broken
feature rather than a missing directory — and the error message says
`run 'ollama pull qwen2.5:7b'`, which would waste 4.7 GB re-downloading a model
that is already there. Check `/api/health` first; it reports which backends are
reachable and why.

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

Three starting guesses, not two. **Cold** is the flat start — every node at
tank, every shaft at rest. **Nominal** is what a competent tool defaults to: a
guess built from the case setup alone (`model.nominal_start`), no archive and
no solve. **Warm** is the nearest archived case's converged state.

| | cold (flat) | nominal | warm |
|---|---|---|---|
| mean Newton iterations | 8.3 | 7.1 | 4.9 |
| total iterations | 1631 | 1420 | 953 |
| runs that never converged | 4 / 200 | 0 / 200 | 0 / 200 |

**42% fewer iterations than the flat start, 31% fewer than the nominal guess**,
and the answers agree to 4e-08 bar and 3e-08 rev/min across all 196 cases where
both converged. The 31% is the number that matters — see below.

### The archive knows more than the endpoint

The `warm` column above hands Newton the neighbour's converged state
**verbatim** — the retrieved answer, asserted as the query's answer. That
throws away everything the archived run knows except where it landed. It also
knows the tangent of its own solution: differentiating the converged residual
through the implicit function theorem gives `dx*/dp = -J⁻¹ ∂F/∂p`, cheap to
compute once per card and stored on it (`model.solution_sensitivity`). The
start becomes `x0 = x_j + S_j (p - p_j)` — the neighbour's answer, walked
toward the query — instead of the neighbour's answer standing in for it.

| | warm (verbatim) | + sensitivity | + ranked by predicted error, k=5 | **+ second-order** |
|---|---|---|---|---|
| mean Newton iterations | 4.9 | 3.8 | 3.4 | **3.0** |
| **vs nominal** | **31.1%** | **47.1%** | **51.5%** | **57.2%** |
| vs the verbatim warm start | — | 23.3% | 29.7% | 37.9% |
| vs the flat start (total iterations, 1631) | 41.6% | 54.0% | 57.8% | **62.7%** |

Same candidate as `warm` in the second column — only the transfer changes, so
it isolates what the tangent alone is worth. The third column also lets the
tangent choose *which* card to transfer from, ranked by predicted start error
(`‖S_j Δp‖`, scaled) instead of by parameter distance — which is the actual
question retrieval was a proxy for. The fourth adds the curvature of the
solution manifold, `d²x*/dp²` (`model.solution_hessian`, recorded per card by
`dejasolve/sweep.py`): the archived answer is walked toward the query *along the curve*
rather than shooting straight off the tangent, which matters wherever the relief
valve cracks or a shaft crosses the Stribeck peak. **0 answers differ** from the
verbatim column across all four; same tolerance, same agreement to 4e-08 bar. A
simplex arm (interpolating between several candidates) was measured as well and
lands at 4.2 iterations / 40.9% — worse than ranking, so it is not shipped.

The tangent costs one 7×7 matrix–vector product per query — about 15% of one
residual evaluation — and is computed once when the case enters the archive. The
Hessian adds ~50 ms per card, offline. A card without a Hessian degrades to
first-order, and one without a tangent to verbatim, so an old archive keeps
working at the accuracy it can support; the report names which order it used.
`python -m benchmarks.selftest` checks the analytic `∂F/∂p` against central differences
(worst relative error 3e-08) the same way it checks the Jacobian.

### The number as the app produces it

`benchmarks/bench.py` scores each construction on its own, with no verifier and no fallback.
The app does not run one construction — `dejasolve.analyse` shortlists the 5
nearest, lets the verifier **filter** them, ranks the survivors by predicted start
error and transfers second-order. `experiments/bench_app_path.py` runs exactly that path over
the same 200 queries:

| | nominal | **app path** |
|---|---|---|
| mean Newton iterations | 7.10 | **3.035** |
| **vs nominal** | — | **57.3%** |
| runs that never converged | 0 / 200 | 0 / 200 |
| picked a case other than the nearest | — | 131 / 200 |
| fell back to the nominal guess (gate admitted nobody) | — | 2 / 200 |
| transfer order used | — | second-order on 198 |

The order of the three steps is the design: **filter, then rank.** Ranking first
and gating the winner afterwards is the obvious implementation and it is worse —
the ranked pick is often further away than the nearest, so the coverage rule
refuses it and the archive is abandoned for a case two rows down that the gate
would have admitted. Measured on the same 200 queries: rank-then-gate falls back
to the nominal guess on 21, gate-then-rank on 2. And when the gate refuses all 5,
ranking is abandoned and the plain nearest case is returned with its refusal:
predicted start error is read off a tangent recorded at the candidate's own
operating point, and that stops describing anything outside the region the gate
vouches for. On `run-bigpump.log` ranking the refused shortlist puts the *worst*
of the five first.

**The 31% remains the conservative number for everything else in this file.** It is
what a verbatim transfer gets, and the surrogate comparison, the dimensionality
table and the wide-parameter sweep below are all measured against that arm, so
changing the baseline there would mean re-measuring all of them. The 57% is the
shipped result, on the base circuit, reported alongside it rather than in place of
it.

### Why there is a third column

Reporting a warm start only against a flat start is exactly the methodological
error [WARP](https://arxiv.org/abs/2605.05728) documents in the warm-start
literature: the baseline is one nobody would ship, so the win is inflated. The
flat start is especially weak *here*, and `dejasolve/model.py` says why — equal pressures
put every orifice on the worst spot of the sqrt curve and zero speed sits in the
Stribeck regularisation. So the nominal arm was added and the headline is
reported against both.

Two claims did not survive it, and both are stated here rather than dropped:

- **The rescues are not the archive's.** All 4 flat-start failures are fixed by
  the nominal guess too, so the archive rescues nothing the case setup could not.
- **A worse Jacobian does not make the archive worth more.** It makes the *flat
  start* worth less. The nominal guess absorbs all of it:

| solver Jacobian | cold failures | nominal failures | warm failures |
|---|---|---|---|
| exact analytic | 4 / 200 | 0 / 200 | 0 / 200 |
| finite difference, `sqrt(eps)` step | 2 / 200 | 0 / 200 | 0 / 200 |
| finite difference, coarse step | 45 / 200 | 0 / 200 | 0 / 200 |

What does survive is the iteration count: ~31% fewer Newton steps than a good
engineering guess, stable across all three Jacobian settings, with the same
answer to 4e-08 bar. That is a smaller claim than "every failure rescued" and
it is the one the numbers support.

The headline still uses the **analytic** Jacobian on purpose: it is the best
case for both baselines, so the advantage measured against them is real.

## The other warm start: a predicted state

Retrieval recalls a real converged state from a *similar* case. A surrogate predicts an
approximate state for *this* case. Both are just an `x0` handed to Newton, and
`benchmarks/surrogate.py` measures the second one on the same 200 queries.

The surrogate is a **quadratic response surface** — 7 normalised parameters → 36
polynomial features → 7 states, ridge least squares, ~40 lines of numpy and no new
dependency. It fits the 395-case archive in 1 ms and predicts in 150 µs. It is
deliberately not good, and deliberately not a nearest-neighbour regressor, which would
have been retrieval wearing a different hat.

**It is not an answer.** Against a solver tolerance of 1e-8, the predicted state's
residual has a median of **8.26** and a worst case of **230**. **0 of 200 predictions
were solutions.**

**It is the best starting guess on the table.**

| arm | converged | total Newton iterations | mean |
|---|---|---|---|
| cold (flat start) | 196 / 200 | 1631 | 8.32 |
| nominal guess | 200 / 200 | 1420 | 7.10 |
| warm — retrieval | 200 / 200 | 979 | 4.89 |
| **predicted — surrogate** | **200 / 200** | **924** | **4.62** |
| verified — prediction, gated | 200 / 200 | 920 | 4.60 |

**34.9% fewer iterations than the nominal guess**, against retrieval's 31% — so the
prediction beats the archive by 5.6%. That is the expected result, not an upset: the
surrogate sees all 395 archived cases for every query and retrieval uses exactly one.
What it costs is the guarantee. Retrieval hands the solver a real converged state of a
real case; the surrogate hands it something that satisfies nothing. They reach the same
answer here only because the solver is what guarantees the answer — which is the whole
argument, stated by the results rather than by the pitch.

The archive still earns its place: the surrogate needed 395 solved cases to exist before
it could be fitted, and retrieval works from run number two.

**Gating the prediction is honest about not helping — here.** A predicted state has no
source case, so the transfer gate does not apply; the admissibility gate does, pointed at
the prediction — *is this even a legal state to start from?* It fires 15 times in 200,
every one a cavitating pressure the polynomial extrapolated. Using those 15 anyway costs
**4 Newton iterations across the whole run**, and none of them failed to converge. On this
circuit the filter is pointless, because the circuit has a unique root everywhere and a
bad start can only cost iterations — it cannot change the answer.

### The circuit where it does matter

```bash
python -m benchmarks.surrogate --fold
```

The fold circuit, where the starting guess selects *which* of three roots Newton finds and
the middle one is dynamically unstable. Same archive and same 200 queries as `benchmarks/fold.py`:

| same circuit, same queries | from **retrieval** | from **prediction** |
|---|---|---|
| naive — valid operating point | 147 | 158 |
| **naive — unstable root, silently wrong** | **4** | **40** |
| naive — no answer at all | 49 | 2 |
| verified — valid operating point | **200** | **200** |
| verified — silently wrong | **0** | **0** |
| verified — total Newton iterations | 1579 | **1300** |

**The prediction is the better starting guess and, unverified, ten times more dangerous.**
200 valid answers for 18% less solver work than retrieval — and 40 silently wrong answers
against retrieval's 4.

The mechanism is worse than the count. Naive retrieval fails to converge 49 times, which is
a loud failure a human goes and investigates. The prediction converges 198 times out of 200,
and 40 of those land at a residual of 1e-8 on an operating point no machine can occupy.
**The surrogate converts loud failures into silent wrongness.**

**And the pre-filter is a cost mechanism, not a safety one.** A third arm — `post_only`, no
check on the prediction, only the gate on the answer plus escalation — also returns 200
valid and 0 wrong, for 1559 iterations against the guarded policy's 1300. Safety comes from
the gate on the *answer*, on both circuits and for both sources; checking the prediction
first is worth nothing on the base circuit and 17% of solver work here. That arm exists so
the easier, false claim cannot be made by accident.

Full record: [docs/phases/phase-1b-surrogate.md](docs/phases/phase-1b-surrogate.md).

## Hundreds of parameters

Real models have hundreds of parameters; this circuit has 7. The useful question
is which layer breaks first when it is not 7 — so the physics stays untouched and
the *recorded* vector grows with entries that are real numbers on the Case Card
and inert in the equations, 7 to 1007. Nuisance entries occupy [0, 1], the same
range the real parameters do after normalisation, which is the favourable case
for naive retrieval.

| Case Card width | mean iterations | vs nominal | same neighbour as physics-only retrieval | contrast |
|---|---|---|---|---|
| 7 (real only) | 4.89 | **31.1%** | 200/200 | 0.661 |
| 37 | 5.69 | 19.9% | 3/200 | 0.278 |
| 107 | 5.96 | 16.0% | 3/200 | 0.161 |
| 1007 | 6.20 | **12.7%** | 1/200 | 0.052 |

**It degrades without collapsing, and that is not a compliment to the index.** At
1007 parameters retrieval still beats the nominal guess by 12.7% — because on this
circuit every archived state is a plausible operating point, so even a random one
beats a formula. The archive is doing the work; the index has stopped
contributing. By **37 recorded parameters** it agrees with physics-only retrieval
on 3 of 200 queries, which is near chance.

**And the distance gate cannot see it.** The coverage rule is re-derived in
whatever space retrieval indexes, so its radius scales correctly — 0.53 to 12.52 —
and it goes on admitting **196–198 of 200 at every width**. It does not fail
loudly; it fails by approving, because the concentration that destroyed the signal
also inflated the radius the distance is checked against.

> A distance threshold cannot detect the failure of a distance metric.

`envelope`, `breakaway` and `relief` read the 7 real parameters and the source's
recorded regime, and are independent of the card's width by construction. That is
the measurement behind the Phase 2 decision to build the gate from cheap physics
rather than a distance threshold.

![retrieval at hundreds of parameters](results/figs/dimensionality.png)

Full record: [docs/phases/phase-1c-dimensionality.md](docs/phases/phase-1c-dimensionality.md).

## The failed runs are in the archive too

An engineer asked for them, and they were right: the failures were being counted
and thrown away. On the fold circuit that meant discarding **165 runs of 300** —
more than half the compute. `dejasolve/sweep.py` now writes `data/archive/failures.jsonl`, and
`fold.sweep_fold()` returns its rejects instead of tallying them.

Then the obvious rule was tested rather than assumed — *warn when the nearest
failed case is closer than the nearest successful one*:

| | **will this run die?** | **will reuse go wrong?** |
|---|---|---|
| base rate | 56.0% | 26.5% |
| P(bad \| rule fired) | **74.8%** | 30.4% |
| lift over base rate | **1.34x** | 1.15x |
| **AUC** | **0.770** | 0.633 |

**The control matters more than the result.** Failures cluster where the circuit
is hard, and successes are sparse in the same places — so a positive score could
just mean *"you are far from anything solved"*, which the coverage rule already
sees. Scoring on distance-to-nearest-success alone gives AUC **0.650**; the rule
gives **0.770**. The failed runs carry information the successful ones do not.

**And the rule is still not in the gate.** It predicts whether a *case is hard*
and barely predicts whether a *transfer is legitimate* — different questions, and
the archive answers one of them. So it is advisory information for the engineer
rather than a rule the system acts on. Two more reasons: a 56% base rate means
"this one might die" is not news, and on the base circuit (5 failures in 400) the
rule fires 3 times in 200 and catches none of the 4 hard cases. `benchmarks/failure_zone.py`
prints **UNDERPOWERED** rather than letting that be quoted as evidence.

A failure archive is only worth consulting where runs actually fail.

Full record: [docs/phases/phase-2b-failure-archive.md](docs/phases/phase-2b-failure-archive.md).

## The verifier (Phase 2)

A converged answer can still be wrong. The steady state is the equilibrium of a
dynamic system, and a root on the Stribeck downslope is **dynamically
unstable** — it satisfies the equations to 1e-8 and no machine can sit there.
Newton cannot tell; the eigenvalues can.

The base circuit above has a *unique* root everywhere in its envelope — checked
with a 16-seed multi-start over all 400 cases, not assumed. So it cannot
demonstrate that failure mode. `benchmarks/fold.py` builds the same equations around a
smaller motor (5 cm³/rev), where the operating point falls into the Stribeck
fold and the torque balance picks up three roots.

200 fresh cases on that circuit:

| | naive retrieval | verified |
|---|---|---|
| valid operating point | 147 | **200** |
| **unstable root (silently wrong)** | **4** | **0** |
| no answer | 49 | **0** |
| total Newton iterations | 1571 | **1579** |

**4 silently wrong answers → 0, for +1% solver work.** The gate is built from
physics rather than a distance threshold, because setup distance turned out to
predict transfer cost with r = 0.18 — barely at all.

**It is a gate that argues rather than one that refuses.** Asked whether the
system should refuse when unsure or warn and let them decide, the two engineers
interviewed for this project chose the second — so a verdict carries a severity.
Gate 1 *estimates*, before any solve, and everything it decides is a **warning**
the engineer may override under their own name. Gate 2 *measures*, after the
solve, and what it finds is a **fact** with no override: the equations are
satisfied and no machine runs there. Both always produce a report.

The +1% is recent. When a refused transfer fell back to the flat start this cost
+36%; falling back to the nominal guess instead makes safety almost free. But
the swap is **answer-changing, not just cheaper**, and `benchmarks/fold.py` measures that
rather than footnoting it: **12 of 200 cases resolve to a different operating
point** (max |dw| 789 rev/min). Both are stable and both pass the verifier —
these cases are genuinely bistable. The guarantee is that you never land on an
*impossible* operating point, not that you land on the same valid one a
different starting guess would have found.

### The first-order transfer is safer here, not just cheaper

The base-circuit finding above holds on the harder circuit too — and here the
transfer gate is already in the loop, so it is measured through it rather than
instead of it. `benchmarks/agent_select.py`'s k=5 shortlist evaluation reruns this
comparison with the same gated retrieval, transferring first-order instead of
verbatim:

| arm (gated, k=5) | mean iterations | inadmissible |
|---|---|---|
| verbatim (distance picks, copies) | 7.95 | 11 |
| + sensitivity (distance picks, tangent transfers) | 5.33 | 1 |
| + sensitivity ranked | 5.13 | **1** |

These are the k=5 gated-shortlist numbers, not the k=1 arm in the table above,
so they are not directly comparable line-for-line — see
`agent_select_results.json`. The mechanism is the same one that helps on the
base circuit: a start that lands closer to the true operating point is a start
less likely to overshoot into an unstable one, so cost and correctness improve
together instead of trading off.

## The baseline that beats the archive

[WARP](https://arxiv.org/abs/2605.05728) says to test against the baseline a sceptic
would pick, and `nominal_start` is still three rules of thumb. A competent engineer
*decomposes*: each branch sees the rest of the machine through one scalar, the
manifold pressure. Fix it, close the branch in closed form, bisect until supply meets
demand. No archive, no solve, no residual evaluation. `experiments/coupled.py` builds it.

| circuit | shipped `nominal_start` | archive (ranked + 1st order) | decomposed guess |
|---|---|---|---|
| base, mean iterations | 7.10 | 3.44 | **2.70** |
| fold, mean iterations | — | 7.40 | **4.52** |
| fold, failures / inadmissible roots | — | 49 / 4 | **0 / 0** |

It beats retrieval outright — the second-order transfer (3.04) narrows the base-circuit
gap without closing it. Three attempts to build a circuit that does *not* decompose
all failed: a wider manifold (more branches is *more* decomposable), a load-sensing
pump, and a shared return manifold with a bistable band. A hydraulic network is a
handful of shared pressures joining locally-closed-form branches, and that is the
definition of decomposable.

What survives, and it is measurable: **a decomposed initialiser is bound to its
topology.** It cannot even be called on the 12-unknown geometry circuit, the
22-unknown manifold or the 14-unknown coupled circuit — wrong state dimension — and
each needed about forty lines of algebra specific to that circuit. Retrieval needed
nothing: the same code, on any circuit whose Case Card you can build, from run number
two. The claim is therefore not *"fewer iterations than a competent tool"*. It is:

> A hand-derived initialiser beats retrieval on the circuit it was written for.
> Nobody writes one per model. Retrieval is within ~30% of it, needs no derivation,
> and transfers to a circuit it has never seen.

That is why the layers a formula cannot replace — **ingest** and the **verifier** —
carry the project as much as the speed number does. Full record:
[docs/phases/phase-1g-decomposition.md](docs/phases/phase-1g-decomposition.md). These numbers
come from `experiments/coupled.py` and are not in `run_all.py`.

## Beyond the base circuit

Real models are not 7 parameters. Two extensions were built and measured; neither
is shipped, and neither confirmed the tempting story.

**Scaling** (`experiments/manifold.py`, [phase 1f](docs/phases/phase-1f-scaling.md)). The pitch "cold
starts on bigger models take 30–50 iterations, so the saving grows to 80–90%" inflates
the baseline — the error above, again. Measured on a manifold of 2–6 branches
(36–88 parameters), on a uniform archive, **the first-order transfer degrades faster
than the verbatim one** — a tangent has a validity radius — and at four branches it is
worse than doing nothing. The ranked arm survives because it declines to
extrapolate far. Rebuilt the way real archives look — a handful of machine designs,
many operating points each — the ranked arm returns **40.8–48.5%** at 62–88 parameters.
The saving tracks archive density in the *effective* dimension, not the width of the
Case Card: it degrades gently with complexity rather than growing with it. The
n = 6 row carries a caveat: the nominal guess itself stops working there.

**Geometry** (`experiments/geometry.py`, [phase 1e](docs/phases/phase-1e-geometry.md)). Give the circuit
five pipe runs with a length and a bore (Darcy–Weisbach; 12 unknowns, 18 parameters)
and the "layout is illustrative" disclaimer becomes false. Retrieval returns **14.3%**
against nominal, against 31% on the lumped circuit — and a random archived state is
now *worse* than the nominal guess (−2.8%), so the index is doing all the work.
Retrieving on the 7 lumped parameters alone gets 7.9%: geometry has to be on the Case
Card. The oracle sits at 40.2%, which is headroom left unclaimed.

## Claims tested and declined

The pattern of declining its own claims is deliberate, and each is a file you can run:

| claim | verdict |
|---|---|
| The archive rescues runs that fail cold | **No** — the nominal guess rescues all 4 too |
| A worse Jacobian makes the archive worth more | **No** — it makes the *flat start* worth less |
| Pre-filtering a predicted start is a safety mechanism | **No** — a cost mechanism; safety comes from the gate on the *answer* |
| Proximity to a failed run should be a gate rule | **No** — advisory only (AUC 0.77 for "will this die?", 0.63 for "will reuse go wrong?") |
| Walking deeper into the archive by distance (`experiments/topk.py`) | **No** — k = 1 is the optimum by distance |
| A model or heuristic can rank the candidates better (`benchmarks/agent_select.py`) | **No** — four rankers at or below the random floor; the models parse cleanly and choose badly |
| The saving grows with model complexity | **No** — it degrades gently ([above](#beyond-the-base-circuit)) |
| Retrieval beats a competent baseline on iteration count | **No** — not against a hand-derived one ([above](#the-baseline-that-beats-the-archive)) |

The selection-agent result and the shipped ranking do not contradict each other: what
lost was ordering candidates by distance, by physics heuristics or by a model; what
won is ranking the gate's survivors by the tangent-predicted start error, which is the
question distance was a proxy for. The verifier holds the veto throughout — the agent
proposes, the verifier disposes.

## Runtime: Docker and the AWS build

```bash
docker compose up                        # the demo at http://localhost:8000
docker compose --profile reproduce up    # regenerate every number, then exit
```

One image, two services — `ui` (FastAPI + the page) and `runner` (`python run_all.py`,
profile-gated) — non-root, with a `HEALTHCHECK` on `/api/health`. It needs no secrets:
the full demo runs on the deterministic ingest backend, and the Phase 1 summary hash
is identical from the host and from the container.

The "at scale" row of [docs/architecture.md](docs/architecture.md) is written as real
code and CloudFormation, not a diagram: Aurora Serverless v2 with pgvector for
retrieval (`RETRIEVAL_BACKEND=aurora`), an SQS queue and ECS Fargate worker for ingest,
a DynamoDB mirror of the audit trail (`AUDIT_TABLE`), S3 for raw artifacts, and a CPU
Ollama instance for the model backend — four templates in
[`infra/cloudformation/`](infra/cloudformation/), deployed in order and torn down
independently ([docs/aws-deployment-plan.md](docs/aws-deployment-plan.md)).

**It was deployed and it worked** — all four stacks (network, data, ollama, compute)
were built in `eu-west-2`, with the same container running on ECS Fargate behind an
ALB against Aurora, SQS and DynamoDB. **It is not running now:** all of it was deleted after the presentation so the account carries no cost, so
there is no live URL. The templates are unchanged and redeploy in the order the plan
gives. Every backend is gated behind an environment variable that defaults to off, so
the benchmarked pipeline and a plain `docker compose up` never touch AWS, and none of
the reported numbers depend on it.

## Status and limits

The project is finished and presented. What it does not do, stated plainly:

- **No live cloud deployment.** The AWS stack was built and verified, then torn down
  (see [Runtime](#runtime-docker-and-the-aws-build)); what remains is the templates.
- **State vectors only.** No mesh handling, no field transfer, no structural solving.
  `part-bracket.log` (NX Nastran) is refused at the domain gate, on purpose, and the
  mapped-field adapter needed for 3D is the next piece of real engineering. Amesim
  (a state vector) is what the demo covers; STAR-CCM+ and Simcenter 3D are a mapping,
  with FMI/FMU as the standard warm-start interface.
- **One circuit family.** Every headline number is on a hydraulic manifold with two
  motors. The scaling and geometry work says how it degrades; it does not say it
  generalises.
- **The speed number is against a rule-of-thumb baseline.** A hand-derived
  initialiser beats it on the circuit it was written for (see above).
- **No tenancy, authentication or retention policy.** One archive, one domain, no
  notion of who may reuse whose results.
- **The hosted-model (Claude) ingest backend is written and has never executed here.**
  The local model (`qwen2.5:7b` via Ollama) is what was measured.
- **The archive is a file.** `cases.jsonl` is read into memory — right for 395 cases,
  wrong for the first customer. Phase 1c also shows the *metric* degrades long before
  the *scan* does, so an ANN index would make a failing search faster, not better.

The bug sweep in [docs/known-bugs.md](docs/known-bugs.md) records every finding against
the app and how each was resolved.
