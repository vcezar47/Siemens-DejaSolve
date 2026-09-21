# Phase records

One file per phase, written **as the phase is implemented** — what was actually
built, what was decided and why, what was measured, and what was rejected.

These are backward-looking records. [`../DEJA_SOLVE_PLAN.md`](../DEJA_SOLVE_PLAN.md)
is the forward-looking plan; where the two disagree, these files are what
happened and the plan is what was intended.

| Phase | Status | Record |
|---|---|---|
| 0 · Validate + scaffold | ✅ closed 16 Aug | [phase-0-validation.md](phase-0-validation.md) |
| 1 · THE NUMBER | ✅ gate met 16 Aug | [phase-1-the-number.md](phase-1-the-number.md) |
| 1b · Surrogate arm | ✅ built 20 Aug — the *predicted* warm start, measured | [phase-1b-surrogate.md](phase-1b-surrogate.md) |
| 1c · Dimensionality | ✅ built 20 Aug — retrieval at 1000 parameters, and what the gate misses | [phase-1c-dimensionality.md](phase-1c-dimensionality.md) |
| 1d · Wide parameters | ✅ built 20 Aug — 25 physical parameters; a latent bug in the hardware rule | [phase-1d-wide-parameters.md](phase-1d-wide-parameters.md) |
| 1e · Geometry | ✅ built 24 Aug — the archive seen, and the circuit drawn in 3D | [phase-1e-geometry.md](phase-1e-geometry.md) |
| 2 · Verifier | ✅ gate met 17 Aug · contract amended 19 Aug (warn/block) | [phase-2-verifier.md](phase-2-verifier.md) |
| 2b · Failure archive | ✅ built 20 Aug — measured, and declined as a gate rule | [phase-2b-failure-archive.md](phase-2b-failure-archive.md) |
| 2c · Top-k retrieval | ✅ built 20 Aug — measured, and declined; k=1 is the optimum | [phase-2c-topk.md](phase-2c-topk.md) |
| 2d · Selection agent | ✅ built 20 Aug — four rankers, all at or below chance; declined | [phase-2d-selection-agent.md](phase-2d-selection-agent.md) |
| 3 · Agent + UI | ✅ gate met 17 Aug (UI shipped) · domain gate added 20 Aug (3D artifact) | [phase-3-ingest.md](phase-3-ingest.md) |
| 4 · Cloud/Docker + final measurements | ✅ gate met 20 Aug — `docker compose up` verified on a clean build; architecture mapped | [../docs/architecture.md](../architecture.md) |
| 5 · Slides + rehearsal | not started | — |

**Rule for these files:** every number quoted here must be reproducible with
`python run_all.py`. If it is not in `results.json`, it does not belong in a
phase record or on a slide.
