"""What happens to retrieval when the Case Card has hundreds of parameters.

The circuit here has 7 swept parameters. Real models have hundreds — an engineer
said so, and he is obviously right. The question that matters for this project
is not whether 7 is small; it is **which layer breaks first when it is not 7**.

The realistic situation is not "hundreds of parameters that all matter". It is
hundreds of parameters *recorded*, of which a handful drive any particular
output — the metering valve and the relief setting decide this initialisation,
while the seat material and the bracket thickness are on the same Case Card and
have nothing to do with it. A Case Card carries what the run stated; it cannot
know in advance which entries matter.

So: keep the physics exactly as it is, and grow the *recorded* parameter vector
with entries that are real numbers on the card and inert in the equations. Then
measure retrieval, which is the layer that indexes on that vector.

Three arms at every dimension:

  * ``warm_all``     -- nearest neighbour over all 7 + D recorded parameters.
    This is what a system does when nobody has told it which entries matter.
  * ``warm_physics`` -- nearest neighbour over the 7 that actually drive the
    solve. Constant by construction: it is Phase 1's warm arm, and it is what
    retrieval *could* achieve if it knew.
  * ``nominal``      -- the archive-free guess. Also constant, and the line
    ``warm_all`` is falling towards.

**The favourable assumption is deliberate.** Nuisance entries are drawn uniform
on [0, 1] — exactly the range the real parameters occupy after normalisation —
so they carry no more weight in the distance than a real parameter does. Wider
nuisance would swamp the signal sooner. This is the *best* case for naive
retrieval, and it still goes where it goes.

**And yes, this is textbook.** Distance concentration in high dimensions is not
a discovery. It is, however, the answer to "we have hundreds of parameters" —
being textbook does not stop it deciding whether the system works on a real
model. What the experiment adds is *which* layer it takes down and which it
leaves alone: the physics rules in `dejasolve/verifier.py` never touch the setup vector,
so they are dimension-blind by construction, and the measurement says so rather
than the README claiming it.

    python -m benchmarks.dimensionality
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from dejasolve import model
from dejasolve import verifier
from benchmarks.bench import load_archive
from dejasolve.sweep import sample_cases

#: recorded-but-inert parameters added on top of the 7 real ones. Nested on
#: purpose: the first 10 columns are the same 10 at every larger D, so the
#: sequence is one growing Case Card rather than seven unrelated experiments.
DIMS = (0, 3, 10, 30, 100, 300, 1000)

#: fixed so a card's nuisance entries are properties of that case, not noise
#: redrawn per run
NUISANCE_SEED = 4242

WARM_ALL = "#c0392b"
WARM_PHYSICS = "#1f77b4"
NOMINAL = "#e69f00"


def nuisance(n: int, d_max: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).random((n, d_max))


def cdist(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Euclidean distances between every row of `a` and every row of `b`.

    Via the squared-norm identity rather than broadcasting: at 1000 columns the
    naive (n, m, d) intermediate is most of a gigabyte for no reason.
    """
    d2 = ((a ** 2).sum(1)[:, None] + (b ** 2).sum(1)[None, :] - 2 * (a @ b.T))
    return np.sqrt(np.maximum(d2, 0.0))


def coverage_radius_in(space: np.ndarray, pct: float = 99.0) -> float:
    """The archive's own spacing, measured in whatever space it is indexed in.

    `Verifier` computes this over the 7 real parameters. The coverage rule is a
    *distance* rule, so if retrieval indexes a wider vector the radius has to be
    measured in that same wider space -- otherwise the rule is comparing a
    1000-dimensional distance against a 7-dimensional threshold and refuses
    everything, which says nothing about high dimensions and everything about
    mixing two metrics.
    """
    d = cdist(space, space)
    np.fill_diagonal(d, np.inf)
    return float(np.percentile(d.min(axis=1), pct))


def contrast(dists: np.ndarray) -> float:
    """Relative contrast: (mean - min) / mean, averaged over queries.

    The standard symptom of the curse. At 1.0 the nearest neighbour is far
    closer than average and "nearest" means something; as it approaches 0 every
    archived case is about equally far away and the word stops meaning anything.
    """
    return float(np.mean((dists.mean(axis=1) - dists.min(axis=1)) / dists.mean(axis=1)))


def run(archive_path: Path, n_queries: int, seed: int, out: Path,
        fig_path: Path) -> dict:
    records, arch_norm, arch_states = load_archive(archive_path)
    queries = sample_cases(n_queries, seed)
    # normalise the whole block at once: model.normalise returns 2-D for a
    # single vector, so a list comprehension would give (n, 1, 7)
    q_norm = model.normalise(
        np.array([model.param_vector(p) for p in queries]))

    d_max = max(DIMS)
    arch_nuis = nuisance(len(records), d_max, NUISANCE_SEED)
    q_nuis = nuisance(n_queries, d_max, NUISANCE_SEED + 1)

    v = verifier.Verifier(records)

    # --- the two constant reference arms, solved once ----------------------
    nominal, warm_physics, physics_pick = [], [], []
    for i, p in enumerate(queries):
        d = np.linalg.norm(arch_norm - q_norm[i], axis=1)
        j = int(np.argmin(d))
        physics_pick.append(j)
        nom = model.solve(p, x0=model.nominal_start(p))
        warm = model.solve(p, x0=arch_states[j])
        nominal.append(nom)
        warm_physics.append(warm)

    def arm(rs: list[dict]) -> dict:
        conv = [r for r in rs if r["converged"]]
        return {"converged": len(conv), "failed": len(rs) - len(conv),
                "total_iterations": int(sum(r["iterations"] for r in conv)),
                "mean_iterations": float(np.mean([r["iterations"] for r in conv]))}

    rows = []
    for d in DIMS:
        a = np.hstack([arch_norm, arch_nuis[:, :d]])
        q = np.hstack([q_norm, q_nuis[:, :d]])

        dists = cdist(q, a)
        picks = dists.argmin(axis=1)

        # The coverage rule is re-derived in this space, so it is measuring the
        # archive's spacing against query distances in the same units. Every
        # other gate-1 rule reads the 7 real parameters and the source case's
        # recorded regime, and is therefore independent of the card's width by
        # construction -- which is the asymmetry the experiment exists to show.
        v.coverage_radius = coverage_radius_in(a)

        warm_all, gate = [], {}
        for i, p in enumerate(queries):
            j = int(picks[i])
            warm_all.append(model.solve(p, x0=arch_states[j]))
            verdict = v.check_transfer(p, records[j], float(dists[i, j]))
            gate[verdict.rule] = gate.get(verdict.rule, 0) + 1

        rows.append({
            "extra_parameters": d,
            "recorded_parameters": d + len(model.PARAM_NAMES),
            "warm_all": arm(warm_all),
            "same_neighbour_as_physics": int(sum(
                int(picks[i]) == physics_pick[i] for i in range(n_queries))),
            "relative_contrast": contrast(dists),
            "coverage_radius": v.coverage_radius,
            "gate_verdicts": gate,
        })

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "archive_size": len(records),
        "n_queries": n_queries,
        "real_parameters": len(model.PARAM_NAMES),
        "nuisance": {
            "distribution": "uniform [0, 1], the range the real parameters "
                            "occupy after normalisation -- the favourable case",
            "seed": NUISANCE_SEED,
            "nested": True,
        },
        "reference": {
            "nominal": arm(nominal),
            "warm_physics": arm(warm_physics),
        },
        "by_dimension": rows,
        "crossover": crossover(rows, arm(nominal)["mean_iterations"]),
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    draw(payload, fig_path)
    return payload


def crossover(rows: list[dict], nominal_mean: float) -> dict:
    """The number the engineer actually asked for: when does this stop working?"""
    for r in rows:
        if r["warm_all"]["mean_iterations"] >= nominal_mean:
            return {"extra_parameters": r["extra_parameters"],
                    "recorded_parameters": r["recorded_parameters"],
                    "note": "first tested width at which naive retrieval stops "
                            "beating the archive-free nominal guess"}
    return {"extra_parameters": None,
            "note": f"naive retrieval still beat the nominal guess at every "
                    f"tested width, up to {max(DIMS)} extra parameters"}


def draw(payload: dict, out: Path) -> None:
    rows = payload["by_dimension"]
    xs = [r["recorded_parameters"] for r in rows]
    ys = [r["warm_all"]["mean_iterations"] for r in rows]
    nom = payload["reference"]["nominal"]["mean_iterations"]
    phys = payload["reference"]["warm_physics"]["mean_iterations"]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15.5, 4.4))

    ax1.axhline(nom, color=NOMINAL, ls="--", lw=1.6,
                label=f"nominal guess, no archive ({nom:.2f})")
    ax1.axhline(phys, color=WARM_PHYSICS, ls="--", lw=1.6,
                label=f"retrieval on the 7 that matter ({phys:.2f})")
    ax1.plot(xs, ys, "o-", color=WARM_ALL, lw=2,
             label="retrieval on every recorded parameter")
    ax1.set_xscale("log")
    ax1.set_xlabel("parameters on the Case Card (7 real + inert)")
    ax1.set_ylabel("mean Newton iterations")
    ax1.set_title("Naive retrieval degrades; the physics does not move")
    ax1.legend(fontsize=8, loc="lower right")
    ax1.grid(alpha=.25)

    ax2.plot(xs, [r["relative_contrast"] for r in rows], "o-",
             color=WARM_ALL, lw=2)
    ax2.set_xscale("log")
    ax2.set_xlabel("parameters on the Case Card")
    ax2.set_ylabel("relative contrast  (mean - min) / mean")
    ax2.set_title('How much "nearest" still means')
    ax2.grid(alpha=.25)

    # --- C: the one that matters -------------------------------------------
    # Retrieval stops finding the right neighbour long before anything
    # complains, and the distance-based gate keeps waving it through -- because
    # the same concentration that destroyed the signal also inflated the radius
    # it is checked against. A distance threshold cannot detect the failure of a
    # distance metric.
    n = payload["n_queries"]
    same = [100 * r["same_neighbour_as_physics"] / n for r in rows]
    admitted = [100 * r["gate_verdicts"].get("ok", 0) / n for r in rows]
    ax3.plot(xs, admitted, "o-", color=NOMINAL, lw=2,
             label="admitted by the distance gate")
    ax3.plot(xs, same, "o-", color=WARM_PHYSICS, lw=2,
             label="same neighbour as physics-only retrieval")
    ax3.set_xscale("log")
    ax3.set_ylim(-4, 104)
    ax3.set_xlabel("parameters on the Case Card")
    ax3.set_ylabel("% of 200 queries")
    ax3.set_title("The gate cannot see retrieval failing")
    ax3.legend(fontsize=8, loc="center right")
    ax3.grid(alpha=.25)

    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def report(payload: dict) -> None:
    ref = payload["reference"]
    print()
    print(f"archive {payload['archive_size']} cases, {payload['n_queries']} queries, "
          f"{payload['real_parameters']} real parameters")
    print(f"reference: nominal {ref['nominal']['mean_iterations']:.2f} iterations, "
          f"retrieval on the real 7 {ref['warm_physics']['mean_iterations']:.2f}")
    print()
    print(f"{'card width':>11}{'mean iters':>12}{'vs nominal':>12}"
          f"{'same pick':>11}{'contrast':>10}")
    for r in payload["by_dimension"]:
        m = r["warm_all"]["mean_iterations"]
        rel = 100 * (1 - m / ref["nominal"]["mean_iterations"])
        print(f"{r['recorded_parameters']:>11}{m:>12.2f}{rel:>11.1f}%"
              f"{r['same_neighbour_as_physics']:>10}/{payload['n_queries']}"
              f"{r['relative_contrast']:>10.3f}")
    c = payload["crossover"]
    print()
    print(f"crossover: {c['note']}"
          + (f"  -> {c['recorded_parameters']} recorded parameters"
             if c.get("recorded_parameters") else ""))

    print()
    print("gate-1 verdicts, which are written in terms of the real parameters:")
    for r in payload["by_dimension"]:
        print(f"  {r['recorded_parameters']:>5} params "
              f"(coverage radius {r['coverage_radius']:.2f}): {r['gate_verdicts']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=Path("data/archive/cases.jsonl"))
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--seed", type=int, default=99,
                    help="must match benchmarks/bench.py so the reference arms line up")
    ap.add_argument("--out", type=Path, default=Path("results/dimensionality_results.json"))
    ap.add_argument("--fig", type=Path, default=Path("results/figs/dimensionality.png"))
    args = ap.parse_args()
    report(run(args.archive, args.queries, args.seed, args.out, args.fig))
    print()
    print(f"wrote {args.out} and {args.fig}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
