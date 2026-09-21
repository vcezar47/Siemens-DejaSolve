# Déjà Solve — Plan (Siemens Summer School 2026)

**Deadline:** Friday 28 August 2026, 13:00 · **Today:** Wednesday 19 August 2026 · **9 days**
*(plan revised 16 Aug after mentor's answers — see §0; revised again 19 Aug after the engineer interview — see §0b;
revised again 25 Aug after the first-order transfer landed — see §6a)*
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

> **Amended 19 Aug (§0b) — the vocabulary stands, the framing does not.** The engineers asked for something
> general rather than tied to one product, and talked mostly about **Simcenter 3D**. Nothing above changes as
> a *build* decision; all four reasons still hold. What changes is what you claim out loud:
>
> **Do not say** "this is an Amesim project." **Say** "the layer is solver-agnostic — a Case Card, an index
> and a verifier do not know what produced the state they reason about. The reference implementation is a
> system-simulation circuit because that is what I could validate end-to-end and prove with numbers."
>
> Note that **reason 3 above is now the defence rather than the choice**: the warm-start object here is a
> 7-element state vector, and in Simcenter 3D it becomes a field mapped between meshes. That is the adapter,
> it is real engineering, and it goes on the next-steps slide — not into a demo with 9 days left.

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

## 0b. Engineer interview — 19 Aug 2026, and what it changes

Two engineers, in person, just over an hour. This is the conversation the mentor offered in §0/Q2, and it was
worth more than a day of code.

**Read this first:** the answers below are **recorded paraphrase, not verbatim**. It was a spoken meeting and
nothing was written down at the time. On a slide say *"the two engineers I spoke to said…"* — never put it in
quotation marks, and never attribute a sentence to a named person.

Three answers confirm decisions already taken. One produced a code change, shipped the same day. One is a
request to push back on — carefully.

### Q — "Is this done internally?" → No, with one pointer that must be named first

Not that they know of. There were **implementation ideas and concepts of this in the past, at a very high level
in the company**. Something slightly similar might exist **at Teamcenter level**.

**What it changes.** Not the plan — the *ordering* of slide 2. Teamcenter SPDM already is the simulation data
layer: it stores runs, provenance and search. Name it before anyone in the room does, then draw the line:

> Teamcenter answers *which files exist, who made them and when*. Déjà Solve answers *which solved state is
> physically closest, and whether reusing it is legitimate*. One is a data layer, the other is a selection and
> verification layer on top of it.

This sits naturally beside the existing §2 bullet 2 about Simcenter Client for Git filtering on typed metadata:
same argument, one level up.

**On the "concepts existed in the past" half — do not claim novelty, claim evidence.** The line to use:

> This has been thought about at concept level before. What I am bringing is a measurement of whether the gate
> can be built from physics rather than from a similarity threshold — and the answer is that setup distance
> predicts transfer cost at r = 0.18, so it cannot.

### Q — "How often does a run fail, and what do you do?" → the answer that validates the Phase 1 pivot

A run **does not really fail at the solver level**. The solver can fail **when integrating**, and it can fail on
**non-linearity cases, when there is no more congruence — the physical limits are blown away**. When it happens,
the engineer looks over the results and decides; usually that means **a change of design or material**.

**What it changes — three things, and the first one is the important one.**

1. **The headline stays iteration count. Never sell rescued failures.** §6a already retired that claim after the
   nominal baseline absorbed all 4 flat-start failures. This answer independently confirms it was right: nobody
   in that room believes their solver falls over, so "we save your failed runs" reads as a student who has never
   watched a real sweep. **31% fewer Newton iterations than a good engineering guess** is the claim, and it is
   the one the numbers support.
2. **"No more congruence, physical limits blown away" is a plain-English description of the Phase 2 failure
   mode.** A root on the Stribeck downslope satisfies the equations to 1e-8 and is not an operating point any
   machine can occupy. That is now *their* framing of the thing `benchmarks/fold.py` measures — **4 silently wrong answers
   → 0, for +1% solver work**. Open the verifier slide with their words, then show the number.
3. **The reuse case is a changed design, not a re-run.** "Usually a change of design or material" means the next
   solve is a *near miss* of the last one — one material property, one dimension. That is exactly what a
   physics-based nearest-neighbour is for, and exactly what filename or metadata search cannot do. Retire any
   phrasing that sounds like "run the same case twice".

### Q — "Refuse when unsure, or warn?" → **warn**, and this is now implemented

> Generate a report and give out a warning. Leave it up to the engineer to proceed with the simulation or not.

This was §8b/Q4, the question written specifically to shape Layer 3 — and the answer contradicted what the code
did. The pipeline **refused**: `refused_incomplete`, nearest case located, shown, and not applied. So it changed
the same day. **Implemented 19 Aug — see §6d.**

The change is not "warn about everything", which is its own kind of useless. It is two tiers, split on one rule:

> **The engineer decides what to do with a risk. The system decides what is a fact.**

| tier | what it is | what happens |
|---|---|---|
| **warn** | a *judgement* about transferring a state — the verifier estimated, before any solve, that this transfer is not legitimate | full report, archive not used, **override offered**; accepting it is recorded with a name and a reason |
| **block** | a *fact* about the data or the physics — a parameter that was never read, a unit out by 10⁶, a source case on different hardware, a converged root no machine can sit at | full report, no override, because there is nothing to decide |

The split falls exactly where the verifier's two gates already sat: **before** the solve it is estimating (warn),
**after** the solve it is measuring (block). That is not a coincidence dressed up after the fact — it is why the
rule is defensible out loud.

**This is the strongest slide available to a student in that room** (§0/Q2 predicted exactly this):

> I asked two engineers whether the system should refuse when it is unsure, or warn and let them decide. They
> said warn, and give them a report. So the gate stopped being a gate. Here it is.

### The extras — unasked-for, and two of them change the deck

**The three gates.** Vehicle programmes run concept → prototyping (≈25 vehicles, many iterations, real-life
tests) → series production, and an error or miscalculation at any gate can throw you back to the previous one or
to the start. **Put this on slide 2 as a diagram**: it is a cost narrative in their language rather than an
invented one, every backward arrow is the expensive event, and prototyping is the archive-population story told
for free. Déjà Solve sits on the loop-back arrows.

**Hundreds of parameters, not seven.** Answered with a measurement rather than an apology: §6g. The index
degrades (31% → 12.7% at 1007 recorded parameters, picking at near-random by 37) and the physics gate does
not — which is why the gate was built from physics in the first place.

**Both successful and failed runs in the archive.** Acted on the same week — the failures were being
collected and thrown away. Built, measured, and *declined as a gate rule* on the evidence: §6f.

**Domains: automotive, aerospace, heavy industry.** Narrate automotive — it is the one the three gates belong to
— and name the other two as transferable in a single line.

**"Make it general, almost universal."** Offered STAR-CCM+ or Amesim as anchors, they said those would each be
slightly different in implementation and they would rather it be general. The product they talked about most,
by a distance, was **Simcenter 3D**.

> **Update 20 Aug — §6h.** The verbal answer below still stands, and it is now backed by a live behaviour:
> a Simcenter 3D / NX Nastran solver log is the seventh fixture. Layer 1 reads it, the domain gate refuses it
> as a different kind of model, and the Case Card reports the field-name collision it prevented. A
> demonstration of the boundary, not a crossing of it.

**Do not rewrite the demo onto Simcenter 3D**, and be clear-eyed about why: 9 days left, and in 3D the
warm-start object stops being a 7-element state vector and becomes a field that must be mapped mesh-to-mesh.
§4 scoped that out for good reasons and none of them have changed. Shipping an unvalidated 3D story would cost
the one thing that makes this project credible — every number reproducible from `run_all.py`.

**The honest answer that satisfies them is that generality is a property of the layer, not of the demo** — and
here that happens to be true rather than a dodge. The Case Card, the retrieval index and the verifier do not
know what produced the state they reason about. So:

- **Re-anchor the wording.** §0/Q1 locked Amesim as "the vocabulary". It becomes: *the layer is solver-agnostic;
  the reference implementation is a system-simulation circuit because that is what could be validated
  end-to-end and proved with numbers.* Amesim stays the demo's vocabulary; it stops being the pitch's scope.
- **Add one slide: what changes per solver.** Three rows — Amesim (state vector, essentially free), STAR-CCM+
  (field plus XYZ-table, the existing manual path), Simcenter 3D (field mapped between meshes, the real
  engineering work). Same three layers, different adapter. This answers "is it universal?" with an engineering
  answer instead of a marketing one, and converts their Simcenter 3D interest into the next-steps slide rather
  than a hole in the demo.

**"There are whole departments behind the simulations, not just one engineer."** The sleeper. It independently
validates Layer 1: different people, different tools, different naming, different *languages* is precisely why
the fixtures include an English email and a Romanian note, and why the hybrid backend scores 35/35 with zero
inventions. It also made the override **attributed** rather than anonymous — an accepted risk in a departmental
workflow needs a name, a reason and a timestamp, which is what `trace["audit"]` now carries.

### What did *not* change

The §0 guardrail holds: this feeds the **verifier's contract and the Case Card schema only**. No new layer, no
new scope. Simcenter 3D goes on next steps. The three gates go on slide 2. Neither reopens the build.

### Backlog — wanted, not scheduled

- ~~**3D visualisation (requested 20 Aug).**~~ **Built 24 Aug — §6l,
  [record](phases/phase-1e-geometry.md).** The fork above was the right one to force, and the answer was
  *neither*: not a mesh, and not the adapter. The archive is drawn in **solution space**, where a 3D
  projection is honest (97.5% of variance, distance fidelity r=0.999) rather than in parameter space, where
  it is not (49.5%, r=0.667) — and the circuit itself is drawn as a 3D **schematic** whose colours, bores,
  valve state and shaft speeds are all solved quantities. No mesh is rendered and no field is mapped, so
  §6h's boundary is untouched; the adapter remains the first next-steps item.

### Still unanswered — and deliberately left that way (decided 19 Aug)

Of the eight questions in §8b, four were covered (Q1 and Q4 directly, plus the two extras). These were not:

- **Q3** — what would they need to *see* to accept a proposed starting state? (a score, which parameters differ,
  who ran the source case and when)
- **Q5** — does anything they deliver require the run to be reproducible or documented, and is a differing
  iteration path a problem even when the converged answer is identical?
- **Q6** — may results be reused across projects or across customers, and where does that stop?
- **Q8** — what would make you stop using it after a week?

**Decision: no follow-up round. The remaining time goes to the deck, not to another question.** The reasoning,
which is also the answer if it comes up in Q&A:

- **Q4 was the load-bearing question and it was answered.** It contradicted the code, the code changed the same
  day (§6d). That is the validation loop closing, not an open thread.
- **Q8 was written as Act 3's argument back when Act 3 was a guess.** It no longer is: Act 3 now rests on a
  requirement two engineers stated out loud, not on speculation about what engineers distrust. Q8 would sharpen
  the *next-steps* slide; it is no longer load-bearing for the demo.
- **Q3 would grade the report's fields.** Unasked, they stand as designed — severity, reason, consequence,
  nearest case and its distance, and who overrode what. That is defensible on its own merits; it is simply not
  *their* specification, and §6d should not claim it is.
- **Q5 and Q6 are governance questions** whose honest answer is "out of scope for a 10-minute student project",
  and they belong on the limits slide either way.

**Say it plainly if asked "did you go back to them?"** — *"I had an hour with two engineers, got the answer that
changed the design, and spent the remaining days building and rehearsing rather than asking again."* That is a
better answer than a second round of questions with nothing built on top of the first.

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

| Source | Needs | Works when | **Measured (§6e)** |
|---|---|---|---|
| **Retrieval** — nearest solved case from the archive | nothing but a second run | from day one; no training, no minimum dataset | 4.89 mean iterations, **31%** under the nominal guess |
| **Prediction** — a surrogate's predicted field | a trained model (≥20 runs for PhysicsAI) | once a model exists — **this is where PhysicsAI plugs in** | 4.62 mean iterations, **34.9%** under the nominal guess |

Both feed the same solver, both gated by the same verifier. Say it as: *"PhysicsAI makes prediction cheap.
Déjà Solve makes verification cheap."*

**This table stopped being architecture on 20 Aug — both rows are now measured on the same 200 cases.** The
prediction is the better starting guess *and* the one that satisfies nothing, which is the cleanest statement
of why the verifier exists. Lead with the concession in §6e when you present it.

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
- **Built 16 Aug: a hydraulic manifold driving two motors** (`dejasolve/model.py`) — nonlinear orifice flow
  (`Q ∝ sign(Δp)·√|Δp|`), a relief valve, and two shafts loaded quadratically through **Stribeck friction**.
  7 unknowns: five pressures, two shaft speeds. Chosen over battery+thermal and powertrain because it is the
  most Amesim-shaped of the three (§0), and because the mechanical side is what makes the initialisation
  genuinely hard — see §6a. Squarely automotive-aerospace, i.e. their industry
- 300–500 case archive from a parameter sweep
- Case Card schema + LLM ingest
- Vector index + retrieval
- **A small surrogate trained on the archive** (sklearn/XGBoost/tiny MLP) — stands in for PhysicsAI so you can
  demo the three-way comparison. It does **not** need to be good; it needs to be *fast and slightly wrong*,
  which is the whole point.
  **✅ Built 20 Aug** — `benchmarks/surrogate.py`, a 36-feature quadratic response surface in numpy, no new dependency.
  It is fast (150 µs) and wrong (0 of 200 predictions satisfy the equations), which is exactly the brief.
  Measured results and the two concessions that came with them: §6e.
- Warm-started Newton / initialisation solve
- Verifier rule set
- `docker compose up` demo + AWS mapping slide
- Measured results: iterations, failure rate, wall time

**Explicitly out (say so on a slide — scoping discipline reads as maturity):**
- Any real Simcenter integration or file format
- **3D field mapping between different meshes** — *this is the adapter, and after §0b it is the first
  next-steps item rather than a footnote.* The three layers are unchanged by it; what changes per solver is
  the object being transferred. Put the three-row table on the limits/next slide: Amesim (state vector,
  essentially free) · STAR-CCM+ (field plus XYZ table, the existing manual path) · Simcenter 3D (field mapped
  between meshes, the real engineering work)
- Learned embeddings trained from scratch
- Anything touching GPU

---

## 5. Timeline — re-baselined 16 Aug, updated 19 Aug

**Status, 19 Aug (9 days left).** Phases 0–3 are closed, all of them early. The engineer interview landed
(§0b) and produced one code change, shipped the same day (§6d). **Phase 4 is further along than this table
says:** `Dockerfile` and `docker-compose.yml` are written and the compose file records that the Phase 1
summary hash was already verified identical from inside the container — what remains is a rebuild against the
current tree and the AWS architecture slide, not two days of work.

**Update 20 Aug: the surrogate arm is built (§6e, [record](phases/phase-1b-surrogate.md)), so §4's In list is
now complete and there is no open build decision.** Everything that remains is Phase 4's last mile (rebuild,
architecture slide) and Phase 5.

**So roughly three days (21–23 Aug) are unscheduled.** Spend them on Phase 5 pulled forward — the deck, and
rehearsals with a timer. A 10-minute talk with a live demo is where this gets lost, not in the code.

| Phase | Dates | Work | **Gate** |
|---|---|---|---|
| ~~0. Validate + scaffold~~ | ~~Tue 11 – Thu 13 Aug~~ | **Done.** Mentor answered (§0). Amesim locked as vocabulary | ✅ confirmed |
| ~~1. THE NUMBER~~ | ~~Sun 16 – Tue 18 Aug~~ | **Done 16 Aug.** `dejasolve/model.py`, `dejasolve/sweep.py`, `benchmarks/bench.py`, `benchmarks/plot_convergence.py`, `run_all.py`. 400-case archive, 200 fresh queries, 1-NN retrieval | ✅ **plot exists, 42% fewer iterations than a flat start and 31% than a nominal guess, answers agree to 4e-08 bar.** *The project can no longer fail* |
| ~~2. Verifier~~ | ~~Wed 19 – Thu 20 Aug~~ | **Done 17 Aug.** `dejasolve/verifier.py` (5 pre-solve rules + 2 post-solve), `benchmarks/fold.py`. Eigenvalue admissibility check | ✅ **4 silently-wrong answers → 0, at +1% solver work.** [record](phases/phase-2-verifier.md) |
| ~~3. Agent + UI~~ | ~~Fri 21 – Sun 23 Aug~~ | **Done 17 Aug.** `dejasolve/casecard.py`, `dejasolve/ingest.py` (rules + Claude backends), `benchmarks/make_logs.py`, `dejasolve/pipeline.py`, and a FastAPI service + single-page UI (`app.py`, `dejasolve/static/index.html`) | ✅ **messy artifact → verified warm start, 8 cold / 7 nominal → 4 warm iterations, in the browser.** [record](phases/phase-3-ingest.md) |
| **4. Cloud/Docker + final measurements** | Mon 24 – Tue 25 Aug | compose file, AWS architecture slide, re-run all benchmarks clean, freeze numbers | `docker compose up` works on a clean machine |
| **5. Slides + rehearsal** | Wed 26 – Thu 27 Aug | Deck, script, 3 full rehearsals with a timer | Under 10:00 twice in a row |
| **Buffer** | Fri 28 morning | Nothing new. Only rehearsal | — |

**~~Floating, not scheduled:~~ the engineer interview — held Wed 19 Aug.** It pre-empted that day's coding
block exactly as planned, and was worth more than the block would have been: answers in §0b, the code change
it caused in §6d, and the decision not to run a second round in §0b's closing note.

**Implementation records:** each finished phase gets a file in [`phases/`](phases/) — what was actually
built, what was decided, what was measured, what was rejected. This plan is what was *intended*; those files
are what *happened*. Write the record at the end of the phase, not later.

**Cut lines, in order, if you fall behind:** cut the UI polish → cut the LLM ingest layer (Layer 1) → cut the
cloud deployment (keep the architecture slide). **Never cut Layer 2 or Layer 3.** A demo with a hard number
and a trust story beats a demo with a chat box.

---

## 6. The demo — 3 acts, ~3 minutes total

**Act 1 — the archive works (35s).** `python -m dejasolve --all`. Six real artifacts go in — a tidy solver
log, an older banner log in SI units, a truncated log, an English email, a Romanian note, and a log for a pump
bigger than anything the archive has seen. Each becomes a Case Card with canonical units and quoted
provenance; retrieval names the nearest archived case and its regime.

**Show what it will not do, it is the better half of Act 1.** The truncated log is missing `p_crack`; the
system names the gap, finds the nearest case on the six parameters that *were* stated, shows what that case
used — and **blocks** rather than applying it: *"a missing parameter is a question for the engineer, not a
value to borrow."* A mis-read unit (`7.8 m2` → 7.8e+06 mm²) is caught as implausible before it ever reaches
retrieval. Say the word **blocked**, not *refused* — Act 3 turns on the difference.

**Act 2 — the number (55s).** Panel A of `results/figs/convergence.png`, mirroring the PhysicsAI workflow:

| Approach | Answer | Cost |
|---|---|---|
| Surrogate alone | **residual 6.2 — satisfies nothing** | **0.15 ms** |
| Cold-start solver (flat start) | exact | **11 iterations** |
| Nominal-guess solver (no archive) | exact | **7 iterations** |
| **Retrieval → warm-started solver** | **exact, same residual** | **4 iterations** |
| **Prediction → warm-started solver** | **exact, same residual** | **4 iterations** |

*(query-0055, the exemplar the benchmark picks automatically. Every row is measured — the surrogate row was a
placeholder until 20 Aug and is not one any more (§6e). The nominal row is the honest baseline: a starting
guess built from the case setup alone, no archive involved — it is the row the warm start actually has to
beat.)*

**The first row is the one to say slowly.** *"The surrogate answers in 0.15 milliseconds. Its residual is 6.2,
and the solver stops at 1e-8. That is not a slightly-imprecise answer — it is not an answer. And the workflow
that produced it throws it away and starts the validation run from zero."*

**On this exemplar retrieval and prediction tie at 4.** They separate at sweep level, and not in the direction
you might expect — the prediction wins by 5.6%. Concede it there (§6e), do not stage it here.

Say the last row out loud: **"the speed of AI, the guarantee of the solver."** Then the sweep-level number
from §6a: *"Across 200 fresh cases: 51% fewer Newton iterations than a good engineering guess, by walking the
archived state toward the query instead of copying it — 31% if I only reuse the state as-is — and the answers
agree to 4×10⁻⁸ bar."*

**Lead with 51%, and have the 31% ready as the fallback number.** If time is short or the room is not
technical, the three-arm table and its 31%/42% is still a complete, true story — say it and stop; the
fourth-arm slide is additive, not required. If someone asks *"is that the best you can do?"*, the honest
answer moved: **"the 31% is what copying the archived state gets. It also knows how its own answer moves —
that is one derivative, computed once, offline — and using that gets 51%, with the same 0 disagreements."**
Do **not** say "all four cold-start failures rescued" — that claim was retracted (§6a), because the nominal
guess rescues the same four.

**Act 3 — the trust layer (80s), in two beats.** This is the act the engineer interview rewrote, and the two
beats are the two halves of one rule: *the engineer decides what to do with a risk; the system decides what is
a fact.* Beat A is the fact. Beat B is the risk.

**Rehearsal warning:** beat A is a figure, beat B is the browser. That is the only surface switch in the demo
— have the page already open on `run-bigpump.log`, on a second window or a second desktop, before you start
talking. Do not click *Analyse* until you get there.

**Open Act 3 with the honesty, it is stronger than the demo:** *"I first checked whether my own base circuit could
produce a silently wrong answer. A 16-seed multi-start over all 400 cases found exactly one root every time —
it can't, and I'll say so. This is the hardware corner where it can."* See §6b.

**Beat A — the fact it will not let you overrule (45s).** `results/figs/verifier.png`, case `foldq-0009`. Naive
retrieval warm-starts and
converges in **8 clean iterations** to shaft b at **35.6 rev/min** — residual 1e-8, looks perfect. It is a
**dynamically unstable root**: the circuit's supply curve crosses the Stribeck load curve three times and it
landed on the middle crossing, where no machine can run. Déjà Solve refuses in one line — *"converged onto a
dynamically unstable root; the equations are satisfied but no machine runs here"* — and recovers a real
operating point at 462.5 rev/min.

Across 200 cases: **4 silently wrong answers → 0**, for **+1% solver work**.

**Then land the harder number, which is new as of 20 Aug (§6e).** Run the same circuit and the same 200 cases
with the *surrogate's* prediction as the starting guess instead of the archive's: **40 silently wrong answers,
not 4.** The arm that won Act 2 is ten times more dangerous here. And the mechanism is worse than the count —
naive retrieval simply fails to converge 49 times, which is a loud failure somebody investigates, while the
prediction converges 198 times out of 200 and lands 40 of them at a residual of 1e-8 on an operating point no
machine can occupy. *"The surrogate turns loud failures into silent wrongness. That is the failure mode this
layer exists for, and I found it in my own best component."*

**If asked "how is it almost free?"** — because the fallback after a refusal is a decent guess rather than a
flat start. And volunteer the other half before it is asked: this circuit is genuinely bistable, so the
fallback decides *which* valid operating point comes back. **12 of 200 cases resolve to a different root**
than a flat-start fallback would have found, all of them stable, all of them admissible. The guarantee is
that you never land on an impossible operating point — not that there is only one right answer. That is
measured in `fold_results.json`, not hand-waved (§6b, concession 3).

*"Silent wrongness is the failure mode that actually scares engineers. This is the layer nobody builds."*

**Beat B — the risk it hands back to you (35s).** Switch to the browser, `run-bigpump.log` already loaded. A
118 L/min pump against an archive swept over 30–90. The Verify stage goes **amber, not red**, and the report
says what is wrong, what the system did about it, and what happens if you do nothing — *the archive is not
used; the solver starts from the nominal guess, so the warning costs you nothing.* Then the line that is the
whole point:

> I asked two engineers whether this should refuse when it is unsure, or warn and let them decide. They said
> warn, and give us a report. So it does.

Type a name and a reason. **Warm-start anyway.** `10 cold / 7 nominal → 5 warm iterations`, still admissible,
and the audit trail appears at the bottom of the page with who accepted what and why.

**Volunteer the twist — it is the strongest thing in the act.** *"Here the warning was conservative. The
override was right, and it saved two iterations against the nominal guess. That is the argument for warning
instead of refusing — and what makes it safe is that the second gate is not overridable. You can accept a
risky start. You cannot be handed an impossible answer."*

**If you are running long, cut the typing, not the sentence.** Narrate beat B over a pre-run screen and keep
the quote and the twist; they carry the act. The typing is theatre, the requirement is the argument.

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

### A fourth arm — 25 Aug, and this one is the new headline

The `warm` row above still hands Newton the neighbour's converged state **verbatim** — the archived answer,
asserted as this query's answer. It throws away everything the archived run knows except where it landed.
It also knows the *tangent* of its own solution: `dx*/dp = -J⁻¹ ∂F/∂p` by the implicit function theorem, one
linear solve per card, computed once and stored on the Case Card (392 bytes, 277 µs). The start becomes
`x0 = x_j + S_j (p - p_j)` — the neighbour's answer, walked toward the query — instead of standing in for it.

| | cold | nominal | warm (verbatim) | + sensitivity | + ranked, k=5 |
|---|---|---|---|---|---|
| mean iterations | 8.3 | 7.1 | 4.9 | **3.8** | **3.4** |
| vs nominal | — | — | 31.1% | **47.1%** | **51.5%** |

**0 answers differ from the verbatim column**, same 3e-08 bar agreement, `benchmarks/selftest.py` gained a fourth
invariant checking the new derivative (worst relative error 3e-08), and **the phase-1 summary hash did not
move** — `830da3e6a4480676`, same as 16 Aug. This is additive: the archive gained a field, cold/nominal/warm
are bit-identical, and every other number in this file measured against the 31% (the surrogate comparison,
the dimensionality table, the wide-parameter sweep) still is — none of those were re-run.

**Say 51.5%, not 31%, if there is time for one number.** If there is only room for the three-arm table, say
31% and move on — it is still true, and it is the more conservative claim. If asked *"is that the best you
can do?"* the honest answer is now yes, further: it also **fixes** the fold circuit's inadmissible answers
(11 → 1 on the same k=5 gated shortlist, § 6k) — something none of §6k's four rankers managed, because every
arm there, including the oracle, still copied the state verbatim. It is the reason §6k's "four rankers that
all lose" is no longer the last word: none of them were choosing badly, they were all limited by what a
verbatim transfer can buy no matter which candidate is picked.

**One claim was retracted when the third arm went in, and saying so is an asset, not a liability:** *"all 4
cold-start failures rescued"* is gone. The nominal guess rescues the same four, so the archive rescues
nothing the case setup could not. What survives is the iteration count — a smaller claim that holds up when
someone in the room has read the literature.

### The caveat to state before anyone asks

How often cold start *fails* depends on how good the solver's Jacobian is. `benchmarks/bench.py` reports the
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

Full record: [`docs/phases/phase-2-verifier.md`](phases/phase-2-verifier.md). Numbers from `fold_results.json`.

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

**Say the trade-off in the same breath, because the swap changes answers, not just cost.** `benchmarks/fold.py`
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

Full record: [`docs/phases/phase-3-ingest.md`](phases/phase-3-ingest.md).

**The model layer is justified by a number, not an assertion.** Five *scored* artifacts, 35 fields, scored
against ground truth — a sixth, `run-bigpump.log`, was added on 19 Aug to exercise the verifier and is
deliberately excluded from this score (§6d) (correct = within 1%, *or* correctly reported missing). Inventing a plausible value counts as a
miss, not partial credit:

| artifact style | parser | local model (qwen2.5:7b) | **hybrid** |
|---|---|---|---|
| machine logs (3 files, unit conversion + a corrupted value) | **21/21** | 15/21 | **21/21** |
| prose — an English email and a Romanian note | 2/14 | **14/14** | **14/14** |
| **total** | 23/35 (66%) | 29/35 (83%) | **35/35 (100%)** |
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

## 6d. Warn, don't refuse — implemented 19 Aug, the same day it was asked for

Driven entirely by §0b: *generate a report and give out a warning; leave it up to the engineer to proceed with
the simulation or not.* The pipeline used to refuse. Now it reports, warns, and offers an override.

**One rule, two tiers.** The engineer decides what to do with a **risk**; the system decides what is a
**fact**. A `Verdict` carries a severity as well as a decision (`dejasolve/verifier.py`), and the split lands exactly on
the two gates that already existed — gate 1 *estimates* before the solve (warn, overridable), gate 2 *measures*
after it (block, not overridable).

| what | tier | in the demo |
|---|---|---|
| transfer outside the archive's envelope / coverage / regime | **warn** | report + override offered |
| source case on different hardware | **block** | a category error, not a risk |
| a parameter never read from the artifact | **block** | the value must come from an engineer |
| a unit out by orders of magnitude | **block** | the artifact has to be corrected |
| converged root is dynamically unstable or cavitating | **block** | no machine runs there |

**Every path now produces a `report`** — severity, reason, and *consequence*: not only what is wrong but what
the system did about it and what happens if the engineer does nothing. It is emitted on the clean path too; a
report that only appears on bad news is one nobody learns to read.

**An override is attributed**, because §0b said simulation is a departmental activity. `operator` and `basis`
travel with the request and land in `trace["audit"]` with a timestamp. The CLI defaults `--operator` to the OS
user; the page asks for a name and a reason, and remembers the name. An override that then produces an
inadmissible answer writes a second audit entry — that sequence is exactly what an audit trail is for.

**A sixth fixture exists to exercise this:** `data/logs/run-bigpump.log` — a tidy machine log for a **118 L/min**
pump, against an archive swept over 30–90 L/min. Easy to parse, deliberately outside the envelope, so the
verifier warns rather than blocks.

| `run-bigpump.log` | cold | nominal | warm |
|---|---|---|---|
| warned, not overridden | 10 | **7** (used) | — archive not used |
| overridden by the engineer | 10 | 7 | **5**, same answer to 2.4e-09, admissible |

**Concede this before anyone asks: here the warning was conservative.** The override converged to a valid
operating point and beat the nominal guess. That is not an argument against the gate — it is the argument for
*warning* instead of refusing, made with the project's own numbers. What makes the override safe is that gate 2
still runs on the result: the engineer can accept a risky *start*, and cannot be handed an impossible *answer*.

**No quoted number moved.** The new fixture is deliberately excluded from ingest scoring (`scored=False` in
`benchmarks/make_logs.py`) — the accuracy figure measures the parser on messy artifacts, and padding it with an easy
machine log would move a slide number for a reason that has nothing to do with ingest. After the change,
`python run_all.py` still prints ingest 23/35 for the parser and the same phase-1 summary hash
**830da3e6a4480676**.

**Demo beat (Act 3, replacing the old refusal-only ending).** Click `run-bigpump.log` → the Verify stage turns
amber, not red → the report says the archive has never seen a pump this big, and that the solver is proceeding
from the nominal guess so the warning costs nothing → type a name and a reason → **Warm-start anyway** → 10 cold
/ 7 nominal → 5 warm, admissible, and the audit trail appears at the bottom of the page. Then say the sentence:

> I asked two engineers whether it should refuse or warn. They said warn and give them a report. This is what
> that changed.

---

## 6e. Measured results — the surrogate arm, 20 Aug

Full record: [`docs/phases/phase-1b-surrogate.md`](phases/phase-1b-surrogate.md). Reproduce with
`python -m benchmarks.surrogate`; it also runs inside `python run_all.py` as *Phase 1b*.

This closes the last In-scope item in §4 and turns §3's *two sources, one verifier* from a claim into two
measured arms. The surrogate is a **quadratic response surface** — normalise the 7 setup parameters, expand to
36 polynomial features, ridge-fit the 7 converged states — fitted on the 395-case archive in **1 ms**, and
predicting a state in **150 µs**. No new dependency; it is ~40 lines of numpy on purpose, and it is
deliberately not a nearest-neighbour regressor, which would have been retrieval wearing a different hat.

### It is fast, and it is not an answer

| | |
|---|---|
| solver tolerance | 1e-8 |
| residual of the predicted state | **median 8.26**, worst 230 |
| predictions that were actually solutions | **0 / 200** |

**This is the Act 2 "surrogate alone" row, and it is now a number rather than an adjective.** Say it exactly
this way: *the prediction satisfies nothing. Its residual is eight orders of magnitude above where the solver
stops. It is not a slightly-imprecise answer — it is not an answer.*

### As a starting guess it is the best thing on the table

200 fresh cases, same queries as §6a (`sample_cases(200, 99)`), same solver, same tolerance:

| arm | converged | total Newton iterations | mean |
|---|---|---|---|
| cold (flat start) | 196 / 200 | 1631 | 8.32 |
| nominal guess | 200 / 200 | 1420 | 7.10 |
| warm — retrieval | 200 / 200 | 979 | 4.89 |
| **predicted — surrogate** | **200 / 200** | **924** | **4.62** |
| verified — prediction, gated | 200 / 200 | 920 | 4.60 |

**34.9% fewer iterations than the nominal guess** (retrieval gets 31%), and the answers agree with the cold
solve to **2.9e-08 bar / 3.2e-08 rev/min** across all 196 cases where cold converged. `benchmarks/surrogate.py`
cross-checks its cold/nominal/warm arms against `results.json` case by case and asserts they are identical —
two files reporting the same quantity is how two different numbers for the same thing end up on two slides.

### Concede this first, before anyone works it out: the prediction beats the archive

**5.6% fewer iterations than retrieval.** Do not hide it, and do not let it read as a surprise — it is the
expected result and the reason is one sentence:

> The surrogate sees all 395 archived cases for every query. Retrieval uses exactly one of them. Of course the
> fitted model is the better guess — it has four hundred times more information per query.

Three things follow, and they are the whole argument for keeping both:

1. **The surrogate needs the archive to exist first.** 395 solved cases had to happen before it could be
   fitted. Retrieval works from run number two, with no training and no minimum dataset — which is exactly
   what §3's table already claimed and can now be said with the numbers next to it.
2. **The better guess is the one you cannot trust.** Retrieval hands the solver a *real converged state of a
   real case*. The surrogate hands it a state that satisfies nothing. Both end at the same answer here only
   because the solver is what guarantees the answer — which is the pitch, stated by the results rather than by
   me.
3. **It makes the verifier the hero rather than the archive**, and it sharpens the §1 hook rather than
   blunting it: PhysicsAI's discarded prediction is measurably the *best available starting state*, and the
   documented workflow throws it away and starts the validation run from zero. That is the missing arrow, now
   with a number on it.

### And concede this second: the pre-filter on predictions buys nothing *on this circuit*

A predicted state has no source case, so gate 1 does not apply. Gate 2 does, pointed at the *prediction*:
**15 of 200 predicted states are not legal** — all `cavitation`, i.e. the surrogate extrapolated a pressure
below the model's validity floor. The `verified` arm declines those and takes the nominal guess instead.

**What that is worth: 4 Newton iterations across 200 cases** (110 → 106 on the 15 affected), and **none of the
15 failed to converge from the illegal start.** On this circuit the filter is measurably pointless, and saying
so is worth more than the filter.

**Why, and it is Phase 2's own finding rather than an excuse:** the base circuit has a *unique root everywhere
in its envelope* — verified with a 16-seed multi-start over all 400 cases (§6b). Where there is one root, a
bad starting guess can only cost iterations; it cannot change the answer. There is nothing for a pre-filter to
protect. **The place it would matter is the fold circuit — and that experiment has now been run.**

### The fold circuit answers it, and the answer is the best slide in the deck

`python -m benchmarks.surrogate --fold`, on the circuit where the starting guess selects *which* of three roots Newton
finds and the middle one is dynamically unstable. Same archive seed (11) and same 200 queries (seed 77) as
`benchmarks/fold.py`, so this sits directly beside the retrieval result rather than merely near it.

| same circuit, same queries | warm start from **retrieval** | warm start from **prediction** |
|---|---|---|
| naive — valid operating point | 147 | 158 |
| **naive — unstable root, silently wrong** | **4** | **40** |
| naive — no answer at all | 49 | 2 |
| verified — valid operating point | **200** | **200** |
| verified — silently wrong | **0** | **0** |
| verified — total Newton iterations | 1579 | **1300** |

**Say this out loud, slowly, because it is the whole project in two numbers.** The prediction is the *better*
starting guess — 200 valid answers for 18% less solver work than retrieval. Used without a verifier it is
**ten times more dangerous**: 40 silently wrong answers against retrieval's 4.

And the mechanism is worse than the count suggests: **the surrogate converts loud failures into silent
wrongness.** Naive retrieval simply fails to converge 49 times — you notice that; it ruins your morning and
you go and look. The prediction converges 198 times out of 200, and 40 of those converge beautifully onto an
operating point no machine can occupy. *A residual of 1e-8 and an answer that is not real.*

**This is the argument for Layer 3, made against the project's own best component.** "Feed the surrogate's
prediction to the solver" is not the pitch — it is the dangerous half of the pitch. The pitch is *feed it
through a verifier first*, and now there is a number for what happens if you do not.

**The third arm, which exists to keep me honest.** A `post_only` policy — no pre-filter on the prediction,
just the gate on the answer plus escalation — also reaches **200 valid, 0 wrong**, for 1559 iterations against
the guarded policy's 1300.

> **So the pre-filter is a cost mechanism, not a safety mechanism.** Safety comes from gate 2 on the *answer*,
> on both circuits and for both sources. Checking the prediction before spending a solve on it is worth
> nothing on the base circuit and **17% of solver work** on the fold circuit — because there it avoids
> converging onto a root you are about to reject.

State it that way round. Claiming the pre-filter is what keeps you safe would be the easy version and the
false one, and the `post_only` arm exists in `benchmarks/surrogate.py` precisely so the claim cannot be made carelessly.

### What this changes in the deck

- **§6 Act 2's table gets a real top row and a fifth row.** Four measured rows, no placeholder.
- **§3's two-sources table stops being architecture and becomes results.** Both sources measured, one verifier.
- **Act 3 beat A gains its strongest version.** The unstable-root story is currently told with retrieval's 4
  silently wrong answers. The prediction's **40** is the same story an order of magnitude louder, on the same
  circuit and the same queries — and it lands harder because the prediction is the arm that just *won* Act 2.
- **Do not claim the surrogate is PhysicsAI.** It is a 36-feature polynomial standing in for one, so that the
  comparison can be shown on a laptop. Say that out loud; the audience built the real thing.

---

## 6f. Measured results — the failure archive, 20 Aug

Full record: [`docs/phases/phase-2b-failure-archive.md`](phases/phase-2b-failure-archive.md). Reproduce with
`python -m benchmarks.failure_zone`, or as *Phase 2b* inside `python run_all.py`.

Straight from §0b: the engineers asked for **both successful and failed runs** in the archive. They were right
and the code was wrong — `dejasolve/sweep.py` was reducing failures to a tally, and `fold.build_archive` was discarding
**165 of 300 runs**, more than half the compute, behind a comment claiming that filtering is what makes the
archive an asset.

The runs are now kept. Whether that is a feature or a filing cabinet was then measured rather than assumed.

**The candidate rule**, deliberately the simplest thing that could work and the same shape as the gate it
would have joined: *warn when the nearest **failed** case is closer than the nearest **successful** one.*

### It predicts one thing well and the other thing barely

Fold circuit, 135 succeeded / 165 failed, 200 queries:

| | **`hard_case`** — will this run die? | **`bad_transfer`** — will reuse go wrong? |
|---|---|---|
| base rate | 56.0% | 26.5% |
| P(bad \| rule fired) | **74.8%** | 30.4% |
| recall | 76.8% | 66.0% |
| lift over base rate | **1.34x** | 1.15x |
| **AUC** | **0.770** | 0.633 |

### The control is the part worth presenting

Failures cluster where the circuit is hard — and successes are **sparse in the same places**. So a positive
result might mean nothing more than *"you are far from anything solved"*, which the **coverage rule already
sees**. That confound is checked on every run:

| score | `hard_case` AUC |
|---|---|
| distance to nearest **success** only — *what coverage already sees* | 0.650 |
| distance to nearest **failure** only | 0.740 |
| **the rule** (success − failure) | **0.770** |

**0.650 → 0.770: the failed runs carry information the successful ones do not.** The engineer's request was
correct, and it is not an artefact of sparsity.

### And it is *not* being added to the gate — say this before anyone asks why

**Failure-proximity predicts whether the case is hard. It barely predicts whether a transfer is legitimate**
(0.770 against 0.633). Those are different questions and the archive answers one of them. So it is **advisory
information for the engineer, not a rule in the transfer gate** — which is exactly the line §0b already drew:
*the engineer decides what to do with a risk; the system decides what is a fact.*

Two more reasons, both worth saying out loud:

1. **The base rate is 56%.** On a circuit where over half the runs die from cold, *"this one might die"* is
   not news. The rule beats always-warning on precision and the AUC says the ranking is real, but the value
   depends on a failure rate the demo circuit does not have.
2. **It would be inert in the demo.** The base circuit fails 5 times in 400; the rule fires 3 times in 200 and
   catches 0 of the 4 hard cases. `benchmarks/failure_zone.py` prints **UNDERPOWERED** rather than letting anyone quote
   that number as evidence.

> **A failure archive is only worth consulting where runs actually fail.** That is the honest scoping
> sentence, and it is also the answer to *"would this help us?"* — it depends on your failure rate, and here
> is roughly where it starts paying.

### What this changes in the deck

- **The limits slide gains the best line in it:** *"They asked for the failed runs. I added them, measured
  whether proximity to a failure predicts anything, and it predicts case difficulty at AUC 0.77 — but not
  transfer legitimacy, so I did not put it in the gate."* Requested, built, measured, **and declined on the
  evidence.**
- **Nothing in the demo changes.** No new stage, no new rule, no new artifact on screen.
- **It is the third claim this project has tested and not shipped**, after the rescued-failures claim (§6a)
  and the prediction pre-filter as a safety mechanism (§6e). That pattern is the most credible thing about
  the work — and this time the measurement happened *before* the code would have gone in.

---

## 6g. Measured results — hundreds of parameters, 20 Aug

Full record: [`docs/phases/phase-1c-dimensionality.md`](phases/phase-1c-dimensionality.md) ·
figure: `results/figs/dimensionality.png` · reproduce with `python -m benchmarks.dimensionality`.

From §0b: *these simulations have hundreds of parameters, not seven.* Correct, and the useful question is not
whether 7 is small — it is **which layer breaks first when it is not 7.**

The realistic case is not hundreds of parameters that all matter; it is hundreds *recorded*, of which a
handful drive any given output. So the physics stays exactly as it is and the *recorded* vector grows with
entries that are real numbers on the Case Card and inert in the equations, 7 → 1007. Nuisance entries are
drawn on [0, 1], the same range the real parameters occupy after normalisation, so they carry no more weight
in the distance than a real one — **the favourable case for naive retrieval.**

| Case Card width | mean iterations | vs nominal | same neighbour as physics-only retrieval | relative contrast |
|---|---|---|---|---|
| 7 (real only) | 4.89 | **31.1%** | 200/200 | 0.661 |
| 17 | 5.34 | 24.8% | 23/200 | 0.423 |
| 37 | 5.69 | 19.9% | 3/200 | 0.278 |
| 107 | 5.96 | 16.0% | 3/200 | 0.161 |
| 1007 | 6.20 | **12.7%** | 1/200 | 0.052 |

### Say these three in this order

**1. It degrades, it does not collapse — and the reason is not a compliment to the index.** At 1007 recorded
parameters retrieval still beats the archive-free nominal guess by 12.7%. That is because on this circuit
every archived state is a plausible operating point, so even a random one beats a formula. *The archive is
doing the work; the index has stopped contributing.* Circuit-specific — where the starting guess selects the
answer rather than the cost (the fold circuit), a random neighbour is not slower, it is wrong. **Not
measured**; say so.

**2. Retrieval stops working long before it stops helping.** By **37 recorded parameters** the index agrees
with physics-only retrieval on **3 of 200** queries — near chance. Relative contrast collapses 0.661 → 0.052:
every archived case is about equally far away and "nearest" has stopped meaning anything. The iteration count
barely notices, which is what makes it dangerous.

**3. The distance gate cannot see any of it. This is the result.** The coverage rule is re-derived in
whatever space retrieval indexes, so it is compared like with like — its radius scales correctly, 0.53 → 12.52
— **and it keeps admitting 196–198 of 200 at every width.** It does not fail loudly; it fails by *approving*,
because the same concentration that destroyed the signal inflated the radius the distance is checked against.

> **A distance threshold cannot detect the failure of a distance metric.**

Every other gate-1 rule — `envelope`, `breakaway`, `relief` — reads the 7 real parameters and the source's
recorded regime, and is independent of the card's width **by construction rather than by tuning**.

### Why this is the best answer to the question you were actually asked

It justifies the Phase 2 design decision *retrospectively and with a number*. §6b built the gate out of cheap
physics rather than a distance threshold because setup distance predicted transfer cost at r = 0.18. §6g says
what the alternative would have done at scale: **a distance-threshold verifier keeps saying "close enough"
while retrieval degenerates into picking at random.**

And it reframes the whole objection. *"You only have 7 parameters"* is answered not with an apology but with:
*"Here is what happens to this system at 1000. The index degrades and the physics gate does not, and that is
why the gate is built the way it is. The fix is not more data — it is knowing which parameters matter, and
that is a physics question."*

### What to concede before it is asked

- **It is textbook.** Distance concentration in high dimensions is not a discovery. It is still the answer to
  the question, and the non-textbook part is *which* of the two gates it takes down.
- **It says nothing about a model with 300 genuinely active parameters.** That is a harder and different
  problem.
- **The graceful degradation is a property of this circuit**, not a general result.

### What this changes in the deck

- **The limits slide loses its weakest line.** "Only 7 parameters" stops being an admission and becomes a
  measured claim with a figure behind it.
- **Panel C of `results/figs/dimensionality.png` is a slide on its own** if there is room: two lines, one falling to
  the floor and one staying flat at the top, captioned *the gate cannot see retrieval failing.*
- **Nothing in the demo changes.** No new stage, no new artifact on screen.

---

## 6h. The 3D artifact — the boundary, demonstrated rather than promised, 20 Aug

Record: addendum in [`docs/phases/phase-3-ingest.md`](phases/phase-3-ingest.md). Run it with
`python -m dejasolve data/logs/part-bracket.log`, or click it in the page.

From §0b: they asked for something general and talked mostly about **Simcenter 3D**. §0b's answer was that
generality is a property of the layer and the adapter goes on next steps. That is a correct answer and an
unsatisfying one to hear, so there is now a seventh artifact: **a Simcenter 3D / NX Nastran solver log**, which
goes through the real pipeline on stage.

### What happens, in the order it happens

1. **Ingest reads it, and the stage is green.** *"3D structural FE (NX Nastran deck) recognised — 9 facts read,
   none of them this schema's."* SOL 101, the title, Young's modulus, Poisson's ratio, shell thickness, 6
   GRIDs, 2 CQUAD4s. Layer 1 is format-agnostic and this is it working, so marking the stage as failed would
   have been a lie about which component did what.
2. **The domain gate stops it at Retrieve**, before the unit check — deliberately. Plausibility is judged
   against a schema, so if the schema does not apply then *"off by orders of magnitude"* is the wrong
   complaint. An aluminium density is not a badly scaled fluid density; it is a number from another problem.
3. **The report names the boundary:** *the three layers are solver-agnostic but the Case Card schema is not,
   and a state cannot be transferred between physics that do not share unknowns.*

### The line to say out loud

The banner reads `Density .........: 2.70E-09 tonne/mm^3`. `SYNONYMS` maps **"density" onto `rho`**. So a
parser without a domain check records **aluminium as the hydraulic fluid density** and carries on — and the
Case Card says so, in as many words:

    would_have_been_mismapped   rho <- 2.70E-09 tonne/mm^3

**Concede the scale of it honestly.** That is *one* collision, because this schema has seven fields and only
one of them shares a name with anything in a structural log. **No synonym was added to manufacture it** — that
would have been introducing the bug in order to demonstrate catching it. The point is not that there is one
collision here; it is that field names are domain-scoped, and the count grows with the schema. At the hundreds
of parameters §6g is about, "which fields mean the same thing" stops being a footnote.

The unit gate would have caught this particular value by luck, because 2.7e-09 is absurd as a fluid density.
It would not have caught one that happened to look plausible.

**And a foreign artifact never reaches the model.** `ingest_hybrid` returns before calling it — there is
nothing for it to extract, the fields are not in the file, and asking anyway is how a language model gets
talked into inventing seven of them. Cheaper *and* safer, which is unusual enough to mention.

### What this does not claim, and say it before anyone asks

- **No 3D anything is solved.** No mesh, no field, no mapping. Nothing in this repo does structural FE.
- **The transfer adapter is not built**, and that is the actual work — the three-row table on the limits slide
  (§4) is where it lives.
- **It is a demonstration of a boundary, not a crossing of one.** The claim is exactly: *this layer reads your
  file and correctly declines to pretend it can use it.*

That is a smaller claim than "it works with Simcenter 3D", and it is the one that survives being asked a
second question.

### What this changes in the deck

- **The 3D answer stops being verbal.** When someone asks *"would this work on our models?"* — and after §0b
  they will — the answer is a click rather than a paragraph.
- **Act 1 gains a fourth beat if there is room**, and it is 15 seconds: read it, refuse it, show the
  mis-mapping it prevented. If time is tight this belongs in Q&A instead, not in the demo.
- **The limits slide is now backed by a live behaviour** rather than by a promise about future work.

---

## 6i. Measured results — 25 real parameters, 20 Aug

Full record: [`docs/phases/phase-1d-wide-parameters.md`](phases/phase-1d-wide-parameters.md) ·
`python -m benchmarks.selftest` · `python -m benchmarks.wide_sweep`.

§6g widened the *index* with inert entries. This widens the **physics**: `model.HARDWARE` promotes 18 circuit
constants to per-case parameters — discharge coefficient, pump leakage, relief band, and per branch the motor
displacement, return restriction, leakage, Coulomb and breakaway torque, Stribeck velocity, viscous drag. With
the 7 swept parameters that is **25 physical parameters**, and the two shafts are no longer forced to be the
same motor.

**Default-preserving, proved twice.** `benchmarks/selftest.py` measures implicit-vs-explicit defaults at **0.00e+00**,
and the phase-1 summary hash is still **830da3e6a4480676** after the refactor. Nothing measured before today
stopped being comparable.

**`benchmarks/selftest.py` was written before the change, not after.** The refactor threads per-branch constants through a
hand-derived analytic Jacobian; a transcription slip there would not crash, it would quietly change iteration
counts. So: analytic against central differences, including on cases where the branches are built differently
— worst relative error **1.5e-08**, and `run_all.py` refuses to regenerate anything if it fails.

### The headline holds when the parameters are real

`benchmarks/wide_sweep.py`, 6 machine variants with many operating points each — the archive shape §0b describes:

| arm | mean iterations |
|---|---|
| cold | 8.61 |
| nominal | 7.08 |
| **warm — retrieval over all 25** | **5.21** |

**26% fewer iterations than the nominal guess**, against 31% on the 7-parameter circuit.

### The finding, and it belongs to Layer 1

**0 of 200 nearest neighbours came from a different machine.** With hardware on the Case Card, those 18
dimensions dominate the distance and retrieval groups by design without being told to. What stops a state
crossing machines is *recording the hardware*, not the gate.

### The bug that found — say this one out loud, it is the best thing here

That null was suspicious: within a variant, every unit had bit-identical hardware. Real units do not. Adding
manufacturing scatter broke the `hardware` rule instantly — and the rule had never been measured, because on
the 7-parameter circuit every case was the same machine and it was unreachable.

| per-unit scatter | exact match | per-constant 5% band | **aggregate 5% band** |
|---|---|---|---|
| 0% | 197 admitted | 197 | **197** |
| 2% | **0 admitted** | 50 | **198** |
| 5% | 0 | 0 | 17 |

**An exact-match rule refuses every transfer the moment two units of one design are not identical.** A
per-constant band does not save it either: with 18 constants, *"refuse if any one is out of band"* is a
multiple-comparisons problem, and at 2% scatter it refused 150 of 200 same-machine transfers — the 76% that
arithmetic predicts. **A per-parameter threshold degrades as the parameter count grows**, which is exactly the
failure §6g finds in the coverage rule.

The fix compares the **norm** rather than the worst draw, and comes with a stated limit rather than a tuned
constant: at 5% scatter against a 5% band it refuses again, correctly, because two units differ by about
√2 × the scatter and **the band has to exceed the fleet's**.

> *"I promoted 18 constants to parameters. That made a rule reachable that had never been reachable before,
> and it was wrong — it would have refused every transfer in any fleet with manufacturing tolerance. The
> parameter count did not just make the model bigger; it made a latent bug visible."*

---

## 6j. Measured results — top-k retrieval, declined, 20 Aug

Full record: [`docs/phases/phase-2c-topk.md`](phases/phase-2c-topk.md) · `python -m experiments.topk`.

§3 promised a retrieval layer that decides *which* past run to start from; one `argmin` is a thin version of
that. So: take the k nearest, gate each, start from the first admitted. On the fold circuit the gate refuses
**69 of 200** transfers, and each refusal abandons an archive that might hold an admissible case two rows down.

Two ways to spend the candidates were measured, because testing only the one that loses would be worthless —
**selection** (first candidate gate 1 admits) and **escalation** (try the next archived candidate when gate 2
rejects the answer).

| fold, k | selection: used archive | mean iters | inadmissible | escalation: mean iters | inadmissible |
|---|---|---|---|---|---|
| 1 | 131 | 7.75 | 3 | 7.89 | **0** |
| 3 | 160 | 7.78 | 3 | 8.35 | **0** |
| 10 | 172 | 7.88 | **4** | 8.60 | **0** |

Base circuit: identical at every k.

**Both directions say k = 1 is right.** Selection depth uses the archive far more and is worse for it —
iterations up, and one more inadmissible answer, because a deeper candidate is further away and further away
is a worse guess than a formula built from the case's own parameters. Escalation depth is already perfect at
k = 1, so every extra candidate is a 9% bill for an improvement of zero.

**And on the base circuit depth cannot help even in principle.** The refusals there are `envelope` and
`coverage` — rules about the **query**, not the source. No candidate can satisfy a rule the source was never
party to.

> **A refusal is a statement about the archive, not about the candidate.** *"This archive has nothing for
> you"*, not *"try the next one"*.

### What to say, and what it opens

The Phase 1 policy — one neighbour, gated, nominal fallback — was chosen for simplicity before any of this
could be measured. It is now **the measured optimum among the obvious alternatives**, which is a better thing
to have than an untested default.

And it sharpens the open question rather than closing it. Depth ordered *by distance* does not pay — but this
project already knows distance is weak (r = 0.18). The well-posed question is now **whether a better
*ordering* of the same candidates pays**, and that is exactly where a selection agent would have to earn its
place. `experiments/topk.py` is the harness: candidates, gate, cost accounting and answer-movement check all exist.
Prediction on record, as with the surrogate: it will not beat the physics gate.

---

## 6k. Measured results — the selection agent, declined, 20 Aug

Full record: [`docs/phases/phase-2d-selection-agent.md`](phases/phase-2d-selection-agent.md) ·
`python -m benchmarks.agent_select` · `--model granite4` for the model arm.

§6j left one question open: depth ordered *by distance* does not pay, but distance is a weak signal (r = 0.18),
so does a better **ordering** pay? A selection agent is the obvious thing to try, and this is it — measured.

**The ceiling came first, before any GPU time.** Solving every candidate bounds what *any* ranker could win.
At 1% the question would have closed without an inference call; it came back at **11.8% (base)** and
**14.3% (fold)**, so the experiment was worth running. **A random floor came second**, because a ranker that
contributes nothing still lands somewhere between distance and oracle.

Four rankers, k = 5, the gate holding the veto in every arm — no ranker can admit what the physics refuses:

| arm | base (200) | fold (200) |
|---|---|---|
| **oracle** — solves every candidate; not achievable | **868** | **1361**, 5 inadmissible |
| distance — today | 984 | 1589, 11 |
| physics — by estimated regime match | 996 | 1589, 11 |
| random — no opinion | 1018 | 1584, 13 |
| **granite4** (3.4B) | **1038** | 1575, 10 |
| **qwen2.5:7b** (7.6B, 40 cases) | 205 vs distance 198, random 207 | 319 vs distance 303, random 314 |

**Zero parse failures throughout.** The models answered cleanly and chose badly.

### The five things to say, in order

1. **Both models rank at or below chance.** granite4 lands *below* the random floor on the base circuit. They
   disagreed with distance on most queries, so they were choosing — the choices just carried no information.
2. **The 7.6B model is no better than the 3.4B one**, which is why it was run: without that control,
   *"you only used a small model"* is an unanswerable objection to a null.
3. **Ranking by physics fails for the interesting reason.** On the fold circuit it is byte-identical to
   distance, because **the gate already uses regime match to decide admission** — among admitted candidates
   the agreement is constant and every score ties. *A signal cannot be spent twice.*
4. **On the fold circuit distance is itself no better than chance** (1589 against 1584). That is r = 0.18 made
   visible as an ordering rather than a correlation.
5. **The headroom is real and nothing cheap reaches it.** The oracle is 12–14% below everything, and it gets
   there by solving each candidate. Capturing it needs a predictor of *transfer cost* — exactly the quantity
   §6b measured distance as failing to predict. Naming that is more honest than promising a better prompt.

> *"I built the agent. I measured the ceiling first, so I would know whether it could help at all, and a random
> floor, so I would know whether it did anything. Two local models — 3.4B and 7.6B — both ranked at or below
> random, and so did ranking by physics, because the gate had already used that information to decide
> admission. The 12% a perfect ranker would win is real, and nothing I tried could see it."*

**Quote the model arm as "at or below chance", not to three significant figures.** `temperature: 0` and a
fixed seed did not make Ollama bit-reproducible: two runs over the same 200 queries captured -47% and -49%.
The conclusion is unmoved -- both are below the random floor -- but the digits are not stable, so the model
arm writes its own file and stays out of `run_all.py`. The deterministic arms are exact and are in it.

**This is the fifth claim the project has tested and declined**, after rescued failures (§6a), the prediction
pre-filter as a safety mechanism (§6e), the failure-proximity gate rule (§6f) and top-k retrieval (§6j). The
pattern is the most credible thing in the deck — and this one cost two models and a prompt to establish.

### The headroom this section could not reach — reached, 25 Aug, and not by ranking

Point 5 above named what was missing: *"capturing it needs a predictor of transfer cost."* Every arm in this
table shares one assumption — the transferred state is the neighbour's state, verbatim, and the only freedom
is *which* neighbour. That assumption is what makes the ceiling a ceiling. Differentiating the converged
residual through the implicit function theorem gives `dx*/dp = -J⁻¹ ∂F/∂p` at the archived solution — a
predictor of transfer cost, computed offline and stored on the card, not asked of a model. `‖S_j Δp‖` scaled
per state is that predictor, and ranking by it is the sixth arm this table did not have:

| arm (k=5, gated) | base total | fold total, inadmissible |
|---|---|---|
| oracle *(this table's ceiling)* | 868 | 1361, 5 |
| distance — today | 984 | 1589, 11 |
| **+ sensitivity (transfer only, distance still picks)** | **757** | **1067, 1** |
| **+ sensitivity, ranked by it** | **705** | **1026, 1** |

**Both beat the oracle in this table**, because that oracle bounded *selection among verbatim transfers* and
this is not one. It is not a rebuttal of §6k — every conclusion there about the four rankers stands, and
distance genuinely is a weak *ordering* signal on the states this table gave it to rank. What changed is the
thing being ranked stopped being a fixed cost. Full numbers and the fold-circuit safety result (inadmissible
11 → 1) in `docs/phases/phase-1-the-number.md` § *A fourth arm*.

---

## 7. 10-minute presentation — time budget

*Re-budgeted 19 Aug: one slide added for the engineer interview (§0b), and the demo is 10s longer because
Act 3 gained a second beat. The time came out of architecture and platform, not out of the demo or the
results.*

| Time | Slide | Content |
|---|---|---|
| 0:00–0:45 | Hook | **The PhysicsAI workflow diagram with the missing arrow drawn in red.** "It predicts the answer at every node. Then, to check it, we start the solver from zero." Name the product once |
| 0:45–1:50 | Problem | The evidence bullets. PhysicsAI's discarded prediction. HASTT 50%. Client for Git finds files, not physics. DAE init failures. **Now opens with the three-gate loop** — concept → prototyping (25 vehicles) → series production, every backward arrow expensive (§0b). Their framing, not yours |
| 1:50–2:30 | **What already exists** | PhysicsAI 2026.1, ROM Builder, RomAI, AMR, Insights Hub anomaly detection, Design Copilot NX — *"I checked. Here's what Siemens already has, and here's the one arrow that's missing."* **Name Teamcenter SPDM here before anyone else does** (§0b): it answers *which files exist*; this answers *which solved state is physically closest, and whether reusing it is legitimate*. **This slide buys you enormous credibility with this specific audience — they built these** |
| 2:30–3:30 | Solution architecture | The 4 layers, one sentence each. The precision statement about *what* is warm-started. One line on solver-agnosticism (§0/Q1, amended) — do not oversell it here, the adapter table at 8:50 is where it is earned |
| 3:30–4:10 | **What the engineers asked for** *(new)* | *"I spent an hour with two engineers. Three things came out of it."* The three gates (already used at 0:45), *make it general*, and — the one that changed code — **refuse or warn? They said warn, and give us a report.** State which you implemented and which you did not. **This is the strongest slide a student can put in this room, and it is the setup for Act 3** |
| 4:10–7:00 | **Demo** | The 3 acts. Act 2's table now has five measured rows and carries the *prediction beats retrieval* concession (§6e); Act 3 is two beats — the fact it will not let you overrule, then the risk it hands back to you |
| 7:00–8:10 | Results | The measured table. Iterations, failure rate, wall time. Then translate to Simcenter X credits / kg CO₂ |
| 8:10–8:50 | Why it's a platform | The archive is a flywheel: the more the company simulates, the faster it gets. Cloud/Docker architecture slide |
| 8:50–9:30 | Limits + next | What you did *not* do, honestly. **The three-row adapter table** — Amesim / STAR-CCM+ / Simcenter 3D, same layers, different object transferred (§4). FMI/FMU initialisation as the obvious next step |
| 9:30–10:00 | Close | One sentence, the name again |

**Act 2 got heavier on 20 Aug and its 55 seconds did not.** Five rows and a concession will not fit at
speaking pace. Rehearse it against a timer first, and if it overruns, the thing to drop is the *cold* row —
it is the baseline you already argue against elsewhere, and §6a's "lead with 51%" rule means you
are not leaning on the flat-start comparison anyway. Do not drop the concession; a table with an unexplained winner invites the
question you did not get to answer.

**The 3:30 slide has to pay for itself in 40 seconds.** Do not narrate the meeting. Three bullets, one of them
a requirement that changed the code, and then hand straight to the demo that shows it. If rehearsals run long,
this slide is *not* the cut — cut 10s from the architecture slide and 10s from the platform slide again.

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

## 8b. The engineer interview — accept, then prepare ✅ **held 19 Aug**

> **Answers and consequences: §0b.** Q1 and Q4 were answered directly; Q3, Q5, Q6, Q7 and **Q8** were not.
> The two extras they volunteered (the three vehicle gates, and "make it general — Simcenter 3D") changed the
> deck more than most of the prepared questions would have. Kept below as written, because which questions
> got answered is itself part of the record.

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

**What actually happened (19 Aug):** it was a spoken meeting, so the record in §0b is *paraphrase, not
verbatim* — say "the engineers I spoke to said", never use quotation marks on a slide. Q4 became a verifier
rule the same day (§6d). Q3, Q5, Q6 and Q8 went unanswered, and the decision was taken not to chase them —
reasoning in §0b.

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
*(The interview happened on 19 Aug — §0b. This requirement is no longer a guess, so quote them: "I asked, and
they told me to warn rather than refuse.")*

**"If the prediction is the better guess, why not just use the prediction?"** — *(The question Act 2 sets up
and Act 3 answers. It is the best question anyone can ask you.)* Because on the circuit where a starting guess
can select the answer rather than just the cost, the unverified prediction is **ten times more dangerous** —
40 silently wrong answers against retrieval's 4, on the same 200 cases. It also converges more often, which
sounds good and is not: naive retrieval fails outright 49 times and somebody notices, while the prediction
converges 198 times out of 200 and 40 of those are impossible operating points at a residual of 1e-8. **Use
the prediction — it is the best starting state available. Just never use it unverified.** That is the product.

**"Your model beat your archive. Why keep the archive?"** — *(The obvious question the moment Act 2's table
is on screen. Concede before it is asked, §6e.)* It did, by 5.6%, and it should have: the surrogate sees all
395 archived cases for every query and retrieval uses exactly one. Three things keep the archive. It needed
those 395 solved cases to exist before it could be fitted, and retrieval works from run number two — no
training, no minimum dataset. The prediction satisfies nothing; median residual 8.26 against a solver
tolerance of 1e-8, and 0 of 200 predictions were solutions — the recalled state is at least a real answer to a
real case. And both end at the same converged answer only because the solver is what guarantees it, which is
the argument I am making. **The better guess is the one you can trust least. That is why the verifier gates
both, and why it is the layer worth building.**

**"Is your surrogate PhysicsAI?"** — No, and I would not claim it. It is a 36-feature quadratic response
surface in 40 lines of numpy, standing in for a PhysicsAI-class model so the comparison fits on a laptop.
PhysicsAI does geometric deep learning on full fields; mine does polynomial regression on seven numbers. The
point it demonstrates is structural, not numerical: whatever produces the prediction, the prediction is
currently thrown away before the validation run.

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

**"What if the retrieved case is wrong?"** — That's Layer 3, and it's Act 3 of the demo. Not using the
archive is a feature.

**"If the engineer can override the verifier, what is it actually for?"** — *(The sharpest question in the
list, and it exists because of the 19 Aug change. Have this one cold.)* Two things are being conflated. Before
the solve the verifier is **estimating** — it has closed-form bounds and no answer yet, so it can be
conservative and wrong, and my own demo case proves it: it warns about the 118 L/min pump, the engineer
overrides, and the override is right. Making that a hard refusal would mean a tool that is wrong and cannot be
argued with, which is a tool people switch off. After the solve it is **measuring** — eigenvalues of a
converged state — and there is no override, because "no machine runs at this operating point" is not an
opinion. So: you can accept a risky *start*; you cannot be handed an impossible *answer*. And every
acceptance is recorded with a name, a reason and a timestamp, which is more than the current process produces.

**"Why not just warn about everything, then?"** — Because a warning you cannot act on is noise, and noise is
how a gate gets ignored. A missing parameter is not a risk to weigh, it is a value that has to come from a
person; there is nothing for an engineer to decide, so the system does not pretend to offer them a decision.

**"Does this scale to 3D fields / real meshes?"** — *(Expect it: the engineers I interviewed asked for
exactly this, and Simcenter 3D is what they talked about most.)* Not in this demo, and I say so on the limits
slide — with the three-row table: same three layers, different object transferred. Amesim moves a state
vector and is essentially free; STAR-CCM+ moves a field through an XYZ table, which is the manual path that
already exists; Simcenter 3D needs a field mapped between meshes, and that is real engineering. The retrieval
and verification layers are mesh-agnostic — a Case Card and a verifier do not know what produced the state
they reason about. The transfer operator is the adapter, and it is the first next-steps item.

**"So is this an Amesim project?"** — No. It is a solver-agnostic layer with a system-simulation reference
implementation, and I chose that implementation because it is the one I could validate end-to-end and prove
with numbers in the time I had. Every figure in this deck regenerates with one command; a 3D demo I could not
have measured would have been a better-looking talk and a worse project.

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

**Corrected 20 Aug — this was the plan, and it is not what shipped.** The original list is kept below the
line because the difference is worth a sentence on the limits slide: most of it turned out to be unnecessary.

**What actually ships:** Python · NumPy (Newton and the analytic Jacobian are hand-written; no SciPy) ·
plain numpy nearest-neighbour, no index library · FastAPI + one hand-written HTML page, no Streamlit ·
Docker Compose with **two** services from one image · matplotlib for the figures · optional local model via
Ollama for ingest only. **Four wheels total.** Full mapping, including what each layer becomes at scale:
[`docs/architecture.md`](architecture.md).

*Original intent, superseded:* ~~Python · NumPy/SciPy (`solve_ivp`, `fsolve`/Newton; `casadi` if you go DAE) ·
FAISS or sklearn NN or pgvector · sentence-transformers or an API model for embeddings · FastAPI + Streamlit ·
Docker Compose (runner, index, MinIO, Redis, api) · matplotlib for the convergence plots.~~

**Why it shrank, and say this if asked:** every one of those was dropped because the simplest thing that could
work did work, and each dependency dropped is one fewer thing to explain and one fewer thing to break in a
live demo. An index library over 395 rows would have been slower to justify than to write.

**Keep a `results.json` from day one.** Every benchmark number in the deck must be regenerable by one command.
