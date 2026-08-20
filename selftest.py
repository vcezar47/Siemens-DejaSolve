"""Invariants of the numerical core, checked rather than trusted.

`run_all.py` proves the *results* reproduce. This proves the things those
results rest on, which is a different job and the one that matters when the
model is being changed a week before a deadline:

  1. **The analytic Jacobian is the derivative of the residual.** Every number
     in this project is downstream of it — the benchmark hands the solver an
     exact derivative on purpose, so a wrong entry would not announce itself as
     a crash. It would quietly change iteration counts, which is precisely the
     quantity being reported.
  2. **Stating a hardware constant explicitly is the same as leaving it out.**
     The circuit constants can be swept per case; the defaults must reproduce
     the module constants exactly, or every measurement taken before they were
     promoted stops being comparable with every one taken after.
  3. **Asymmetric hardware is wired to the right shaft.** The transcription
     error this refactor invites is using branch a's constant in branch b's
     row, and symmetric test cases cannot see it.

Central differences rather than forward: the orifice law is regularised on a
scale of 1e-3 bar and the friction law on 5 rev/min, so a sloppy step size
measures the regularisation instead of the derivative. States are sampled away
from those kinks for the same reason, and the check says so rather than quietly
choosing a tolerance that hides it.

    python selftest.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import model
from sweep import sample_cases

#: away from the orifice kink at dp = 0 and the friction kink at w = 0, where
#: the regularisation -- not the physics -- sets the local scale
PRESSURE_RANGE = (5.0, 240.0)
SPEED_RANGE = (80.0, 1600.0)


def random_state(rng: np.random.Generator) -> np.ndarray:
    lo, hi = PRESSURE_RANGE
    wlo, whi = SPEED_RANGE
    p1 = rng.uniform(lo, hi)
    return np.array([
        p1,
        rng.uniform(lo, p1), rng.uniform(lo, p1), rng.uniform(wlo, whi),
        rng.uniform(lo, p1), rng.uniform(lo, p1), rng.uniform(wlo, whi),
    ])


def central_jacobian(x: np.ndarray, p: dict, rel_step: float = 1e-6) -> np.ndarray:
    n = len(x)
    J = np.zeros((n, n))
    for j in range(n):
        h = rel_step * max(abs(x[j]), 1.0)
        xp, xm = x.astype(float).copy(), x.astype(float).copy()
        xp[j] += h
        xm[j] -= h
        J[:, j] = (model.residual(xp, p) - model.residual(xm, p)) / (2.0 * h)
    return J


def check_jacobian(cases: list[dict], seed: int, tol: float,
                   label: str) -> tuple[int, float]:
    """Max relative disagreement between the analytic and numerical Jacobian."""
    rng = np.random.default_rng(seed)
    worst, worst_where = 0.0, ""
    for i, p in enumerate(cases):
        x = random_state(rng)
        Ja, Jn = model.jacobian(x, p), central_jacobian(x, p)
        scale = np.maximum(np.abs(Ja), np.abs(Jn))
        scale[scale < 1e-9] = 1.0          # both entries ~0: nothing to compare
        rel = np.abs(Ja - Jn) / scale
        if rel.max() > worst:
            worst = float(rel.max())
            r, c = np.unravel_index(rel.argmax(), rel.shape)
            worst_where = f"case {i}, J[{r},{c}]"
    ok = worst <= tol
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<44} "
          f"worst relative error {worst:.2e}  ({worst_where})")
    return int(ok), worst


def asymmetric(p: dict, rng: np.random.Generator) -> dict:
    """Give the two branches genuinely different hardware.

    Only touches names `model.HARDWARE` knows about, so on a build where the
    constants have not been promoted this returns the case unchanged and the
    check still runs -- it just cannot fail the way it is designed to.
    """
    out = dict(p)
    for name, default in getattr(model, "HARDWARE", {}).items():
        if name.endswith(("_a", "_b")):
            out[name] = float(default) * rng.uniform(0.6, 1.6)
    return out


def check_defaults(cases: list[dict], tol: float) -> int:
    """Stating every constant explicitly must change nothing at all."""
    hw = getattr(model, "HARDWARE", {})
    if not hw:
        print("  SKIP  defaults: no promotable constants on this build")
        return 1
    worst = 0.0
    for p in cases:
        explicit = {**p, **{k: float(v) for k, v in hw.items()}}
        a = model.solve(p)
        b = model.solve(explicit)
        if a["converged"] != b["converged"] or a["iterations"] != b["iterations"]:
            print(f"  FAIL  defaults: {p} solved differently when stated explicitly")
            return 0
        if a["converged"]:
            worst = max(worst, float(np.abs(np.array(a["x"]) - np.array(b["x"])).max()))
    ok = worst <= tol
    print(f"  {'PASS' if ok else 'FAIL'}  {'explicit defaults == module defaults':<44} "
          f"worst state difference {worst:.2e}")
    return int(ok)


#: written so the page can state that the invariants hold rather than the
#: reader having to take the numbers on trust
RESULTS = Path("selftest_results.json")


def main_checks(n_cases: int = 60, seed: int = 7, tol: float = 1e-5) -> int:
    """Run every check. Returns 0 if all pass, so `run_all.py` can gate on it."""
    cases = sample_cases(n_cases, seed)
    rng = np.random.default_rng(seed + 1)

    print(f"selftest: {n_cases} cases, seed {seed}, tol {tol:g}")
    ok_sym, worst_sym = check_jacobian(
        cases, seed, tol, "analytic Jacobian == central differences")
    ok_asym, worst_asym = check_jacobian(
        [asymmetric(p, rng) for p in cases], seed, tol,
        "  ... with the two branches built differently")
    ok_def = check_defaults(cases[:12], tol=1e-12)
    passed = ok_sym + ok_asym + ok_def

    RESULTS.write_text(json.dumps({
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases": n_cases, "tolerance": tol,
        "passed": passed, "total": 3,
        "jacobian_worst_rel_error": worst_sym,
        "jacobian_worst_rel_error_asymmetric": worst_asym,
        "defaults_exact": bool(ok_def),
    }, indent=2), encoding="utf-8")

    print(f"{passed}/3 checks passed")
    return 0 if passed == 3 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--tol", type=float, default=1e-5,
                    help="relative tolerance on the Jacobian comparison")
    args = ap.parse_args()
    return main_checks(args.cases, args.seed, args.tol)


if __name__ == "__main__":
    raise SystemExit(main())
