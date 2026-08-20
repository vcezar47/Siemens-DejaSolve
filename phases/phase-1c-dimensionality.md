# Phase 1c — Retrieval at hundreds of parameters

**Built:** Thu 20 Aug 2026 · **Gate:** answer *"real models have hundreds of parameters, you have 7"* with a
measurement → ✅
Reproduce with `python dimensionality.py`, or as *Phase 1c* inside `python run_all.py`.
Figure: [`../figs/dimensionality.png`](../figs/dimensionality.png).

From §0b: an engineer pointed out that these simulations carry hundreds of parameters, not seven. He is
right, and the useful question is not whether 7 is small — it is **which layer breaks first when it is not 7.**

## The setup, and the assumption that makes it fair

The realistic situation is not "hundreds of parameters that all matter". It is hundreds of parameters
*recorded*, of which a handful drive any particular output: the metering valve and the relief setting decide
this initialisation, while the bracket thickness sits on the same Case Card and has nothing to do with it. A
Case Card carries what the run stated; it cannot know in advance which entries matter.

So the physics is untouched and the *recorded* vector grows with entries that are real numbers on the card
and inert in the equations. Widths tested: **7 → 1007**, nested, so it is one growing Case Card rather than
seven unrelated experiments.

**The nuisance entries are drawn uniform on [0, 1] — exactly the range the real parameters occupy after
normalisation.** They therefore carry no more weight in the distance than a real parameter does. Wider
nuisance would swamp the signal sooner. **This is the favourable case for naive retrieval**, and it still
goes where it goes.

## Measured

| Case Card width | mean Newton iterations | vs the nominal guess | same neighbour as physics-only retrieval | relative contrast |
|---|---|---|---|---|
| 7 (real only) | 4.89 | **31.1%** | 200/200 | 0.661 |
| 10 | 5.11 | 28.0% | 50/200 | 0.552 |
| 17 | 5.34 | 24.8% | 23/200 | 0.423 |
| 37 | 5.69 | 19.9% | 3/200 | 0.278 |
| 107 | 5.96 | 16.0% | 3/200 | 0.161 |
| 307 | 5.95 | 16.2% | 2/200 | 0.093 |
| 1007 | 6.20 | **12.7%** | 1/200 | 0.052 |

Reference arms, constant by construction: the archive-free **nominal** guess at 7.10 mean iterations, and
retrieval restricted to **the 7 that matter** at 4.89.

## Three findings, in increasing order of importance

### 1. It degrades gracefully — it does not collapse

At 1007 recorded parameters naive retrieval still beats the nominal guess by **12.7%**. There is no crossover
in the tested range, and the honest reason is not flattering to the retrieval metric: on this circuit *every*
archived state is a physically plausible operating point, so even a randomly chosen one is a better starting
guess than a formula. The archive is doing the work; the index has stopped contributing.

**This is circuit-specific and must be said as such.** Where a bad neighbour is merely a worse guess, random
retrieval costs iterations. On the fold circuit, where the starting guess selects *which* of three roots
Newton finds, a random neighbour is not a slower answer — it is a wrong one. **Not measured**; §6e's naive
arm (4 silently wrong from a *good* neighbour) is the nearest available evidence for what it would cost.

### 2. Retrieval stops working long before it stops helping

By **37 recorded parameters** the index agrees with physics-only retrieval on **3 of 200** queries — near
chance. Relative contrast falls from 0.661 to 0.052: at that point every archived case is about equally far
away and the word "nearest" has stopped meaning anything. The iteration count barely notices, which is
exactly what makes it dangerous.

### 3. The distance gate cannot see any of it — and this is the result

The coverage rule is re-derived in whatever space retrieval indexes, so it is compared like with like: its
radius scales correctly, 0.53 at 7 parameters to 12.52 at 1007.

**And it keeps admitting 196–198 of 200 at every width.**

The rule does not fail loudly. It fails by *approving* — because the same concentration that destroyed the
signal also inflated the radius the distance is checked against. Both sides of the comparison grow together
and the test stays satisfied while the thing it is testing quietly stops working.

> **A distance threshold cannot detect the failure of a distance metric.**

Every other gate-1 rule — `envelope`, `breakaway`, `relief` — reads the 7 real parameters and the source
case's recorded regime. They are independent of the card's width **by construction**, not by tuning.

**This is the measurement that justifies the Phase 2 decision retrospectively.** §6b built the gate out of
cheap physics rather than a distance threshold because setup distance predicted transfer cost at r = 0.18.
This says what the alternative would have done at scale: a distance-threshold verifier would have gone on
saying *"close enough"* while retrieval degenerated into picking at random.

## What it does not show

- **Nothing about the solver.** The physics is unchanged; this measures the index.
- **Nothing about parameters that genuinely all matter.** A model with 300 *active* parameters is a harder
  and different problem, and this experiment says nothing about it.
- **It is textbook.** Distance concentration in high dimensions is not a discovery. It is, however, the
  answer to *"we have hundreds of parameters"* — being textbook does not stop it deciding whether the system
  works on a real model, and the part that is not textbook is which of the two gates it takes down.

## Rejected

- **Adding the nuisance entries to `PARAM_NAMES`.** They would have entered the envelope rule, the sweep and
  `results.json`, and moved the phase-1 summary hash for an experiment that is not the headline. They live in
  the index only.
- **Comparing an augmented-space distance against the 7-dimensional coverage radius.** The first run did this
  by accident and produced a dramatic 199/200 refusal rate that was pure unit mismatch — a 1000-dimensional
  distance measured against a 7-dimensional threshold. It said nothing about high dimensions and everything
  about mixing two metrics. `coverage_radius_in()` exists so it cannot happen again.
- **Concluding that retrieval "still works fine at 1000 parameters".** The iteration count says so and the
  neighbour agreement says the opposite. Quoting the first without the second would be the most flattering
  and least honest reading available.
