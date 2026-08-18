# Phase 2 — The verifier

**Planned:** Wed 19 – Thu 20 Aug 2026 · **Gate met:** Mon 17 Aug, ahead of schedule
**Gate:** a case that converges fast to a *wrong* answer, and is refused → ✅
[`../figs/verifier.png`](../figs/verifier.png)

## The finding that shaped the whole phase

Before building any rules, the obvious question had to be answered: **can a
warm start on this model actually produce a wrong answer?**

A 16-seed multi-start over all 400 base-circuit sweep cases found **exactly one
root every time**. The Phase 1 circuit has a unique steady state throughout its
envelope. So on that circuit a warm start can change what a run *costs* and
never what it *says* — which is exactly what Phase 1 measured independently
(0 disagreements in 196 cases), now explained rather than just observed.

**This is worth saying out loud in the talk.** It is a good property of the base
demo and it is evidence the benchmark was not hiding anything. It also means
the base circuit *cannot* demonstrate the failure mode the verifier exists for,
and manufacturing one there would have been dishonest.

### Why the fold was missing, and how it was found

Four probes failed before the analysis worked:

| attempt | result |
|---|---|
| Multi-start over the base sweep | 0 multi-root cases / 400 |
| Sweeping breakaway torque 6–40 Nm | 0 / 150 |
| Near-closed metering valves (0.12–12 mm²) | 0 / 400 |
| **Analysis instead of search** | found the condition |

At rest the motors pass only leakage, so the pump deadheads against the relief
valve and the manifold sits at roughly the cracking pressure. Available torque
at rest is therefore `p_crack × K_TORQUE ≈ 60–130 Nm` — always far above the
14 Nm breakaway. Every shaft blows straight through the Stribeck dip to the
quadratic branch. **The fold exists in the equations but the sweep never visits
it.**

Multiplicity needs the available torque to land *between* Coulomb and breakaway
torque, which means less torque per bar, which means a smaller motor. Scanning
displacement confirmed it:

| motor | torque at 150 bar | multi-root cases | with an unstable root |
|---|---|---|---|
| 32 cm³/rev (base) | 76.4 Nm | 0 / 150 | 0 |
| 12 cm³/rev | 28.6 Nm | 0 / 150 | 0 |
| 8 cm³/rev | 19.1 Nm | 0 / 150 | 0 |
| **5 cm³/rev** | **11.9 Nm** | **44 / 150** | **36** |
| 3 cm³/rev | 7.2 Nm | 150 / 150 | 146 |

**Decision:** keep the base circuit and every Phase 1 number untouched, and add
the 5 cm³/rev circuit as a documented variant. `D_mot` became an optional
per-case parameter defaulting to 32, so the base sweep is byte-identical and
every Phase 1 number still reproduces exactly.

That claim is checkable: `run_all.py` prints a **Phase 1 summary hash**, now
`2bdd767bfe02fd5d`, over the quotable part of `results.json` — the recipe is
`bench.summary_hash()`, which skips timings, the timestamp and the archive path
because those move on every run and every OS. An earlier digest quoted here was
computed by a throwaway command and could not be re-run, which made it a claim
rather than a check; the numbers behind it (8.32 → 4.86 iterations, 1631 → 953,
4 → 0 failures, agreement 3.6e-08 bar) are unchanged and verified.

## What "wrong" means here, precisely

The steady state is the equilibrium of a dynamic system: oil compressibility
gives each node a pressure state, each shaft has inertia. Writing that as
`dx/dt = S·F(x)` and taking the eigenvalues of `S·J` at a converged root asks
whether the root is an **operating point** at all.

A root on the Stribeck downslope has `d(load torque)/dw < 0` — positive
feedback on the shaft. It satisfies the equations to 1e-8 and is dynamically
unstable. **No machine can sit there.** Newton cannot tell. The eigenvalues can.

That is the concrete form "silently wrong" takes in this model, and it is not a
contrivance: it is the standard reason stick-slip systems are hard to
initialise.

## The rules ([`../verifier.py`](../verifier.py))

Two gates at two moments. Every refusal carries one line of plain English,
because a gate an engineer cannot argue with is a gate they will switch off.

**Before the solve** — no solve permitted, closed-form bounds only:

| rule | refuses when |
|---|---|
| `hardware` | source case is a different circuit (different motor) — a category error, not a judgement call |
| `envelope` | a parameter is outside the archive's range |
| `coverage` | nearest case is further away than the archive's own case spacing — extrapolation |
| `breakaway` | query cannot break away but the source has the shaft turning, or vice versa |
| `relief` | the relief valve must be open here but is shut in the source case |

**After the solve:**

| rule | refuses when |
|---|---|
| `cavitation` | converged below vapour pressure — outside the model's validity |
| `unstable` | converged onto a dynamically unstable root |

### Two design decisions worth defending

**The gate is physics, not distance.** Phase 1 measured the correlation between
setup distance and what a transfer costs: **r = 0.18**. Parameter similarity is
a weak proxy for physical transferability, so a distance threshold would be a
tuned knob pretending to be a rule. Distance survives only as an envelope
guard, and its threshold is not tuned either — it is the archive's own 99th
percentile nearest-neighbour spacing (0.53 for the base archive). Beyond that
the archive has no evidence to offer.

**The estimators were validated before being trusted.** Both cheap regime
estimates were checked against solved ground truth on all 395 base archive
cases: the breakaway estimate agrees **395/395 (100%)**, and `relief_must_open`
never contradicts the truth **395/395**. A gate built on a wrong estimate is
worse than no gate.

## Results — 200 fresh fold-circuit cases

Archive: 300 fold-circuit sweep cases → **135 kept**, 1 rejected as dynamically
unstable, 164 never converged cold. The verifier runs at ingest too: a
converged-but-unstable run is never allowed into the archive, because that is
what turns an archive from an asset into a liability.

| | naive retrieval | verified |
|---|---|---|
| converged to a valid operating point | 147 | **200** |
| converged to an **unstable root** (silently wrong) | **4** | **0** |
| no answer | 49 | **0** |
| total Newton iterations | 1571 | **1579** |

**Transfers refused by the pre-solve gate: 69 of 200.** The price of never being
silently wrong: **+1% solver work** — see *The fallback rung* below; it was +36%
until the ladder stopped falling back to a flat start.

### The demo case — `foldq-0009`

Naive retrieval converges in **8 iterations** — fast, clean, residual 1e-8 — to
shaft b at **35.6 rev/min**, sitting on the friction downslope. It looks like a
perfectly good answer. It is an unstable root the machine cannot occupy.

```
ADMIT  [ok] same regime, 0.48 away in setup space
warm:  REFUSE [unstable] converged onto a dynamically unstable root
       (shaft b sits on the friction downslope); the equations are
       satisfied but no machine runs here
nominal: ADMIT  [ok] stable operating point
```

Resolved from the nominal guess to shaft b at **462.5 rev/min**.

Panel A of the figure is the explanation: the circuit's supply curve is nearly
flat and crosses the Stribeck load curve **three times**. Naive warm start lands
exactly on the middle crossing.

## Honest caveats — say these before anyone asks

1. **The pre-solve gate did not catch the demo case.** It admitted the transfer
   ("same regime, 0.48 away"); the *post-solve* stability check caught it. The
   cheap gate cannot see everything, and the backstop is the part that makes the
   guarantee. Do not claim the rules predict every bad transfer.
2. **The comparison is not like-for-like on effort, and that is the point.** The
   verified policy escalates — warm, then the nominal guess, then multi-start —
   *because it can tell when it has failed*. The naive policy gets one shot
   because it has no idea anything went wrong. The +1% is the honest price, and
   it is that low only because the fallback rung is a competent guess.
3. **Admissible does not mean unique — and the fallback swap proved it.** These
   cases are genuinely bistable: for `foldq-0009` both 5.5 and ~460 rev/min are
   stable operating points, and the demo case now resolves to the *other* one
   than it used to. Across the run, **12 of 200 cases land on a different valid
   root** depending only on the fallback rung. The verifier guarantees you land
   on *an* operating point, never on an impossible one. Choosing between stable
   branches needs history — a transient run — and is out of scope. This belongs
   on the limits slide.
4. **The wrong-answer demo lives on a variant circuit**, and the deck must say
   so plainly: *"I checked whether my own demo could produce a silently wrong
   answer. In the base envelope it cannot, and here is the evidence. Here is the
   hardware corner where it can, and here is the layer that catches it."*
5. **The fold circuit is hard for everyone.** 164/300 sweep cases never
   converged cold. That is a property of the circuit, not of retrieval.

## Files

| file | role |
|---|---|
| [`../verifier.py`](../verifier.py) | The rules, the cheap regime estimators, both gates |
| [`../fold.py`](../fold.py) | The fold-circuit variant, multi-start root finding, naive vs verified experiment, the figure |
| `../model.py` | Gained `motor_constants()`, `dynamic_scales()`, `stability()` |
| `../fold_results.json` | Every number above |

Regenerate everything, both phases, with `python run_all.py`.

## What Phase 3 inherits

The verifier already produces one-line human-readable reasons, which is exactly
what the UI and the LLM explanation layer need — the text does not have to be
generated, only presented. `Verdict` carries `rule`, `reason` and a `details`
dict with the estimates behind the decision.

## The fallback rung — changed 18 Aug

When the gate refuses a transfer, or the post-solve check rejects the warm
answer, the ladder has to restart the solve from somewhere. It used to restart
from `COLD_START` — the flat all-zeros vector. That rung was swapped for
`model.nominal_start`, the same archive-free guess Phase 1's third arm uses.

Nothing about the refusal changed: the archive is still refused, the gate rules
are untouched, and every safety counter is identical — 200/200 valid, 0 unstable
roots, 0 unresolved, 69 refusals. What changed is the bill:

| | flat-start rung | nominal rung |
|---|---|---|
| total Newton iterations (verified) | 2130 | **1579** |
| price of never being silently wrong | +36% | **+1%** |

**The important part is what a cost table cannot show.** Both ladders are run
side by side in `fold.py` and their answers are diffed, because the fallback is
not a cost knob on this circuit — it selects which root Newton falls into.
**12 of 200 cases resolve to a different operating point** (max |dp| 33.2 bar,
max |dw| 789 rev/min), and the demo case `foldq-0009` is one of them: it used to
resolve to shaft b at 5.5 rev/min and now resolves to 462.5 rev/min. Both are
stable, both pass the eigenvalue check, neither is wrong.

This was already conceded qualitatively in caveat 3 before the change. It is now
a measured number in `fold_results.json`, which is the better version of the
same admission — and it is the reason the answer diff is instrumented
permanently rather than checked once. A change that leaves every summary counter
identical can still be moving the answers underneath them.
