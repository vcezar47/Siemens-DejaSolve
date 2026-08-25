"""The circuit that does not decompose — a load-sensing pump.

Built to answer an objection the project could not answer this morning.

A competent engineer does not guess a starting point with three rules of thumb;
they *decompose*. On the base circuit each branch sees the rest of the world
through a single scalar — the manifold pressure — so its torque balance closes
in closed form, and one bisection on that scalar finds the operating point.
Measured, that beats the archive outright: 2.70 mean iterations against
retrieval's 3.44, and on the fold circuit 4.52 with **zero** inadmissible roots
against retrieval's 7.40 and four. Every warm-start number in this project rests
on the baseline being weaker than that.

So the honest question is not "is warm-starting fast" but **"when is there
anything left for it to do?"** — and the answer is: when the circuit does not
decompose.

Two ingredients, both ordinary hardware, neither invented for this:

* **A load-sensing pump.** The pump reads the highest branch pressure through a
  load-sense line and destrokes to hold the manifold just above it. Standard on
  every modern excavator. It makes the coupling *all to all*: branch i's inlet
  pressure sets the pump, the pump sets the manifold, the manifold drives branch
  j. There is no single scalar to bisect on, because the scalar depends on the
  answer.

* **Stribeck stiction**, already in `model.py`. Each shaft has more than one
  admissible speed for the same supply, so each branch is a *multi-valued*
  function of the manifold pressure.

Together those give **2^N global configurations** — which shafts broke away and
which stayed stuck — and the configuration is not a per-branch property. A shaft
sticks because the others are drawing flow; the others draw flow because it
stuck. A decomposed formula has to guess the configuration before it can start,
and it has no basis to guess with.

An archived run of a similar machine has exactly that basis: it *is* a
configuration that a real machine settled into.

    python coupled.py --selftest    # the analytic Jacobian
    python coupled.py               # the comparison that matters

Nothing here is imported by `run_all.py`.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import model

GLOBAL_PARAMS = ("Q_nom", "p_crack", "rho", "cd", "R_leak", "A_relief_max",
                 "relief_band", "A_drain")
BRANCH_PARAMS = ("A_valve", "c_load", "D_mot", "A_ret", "leak_mot",
                 "t_coul", "t_stat", "w_strib", "b_visc")

GLOBAL_BOUNDS = {
    "Q_nom": (40.0, 100.0),
    "p_crack": (170.0, 250.0),
    "rho": (800.0, 900.0),
    "cd": (0.62, 0.78),
    "R_leak": (45.0, 90.0),
    "A_relief_max": (18.0, 34.0),
    "relief_band": (8.0, 22.0),
    #: the shared return restriction -- the whole point. Every branch's
    #: exhaust passes through this one orifice, so each branch's flow raises
    #: the back-pressure every *other* branch has to push against.
    "A_drain": (3.0, 11.0),
}
#: Sized so breakaway is *marginal*: t_stat / kt lands near p_crack, which a
#: sweep of these bounds straddles. Away from that band every shaft simply
#: spins and there is one configuration; inside it, whether a shaft turns
#: depends on how much back-pressure its neighbours are making.
BRANCH_BOUNDS = {
    "A_valve": (0.6, 10.0),
    "c_load": (0.7e-5, 3.0e-5),
    "D_mot": (5.0, 9.0),
    "A_ret": (6.0, 16.0),
    "leak_mot": (0.008, 0.035),
    "t_coul": (2.0, 7.0),
    "t_stat": (14.0, 24.0),
    "w_strib": (35.0, 90.0),
    "b_visc": (1.0e-3, 3.5e-3),
}

#: sharpness of the smooth maximum standing in for the load-sense shuttle
#: stack. A real stack of shuttle valves is a hard max; this is the same thing
#: with a differentiable corner, the way `relief_opening` is a differentiable
#: version of a valve that really does slam.
LS_BETA = 0.35


def softmax_pressure(p2: np.ndarray, beta: float = LS_BETA) -> tuple[float, np.ndarray]:
    """The sensed load pressure, and d(p_ls)/d(p2_i).

    Log-sum-exp with the max shifted out, so it cannot overflow at 250 bar.
    The weights are the softmax, which is exactly the derivative -- a shuttle
    valve stack passes the highest pressure, and this passes a blend dominated
    by the highest.
    """
    m = float(np.max(p2))
    e = np.exp(beta * (p2 - m))
    s = float(np.sum(e))
    return m + np.log(s) / beta, e / s


def destroke(z, band: float):
    """Swashplate fraction: 1 at full stroke, 0 once the margin is exceeded."""
    s = min(max(z / band, 0.0), 1.0)
    return 1.0 - s * s * (3.0 - 2.0 * s)


def d_destroke(z, band: float):
    s = z / band
    if s <= 0.0 or s >= 1.0:
        return 0.0
    return -6.0 * s * (1.0 - s) / band


class Circuit:
    """N branches on one load-sensing pump. 1 + 3N unknowns."""

    def __init__(self, n_branches: int):
        self.n = n_branches
        self.n_state = 2 + 3 * n_branches
        self.state_names = ("p1", "p_ret") + tuple(
            f"{k}{i}" for i in range(n_branches) for k in ("p2_", "p3_", "w_"))
        self.param_names = tuple(GLOBAL_PARAMS) + tuple(
            f"{k}_{i}" for i in range(n_branches) for k in BRANCH_PARAMS)
        self.bounds = {**GLOBAL_BOUNDS,
                       **{f"{k}_{i}": v for i in range(n_branches)
                          for k, v in BRANCH_BOUNDS.items()}}
        self.n_param = len(self.param_names)

    P1, PRET = 0, 1

    def p2(self, i): return 2 + 3 * i
    def p3(self, i): return 2 + 3 * i + 1
    def w(self, i): return 2 + 3 * i + 2
    def row_in(self, i): return 2 + 3 * i
    def row_out(self, i): return 2 + 3 * i + 1
    def row_sh(self, i): return 2 + 3 * i + 2

    def b(self, p, k, i): return float(p[f"{k}_{i}"])

    def residual(self, x, p: dict) -> np.ndarray:
        rho, cd = float(p["rho"]), float(p["cd"])
        F = np.zeros(self.n_state)
        p1, p_ret = x[self.P1], x[self.PRET]

        q_rel = (model.orifice_gain(p["A_relief_max"], rho, cd)
                 * model.relief_opening(p1, p["p_crack"], p["relief_band"])
                 * model.f_dp(p1 - model.P_TANK))
        F[0] = float(p["Q_nom"]) - p1 / float(p["R_leak"]) - q_rel
        # every branch exhausts into the SAME node, and that node drains
        # through one orifice -- this is the coupling
        F[1] = -(model.orifice_gain(p["A_drain"], rho, cd)
                 * model.f_dp(p_ret - model.P_TANK))

        for i in range(self.n):
            d_mot = self.b(p, "D_mot", i)
            kt, kd = d_mot / (20.0 * np.pi), d_mot / 1000.0
            q_v = (model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
                   * model.f_dp(p1 - x[self.p2(i)]))
            q_m = kd * x[self.w(i)] + self.b(p, "leak_mot", i) * (
                x[self.p2(i)] - x[self.p3(i)])
            q_r = (model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
                   * model.f_dp(x[self.p3(i)] - p_ret))
            F[0] -= q_v
            F[1] += q_r
            F[self.row_in(i)] = q_v - q_m
            F[self.row_out(i)] = q_m - q_r
            F[self.row_sh(i)] = (
                (x[self.p2(i)] - x[self.p3(i)]) * kt
                - model.load_torque(x[self.w(i)], self.b(p, "c_load", i),
                                    self.b(p, "t_coul", i), self.b(p, "t_stat", i),
                                    self.b(p, "w_strib", i),
                                    self.b(p, "b_visc", i)))
        return F

    def jacobian(self, x, p: dict) -> np.ndarray:
        rho, cd = float(p["rho"]), float(p["cd"])
        J = np.zeros((self.n_state, self.n_state))
        p1, p_ret = x[self.P1], x[self.PRET]

        g_rel = model.orifice_gain(p["A_relief_max"], rho, cd)
        op = model.relief_opening(p1, p["p_crack"], p["relief_band"])
        dop = model.d_relief_opening(p1, p["p_crack"], p["relief_band"])
        J[0, self.P1] = (-1.0 / float(p["R_leak"])
                         - g_rel * (dop * model.f_dp(p1 - model.P_TANK)
                                    + op * model.df_dp(p1 - model.P_TANK)))
        d_drain = (model.orifice_gain(p["A_drain"], rho, cd)
                   * model.df_dp(p_ret - model.P_TANK))
        J[1, self.PRET] = -d_drain

        for i in range(self.n):
            d_mot = self.b(p, "D_mot", i)
            kt, kd = d_mot / (20.0 * np.pi), d_mot / 1000.0
            lk = self.b(p, "leak_mot", i)
            d_v = (model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
                   * model.df_dp(p1 - x[self.p2(i)]))
            d_r = (model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
                   * model.df_dp(x[self.p3(i)] - p_ret))

            J[0, self.P1] -= d_v
            J[0, self.p2(i)] += d_v
            J[1, self.p3(i)] += d_r
            J[1, self.PRET] -= d_r

            ri, ro, rs = self.row_in(i), self.row_out(i), self.row_sh(i)
            J[ri, self.P1] = d_v
            J[ri, self.p2(i)] = -d_v - lk
            J[ri, self.p3(i)] = lk
            J[ri, self.w(i)] = -kd
            J[ro, self.p2(i)] = lk
            J[ro, self.p3(i)] = -lk - d_r
            J[ro, self.PRET] = d_r
            J[ro, self.w(i)] = kd
            J[rs, self.p2(i)] = kt
            J[rs, self.p3(i)] = -kt
            J[rs, self.w(i)] = -model.d_load_torque(
                x[self.w(i)], self.b(p, "c_load", i), self.b(p, "t_coul", i),
                self.b(p, "t_stat", i), self.b(p, "w_strib", i),
                self.b(p, "b_visc", i))
        return J

    def solve(self, p, x0=None, max_iter: int = model.MAX_ITER) -> dict:
        x = np.zeros(self.n_state) if x0 is None else np.array(x0, dtype=float)
        F = self.residual(x, p)
        r = float(np.max(np.abs(F)))
        iters, status = 0, "converged"
        while r > model.TOL:
            if iters >= max_iter:
                status = "max_iter"
                break
            try:
                dx = np.linalg.solve(self.jacobian(x, p), -F)
            except np.linalg.LinAlgError:
                status = "singular_jacobian"
                break
            alpha = 1.0
            while True:
                xn = x + alpha * dx
                Fn = self.residual(xn, p)
                rn = float(np.max(np.abs(Fn)))
                if np.isfinite(rn) and rn < (1.0 - 1e-4 * alpha) * r:
                    break
                alpha *= 0.5
                if alpha < model.MIN_ALPHA:
                    status = "line_search_stall"
                    break
            if status != "converged":
                break
            x, F, r = xn, Fn, rn
            iters += 1
            if not np.all(np.isfinite(x)) or np.max(np.abs(x)) > model.DIVERGED_AT:
                status = "diverged"
                break
        return {"converged": status == "converged", "status": status,
                "iterations": iters, "residual_inf": r, "x": np.asarray(x).tolist()}

    # -- the baselines --------------------------------------------------
    def flat_start(self):
        return np.zeros(self.n_state)

    def decomposed_start(self, p: dict) -> np.ndarray:
        """The best per-branch formula available, ported here as fairly as it can be.

        This is the arm that beat the archive on every other circuit. It still
        gets the manifold pressure by bisection and each shaft by the same
        closed-form quadratic. What it cannot do is know the *configuration*:
        the shared return node means a shaft's available pressure drop depends
        on how much flow every other shaft is passing, and whether a shaft
        passes flow depends on whether it broke away. The formula has to assume
        one, and the only assumption available without solving is the one the
        hardware advertises -- that everything turns.
        """
        rho, cd = float(p["rho"]), float(p["cd"])
        pc = float(p["p_crack"])
        g_d = model.orifice_gain(p["A_drain"], rho, cd)

        def branch(i, p1, p_ret):
            d_mot = self.b(p, "D_mot", i)
            kt, kd = d_mot / (20.0 * np.pi), d_mot / 1000.0
            g_v = model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
            g_r = model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
            a = kd * kd * (1.0 / g_v ** 2 + 1.0 / g_r ** 2)
            A = self.b(p, "c_load", i) + kt * a
            B = self.b(p, "b_visc", i)
            C = self.b(p, "t_coul", i) - kt * max(p1 - p_ret, 0.0)
            w = 0.0 if C >= 0 else float(min(
                (-B + np.sqrt(B * B - 4 * A * C)) / (2 * A), model.W_NOMINAL_MAX))
            return w, kd * w, g_v, g_r

        # alternate: guess the return pressure, solve the branches, update it
        p_ret = 1.0
        p1 = pc
        for _ in range(30):
            tot = sum(branch(i, p1, p_ret)[1] for i in range(self.n))
            p_ret_new = (tot / g_d) ** 2 if g_d > 0 else 0.0
            demand = tot
            supply = float(p["Q_nom"]) - p1 / float(p["R_leak"])
            # if the branches take less than the pump makes, the relief holds
            # the manifold at cracking pressure; otherwise pressure falls
            p1_new = pc if supply > demand else max(p1 * 0.97, p_ret + 1.0)
            if abs(p_ret_new - p_ret) < 1e-6 and abs(p1_new - p1) < 1e-6:
                p_ret, p1 = p_ret_new, p1_new
                break
            p_ret = 0.5 * (p_ret + p_ret_new)
            p1 = 0.5 * (p1 + p1_new)

        x = np.zeros(self.n_state)
        x[self.P1], x[self.PRET] = p1, p_ret
        for i in range(self.n):
            w, q, g_v, g_r = branch(i, p1, p_ret)
            p3 = p_ret + (q / g_r) ** 2
            x[self.p2(i)] = max(p1 - (q / g_v) ** 2, p3)
            x[self.p3(i)] = p3
            x[self.w(i)] = w
        return x

    # -- bookkeeping ------------------------------------------------------
    def param_vector(self, p): return np.array([p[k] for k in self.param_names])

    def normalise(self, v):
        lo = np.array([self.bounds[k][0] for k in self.param_names])
        hi = np.array([self.bounds[k][1] for k in self.param_names])
        return (np.atleast_2d(np.asarray(v, float)) - lo) / (hi - lo)

    def sample_cases(self, n, seed):
        rng = np.random.default_rng(seed)
        u = np.empty((n, self.n_param))
        for j in range(self.n_param):
            u[:, j] = (rng.permutation(n) + rng.random(n)) / n
        lo = np.array([self.bounds[k][0] for k in self.param_names])
        hi = np.array([self.bounds[k][1] for k in self.param_names])
        return [dict(zip(self.param_names, row)) for row in lo + u * (hi - lo)]

    def variant_cases(self, n_variants, per_variant, seed):
        """Few machines, many operating points -- the realistic archive shape."""
        rng = np.random.default_rng(seed)
        op = {"Q_nom", "p_crack"} | {f"A_valve_{i}" for i in range(self.n)} \
             | {f"c_load_{i}" for i in range(self.n)}
        out = []
        for _ in range(n_variants):
            hw = {k: rng.uniform(*self.bounds[k]) for k in self.param_names
                  if k not in op}
            for _ in range(per_variant):
                case = dict(hw)
                for k in op:
                    case[k] = rng.uniform(*self.bounds[k])
                out.append(case)
        return out

    def configuration(self, x) -> tuple:
        """Which shafts broke away — the thing a formula has to guess."""
        return tuple(int(abs(x[self.w(i)]) > 2.0 * model.W_REG)
                     for i in range(self.n))


def check_jacobian(widths=(2, 3, 4), n_cases=15, seed=7, tol=1e-5) -> int:
    ok_all = 1
    for nb in widths:
        c = Circuit(nb)
        rng = np.random.default_rng(seed)
        worst, where = 0.0, ""
        for ci, p in enumerate(c.sample_cases(n_cases, seed + nb)):
            top = rng.uniform(80.0, 250.0)
            x = np.zeros(c.n_state)
            x[c.P1] = top
            x[c.PRET] = top * rng.uniform(0.02, 0.15)
            for i in range(nb):
                x[c.p2(i)] = top * rng.uniform(0.5, 0.92)
                x[c.p3(i)] = x[c.PRET] + (top - x[c.PRET]) * rng.uniform(0.05, 0.4)
                x[c.w(i)] = rng.uniform(60.0, 1500.0)
            Ja = c.jacobian(x, p)
            Jn = np.zeros_like(Ja)
            for j in range(c.n_state):
                h = 1e-6 * max(abs(x[j]), 1.0)
                xp, xm = x.copy(), x.copy()
                xp[j] += h
                xm[j] -= h
                Jn[:, j] = (c.residual(xp, p) - c.residual(xm, p)) / (2 * h)
            sc = np.maximum(np.abs(Ja), np.abs(Jn))
            sc[sc < 1e-9] = 1.0
            rel = np.abs(Ja - Jn) / sc
            if rel.max() > worst:
                worst = float(rel.max())
                r, cc = np.unravel_index(rel.argmax(), rel.shape)
                where = f"case {ci}, dF[{r}]/d{c.state_names[cc]}"
        ok = worst <= tol
        ok_all &= int(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  n={nb}  {c.n_state:>2} unknowns, "
              f"{c.n_param:>3} params   J {worst:.1e}  ({where})")
    return ok_all


def study(nb: int, n_variants: int, per_variant: int, n_query: int) -> dict:
    c = Circuit(nb)
    recs, states = [], []
    configs = {}
    for p in c.variant_cases(n_variants, per_variant, seed=1):
        r = c.solve(p, x0=c.decomposed_start(p))
        if not r["converged"]:
            r = c.solve(p)
        if r["converged"]:
            recs.append(p)
            states.append(np.asarray(r["x"]))
            cfg = c.configuration(r["x"])
            configs[cfg] = configs.get(cfg, 0) + 1
    states = np.array(states)
    norm = c.normalise(np.array([c.param_vector(p) for p in recs]))

    rng = np.random.default_rng(7)
    op = {"Q_nom", "p_crack"} | {f"A_valve_{i}" for i in range(nb)} \
         | {f"c_load_{i}" for i in range(nb)}
    src = c.variant_cases(n_variants, 1, seed=1)
    queries = []
    for v in range(n_variants):
        for _ in range(max(1, n_query // n_variants)):
            q = dict(src[v])
            for k in op:
                q[k] = rng.uniform(*c.bounds[k])
            queries.append(q)

    arms = ("flat", "decomposed", "warm")
    it = {a: [] for a in arms}
    fails = {a: 0 for a in arms}
    cfg_hit = {"decomposed": 0, "warm": 0}
    n_cfg = 0

    for p in queries:
        v = c.normalise(c.param_vector(p))
        j = int(np.argmin(np.linalg.norm(norm - v, axis=1)))
        got = {"flat": c.solve(p),
               "decomposed": c.solve(p, x0=c.decomposed_start(p)),
               "warm": c.solve(p, x0=states[j])}
        for a in arms:
            it[a].append(got[a]["iterations"] if got[a]["converged"] else None)
            if not got[a]["converged"]:
                fails[a] += 1
        # did each start already have the right configuration?
        truth = None
        for a in ("flat", "decomposed", "warm"):
            if got[a]["converged"]:
                truth = c.configuration(got[a]["x"])
                break
        if truth is not None:
            n_cfg += 1
            if c.configuration(c.decomposed_start(p)) == truth:
                cfg_hit["decomposed"] += 1
            if c.configuration(states[j]) == truth:
                cfg_hit["warm"] += 1

    def paired(a, b):
        both = [(x, y) for x, y in zip(it[a], it[b])
                if x is not None and y is not None]
        if not both:
            return None
        ta, tb = sum(x for x, _ in both), sum(y for _, y in both)
        return float(100 * (1 - ta / tb)) if tb else None

    ok = {a: [v for v in it[a] if v is not None] for a in arms}
    return {
        "branches": nb, "unknowns": c.n_state, "parameters": c.n_param,
        "archive": len(recs), "n_queries": len(queries),
        "distinct_configurations": len(configs),
        "arms": {a: {"mean": float(np.mean(ok[a])) if ok[a] else None,
                     "failures": fails[a]} for a in arms},
        "warm_vs_decomposed_pct": paired("warm", "decomposed"),
        "warm_vs_flat_pct": paired("warm", "flat"),
        "configuration_hit": {k: (v, n_cfg) for k, v in cfg_hit.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--widths", type=int, nargs="+", default=[2, 3, 4])
    ap.add_argument("--variants", type=int, default=20)
    ap.add_argument("--per-variant", type=int, default=25)
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--out", type=Path, default=Path("coupled_results.json"))
    args = ap.parse_args()

    print("load-sensing circuit selftest")
    if not check_jacobian(tuple(args.widths)):
        print("  Jacobian is wrong -- nothing else will be run")
        return 1
    if args.selftest:
        return 0

    rows = []
    for nb in args.widths:
        print(f"  running n={nb} ...", flush=True)
        rows.append(study(nb, args.variants, args.per_variant, args.queries))

    print()
    print("--- does the archive beat a decomposed formula here? ---")
    print(f"  {'br':>3}{'unk':>5}{'par':>5}{'cfgs':>6}{'flat':>8}{'decomp':>9}"
          f"{'warm':>7}   {'warm vs decomposed':>20}")
    for r in rows:
        a = r["arms"]
        vd = ("--" if r["warm_vs_decomposed_pct"] is None
              else f"{r['warm_vs_decomposed_pct']:+.1f}%")
        print(f"  {r['branches']:>3}{r['unknowns']:>5}{r['parameters']:>5}"
              f"{r['distinct_configurations']:>6}"
              f"{a['flat']['mean']:>8.2f}{a['decomposed']['mean']:>9.2f}"
              f"{a['warm']['mean']:>7.2f}{vd:>20}")
    print()
    print("  starts that already had the right break-away configuration:")
    for r in rows:
        d, n = r["configuration_hit"]["decomposed"]
        w, _ = r["configuration_hit"]["warm"]
        print(f"    n={r['branches']}: decomposed {d}/{n}   archive {w}/{n}")
    print()
    print("  failures (flat / decomposed / warm):")
    for r in rows:
        a = r["arms"]
        print(f"    n={r['branches']}: {a['flat']['failures']} / "
              f"{a['decomposed']['failures']} / {a['warm']['failures']}")

    args.out.write_text(json.dumps(
        {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "widths": rows}, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
