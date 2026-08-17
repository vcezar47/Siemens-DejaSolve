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
| 2 · Verifier | ✅ gate met 17 Aug | [phase-2-verifier.md](phase-2-verifier.md) |
| 3 · Agent + UI | ✅ gate met 17 Aug (UI deferred) | [phase-3-ingest.md](phase-3-ingest.md) |
| 4 · Cloud/Docker + final measurements | not started | — |
| 5 · Slides + rehearsal | not started | — |

**Rule for these files:** every number quoted here must be reproducible with
`python run_all.py`. If it is not in `results.json`, it does not belong in a
phase record or on a slide.
