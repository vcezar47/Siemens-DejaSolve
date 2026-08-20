# Phase 2b — The failure archive

**Built:** Thu 20 Aug 2026 · **Gate:** does keeping the failed runs predict anything? → ✅ **yes, but not the
thing it would have been natural to use it for**
Reproduce with `python failure_zone.py`, or as *Phase 2b* inside `python run_all.py`.

From the engineer interview (§0b): they asked for **both successful and failed runs** to be in the archive.
The reasoning was better than the code's: a run that died is expensive evidence about *where* initialisation
is hard, and reducing it to a tally throws that away. `sweep.py` was collecting failures and discarding them
into a count; `fold.build_archive` was worse, dropping **165 of 300** — more than half the compute — behind a
comment claiming that filtering is what makes the archive an asset.

## What was built

- `sweep.py` writes `archive/failures.jsonl` alongside `cases.jsonl` — a separate file, because everything
  downstream reads the archive expecting a converged `solution` on every line and a record without one would
  be a landmine in every consumer.
- `fold.sweep_fold()` returns `(admissible, rejected, stats)` and `build_archive` is now a thin wrapper over
  it, so **every existing caller sees a bit-identical archive and identical stats** — asserted, not assumed.
  Rejects are typed: `no_convergence` (164) and `inadmissible` (1, converged onto something no machine can
  sit at — a different and more interesting kind of failure).
- `failure_zone.py` tests the obvious candidate rule, in the same normalised setup space retrieval already
  uses:

      warn if   d(nearest failed) < d(nearest succeeded)

Two targets, because *"goes badly"* means two different things:

- **`hard_case`** — the query's own cold solve never converges. This is the engineer's framing: *tell me this
  run is likely to die.*
- **`bad_transfer`** — naive retrieval from the nearest archived case returns no valid answer.

## Measured — fold circuit, 135 succeeded / 165 failed, 200 queries

| | `hard_case` | `bad_transfer` |
|---|---|---|
| base rate | 56.0% | 26.5% |
| P(bad \| rule fired) | **74.8%** | 30.4% |
| recall | 76.8% | 66.0% |
| lift over base rate | **1.34x** | 1.15x |
| **AUC** | **0.770** | 0.633 |

## The control, which is the point of the experiment

Failures cluster where the circuit is hard — and successes are **sparse in exactly the same places**. So a
positive result could mean nothing more than *"you are far from anything solved"*, which the **coverage rule
already sees**. If that were the whole story, the honest conclusion would be "keep the files, skip the rule".

Both controls are computed on every run so the question cannot quietly stop being asked:

| score | `hard_case` AUC | `bad_transfer` AUC |
|---|---|---|
| distance to nearest **success** only *(what coverage already sees)* | 0.650 | 0.585 |
| distance to nearest **failure** only | 0.740 | 0.622 |
| **the candidate rule** (success − failure) | **0.770** | 0.633 |

**0.650 → 0.770. The failures carry information the successes do not.** The engineer was right, and the
result is not an artefact of sparsity.

## The finding, and why the rule is *not* being added to the gate

**Failure-proximity predicts whether the case is hard. It barely predicts whether a transfer is legitimate.**
AUC 0.770 against 0.633, and a lift of 1.34x against 1.15x. Those are different questions and the archive
answers only one of them.

So this is **advisory information for the engineer, not a rule in the transfer gate** — which lands exactly on
the line §0b already drew: the engineer decides what to do with a risk, the system decides what is a fact.
Failure-proximity is a risk worth mentioning and not a fact worth acting on.

Two further reasons it stays out of `verifier.py` for now:

1. **A 56% base rate.** On a circuit where more than half the runs die from cold, *"this one might die"* is
   not news. The rule beats always-warning on precision (74.8% against 56%) at 76.8% recall, and the AUC says
   the ranking is real — but the practical value depends on a base rate the demo circuit does not have.
2. **It would do nothing in the demo.** The base circuit fails 5 times in 400. The rule fires 3 times in 200
   there and catches 0 of the 4 hard cases. Shipping a gate rule that is inert in the only circuit the demo
   runs would be a feature that exists to be described rather than to work.

**A failure archive is only worth consulting where runs actually fail** — which is an honest scoping sentence,
and it is also the answer to *"would this help us?"*: it depends on your failure rate, and here is the number
at which it starts paying.

## Rejected

- **Adding the rule to `check_transfer` anyway.** It was requested, it sounds sensible, and it does not
  predict transfer legitimacy. Shipping it would have been the third plausible claim this project failed to
  support — the difference is that this time the measurement happened before the code.
- **Flagging failures inside `cases.jsonl`.** Every consumer reads that file expecting a converged state.
- **Reporting the base-circuit result as evidence.** 5 failures is below the threshold for a conclusion;
  `failure_zone.py` carries `MIN_FAILURES = 30` and prints `UNDERPOWERED` rather than letting a reader draw
  one anyway.
