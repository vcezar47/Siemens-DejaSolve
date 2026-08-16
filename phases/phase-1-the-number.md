# Phase 1 — THE NUMBER

**Planned:** Sun 16 – Tue 18 Aug 2026 · **Gate met:** Sun 16 Aug, two days early
**Gate:** the convergence-comparison plot exists — cold vs warm, same final
residual → ✅ [`../figs/convergence.png`](../figs/convergence.png)

After this phase the project cannot fail: there is a measured result and one
command that regenerates it.

## What was built

| file | role |
|---|---|
| [`../model.py`](../model.py) | The physics and the damped-Newton initialisation solve |
| [`../sweep.py`](../sweep.py) | 400-case Latin-hypercube sweep → the archive |
| [`../bench.py`](../bench.py) | Cold vs retrieval-warm on 200 fresh cases → `results.json` |
| [`../plot_convergence.py`](../plot_convergence.py) | The gate figure, drawn from `results.json` only |
| [`../run_all.py`](../run_all.py) | All of the above, in order |

```bash
python run_all.py
```

Runs in a few seconds and is deterministic — two clean runs produce an
identical summary hash. Timings vary; nothing else does.

## The model, and why it is this model

A hydraulic manifold driving two motors:

```
pump ──┬───────────────────────────── relief valve ──> tank
       │
      [p1]  manifold
       ├─ valve_a ─[p2a]─ MOTOR a ─[p3a]─ return ─> tank
       └─ valve_b ─[p2b]─ MOTOR b ─[p3b]─ return ─> tank
```

Unknowns `[p1, p2a, p3a, w_a, p2b, p3b, w_b]` — five pressures, two shaft
speeds. Steady state is a 7×7 nonlinear system: flow balance at each node,
torque balance at each shaft. Seven parameters are swept: pump delivery, both
valve areas, both load coefficients, relief cracking pressure, fluid density.

### Two models were built and rejected first

This is the most important engineering note in the phase.

**Rejected 1 — a plain resistive hydraulic network (5 unknowns, no shafts).** It is
*globally convergent*. A damped Newton with an analytic Jacobian solves it from
anywhere in 7–8 iterations with **zero failures**, and no element tweak changes
that: monotone dissipative networks are well-behaved by construction. Tried
smaller orifice regularisation (`P_REG` down to 1e-7) and check valves on every
branch — both made no measurable difference.

**Rejected 2 — the same network plus motors with ordinary Coulomb friction.**
Still 0 failures out of 300; on the warm-start comparison, cold mean 7.7 vs
warm mean 4.9. Better, but with nothing ever failing there was no trust story
to tell, only a modest iteration saving.

**Accepted — motors loaded through Stribeck friction.** Breakaway torque decays
to Coulomb torque as the shaft picks up speed, so the friction curve has a
**negative-slope branch**, the torque balance can have three roots, and the
basin of attraction around the operating point is narrow. This is ordinary
mechatronics, not a contrivance, and it is what makes a cold guess expensive.

The rule followed throughout: **make the problem harder through physics, never
by weakening the solver.** A cold baseline that was hobbled would be spotted
immediately by this audience, and it would be the only thing anyone remembered.

## Benchmark protocol

1. Sweep 400 cases from the cold guess (every node at tank pressure, both
   shafts at rest). 395 converge and become the archive; 5 fail and are dropped,
   because an archive holds successful runs.
2. Draw **200 fresh cases** from a different seed — never solved before, not in
   the archive.
3. For each: solve cold; find the nearest archive case by Euclidean distance on
   the min-max normalised 7-parameter setup vector; solve again warm-started
   from that neighbour's converged state.
4. Compare answers, iteration counts, failures.

Same residual, same Jacobian, same tolerance (1e-8), same solver. **The only
difference is `x0`.** Anything else would make the comparison meaningless.

## Results

| | cold start | warm start |
|---|---|---|
| mean Newton iterations | 8.32 | **4.86** |
| median iterations | 8 | **4** |
| total iterations (196 cases) | 1631 | **953** |
| runs that never converged | 4 / 200 | **0 / 200** |
| total wall time | 160 ms | 81 ms |

- **41.6% fewer Newton iterations**
- **4 cold-start failures rescued, 0 runs broken**
- **Answers agree to 3.60e-08 bar and 3.16e-08 rev/min** across all 196 cases
  where both converged — **0 disagreements**

That last line is the one that matters most in front of this audience: it is the
evidence that warm-starting changed the cost and not the answer. Every cold
failure was `line_search_stall` — the step direction stops producing a decrease,
which is what the Stribeck barrier does to a guess outside the basin.

**Retrieval is not doing anything clever.** Mean neighbour distance is 0.357 in
a 7-D unit cube (max 0.60), so neighbours are not especially close — and the
result holds anyway. Plain 1-NN was chosen deliberately: Phase 1 had to show the
idea pays off before Phase 2 spends effort on a better index.

### Exemplars picked automatically by `bench.py`

- **`query-0055`** (Panel A): cold 11 iterations, warm 4. The cold run spends 8
  iterations crawling across a plateau before it can converge at all.
- **`query-0021`**: cold stalls after 8 iterations and never converges; warm
  converges in 7 from neighbour `sweep-0170` at distance 0.354.

## The trap that was avoided

An intermediate version of this benchmark reported a **22% cold-start failure
rate**. It was wrong — an artifact of the prototype's finite-difference step
size, not of the physics. With the textbook `sqrt(eps)` step the same cases fail
2/200.

Had that gone on a slide, the first engineer to ask *"what step size?"* would
have taken the whole talk down. It is now a reported result instead of a hidden
assumption — `bench.py` runs the sensitivity every time:

| solver Jacobian | cold failures | warm failures | iteration saving |
|---|---|---|---|
| exact analytic | 4 / 200 | 0 / 200 | 42% |
| finite difference, `sqrt(eps)` step | 2 / 200 | 0 / 200 | 42% |
| finite difference, coarse step | **45 / 200** | 0 / 200 | 42% |

**The headline uses the analytic Jacobian on purpose — it is the best case for
the cold baseline**, so the advantage measured against it is real. The iteration
saving is stable at ~42% in all three. State openly that the dramatic
*failure-rate* story appears only when the solver's derivatives are poor, which
is what happens when components come from a user-extensible library that does
not supply them.

## Deliberately not done

- No verifier — a warm start is currently accepted unconditionally. That is
  Phase 2, and it is the reason Act 3 of the demo exists.
- No surrogate model. The Act 2 table still has a placeholder row for it.
- No index service, no Docker, no UI, no LLM ingest. None produce a number.
- Retrieval ignores the operating regime entirely, which is exactly the hole
  Phase 2 fills.

## What Phase 2 inherits

`model.regime()` already tags every archived case with the information the
verifier will gate on:

- `relief_open` / `relief_fraction` / `relief_flow_share` — the relief valve is
  open in **31%** of the archive, so the archive genuinely spans two hydraulic
  regimes;
- `shaft_a` / `shaft_b` ∈ `stuck` | `stribeck` | `viscous` — which branch of the
  friction curve each shaft settled on.

The Stribeck fold is also the physical mechanism for Act 3: near a fold, two
valid steady states exist, and which one Newton lands on depends on where it
started. That is how to build a case that converges beautifully to a *wrong*
answer — from real physics rather than a contrived example.

**Caution for Phase 2:** across all 196 compared cases in this benchmark, cold
and warm never disagreed. The wrong-answer case has to be constructed
deliberately near a fold; it does not fall out of the current sweep. If it turns
out to be hard to construct, say so honestly on the limits slide rather than
faking it.
