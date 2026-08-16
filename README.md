# Déjà Solve

Warm-start a solver's initialisation from the physically-nearest case it has
already solved, instead of starting from zero every time.

Siemens Summer School 2026 · domain: *Digital Twins & Platforms*

- [DEJA_SOLVE_PLAN.md](DEJA_SOLVE_PLAN.md) — the plan, the pitch and the presentation notes
- [phases/](phases/) — what was actually built in each phase, and what was rejected

## Reproduce every number

```bash
python run_all.py
```

Writes `archive/cases.jsonl`, `results.json` and `figs/convergence.png`.
Runs in a few seconds. No number in the deck is typed by hand — if it is not in
`results.json`, it does not go on a slide.

Requires Python 3.11+, numpy and matplotlib (`pip install -r requirements.txt`).

## What is here — Phase 1

| file | what it does |
|---|---|
| `model.py` | The physics: a hydraulic manifold driving two motors against Stribeck friction. 7 nonlinear equations, analytic Jacobian, damped Newton |
| `sweep.py` | Runs a 400-case parameter sweep and keeps what converged — this is the archive |
| `bench.py` | On 200 *fresh* cases: solve cold, retrieve the nearest archived case, solve warm. Writes `results.json` |
| `plot_convergence.py` | Draws the comparison figure from `results.json` |
| `run_all.py` | All three, in order |

## The model

```
pump ──┬───────────────────────────── relief valve ──> tank
       │
      [p1]  manifold
       ├─ valve_a ─[p2a]─ MOTOR a ─[p3a]─ return ─> tank
       └─ valve_b ─[p2b]─ MOTOR b ─[p3b]─ return ─> tank
```

Unknowns are `[p1, p2a, p3a, w_a, p2b, p3b, w_b]` — five pressures and two
shaft speeds. Steady state is a 7×7 nonlinear system: flow balance at each
node, torque balance at each shaft. That is the *initialisation problem*, and
warm-starting it does not change the physics of the case — only the guess
handed to Newton.

It is hard for two ordinary reasons: turbulent orifice flow whose slope blows
up as Δp → 0, and Stribeck friction, whose decaying branch has negative slope
and narrows the basin of attraction around the operating point.

Swept per case: pump delivery, both valve areas, both load coefficients, relief
cracking pressure, fluid density.

## Result

400-case archive, 200 fresh query cases, 1-nearest-neighbour retrieval on the
normalised setup vector. Same residual, same Jacobian, same tolerance — the
only thing that differs is the starting guess.

| | cold start | warm start |
|---|---|---|
| mean Newton iterations | 8.3 | 4.9 |
| total iterations | 1631 | 953 |
| runs that never converged | 4 / 200 | 0 / 200 |

**42% fewer iterations**, every cold-start failure rescued, and the answers
agree to 4e-08 bar and 3e-08 rev/min across all 196 cases where both converged.

### One caveat worth stating out loud

The failure count depends on how good the solver's Jacobian is, so `bench.py`
reports that sensitivity instead of choosing a flattering setting:

| solver Jacobian | cold failures | warm failures |
|---|---|---|
| exact analytic | 4 / 200 | 0 / 200 |
| finite difference, `sqrt(eps)` step | 2 / 200 | 0 / 200 |
| finite difference, coarse step | 45 / 200 | 0 / 200 |

The headline uses the **analytic** Jacobian on purpose: it is the best case for
the cold baseline, so the advantage measured against it is real. The iteration
saving is stable at ~42% in all three.

## Not done yet

Phase 2 is the verifier — the layer that refuses a warm start when the
retrieved case is in a different physical regime. `model.regime()` already
tags each archived case (relief valve open/closed, and which branch of the
friction curve each shaft settled on), which is what the rules will gate on.
