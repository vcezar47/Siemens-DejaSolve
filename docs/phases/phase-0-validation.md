# Phase 0 — Validate + scaffold

**Planned:** Tue 11 – Thu 13 Aug 2026 · **Closed:** Sun 16 Aug 2026
**Gate:** direction confirmed by a mentor → ✅ met

The point of this phase was to spend three days finding out whether the idea
was already a shipped feature, rather than seventeen days building something
that exists. It also had to settle which Simcenter vocabulary to speak.

## What was done

Sent the validation message (plan §8) on 11 Aug with three questions, the third
being a deliberate kill-switch: *if this already exists in Simcenter, tell me
before I start.* Answers came back 12 Aug and were absorbed into the plan on
16 Aug as §0.

## The answers, and what each one changed

### Q3 — "does this already exist?" → not a kill switch, but the claim was wrong

> *"Cred că depinde de solver și de cât de avansat este, dar da, unele asta fac.
> Păstrarea unor info utile din simulări cu succes ar putea să fie o chestie
> faină și care să optimizeze fluxul."*

Two halves, and both mattered.

**A correction.** Some solvers do reuse state. Any sentence of the form
*"nobody reuses previous solutions"* is false and would have been corrected in
the room by someone who owns that code.

**An endorsement.** She described the archive layer back unprompted — keeping
useful information from successful simulations, to optimise the flow. That is a
mentor independently restating Layers 1–2 as a good idea.

**Decision:** narrow the claim rather than retreat from it. The wording locked
for all future material:

> Warm-starting is a **solver** feature. It works inside one session, on a run
> a human already picked. What no solver does is look across hundreds of
> finished runs it has never seen, decide **which one** is physically closest,
> and prove that reusing it is **legitimate**. Déjà Solve sits *above* the
> solver, not inside it.

Consequence: the "missing arrow" is retrieval + verification, not warm-start.
Plan §2 bullet 2 was rewritten to concede the solver-side mechanism *first*,
before anyone raises it.

### Q1 — which product lines at Brașov? → free choice

> *"Toate sunt folosite, depinzând de divizie, deci alege ce vrei."*

A constraint disappeared, which is a trap: an open choice can absorb days.

**Decision — locked, not deliberated:** Amesim is the anchor vocabulary.
1. DAE initialisation failure is an Amesim-shaped problem; STAR-CCM+ does not
   fail that way.
2. Study Manager sweeps *are* the demo.
3. The warm-start object stays a small state vector, so mesh-to-mesh mapping —
   already declared out of scope — cannot creep back in.
4. A faithful mock is a few hundred lines of numpy, buildable immediately.

PhysicsAI stays the AI arrow; STAR-CCM+ gets exactly one citation as prior art
for manual previous-solution init.

### Q2 — why would an engineer *not* want this? → deflected into something better

> *"Nu, ce cred este poate totuși că ar fi fain să luăm legătura cu unul doar ca
> să îți mai dea niște 'cerințe utile'? Din punct de vedere ingineresc."*

She did not answer, and offered an engineer instead.

**Decision:** accept immediately. The objection list is the only part of the
plan that cannot be validated alone — Act 3 of the demo rests on a claim about
what engineers distrust, and that claim is currently a guess. Reply and an
ordered question list are in plan §8b. The interview floats: whenever it lands
it pre-empts that day's coding block.

**Guardrail set now, before the conversation happens:** requirements from it
feed the verifier rules and the Case Card schema only. A fourth layer, if one
is described, goes on the next-steps slide.

## Scaffold

Repo created as a private GitHub repo (`Siemens-DejaSolve`). No Docker, no
index service, no UI — those produce no number and were explicitly deferred
past Phase 1.

## Cost

Two days of the original 17 were spent before Phase 1 began, and the buffer was
declared gone. Phase 1 then landed two days early and gave them back.

## Open at close of phase

- The engineer interview has not happened yet — highest-value outstanding item.
- The kill-switch answer was "some solvers do this," which is *softer* than a
  clean no. If the engineer says the selection layer also exists somewhere, that
  is the real kill switch, and it is better to hear it in an interview than in
  the Q&A.
