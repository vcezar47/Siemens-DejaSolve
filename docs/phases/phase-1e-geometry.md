# Phase 1e — what if the model *did* have geometry?

**Built:** Tue 25 Aug 2026 · **Status:** works, measured, **not adopted** ·
[`../geometry.py`](../../experiments/geometry.py) · `python -m experiments.geometry --retrieval`

Not in `run_all.py` and not imported by `dejasolve/model.py`, `benchmarks/bench.py` or anything that
produces a shipped number. The frozen Phase 1 hash does not know this file
exists.

## The disclaimer this started from

The machine view carries a line that is honest and is a real limitation:

> The layout is illustrative — the model is lumped and has no geometry.

Pipe colour is the solved pressure **at a node**. Between two nodes the drawing
invents a route the solver knows nothing about. Draw the same circuit with the
pipes twice as long and every number stays identical. The question was what it
would take for that sentence to be false — and the answer had to be *make
length and bore drive the answer*, because drawing better would leave it just
as illustrative, only prettier.

## What was built

Five pipe runs, each with a length and a bore, each dropping pressure through
Darcy–Weisbach:

```
pump ─[L0,D0]─ p1 ─┬──────────── relief ──> tank
                   ├─[La,Da]─ p1a ─ valve_a ─ p2a ─ MOTOR a ─ p3a ─[Ra,Dra]─ p4a ─ ret ─> tank
                   └─[Lb,Db]─ p1b ─ valve_b ─ p2b ─ MOTOR b ─ p3b ─[Rb,Drb]─ p4b ─ ret ─> tank
```

**7 unknowns → 12. 7 parameters → 18** (the 7 swept, fluid viscosity, and 10
geometric). Viscosity is new because it has to be: an orifice is
inertia-dominated and carries only density, so the fluid gains a second
property the moment the model gains length.

**The line element is a genuinely different nonlinearity, and it is exercised.**
An orifice is `Q ~ sqrt(dp)` everywhere. A line is *linear* in `dp` while
laminar and reverts to `dp^(4/7)` once turbulent, so the same element changes
character across the envelope. Both branches are inverted analytically and
composed as resistances in series — smooth, no regime switch, no `if`. Across
1485 solved line-instances: **13.9% turbulent, 32% at or past transition**, so
the second branch is not dead code.

## The bug the invariant caught, and the real flaw underneath it

The 12×12 Jacobian is hand-derived across five shared pipe elements, so it got
the same treatment `benchmarks/selftest.py` gives the base circuit — central differences,
before any number was quoted. It failed: **11% relative error at `J[0,1]`**.

The derivative was right; the *test* sampled `p0 == p1`, putting the supply
line at exactly `dp = 0`, and the finite-difference step straddled a
regularisation set 4 orders of magnitude smaller. That is precisely the trap
`benchmarks/selftest.py`'s own docstring warns about.

But it exposed a real modelling flaw rather than only a test bug. The turbulent
branch carries `s^(4/7)`, whose **second** derivative diverges at the origin,
and `DP_REG_LINE` was small enough that the slope fell ~13% between `dp = 0` and
`dp = 1e-3` bar. That is a kink in all but name, and Newton's local model is
quadratic. `DP_REG_LINE` is now `model.P_REG`, for exactly the reason that
constant exists. Both fixed, and the check passes at **9.3e-08**.

## Results

| arm | mean iterations | failures |
|---|---|---|
| cold | 8.36 | 1 / 200 |
| nominal | 7.26 | 0 |
| warm — retrieval | **6.22** | 0 |

**14.3% fewer iterations than the nominal guess**, against 31% on the lumped
7-parameter circuit. Cold and warm agree to 4.6e-08 bar.

### The retrieval question this was actually built for

Geometry is *both* things the project already measured: 10 more real parameters
(phase-1c said a distance metric degrades as the card widens) and the thing
that makes two otherwise-identical manifolds different machines (phase-1d).
So — with the floor and the bound phase-1c insists on:

| arm | total iterations | vs nominal | picked the oracle's case |
|---|---|---|---|
| nominal | 1453 | — | |
| **random archived state** | 1494 | **−2.8%** | |
| 7 lumped parameters only | 1338 | 7.9% | 26 / 200 |
| 11 geometry + fluid only | 1316 | 9.4% | 22 / 200 |
| **all 18 parameters** | **1245** | **14.3%** | **48 / 200** |
| oracle — cheapest of all 297 | 869 | 40.2% | |

Three things, and the first two are the interesting ones:

1. **A random archived state is now *worse* than the nominal guess (−2.8%).**
   On the base circuit phase-1c found the opposite — every archived state was a
   plausible operating point, so even a random one beat a formula, and the
   index had stopped contributing. Here that is no longer true: the archive
   alone buys nothing and **the index is doing all of the work.**
2. **Geometry has to be on the Case Card.** Retrieving on the 7 lumped
   parameters gets 7.9%; the full card gets 14.3% and finds the best available
   candidate nearly twice as often. Ignoring the plumbing costs almost half the
   benefit.
3. **The headroom is large and unclaimed.** The oracle is at 40.2% against the
   metric's 14.3%. That is a far bigger gap than the base circuit's 11.8%, and
   it is where the first-order transfer (§ phase-1 *A fourth arm*) would be
   worth trying next — the sensitivity would need `∂F/∂p` extended across the
   18 parameters, including the line coefficients' dependence on `L`, `D` and
   `mu`.

*An earlier draft of that table had an "oracle" ranked by Euclidean distance on
the solution vector. That vector mixes bar with rev/min, so shaft speed
dominated the norm and the "bound" came out **worse** than the parameter
metric — which is how it announced itself as not a bound. Redefined by cost,
the way `benchmarks/agent_select.py` defines it.*

## Why it is not adopted, and what the disclaimer should say instead

**The physics is real but small.** Against the same case solved on the lumped
circuit: median manifold pressure shift **0.69%** (p95 6.1%), median shaft
speed shift **0.32%** — 2.8 rev/min, max 50. Doubling *every* pipe run in the
circuit moves the manifold 135.2 → 137.0 bar. Line losses are ~1 bar on a
200 bar system, which is exactly what a hydraulic engineer would tell you
before any of this was built.

So the trade is: **a <1% correction to the answer, paid for with a
12-unknown system, an 18-dimensional Case Card, mean neighbour distance
0.357 → 1.041, and 31% → 14.3% on the headline.** That is a bad trade for this
deck, and it is a good example of the thing the project keeps finding — the
expensive layer is rarely the one that pays.

**And it would only make half the disclaimer false.** Only `L` and `D` enter
the equations. Two runs of equal length routed completely differently are
*identical* to this model, so the 3D routing in the view stays illustrative
even with all of this in. An honest revised caption would be:

> Pipe length and bore are simulated; the 3D routing is not.

Making routing itself matter needs bend losses — a K-factor per elbow, so the
number of turns in a run changes its resistance. That is the natural next step
and it is the point at which the drawn path would finally be the simulated
path.

## What is worth keeping from it

- The line element and its analytic derivative are correct and verified, so
  this is a working base if geometry is ever wanted for real.
- The `--retrieval` experiment is the strongest evidence in the project that
  **the index earns its place** — it is the one circuit where random retrieval
  loses to a formula, so the 14.3% is unambiguously the metric's doing.
- The `DP_REG_LINE` finding generalises: any element blended across two power
  laws needs its regularisation set on the scale of the *curvature*, not the
  value.
