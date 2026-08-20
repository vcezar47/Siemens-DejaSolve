# Phase 2c — Top-k retrieval, measured and declined

**Built:** Thu 20 Aug 2026 · **Gate:** does walking deeper into the archive beat one `argmin`? → ✅ measured,
**and the answer is no**
`python topk.py`.

§3 promised a retrieval layer that decides *which* past run to start from, and one `argmin` is a thin version
of that. The obvious thickening: take the k nearest, ask the verifier about each, start from the first it
admits. On the fold circuit the gate refuses **69 of 200** transfers today and each one abandons an archive
that might have held an admissible case two rows down.

Two ways to spend k candidates, because they answer different questions, and only testing the one that loses
would be weak:

- **selection** — first candidate gate 1 admits; if its answer turns out inadmissible, that is the answer.
- **escalation** — when gate 2 rejects the converged answer, try the *next* archived candidate before falling
  back to the nominal guess. This is `fold.guarded_transfer`'s ladder with its first rungs moved inside the
  archive.

## Measured — fold circuit, 200 queries

| k | selection: used archive | mean iters | inadmissible | escalation: mean iters | inadmissible |
|---|---|---|---|---|---|
| 1 | 131 | 7.75 | 3 | 7.89 | **0** |
| 2 | 150 | 7.76 | 3 | 8.10 | **0** |
| 3 | 160 | 7.78 | 3 | 8.35 | **0** |
| 5 | 165 | 7.84 | 3 | 8.46 | **0** |
| 10 | 172 | 7.88 | **4** | 8.60 | **0** |
| 25 | 172 | 7.88 | 4 | 8.61 | **0** |

Base circuit: **identical at every k**, 198 of 200 using the archive and 4.92 mean iterations throughout.

## The finding

**Both directions say k = 1 is right, for different reasons.**

**Selection depth makes things worse.** It uses the archive far more — 131 → 172 — and pays for it: iterations
up 7.75 → 7.88, and inadmissible answers up from 3 to 4. Using the archive more often is not the objective;
it was never the objective. A deeper candidate is further away, and further away is a worse guess than a
formula built from the case's own parameters.

**Escalation depth buys nothing because there is nothing left to buy.** It reaches **0 inadmissible at k = 1**
— falling back to nominal when the archive's answer is rejected is already sufficient, which is what
`fold.py` does. Every extra candidate after that costs solves: 7.89 → 8.60 mean iterations, a 9% bill for an
improvement of zero.

**On the base circuit depth is structurally incapable of helping**, and this is the part worth understanding
rather than just recording. The two refusals there are `envelope` and `coverage` — rules about the **query**,
not about the source. A query outside the archive's envelope is outside it for every candidate; a query beyond
the coverage radius gets further from each successive one. No amount of depth can satisfy a rule the source
case was never party to.

> **A refusal is a statement about the archive, not about the candidate.** When the gate declines the nearest
> case, the useful reading is "this archive has nothing for you" rather than "try the next one".

## Why this is worth having as a null

The current policy — one nearest neighbour, gate it, fall back to nominal — was chosen in Phase 1 for
simplicity, before any of this could be measured. It is now the measured optimum among the obvious
alternatives rather than the first thing that was tried.

## What it opens up

Depth ordered **by distance** does not pay. That is not a general statement about depth; it is a statement
about the ordering, and this project already knows that distance is a weak signal — setup distance predicts
transfer cost at r = 0.18 (§6b). So the well-posed version of the question is now:

**does a better *ordering* of the same k candidates pay, where "better" is not distance?**

That is where a selection agent would earn its place, and `topk.py` is the harness it would be measured in:
the candidates, the gate, the cost accounting and the answer-movement check already exist. The prediction on
record is that it will not beat the physics gate — the same prediction the surrogate arm made and lost
gracefully.

## Rejected

- **Wiring top-k into `dejasolve.analyse()`.** It was built to be measured, and it lost. Shipping it would
  have added a knob that makes the pipeline slower and marginally less safe.
- **Reporting "used the archive 172 times instead of 131" as an improvement.** It is the metric that flatters
  the feature and it is not the objective.
- **Testing selection only.** Escalation is the version that could have won, and leaving it out would have
  made the null look like a rigged demolition.
