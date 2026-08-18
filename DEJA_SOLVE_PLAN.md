# Déjà Solve — Plan (Siemens Summer School 2026)

**Deadline:** Friday 28 August 2026, 13:00 · **Today:** Sunday 16 August 2026 · **12 days**
*(plan revised 16 Aug after mentor's answers — see §0)*
**Presentation:** 10 minutes · **Audience:** SISW SRL Brașov colleagues, incl. teachers/lab assistants
**Domain to register under:** *Digital Twins & Platforms* (primary) — it is a platform/data layer, and it avoids
colliding with the colleague who took *Procesare Semnal & Algoritmi* with the ROM idea.

---

## 0. Mentor feedback — 12 Aug 2026, and what it changes

Three questions were asked (§8). Two answered, one deflected into something better.

### Q3 — "does this already exist?" → **Not a kill switch, but the claim must be sharpened**

> *"Cred că depinde de solver și de cât de avansat este, dar da, unele asta fac. Păstrarea unor info utile
> din simulări cu succes ar putea să fie o chestie faină și care să optimizeze fluxul."*

Read it in two halves.

**First half — a correction.** Some solvers *do* reuse state. This kills any sentence of the form *"nobody
reuses previous solutions."* Never say that in the room; someone owns that code.

**Second half — an endorsement.** She independently described the archive layer ("keeping useful info from
successful simulations… would optimise the flow") without being prompted with it. That is a mentor
describing Layer 1+2 back to you as a good idea.

**The claim, restated — use exactly this wording from now on:**

> Warm-starting is a **solver** feature. It works inside one session, on a run a human already picked:
> continuation, restart files, "initialise from previous solution." What no solver does is look across
> **hundreds of finished runs it has never seen**, decide **which one** is physically closest, and prove that
> reusing it is **legitimate**. Déjà Solve sits *above* the solver, not inside it. It is a selection and
> verification layer, and it hands the solver something the solver already knows how to consume.

Corollary for the deck: the "missing arrow" slide stays, but the missing arrow is *retrieval + verification*,
not *warm-start*. §2 bullet 2 and §9 have been updated accordingly.

### Q1 — which Simcenter product lines at Brașov? → **Free choice: "toate sunt folosite, alege ce vrei"**

> *"Toate sunt folosite, depinzând de divizie, deci alege ce vrei."*

A constraint disappeared, so **lock it yourself and stop deliberating: Amesim is the anchor vocabulary.**
Reasons, in order:

1. **The pain is documented and specific there.** DAE initialisation failure across inconsistent states
   (§2 bullet 3) is an Amesim-shaped problem. STAR-CCM+ doesn't fail that way.
2. **Study Manager sweeps are literally the demo.** 300–500 cases, one sweep, some die overnight.
3. **The warm-start object is a small state vector, not a 3D field.** No mesh-to-mesh mapping — which §4
   already declares out of scope. Anchoring on STAR-CCM+ or Simcenter 3D would drag that back in.
4. **A faithful mock is ~200 lines of scipy.** Hydraulic circuit or battery+thermal. Buildable today.

So: **Amesim = the vocabulary** (states, causality, initialisation, Study Manager, sweep).
**PhysicsAI = the AI arrow** (the surrogate that produces a predicted starting state).
**STAR-CCM+ = one citation** as prior art for manual previous-solution init. Nothing else.

### Q2 — why would an engineer *not* want this? → **She didn't answer. She offered an engineer.**

> *"Nu, ce cred este poate totuși că ar fi fain să luăm legătura cu unul doar ca să îți mai dea niște
> 'cerințe utile'? Din punct de vedere ingineresc."*

**Say yes today.** This is the highest-value thing available in the whole 12 days and it costs 30 minutes.
Reasons it matters more than another day of code:

- The objection list is the **only unvalidated part of the plan**. Everything else you can test yourself; this
  you cannot.
- Act 3 of the demo (the refusal) is an argument about **what engineers distrust**. Right now that argument is
  your guess. One interview turns it into a quote.
- "I talked to an engineer, here are the three requirements they gave me, here is which two I implemented" is
  the single strongest slide available to a student in this room.

Question list and the reply to send: **§8b**. Whenever the interview lands, it takes priority over that day's
coding block.

**Guardrail:** requirements from that conversation feed the **verifier rules and the Case Card schema only**.
They do not reopen scope. If the engineer describes a fourth layer, it goes on the "next steps" slide.

---

## 1. One-line pitch

> Every solver run starts from zero — even when the company already solved a nearly identical case last week,
> and even when an AI model has *just predicted the answer*. **Déjà Solve** finds the physically-nearest
> available starting state (a past solution, or a surrogate's prediction), verifies that using it is
> legitimate, and warm-starts the solver from it — **same converged answer, fewer iterations, fewer failed
> runs.**

**The hook (post-PhysicsAI):** Simcenter PhysicsAI predicts a complete field at every node, then the workflow
says *"optionally validate with a full solver run"* — and that validation run starts from scratch. The
prediction it just made is discarded. **Déjà Solve is the return path.** The speed of AI, the guarantee of
the solver.

---

## 2. Problem statement (the 3 evidence bullets for slide 2)

0. **Why now — Siemens already agrees with the premise.** **Simcenter PhysicsAI 2026.1** (shipped 2026) trains
   surrogates on *historical simulation data*, geometric deep learning, "up to 1000x faster than traditional
   solver simulations", output is "a spatially distributed field — stress, pressure, temperature, velocity at
   every node". Its documented workflow: train → predict → assess confidence → **"optionally validate with a
   full solver run."** *That validation run starts from zero.* No public evidence (product pages, 2510 / 2602
   / 2606 release notes, workflow write-ups) that a PhysicsAI prediction is ever fed back as a solver initial
   condition. **That missing arrow is the project.**
1. **Analysts don't analyse.** HASTT study (Rolls-Royce Aero-Engines), cited by Siemens' own Teamcenter blog:
   **over 50% of a simulation analyst's time is spent seeking and providing information.**
2. **Solvers can already consume a starting state — nothing tells them which one.** Say this *first*, out
   loud, before anyone corrects you: restart files, continuation, "initialise from previous solution" — these
   exist, and STAR-CCM+ does it via a manual XYZ-table export/import. Every one of them assumes **a human
   already knows which past run to point at.** Meanwhile the tooling that should answer that question searches
   files, not physics: Simcenter Client for Git filters on *collection type, classification, maturity status,
   branch, custom attributes, version comments* — i.e. it only works if somebody typed good metadata.
   **The selection step is manual, and the verification step doesn't exist.**
3. **In system simulation it's worse than slow — it fails.** DAE solvers fail when initial conditions across
   state variables are inconsistent; "even slightly inconsistent" conditions often kill the initialisation
   problem outright. A 500-case Study Manager sweep that dies overnight on initialisation failures is a
   ruined morning.

**The gap in one sentence:** the solver can start from a previous state — but nobody automatically finds the
physically-nearest solved case, and nobody verifies that reusing it is legitimate.

---

## 3. What it is — 4 layers

Each layer exists for a reason you must be able to defend out loud.

| # | Layer | What it does | Why it's there |
|---|---|---|---|
| 1 | **Ingest agent** (LLM) | Parses heterogeneous run artifacts — logs, input decks, free-text notes — into a structured **Case Card** (JSON) | Past runs share no schema; unstructured→structured is what LLMs are genuinely good at. Makes the archive searchable *without* human-typed metadata |
| 2 | **Retrieval + warm start** (ML + numerics) | Hybrid index (numeric setup vector + text embedding). New case → nearest solved case → use its state as the starting guess for the nonlinear solve | **This is the layer that produces the number.** Backed by NOWS (2026): up to 90% compute-time reduction, *preserving convergence guarantees* |
| 3 | **Verifier** (physics rules) | Gates transfer: same physics regime? dimensionless numbers in band? same BC/topology signature? consistent units? Refuses with a one-line reason | The trust layer. Published CFD agents report ~88% "success" — where success means *the job didn't crash*, not that the physics was right. **Who checks the copilots?** |
| 4 | **Runtime** (Docker/cloud) | Containers: solver-runner, index service, object store, queue, API + UI | Cloud story that survives losing AWS access |

### Two sources of warm start, one verifier

| Source | Needs | Works when |
|---|---|---|
| **Retrieval** — nearest solved case from the archive | nothing but a second run | from day one; no training, no minimum dataset |
| **Prediction** — a surrogate's predicted field | a trained model (≥20 runs for PhysicsAI) | once a model exists — **this is where PhysicsAI plugs in** |

Both feed the same solver, both gated by the same verifier. Say it as: *"PhysicsAI makes prediction cheap.
Déjà Solve makes verification cheap."*

### Positioning the verifier vs. PhysicsAI's similarity score

PhysicsAI 2026.1 ships a **geometric similarity score (0–1)** to flag when a *prediction* is unreliable.
**Cite it as prior art you are extending — do not pretend to have invented similarity scoring.** Different
question: theirs scores *geometric novelty of a design*; yours scores *physics-regime transferability of a
solution used as a starting state*. Their own caveat supports you: a dataset "can meet the minimum while
failing to represent important geometry, load cases or operating limits."

### Technical precision — say it exactly this way

Warm-starting does **not** change the physical initial condition of a transient (that would change the
problem). It warm-starts the **nonlinear algebraic solves**:

- the **initialisation problem** (finding consistent algebraic states / derivatives that satisfy the
  constraints, given the differential states), and
- **steady-state / operating-point solves** in a parameter sweep.

The converged answer is identical to tolerance. Newton just gets a better starting guess. **Get this right —
the room contains people who will check.**

---

## 4. Scope

**In:**
- **Built 16 Aug: a hydraulic manifold driving two motors** (`model.py`) — nonlinear orifice flow
  (`Q ∝ sign(Δp)·√|Δp|`), a relief valve, and two shafts loaded quadratically through **Stribeck friction**.
  7 unknowns: five pressures, two shaft speeds. Chosen over battery+thermal and powertrain because it is the
  most Amesim-shaped of the three (§0), and because the mechanical side is what makes the initialisation
  genuinely hard — see §6a. Squarely automotive-aerospace, i.e. their industry
- 300–500 case archive from a parameter sweep
- Case Card schema + LLM ingest
- Vector index + retrieval
- **A small surrogate trained on the archive** (sklearn/XGBoost/tiny MLP) — stands in for PhysicsAI so you can
  demo the three-way comparison. It does **not** need to be good; it needs to be *fast and slightly wrong*,
  which is the whole point
- Warm-started Newton / initialisation solve
- Verifier rule set
- `docker compose up` demo + AWS mapping slide
- Measured results: iterations, failure rate, wall time

**Explicitly out (say so on a slide — scoping discipline reads as maturity):**
- Any real Simcenter integration or file format
- 3D field mapping between different meshes
- Learned embeddings trained from scratch
- Anything touching GPU

---

## 5. Timeline — re-baselined 16 Aug

**Status:** Phase 0 closed. **Phase 1 gate met on Sun 16 Aug, two days early** — `figs/convergence.png`
exists and every number is regenerable with `python run_all.py`. Measured results in §6a. Two days of slack
are back; spend them on Phase 2, not on polishing Phase 1.

| Phase | Dates | Work | **Gate** |
|---|---|---|---|
| ~~0. Validate + scaffold~~ | ~~Tue 11 – Thu 13 Aug~~ | **Done.** Mentor answered (§0). Amesim locked as vocabulary | ✅ confirmed |
| ~~1. THE NUMBER~~ | ~~Sun 16 – Tue 18 Aug~~ | **Done 16 Aug.** `model.py`, `sweep.py`, `bench.py`, `plot_convergence.py`, `run_all.py`. 400-case archive, 200 fresh queries, 1-NN retrieval | ✅ **plot exists, 42% fewer iterations than a flat start and 31% than a nominal guess, answers agree to 4e-08 bar.** *The project can no longer fail* |
| ~~2. Verifier~~ | ~~Wed 19 – Thu 20 Aug~~ | **Done 17 Aug.** `verifier.py` (5 pre-solve rules + 2 post-solve), `fold.py`. Eigenvalue admissibility check | ✅ **4 silently-wrong answers → 0, at +1% solver work.** [record](phases/phase-2-verifier.md) |
| ~~3. Agent + UI~~ | ~~Fri 21 – Sun 23 Aug~~ | **Done 17 Aug.** `casecard.py`, `ingest.py` (rules + Claude backends), `make_logs.py`, `dejasolve.py`, and a FastAPI service + single-page UI (`app.py`, `static/index.html`) | ✅ **messy artifact → verified warm start, 8 cold / 7 nominal → 4 warm iterations, in the browser.** [record](phases/phase-3-ingest.md) |
| **4. Cloud/Docker + final measurements** | Mon 24 – Tue 25 Aug | compose file, AWS architecture slide, re-run all benchmarks clean, freeze numbers | `docker compose up` works on a clean machine |
| **5. Slides + rehearsal** | Wed 26 – Thu 27 Aug | Deck, script, 3 full rehearsals with a timer | Under 10:00 twice in a row |
| **Buffer** | Fri 28 morning | Nothing new. Only rehearsal | — |

**Floating, not scheduled:** the engineer interview (§8b). Whenever it lands, it pre-empts that day's coding
block. It cannot be scheduled because it isn't yours to schedule.

**Implementation records:** each finished phase gets a file in [`phases/`](phases/) — what was actually
built, what was decided, what was measured, what was rejected. This plan is what was *intended*; those files
are what *happened*. Write the record at the end of the phase, not later.

**Cut lines, in order, if you fall behind:** cut the UI polish → cut the LLM ingest layer (Layer 1) → cut the
cloud deployment (keep the architecture slide). **Never cut Layer 2 or Layer 3.** A demo with a hard number
and a trust story beats a demo with a chat box.

---

## 6. The demo — 3 acts, ~3 minutes total

**Act 1 — the archive works (40s).** `python dejasolve.py --all`. Five real artifacts go in — a tidy solver
log, an older banner log in SI units, a truncated log, an English email, a Romanian note. Each becomes a Case
Card with canonical units and quoted provenance; retrieval names the nearest archived case and its regime.

**Show the refusals, they are the better half of Act 1.** The truncated log is missing `p_crack`; the system
names the gap, finds the nearest case on the six parameters that *were* stated, shows what that case used —
and refuses to apply it: *"a missing parameter is a question for the engineer, not a value to borrow."* A
mis-read unit (`7.8 m2` → 7.8e+06 mm²) is caught as implausible before it ever reaches retrieval.

**Act 2 — the number (60s).** Panel A of `figs/convergence.png`, mirroring the PhysicsAI workflow:

| Approach | Answer | Cost |
|---|---|---|
| Surrogate alone | approximate, no guarantee | instant |
| Cold-start solver (flat start) | exact | **11 iterations** |
| Nominal-guess solver (no archive) | exact | **7 iterations** |
| **Retrieval → warm-started solver** | **exact, same residual** | **4 iterations** |

*(query-0055, the exemplar the benchmark picks automatically. The surrogate row is still a placeholder —
that model is not built yet. The nominal row is the honest baseline: a starting guess built from the case
setup alone, no archive involved — it is the row the warm start actually has to beat.)*

Say the last row out loud: **"the speed of AI, the guarantee of the solver."** Then the sweep-level number
from §6a: *"Across 200 fresh cases: 31% fewer Newton iterations than a good engineering guess — 42% against
a flat start — and the answers agree to 4×10⁻⁸ bar."*

**Quote the 31%, not the 42%.** If someone asks why, the answer is the strongest thing on this slide: *"42%
is against a flat start, which is a baseline nobody ships. I added the guess a competent tool actually makes
and re-measured against that."* Do **not** say "all four cold-start failures rescued" — that claim was
retracted (§6a), because the nominal guess rescues the same four.

**Act 3 — the refusal (60s).** `figs/verifier.png`, case `foldq-0009`. Naive retrieval warm-starts and
converges in **8 clean iterations** to shaft b at **35.6 rev/min** — residual 1e-8, looks perfect. It is a
**dynamically unstable root**: the circuit's supply curve crosses the Stribeck load curve three times and it
landed on the middle crossing, where no machine can run. Déjà Solve refuses in one line — *"converged onto a
dynamically unstable root; the equations are satisfied but no machine runs here"* — and recovers a real
operating point at 462.5 rev/min.

Across 200 cases: **4 silently wrong answers → 0**, for **+1% solver work**.

**If asked "how is it almost free?"** — because the fallback after a refusal is a decent guess rather than a
flat start. And volunteer the other half before it is asked: this circuit is genuinely bistable, so the
fallback decides *which* valid operating point comes back. **12 of 200 cases resolve to a different root**
than a flat-start fallback would have found, all of them stable, all of them admissible. The guarantee is
that you never land on an impossible operating point — not that there is only one right answer. That is
measured in `fold_results.json`, not hand-waved (§6b, concession 3).

*"Silent wrongness is the failure mode that actually scares engineers. This is the layer nobody builds."*

**Open with the honesty, it is stronger than the demo:** *"I first checked whether my own base circuit could
produce a silently wrong answer. A 16-seed multi-start over all 400 cases found exactly one root every time —
it can't, and I'll say so. This is the hardware corner where it can."* See §6b.

---

## 6a. Measured results — Phase 1, 16 Aug

Regenerate with `python run_all.py`. Everything below comes out of `results.json`; nothing is typed by hand.
**If a number is not in `results.json`, it does not go on a slide.**

Setup: 400-case Latin-hypercube sweep → 395 converged → archive. 200 *fresh* query cases (different seed).
Retrieval is 1-nearest-neighbour on the min-max normalised 7-parameter setup vector. Same residual, same
Jacobian, same tolerance (1e-8) for all three runs — **the only difference is the starting guess.**

Three arms, not two. **Cold** is the flat start — every node at tank, every shaft at rest. **Nominal** is
the guess a competent tool makes from the case setup alone (`model.nominal_start`): no archive, no solve.
**Warm** is the nearest archived case's converged state.

| | cold (flat) | nominal | warm |
|---|---|---|---|
| mean Newton iterations | 8.3 | 7.1 | **4.9** |
| median iterations | 8 | 7 | **4** |
| total iterations | 1631 | 1420 | **953** |
| runs that never converged | 4 / 200 | 0 / 200 | **0 / 200** |

**31% fewer Newton iterations than the nominal guess; 42% fewer than the flat start.** Answers agree to
**3.6e-08 bar** and **3.2e-08 rev/min** across all 196 cases where both converged — 0 disagreements. That
agreement figure is the one that matters most in this room: it is the evidence that warm-starting changed
the cost and not the answer.

**The 31% is the headline; the 42% is context.** Reporting a warm start only against a flat start is the
methodological error [WARP](https://arxiv.org/abs/2605.05728) documents in the warm-start literature — the
baseline is one nobody would ship, so the win is inflated. The flat start is especially weak *here*: equal
pressures sit on the worst spot of the orifice sqrt curve and zero speed sits in the Stribeck
regularisation, so the model punishes that guess specifically.

**One claim was retracted when the third arm went in, and saying so is an asset, not a liability:** *"all 4
cold-start failures rescued"* is gone. The nominal guess rescues the same four, so the archive rescues
nothing the case setup could not. What survives is the iteration count — a smaller claim that holds up when
someone in the room has read the literature.

### The caveat to state before anyone asks

How often cold start *fails* depends on how good the solver's Jacobian is. `bench.py` reports the
sensitivity rather than picking the flattering setting:

| solver Jacobian | cold failures | nominal failures | warm failures | saving vs cold | vs nominal |
|---|---|---|---|---|---|
| exact analytic | 4 / 200 | 0 / 200 | 0 / 200 | 42% | 31% |
| finite difference, `sqrt(eps)` step | 2 / 200 | 0 / 200 | 0 / 200 | 42% | 31% |
| finite difference, coarse step | **45 / 200** | 0 / 200 | 0 / 200 | 41% | 31% |

**The headline uses the analytic Jacobian on purpose — it is the best case for both baselines**, so the
advantage measured against them is real. The iteration saving is stable at ~42% against the flat start and
exactly 31% against nominal in all three settings.

**The second retraction lives in this table.** The old version of this section argued that the worse the
solver's Jacobian, the more the archive is worth. That is false: a worse Jacobian makes the **flat start**
worth less. The nominal guess converges 200/200 in every setting, including the coarse finite-difference one
where the flat start fails 45 times. The failure-rate story is a story about bad initialisation, not about
the archive — and the archive's actual case is the iteration column.

**A trap avoided, worth remembering:** the first version of this benchmark showed a 22% cold failure rate.
That was an artifact of the prototype's finite-difference step size, not of the physics. Had it gone on a
slide unchecked, the first engineer to ask "what step size?" would have taken the whole talk down with it.

### What the physics needed

A plain resistive hydraulic network was tried first and is **globally convergent** — a damped Newton solves
it from anywhere in 7–8 iterations, with zero failures. There is no warm-start story on such a model, and
manufacturing one by crippling the solver would have been obvious to this audience. The difficulty has to be
physical: the working model adds two motor shafts loaded through **Stribeck friction**, whose decaying
branch has negative slope and narrows the basin of attraction around the operating point. That is an
ordinary mechatronic nonlinearity, not a contrivance — and it is why Panel A shows the cold run crawling
across a plateau for 8 iterations before it can converge at all.

---

## 6b. Measured results — Phase 2, 17 Aug

Full record: [`phases/phase-2-verifier.md`](phases/phase-2-verifier.md). Numbers from `fold_results.json`.

**What "wrong" means, precisely.** The steady state is the equilibrium of a dynamic system (oil
compressibility gives each node a pressure state, each shaft has inertia). A root on the Stribeck downslope
has `d(load torque)/dw < 0` — positive feedback. It satisfies the equations to 1e-8 and is **dynamically
unstable**; no machine can sit there. Newton cannot tell. The eigenvalues can.

200 fresh cases on the fold circuit:

| | naive retrieval | verified |
|---|---|---|
| valid operating point | 147 | **200** |
| **unstable root (silently wrong)** | **4** | **0** |
| no answer | 49 | **0** |
| total Newton iterations | 1571 | **1579** |

69 of 200 transfers refused by the pre-solve gate. **Price of never being silently wrong: +1% solver
work** — it was +36% when a refused transfer fell back to the flat start; the ladder now falls back to the
nominal guess, which is archive-free either way, so the refusal is unchanged and only the bill shrank.

**Say the trade-off in the same breath, because the swap changes answers, not just cost.** `fold.py`
measures it: **12 of 200 cases resolve to a different operating point** than the flat-start ladder found
(max |dw| 789 rev/min). Both are stable, both pass the verifier — see concession 3.

**The gate is physics, not distance** — and this is the strongest argument for Layer 3 existing at all: in
Phase 1 the correlation between setup distance and what a transfer actually costs is **r = 0.18**. Parameter
similarity barely predicts transferability. Distance survives only as an envelope guard, and even its
threshold is not tuned — it is the archive's own 99th-percentile case spacing.

Both cheap regime estimators were validated against solved ground truth before being trusted: **395/395**.

### Four things to concede before anyone asks

1. **The pre-solve gate did not catch the demo case** — it admitted the transfer; the post-solve eigenvalue
   check caught it. The rules do not predict every bad transfer; the backstop is what makes the guarantee.
2. **The effort comparison is not like-for-like, deliberately.** The verified policy escalates (warm →
   nominal → multi-start) *because it can tell it failed*. The naive one gets one shot because it never
   knows. +1% is the honest price, and the honest footnote is that it is only that low because the fallback
   rung is a decent guess rather than a flat start.
3. **Admissible ≠ unique — and now there is a number for it.** These cases are genuinely bistable; both 5.5
   and ~460 rev/min are valid operating points. Swapping the fallback rung moved **12 of 200 cases onto a
   different valid root**, which is the cleanest possible demonstration that the starting guess selects the
   branch. The verifier guarantees you never land on an impossible operating point; it does not promise a
   canonical one. Choosing between real branches needs a transient — out of scope, limits slide.
4. **The wrong-answer demo runs on a variant circuit** (5 cm³/rev motor instead of 32). The base circuit has
   a unique root everywhere — verified by multi-start, not assumed. Say this *first*; it is the credibility
   move, not the weakness.

---

## 6c. Measured results — Phase 3, 17 Aug

Full record: [`phases/phase-3-ingest.md`](phases/phase-3-ingest.md).

**The model layer is justified by a number, not an assertion.** Five artifacts, 35 fields, scored against
ground truth (correct = within 1%, *or* correctly reported missing). Inventing a plausible value counts as a
miss, not partial credit:

| artifact style | parser | local model (qwen2.5:7b) | **hybrid** |
|---|---|---|---|
| machine logs (3 files, unit conversion + a corrupted value) | **21/21** | 15/21 | **21/21** |
| prose — an English email and a Romanian note | 2/14 | **12/14** | **12/14** |
| **total** | 23/35 (66%) | 27/35 (77%) | **33/35 (94%)** |
| **invented** | 0 | 0 | **0** |

**The headline finding is not "the model wins" — it is that the two fail on disjoint inputs.** The parser is
perfect on machine logs (`4.09 m3/h → 68.18 L/min`, a corrupted `p_crack = ####` reported missing not zero)
and scores 0/7 on the Romanian note. The model reads the Romanian note 7/7 and misreads machine logs. So the
shipped backend runs the parser first and calls a model **only for the fields it could not fill** — which is
also what makes the demo fast: a well-formed log never reaches the model and returns in 1.6 s.

**Layer 1 needed its own verifier, and that is the best story in this phase.** The first run showed the local
model inventing 3 values — the project's own failure mode appearing in ingest. It answered *"the standard fan
curves"* with `c_load = 0.0`, while giving correct values with no citation at all. The fix is deterministic:
a citation supports a number only if it **contains a digit**; a value outside the physical envelope is
dropped; a missing citation is fine if the value's digits are in the artifact. That took the local model from
3 inventions to **0**, and raised its score 21→27 at the same time. *A model can talk its way past an
instruction; it cannot talk its way past this.*

**Local by default — and the reason is confidentiality, not cost.** Ingest runs on `qwen2.5:7b` via Ollama,
on the machine. Nothing leaves the network, and the demo needs no internet. See the new §9 Q&A entry.

**Two things to say plainly:** the *Claude* backend is written but has never executed (no key on the build
machine) — do not quote a number for it. And the local model is **slow on this laptop**: an RTX 3050 has 4 GB
VRAM against a ~4.7 GB model, so only 12 of 29 layers fit on the GPU and a prose artifact costs 1–3 minutes.
Machine logs are unaffected. For the live demo, run the prose case beforehand or demo the instant path.

**The UI is a FastAPI service with a single-page client** (`python app.py`), not a Streamlit script — and that
is a pitch decision, not just a technical one. You are registered under *Digital Twins & Platforms* and slide
8 is "why it's a platform"; what a platform exposes is an API. `POST /api/analyse` is the same endpoint a
Study Manager sweep would call, and it maps 1:1 onto the AWS architecture slide. A widget script would have
quietly contradicted the pitch. It also keeps the Phase 4 image small and needs no CDN, so it runs in a
conference room with no internet.

**Demo it with the refusals, not just the green path.** The page styles a refusal as a first-class outcome:
Retrieve turns red, names the missing `p_crack`, shows what the nearest case used — and the downstream stages
grey out as *skipped* so the room sees exactly where the pipeline stopped.

---

## 7. 10-minute presentation — time budget

| Time | Slide | Content |
|---|---|---|
| 0:00–0:45 | Hook | **The PhysicsAI workflow diagram with the missing arrow drawn in red.** "It predicts the answer at every node. Then, to check it, we start the solver from zero." Name the product once |
| 0:45–2:00 | Problem | The evidence bullets. PhysicsAI's discarded prediction. HASTT 50%. Client for Git finds files, not physics. DAE init failures |
| 2:00–2:45 | **What already exists** | PhysicsAI 2026.1, ROM Builder, RomAI, AMR, Insights Hub anomaly detection, Design Copilot NX — *"I checked. Here's what Siemens already has, and here's the one arrow that's missing."* **This slide buys you enormous credibility with this specific audience — they built these** |
| 2:45–4:00 | Solution architecture | The 4 layers, one sentence each. The precision statement about *what* is warm-started |
| 4:00–7:00 | **Demo** | The 3 acts |
| 7:00–8:15 | Results | The measured table. Iterations, failure rate, wall time. Then translate to Simcenter X credits / kg CO₂ |
| 8:15–9:00 | Why it's a platform | The archive is a flywheel: the more the company simulates, the faster it gets. Cloud/Docker architecture slide |
| 9:00–9:30 | Limits + next | What you did *not* do, honestly. FMI/FMU initialisation as the obvious next step |
| 9:30–10:00 | Close | One sentence, the name again |

---

## 8. Mentor thread — sent 11 Aug, answered 12 Aug ✅

*(kept for the record; the answers and their consequences are in §0)*

> Buna ziua, tema la care m-am gandit pentru proiectul final pleaca chiar de la articolul despre Simcenter
> PhysicsAI. Modelul prezice un camp complet, la fiecare nod, iar apoi workflow-ul spune "validate with a full
> solver run" — dar rularea aia de validare porneste de la zero, deci predictia tocmai facuta se pierde.
>
> Ideea mea e sa inchid bucla: solverul sa fie initializat din predictie sau din cel mai apropiat caz deja
> rezolvat din arhiva, printr-un strat care verifica intai daca reutilizarea e legitima (regim fizic, numere
> adimensionale, consistenta). Converge la exact aceeasi solutie, doar cu mai putine iteratii si cu mai putine
> rulari esuate intr-un sweep.
>
> Ca demo: un model de sistem in Python si o arhiva de ~400 de cazuri, cu o comparatie intre surogat singur
> (instant, aproximativ), solver de la zero (exact, lent) si solver initializat (exact si rapid).
>
> Am cautat si nu am gasit public nimic care sa aleaga automat o initializare din rezultate anterioare — daca
> exista deja ceva de genul in Simcenter, as vrea sa stiu inainte sa incep. Si, daca se poate, ce linii de
> produs se dezvolta la Brasov, ca sa folosesc vocabularul potrivit.
> Va stau la dispozitie pentru intrebari :)

**The kill-switch was in the last paragraph.** Answer came back: *some solvers do reuse state, but the idea of
keeping useful information from successful simulations is a good one.* Premise survives, wording sharpened
(§0).

---

## 8b. The engineer interview — accept, then prepare

### Reply to send (today, short, no hedging)

> Da, mi-ar folosi enorm — dacă se poate un call scurt (20–30 min) sau chiar și răspunsuri pe scris, oricum
> le e mai comod. Aș veni cu întrebări pregătite ca să nu le iau din timp.
>
> Între timp am ales direcția: rămân pe partea de **system simulation, cu vocabular de Amesim** — pentru că
> acolo problema de inițializare și sweep-urile din Study Manager se potrivesc cel mai bine cu ce vreau să
> demonstrez, iar demo-ul îl fac pe un model propriu în Python, nu pe fișiere reale.
>
> Și mulțumesc pentru răspunsul de la a treia întrebare — mi-a fost util fix pentru că m-a făcut să reformulez:
> nu mai zic că "nu se reutilizează soluții anterioare" (evident că unele solvere fac asta), ci că **alegerea
> automată a cazului potrivit din arhivă și verificarea că reutilizarea e legitimă** e partea care lipsește.

### The 8 questions (ordered — if they only answer three, these are the three)

**Pain — is the problem real?**
1. Cât de des vi se întâmplă ca o rulare sau un sweep întreg să pice la inițializare? Ce faceți concret când
   se întâmplă — reglați manual condițiile inițiale, porniți din alt caz, altceva?
2. Când începeți un caz nou, vă uitați la rulări anterioare? Cum le găsiți — după nume de fișier, după cine
   le-a făcut, întrebați un coleg?

**Trust — this shapes the verifier, i.e. Layer 3**

3. Dacă un sistem v-ar propune automat o stare inițială luată dintr-o rulare veche, **ce ar trebui să vedeți ca
   să acceptați?** Un scor? Ce parametri diferă? Cine a rulat cazul-sursă și când?
4. Ați prefera ca sistemul să **refuze** când nu e sigur, sau să vă avertizeze și să vă lase pe voi să decideți?
5. Există ceva în ce livrați care cere ca rularea să fie **reproductibilă sau documentată** (raport, validare,
   certificare)? Ar fi o problemă că traseul iterațiilor diferă, chiar dacă soluția convergentă e aceeași?

**Reality — the things a student cannot guess**

6. Aveți voie să refolosiți rezultate **între proiecte sau între clienți**? Unde se oprește asta?
7. Unde ar trebui să stea un astfel de lucru ca să-l folosiți: în interiorul tool-ului, ca serviciu separat,
   sau în pipeline-ul de sweep?
8. **Ce v-ar face să-l opriți după o săptămână?**

Q8 is the one to press on. It is the question the mentor deflected, and the answer is Act 3 of the demo.

**After the interview:** write the answers into this file, verbatim, same day. Two of them become verifier
rules; one becomes a quote on the problem slide.

---

## 9. Q&A prep — they *will* ask these

**"Your baseline was just a bad solver."** — The cold baseline gets the *exact analytic Jacobian* and a
backtracking line search; it is the best case for the baseline, not the worst. I also report the same
benchmark with finite-difference Jacobians at two step sizes, and the 42% iteration saving holds in all
three (§6a). The failure-rate advantage, I say openly, is the one that depends on Jacobian quality.

**"How do I know the answer didn't change?"** — Every warm run is checked against the cold run on the same
case: they agree to 3.6e-08 bar and 3.2e-08 rev/min across all 196 cases, with zero disagreements. Same
residual function, same tolerance — a warm start that changed the answer would be a bug, and the benchmark
would show it.

**"But some solvers already reuse previous solutions."** — *(Asked by the mentor already, so it will be asked
again. Pre-empt it on slide 2 rather than defending it here.)* Correct, and I say so on the problem slide:
restart files, continuation, previous-solution init. All of them start from a run **a human already chose**.
My layer is the choosing and the checking — across an archive the solver has never seen. The solver-side
mechanism is the part I *don't* have to invent, and that's a feature: I'm feeding an interface that already
exists.

**"Would it still be reproducible? Some of what we deliver has to be."** — The converged answer is identical
to tolerance; the iteration path differs. Every run records the parent state it started from, so provenance is
*better* than today, not worse — right now "which previous run did you initialise from" lives in someone's
memory. And a cold-start rerun is always available as the audit path, because the solver is untouched.

**"Are we allowed to reuse results across projects or customers?"** — Retrieval is scoped by
project/permission; that's a filter on the index, not a policy document. Worth showing on the cloud slide:
the archive is per-tenant, and the verifier refuses across a scope boundary before it ever looks at physics.
*(Flag honestly if the engineer interview hasn't happened yet: "this is the requirement I most want to hear
from a real user.")*

**"How is this different from PhysicsAI / ROM Builder / RomAI?"** — They *replace* the solver with an
approximation you can't certify. Déjà Solve keeps the exact solver and only improves its starting guess. The
answer is identical to tolerance. **And they aren't competitors — PhysicsAI is my best warm-start generator.
I'm the consumer of its output.**

**"PhysicsAI already scores similarity."** — Yes, geometric similarity, to tell you when a *prediction* is
unreliable. I'm asking a different question: is this solution legitimate to use as a *starting state*?
Different regime → refuse, even if the geometry looks identical. I cite theirs on the slide.

**"Doesn't PhysicsAI already do this internally?"** — Not that I can find publicly: not in the product pages,
not in 2510 / 2602 / 2606 release notes. **If it does, tell me and I'll say so on the slide** — the workflow
gap is my whole premise, and I'd rather be corrected now than in this room.

**"STAR-CCM+ can already initialise from a previous solution."** — Yes, and I cite that in the deck. It's
manual, per-case, and requires you to already know which run to use. My contribution is the *retrieval* and
the *verification*, not the initialisation itself.

**"What if the retrieved case is wrong?"** — That's Layer 3, and it's Act 3 of the demo. Refusal is a
feature.

**"Does this scale to 3D fields / real meshes?"** — Not in this demo, and I say so on the limits slide. The
mapping problem between different meshes is real work. The retrieval and verification layers are
mesh-agnostic; the transfer operator is the part that would need engineering.

**"Would our simulation data leave our network?"** — *(Expect this one. Run artifacts are customer data, and
it is the objection most likely to kill adoption regardless of how good the numbers are.)* No. Ingest has
three interchangeable backends: a deterministic parser (no network at all), a **local model over Ollama**
(nothing leaves the machine), and a hosted model for the quality ceiling. The default deployment can be
entirely on-prem. And the layer that matters — retrieval, the verifier, the solver — never touches a network
under any configuration; the model only ever turns text into a Case Card. Pick the backend to match your
data-governance rules, and the rest of the system does not change.

**"Why an LLM at all?"** — Only for unstructured→structured on ingest, and for the human-readable
explanation. **It never touches numerics.** If you delete it, the system still works — it just needs clean
metadata, which is the assumption that fails in practice.

**"Where's the cloud part?"** — Every component is a container; the archive is the shared asset that makes
this a platform rather than a script. Architecture maps to ECS/Batch, S3, SQS, pgvector/OpenSearch.

---

## 10. Stack

Python · NumPy/SciPy (`solve_ivp`, `fsolve`/Newton; `casadi` if you go DAE) · FAISS or sklearn NN or pgvector ·
sentence-transformers or an API model for embeddings · FastAPI + Streamlit · Docker Compose (runner, index,
MinIO, Redis, api) · matplotlib for the convergence plots.

**Keep a `results.json` from day one.** Every benchmark number in the deck must be regenerable by one command.
