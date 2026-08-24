# Phase 1e · Geometry — the archive seen, and the machine drawn

**Built 24 Aug 2026.** `viz.py`, `viz_results.json`, `GET /api/viz`, and two new
sections on the page: *The geometry* and *The machine*. One line added to
`model.solve` and nothing else in the solver.

Reproduce with `python run_all.py`; the view is at `python app.py`.

---

## Why this exists

Everything measured up to here was a table. The claim *"a retrieved state is a
good place to start"* was carried entirely by iteration counts, and the request
was for something that could be **seen** — including, explicitly, a piece of
engineering rather than a chart.

Two things had to be true for that to be worth building: it had to be driven by
solved numbers rather than drawn by hand, and it had to avoid claiming the one
thing §6h of the plan is careful never to claim.

---

## The measurement that decided the design

The obvious layout is to scatter the archive in *parameter* space, since that is
where retrieval happens. Measured, that is not defensible:

| space | variance in 3 axes | 3D vs true distance (Pearson r) |
|---|---|---|
| **parameter** (7 setup parameters, min-max normalised) | **49.5%** | **0.667** |
| **solution** (5 pressures + 2 speeds, z-scored) | **97.5%** | **0.9993** |

The sweep samples the seven parameters independently and uniformly, so the
inputs have no low-dimensional structure to find — the seven principal axes
carry 17.6% down to 10.7%, which is a ball. Drawing that and telling a room
"close on screen means close to the algorithm" would be false by a third.

Solution space is the opposite, and for a physical reason: the seven unknowns
are coupled by the circuit, so solved states lie on a thin sheet. Two axes carry
88.7% between them.

**That gap is the product's argument in one sentence:** the inputs are
irreducibly 7-dimensional, the answers are effectively 2-dimensional, and a warm
start works *because* a solved neighbour is already on the sheet while a cold
start begins off it. The picture is not decoration for the number — it is the
reason the number exists.

The three axes, read off the loadings:

| axis | variance | meaning |
|---|---|---|
| 1 | 45.4% | load split between the two motor branches |
| 2 | 43.3% | overall pressure and flow level (all seven moving together) |
| 3 | 8.8% | manifold pressure against everything downstream — the relief valve |

The cold start sits at the bottom of axis 2, which is exactly what "every
unknown at zero" means physically: no pressure anywhere.

---

## What was built

**`viz.py`** — projection, contact sheet, matched pair, and the three solver
runs with every Newton iterate kept. It fits the projection, measures distance
fidelity over all 77 815 archive pairs (no sampling, so no seed appears in a
number that reaches a slide), and picks the 20 contact-sheet cases by
farthest-point sampling so the sheet spans the cloud instead of one corner of
the sweep.

**`model.solve(..., record_path=True)`** — returns every iterate, not just the
residual at each one. Off by default and the key is *absent* when off, so the
benchmark's output is byte-identical with and without it. Verified: the phase-1
summary hash is `830da3e6a4480676` before and after the change.

**Three views on the page.** The archive as a cloud; the matched pair with the
link drawn between them; the race, stepping cold / nominal / warm through their
iterates to the same point. Plus a 20-tile contact sheet of circuit schematics.

**The machine** — the circuit in 3D: reservoir, pump, manifold block, relief
valve, two feed lines through their orifices, two motors, two returns. Query and
retrieved case side by side, sharing one rotation.

Hand-built primitives with per-segment depth sorting, gradient-shaded tubes,
projected elliptical end caps and a mild perspective divide. No CDN and no
dependency, for the same reason `lineChart` is hand-drawn: the demo has to run
in a room with no internet.

---

## What it does not claim — say this before anyone asks

- **The machine's layout is illustrative.** The model is lumped: seven unknowns,
  no geometry. Nothing here was meshed and no field was mapped. This does not
  weaken §6h, and it must not be presented as softening it.
- **What drives the picture is solved**, and that is the whole defence: pipe
  colour is the solved pressure at that node, the orifice bore is the valve's
  real flow area, the relief valve stands open only when the solved regime says
  it does, and each shaft turns at its own solved speed. The rotation is slowed
  by a fixed factor, the same for both motors, so the ratio between them stays a
  solved quantity.
- **Retrieval does not search the space the cloud is drawn in.** It searches the
  parameters. Every distance quoted on the page is therefore a true
  seven-parameter distance, never one measured on screen — and the rejected
  parameter-space projection is written into `viz_results.json` so the caveat
  has a measurement behind it rather than a disclaimer.

---

## The beat worth putting in the demo

Clicking any contact-sheet tile compares the query against *that* case instead
of the retrieved one. Picking `sweep-0373` by hand gives a state **96.8 bar**
away; the case retrieval chose is **7.0 bar** away — **13.9× closer**.

Letting the room pick badly, and showing what it costs, turns the comparison
from an illustration into a measurement they can check. It is also the honest
form of the "similar cases" claim: similarity is pairwise, so the demo narrates
two cases and lets twenty sit behind them as texture.

---

## Guard

`viz.py` re-solves the exemplar and **refuses to write the file** if either the
retrieved neighbour or any of the three iteration counts disagrees with
`results.json`. A picture that has drifted from the table it illustrates is
worse than no picture, so it fails loudly instead of drawing something plausible.

Current values: `query-0055` → `sweep-0380`, setup distance 0.3334, state gap
7.0 bar / 91 rev/min, and **11 → 7 → 4** iterations agreeing to 5.4e-13 bar.
