# Graph Report - Siemens-DejaSolve  (2026-08-25)

## Corpus Check
- 56 files · ~195,131 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 676 nodes · 1085 edges · 42 communities (41 shown, 1 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7bc01903`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_model.py|model.py]]
- [[_COMMUNITY_bench.py|bench.py]]
- [[_COMMUNITY_ingest.py|ingest.py]]
- [[_COMMUNITY_sample_cases|sample_cases]]
- [[_COMMUNITY_geometry.py|geometry.py]]
- [[_COMMUNITY_topk.py|topk.py]]
- [[_COMMUNITY_agent_select.py|agent_select.py]]
- [[_COMMUNITY_dejasolve.py|dejasolve.py]]
- [[_COMMUNITY_app.py|app.py]]
- [[_COMMUNITY_fold.py|fold.py]]
- [[_COMMUNITY_viz.py|viz.py]]
- [[_COMMUNITY_Phase 3 — Ingest and the end-to-end run|Phase 3 — Ingest and the end-to-end run]]
- [[_COMMUNITY_wide_sweep.py|wide_sweep.py]]
- [[_COMMUNITY_dimensionality.py|dimensionality.py]]
- [[_COMMUNITY_failure_zone.py|failure_zone.py]]
- [[_COMMUNITY_Déjà Solve|Déjà Solve]]
- [[_COMMUNITY_archive_aurora.py|archive_aurora.py]]
- [[_COMMUNITY_Déjà Solve — Plan (Siemens Summer School 2026)|Déjà Solve — Plan (Siemens Summer School 2026)]]
- [[_COMMUNITY_AWS deployment plan — the real build|AWS deployment plan — the real build]]
- [[_COMMUNITY_Phase 2 — The verifier|Phase 2 — The verifier]]
- [[_COMMUNITY_README|README.md]]
- [[_COMMUNITY_Phase 1 — THE NUMBER|Phase 1 — THE NUMBER]]
- [[_COMMUNITY_Phase 0 — Validate + scaffold|Phase 0 — Validate + scaffold]]
- [[_COMMUNITY_Phase 1b — The surrogate arm|Phase 1b — The surrogate arm]]
- [[_COMMUNITY_Phase 1c — Retrieval at hundreds of parameters|Phase 1c — Retrieval at hundreds of parameters]]
- [[_COMMUNITY_Phase 1e — what if the model did have geometry|Phase 1e — what if the model *did* have geometry?]]
- [[_COMMUNITY_0b. Engineer interview — 19 Aug 2026, and what it changes|0b. Engineer interview — 19 Aug 2026, and what it changes]]
- [[_COMMUNITY_Phase 2d — The selection agent, and four rankers that all lose|Phase 2d — The selection agent, and four rankers that all lose]]
- [[_COMMUNITY_6e. Measured results — the surrogate arm, 20 Aug|6e. Measured results — the surrogate arm, 20 Aug]]
- [[_COMMUNITY_Phase 1d — 25 real parameters, and a latent bug in the hardware rule|Phase 1d — 25 real parameters, and a latent bug in the hardware rule]]
- [[_COMMUNITY_Phase 2c — Top-k retrieval, measured and declined|Phase 2c — Top-k retrieval, measured and declined]]
- [[_COMMUNITY_Phase 2b — The failure archive|Phase 2b — The failure archive]]
- [[_COMMUNITY_6f. Measured results — the failure archive, 20 Aug|6f. Measured results — the failure archive, 20 Aug]]
- [[_COMMUNITY_6g. Measured results — hundreds of parameters, 20 Aug|6g. Measured results — hundreds of parameters, 20 Aug]]
- [[_COMMUNITY_6h. The 3D artifact — the boundary, demonstrated rather than promised, 20 Aug|6h. The 3D artifact — the boundary, demonstrated rather than promised, 20 Aug]]
- [[_COMMUNITY_Architecture — what runs, and what it becomes|Architecture — what runs, and what it becomes]]
- [[_COMMUNITY_0. Mentor feedback — 12 Aug 2026, and what it changes|0. Mentor feedback — 12 Aug 2026, and what it changes]]
- [[_COMMUNITY_3. What it is — 4 layers|3. What it is — 4 layers]]
- [[_COMMUNITY_6a. Measured results — Phase 1, 16 Aug|6a. Measured results — Phase 1, 16 Aug]]
- [[_COMMUNITY_6i. Measured results — 25 real parameters, 20 Aug|6i. Measured results — 25 real parameters, 20 Aug]]
- [[_COMMUNITY_6k. Measured results — the selection agent, declined, 20 Aug|6k. Measured results — the selection agent, declined, 20 Aug]]
- [[_COMMUNITY_8b. The engineer interview — accept, then prepare ✅ held 19 Aug|8b. The engineer interview — accept, then prepare ✅ **held 19 Aug**]]

## God Nodes (most connected - your core abstractions)
1. `Déjà Solve — Plan (Siemens Summer School 2026)` - 25 edges
2. `sample_cases()` - 21 edges
3. `CaseCard` - 18 edges
4. `Verifier` - 16 edges
5. `load_archive()` - 14 edges
6. `jacobian()` - 14 edges
7. `run_bench()` - 12 edges
8. `analyse()` - 12 edges
9. `Déjà Solve` - 12 edges
10. `Phase 3 — Ingest and the end-to-end run` - 12 edges

## Surprising Connections (you probably didn't know these)
- `Archive` --uses--> `CaseCard`  [INFERRED]
  dejasolve.py → casecard.py
- `shortlist()` --references--> `Verifier`  [EXTRACTED]
  agent_select.py → verifier.py
- `evaluate_ceiling()` --calls--> `Verifier`  [EXTRACTED]
  agent_select.py → verifier.py
- `base_circuit()` --calls--> `sample_cases()`  [EXTRACTED]
  agent_select.py → sweep.py
- `run_deterministic()` --calls--> `sample_cases()`  [EXTRACTED]
  agent_select.py → sweep.py

## Import Cycles
- None detected.

## Communities (42 total, 1 thin omitted)

### Community 0 - "model.py"
Cohesion: 0.07
Nodes (53): d_friction(), d_load_torque(), d_relief_opening(), df_dp(), dresidual_dp(), dynamic_scales(), f_dp(), friction() (+45 more)

### Community 1 - "bench.py"
Cohesion: 0.07
Nodes (44): arm_vs_nominal(), _exemplar(), main(), nearest(), nearest_k(), pick_exemplars(), ndarray, Path (+36 more)

### Community 2 - "ingest.py"
Cohesion: 0.07
Nodes (41): CaseCard, detect_domain(), normalise_unit(), parse_number(), The Case Card — the structured record every run artifact becomes.  The archive, Convert a value to its canonical unit. Returns (value, unit_as_given)., Parse a number written the way people actually write them.      Handles scient, One run artifact, structured. `params` is always in canonical units. (+33 more)

### Community 3 - "sample_cases"
Cohesion: 0.08
Nodes (30): Generate the messy run artifacts the ingest layer has to cope with.  Every fix, draw(), main(), Path, The Phase 1 gate figure, drawn from results.json — nothing is hard-coded., Regenerate every number and figure in the deck, from scratch, in one command., asymmetric(), central_dresidual_dp() (+22 more)

### Community 4 - "geometry.py"
Cohesion: 0.11
Nodes (34): central_jacobian(), check_jacobian(), d_line_flow(), jacobian(), line_coeffs(), line_flow(), line_report(), main() (+26 more)

### Community 5 - "topk.py"
Cohesion: 0.10
Nodes (24): base_circuit(), evaluate(), fold_circuit(), main(), ndarray, Path, Walk the archive before abandoning it: k candidates instead of one.  Retrieval, First gate-admitted candidate among the k nearest, else the nominal guess. (+16 more)

### Community 6 - "agent_select.py"
Cohesion: 0.13
Nodes (30): ask_model(), base_circuit(), build_prompt(), evaluate_ceiling(), _fmt_params(), _fmt_regime(), fold_circuit(), main() (+22 more)

### Community 7 - "dejasolve.py"
Cohesion: 0.13
Nodes (18): analyse(), Archive, _audit(), main(), ndarray, Path, End to end: a messy run artifact in, a verified warm-started solve out.  This is, The start to hand Newton for query `params`, from archive case `j`.          Fir (+10 more)

### Community 8 - "app.py"
Cohesion: 0.12
Nodes (19): analyse(), AnalyseRequest, archive(), evidence(), health(), _load(), _mirror_audit_to_dynamo(), HTTP service + demo UI for Déjà Solve.  A service rather than a notebook-style a (+11 more)

### Community 9 - "fold.py"
Cohesion: 0.16
Nodes (20): all_roots(), build_archive(), draw(), fold_cases(), guarded_transfer(), main(), naive_transfer(), ndarray (+12 more)

### Community 10 - "viz.py"
Cohesion: 0.18
Nodes (20): distance_fidelity(), failure_payload(), fit_projection(), main(), parameter_space_fidelity(), pick_tiles(), project(), ndarray (+12 more)

### Community 11 - "Phase 3 — Ingest and the end-to-end run"
Cohesion: 0.11
Nodes (19): 1. Hybrid ingest — parser first, model only for the gaps, 2. An anti-invention check — Layer 1 gets its own verifier, Addendum — 20 Aug: a Case Card is a record *of a kind of model*, End-to-end result, Final measurement, Local models: measured, and the result changed the design, Never invent a value, Phase 3 — Ingest and the end-to-end run (+11 more)

### Community 12 - "wide_sweep.py"
Cohesion: 0.16
Nodes (18): latin_hypercube(), ndarray, Stratified sample in the unit cube — better coverage than plain uniform     for, _arm(), main(), make_cases(), make_variants(), ndarray (+10 more)

### Community 13 - "dimensionality.py"
Cohesion: 0.22
Nodes (16): cdist(), contrast(), coverage_radius_in(), crossover(), draw(), main(), nuisance(), ndarray (+8 more)

### Community 14 - "failure_zone.py"
Cohesion: 0.18
Nodes (16): auc(), contingency(), evaluate(), main(), _norm(), _num(), _pct(), ndarray (+8 more)

### Community 15 - "Déjà Solve"
Cohesion: 0.12
Nodes (17): Before the demo: check the model is actually reachable, Déjà Solve, Hundreds of parameters, Not done yet, Reproduce every number, Result, The archive knows more than the endpoint, The circuit where it does matter (+9 more)

### Community 16 - "archive_aurora.py"
Cohesion: 0.19
Nodes (12): AuroraArchive, _connect(), Aurora-backed archive -- the same interface as dejasolve.Archive, backed by Auro, A fresh connection per call, not a pooled one -- this backend serves a     ten-m, pgvector's text input format for a `vector(7)` value: '[v1,v2,...,v7]'., Overrides __init__ (loads from Aurora, not a file) and nearest()     (queries pg, The one query that actually goes through pgvector rather than numpy.          Ma, _vector_literal() (+4 more)

### Community 17 - "Déjà Solve — Plan (Siemens Summer School 2026)"
Cohesion: 0.12
Nodes (16): 10. Stack, 1. One-line pitch, 2. Problem statement (the 3 evidence bullets for slide 2), 4. Scope, 5. Timeline — re-baselined 16 Aug, updated 19 Aug, 6. The demo — 3 acts, ~3 minutes total, 6b. Measured results — Phase 2, 17 Aug, 6c. Measured results — Phase 3, 17 Aug (+8 more)

### Community 18 - "AWS deployment plan — the real build"
Cohesion: 0.12
Nodes (15): 1. Before deploying, 2.1 Stack 1 — networking, 2.2 Stack 2 — data layer (Aurora, S3, SQS, DynamoDB, bastion), 2.3 Build and push the image — the one step that needs a terminal, 2.4 Stack 3 — compute (ALB, ECS cluster, services), 2.5 Ollama on EC2 (CPU) — the model backend, in the VPC, 2. Deploy — via the console, 3. Wired in — the three follow-ups, now built (+7 more)

### Community 19 - "Phase 2 — The verifier"
Cohesion: 0.15
Nodes (13): Addendum — 19 Aug: the gate stopped being a gate, Files, Honest caveats — say these before anyone asks, Phase 2 — The verifier, Results — 200 fresh fold-circuit cases, The demo case — `foldq-0009`, The fallback rung — changed 18 Aug, The finding that shaped the whole phase (+5 more)

### Community 21 - "Phase 1 — THE NUMBER"
Cohesion: 0.17
Nodes (12): A fourth arm: transferring first-order instead of verbatim (25 Aug), A third arm: the nominal baseline, Benchmark protocol, Deliberately not done, Exemplars picked automatically by `bench.py`, Phase 1 — THE NUMBER, Results, The model, and why it is this model (+4 more)

### Community 22 - "Phase 0 — Validate + scaffold"
Cohesion: 0.20
Nodes (9): Cost, Open at close of phase, Phase 0 — Validate + scaffold, Q1 — which product lines at Brașov? → free choice, Q2 — why would an engineer *not* want this? → deflected into something better, Q3 — "does this already exist?" → not a kill switch, but the claim was wrong, Scaffold, The answers, and what each one changed (+1 more)

### Community 23 - "Phase 1b — The surrogate arm"
Cohesion: 0.20
Nodes (10): 1. The prediction beats the archive — 5.6% fewer iterations than retrieval, 2. Gating the *prediction* buys nothing on this circuit, Measured, Phase 1b — The surrogate arm, Rejected, The finding, The fold circuit — 20 Aug, same day, The third arm, which exists to prevent an easy false claim (+2 more)

### Community 24 - "Phase 1c — Retrieval at hundreds of parameters"
Cohesion: 0.22
Nodes (9): 1. It degrades gracefully — it does not collapse, 2. Retrieval stops working long before it stops helping, 3. The distance gate cannot see any of it — and this is the result, Measured, Phase 1c — Retrieval at hundreds of parameters, Rejected, The setup, and the assumption that makes it fair, Three findings, in increasing order of importance (+1 more)

### Community 25 - "Phase 1e — what if the model *did* have geometry?"
Cohesion: 0.22
Nodes (8): Phase 1e — what if the model *did* have geometry?, Results, The bug the invariant caught, and the real flaw underneath it, The disclaimer this started from, The retrieval question this was actually built for, What is worth keeping from it, What was built, Why it is not adopted, and what the disclaimer should say instead

### Community 26 - "0b. Engineer interview — 19 Aug 2026, and what it changes"
Cohesion: 0.25
Nodes (8): 0b. Engineer interview — 19 Aug 2026, and what it changes, Backlog — wanted, not scheduled, Q — "How often does a run fail, and what do you do?" → the answer that validates the Phase 1 pivot, Q — "Is this done internally?" → No, with one pointer that must be named first, Q — "Refuse when unsure, or warn?" → **warn**, and this is now implemented, Still unanswered — and deliberately left that way (decided 19 Aug), The extras — unasked-for, and two of them change the deck, What did *not* change

### Community 27 - "Phase 2d — The selection agent, and four rankers that all lose"
Cohesion: 0.25
Nodes (7): Four rankers, k = 5, the verifier holding the veto throughout, Phase 2d — The selection agent, and four rankers that all lose, Rejected, Say it this way, The model arm is not bit-reproducible, and that is stated rather than hidden, The order of operations was the design decision, What it says

### Community 28 - "6e. Measured results — the surrogate arm, 20 Aug"
Cohesion: 0.29
Nodes (7): 6e. Measured results — the surrogate arm, 20 Aug, And concede this second: the pre-filter on predictions buys nothing *on this circuit*, As a starting guess it is the best thing on the table, Concede this first, before anyone works it out: the prediction beats the archive, It is fast, and it is not an answer, The fold circuit answers it, and the answer is the best slide in the deck, What this changes in the deck

### Community 29 - "Phase 1d — 25 real parameters, and a latent bug in the hardware rule"
Cohesion: 0.29
Nodes (7): Phase 1d — 25 real parameters, and a latent bug in the hardware rule, Rejected, selftest.py — built before the change, not after, The bug that found, and the fix, The finding: recording hardware makes the index separate machines by itself, What was promoted, wide_sweep.py — and the realistic archive is not 400 unique machines

### Community 30 - "Phase 2c — Top-k retrieval, measured and declined"
Cohesion: 0.29
Nodes (6): Measured — fold circuit, 200 queries, Phase 2c — Top-k retrieval, measured and declined, Rejected, The finding, What it opens up, Why this is worth having as a null

### Community 31 - "Phase 2b — The failure archive"
Cohesion: 0.33
Nodes (6): Measured — fold circuit, 135 succeeded / 165 failed, 200 queries, Phase 2b — The failure archive, Rejected, The control, which is the point of the experiment, The finding, and why the rule is *not* being added to the gate, What was built

### Community 32 - "6f. Measured results — the failure archive, 20 Aug"
Cohesion: 0.40
Nodes (5): 6f. Measured results — the failure archive, 20 Aug, And it is *not* being added to the gate — say this before anyone asks why, It predicts one thing well and the other thing barely, The control is the part worth presenting, What this changes in the deck

### Community 33 - "6g. Measured results — hundreds of parameters, 20 Aug"
Cohesion: 0.40
Nodes (5): 6g. Measured results — hundreds of parameters, 20 Aug, Say these three in this order, What this changes in the deck, What to concede before it is asked, Why this is the best answer to the question you were actually asked

### Community 34 - "6h. The 3D artifact — the boundary, demonstrated rather than promised, 20 Aug"
Cohesion: 0.40
Nodes (5): 6h. The 3D artifact — the boundary, demonstrated rather than promised, 20 Aug, The line to say out loud, What happens, in the order it happens, What this changes in the deck, What this does not claim, and say it before anyone asks

### Community 35 - "Architecture — what runs, and what it becomes"
Cohesion: 0.40
Nodes (5): Architecture — what runs, and what it becomes, At scale: the same four layers, different backing services, Today: one image, two services, What is not built, stated plainly, What would have to change first

### Community 36 - "0. Mentor feedback — 12 Aug 2026, and what it changes"
Cohesion: 0.50
Nodes (4): 0. Mentor feedback — 12 Aug 2026, and what it changes, Q1 — which Simcenter product lines at Brașov? → **Free choice: "toate sunt folosite, alege ce vrei"**, Q2 — why would an engineer *not* want this? → **She didn't answer. She offered an engineer.**, Q3 — "does this already exist?" → **Not a kill switch, but the claim must be sharpened**

### Community 37 - "3. What it is — 4 layers"
Cohesion: 0.50
Nodes (4): 3. What it is — 4 layers, Positioning the verifier vs. PhysicsAI's similarity score, Technical precision — say it exactly this way, Two sources of warm start, one verifier

### Community 38 - "6a. Measured results — Phase 1, 16 Aug"
Cohesion: 0.50
Nodes (4): 6a. Measured results — Phase 1, 16 Aug, A fourth arm — 25 Aug, and this one is the new headline, The caveat to state before anyone asks, What the physics needed

### Community 39 - "6i. Measured results — 25 real parameters, 20 Aug"
Cohesion: 0.50
Nodes (4): 6i. Measured results — 25 real parameters, 20 Aug, The bug that found — say this one out loud, it is the best thing here, The finding, and it belongs to Layer 1, The headline holds when the parameters are real

### Community 40 - "6k. Measured results — the selection agent, declined, 20 Aug"
Cohesion: 0.67
Nodes (3): 6k. Measured results — the selection agent, declined, 20 Aug, The five things to say, in order, The headroom this section could not reach — reached, 25 Aug, and not by ranking

### Community 41 - "8b. The engineer interview — accept, then prepare ✅ **held 19 Aug**"
Cohesion: 0.67
Nodes (3): 8b. The engineer interview — accept, then prepare ✅ **held 19 Aug**, Reply to send (today, short, no hedging), The 8 questions (ordered — if they only answer three, these are the three)

## Knowledge Gaps
- **166 isolated node(s):** `Q3 — "does this already exist?" → **Not a kill switch, but the claim must be sharpened**`, `Q1 — which Simcenter product lines at Brașov? → **Free choice: "toate sunt folosite, alege ce vrei"**`, `Q2 — why would an engineer *not* want this? → **She didn't answer. She offered an engineer.**`, `Q — "Is this done internally?" → No, with one pointer that must be named first`, `Q — "How often does a run fail, and what do you do?" → the answer that validates the Phase 1 pivot` (+161 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Déjà Solve — Plan (Siemens Summer School 2026)` connect `Déjà Solve — Plan (Siemens Summer School 2026)` to `6f. Measured results — the failure archive, 20 Aug`, `6g. Measured results — hundreds of parameters, 20 Aug`, `6h. The 3D artifact — the boundary, demonstrated rather than promised, 20 Aug`, `0. Mentor feedback — 12 Aug 2026, and what it changes`, `3. What it is — 4 layers`, `6a. Measured results — Phase 1, 16 Aug`, `6i. Measured results — 25 real parameters, 20 Aug`, `6k. Measured results — the selection agent, declined, 20 Aug`, `8b. The engineer interview — accept, then prepare ✅ **held 19 Aug**`, `README.md`, `0b. Engineer interview — 19 Aug 2026, and what it changes`, `6e. Measured results — the surrogate arm, 20 Aug`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `sample_cases()` connect `sample_cases` to `bench.py`, `topk.py`, `agent_select.py`, `fold.py`, `wide_sweep.py`, `dimensionality.py`, `failure_zone.py`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `Verifier` connect `topk.py` to `fold.py`, `agent_select.py`?**
  _High betweenness centrality (0.022) - this node is a cross-community bridge._
- **What connects `Can anything rank the candidates better than distance can?  `topk.py` found th`, `The k nearest, each with the gate's verdict already attached.      The gate ru`, `Distance against the best possible pick. No model involved.` to the rest of the system?**
  _325 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `model.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07197763801537387 - nodes in this community are weakly interconnected._
- **Should `bench.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07294117647058823 - nodes in this community are weakly interconnected._
- **Should `ingest.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06887755102040816 - nodes in this community are weakly interconnected._