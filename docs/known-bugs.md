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

**Status:** C1, C2, M1, M2, M3 and M4 are **fixed** — see the resolution note on
each. **M5 was not a bug** and has been withdrawn; the endpoint it called dead
has a live consumer. **M6 is won't-fix** by decision: this is a desktop demo.
Everything under Minor still stands.

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

### N2 — The breakaway gate refuses any source case with mixed shaft states

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

### N3 — The 18 promoted constants cannot be read from any artifact

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

### N4 — "Show the retrieved pair" leaves the hand-picked tile selected

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

### N5 — Three uncapped `requestAnimationFrame` loops, ~12 ms of JS per frame

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

### N6 — `prefers-reduced-motion` does not stop the animations that actually move

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

### N7 — Content columns do not line up

**Verified** at 1280 px wide. `main` is full-bleed with `padding:20px 26px`, so its
panels start at x = 26. `.geo` / `.mach` are `max-width:1180px; margin:… auto`
with `padding:0 18px`, so they start at x = 43 and end at 1223 against `main`'s
1265. Every section below the fold is inset 17 px from the two above it.

### N8 — The status hint is wiped by the health poll

**Verified.** `static/index.html:494` (`explain`), `:510` (`refreshHealth`)

`loadFile()` writes `loaded <name> (n kB)` into `#hint`. `refreshHealth()` runs on
a 15 s interval and on window focus, and calls `explain()`, which unconditionally
overwrites `#hint` with the backend description. Confirmed: set the hint, call
`refreshHealth()`, the confirmation is gone. So the only feedback that a dropped
or picked file was read disappears within fifteen seconds.

### N9 — `AuroraArchive.nearest()` can raise `StopIteration`, and reconnects per request

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

### N10 — Dead code and unescaped interpolation in `draw()`

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

### N11 — `PSCALE` is fixed at boot, so a high-pressure live case saturates

**By inspection.** `static/index.html:941` (`renderTiles`)

`PSCALE` is computed once from the contact-sheet tiles plus the fixture pair
(measured: 258.3 bar) and is never recomputed in `adoptTrace`. `ramp()` clamps
its argument to 1, so any analysed case with `p1 > 258` renders every pipe at the
top of the colour ramp and is visually indistinguishable from any other
high-pressure case. `p_crack` alone goes to 260 bar in `PARAM_BOUNDS`, and `p1`
sits above `p_crack` whenever the relief is cracked, so this is reachable.

### N12 — Assorted smaller items

* `casecard.py:117` — `"bara"` and `"barg"` both map to a factor of 1.0. The
  model works in gauge pressure (`P_TANK`), so an artifact stating `bara` is
  read one bar high with no complaint.
* `casecard.py:125` — `normalise_unit` silently returns the value unconverted
  for any unit it does not recognise (`kg/dm^3` is absent while `kg/dm3` is
  present, for instance). A misread unit becomes a plausible-looking number,
  which is the exact failure mode the Units gate exists to catch — and the Units
  gate only sees the already-converted value.
* `ingest.py:89` — `if canon is None or canon in params: continue` means the
  *first* occurrence of a key wins. A log that states a value and then corrects
  it later keeps the superseded one.
* `ingest.py:513` — `ingest_hybrid` copies `model_side.notes` onto the card even
  when the model contributed nothing, including the "[dropped …]" note
  `verify_provenance` appends about fields that were never used.
* `app.py:90` — `AnalyseRequest.text` has no `max_length`. A large paste runs the
  full parser and, on the ollama path, a 280 s inference, with no bound.
* `app.py:70` — `_mirror_audit_to_dynamo` uses `print()` for its failure path
  rather than a logger, so under uvicorn the message lands on stdout with no
  level or timestamp.
* `static/index.html:1749` — `geoBoot().catch()` removes `#mach` when
  `/api/viz` is unavailable, but `#stepper` and `#flow` are left in the DOM. Since
  `stepperBoot()` is only reached from the tail of `machBoot()` (itself the tail
  of `geoBoot()`), the "Newton Convergence & Fluid Dynamics Studio" renders in
  full — tabs, slider, Play button — with no event handlers attached to any of
  it. Every control is inert and nothing says why.
