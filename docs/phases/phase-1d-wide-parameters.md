# Phase 1d — 25 real parameters, and a latent bug in the hardware rule

**Built:** Thu 20 Aug 2026 · **Gate:** the circuit carries a realistic parameter count, and the `hardware`
rule is measured for the first time → ✅
`python -m benchmarks.selftest` · `python -m benchmarks.wide_sweep` · both inside `python run_all.py`.

§6g answered *"real models have hundreds of parameters"* by widening the **index** with entries that are inert
in the equations. This is the other half: extra parameters that are **real**, drive the physics, and describe
**different hardware**.

## What was promoted

`model.HARDWARE` turns 18 module constants into per-case parameters — discharge coefficient, pump leakage,
relief band, and *per branch* motor displacement, return restriction, cross-port leakage, Coulomb and
breakaway torque, Stribeck velocity, viscous drag. With the 7 swept parameters that is **25 physical
parameters**, and shafts a and b are no longer forced to be the same motor.

**Default-preserving, and that is the whole safety argument.** A case stating none of them solves
bit-identically to before. Two independent detectors say so: `benchmarks/selftest.py` measures the worst state difference
between implicit and explicit defaults at **0.00e+00**, and the phase-1 summary hash is still
**830da3e6a4480676** after the refactor.

## benchmarks/selftest.py — built before the change, not after

The refactor threads per-branch constants through `residual` and a hand-derived analytic `jacobian`. The
error it invites is a transcription slip — shaft a's breakaway torque in shaft b's row — which no symmetric
test can see and which would not crash. It would quietly change iteration counts, which is the quantity this
project reports.

So the detector came first: the analytic Jacobian against central differences, on random states sampled away
from the regularisation kinks, **and on cases where the two branches are built differently**. Worst relative
error **1.5e-08** on both. `run_all.py` now runs it before regenerating anything and stops if it fails.

## benchmarks/wide_sweep.py — and the realistic archive is not 400 unique machines

It is a handful of designs with many operating cases each, which is the loop §0b describes: concept,
prototyping with ~25 vehicles, series. So the sweep splits the parameters by what they mean —
**hardware defines the machine** (a few discrete variants), **operating parameters define the run**
(continuous, many per variant).

| arm | mean Newton iterations |
|---|---|
| cold | 8.61 (10 failures) |
| nominal | 7.08 |
| **warm, retrieval over all 25** | **5.21** |
| warm, gate enforced | 5.24 |

**26% fewer iterations than the nominal guess**, against 31% on the 7-parameter circuit. The result holds when
the parameters are real.

## The finding: recording hardware makes the index separate machines by itself

**0 of 200** nearest neighbours came from a different machine. The 18 hardware dimensions dominate the
distance, so retrieval groups by design without being told to. The `hardware` rule — unreachable on the
7-parameter circuit, where every case was the same machine, and therefore never measured until now — has
nothing to catch.

That is a **Layer 1 argument, not a Layer 3 one**: what keeps a state from crossing machines is the Case Card
recording the hardware in the first place.

## The bug that found, and the fix

The null result was suspicious, because within a variant every unit had **bit-identical** hardware. Real units
do not. Adding per-case manufacturing scatter broke the rule immediately:

| per-unit scatter | exact match | per-constant 5% band | **aggregate 5% band** |
|---|---|---|---|
| 0% | 197 admitted | 197 | **197** |
| 2% | **0 admitted — 200/200 refused** | 50 admitted | **198** |
| 5% | 0 | 0 | 17 |

**An exact-match hardware rule refuses every transfer, including every same-machine one, the moment two units
of one design are not bit-identical.** That is a gate nobody would leave switched on, and it was sitting in
the verifier unmeasured because no experiment had ever varied hardware.

**A per-constant band does not fix it either**, and the reason generalises: with 18 constants each carrying
independent scatter, *"refuse if any one is out of band"* is a multiple-comparisons problem. At 2% scatter it
refused 150 of 200 same-machine transfers — close to the 76% that arithmetic predicts. **A per-parameter
threshold degrades as the parameter count grows**, which is the same failure mode `benchmarks/dimensionality.py` finds in
the coverage rule, caught here before it shipped.

**The fix is to compare the norm rather than the worst draw.** `HARDWARE_REL_TOL = 0.05` is now applied to the
RMS relative difference across the hardware vector, which averages scatter instead of taking its maximum and
therefore stops degrading with dimension.

**And it has a stated limit rather than a tuned one.** At 5% scatter against a 5% band the rule refuses again —
correctly. Two units differ by roughly √2 × the per-unit scatter, so **the band must exceed the fleet's actual
scatter**, and the table above is where that is measured rather than asserted.

## Rejected

- **Widening the band until the failures stopped.** It would have admitted genuinely different designs, and
  the aggregate form fixes the real defect instead of hiding it.
- **Promoting the constants into `PARAM_BOUNDS` and the main sweep.** That would move `results.json` and the
  frozen hash for a result that is not the headline. `benchmarks/wide_sweep.py` is a separate experiment, like `benchmarks/fold.py`
  and `benchmarks/surrogate.py`.
- **Sweeping hardware per case in the wide sweep.** Every case would then be a unique machine, no transfer
  would ever be legitimate, and the experiment would measure the sampler rather than the gate. The
  variant-plus-tolerance structure is what makes it mean anything.
- **Reporting the first run's gate verdicts.** They showed 74 coverage refusals and were pure unit mismatch —
  a 25-dimensional distance against a 7-dimensional radius, the same trap documented in phase 1c. The coverage
  radius is now re-derived in the space retrieval indexes, and the corrected figure is 2.
