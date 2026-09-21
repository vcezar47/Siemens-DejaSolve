# Phase 1f — does the result scale with complexity?

**Built:** Tue 25 Aug 2026 · [`../manifold.py`](../../experiments/manifold.py) ·
`python -m experiments.manifold --selftest` · `python -m experiments.manifold`

Not in `run_all.py`. The frozen Phase 1 hash does not know this file exists.

## The question, and the tempting wrong answer

The base circuit is 7 parameters and 7 unknowns, and cold start takes ~8.3
Newton iterations. The tempting pitch is: *real models are bigger, cold starts
on them take 30–50 iterations, warm starts still take 3, so the saving grows to
80–90% as complexity rises.*

**That reasoning inflates the baseline, which is the exact error
[WARP](https://arxiv.org/abs/2605.05728) documents and the exact error §6a
already corrects for once.** Making the problem harder so the cold arm looks
worse is the same move as measuring against a flat start. It is also, as it
turns out, factually wrong here.

## What was built

`experiments/manifold.py` generates an N-branch manifold rather than hand-writing one:

```
pump ─[supply]─ p1 ─┬── relief ──> tank
                    ├─[line 0]─ valve 0 ─ MOTOR 0 ─[return 0]─> tank
                    ├─[line 1]─ valve 1 ─ MOTOR 1 ─[return 1]─> tank
                    └─ ... N branches
```

`2 + 5n` unknowns, `10 + 13n` parameters — six of the thirteen per-branch
parameters are pipe geometry, seven are the motor and its friction, so a wider
machine is more *independent hardware*, not just a longer list. A four-function
manifold is ordinary: an excavator's boom, arm, bucket and swing.

| branches | unknowns | parameters |
|---|---|---|
| 2 | 12 | 36 |
| 4 | 22 | 62 |
| 6 | 32 | 88 |

**The residual, the analytic Jacobian and the analytic dF/dp are assembled in
loops**, which is the only reason a 32×32 Jacobian and a 32×88 parameter
derivative are tractable to hand-derive. Verified at every width:

```
PASS  n=2  12 unknowns,  36 params   J 6.9e-08   dF/dp 1.7e-09
PASS  n=3  17 unknowns,  49 params   J 5.5e-08   dF/dp 2.0e-09
PASS  n=4  22 unknowns,  62 params   J 3.0e-08   dF/dp 2.2e-09
PASS  n=6  32 unknowns,  88 params   J 8.6e-08   dF/dp 3.0e-09
```

### The check had to change, and the reason is worth keeping

Probing dF/dp one parameter at a time kept failing on the friction columns, and
the failure was in the instrument. The shaft row is
`(p2-p3)·kt − load_torque` — two O(500) terms cancelling to O(15), so a
difference in that row carries the roundoff of the *terms*. Meanwhile a shaft
spinning past its Stribeck velocity has `exp(−(w/w_strib)²) ≈ 1e-13`, so
`dF/d(t_stat)` is genuinely that small. Analytic `−1.1e-12`, numeric a hard
`0.0`, noise floor `3.3e-10`: **the true derivative sat 300× below what the
difference could resolve**, and no threshold separates "tiny and right" from
"tiny and wrong".

Fixed by checking dF/dp **directionally** — a random unit direction in
parameter space, so every column contributes to one well-scaled number, and a
wrong column is orthogonal to a random direction with probability zero. That is
the standard way to verify a large derivative matrix and the only one that
works here.

## Result 1 — the scaling claim is false

Uniform archive (400 cases, every parameter scattered independently):

| branches | params | nbr dist | cold | nominal | warm | +1st order | +ranked |
|---|---|---|---|---|---|---|---|
| 2 | 36 | 1.745 | 9.07 | 7.26 | 6.95 | 6.96 | 6.54 |
| 3 | 49 | 2.166 | 8.99 | 7.55 | 6.69 | 7.28 | 6.74 |
| 4 | 62 | 2.530 | 9.30 | 8.08 | 7.38 | 8.30 | 7.13 |
| 6 | 88 | 3.156 | 10.10 | 9.69 | 8.57 | 9.66 | 8.63 |

Reduction vs nominal: warm 4.4 → 12.7%, **first-order 4.2 → 0.3%**, ranked
10.0 → 9.8%.

**The first-order transfer degrades faster than the verbatim one — the opposite
of the hypothesis.** At four branches it is *worse than doing nothing*
(−1.1%). The mechanism is plain in the distance column: a tangent has a
validity radius, and at a mean neighbour distance of 3.16 unit-cube diameters
the linear extrapolation is far outside it and overshoots. The ranked arm
survives because it explicitly selects the candidate whose predicted start
error is smallest — i.e. it declines to extrapolate far.

Cold-start failures also explode, 8 → 75 of 200, and **the answers stop
agreeing**: at n ≥ 3 cold and warm converge to genuinely different roots (both
residuals ~1e-13; one case has shaft 2 at 166.7 vs 107.2 rev/min). With one
Stribeck fold per shaft, multi-rootedness appears combinatorially. The verifier
stops being a Phase 2 demo and becomes mandatory.

## Result 2 — it was never about parameter count

A uniform sweep over 88 parameters builds 400 machines nobody ever made. Real
archives are what §0b and phase-1d describe: **a handful of designs with many
operating points each.** Rebuilding the archive that way — 8 machine variants,
hardware drawn once per variant, 50 operating points each — while every Case
Card still records all 88 parameters:

| branches | params | eff. dim | nbr dist | warm | +1st order | +ranked |
|---|---|---|---|---|---|---|
| 2 | 36 | 6 | 0.440 | 26.1% | 37.6% | **44.6%** |
| 4 | 62 | 10 | 0.757 | 37.4% | 39.1% | **48.5%** |
| 6 | 88 | 14 | 1.018 | 40.1% | 38.9% | **40.8%** |

Same circuits, same solver, same arms, same parameter counts. The only change
is the archive's *structure*, and it moves the ranked arm from ~10% to ~45%.

> The percentage tracks archive density in the **effective** dimension — the
> parameters that actually vary between runs — not the width of the Case Card.

That is why the idea works in industry and it strengthens rather than replaces
phase-1d: recording 88 parameters costs nothing at retrieval time as long as
most of them are constant within a machine family.

## The honest comparison, and a caveat on it

Like-for-like (first-order + ranked, no second-order arm at these widths):

| circuit | params | ranked, vs nominal |
|---|---|---|
| base | 7 | **51.5%** |
| manifold, 4 branches | 62 | 48.5% |
| manifold, 6 branches | 88 | 40.8% |

**It degrades gently rather than growing.** 62 parameters and 22 unknowns still
returns 48.5%, which is the useful claim: the method survives realistic
complexity. It does not get *better* with it.

**And the n = 6 row must not be quoted without its caveat.** At six branches the
nominal baseline costs 9.71 iterations against cold's 9.67 — `nominal_start`
assumes lossless lines and half-pressure metering, and at six branches of varied
hardware that guess is no better than the flat start. A percentage measured
against a baseline that has stopped being competent is the very thing this
project corrects for elsewhere, so the 40.8% is **not** comparable to the base
circuit's 51.5%. Fixing it means writing a manifold-aware nominal guess; until
that exists, n = 2 and n = 4 are the rows that carry weight.

## What to say

- **The headline stays the base circuit's 57.2%.** Nothing here beats it, and
  three separate attempts to buy a bigger number with complexity all returned
  less.
- **The scaling result is a robustness claim, not a bigger number:** at 62
  parameters and 22 unknowns the method still returns ~48%.
- **The real scaling law is about the archive, not the model** — effective
  dimension, not parameter count. It is the sixth claim this project has tested
  and declined, after rescued failures (§6a), the prediction pre-filter (§6e),
  the failure-proximity rule (§6f), top-k retrieval (§6j) and the selection
  agent (§6k).
