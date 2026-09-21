"""The same measurement on a 25-parameter circuit, where the machines differ.

§6g answered "real models have hundreds of parameters" by widening the *index*
with entries that are inert in the equations. This answers the other half of it,
which is harder and more interesting: what happens when the extra parameters are
**real**, drive the physics, and describe *different hardware*.

`model.HARDWARE` promotes 18 circuit constants -- discharge coefficient, pump
leakage, relief band, and per branch the motor displacement, return restriction,
cross-port leakage, Coulomb and breakaway torque, Stribeck velocity and viscous
drag. With the 7 swept parameters that is **25 physical parameters**, and the two
branches are no longer forced to be the same motor.

**The realistic archive is not 400 unique machines.** It is a handful of designs
with many operating cases each -- which is exactly the loop §0b describes:
concept, then prototyping with ~25 vehicles, then series. So the sweep here draws
a small number of **machine variants** and many **operating points** on each:

    hardware   -> defines the machine   -> a few discrete variants
    operating  -> defines the run       -> continuous, many per variant

That split is what makes the experiment worth running, because it separates two
things the 7-parameter circuit could not tell apart:

  * **warm_naive**  -- nearest neighbour over all 25 parameters, gate ignored.
    This is what a similarity search does when nobody has told it that some
    parameters describe the machine and others describe the run. It will happily
    hand a state from one machine to another.
  * **warm_gated**  -- the same retrieval with `check_transfer` enforced, so a
    source case on different hardware is refused as a category error and the
    fallback is the archive-free nominal guess.

The question is what the gate is worth once hardware genuinely varies. On the
7-parameter circuit the `hardware` rule was unreachable -- every case was the
same machine -- so it has never been measured. This measures it.

Separate file and separate results, like `benchmarks/surrogate.py` and `benchmarks/fold.py`: nothing
here touches `results.json` or the phase-1 summary hash.

    python -m benchmarks.wide_sweep
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from dejasolve import model
from dejasolve import verifier
from dejasolve.sweep import latin_hypercube
#: moved to dejasolve/model.py, next to the `HARDWARE` defaults it is a spread around --
#: `casecard.validate()` needed the same numbers for a second purpose (catching
#: a misread unit on ingest) and a second copy was the wrong way to share them.
from dejasolve.model import HARDWARE_SPREAD


def make_variants(n: int, seed: int) -> list[dict]:
    """`n` machine designs. Variant 0 is the nominal machine, deliberately.

    Keeping the stock circuit in the population means the wide experiment still
    contains the one every other measurement in this project was taken on.
    """
    rng = np.random.default_rng(seed)
    variants = [{k: float(v) for k, v in model.HARDWARE.items()}]
    for _ in range(n - 1):
        variants.append({
            k: float(model.HARDWARE[k]) * rng.uniform(*HARDWARE_SPREAD[k])
            for k in model.HARDWARE
        })
    return variants


def make_cases(n: int, seed: int, variants: list[dict],
               tolerance: float = 0.0) -> list[dict]:
    """Operating points spread over the machine variants, round-robin.

    `tolerance` is per-case manufacturing scatter on the hardware: two units of
    the same design are never bit-identical, and assuming they are is what makes
    a same-machine result look trivially easy. At 0.0 every unit of a variant is
    exactly alike, which is the flattering case and the one to distrust.
    """
    rng = np.random.default_rng(seed)
    u = latin_hypercube(n, len(model.PARAM_NAMES), rng)
    lo = np.array([model.PARAM_BOUNDS[k][0] for k in model.PARAM_NAMES])
    hi = np.array([model.PARAM_BOUNDS[k][1] for k in model.PARAM_NAMES])
    scaled = lo + u * (hi - lo)
    out = []
    for i, row in enumerate(scaled):
        v = i % len(variants)
        hw = variants[v]
        if tolerance:
            hw = {k: val * float(1.0 + rng.normal(0.0, tolerance))
                  for k, val in hw.items()}
        out.append({**dict(zip(model.PARAM_NAMES, row)), **hw, "_variant": v})
    return out


def wide_vector(p: dict) -> np.ndarray:
    """All 25 parameters, each normalised by its own range."""
    vals, lo, hi = [], [], []
    for k in model.PARAM_NAMES:
        vals.append(p[k])
        lo.append(model.PARAM_BOUNDS[k][0])
        hi.append(model.PARAM_BOUNDS[k][1])
    for k, (f_lo, f_hi) in HARDWARE_SPREAD.items():
        d = float(model.HARDWARE[k])
        vals.append(p.get(k, d))
        lo.append(d * f_lo)
        hi.append(d * f_hi)
    vals, lo, hi = np.array(vals), np.array(lo), np.array(hi)
    return (vals - lo) / np.maximum(hi - lo, 1e-30)


def _arm(rs: list[dict]) -> dict:
    conv = [r for r in rs if r["converged"]]
    return {"converged": len(conv), "failed": len(rs) - len(conv),
            "total_iterations": int(sum(r["iterations"] for r in conv)),
            "mean_iterations": (float(np.mean([r["iterations"] for r in conv]))
                                if conv else None)}


def run(n_variants: int, n_archive: int, n_query: int, out: Path,
        tolerance: float = 0.0) -> dict:
    variants = make_variants(n_variants, seed=5)
    archive_cases = make_cases(n_archive, seed=1, variants=variants,
                               tolerance=tolerance)
    queries = make_cases(n_query, seed=99, variants=variants,
                         tolerance=tolerance)

    records, arch_vecs, arch_states = [], [], []
    for i, p in enumerate(archive_cases):
        r = model.solve(p)
        if not r["converged"]:
            continue
        records.append({"case_id": f"wide-{i:04d}", "variant": p["_variant"],
                        "params": {k: float(v) for k, v in p.items()
                                   if not k.startswith("_")},
                        "solution": dict(zip(model.STATE_NAMES, r["x"])),
                        "regime": model.regime(r["x"], p)})
        arch_vecs.append(wide_vector(p))
        arch_states.append(r["x"])
    arch_vecs = np.array(arch_vecs)
    arch_states = np.array(arch_states)

    v = verifier.Verifier(records)
    # The coverage rule is a *distance* rule, so its radius has to be measured
    # in the space retrieval actually indexes. `Verifier` derives it over the 7
    # swept parameters; leaving it there while passing 25-dimensional distances
    # compares a 25-D distance against a 7-D threshold and refuses on a unit
    # mismatch -- the same trap `dimensionality.coverage_radius_in` exists to
    # prevent, and it caught this file too.
    d_arch = np.linalg.norm(arch_vecs[:, None, :] - arch_vecs[None, :, :], axis=-1)
    np.fill_diagonal(d_arch, np.inf)
    v.coverage_radius = float(np.percentile(d_arch.min(axis=1), 99.0))
    coverage_radius_7d = verifier.Verifier(records).coverage_radius

    cases = []
    for p in queries:
        d = np.linalg.norm(arch_vecs - wide_vector(p), axis=1)
        j = int(np.argmin(d))
        src = records[j]
        cross_machine = src["variant"] != p["_variant"]

        verdict = v.check_transfer(p, src, float(d[j]))
        cold = model.solve(p)
        nom = model.solve(p, x0=model.nominal_start(p))
        naive = model.solve(p, x0=arch_states[j])
        gated = naive if verdict.admit else nom

        cases.append({
            "variant": p["_variant"], "neighbour_variant": src["variant"],
            "cross_machine": bool(cross_machine),
            "gate": verdict.rule, "admitted": bool(verdict.admit),
            "cold": cold, "nominal": nom, "warm_naive": naive,
            "warm_gated": gated,
        })

    # Did the state actually come from another machine, and did anyone notice?
    cross = [c for c in cases if c["cross_machine"]]
    caught = [c for c in cross if c["gate"] == "hardware"]
    gate_counts: dict[str, int] = {}
    for c in cases:
        gate_counts[c["gate"]] = gate_counts.get(c["gate"], 0) + 1

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hardware_rel_tol": verifier.HARDWARE_REL_TOL,
        "parameters": {"swept": len(model.PARAM_NAMES),
                       "hardware": len(model.HARDWARE),
                       "total": len(model.PARAM_NAMES) + len(model.HARDWARE)},
        "variants": n_variants,
        "hardware_tolerance": tolerance,
        "archive": {"attempted": n_archive, "kept": len(records)},
        "n_queries": len(cases),
        "cross_machine": {
            "nearest_neighbour_was_another_machine": len(cross),
            "caught_by_the_hardware_rule": len(caught),
            "missed": len(cross) - len(caught),
        },
        "gate_verdicts": gate_counts,
        "coverage_radius": {"in_25d": v.coverage_radius,
                            "in_7d_would_have_been": coverage_radius_7d},
        "arms": {name: _arm([c[name] for c in cases])
                 for name in ("cold", "nominal", "warm_naive", "warm_gated")},
    }
    if out is not None:
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


#: scatter levels the gate is scanned over. The table this produces is the
#: finding, so it belongs in the results file rather than in three separate
#: invocations somebody has to remember to run.
SCAN_TOLERANCES = (0.0, 0.02, 0.05)


def tolerance_scan(n_variants: int, n_archive: int, n_query: int) -> list[dict]:
    """How the hardware rule behaves as units of one design stop being identical.

    Deliberately smaller than the main run: this measures gate verdicts, not
    iteration counts, and a scan that doubled the reproducer's runtime would be
    the first thing somebody deletes.
    """
    rows = []
    for tol in SCAN_TOLERANCES:
        r = run(n_variants, n_archive, n_query, None, tolerance=tol)
        rows.append({"tolerance": tol,
                     "admitted": r["gate_verdicts"].get("ok", 0),
                     "refused_hardware": r["gate_verdicts"].get("hardware", 0),
                     "n": r["n_queries"]})
    return rows


def report(payload: dict) -> None:
    pr, cm = payload["parameters"], payload["cross_machine"]
    print()
    print(f"{pr['total']} physical parameters "
          f"({pr['swept']} operating + {pr['hardware']} hardware), "
          f"{payload['variants']} machine variants")
    print(f"archive {payload['archive']['kept']}/{payload['archive']['attempted']} "
          f"converged, {payload['n_queries']} queries, "
          f"hardware tolerance {payload['hardware_tolerance']:.1%}")
    print()
    print("nearest neighbour over all 25 parameters:")
    print(f"  came from a DIFFERENT machine : "
          f"{cm['nearest_neighbour_was_another_machine']} / {payload['n_queries']}")
    print(f"  caught by the hardware rule   : {cm['caught_by_the_hardware_rule']}")
    print(f"  missed                        : {cm['missed']}")
    print(f"  gate verdicts                 : {payload['gate_verdicts']}")
    cr = payload["coverage_radius"]
    print(f"  coverage radius, measured in 25-D: {cr['in_25d']:.2f}  "
          f"(7-D would have been {cr['in_7d_would_have_been']:.2f})")
    print()
    print(f"{'arm':<13}{'converged':>11}{'failed':>8}{'total iters':>13}{'mean':>8}")
    for name, a in payload["arms"].items():
        mean = f"{a['mean_iterations']:.2f}" if a["mean_iterations"] else "-"
        print(f"{name:<13}{a['converged']:>11}{a['failed']:>8}"
              f"{a['total_iterations']:>13}{mean:>8}")

    scan = payload.get("tolerance_scan")
    if scan:
        print()
        print(f"the hardware rule as units of one design stop being identical "
              f"(band {payload['hardware_rel_tol']:.0%}):")
        for r in scan:
            print(f"  scatter {r['tolerance']:>5.1%}: {r['admitted']:>3}/{r['n']} "
                  f"admitted, {r['refused_hardware']:>3} refused as different hardware")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--variants", type=int, default=6)
    ap.add_argument("--archive", type=int, default=400)
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--out", type=Path, default=Path("results/wide_sweep_results.json"))
    ap.add_argument("--tolerance", type=float, default=0.0,
                    help="per-case manufacturing scatter on the hardware")
    ap.add_argument("--no-scan", dest="scan", action="store_false",
                    help="skip the scatter scan of the hardware rule")
    args = ap.parse_args()
    payload = run(args.variants, args.archive, args.queries, None,
                  args.tolerance)
    if args.scan:
        payload["tolerance_scan"] = tolerance_scan(args.variants, 200, 100)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report(payload)
    print()
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
