"""Act 3 — the case that converges beautifully to an answer that is wrong.

The Phase 1 circuit has a **unique** steady state everywhere in its envelope.
That was checked, not assumed: a 16-seed multi-start over all 400 sweep cases
found exactly one root every time. So on that circuit a warm start can change
what a run *costs* and never what it *says*, which is a good property to be
able to state — and it means the base circuit cannot demonstrate the failure
mode the verifier exists for.

This module builds the same equations around a **smaller motor** (5 cm3/rev
instead of 32). Nothing else changes. With less torque per bar, the operating
point falls into the Stribeck fold, and the torque balance picks up three
roots: a nearly-stuck one, one on the friction downslope, and a spinning one.
The middle root is *dynamically unstable* — it satisfies the equations to 1e-8
and no machine can ever sit there.

Newton cannot tell the difference. That is the whole point.

    python fold.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import model
import verifier
import sweep
from sweep import sample_cases

D_FOLD = 5.0          # cm^3/rev -- a small motor, ordinary hardware

#: per shaft: its state index, the indices left free when it is held, and the
#: two pressure indices whose difference drives it
SHAFT = {
    "a": {"idx": 3, "free": [0, 1, 2, 4, 5, 6], "dp": (1, 2)},
    "b": {"idx": 6, "free": [0, 1, 2, 3, 4, 5], "dp": (4, 5)},
}


def fold_cases(n: int, seed: int) -> list[dict]:
    return [{**p, "D_mot": D_FOLD} for p in sample_cases(n, seed)]


# --- multi-start root finding ----------------------------------------------

SEEDS = [0.0, 15.0, 40.0, 150.0, 600.0, 1500.0]


def all_roots(p: dict, tol: float = 1e-5) -> list[np.ndarray]:
    """Distinct converged roots found by seeding the shafts across the curve."""
    roots: list[np.ndarray] = []
    for wa in SEEDS:
        for wb in SEEDS:
            x0 = np.array([150.0, 100.0, 20.0, wa, 100.0, 20.0, wb])
            r = model.solve(p, x0=x0)
            if not r["converged"]:
                continue
            x = np.array(r["x"])
            if not any(np.max(np.abs(x - y)) < tol for y in roots):
                roots.append(x)
    return roots


# --- torque characteristic, for the explanatory figure ----------------------

def torque_characteristic(p: dict, w_grid: np.ndarray,
                          shaft: str = "a") -> tuple[np.ndarray, np.ndarray]:
    """Hydraulic torque available vs load torque demanded, sweeping one shaft.

    For each speed the remaining six unknowns are solved, so this is the true
    supply curve of the circuit rather than a sketch. Where the two curves
    cross is a steady state.
    """
    k_torque, _ = model.motor_constants(p)
    cfg = SHAFT[shaft]
    free, (hi, lo) = cfg["free"], cfg["dp"]
    supply, demand = [], []
    x = np.array([150.0, 100.0, 20.0, 300.0, 100.0, 20.0, 300.0])
    for w in w_grid:
        x[cfg["idx"]] = w
        for _ in range(60):
            F = model.residual(x, p)[free]
            if np.max(np.abs(F)) < 1e-9:
                break
            J = model.jacobian(x, p)[np.ix_(free, free)]
            try:
                x[free] += np.linalg.solve(J, -F)
            except np.linalg.LinAlgError:
                break
        supply.append((x[hi] - x[lo]) * k_torque)
        demand.append(model.load_torque(w, p[f"c_load_{shaft}"]))
    return np.array(supply), np.array(demand)


# --- the two policies -------------------------------------------------------

def naive_transfer(p: dict, x0) -> dict:
    """Retrieval warm start with nothing checking it — today's behaviour."""
    r = model.solve(p, x0=x0)
    if r["converged"]:
        r["admissible"] = verifier.Verifier.check_solution(r["x"], p).admit
    return r


#: which state entries are pressures and which are speeds, for the answer diff
PRESSURE_IDX = [0, 1, 2, 4, 5]
SPEED_IDX = [3, 6]

#: the rung the ladder falls back to when the archive is refused or its answer
#: is rejected. ``nominal`` is a guess built from the case setup alone;
#: ``cold`` is the flat start this experiment originally used. Both are
#: archive-free, so neither weakens a refusal -- but see ``run()``: on this
#: circuit the choice decides *which* valid root you land on, not just cost.
FALLBACKS = {
    "nominal": lambda p: model.nominal_start(p),
    "cold": lambda p: model.COLD_START,
}


def guarded_transfer(p: dict, x0, source: dict, distance: float,
                     v: verifier.Verifier, fallback: str = "nominal") -> dict:
    """Verified transfer: gate before, check after, escalate rather than lie."""
    trail = []
    vt = v.check_transfer(p, source, distance)
    trail.append(str(vt))

    attempts = []
    if vt.admit:
        attempts.append(("warm", x0))
    attempts.append((fallback, FALLBACKS[fallback](p)))
    attempts += [("multistart", np.array([150.0, 100.0, 20.0, w, 100.0, 20.0, w]))
                 for w in (600.0, 15.0, 1500.0)]

    spent = 0
    for label, start in attempts:
        r = model.solve(p, x0=start)
        spent += r["iterations"]
        if not r["converged"]:
            trail.append(f"{label}: {r['status']}")
            continue
        vs = v.check_solution(r["x"], p)
        trail.append(f"{label}: {vs}")
        if vs.admit:
            return {**r, "resolved_by": label, "admissible": True, "trail": trail,
                    "refused_transfer": not vt.admit, "gate": vt.rule,
                    "fallback": fallback, "iterations_total": spent}
    return {"converged": False, "status": "no_admissible_root", "iterations": 0,
            "resolved_by": None, "admissible": False, "trail": trail,
            "refused_transfer": not vt.admit, "gate": vt.rule,
            "fallback": fallback, "iterations_total": spent}


# --- experiment -------------------------------------------------------------

def sweep_fold(n: int, seed: int) -> tuple[list[dict], list[dict], dict]:
    """Sweep the fold circuit; return (admissible, rejected, stats).

    The verifier runs at ingest: a converged-but-unstable run is not something
    the archive should ever hand to a future case as a starting point, and a run
    that never converged has no state to hand over at all. Filtering those out
    of the *warm-start* archive is what makes it an asset rather than a
    liability.

    But `rejected` is returned rather than counted, which is the half this
    function used to throw away. On this circuit that is **more than half the
    compute** — an engineer asked for the failed runs to be kept too, on the
    grounds that a run that died is expensive evidence about where
    initialisation is hard. Whether that evidence predicts anything is measured
    in `failure_zone.py`; it is not assumed here, and nothing in the warm-start
    path reads these records.
    """
    kept, rejected = [], []
    for i, p in enumerate(fold_cases(n, seed)):
        r = model.solve(p)
        case_id = f"fold-{i:04d}"
        params = {k: float(v) for k, v in p.items()}

        if not r["converged"]:
            rejected.append({"case_id": case_id, "params": params,
                             "kind": "no_convergence", "detail": r["status"],
                             "iterations": r["iterations"],
                             "residual_inf": r["residual_inf"]})
            continue

        vs = verifier.Verifier.check_solution(r["x"], p)
        if not vs.admit:
            # converged, and to something no machine can sit at -- a different
            # kind of failure from "no answer", and the more interesting one
            rejected.append({"case_id": case_id, "params": params,
                             "kind": "inadmissible", "detail": vs.rule,
                             "iterations": r["iterations"],
                             "residual_inf": r["residual_inf"],
                             "solution": dict(zip(model.STATE_NAMES, r["x"]))})
            continue

        kept.append({
            "case_id": case_id,
            "params": params,
            "solution": dict(zip(model.STATE_NAMES, r["x"])),
            "regime": model.regime(r["x"], p),
            #: the same tangent `sweep.py` records on the base circuit. It
            #: matters more here: on a circuit with three roots the transfer
            #: decides which one Newton walks to, and a start that lands
            #: closer to the *admissible* root is not only cheaper, it is
            #: right more often.
            "sensitivity": sweep.sensitivity_of(r["x"], p),
            "solve": {"start": "cold", "status": r["status"],
                      "iterations": r["iterations"],
                      "residual_inf": r["residual_inf"]},
        })

    stats = {"n": n, "kept": len(kept),
             "rejected_unstable": sum(1 for x in rejected
                                      if x["kind"] == "inadmissible"),
             "failed": sum(1 for x in rejected
                           if x["kind"] == "no_convergence")}
    return kept, rejected, stats


def build_archive(n: int, seed: int) -> tuple[list[dict], dict]:
    """The warm-start archive alone -- unchanged contract for existing callers."""
    kept, _rejected, stats = sweep_fold(n, seed)
    return kept, stats


def run(n_archive: int, n_query: int, out: Path, fig: Path) -> dict:
    records, stats = build_archive(n_archive, seed=11)
    print(f"fold-circuit archive: {stats['kept']}/{stats['n']} kept, "
          f"{stats['rejected_unstable']} rejected as dynamically unstable, "
          f"{stats['failed']} never converged")

    v = verifier.Verifier(records)
    arch_norm = model.normalise(
        np.array([[r["params"][k] for k in model.PARAM_NAMES] for r in records]))
    arch_x = np.array([[r["solution"][k] for k in model.STATE_NAMES] for r in records])

    queries = fold_cases(n_query, seed=77)
    outcomes = {"naive_wrong": 0, "naive_ok": 0, "naive_failed": 0,
                "guarded_ok": 0, "guarded_unresolved": 0, "guarded_refused": 0,
                "naive_iterations": 0, "guarded_iterations": 0,
                # the previous ladder, run alongside so the cost of the swap
                # and the answers it moves are both measured, not asserted
                "guarded_cold_iterations": 0, "answer_compared": 0,
                "answer_differs_from_cold_fallback": 0,
                "max_dp_bar_vs_cold_fallback": 0.0,
                "max_dw_rpm_vs_cold_fallback": 0.0}
    cases, demo = [], None

    for i, p in enumerate(queries):
        vq = model.normalise(model.param_vector(p))
        d = np.linalg.norm(arch_norm - vq, axis=1)
        j = int(np.argmin(d))

        naive = naive_transfer(p, arch_x[j])
        guarded = guarded_transfer(p, arch_x[j], records[j], float(d[j]), v)
        # The fallback rung is not a cost knob. This circuit has several valid
        # operating points, so where the ladder restarts decides *which* one is
        # returned. Run the old flat-start ladder alongside and diff the two
        # answers, so an answer-changing change is a reported number rather
        # than something the audience discovers.
        guarded_cold = guarded_transfer(p, arch_x[j], records[j], float(d[j]), v,
                                        fallback="cold")
        outcomes["guarded_cold_iterations"] += guarded_cold["iterations_total"]

        same_answer = None
        if guarded.get("converged") and guarded_cold.get("converged"):
            dx = np.abs(np.array(guarded["x"]) - np.array(guarded_cold["x"]))
            dp = float(dx[PRESSURE_IDX].max())
            dw = float(dx[SPEED_IDX].max())
            same_answer = dp <= 1e-6 and dw <= 1e-6
            outcomes["answer_compared"] += 1
            outcomes["answer_differs_from_cold_fallback"] += not same_answer
            outcomes["max_dp_bar_vs_cold_fallback"] = max(
                outcomes["max_dp_bar_vs_cold_fallback"], dp)
            outcomes["max_dw_rpm_vs_cold_fallback"] = max(
                outcomes["max_dw_rpm_vs_cold_fallback"], dw)

        if not naive["converged"]:
            outcomes["naive_failed"] += 1
        elif naive["admissible"]:
            outcomes["naive_ok"] += 1
        else:
            outcomes["naive_wrong"] += 1

        if guarded["admissible"]:
            outcomes["guarded_ok"] += 1
        else:
            outcomes["guarded_unresolved"] += 1
        outcomes["guarded_refused"] += bool(guarded["refused_transfer"])
        outcomes["naive_iterations"] += naive.get("iterations", 0)
        outcomes["guarded_iterations"] += guarded["iterations_total"]

        entry = {
            "case_id": f"foldq-{i:04d}", "neighbour_id": records[j]["case_id"],
            "neighbour_distance": float(d[j]),
            "params": {k: float(val) for k, val in p.items()},
            "naive": {"converged": naive["converged"],
                      "iterations": naive.get("iterations"),
                      "residual_inf": naive.get("residual_inf"),
                      "admissible": naive.get("admissible", False),
                      "w_a": naive["x"][3] if naive["converged"] else None,
                      "w_b": naive["x"][6] if naive["converged"] else None},
            "guarded": {"admissible": guarded["admissible"],
                        "resolved_by": guarded["resolved_by"],
                        "gate": guarded["gate"], "trail": guarded["trail"],
                        "iterations_total": guarded["iterations_total"],
                        "w_a": guarded["x"][3] if guarded.get("converged") else None,
                        "w_b": guarded["x"][6] if guarded.get("converged") else None},
            "guarded_cold_fallback": {
                "resolved_by": guarded_cold["resolved_by"],
                "iterations_total": guarded_cold["iterations_total"],
                "admissible": guarded_cold["admissible"],
                "w_a": guarded_cold["x"][3] if guarded_cold.get("converged") else None,
                "w_b": guarded_cold["x"][6] if guarded_cold.get("converged") else None,
                "same_answer": same_answer},
        }
        cases.append(entry)

        # the demo case: naive lands on an unstable root, guarded recovers
        if demo is None and naive["converged"] and not naive["admissible"] \
                and guarded["admissible"]:
            bad = model.stability(naive["x"], p)["unstable_shafts"]
            if not bad:
                continue
            demo = entry
            demo["unstable_shaft"] = bad[0]
            demo["roots"] = [
                {"x": dict(zip(model.STATE_NAMES, r)),
                 "stable": model.stability(r, p)["stable"]}
                for r in all_roots(p)
            ]

    payload = {"archive_stats": stats, "outcomes": outcomes,
               "coverage_radius": v.coverage_radius,
               "n_queries": n_query, "demo": demo, "cases": cases}
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report(outcomes, n_query, demo)
    if demo:
        draw(demo, payload, fig)
    print(f"  -> {out}")
    return payload


def report(o: dict, n: int, demo) -> None:
    print(f"\n{n} fresh fold-circuit cases\n")
    print(f"{'':34} {'naive':>10} {'verified':>10}")
    print(f"{'converged to a valid operating point':34} {o['naive_ok']:>10} "
          f"{o['guarded_ok']:>10}")
    print(f"{'converged to an UNSTABLE root':34} {o['naive_wrong']:>10} {0:>10}")
    print(f"{'no answer':34} {o['naive_failed']:>10} "
          f"{o['guarded_unresolved']:>10}")
    print(f"{'total Newton iterations spent':34} {o['naive_iterations']:>10} "
          f"{o['guarded_iterations']:>10}")
    print(f"\n  transfers refused by the gate: {o['guarded_refused']}")
    print(f"  price of never being silently wrong: "
          f"{o['guarded_iterations'] / max(o['naive_iterations'], 1) - 1:+.0%} solver work")
    if o.get("guarded_cold_iterations"):
        print(f"    (same ladder with the flat start it used before: "
              f"{o['guarded_cold_iterations'] / max(o['naive_iterations'], 1) - 1:+.0%})")

    # An answer-changing change has to be reported as a number, not a caveat.
    diff = o.get("answer_differs_from_cold_fallback", 0)
    if o.get("answer_compared"):
        print(f"\n  vs the flat-start ladder: {diff}/{o['answer_compared']} cases "
              f"resolve to a DIFFERENT operating point")
        if diff:
            print(f"    max |dp| {o['max_dp_bar_vs_cold_fallback']:.1f} bar, "
                  f"max |dw| {o['max_dw_rpm_vs_cold_fallback']:.1f} rev/min")
            print("    Both are stable, both pass the verifier. On this circuit the "
                  "fallback decides")
            print("    WHICH valid operating point you get: the gate promises *a* "
                  "correct answer,")
            print("    not *the* one another starting guess would have found.")
    if demo:
        s = demo["unstable_shaft"]
        print(f"\n  demo case {demo['case_id']}: naive converged in "
              f"{demo['naive']['iterations']} iterations to shaft {s} at "
              f"{demo['naive'][f'w_{s}']:.1f} rev/min -- on the friction downslope")
        for line in demo["guarded"]["trail"]:
            print(f"    {line}")
        print(f"    resolved by {demo['guarded']['resolved_by']} -> shaft {s} at "
              f"{demo['guarded'][f'w_{s}']:.1f} rev/min")


def draw(demo: dict, payload: dict, fig: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    p = demo["params"]
    shaft = demo["unstable_shaft"]
    key = f"w_{shaft}"
    w = np.linspace(0.5, 900, 500)
    supply, demand = torque_characteristic(p, w, shaft)

    f, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 4.8))
    ax1.plot(w, demand, color="#c0392b", label="torque demanded by the load")
    ax1.plot(w, supply, color="#1f77b4", label="torque the circuit can supply")
    seen = set()
    for r in demo["roots"]:
        ws = r["x"][key]
        if any(abs(ws - s) < 1e-3 for s in seen):
            continue
        seen.add(ws)
        ax1.plot([ws], [model.load_torque(ws, p[f"c_load_{shaft}"])],
                 "o" if r["stable"] else "X", ms=11,
                 color="#2e7d32" if r["stable"] else "#c0392b",
                 mec="k", mew=0.8, zorder=5)
    w_bad = demo["naive"][key]
    ax1.annotate("naive warm start\nconverges here", xy=(w_bad,
                 model.load_torque(w_bad, p[f"c_load_{shaft}"])),
                 xytext=(0.42, 0.78), textcoords="axes fraction", fontsize=9,
                 color="#c0392b", arrowprops=dict(arrowstyle="->", color="#c0392b"))
    ax1.set_xscale("symlog", linthresh=30)
    ax1.set_xlabel(f"shaft speed w_{shaft} [rev/min]")
    ax1.set_ylabel("torque [Nm]")
    ax1.set_title(f"A · {demo['case_id']}, shaft {shaft}: the load curve is crossed "
                  "three times\nX = dynamically unstable · O = valid operating point",
                  fontsize=10)
    ax1.legend(fontsize=8, loc="upper right")
    ax1.grid(alpha=0.3)

    o = payload["outcomes"]
    n = payload["n_queries"]
    labels = ["valid operating\npoint", "UNSTABLE root\n(silently wrong)", "no answer"]
    naive = [o["naive_ok"], o["naive_wrong"], o["naive_failed"]]
    guard = [o["guarded_ok"], 0, o["guarded_unresolved"]]
    y = np.arange(3)
    ax2.barh(y - 0.2, naive, height=0.38, color="#c0392b", label="naive retrieval")
    ax2.barh(y + 0.2, guard, height=0.38, color="#1f77b4", label="verified")
    for i, (a, b) in enumerate(zip(naive, guard)):
        ax2.text(a + n * 0.01, i - 0.2, str(a), va="center", fontsize=9)
        ax2.text(b + n * 0.01, i + 0.2, str(b), va="center", fontsize=9)
    ax2.set_yticks(y)
    ax2.set_yticklabels(labels, fontsize=9)
    ax2.invert_yaxis()
    ax2.set_xlabel(f"cases (of {n})")
    ax2.set_title("B · what the two policies actually return", fontsize=10)
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.3, axis="x")

    f.suptitle("Déjà Solve -- the verifier: refusing a transfer the physics does "
               "not justify", fontsize=11)
    f.tight_layout(rect=(0, 0, 1, 0.95))
    fig.parent.mkdir(parents=True, exist_ok=True)
    f.savefig(fig, dpi=160, bbox_inches="tight")
    print(f"  -> {fig}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-archive", type=int, default=300)
    ap.add_argument("--n-query", type=int, default=200)
    ap.add_argument("--out", type=Path, default=Path("fold_results.json"))
    ap.add_argument("--fig", type=Path, default=Path("figs/verifier.png"))
    args = ap.parse_args()
    run(args.n_archive, args.n_query, args.out, args.fig)


if __name__ == "__main__":
    main()
