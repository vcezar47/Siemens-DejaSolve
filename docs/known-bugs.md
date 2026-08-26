# Known bugs

A bug sweep of the app as it stands (working tree at `3bf1694` + uncommitted
changes), covering `static/index.html`, `app.py`, `dejasolve.py`, `ingest.py`,
`casecard.py`, `model.py`, `verifier.py` and `archive_aurora.py`.

Each entry says what is wrong, where, how to reproduce it, and what the user
sees. Findings marked **verified** were reproduced by running the app; the rest
were established by reading the code path and are marked **by inspection**.

Severity is about the demo, not about CVSS: **critical** means it undermines a
claim the project makes on stage, **major** means visibly wrong output,
**minor** means cosmetic or dead code.

**Status:** every finding in this document is now **fixed** except **M5**
(withdrawn — not a bug, the endpoint it called dead has a live consumer) and
**M6** (won't-fix by decision: this is a desktop demo). One decision is
pending — see N2's
resolution note: `wide_sweep_results.json` was measured
against the breakaway gate before this fix and may no longer match it.

---

## Critical

### C1 — The Newton stepper fabricates the convergence path it claims to show

> **FIXED.** The stepper now reads the solver's own iterates for every arm and
> interpolates nothing. Resolution note at the end of this entry.

**Verified.** `static/index.html:1573` `getStepperTrajectory()`

When no artifact has been analysed yet (the state the page boots in, and the
state it returns to via "Show the shipped example"), `LIVE` is `null`, so the
"Newton Convergence & Fluid Dynamics Studio" falls through to a synthetic
branch. It invents a start state, then interpolates to the solved state with a
sine ease:

```js
const smoothU = Math.sin(u * Math.PI / 2);
stepState[k] = start[k] + ((sol[k]||0) - start[k]) * smoothU;
```

That is not Newton's method and it does not resemble it. Measured on the
shipped fixture, cold arm, manifold pressure `p1` per iterate:

| | iterates |
|---|---|
| what the stepper draws | 0, 19.2, 37.9, 55.9, 72.8, 88.2, 101.7, 113.3, 122.5, 129.2, 133.3, **134.63** |
| the real path (`VIZ.race.cold.path_state`) | 0, 107.9, **−20.6**, 87.9, 113.6, 125.4, 131.0, 133.6, 134.8, 134.6, 134.6, **134.63** |

Shaft speed `w_a` is the same story: the real solve overshoots to 1195 rev/min
and comes back down to 839; the drawn one rises monotonically to 839. The real
Newton path passes through a *negative* manifold pressure at iteration 2 —
which is the single most interesting thing about this problem and the reason
the admissibility gate exists — and the stepper smooths it away.

The aggravating detail: **the real iterates are already in the payload the page
loaded.** `viz_results.json` carries `race.{cold,nominal,warm}.path_state` in
full state space; `subjectRace()` reads only `path_xyz` from the same objects
and the stepper never looks at `path_state` at all.

The synthetic "nominal" start is also invented rather than read:

```js
start = {p1: p1_nom, p2a: p1_nom*0.5, p3a: 1.0, w_a: 500, p2b: p1_nom*0.5, p3b: 1.0, w_b: 500};
```

against the real `model.nominal_start`, which for the shipped fixture is
`p3a = 0`, `w_a = 1241`, `w_b = 1858`. The hardcoded `w = 500` and `p3 = 1.0`
correspond to nothing in the model.

Also in the same function: `p_crack || 150` silently substitutes 150 bar for a
legitimately-zero value.

*(An earlier draft of this entry also claimed `relief_open: currState.p1 > p_crack`
was a different criterion from `model.regime`. It is not, in any way that
matters: `relief_opening()` is exactly zero at and below the cracking pressure,
so `op > 1e-9` and `p1 > p_crack` differ only over a band of about 2.7e-4 bar
with `RELIEF_BAND = 15`. Withdrawn.)*

**Why it matters:** this is the one panel on the page whose entire content is
made up, sitting under a heading that says "Newton Convergence", on a page
whose argument is that it never quotes a number the pipeline did not compute.

#### Resolution

`getStepperTrajectory()` is now a one-line call to a new `armPath(arm)`, which
reads `LIVE.paths[arm]` for an analysed run and `VIZ.race[arm].path_state` for
the fixture — both already rows in `state_order` — and returns `null` for an arm
that was never solved. The synthetic branch, the hand-built start states and the
sine ease are gone.

Verified in the browser. On the shipped fixture the drawn cold path is now
byte-identical to `viz_results.json`, negative excursion included:

```
drawn: 0, 107.91, -20.59, 87.9, 113.61, 125.44, 130.97, 133.64, 134.79, 134.63, …
real : 0, 107.91, -20.59, 87.9, 113.61, 125.44, 130.97, 133.64, 134.79, 134.63, …
  identical: true
```

and the nominal start is the real `model.nominal_start` (`p3a = 0`, `w_a = 1241`,
`w_b = 1858`) rather than the invented `p3a = 1.0`, `w = 500`. On `run-tidy.log`
all three arms match the trace the server returned exactly — cold 9 iterates,
nominal 8, warm 4.

A visible consequence worth having: stepping the real cold path on
`run-bigpump.log` shows the relief valve opening at iteration 1, shutting by
iteration 5 and reopening by iteration 10. The old monotone interpolation could
not have produced that, because it never crossed the cracking pressure twice.

Three things came with it:

* **M4 is fixed.** The arm tabs are rendered by `renderStepperArms()` from the
  iterate counts that exist for the case on screen, so "Cold Start (8+ iters)"
  is now "Cold Start (11 iters)" on the fixture and "Cold Start (10 iters)"
  after analysing `run-bigpump.log`. The static labels and the stale
  `max="8" value="3"` on `#steprange` are out of the markup.
* **An arm that was not run says so.** Its tab reads "Warm Start (not run)",
  renders dashed and disabled, and the slider and Play button disable with it.
  This closes the worst part of M2: the stepper no longer fabricates a warm
  trajectory *from the retrieved neighbour* for a transfer the verifier refused,
  and `MACH.overrideState` is cleared so the machine view stops labelling that
  run `(warm start, iter 3/4)`.
* `STEPPER.step` starts at 0 rather than 3, so the first paint is the starting
  guess rather than a mid-iteration state.

Still open from M2: `renderGeoNums` continues to print `undefined` / `NaN` for
`warm_iterations` and `agreement` on a warned-not-overridden run, and the
`#liverow` banner still says "the case retrieval chose for it". Those are in
`renderGeoNums` / `adoptTrace`, not in the stepper.

---

### C2 — Selecting the Ollama backend disables foreign-domain detection

> **FIXED.** The domain check moved out of `ingest_rules` and now runs ahead of
> every backend. Resolution note at the end of this entry.

**Verified.** `ingest.py:330` (`ingest_ollama`), `ingest.py:222` (`ingest_llm`)

`ingest_rules()` calls `casecard.detect_domain(text)` and sets `domain` /
`foreign` on the card. `ingest_ollama()` and `ingest_llm()` construct their
`CaseCard` without either field, so it defaults to `DOMAIN` ("hydraulic-1d")
and `card.foreign_domain` is always `False`.

`ingest_hybrid` is unaffected (it starts from the rules card), but **"ingest:
Ollama only (local)" is a first-class option in the page's dropdown**, and
`part-bracket.log` — the NASTRAN deck shipped specifically to demonstrate the
refusal — is a one-click sample beside it.

Reproduced end-to-end with a live Ollama (`qwen2.5:7b`):

```
ingest.ingest_text(part_bracket_text, 'part-bracket.log', backend='ollama')
  domain      = hydraulic-1d      (should be structural-3d-fe)
  foreign     = False
  params      = {'Q_nom': 1471.0, 'rho': 2700.0}
  missing     = ['A_valve_a', 'A_valve_b', 'c_load_a', 'c_load_b', 'p_crack']

dejasolve.analyse(..., backend='ollama')
  OUTCOME  = refused_incomplete
  SUMMARY  = missing A_valve_a, A_valve_b, c_load_a, c_load_b, p_crack
```

`rho = 2700 kg/m³` is the aluminium density from the `MAT1` card, recorded as
the hydraulic fluid density. `casecard.py:31-39` names this exact scenario as
the reason the domain check exists. The Units gate passes it — 2700 is inside
`lo/100 … hi*100` = 8 … 90000 — and reports "all 2 values are within a physical
range".

The refusal still happens, but for the wrong reason and with the wrong story:
"you forgot five parameters" instead of "this is a 3D structural FE deck and
nothing in this archive applies to it". Fill in five plausible hydraulic
numbers alongside the deck and the aluminium density goes straight into
retrieval.

**Related, same functions:** `ingest_llm` does `float(v)` over the raw payload
with no key filter and no `None` guard (`ingest.py:221`), where `ingest_ollama`
carefully coerces and drops. A `null` or an unexpected key from the model
raises `TypeError` / `KeyError`, neither of which is the `RuntimeError` that
`dejasolve.analyse` catches at line 235 — so it escapes as an HTTP 500 rather
than a pipeline stage with a reason.

#### Resolution

New `ingest.foreign_card(text, artifact, case_id, which)` returns a Case Card
with the foreign domain, the readable facts and no parameters — or `None` if the
artifact belongs to this schema. `ingest_ollama` and `ingest_llm` both call it as
their first statement, so the check runs *before* the model is asked, for the
same reason `ingest_hybrid` already short-circuited there: a structural deck has
nothing for the extractor to find, and asking anyway is how a language model gets
talked into inventing seven parameters.

Verified across every backend with a live Ollama — all five now agree, and the
model paths return instantly instead of paying a minutes-long inference:

```
rules    domain=structural-3d-fe  foreign=True  params={}  by=rules
ollama   domain=structural-3d-fe  foreign=True  params={}  by=ollama:qwen2.5:7b (foreign domain, model not asked)
llm      domain=structural-3d-fe  foreign=True  params={}  by=llm:claude-opus-5 (foreign domain, model not asked)
hybrid   domain=structural-3d-fe  foreign=True  params={}  by=rules (foreign domain, model not asked)
auto     domain=structural-3d-fe  foreign=True  params={}  by=rules (foreign domain, model not asked)
```

and end to end, where the outcome used to be `refused_incomplete` on the model
backends:

```
rules  -> foreign_domain  | 3D structural FE (NX Nastran deck); nothing in this archive applies to it
ollama -> foreign_domain  | 3D structural FE (NX Nastran deck); nothing in this archive applies to it
hybrid -> foreign_domain  | 3D structural FE (NX Nastran deck); nothing in this archive applies to it
```

`rho = 2700` no longer reaches a Case Card by any route.

The related item is fixed too: `ingest_llm` now coerces its payload exactly as
`ingest_ollama` does — unknown keys and `null`s are dropped rather than raising
past `dejasolve.analyse`'s `RuntimeError` handler — and filters `provenance` to
known parameter names.

One deliberate behaviour change: `--backend llm` on a foreign artifact now
returns the refusal without requiring the anthropic SDK or credentials, because
the domain check no longer needs a model to run. `python dejasolve.py --all
--backend rules` and `python selftest.py` (5/5) are unchanged.

---

## Major

### M1 — A warm-started run whose cold arm failed is reported as a cold start

> **FIXED.** The headline branches on which arm ran, not on which comparisons
> happened to be computable, and a failed baseline is named as a failure
> everywhere its iteration count used to appear bare. Resolution note at the end
> of this entry.

**Verified.** `dejasolve.py:492-501`

`solve["agreement"]` and `solve["saved"]` are only set when **both** cold and
warm converged (`dejasolve.py:448`). The headline chain immediately below then
reads:

```python
if warm is not None and "saved" in solve:   ...      # normal case
elif label == "nominal":                     ...      # warned, archive unused
else: headline = f"cold start, {cold['iterations']} iterations"
```

There is no branch for *warm converged, cold did not*. It falls into the `else`
and names the wrong arm, quoting the failed arm's stalled iteration count as if
it were the answer.

Reproduced with `query-0014` from `results.json` (one of the four cases where
the flat start fails), fed in as an artifact:

```
outcome:  warm_started
summary:  cold start, 7 iterations          <- wrong arm, wrong number
cold:     7  line_search_stall              <- did not converge
warm:     4  converged     start = warm
Solve stage headline: "cold start, 7 iterations"
```

In the browser this compounds three ways:

* `draw()` (`static/index.html:1883`) gates the headline block on
  `s.agreement !== undefined`, so **the cold → warm metric block does not render
  at all**. The page's flagship number disappears on exactly the cases where the
  warm start helps most.
* The fallback verdict bar reads `warm_started — cold start, 7 iterations`,
  contradicting itself in seven words.
* The Solve stage renders with a green ✓ and the text "warm-started
  initialisation / cold start, 7 iterations".

Separately, `#geonums` shows `iterations 7 → 4 cold → warm`, presenting a
*stalled* arm's iteration count as the cold baseline with no indication it never
converged.

#### Resolution

Two halves — the trace, and every panel that reads an iteration count out of it.

**`dejasolve.py`.** The headline chain now selects on `warm is not None` rather
than on `"saved" in solve`, so the arm that produced the answer is the arm the
headline names. A baseline that failed is rendered as `cold line_search_stall`
instead of `7 cold`, because its count is the step it gave up on, not a finish
line to compare against.

"Same answer" needs a *converged* arm to be same as. `agreement` used to exist
only in the cold branch; it is now computed against each baseline that converged
(`agreement_vs_cold`, `agreement_vs_nominal`), with `agreement` / `saved`
pointing at the first available and a new `agreement_against` naming which. When
neither baseline converged the claim is not made at all — the headline says
`no converged baseline to check the answer against` rather than quoting an
agreement with nothing.

`solve` also gained `cold_converged` / `nominal_converged` / `warm_converged`,
because every consumer of a count needs to be able to tell a result from a stall
and `cold_status` was a string nobody was reading.

Verified on `query-0014`, the case from the reproduction above:

```
before:  cold start, 7 iterations
after :  cold line_search_stall / 7 nominal -> 4 warm iterations,
         same answer as nominal to 4.3e-14
```

The four clean fixtures are unchanged apart from `same answer to 2.3e-13`
becoming `same answer as cold to 2.3e-13`. `python selftest.py` 5/5.

**`static/index.html`.** The headline block is gated on `s.warm_iterations`
alone, so it renders for these runs instead of collapsing to the verdict bar. A
non-converged arm shows `did not converge` in red in place of its numeral, and
the agreement tile names the arm it compared against — or reads
`no converged baseline` in amber. In the browser:

```
COLD START [did not converge] | NOMINAL GUESS 7 | -> | WARM START 4
| NEWTON ITERATIONS  same answer as nominal to 4.3e-14
```

Three other panels quoted the same count bare and now do not: `#geonums` marks
it `7* → 4 … *did not converge`, the machine panel reads `then solved in 4
iterations from a cold start that never converged`, and the race legend and
caption say `7 iterations, did not converge` / `same answer, from the arms that
got one: the cold start did not converge at all`. The stepper tab reads
`Cold Start (7 iters, stalled)`. `subjectRace()` carries a `converged` flag
alongside `iterations` so the fixture and the live run answer that question the
same way.

---

### M2 — `undefined` and `NaN` on screen after a warned-but-not-overridden run

> **FIXED.** The stepper half went with C1; the `undefined` / `NaN` and every
> panel that described a refused transfer as an accepted one are now done too.
> Resolution note at the end of this entry.

**Verified.** `static/index.html:920` (`renderGeoNums`), `:550` (`liveFromTrace`)

When the verifier warns and the engineer does **not** override,
`dejasolve.analyse` sets `warm = None`, so `solve` has no `warm_iterations` and
no `agreement`. But `trace["retrieval"]["solution"]` is still populated
(`dejasolve.py:478`), so `liveFromTrace()` returns a `LIVE` object and
`adoptTrace()` adopts it. `renderGeoNums` then interpolates the missing keys
directly.

Reproduce: click the `run-bigpump.log` sample, backend `rules`, Analyse.
Verified output of the geometry panel:

```
setup distance   0.692     true, 7 parameters
state gap        57.4 bar  425 rev/min
iterations       10 → undefined   cold → warm
agreement        NaN       bar
```

(`(+undefined).toExponential(1)` is the `NaN`.)

The same run produces three further inconsistencies on the same screen, all
because a refused warm start is treated as an accepted one:

* `#liverow` reads *"showing run-bigpump.log — the artifact you just analysed,
  **and the case retrieval chose for it**"* — the pipeline explicitly did not use
  that case.
* `MACH.overrideLabel` is set to `"run-bigpump.log (warm start, iter 3/4)"`, so
  the machine view labels the case as warm-starting.
* The stepper's default `warm` arm finds no `LIVE.paths.warm`, falls into the C1
  synthetic branch, and fabricates a warm trajectory *starting from the
  retrieved neighbour's solution* — drawing the transfer the verifier just
  refused.

The race-tab caption also asserts `"Cold 10, nominal 7, warm — iterations —
same answer"` (`static/index.html:801`), claiming agreement between arms when one
of them never ran.

#### Resolution

The root cause was that `liveFromTrace` recorded the retrieved neighbour and the
iteration counts but nothing about *whether the archive was used*. `neighbour`
being present is not the same statement as "this run warm-started" — a warned
transfer still retrieves and still reports a neighbour, it just never starts from
it — and five panels read the first as the second.

`liveFromTrace` now carries `usedArchive`, `converged` and `agreementAgainst`
alongside the counts, and each panel says what actually happened:

| panel | before | after |
|---|---|---|
| `#geonums` iterations | `10 → undefined` | `10 → not run` |
| `#geonums` agreement | `NaN bar` | `not checked · the archive was not used` |
| `#liverow` | "…and the case retrieval chose for it" | "…beside the case retrieval found and **the verifier refused**. It was not used as a starting point." |
| `#machdiff` | `then solved in — iterations from 10 cold` | `then solved in 7 iterations from the nominal guess — the archive was not used` |
| `#machnote` | "sweep-0223 is what retrieval chose out of 395." | same, plus "The verifier refused the transfer, so this state was not used as a starting point." |
| race caption | "…warm — iterations — same answer." | "…the warm arm was not run: the transfer was warned and left standing, so the solver started from the nominal guess instead." |

The stepper half was already closed by C1: the warm tab reads
`Warm Start (not run)`, disabled, and `MACH.overrideState` is cleared so the
machine view no longer labels the run `(warm start, iter 3/4)`.

Verified both ways round. Analysing `run-bigpump.log` gives every "refused"
wording above; clicking **Warm-start anyway** and re-analysing flips all six
panels back — headline `COLD START 10 | NOMINAL GUESS 7 | → | WARM START 3 |
same answer as cold to 2.9e-9`, banner back to "the case retrieval chose for it",
stepper arms back to `Warm Start (3 iters)`, and the audit trail records the
override.

---

### M3 — After a refusal, the geometry section keeps claiming to show the run you just analysed

> **FIXED.** A refused run now clears `LIVE` and falls back to the fixture, with
> a line saying which artifact was refused and why there is nothing to draw.
> Resolution note at the end of this entry.

**Verified.** `static/index.html:575` (`adoptTrace`)

`liveFromTrace()` returns `null` for any trace without a solved state — foreign
domain, incomplete card, implausible units, blocked transfer — and `adoptTrace`
returns early. The comment says *"those return null and the views keep showing
the fixture"*, but `LIVE` is never cleared, so what they actually keep showing is
the **previous** live case, banner and all.

Reproduce: analyse `run-bigpump.log`, then analyse `part-bracket.log`. The
pipeline correctly refuses the NASTRAN deck; the geometry section below still
reads:

```
showing run-bigpump.log — the artifact you just analysed, and the case
retrieval chose for it
```

`#geonums`, `#machdiff`, `#machnote`, the contact sheet and both machine views
all continue to describe `run-bigpump.log`. Only `#flow` correctly hides itself
(`adoptFlow` handles the null case, `adoptTrace` does not).

#### Resolution

The teardown existed but lived only inside the "Show the shipped example" button's
click handler, so the one path that also needed it — a refused run — could not
reach it. It is now a function, `showFixture(note)`, which both callers use, and
the per-panel re-render is a second function, `renderGeoAll()`, so no caller can
refresh the view and the machine panel while forgetting the contact sheet. That
selective-refresh mistake is the one the comment above `renderGeoNums` already
describes; it is now structurally hard to repeat.

`adoptTrace`'s early return became a call to `showFixture` with an explanation:

```
part-bracket.log produced no solved state (foreign domain), so there is nothing
to place in this space — showing the shipped example instead. The refusal is above.
```

Verified as a four-step sequence in the browser — analyse `run-bigpump.log`, then
the NASTRAN deck, then `run-truncated.log`, then `run-tidy.log`:

| step | `LIVE` | what the section shows |
|---|---|---|
| `run-bigpump.log` | `run-bigpump.log` | its own numbers, warned wording |
| `part-bracket.log` | `null` | fixture, "produced no solved state (foreign domain)" |
| `run-truncated.log` | `null` | fixture, "produced no solved state (refused incomplete)" |
| `run-tidy.log` | `run-tidy.log` | its own numbers, `8 → 3`, recovered cleanly |

`#flow` hides on both refusals and returns on the clean run. One small behaviour
change: `showFixture` also clears a hand-picked tile, which the old reset handler
did not — going back to the shipped example now resets the whole section rather
than most of it.

---

### M4 — Stepper arm labels are hardcoded and contradict the data beside them

> **FIXED** as part of C1 — the tabs and the slider range are rendered from the
> iterates that exist for the case on screen. See C1's resolution note.

**Verified.** `static/index.html:396-398`

```html
<button class="geotab" data-arm="cold">Cold Start (8+ iters)</button>
<button class="geotab" data-arm="nominal">Nominal Guess (7 iters)</button>
<button class="geotab on" data-arm="warm">Warm Start (3-4 iters)</button>
```

These are static text and nothing updates them. On the shipped fixture the real
counts are cold 11 / nominal 7 / warm 4; after analysing `run-bigpump.log` they
are 10 / 7 / (none). So the tab reads "Cold Start (8+ iters)" while the readout
directly underneath it says `Iteration 0 of 10`, and "Warm Start (3-4 iters)"
sits above a run that has no warm arm at all.

`#steprange` likewise ships `min="0" max="8" value="3"`, which is corrected on
the first `updateStepperUI()` but is the wrong range in the served HTML.

Related: `STEPPER.step` initialises to **3**, not 0, so on first paint the left
machine view is already showing a mid-iteration state labelled
`(warm start, iter 3/4)` rather than the query case's solved state — while
`#machdiff` immediately below quotes differences computed from the *converged*
state. Two panels, one screen, two different states of the same case.

---

### ~~M5 — The evidence panel is gone but `/api/evidence` is still built and served~~

> **WITHDRAWN — not a bug.** The finding's central claim was wrong and the
> conclusion drawn from it would have broken working code. Correction below.

**What I originally reported.** That `GET /api/evidence` returns seven populated
sections and nothing consumes them, so either the panel should come back or
~190 lines of endpoint should go.

**Why that was wrong.** The first half is true only of `static/index.html`. The
endpoint has a live consumer:
[`presentation/evidence-section.html`](../presentation/evidence-section.html)
fetches `/api/evidence` and renders the same seven cards for the deck. I checked
the page and not the project, and reported an unused endpoint on that basis.

`README.md` also documents the removal as a deliberate, reasoned decision rather
than an oversight — the panel was pulled because *a demo showing curated offline
benchmark numbers next to a live pipeline read as more decided than the work
deserved*, with the section kept intact for reuse in the deck and the endpoint
kept serving it. That is a defensible call, and the arrangement is working as
designed.

**What was actually wrong, and is now fixed.** Only the two leftovers in
`static/index.html`, both of which pointed at things that had moved to the deck
file: the orphaned `.ev h2` selector (no `.ev` element exists on the page) and a
comment reading *"the same reason as lineChart above"*, referring to a function
that left with the panel. Both are corrected in place with a note saying where
they went. `.geo h2` / `.mach h2` keep their gradient rule — verified with
`getComputedStyle`, and `/api/evidence` still returns all seven sections with
`missing: []`.

**Standing decision: keep the endpoint.** It backs the deck asset. Anyone
tempted to delete it as dead code should read this entry first — that is the
main reason it is kept here rather than deleted outright.

---

### ~~M6 — Horizontal overflow and a clipped column on mobile~~

> **WON'T FIX** — decided 2026-08-25. This app is a desktop demo shown on a
> laptop or a projector and will never be used on a phone, so the layout is not
> worth the responsive work. The finding is left on record rather than deleted,
> so that a future reader who does open it on a phone finds the explanation
> instead of rediscovering it. Nothing below has been changed in the code.

**Verified** at 375 × 812.

The Case Card table renders 442 px wide inside a 375 px viewport. Measured:
`documentElement.clientWidth = 375`, `scrollWidth = 425` — the whole page scrolls
sideways. Because `.panel` sets `overflow:hidden` (`static/index.html:92`), the
rightmost column (`td.raw`, the "read from" provenance) is **clipped with no way
to scroll to it**, so the provenance — the thing that makes the extraction
auditable — is unreachable on a phone.

The table needs an `overflow-x:auto` wrapper, or the provenance column needs to
collapse below a breakpoint.

---

## Minor

### N1 — `regime()` and `estimate_regime()` ignore the 18 promoted hardware constants

> **FIXED.** Both now resolve this case's own hardware. Resolution note at the
> end of this entry.

**By inspection.** `model.py:856` (`regime`), `verifier.py:110` (`estimate_regime`)

`flows()` correctly resolves per-case hardware via `hardware(p)` / `shaft_hw(h, s)`.
`regime()` does not — it calls `orifice_gain(A_RELIEF_MAX, p["rho"])` and
`relief_opening(p1, p["p_crack"])` with the module constants and the default
`RELIEF_BAND` and default `cd`. A case that states its own `A_relief_max`,
`relief_band` or `cd` gets a `relief_fraction` and `relief_flow_share` computed
for different hardware than it actually has — and `regime` is what the archive
records and what gate 1 compares against.

`shaft_regime(w)` has the same problem: it tests against the global `W_STRIB`,
not the per-shaft `w_strib_a` / `w_strib_b`.

`estimate_regime()` compounds it — it uses `model.motor_constants(p)` (which
reads only the `D_mot` shorthand, never `D_mot_a` / `D_mot_b`) plus
`model.RELIEF_BAND`, `model.R_LEAK`, `model.T_COUL` and `model.T_STAT` directly.
So gate 1 checks the promoted constants very carefully for the hardware rule and
then estimates the regime as if none of them existed.

#### Resolution

`model.regime()` now resolves `hardware(p)` / `shaft_hw` the same way `flows()`
already did, and `shaft_regime()` takes the per-shaft `w_strib` as a parameter
(defaulting to the module constant, so every other caller is untouched).
`model.motor_constants(p, shaft=None)` gained an optional `shaft` argument: with
none it behaves exactly as before (the `D_mot` shorthand `fold.py`'s variant
circuit depends on), and with `'a'`/`'b'` it resolves that branch's own
displacement through `hardware()`.

`verifier.estimate_regime()` keeps its existing top-level keys
(`can_break_away`, `stall_torque_Nm`, `breakaway_margin`) computed exactly as
before — `agent_select.py`'s physics ranker reads them, and changing what they
mean would have silently moved an already-measured result out from under it
without anyone rerunning it. A new `breakaway` dict adds the per-shaft version,
resolving each branch's own `t_stat`, `t_coul` and motor displacement.

This is a **guaranteed no-op for every case in `archive/cases.jsonl` and every
fixture in `logs/`**: `sweep.py` (which built that archive) never sets any of
the 18 constants, so `hardware(p)` resolves to the module defaults for every
record either way. Confirmed with `python selftest.py` (5/5, including the
"explicit defaults == module defaults" check) and `python dejasolve.py --all`
(byte-identical output). The fix only changes behaviour for a case that states
its own hardware — which today means only `wide_sweep.py`'s synthetic machine
variants (see N2's resolution note for what that implies for its results file).

### N2 — The breakaway gate refuses any source case with mixed shaft states

> **FIXED**, together with N1 — the per-shaft `breakaway` dict N1 added is what
> this gate now reads. Resolution and a real before/after test at the end of
> this entry.

**By inspection.** `verifier.py:215-229`

`est["can_break_away"]` is one circuit-wide boolean, but the loop compares it
against each shaft of the source separately:

```python
for s in ("a", "b"):
    src_spinning = src_regime[f"shaft_{s}"] != "stuck"
    if est["can_break_away"] != src_spinning:
        return Verdict(False, "breakaway", ...)
```

If the source has shaft a turning and shaft b stuck, one of the two comparisons
must fail whatever `can_break_away` says, so the transfer is refused
unconditionally. The estimate ought to be per-shaft — the shafts have
independent `c_load_a` / `c_load_b` and, since the promotion, independent
`t_stat_*` and `t_coul_*`, so a per-shaft estimate is well-defined.

#### Resolution

The gate now compares each shaft against `est["breakaway"][s]["can_break_away"]`
rather than the shared scalar. Tested directly against both the finding's
scenario and its mirror image, using a synthetic case with `t_stat_a = 1` Nm
(trivially breaks away) and `t_stat_b = 1e5` Nm (never does) — same torque
supply to both shafts, so only the per-shaft threshold differs:

```
per-shaft breakaway estimate: {a: True, b: False}

Source regime: shaft_a spinning, shaft_b stuck (physically consistent
with the estimate above)
  old code -> BLOCKED: "shaft b breaks away here (104.4 Nm available),
              but the source case has it stuck"
              -- wrong on the facts (t_stat_b=1e5 was ignored, using the
              module default instead) and wrong on the shape of the check
              (one scalar can't agree with two independent shafts)
  new code -> ADMITTED: "same regime, 0.00 away in setup space"

Source regime: shaft_a spinning, shaft_b ALSO spinning (a genuine mismatch --
the query's own physics says shaft b cannot break away, so this source case's
regime does not apply here)
  new code -> still BLOCKED: "shaft b cannot break away here (104.4 Nm
              available vs 100000 Nm needed), but the source case has it
              turning"
```

The second run is the check that matters: the fix admits mixed states that are
physically consistent, and still refuses ones that are not — it did not just
loosen the gate.

**What this does not touch.** Every query the live pipeline can produce today
resolves to default hardware (see N1 — N3 is why: ingest cannot write these
fields onto a Case Card), so `check_transfer`'s behaviour on `/api/analyse` is
unchanged. The one place that already exercises non-default hardware through
this exact gate is `wide_sweep.py --tolerance`, which varies all 18 constants
across six synthetic "machine variants" and calls `Verifier.check_transfer`
directly. Its committed `wide_sweep_results.json` — the "25 real parameters,
six machine variants" section of `/api/evidence` and the README — was measured
against the old, buggy gate, and this fix can change which transfers it admits.
I did not regenerate it: that is a `python wide_sweep.py` rerun (smoke-tested
below, no crash, all queries converged) changing a committed, cited result, and
that call belongs to whoever owns the deck, not to a bug fix. **Flagging for a
decision:** regenerate `wide_sweep_results.json` before the numbers on
`/api/evidence` are shown next to this code, or note the discrepancy if they
are shown as-is in the meantime.

### N3 — The 18 promoted constants cannot be read from any artifact

> **FIXED.** All four backends can now put a hardware constant onto a Case
> Card, `validate()` bounds-checks them, and — the part this fix turned up as
> its own necessary half — a stated override is now visible everywhere the
> pipeline reports on a run, not just used silently. Resolution note at the
> end of this entry.

**By inspection.** `ingest.py:48` (`SYNONYMS`), `ingest.py:125` (`EXTRACTION_SCHEMA`)

`SYNONYMS` covers only the seven swept parameters, and `EXTRACTION_SCHEMA`
enumerates `model.PARAM_NAMES` with `additionalProperties: False`. So no
backend — rules, ollama, llm or hybrid — can put `cd`, `t_stat_a`, `leak_mot_b`
or any of the other 18 onto a Case Card. `/api/health` reports
`"parameters": list(model.PARAM_NAMES)` (7), while the docs describe a 25-parameter
Case Card. Every path that can reach the constants (`fold.py`, `wide_sweep.py`)
is offline; the app itself cannot.

Related: `CaseCard.validate()` only bounds-checks names present in
`model.PARAM_BOUNDS`, so if a constant ever does become ingestible, a stated
`relief_band = 0` or `cd = 0` passes the Units gate and then divides by zero in
`relief_opening()` / `orifice_gain()`.

#### Resolution

**Bounds.** `wide_sweep.py` already had physically-judged (lo, hi) multipliers
per constant (`HARDWARE_SPREAD` — "kept modest on purpose... a range wide
enough to stop cases converging would measure the sampler rather than the
gate"), used to generate its synthetic machine variants. It moved to
`model.py`, next to the `HARDWARE` defaults it is a spread *around*, and a new
`model.HARDWARE_BOUNDS` applies it in absolute units — `PARAM_BOUNDS`'s
counterpart for the 18. `wide_sweep.py` now imports the constant instead of
keeping a private copy that could silently drift from it. `CaseCard.validate()`
checks a stated hardware value against `HARDWARE_BOUNDS` with the same 100×
orders-of-magnitude slack it already applies to the 7 swept parameters —
closing the divide-by-zero risk this entry named.

**Units and synonyms.** `casecard.py` gained `HARDWARE_UNITS` (18 entries,
read off `model.py`'s own inline unit comments) and `ALL_UNITS`, the merged
view code that doesn't care which group a field is from needs. `ingest.py`'s
`SYNONYMS` gained English phrasings for all 18 (no Romanian — unlike the seven
required fields, no fixture demonstrates a concrete need for it, so nothing
was guessed).

**Reaching all four backends.** `ingest_rules` was already general — it stores
whatever `SYNONYMS` maps a line to, with no gate to `PARAM_NAMES` — so the
synonym additions alone made the rules backend capable. `ingest_ollama` and
`ingest_llm` each had an explicit `if key not in model.PARAM_NAMES: continue`
filter that discarded anything else; both now check the wider
`EXTRACTABLE_FIELDS` (`PARAM_NAMES + tuple(model.HARDWARE.keys())`), and
`EXTRACTION_SCHEMA` / the `SYSTEM` prompt describe all 25 fields, with the
prompt explicit that the 18 are optional and must never appear in `missing`
(only the 7 required fields can).

**`ingest_hybrid`'s narrower gap.** Its "rules found everything → skip the
model" fast path is a deliberate, documented speed optimisation (an
artifact-dependent inference call would defeat the whole point) and is
untouched. But when the model *was* already invoked because a required field
was missing, its backfill loop only ever copied fields listed in
`card.missing` — never a hardware constant, since those are never "missing" by
definition — so a hardware override the model found in the same call used to
be silently thrown away. A second loop now merges any of the 18 the model
found, at no extra cost since the call already happened, with `card.params`
checked first so rules keeps precedence where both found the same field.

**A real bug this exposed and fixed alongside it.** `dejasolve.py`'s ingest
stage counted `found = len(card.params)` for its "N of 7 parameters read"
headline. Once `card.params` could hold more than 7 keys, a stated hardware
constant would have inflated that count past the fixed "of 7" denominator —
"8 of 7 parameters read". `found` now explicitly counts only
`model.PARAM_NAMES` membership. Caught by an end-to-end test before it ever
reached a screen, not by inspection.

**The part that made this a complete fix rather than a working feature no one
could see.** A stated hardware constant changes the solve — it feeds
`model.hardware(p)` the same way the seven required fields do — and the Case
Card table on the page only ever displayed the 7. Without more, ingest could
now *read* a value that silently changed the answer while showing nothing on
screen to explain why: exactly the failure mode every other layer of this
project exists to refuse. `dejasolve.analyse` now builds
`trace["hardware_overrides"]` — only the constants a given artifact actually
stated, alongside `model.HARDWARE`'s default for context — and it renders in
three places: the Ingest stage's headline ("7 of 7 parameters read by rules,
2 hardware overrides stated"), the CLI's `render()`, and a second table on the
web page directly under the Case Card, shown only when non-empty.

**Verified end-to-end**, not just read: an artifact stating
`discharge coefficient: 0.62` and `breakaway torque a: 12.5 Nm` alongside the
seven required fields —

```
ingest headline: 7 of 7 parameters read by rules, 2 hardware overrides stated
card.params keys: [..., 'cd', ..., 't_stat_a']
hardware_overrides: [{'name': 'cd', 'value': 0.62, 'default': 0.7}, ...]

p1 WITH cd=0.62 override:    150.50 bar
p1 WITHOUT override (default): 125.97 bar   <- confirms the override reached the solver
```

and in the browser, the same artifact produces the Ingest stage headline
above and a second table reading `cd | 0.62 | | 0.7 | 0.62` /
`t_stat_a | 12.5 | Nm | 14 | 12.5 Nm`. `validate()` on a synthetic `cd = 700`
correctly reports "off by orders of magnitude (plausible range 0.595 to
0.805)". The `ingest_hybrid` merge loop was verified in isolation (substituting
a controlled model response, since the local 7B model's free-prose extraction
turned out to be too unreliable to exercise this specific path deterministically
in a live test) — a required field filled through the existing loop, a
hardware constant filled through the new one, in the same call.

**What this does not change:** the 7 swept parameters, the archive, and
retrieval are completely untouched — `Archive.nearest()` still normalises only
on `model.PARAM_NAMES`, and the Case Card table's first (required) section is
identical to before. Checked directly: no reference to any of the 18 constant
names exists anywhere in `static/index.html`'s 3D drawing code (`machineParts`,
`schematic`, `renderMachine`) — bore sizes come from `A_valve_a`/`A_valve_b`
(already one of the 7), pipe colours and shaft speeds come from the *solved
state*, never from a hardware constant directly. The geometry the page draws
is identical whichever way a case's hardware resolves; only the solved numbers
can move, and only for an artifact that explicitly states one of these 18
fields — none of the shipped sample fixtures do. `python selftest.py` (5/5,
byte-identical) and `python dejasolve.py --all` (byte-identical) confirm the
seven fixtures and the archive are unaffected.

### N4 — "Show the retrieved pair" leaves the hand-picked tile selected

> **FIXED.** The button now clears `GEO.sel` and the tile highlight along with
> `MACH.right`, and re-renders the cloud. Resolution note at the end of this
> entry.

**Verified.** `static/index.html:1728`

`$('#machpair').onclick = () => { MACH.right = null; renderMachPanel(); }` clears
the machine panel's right subject but never clears `GEO.sel` or the tile's `.on`
class. Measured after clicking a tile then clicking the button:

```
GEO.sel        = "sweep-0297"    (still selected)
MACH.right     = null            (reverted)
tile.classList = contains "on"   (still highlighted)
#machnote      = "sweep-0223 is what retrieval chose ..."
```

The contact sheet shows a selected tile, the 3D cloud shows it as the white
highlighted point, and neither machine view is showing it.

#### Resolution

The `#machpair` handler now mirrors `renderTiles`'s own click handler — the
only other place `GEO.sel` was ever cleared — clearing `GEO.sel`, removing
every tile's `.on` class, and calling `renderView()` so the cloud drops the
highlight, not just the panel above it.

Verified as a click sequence: select tile `sweep-0297` (`GEO.sel` set, tile
`.on`, `MACH.right` set), then click "Show the retrieved pair" —
`GEO.sel: null`, `MACH.right: null`, no tile carries `.on`. All three states
now revert together.

### N5 — Three uncapped `requestAnimationFrame` loops, ~12 ms of JS per frame

> **FIXED.** Each loop now skips its expensive redraw while its section has no
> layout box on screen, and the per-pipe checkbox lookup is cached. Resolution
> note at the end of this entry.

**Verified.** `geoTick`, `machTick`, `flowTick` (`static/index.html:974`, `1553`, `1214`)

All three run for the life of the page. None is paused when its section is
scrolled out of view, and none of the stored handles (`GEO.raf`, `MACH.raf`,
`FLOW.raf`) is ever passed to `cancelAnimationFrame`. Measured per frame on a
desktop machine:

| loop | ms/frame | SVG nodes rebuilt |
|---|---|---|
| `machTick` (two views) | 7.99 | 178 each |
| `renderView` (spinning) | 2.65 | 403 |
| `renderFlow` | 1.14 | — |

That is roughly 12 ms of main-thread JavaScript per frame before the browser
parses the new markup and re-lays out ~600 SVG nodes, against a 16.7 ms budget.
On a conference-room laptop this drops frames and spins the fan.

`drawPipe` also does `$('#flowparticles')` — a `document.querySelector` — once per
pipe per view per frame (~1700 lookups/second) to read a checkbox that changes
maybe twice a session.

#### Resolution

A new `trackVisible(id, state)` helper puts an `IntersectionObserver` on a
loop's own section (`#geo`, `#mach`, `#flow`) and sets `state.visible` from
whether it currently has a layout box on screen. Each tick function keeps
advancing its own timers unconditionally — `GEO.yaw`, `MACH.yaw`, the frame
clocks — so the picture is still exactly where it should be the instant the
section scrolls back into view; only the expensive part (`renderView`'s ~400
SVG nodes, `renderMachine`'s ~178 per view) is skipped while nothing could show
it. `#flowparticles` is now read once at boot and kept current by a `change`
listener, replacing the per-segment `document.querySelector`.

**Verification limitation, stated plainly:** I could not observe the
visibility toggling itself in this session's browser tool. Its
`IntersectionObserver` never fired for *any* element, including a trivial
freshly-created div confirmed to be in the viewport by its own
`getBoundingClientRect()` — traced to the preview pane not being displayed, the
same condition that makes `computer{action:"screenshot"}` fail with "the
Browser pane is not displayed, so the page is not compositing frames" in this
tool. A non-composited tab does not run the callback; that is a property of
this automation environment, not of the page. `IntersectionObserver` with a
single `.observe()` call and a `{threshold: 0}` config is standard,
well-supported usage with no unusual conditions attached — nothing in `drawPipe`
or the tick functions depends on when the callback fires, since `state.visible`
starts `false` (correct: nothing is on screen before the browser has laid out
the page) and every render call is already written to tolerate that default.
What I verified directly: the code runs without error through a full sequence
of `Analyse` calls across all seven fixtures with no new console errors, and
`FLOW_PARTICLES_ON` correctly starts `true` (matching the checkbox's `checked`
attribute) and updates on `change`.

### N6 — `prefers-reduced-motion` does not stop the animations that actually move

> **FIXED.** A `REDUCED_MOTION` flag now starts the two spins off and freezes
> every clock-driven redraw; the `#geoview` label and the two tab groups also
> gained ARIA state. Resolution note — including a real bug this work turned
> up — at the end of this entry.

**By inspection.** `static/index.html:33`, `:57`

The reduced-motion rules disable `.gradtext`, `.run`, `header::after` and the
body background drift. The three rAF loops — the spinning 3D assembly, the
rotating shaft marks, the fluid particles, the flow dots — are untouched. A
user who has asked the OS for less motion gets the static gradients and all of
the moving machinery.

Also a11y: `#geoview` has a fixed `aria-label` ("solved states of the archive,
projected to three dimensions") that never updates as the tab changes to "the
matched pair" or "cold vs warm"; the `.geotab` and `#steparms` buttons carry no
`aria-pressed`; and `#steprange` has no label or `aria-label`.

#### Resolution

A `REDUCED_MOTION` flag (`matchMedia('(prefers-reduced-motion: reduce)')`, kept
current on `change`) now does two things: `GEO.spin` and `MACH.spin` start
`false` instead of `true` — the Spin/Stop buttons still work, so nothing is
removed, only the default — and every clock-driven redraw freezes at `t = 0`
instead of reading `performance.now()`: `machTick`'s shaft-mark rotation,
`flowTick`'s dot animation, and `drawPipe`'s pipe-flow particles (the one
animation whose time source wasn't threaded through a caller at all — it read
`performance.now()` directly inside `drawPipe` itself, so it needed its own
gate). `#steprange` picked up `aria-label="Newton iteration"` as part of C1's
rewrite. `#geoview`'s `aria-label` now updates with the tab via a
`GEOVIEW_ARIA_LABEL` map read in `renderControls()`, and both tab groups
(`#geotabs`, `#steparms`) now set `aria-pressed`.

**Verified directly** (this part of the fix has no `IntersectionObserver`
dependency, so N5's tool limitation doesn't apply here): with `REDUCED_MOTION`
forced true, two renders of the same machine view 120ms apart are
byte-identical; with it false, they differ. Same result for the flow view.
`#geoview`'s aria-label reads correctly for all three tabs (`"solved states of
the archive…"` / `"the analysed case and its retrieved neighbour…"` / `"the
solver's path from each starting guess…"`), and both tab groups report correct
`aria-pressed` state.

**A real bug this surfaced, and fixed alongside it.** Adding `aria-pressed` to
`setMode()`'s tab-toggle loop exposed that the loop's own selector,
`document.querySelectorAll('.geotab')`, was never scoped to `#geotabs` — and
`.geotab` is the same class the stepper's arm buttons use, keyed by `data-arm`
rather than `data-mode`. Every time a user switched the geometry view tab
(archive / matched pair / cold-vs-warm), this loop ran across *both* button
groups, found `t.dataset.mode === m` false for every stepper button (they have
no `data-mode`), and stripped their `.on` highlight — so clicking "2 · The
matched pair" silently un-highlighted whichever stepper arm was selected, even
though `STEPPER.arm` itself was untouched and the trajectory kept stepping
correctly underneath. Purely cosmetic before this session (no `aria-pressed` to
also go wrong), it predates every change made here — I did not introduce it,
only made it visible. Fixed by scoping the selector to
`$('#geotabs').querySelectorAll('.geotab')`; the stepper's own tab handler
already scopes to `#steparms` and was never affected in the other direction.
Verified: selecting the warm arm, then switching through all three geometry
tabs and back, the warm tab keeps `on:true` / `aria-pressed:true` throughout.

### N7 — Content columns do not line up

> **FIXED.** `main` now uses the exact same `max-width:1180px; margin:0 auto`
> centring and the same 18px horizontal padding as `.geo`/`#mach` below it, so
> their box edges are identical at every viewport width by construction,
> rather than approximately matching at one width by coincidence.

**Verified** at 1280 px wide. `main` is full-bleed with `padding:20px 26px`, so its
panels start at x = 26. `.geo` / `.mach` are `max-width:1180px; margin:… auto`
with `padding:0 18px`, so they start at x = 43 and end at 1223 against `main`'s
1265. Every section below the fold is inset 17 px from the two above it.

#### Resolution

The two containers used different layout strategies — `main` was full-bleed
with a fixed 26px inset that never moves; `.geo`/`#mach` were centred with a
capped width and their own 18px inset, whose absolute position on screen
depends on viewport width. No single number reconciles a fixed inset with a
variable one at every width; only matching the *strategy* does. `main` picked
up `.geo`/`#mach`'s own numbers (`max-width:1180px;margin:0 auto;padding:20px
18px`, vertical padding kept as it was) rather than the other way round, so
all three now share one centring computation.

Verified at 1280×900: `main`, `.geo` and `#mach` report the identical
`getBoundingClientRect()` — `left: 42.4, right: 1222.4, width: 1180` — for all
three. Re-measured at 640px (below the cap, where the old code already
happened to align by coincidence): all three still match, at `left: 0, right:
624.8`. Same computation, so it can't drift apart at some third width the way
the previous fix-by-coincidence could have.

### N8 — The status hint is wiped by the health poll

> **FIXED.** The file-load confirmation moved to its own element, `#loadhint`,
> so `refreshHealth()`'s poll — which only ever touched `#hint` — has nothing
> in that element to overwrite. Resolution note at the end of this entry.

**Verified.** `static/index.html:494` (`explain`), `:510` (`refreshHealth`)

`loadFile()` writes `loaded <name> (n kB)` into `#hint`. `refreshHealth()` runs on
a 15 s interval and on window focus, and calls `explain()`, which unconditionally
overwrites `#hint` with the backend description. Confirmed: set the hint, call
`refreshHealth()`, the confirmation is gone. So the only feedback that a dropped
or picked file was read disappears within fifteen seconds.

#### Resolution

`#hint` was carrying two unrelated jobs — the backend explanation, rewritten
on every poll, and the file-load confirmation, meant to persist until the next
relevant action — and whichever wrote second always won. A new `#loadhint`
span, styled the same but written only by `loadFile()`, gives the confirmation
its own slot `explain()`/`refreshHealth()` never touch, so the collision is
gone structurally rather than by adding a delay or a "don't overwrite this
one" flag. While in there: a sample chip click now clears `#loadhint` too — it
didn't before, so choosing a sample after dropping a file used to leave a
"loaded x.log" confirmation on screen describing a file that was no longer
what was in the textarea. That half wasn't in the original finding but is the
same staleness problem from the opposite direction, worth closing alongside it.

Verified directly: load a file (`#loadhint` reads "loaded my-test.log (0.0
kB)"), call `refreshHealth()` (what the 15s poll and window-focus listener
both do) — `#loadhint` is untouched, `#hint` updates as it should. Click a
sample chip afterward — `#loadhint` clears.

### N9 — `AuroraArchive.nearest()` can raise `StopIteration`, and reconnects per request

> **FIXED.** A miss now raises a clear `RuntimeError` instead of a bare
> `StopIteration`, and the Secrets Manager round trip is cached for the
> process lifetime. Verified against a fake DB layer (no live Aurora in this
> environment) — resolution note at the end of this entry.

**By inspection.** `archive_aurora.py:98-121`

`self.records` is snapshotted at construction; `nearest()` queries the live table
and then does `next(i for i, r in enumerate(self.records) if r["case_id"] == case_id)`.
Any row inserted into `cases` after the process started returns a `case_id` the
snapshot does not contain, and the bare `next()` raises `StopIteration` —
unhandled, so an HTTP 500 with no message. Either re-read the record from the
same query or give `next()` a default and a real error.

Also, `_connect()` is called per `nearest()`, and each call makes a Secrets
Manager `get_secret_value` round trip plus a fresh TLS handshake to Aurora, so
every analyse pays two network round trips before it retrieves anything. The
docstring says a pool is "complexity this doesn't need yet"; the Secrets Manager
call at least is cacheable for the process lifetime.

#### Resolution

`__init__` now builds `self._index_by_id` (`case_id -> position`) once,
alongside the rest of the snapshot; `nearest()` does a dict `.get()` against
it and raises a `RuntimeError` naming the missing `case_id` and why ("the
archive changed since this service started; restart it to pick up new rows")
when pgvector returns a row this process's snapshot never saw. Still an HTTP
500 if it happens — no route in `dejasolve.analyse()` catches a retrieval
failure and turns it into a pipeline stage, and wiring that in is a bigger
change than this finding asked for — but a clear, actionable message now,
not a bare `StopIteration` with no context.

The Secrets Manager fetch moved into its own `_password(secret_arn)`,
wrapped in `functools.lru_cache(maxsize=1)`. The module's "no connection
pool, this demo doesn't need it" decision is untouched — that is about
Aurora's own connection volume, a separate question from repeating an
unrelated Secrets Manager API call on every single request for a secret that
does not rotate mid-demo.

**Verification limitation, stated plainly:** there is no live Aurora
instance or AWS credentials in this environment, so this could not be
exercised end-to-end the way the file-backed path was. Verified instead
against a fake DB layer standing in for `_connect()`/pgvector, isolating
`nearest()`'s own lookup logic: a `case_id` present in the snapshot resolves
correctly (`j = 1`, matching the expected row), and one absent from it raises
the new `RuntimeError` with the message above rather than a bare
`StopIteration`. `import archive_aurora` succeeds and `_password` carries the
`lru_cache` wrapper (`cache_clear` present). The Secrets Manager caching
itself — that a second `nearest()` call in the same process does not repeat
the API call — was not independently exercised beyond what `functools.
lru_cache`'s own well-established contract already guarantees.

### N10 — Dead code and unescaped interpolation in `draw()`

> **FIXED**, all six items. The `area` fix turned into a real (small) visual
> improvement rather than a deletion — resolution note at the end of this
> entry.

**By inspection.**

* `static/index.html:667` — `VW` and `VH` are declared and never read (`screen()`
  uses `VCX` / `VCY`).
* `static/index.html:1111` — `const L = []` in `flowLeg` is pushed to and never read.
* `static/index.html:820` — `schematic()`'s inner `branch(Y, p2, p3, w_, area)`
  takes `area` and ignores it; `p.A_valve_a` / `p.A_valve_b` are passed in at
  lines 846-847 and dropped. The section copy says "bore is the valve's real flow
  area", which is true of the 3D view (`machineParts` does use `bore(area)`) but
  not of the contact-sheet tiles.
* `static/index.html:74` — `h1 span{}`, an empty rule.
* `static/index.html:1918-1940` — `draw()` escapes most interpolated values but
  not `sug.on_fields`, not the parameter names in `Object.entries(sug.values)`,
  and not `st.detail.indexed_on`. All are server-generated today, so this is a
  consistency/robustness nit rather than a live XSS, but it is the one place in
  the file where `esc()` was skipped.
* `esc()` itself does not escape `'`. Every attribute in the file is
  double-quoted so nothing is currently exploitable, but the helper is one
  single-quoted attribute away from being wrong.

#### Resolution

`VW`/`VH` and `flowLeg`'s `L` array are gone. The empty `h1 span{}` rule is
gone. `esc()` now escapes `'` too (`&#39;`), matching `&`, `<`, `>`, `"`. The
three previously-bare interpolations in `draw()` (`sug.on_fields`, the
parameter names in `Object.entries(sug.values)`, `st.detail.indexed_on`) are
now wrapped in `esc()`.

`schematic()`'s `branch()` did more than start reading its own `area`
parameter — it now draws with it: the valve-to-motor segment's stroke width
is `bore(area) * 8`, the same `bore()` function and the same physical
variable `machineParts()` already uses for the 3D view's orifice bore. Before
this, every contact-sheet tile drew that segment at a fixed width regardless
of the case's actual valve area, so "bore is the valve's real flow area" was
true of the 3D view and false of the tiles beside it. Verified: a tile with
`A_valve_a = 9.55 mm²` renders that segment at stroke-width 3.39; one with
`A_valve_a = 1.08 mm²` renders it at 1.83 — the same physical difference the
3D view already showed, now visible in both places.

### N11 — `PSCALE` is fixed at boot, so a high-pressure live case saturates

> **FIXED.** `PSCALE` now recomputes on every live analyse, not only at boot.
> Verified with a case constructed specifically to exceed the fixture's
> ceiling — resolution note at the end of this entry.

**By inspection.** `static/index.html:941` (`renderTiles`)

`PSCALE` is computed once from the contact-sheet tiles plus the fixture pair
(measured: 258.3 bar) and is never recomputed in `adoptTrace`. `ramp()` clamps
its argument to 1, so any analysed case with `p1 > 258` renders every pipe at the
top of the colour ramp and is visually indistinguishable from any other
high-pressure case. `p_crack` alone goes to 260 bar in `PARAM_BOUNDS`, and `p1`
sits above `p_crack` whenever the relief is cracked, so this is reachable.

#### Resolution

`renderTiles()` already recomputed `PSCALE` correctly on every call — it reads
`subjectPair()`, which resolves to the live case once `LIVE` is set — but it
was only ever *called* once, at boot. The gap was that nothing re-called it
after a live analyse. The computation moved into its own `recomputePScale()`,
now called both from `renderTiles()` (unchanged) and from `renderGeoAll()`
(new) — `renderGeoAll()` rather than a second call to `renderTiles()` itself,
because `renderTiles()` rebuilds `#tiles` from scratch and does not know about
`GEO.sel`; calling it again on every live analyse would have silently cleared
whichever contact-sheet tile was hand-picked.

`PSCALE` also drives `machineParts()`'s pipe colours in the main 3D view, not
only the contact-sheet tiles — so this was clipping the primary visualisation
too, not a secondary one.

Verified with a case chosen specifically to exceed the fixture's own ceiling:
`p_crack = 260` (the sweep's own maximum), high pump flow, small valve areas.
Solved `p1 = 265.15 bar`, above the fixture's 258.33. Before analysing,
`PSCALE = 258.33`; after, `PSCALE = 265.15` — tracking the live case exactly
rather than clipping it. A second case with a more moderate `p1 = 209.65`
(safely under the original ceiling) correctly left `PSCALE` unchanged,
confirming the fix does not just always grow the number.

### N12 — Assorted smaller items

> **FIXED**, all seven. One correction to the original finding's last item
> below (`#flow` was never actually affected). Resolution notes inline with
> each item.

* `casecard.py:117` — `"bara"` and `"barg"` both map to a factor of 1.0. The
  model works in gauge pressure (`P_TANK`), so an artifact stating `bara` is
  read one bar high with no complaint.

  **Fixed.** `bara` (absolute) and gauge pressure differ by an *offset*
  (local atmospheric pressure), not a scale factor, so a purely multiplicative
  table could never represent this correctly at any factor. A new
  `UNIT_OFFSETS = {"bara": -1.01325}` (standard atmosphere) is checked ahead
  of `UNIT_FACTORS` in `normalise_unit`, applied additively rather than
  multiplicatively. `barg` is untouched (already correct — gauge, factor 1.0).
  Verified: `187.0 bara -> 185.98675 bar`; `187.0 bar` (unaffected) stays
  `187.0`.

* `casecard.py:125` — `normalise_unit` silently returns the value unconverted
  for any unit it does not recognise (`kg/dm^3` is absent while `kg/dm3` is
  present, for instance). A misread unit becomes a plausible-looking number,
  which is the exact failure mode the Units gate exists to catch — and the Units
  gate only sees the already-converted value.

  **Fixed generally, not by adding the one missing entry.** `^`/`²`/`³` are
  typography, not a different unit, and a table with an entry for only one
  spelling let every sibling spelling straight through unconverted. Both the
  table's own keys and every incoming unit string are now passed through
  `_norm_unit_key()` (a `str.translate` stripping `^` and mapping `²`/`³` to
  `2`/`3`) before lookup, so `kg/dm^3` and `kg/dm3` — and every other such pair
  already in the table, like `m^3/h`/`m3/h` — resolve identically without
  needing every sibling spelling hardcoded. Verified: `kg/dm^3` and `kg/dm3`
  both now convert to `850.0` from `0.85`; before this fix only the second
  form did.

* `ingest.py:89` — `if canon is None or canon in params: continue` means the
  *first* occurrence of a key wins. A log that states a value and then corrects
  it later keeps the superseded one.

  **Fixed.** Dropped the `or canon in params` clause, so a later line for the
  same field overwrites rather than being skipped — last occurrence wins.
  Verified: an artifact stating `Q_nom = 62.4` then `Q_nom = 65.0` now reads
  `65.0`, with provenance correctly citing the second line.

* `ingest.py:513` — `ingest_hybrid` copies `model_side.notes` onto the card even
  when the model contributed nothing, including the "[dropped …]" note
  `verify_provenance` appends about fields that were never used.

  **Fixed.** The copy is now gated on `filled` being non-empty — only when the
  model actually contributed a field does its note travel onto the card.

* `app.py:90` — `AnalyseRequest.text` has no `max_length`. A large paste runs the
  full parser and, on the ollama path, a 280 s inference, with no bound.

  **Fixed.** `max_length=1_000_000` (generous relative to every real fixture,
  which are all under a few kB, but bounded). Verified against the live API: a
  1,000,001-character payload is rejected with `422 string_too_long`; the
  existing seven fixtures are all far under the limit and unaffected.

* `app.py:70` — `_mirror_audit_to_dynamo` uses `print()` for its failure path
  rather than a logger, so under uvicorn the message lands on stdout with no
  level or timestamp.

  **Fixed.** A module-level `logger = logging.getLogger("dejasolve")`,
  `logger.warning(...)` in place of `print(...)`.

* `static/index.html:1749` — `geoBoot().catch()` removes `#mach` when
  `/api/viz` is unavailable, but `#stepper` and `#flow` are left in the DOM. Since
  `stepperBoot()` is only reached from the tail of `machBoot()` (itself the tail
  of `geoBoot()`), the "Newton Convergence & Fluid Dynamics Studio" renders in
  full — tabs, slider, Play button — with no event handlers attached to any of
  it. Every control is inert and nothing says why.

  **`#flow` was never actually the same problem — withdrawn from the finding.**
  `adoptFlow()` reads only `t.solve.flows`/`.solution`/`.regime` straight off
  an `/api/analyse` trace; it has no dependency on `VIZ` at all, so it renders
  correctly whether or not `/api/viz` succeeded. Grouping it with `#stepper`
  in the original finding was wrong.

  **`#stepper` was worse than inert — fixed.** `armPath()` dereferences
  `VIZ.projection.transform.state_order` unconditionally on *every* call,
  live case or fixture; with `VIZ` still `null` (its state when
  `/api/viz` fails), any path that reached it would throw. In practice
  `adoptTrace` (and therefore `updateStepperUI`) is already guarded by
  `if(VIZ)` upstream, so this was inert rather than actively crashing today —
  but a fully wired-looking widget with dead controls and a latent crash the
  moment anything called into it was still the wrong state to leave on
  screen. `geoBoot().catch()` now also does `$('#stepper').remove()`,
  matching the existing `$('#mach').remove()` precedent. Verified by forcing
  `/api/viz` to fail (a monkeypatched `fetch`) and running the real
  `geoBoot().catch()` path end to end: both `#mach` and `#stepper` are
  removed, only `#geo`'s "geometry unavailable" message remains.
