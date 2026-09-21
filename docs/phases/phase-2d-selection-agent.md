# Phase 2d — The selection agent, and four rankers that all lose

**Built:** Thu 20 Aug 2026 · **Gate:** can anything rank the candidates better than distance? → ✅ measured,
**and the answer is no — including the agent**
`python -m benchmarks.agent_select` (ceiling, floor and physics arms, no GPU) ·
`python -m benchmarks.agent_select --model granite4` (the model arm).

`experiments/topk.py` found that walking deeper into the archive *by distance* does not pay. That is a statement about the
**ordering**, and this project already knows distance is weak — setup distance predicts transfer cost at
r = 0.18 (§6b). So the open question was whether a better ordering of the same candidates pays, and a
selection agent is the obvious thing to try.

## The order of operations was the design decision

**The ceiling was measured before any GPU time.** Solving all k candidates gives the pick a perfect ranker
would have made, which bounds what *any* ranker could win. Had it come back at 1%, the question would have
been closed without a single inference call and without blaming a model.

It came back at 12–14%, so the experiment was worth running:

| circuit | distance | oracle | headroom | distance already optimal |
|---|---|---|---|---|
| base | 984 iters | 868 | **11.8%** | 124 / 198 |
| fold | 1589 iters, 11 inadmissible | 1361, 5 inadmissible | **14.3%** | 81 / 165 |

**And a floor was built before the result was read.** A ranker that contributes nothing still lands *somewhere*
between distance and oracle, so "the agent scored 1038" is unreadable without knowing where no opinion lands.
`random_floor` picks uniformly among the admitted candidates.

## Four rankers, k = 5, the verifier holding the veto throughout

Every arm chooses only among candidates gate 1 already admitted, so no ranker — model included — can
authorise a transfer the physics refuses. **The agent proposes, the verifier disposes**; the worst a bad
ranking can cost is iterations.

| arm | base (200) | fold (200) |
|---|---|---|
| **oracle** — solves every candidate, not achievable | **868** | **1361**, 5 inadmissible |
| **distance** — today's behaviour | 984 | 1589, 11 |
| **physics** — ranked by estimated regime match | 996 | 1589, 11 |
| **random** — no opinion at all | 1018 | 1584, 13 |
| **granite4** (3.4B) | **1038** | 1575, 10 |
| **qwen2.5:7b** (7.6B, 40-query subset) | 205 vs distance 198, random 207 | 319 vs distance 303, random 314 |

**Zero parse failures on every run.** The models answered cleanly and chose badly — this is not a plumbing
result.

## What it says

**1. Both models rank at or below chance.** granite4 lands *below* the random floor on the base circuit
(1038 against 1018). qwen2.5:7b is below the floor on base and worse than it on fold. They disagreed with
distance on most queries — 146/200 and 111/200 — so they were making real choices, and the choices carried no
information.

**2. The bigger model is not better, so it is the task and not the size.** That control is the entire reason
qwen was run at all: without it, "you only used a 3.4B model" is an unanswerable objection to a null result.

**3. The physics ranker fails for a reason worth understanding.** On the fold circuit it is *byte-identical*
to distance — 1589 iterations, 11 inadmissible — because **the gate already uses regime match to decide
admission**. Among admitted candidates the regime agreement is constant, every score ties, and the tie-break
falls through to distance. The information had already been consumed one layer down. A signal cannot be spent
twice.

**4. On the fold circuit, distance itself is no better than chance** — 1589 against a random floor of 1584.
Exactly what r = 0.18 predicts, now visible as an ordering rather than a correlation.

**5. The headroom is real and nothing cheap reaches it.** The oracle is 12–14% below every other arm, and it
gets there by *solving each candidate*. What would capture it is a predictor of **transfer cost**, which is
precisely the quantity §6b measured distance as failing to predict. That is a different project, and naming
it is more honest than gesturing at a better prompt.

## Say it this way

> *"I built the agent. I measured the ceiling first so I would know whether it could possibly help, and a
> random floor so I would know whether it did anything at all. Two local models, one 3.4B and one 7.6B, both
> ranked at or below random — and so did ranking by physics, because the gate had already used that
> information to decide admission. The 12% that a perfect ranker would win is real, and nothing I tried could
> see it."*

That is a better slide than a working agent would have been, and it is the fifth claim this project has
tested and declined.

## The model arm is not bit-reproducible, and that is stated rather than hidden

`temperature: 0` and a fixed `seed` were set, and the run was still not identical. Two granite4 runs over the
same 200 queries agreed with distance 54 and 55 times, and captured -47% and -49% of the headroom. The
conclusion does not move -- both are below the random floor -- but the numbers do, at the first decimal.

So the model arm **writes its own results file and is excluded from `run_all.py`**, which is the reproducer
and has to give the same answer twice. The deterministic arms -- oracle, distance, physics, random -- are in
`run_all.py` and are exact. Quote the model numbers as "at or below chance", not to three significant figures.

## Rejected

- **Reporting the agent against distance alone.** Without the random floor, granite4's 1038 against 984 reads
  as "close, needs prompt work". Against a floor of 1018 it reads as negative signal, which is what it is.
- **Testing only granite4.** The size objection would have been fatal to the null and trivially avoidable.
- **Giving the model `estimate_regime`'s output.** That is the gate's own answer; handing it over would test
  reading comprehension rather than whether a model can infer regime from setup.
- **Letting the model override a gate refusal.** It only ever sees admitted candidates. A ranker with the
  power to admit is not a ranker.
- **A HuggingFace cross-encoder** (`bge-reranker-v2-m3`, `ms-marco-MiniLM`). Reranks textual relevance, and
  these candidates differ by physics rather than prose — plus torch and sentence-transformers against an image
  that ships four wheels.
- **Iterating the prompt until it won.** With a random floor in place, prompt-tuning toward a 12% target on
  200 fixed queries is fitting the test set, and the result would not survive a different archive.
