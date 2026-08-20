# Phase 1b — The surrogate arm

**Built:** Thu 20 Aug 2026 · **Gate:** §3's *two sources, one verifier* measured rather than asserted → ✅
Reproduce with `python surrogate.py`, or as *Phase 1b* inside `python run_all.py`.

The last In-scope item in §4, and the one that makes the pitch's central hook a measurement. Phase 1 showed
that a *recalled* state is a good warm start. This shows what a *predicted* one is worth, because that is the
arrow §1 claims is missing from the PhysicsAI workflow: predict a field, then validate with a solver run that
starts from zero and discards the prediction.

## What was built, and what was deliberately not

A **quadratic response surface**: normalise the 7 setup parameters, expand to 36 polynomial features
(`[1, x_i, x_i·x_j]`), ridge least-squares onto 7 standardised outputs. 40 lines of numpy. Fits the 395-case
archive in ~1 ms and predicts in ~150 µs.

Three constraints shaped it, and each one is defensible out loud:

- **It must not be good.** §4's brief was *fast and slightly wrong*, because being slightly wrong is the whole
  demonstration — an approximate state is a bad final answer for precisely the reason it is a good starting
  guess. A well-tuned model would have obscured that.
- **It must not be a lookup in disguise.** A k-nearest-neighbour regressor is retrieval wearing a different
  hat, and comparing retrieval against itself proves nothing. A global fitted polynomial has genuinely
  different failure modes — it extrapolates, and §6e shows it doing exactly that.
- **It must not add a dependency.** No scikit-learn. The image ships four wheels and the Dockerfile makes a
  point of it.

**Separate file, separate results, on purpose.** `bench.py` owns the headline and `summary_hash` enumerates
its three arms by name, so a fourth arm there would move `830da3e6a4480676` and every document quoting it.
This follows the `fold.py` precedent instead: own experiment, own JSON. **The phase-1 hash is unchanged.**

`surrogate.py` re-solves the cold, nominal and warm arms itself and then cross-checks them case by case
against `results.json`, failing loudly on any disagreement. Two files reporting the same quantity is how two
different numbers for the same thing end up on two slides.

## Measured

200 fresh cases, `sample_cases(200, 99)` — byte-identical to the Phase 1 query set.

| arm | converged | total Newton iterations | mean |
|---|---|---|---|
| cold (flat start) | 196 / 200 | 1631 | 8.32 |
| nominal guess | 200 / 200 | 1420 | 7.10 |
| warm — retrieval | 200 / 200 | 979 | 4.89 |
| **predicted — surrogate** | **200 / 200** | **924** | **4.62** |
| verified — prediction, gated | 200 / 200 | 920 | 4.60 |

**The prediction is not an answer**, and this is the number that says so: against a solver tolerance of 1e-8,
the predicted state's residual has a **median of 8.26** and a worst case of **230**. **0 of 200 predictions
were solutions.** Answers agree with the cold solve to 2.9e-08 bar and 3.2e-08 rev/min on all 196 cases where
cold converged — a different starting guess must not move the answer, and it does not.

## Two concessions, both of which improve the talk

### 1. The prediction beats the archive — 5.6% fewer iterations than retrieval

Expected, and the reason is one sentence: **the surrogate sees all 395 archived cases for every query;
retrieval uses exactly one.** Four hundred times more information per query, so of course the fitted model is
the better guess.

It does not weaken the archive, for three measured reasons:

1. The surrogate **needs 395 solved cases to exist** before it can be fitted. Retrieval works from run number
   two — no training, no minimum dataset. §3's table claimed this; it can now be said with numbers beside it.
2. **The better guess is the one you cannot trust.** Retrieval hands the solver a real converged state of a
   real case. The surrogate hands it something that satisfies nothing.
3. It makes **the verifier the point, not the archive** — and it sharpens §1's hook rather than blunting it:
   the discarded PhysicsAI prediction is measurably the best available starting state.

### 2. Gating the *prediction* buys nothing on this circuit

A predicted state has no source case, so gate 1 (`check_transfer`) does not apply — there is no neighbour
whose regime can be compared. Gate 2 does apply, pointed at the prediction rather than at a converged answer,
and it asks a real question: *is this even a legal state to start from?*

It fires **15 times in 200**, every one of them `cavitation` — the polynomial extrapolating a pressure below
the model's validity floor. And then:

- using those 15 illegal states anyway costs **4 Newton iterations across the whole run** (110 → 106);
- **not one of the 15 failed to converge** from the illegal start.

**So the filter is measurably pointless here, and that is worth more than the filter.** The reason is Phase 2's
own finding rather than an excuse: the base circuit has a **unique root everywhere in its envelope**, verified
with a 16-seed multi-start over all 400 cases. Where there is one root, a bad start can only cost iterations —
it cannot change the answer, so a pre-filter has nothing to protect.

**Where it would matter is the fold circuit**, where the starting guess selects which of three roots Newton
finds and 4 naive transfers landed on an unstable one. **That experiment was run the same day — see below,
and the answer is not the flattering one.**

## The fold circuit — 20 Aug, same day

`python surrogate.py --fold`. The question §6e left open: on the base circuit, gating the *prediction* fires 15
times in 200 and is worth 4 Newton iterations — nothing. That circuit has a unique root everywhere, so a bad
start can only cost. The fold circuit is where a starting guess selects **which** of three roots Newton finds,
and the middle one is dynamically unstable.

Same archive seed (11) and same 200 queries (seed 77) as `fold.py`, so the two experiments sit beside each
other rather than merely near each other. Archive: 135/300 kept, 1 rejected as dynamically unstable.

| same circuit, same queries | from **retrieval** | from **prediction** |
|---|---|---|
| naive — valid operating point | 147 | 158 |
| **naive — unstable root, silently wrong** | **4** | **40** |
| naive — no answer at all | 49 | 2 |
| verified — valid operating point | **200** | **200** |
| verified — silently wrong | **0** | **0** |
| verified — total Newton iterations | 1579 | **1300** |

The predicted state is a worse *state* here than on the base circuit — median residual 15.3 against a solver
tolerance of 1e-8 — and 64 of 200 predictions are not legal states at all, all of them `unstable` rather than
the base circuit's `cavitation`: the polynomial lands on the friction downslope, which is exactly the fold it
cannot see.

### The finding

**The prediction is the better starting guess and, unverified, ten times more dangerous.** 200 valid answers
for 18% less solver work than retrieval — and 40 silently wrong answers against retrieval's 4, on the same
cases.

**The mechanism is worse than the count.** Naive retrieval fails to converge 49 times; that is a loud failure
and a human goes and looks. The prediction converges 198 times out of 200 and 40 of those land on an operating
point no machine can occupy, at a residual of 1e-8. **The surrogate converts loud failures into silent
wrongness** — which is the failure mode this whole project exists to name.

That is the argument for Layer 3 made against the project's own best-performing component, which is the
strongest place to make it.

### The third arm, which exists to prevent an easy false claim

`post_only` — no pre-filter on the prediction, only the gate on the answer plus escalation — also reaches
**200 valid, 0 wrong**, at 1559 iterations against the guarded policy's 1300.

**So the pre-filter is a cost mechanism, not a safety mechanism.** On both circuits and for both sources,
safety comes from gate 2 applied to the *answer*. Checking the prediction before spending a solve on it is
worth nothing on the base circuit and **17% of solver work** on the fold circuit, where it avoids converging
onto a root that is about to be rejected.

The `post_only` arm is in `surrogate.py` for exactly this reason: without it, "we check the prediction before
using it, which is what keeps you safe" is an easy sentence to say and a false one.

## Rejected

- **scikit-learn / XGBoost / an MLP.** More accuracy was the wrong axis. The brief was a stand-in that is fast
  and wrong, and a dependency that triples the image for a 40-line fit is a bad trade on a slide about
  architecture.
- **A fourth arm inside `bench.py`.** Would have moved the phase-1 summary hash for a result that is not the
  headline. The `fold.py` pattern exists for exactly this.
- **Calling it PhysicsAI.** It is a 36-feature polynomial standing in for one, so the comparison fits on a
  laptop. The audience built the real thing; say which one is on screen.
- **Claiming the prediction pre-filter is a safety mechanism.** It is not, and the `post_only` arm was written
  to make that impossible to claim by accident: without a pre-filter the guarded policy still returns 200 valid
  answers and 0 wrong ones. The pre-filter buys 17% of solver work on the fold circuit and nothing on the base
  circuit. Safety is gate 2 on the answer, in every configuration measured.
