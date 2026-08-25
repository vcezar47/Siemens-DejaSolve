# Phase 1g — the baseline that beats the archive, and what survives it

**Built:** Tue 25 Aug 2026 · [`../coupled.py`](../coupled.py) ·
[`../manifold.py`](../manifold.py) · not in `run_all.py`

This is the most important negative result in the project and it should go on a
slide rather than into a drawer.

## The objection nobody had made yet

§6a upgraded the baseline once already, from a flat start to
`model.nominal_start`, after [WARP](https://arxiv.org/abs/2605.05728). But
`nominal_start` is still three rules of thumb. A competent engineer does not
guess — they **decompose**.

On this circuit each branch sees the rest of the world through one scalar, the
manifold pressure. Fix that scalar and the branch closes in closed form: drop
the Stribeck dip and the torque balance is a quadratic in shaft speed, with both
orifice drops quadratic in flow because a motor passes `kd·w`. Then bisect the
scalar until supply meets demand. No archive, no solve, no residual evaluation.

**It beats the archive outright.**

| circuit | shipped `nominal_start` | archive (ranked + 1st order) | decomposed guess |
|---|---|---|---|
| base, mean iterations | 7.10 | 3.44 | **2.70** |
| fold, mean iterations | — | 7.40 | **4.52** |
| fold, failures | — | 49 / 200 | **0** |
| fold, inadmissible roots | — | 4 | **0** |

Against the decomposed baseline the ranked arm scores **−27.4%**. It also takes
the fold-circuit claim with it: "4 silently wrong → 0" is currently credited to
the archive plus the verifier, but the formula gets 0 too — dropping the
Stribeck term lands the quadratic on the viscous branch, which is the stable
root, so it never visits the unstable middle one.

Every measured number in this project is still correct. What is not established
is that they were measured against the baseline a sceptic would pick.

## Three attempts to find a circuit that does not decompose

If the archive is to win on iteration count, it needs a circuit where a
per-branch formula cannot work. Three were built, each ordinary hardware, each
with an analytic Jacobian verified before any number was taken.

**1. A wider machine** (`manifold.py`, up to 42 unknowns / 114 parameters).
Failed: wider is *more* decomposable, because N branches in parallel are N
nearly-independent problems. With a competent baseline the archive goes negative
past four branches (−13.6% at eight).

**2. A load-sensing pump** (`coupled.py`, first version). The pump reads the
highest branch pressure and destrokes to follow it, so every branch feeds back
into every other branch's supply. Failed, and instructively: load sensing
*raises* pressure until the load is met, so it prevents shafts from sticking.
One break-away configuration in the entire archive. Decomposed won by 40–45%.

**3. A shared return manifold** (`coupled.py`, current). Every branch exhausts
into one node draining through one orifice, so each branch's flow raises the
back-pressure the others must push against — genuinely non-monotone feedback,
and a bistable band exists where `t_stat / kt ≈ p_crack`. Failed anyway:
decomposed won by 34–54%.

**The pattern is the result.** Phase 1 already recorded it without recognising
the consequence: *"monotone dissipative networks are well-behaved by
construction."* A hydraulic network is a small number of shared pressures
joining locally-closed-form branches. That is the definition of decomposable,
and no amount of extra branches, parameters or feedback paths changed it.

## What actually survives, and it is measurable

A decomposed initialiser is **bound to its topology**:

| circuit | unknowns | does the base circuit's initialiser apply? |
|---|---|---|
| base / fold | 7 | yes — it was derived for it |
| geometry | 12 | no — wrong state dimension |
| manifold (n=4) | 22 | no — wrong state dimension |
| coupled (n=4) | 14 | no — wrong state dimension |

Not "works worse" — **cannot be called at all**. Each of the three circuits
needed its own derivation (torque quadratic plus a bisection; plus line losses;
plus a fixed point on the shared return), and each is about forty lines of
algebra specific to that circuit. Retrieval needed nothing: the same code, on
any circuit whose Case Card you can build, from run number two.

So the honest claim is not *"fewer iterations than a competent tool."* It is:

> A hand-derived initialiser beats retrieval on the circuit it was written for.
> Nobody writes one per model. Retrieval is within ~30% of it, needs no
> derivation, and transfers to a circuit it has never seen.

That is smaller than the current pitch and it is defensible, which the current
pitch is not once someone in the room asks the question.

## Recommendation

1. **Add the decomposed arm to `bench.py` as a fourth baseline** and report it.
   It is the sixth claim this project has tested and declined, after rescued
   failures (§6a), the prediction pre-filter (§6e), the failure-proximity rule
   (§6f), top-k retrieval (§6j) and the selection agent (§6k). The pattern of
   declining its own claims is the most credible thing in the deck.
2. **Move the speed number off the headline.** Keep it, with the decomposed arm
   beside it, on a limits slide.
3. **Lead with the layers a formula cannot replace** — ingest (a messy artifact
   into a Case Card) and the verifier (is this transfer admissible, is this root
   physical). Neither has a formula-based competitor, and neither is touched by
   anything in this document.
