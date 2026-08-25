"""An N-branch manifold, generated rather than hand-written — the scaling study.

`geometry.py` answered "what if the pipes were real?" on a two-branch circuit:
12 unknowns, 18 parameters. It found something awkward. Going from 7 parameters
to 18 took the headline *down*, 31% -> 14.3%, because mean neighbour distance
went 0.357 -> 1.041 and a verbatim transfer of a far-away neighbour's state is
a bad guess no matter how good the retrieval is.

That is the honest objection to "more complexity makes warm-starting look
better", and it is worth taking seriously rather than arguing around: **more
parameters make retrieval harder faster than they make cold starts worse.**

But it points at a real, falsifiable claim. A verbatim transfer has no way to
account for the parameter gap — it asserts the neighbour's answer *is* the
query's answer, so the further apart they are, the worse it is. A first-order
transfer walks the tangent across exactly that gap. So:

    verbatim transfer should degrade with parameter count.
    first-order transfer should degrade much more slowly.

If that holds, the number gets big because the *method* is robust to
dimensionality, not because the baseline was sandbagged. If it does not hold,
that is a finding and it kills the scaling story honestly.

Testing it needs a machine that actually scales, so this generates one:

      pump ─[supply line]─ p1 ─┬── relief ──> tank
                               ├─[line 0]─ valve 0 ─ MOTOR 0 ─[return 0]─> tank
                               ├─[line 1]─ valve 1 ─ MOTOR 1 ─[return 1]─> tank
                               │   ...
                               └─[line N-1] ...

Every branch is the same five equations and thirteen parameters, so the
residual, the analytic Jacobian and the analytic dF/dp are all assembled in a
loop rather than transcribed N times — which is the only reason a 42-unknown
circuit with 114 parameters is a tractable thing to hand-derive at all.

    n branches   unknowns (2+5n)   parameters (10+13n)
        2              12                 36
        4              22                 62
        6              32                 88
        8              42                114

A four-function manifold is ordinary hardware, not a contrivance: an
excavator's boom, arm, bucket and swing hang off one pump exactly like this.

    python manifold.py --selftest        # Jacobian and dF/dp, every width
    python manifold.py                   # the scaling study

Nothing here is imported by `run_all.py` or by anything that ships a number.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import model
from geometry import (DP_REG_LINE, M_TURB, d_line_flow, line_flow,
                      line_param_derivs, reynolds)

# --- the circuit, as a function of how many branches it has -----------------

#: parameters shared by the whole circuit, whatever its width
GLOBAL_PARAMS = ("Q_nom", "p_crack", "rho", "mu", "cd", "R_leak",
                 "A_relief_max", "relief_band", "L_supply", "D_supply")

#: parameters every branch carries its own copy of. Six of them are geometry
#: (the feed run and the return run), seven are the motor and its friction --
#: so a wider machine is not just a longer list, it is more *independent*
#: hardware, which is the case retrieval finds hardest.
BRANCH_PARAMS = ("A_valve", "c_load", "L_line", "D_line", "L_ret", "D_ret",
                 "D_mot", "A_ret", "leak_mot", "t_coul", "t_stat", "w_strib",
                 "b_visc")

GLOBAL_BOUNDS = {
    "Q_nom": (30.0, 90.0),
    "p_crack": (120.0, 260.0),
    "rho": (800.0, 900.0),
    "mu": (0.012, 0.055),
    "cd": (0.62, 0.78),
    "R_leak": (45.0, 90.0),
    "A_relief_max": (18.0, 34.0),
    "relief_band": (8.0, 22.0),
    "L_supply": (0.4, 4.0),
    "D_supply": (14.0, 28.0),
}

BRANCH_BOUNDS = {
    "A_valve": (0.6, 12.0),
    "c_load": (0.7e-5, 3.0e-5),
    "L_line": (0.3, 3.5),
    "D_line": (8.0, 20.0),
    "L_ret": (0.4, 4.0),
    "D_ret": (10.0, 25.0),
    "D_mot": (18.0, 45.0),
    "A_ret": (6.0, 16.0),
    "leak_mot": (0.008, 0.035),
    "t_coul": (2.0, 7.0),
    "t_stat": (9.0, 20.0),      # Stribeck needs t_stat > t_coul, and it is
    "w_strib": (35.0, 90.0),
    "b_visc": (1.0e-3, 3.5e-3),
}


class Circuit:
    """One manifold width. Holds the index arithmetic so nothing else has to.

    Every method below is written against `self.n`, so the same code is the
    12-unknown circuit and the 42-unknown one. That is deliberate: a
    hand-transcribed 42x42 Jacobian would be a transcription-error generator,
    and the scaling claim would rest on whichever width happened to be right.
    """

    def __init__(self, n_branches: int):
        if n_branches < 1:
            raise ValueError("a manifold needs at least one branch")
        self.n = n_branches
        self.n_state = 2 + 5 * n_branches
        self.state_names = ("p0", "p1") + tuple(
            f"{k}{i}" for i in range(n_branches)
            for k in ("p1_", "p2_", "p3_", "p4_", "w_"))
        self.param_names = tuple(GLOBAL_PARAMS) + tuple(
            f"{k}_{i}" for i in range(n_branches) for k in BRANCH_PARAMS)
        self.bounds = {**GLOBAL_BOUNDS,
                       **{f"{k}_{i}": v for i in range(n_branches)
                          for k, v in BRANCH_BOUNDS.items()}}
        self.n_param = len(self.param_names)
        self.pcol = {name: i for i, name in enumerate(self.param_names)}
        #: which state entries are speeds -- everything else is a pressure
        self.speed_idx = [self.w(i) for i in range(n_branches)]
        self.pressure_idx = [i for i in range(self.n_state)
                             if i not in self.speed_idx]

    # -- state indices --------------------------------------------------
    P0, P1 = 0, 1

    def p1_(self, i: int) -> int: return 2 + 5 * i          # valve inlet
    def p2_(self, i: int) -> int: return 2 + 5 * i + 1      # motor inlet
    def p3_(self, i: int) -> int: return 2 + 5 * i + 2      # motor outlet
    def p4_(self, i: int) -> int: return 2 + 5 * i + 3      # after return line
    def w(self, i: int) -> int: return 2 + 5 * i + 4        # shaft

    # -- residual rows (one block of five per branch) --------------------
    def row_feed(self, i: int) -> int: return 2 + 5 * i     # valve inlet node
    def row_min(self, i: int) -> int: return 2 + 5 * i + 1  # motor inlet node
    def row_mout(self, i: int) -> int: return 2 + 5 * i + 2  # motor outlet node
    def row_ret(self, i: int) -> int: return 2 + 5 * i + 3  # return node
    def row_shaft(self, i: int) -> int: return 2 + 5 * i + 4

    def b(self, p: dict, key: str, i: int) -> float:
        """Branch `i`'s value of branch-parameter `key`."""
        return float(p[f"{key}_{i}"])

    # -- physics ---------------------------------------------------------
    def residual(self, x, p: dict) -> np.ndarray:
        n = self.n
        rho, mu, cd = float(p["rho"]), float(p["mu"]), float(p["cd"])
        F = np.zeros(self.n_state)

        q_sup = line_flow(x[self.P0] - x[self.P1], p["L_supply"], p["D_supply"],
                          rho, mu)
        q_pump = p["Q_nom"] - x[self.P0] / p["R_leak"]
        q_rel = (model.orifice_gain(p["A_relief_max"], rho, cd)
                 * model.relief_opening(x[self.P1], p["p_crack"], p["relief_band"])
                 * model.f_dp(x[self.P1] - model.P_TANK))

        F[0] = q_pump - q_sup
        F[1] = q_sup - q_rel

        for i in range(n):
            q_line = line_flow(x[self.P1] - x[self.p1_(i)],
                               self.b(p, "L_line", i), self.b(p, "D_line", i),
                               rho, mu)
            F[1] -= q_line

            d_mot = self.b(p, "D_mot", i)
            kt, kd = d_mot / (20.0 * np.pi), d_mot / 1000.0
            q_valve = (model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
                       * model.f_dp(x[self.p1_(i)] - x[self.p2_(i)]))
            q_motor = (kd * x[self.w(i)] + self.b(p, "leak_mot", i)
                       * (x[self.p2_(i)] - x[self.p3_(i)]))
            q_ret = line_flow(x[self.p3_(i)] - x[self.p4_(i)],
                              self.b(p, "L_ret", i), self.b(p, "D_ret", i),
                              rho, mu)
            q_orf = (model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
                     * model.f_dp(x[self.p4_(i)] - model.P_TANK))

            F[self.row_feed(i)] = q_line - q_valve
            F[self.row_min(i)] = q_valve - q_motor
            F[self.row_mout(i)] = q_motor - q_ret
            F[self.row_ret(i)] = q_ret - q_orf
            F[self.row_shaft(i)] = (
                (x[self.p2_(i)] - x[self.p3_(i)]) * kt
                - model.load_torque(x[self.w(i)], self.b(p, "c_load", i),
                                    self.b(p, "t_coul", i), self.b(p, "t_stat", i),
                                    self.b(p, "w_strib", i), self.b(p, "b_visc", i)))
        return F

    def jacobian(self, x, p: dict) -> np.ndarray:
        n = self.n
        rho, mu, cd = float(p["rho"]), float(p["mu"]), float(p["cd"])
        J = np.zeros((self.n_state, self.n_state))

        d_sup = d_line_flow(x[self.P0] - x[self.P1], p["L_supply"],
                            p["D_supply"], rho, mu)
        J[0, self.P0] = -1.0 / p["R_leak"] - d_sup
        J[0, self.P1] = d_sup
        J[1, self.P0] = d_sup
        J[1, self.P1] = -d_sup

        band = p["relief_band"]
        g_rel = model.orifice_gain(p["A_relief_max"], rho, cd)
        op = model.relief_opening(x[self.P1], p["p_crack"], band)
        dop = model.d_relief_opening(x[self.P1], p["p_crack"], band)
        J[1, self.P1] -= g_rel * (dop * model.f_dp(x[self.P1] - model.P_TANK)
                                  + op * model.df_dp(x[self.P1] - model.P_TANK))

        for i in range(n):
            a, b_, c_, d_, w_ = (self.p1_(i), self.p2_(i), self.p3_(i),
                                 self.p4_(i), self.w(i))
            d_line = d_line_flow(x[self.P1] - x[a], self.b(p, "L_line", i),
                                 self.b(p, "D_line", i), rho, mu)
            J[1, self.P1] -= d_line
            J[1, a] += d_line

            d_mot = self.b(p, "D_mot", i)
            kt, kd = d_mot / (20.0 * np.pi), d_mot / 1000.0
            lk = self.b(p, "leak_mot", i)
            d_valve = (model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
                       * model.df_dp(x[a] - x[b_]))
            d_ret = d_line_flow(x[c_] - x[d_], self.b(p, "L_ret", i),
                                self.b(p, "D_ret", i), rho, mu)
            d_orf = (model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
                     * model.df_dp(x[d_] - model.P_TANK))

            rf, rm, ro, rr, rs = (self.row_feed(i), self.row_min(i),
                                  self.row_mout(i), self.row_ret(i),
                                  self.row_shaft(i))
            # feed node: q_line - q_valve
            J[rf, self.P1] = d_line
            J[rf, a] = -d_line - d_valve
            J[rf, b_] = d_valve
            # motor inlet: q_valve - q_motor
            J[rm, a] = d_valve
            J[rm, b_] = -d_valve - lk
            J[rm, c_] = lk
            J[rm, w_] = -kd
            # motor outlet: q_motor - q_ret
            J[ro, b_] = lk
            J[ro, c_] = -lk - d_ret
            J[ro, d_] = d_ret
            J[ro, w_] = kd
            # return node: q_ret - q_orifice
            J[rr, c_] = d_ret
            J[rr, d_] = -d_ret - d_orf
            # shaft
            J[rs, b_] = kt
            J[rs, c_] = -kt
            J[rs, w_] = -model.d_load_torque(
                x[w_], self.b(p, "c_load", i), self.b(p, "t_coul", i),
                self.b(p, "t_stat", i), self.b(p, "w_strib", i),
                self.b(p, "b_visc", i))
        return J

    def dresidual_dp(self, x, p: dict) -> np.ndarray:
        """d(residual)/d(parameter), analytic, shaped (n_state, n_param)."""
        n = self.n
        rho, mu, cd = float(p["rho"]), float(p["mu"]), float(p["cd"])
        col = self.pcol
        D = np.zeros((self.n_state, self.n_param))

        # ---- supply line and the pump ----------------------------------
        dp_sup = x[self.P0] - x[self.P1]
        q_sup = line_flow(dp_sup, p["L_supply"], p["D_supply"], rho, mu)
        dL, dD, drho_s, dmu_s = line_param_derivs(
            dp_sup, p["L_supply"], p["D_supply"], rho, mu)
        D[0, col["Q_nom"]] = 1.0
        D[0, col["R_leak"]] = x[self.P0] / (p["R_leak"] ** 2)
        for c, v in (("L_supply", dL), ("D_supply", dD)):
            D[0, col[c]] -= v
            D[1, col[c]] += v
        D[0, col["rho"]] -= drho_s
        D[1, col["rho"]] += drho_s
        D[0, col["mu"]] -= dmu_s
        D[1, col["mu"]] += dmu_s

        # ---- relief valve ----------------------------------------------
        band = p["relief_band"]
        g_rel = model.orifice_gain(p["A_relief_max"], rho, cd)
        s = (x[self.P1] - p["p_crack"]) / band
        op = model.relief_opening(x[self.P1], p["p_crack"], band)
        dop = model.d_relief_opening(x[self.P1], p["p_crack"], band)
        f_rel = model.f_dp(x[self.P1] - model.P_TANK)
        q_rel = g_rel * op * f_rel
        D[1, col["p_crack"]] += g_rel * dop * f_rel
        # the ramp is a function of s, so widening the band rescales s itself
        D[1, col["relief_band"]] += g_rel * f_rel * dop * s
        D[1, col["A_relief_max"]] -= q_rel / p["A_relief_max"]
        D[1, col["cd"]] -= q_rel / cd
        D[1, col["rho"]] += q_rel / (2.0 * rho)

        # ---- per branch -------------------------------------------------
        for i in range(n):
            a, b_, c_, d_, w_ = (self.p1_(i), self.p2_(i), self.p3_(i),
                                 self.p4_(i), self.w(i))
            rf, rm, ro, rr, rs = (self.row_feed(i), self.row_min(i),
                                  self.row_mout(i), self.row_ret(i),
                                  self.row_shaft(i))
            LL, DD = f"L_line_{i}", f"D_line_{i}"
            LR, DR = f"L_ret_{i}", f"D_ret_{i}"

            # feed line
            dpl = x[self.P1] - x[a]
            dL, dD, drho_l, dmu_l = line_param_derivs(
                dpl, self.b(p, "L_line", i), self.b(p, "D_line", i), rho, mu)
            for c, v in ((LL, dL), (DD, dD)):
                D[1, col[c]] -= v
                D[rf, col[c]] += v
            D[1, col["rho"]] -= drho_l
            D[rf, col["rho"]] += drho_l
            D[1, col["mu"]] -= dmu_l
            D[rf, col["mu"]] += dmu_l

            # metering valve
            q_valve = (model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
                       * model.f_dp(x[a] - x[b_]))
            for c, v in ((f"A_valve_{i}", q_valve / self.b(p, "A_valve", i)),
                         ("cd", q_valve / cd), ("rho", -q_valve / (2.0 * rho))):
                D[rf, col[c]] -= v
                D[rm, col[c]] += v

            # motor: displacement and cross-port leakage
            dq_dDmot = x[w_] / 1000.0
            D[rm, col[f"D_mot_{i}"]] -= dq_dDmot
            D[ro, col[f"D_mot_{i}"]] += dq_dDmot
            dq_dleak = x[b_] - x[c_]
            D[rm, col[f"leak_mot_{i}"]] -= dq_dleak
            D[ro, col[f"leak_mot_{i}"]] += dq_dleak

            # return line
            dpr = x[c_] - x[d_]
            dL, dD, drho_r, dmu_r = line_param_derivs(
                dpr, self.b(p, "L_ret", i), self.b(p, "D_ret", i), rho, mu)
            for c, v in ((LR, dL), (DR, dD)):
                D[ro, col[c]] -= v
                D[rr, col[c]] += v
            D[ro, col["rho"]] -= drho_r
            D[rr, col["rho"]] += drho_r
            D[ro, col["mu"]] -= dmu_r
            D[rr, col["mu"]] += dmu_r

            # return orifice
            q_orf = (model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
                     * model.f_dp(x[d_] - model.P_TANK))
            D[rr, col[f"A_ret_{i}"]] -= q_orf / self.b(p, "A_ret", i)
            D[rr, col["cd"]] -= q_orf / cd
            D[rr, col["rho"]] += q_orf / (2.0 * rho)

            # shaft: torque from displacement, minus the load
            D[rs, col[f"D_mot_{i}"]] += (x[b_] - x[c_]) / (20.0 * np.pi)
            D[rs, col[f"c_load_{i}"]] -= x[w_] * abs(x[w_])
            wv = x[w_]
            env_exp = np.exp(-(wv / self.b(p, "w_strib", i)) ** 2)
            tanh_w = np.tanh(wv / model.W_REG)
            tc, ts = self.b(p, "t_coul", i), self.b(p, "t_stat", i)
            ws = self.b(p, "w_strib", i)
            # friction = (tc + (ts-tc) exp(-(w/ws)^2)) tanh(w/W_REG)
            D[rs, col[f"t_coul_{i}"]] -= (1.0 - env_exp) * tanh_w
            D[rs, col[f"t_stat_{i}"]] -= env_exp * tanh_w
            D[rs, col[f"w_strib_{i}"]] -= (
                (ts - tc) * env_exp * (2.0 * wv * wv / ws ** 3) * tanh_w)
            D[rs, col[f"b_visc_{i}"]] -= wv
        return D

    # -- the solve --------------------------------------------------------
    def nominal_start(self, p: dict) -> np.ndarray:
        """The guess a competent tool makes from the case setup alone, N wide.

        `model.nominal_start` assumes the pump runs against the relief valve, so
        the manifold sits at ``p_crack``. That is right for two branches and
        **wrong for six**: N branches in parallel absorb N times the flow, the
        relief never cracks, and the manifold settles far below ``p_crack``.
        Measured, the naive version cost 9.71 iterations at six branches against
        a flat start's 9.67 -- a baseline that had stopped being a baseline, and
        any reduction quoted against it would have been the WARP error this
        project corrects for elsewhere.

        So the manifold pressure is estimated from *flow balance* instead, and
        the relief-open value becomes the ceiling rather than the answer:

            every branch meters roughly half the manifold pressure across its
            valve, so  Q_nom = (sum_i g_i) * sqrt(p1 / 2),  giving
            p1 = 2 (Q_nom / sum_i g_i)^2,  capped at p_crack.

        Still no archive, no solve, and no residual evaluation -- only the case
        parameters and the orifice law. The pipe runs are still assumed
        lossless, deliberately: letting the baseline know about line losses
        would hand it the answer this circuit exists to test.
        """
        rho, cd = float(p["rho"]), float(p["cd"])
        p_crack, q_nom = float(p["p_crack"]), float(p["Q_nom"])

        # Per branch, at a *given* manifold pressure, the steady state closes in
        # closed form. A motor is a positive-displacement device: it passes
        # kd*w, so both orifice drops are quadratic in w, and dropping only the
        # Stribeck dip from the friction leaves
        #     (c_load + kt*a) w^2 + b_visc w + (t_coul - kt*p1) = 0
        # with a = kd^2 (1/g_valve^2 + 1/g_ret^2). One quadratic per branch, no
        # iteration -- treating the branch as a free orifice instead was the
        # first attempt and it under-predicted p1 badly enough to make the
        # baseline worse than a flat start at six branches.
        def branch_speed(i: int, p1: float) -> float:
            kd = self.b(p, "D_mot", i) / 1000.0
            kt = self.b(p, "D_mot", i) / (20.0 * np.pi)
            g_v = model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
            g_r = model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
            if g_v <= 0 or g_r <= 0:
                return 0.0
            a = kd * kd * (1.0 / (g_v * g_v) + 1.0 / (g_r * g_r))
            A = self.b(p, "c_load", i) + kt * a
            B = self.b(p, "b_visc", i)
            C = self.b(p, "t_coul", i) - kt * p1
            if C >= 0.0:                      # not enough pressure to break away
                return 0.0
            disc = B * B - 4.0 * A * C
            return float(min((-B + np.sqrt(disc)) / (2.0 * A),
                             model.W_NOMINAL_MAX))

        def imbalance(p1: float) -> float:
            """pump delivery minus everything the circuit takes at this p1."""
            taken = sum(self.b(p, "D_mot", i) / 1000.0 * branch_speed(i, p1)
                        for i in range(self.n))
            g_rel = model.orifice_gain(p["A_relief_max"], rho, cd)
            q_rel = (g_rel * model.relief_opening(p1, p_crack, p["relief_band"])
                     * model.f_dp(p1 - model.P_TANK))
            return (q_nom - p1 / p["R_leak"]) - taken - q_rel

        # the manifold pressure is where supply meets demand. Monotone
        # decreasing in p1, so bisection is enough -- 40 evaluations of a
        # closed-form sum, no residual and no Jacobian.
        lo, hi = 0.0, p_crack + float(p["relief_band"])
        if imbalance(hi) > 0.0:
            p1 = hi
        else:
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                if imbalance(mid) > 0.0:
                    lo = mid
                else:
                    hi = mid
            p1 = 0.5 * (lo + hi)

        x = np.zeros(self.n_state)
        x[self.P0] = x[self.P1] = p1
        for i in range(self.n):
            w = branch_speed(i, p1)
            kd = self.b(p, "D_mot", i) / 1000.0
            q_i = kd * w
            g_v = model.orifice_gain(self.b(p, "A_valve", i), rho, cd)
            g_r = model.orifice_gain(self.b(p, "A_ret", i), rho, cd)
            p4 = (q_i / g_r) ** 2 if g_r > 0 else model.P_TANK
            p2 = p1 - ((q_i / g_v) ** 2 if g_v > 0 else 0.0)
            x[self.p1_(i)] = p1
            x[self.p2_(i)] = max(p2, p4)
            x[self.p3_(i)] = p4
            x[self.p4_(i)] = p4
            x[self.w(i)] = w
        return x

    def solve(self, p: dict, x0=None, tol: float = model.TOL,
              max_iter: int = model.MAX_ITER) -> dict:
        x = (np.zeros(self.n_state) if x0 is None
             else np.array(x0, dtype=float))
        F = self.residual(x, p)
        r = float(np.max(np.abs(F)))
        iters, status = 0, "converged"
        while r > tol:
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
                "iterations": iters, "residual_inf": r,
                "x": np.asarray(x).tolist()}

    # -- transfer ---------------------------------------------------------
    def param_vector(self, p: dict) -> np.ndarray:
        return np.array([p[k] for k in self.param_names], dtype=float)

    def normalise(self, vec) -> np.ndarray:
        lo = np.array([self.bounds[k][0] for k in self.param_names])
        hi = np.array([self.bounds[k][1] for k in self.param_names])
        return (np.atleast_2d(np.asarray(vec, dtype=float)) - lo) / (hi - lo)

    def solution_sensitivity(self, x, p: dict) -> np.ndarray:
        return np.linalg.solve(self.jacobian(x, p), -self.dresidual_dp(x, p))

    def transfer_start(self, x_src, sens, p_src: dict, p_query: dict):
        x0 = np.asarray(x_src, dtype=float)
        if sens is None:
            return x0
        return x0 + sens @ (self.param_vector(p_query) - self.param_vector(p_src))

    def sample_cases(self, n: int, seed: int) -> list[dict]:
        rng = np.random.default_rng(seed)
        u = np.empty((n, self.n_param))
        for j in range(self.n_param):
            u[:, j] = (rng.permutation(n) + rng.random(n)) / n
        lo = np.array([self.bounds[k][0] for k in self.param_names])
        hi = np.array([self.bounds[k][1] for k in self.param_names])
        return [dict(zip(self.param_names, row)) for row in lo + u * (hi - lo)]


# --- the invariants, at every width -----------------------------------------

def _ladder(rng, top: float, k: int) -> list[float]:
    out, v = [], top
    for _ in range(k):
        out.append(v)
        v *= rng.uniform(0.55, 0.9)
    return out


def sample_state(c: Circuit, rng) -> np.ndarray:
    """A physically-ordered state: pressure falls from pump to tank on every
    branch, so no element sits exactly on its regularisation kink. Sampling
    independently would put lines at dp = 0, where a central difference
    measures the regularisation rather than the derivative."""
    x = np.zeros(c.n_state)
    top = rng.uniform(80.0, 240.0)
    x[c.P0] = top
    x[c.P1] = top * rng.uniform(0.9, 0.98)
    for i in range(c.n):
        lad = _ladder(rng, x[c.P1] * rng.uniform(0.75, 0.95), 4)
        x[c.p1_(i)], x[c.p2_(i)], x[c.p3_(i)], x[c.p4_(i)] = lad
        x[c.w(i)] = rng.uniform(80.0, 1600.0)
    return x


def check_derivatives(widths=(2, 3, 4, 6), n_cases: int = 12,
                      seed: int = 7, tol: float = 1e-5) -> int:
    """Both hand-derived matrices, at every width, before any number is quoted.

    The Jacobian and dF/dp are assembled in loops, so a slip is not a typo in
    one row -- it is the same mistake in every branch of every width, which is
    exactly the failure a single-width check would confirm rather than catch.
    """
    ok_all = 1
    for nb in widths:
        c = Circuit(nb)
        rng = np.random.default_rng(seed)
        worst_j, worst_p, wj, wp = 0.0, 0.0, "", ""
        below, total = 0, 0
        for case_i, p in enumerate(c.sample_cases(n_cases, seed + nb)):
            x = sample_state(c, rng)

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
            if rel.max() > worst_j:
                worst_j = float(rel.max())
                r, cc = np.unravel_index(rel.argmax(), rel.shape)
                wj = f"case {case_i}, dF[{r}]/d{c.state_names[cc]}"

            Da = c.dresidual_dp(x, p)
            # A central difference cannot resolve a derivative smaller than
            # roughly eps*|F|/h -- below that it is subtracting two numbers
            # that agree to machine precision and reporting the rounding. The
            # Stribeck term makes that a real case rather than a pedantic one:
            # a shaft at 400 rev/min with w_strib = 74 has exp(-(w/ws)^2) ~
            # 1e-13, so dF/d(t_stat) is genuinely that small and genuinely
            # correct, while the difference quotient returns a clean 0.0.
            # Comparing them is measuring the check, not the derivative.
            # dF/dp is checked *directionally* rather than column by column,
            # which is the standard way to verify a large derivative matrix and
            # the only one that works here.
            #
            # Probing one parameter at a time was tried first and kept failing
            # on the friction columns for a reason worth recording. The shaft
            # row is `(p2-p3)*kt - load_torque`, two O(500) terms cancelling to
            # O(15), so a difference in that row carries the roundoff of the
            # *terms*. Meanwhile a shaft spinning well past its Stribeck
            # velocity has `exp(-(w/w_strib)^2) ~ 1e-13`, so dF/d(t_stat) is
            # genuinely that small -- correct, and five orders of magnitude
            # under the noise. Column-wise, that entry is unmeasurable; no
            # threshold separates "tiny and right" from "tiny and wrong".
            #
            # A random direction sidesteps it: every column contributes to one
            # well-scaled number, an error in any single column still shows up
            # (a wrong column is orthogonal to a random direction with
            # probability zero), and the difference is taken between residuals
            # that actually differ.
            scale = np.array([max(abs(float(p[k])), 1e-3 * (c.bounds[k][1] - c.bounds[k][0]))
                              for k in c.param_names])
            for _ in range(6):
                v = rng.standard_normal(c.n_param)
                v /= np.linalg.norm(v)
                step = 1e-6 * v * scale

                def shifted(mult: float) -> dict:
                    return {k: float(p[k]) + mult * step[kk]
                            for kk, k in enumerate(c.param_names)}

                num = (c.residual(x, shifted(+1.0))
                       - c.residual(x, shifted(-1.0))) / 2.0
                ana = Da @ step
                denom = max(float(np.max(np.abs(num))), 1e-30)
                rel_dir = float(np.max(np.abs(ana - num)) / denom)
                total += 1
                if rel_dir > worst_p:
                    worst_p = rel_dir
                    wp = f"case {case_i}, random direction"
            rel = np.zeros((1, 1))
        ok = worst_j <= tol and worst_p <= tol
        ok_all &= int(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  n={nb}  "
              f"{c.n_state:>2} unknowns, {c.n_param:>3} params   "
              f"J {worst_j:.1e}   dF/dp {worst_p:.1e}  "
              f"({total} directional probes)")
        if not ok:
            print(f"          worst J at {wj};  worst dF/dp at {wp}")
    return ok_all


#: how many candidates the ranked arm scores, matching `bench.K_RANKED`
K_RANKED = 5

#: What varies from *run* to run rather than from machine to machine. Everything
#: else -- every bore, length, motor and friction constant -- is the hardware,
#: fixed once a machine is built. `wide_sweep.py` established this split on the
#: 25-parameter circuit and §0b established it from the engineer interview:
#: a real archive is a handful of designs with many operating points each, not
#: 400 unique machines.
OPERATING = ("Q_nom", "p_crack")
OPERATING_PER_BRANCH = ("A_valve", "c_load")


def variant_cases(c: Circuit, n_variants: int, per_variant: int,
                  seed: int) -> list[dict]:
    """An archive shaped like a real one: few machines, many operating points.

    The uniform sweep above scatters every one of 88 parameters independently,
    which makes each archived case a machine nobody ever built and puts the
    nearest neighbour 3.2 unit-cube-diameters away. That is the worst case for
    retrieval and it is not the case a company is in.

    Here the hardware is drawn once per variant and *shared* by all its runs,
    so the archive's effective dimensionality is the operating set (2 + 2n)
    rather than the full card (10 + 13n) -- 14 instead of 88 at six branches,
    even though every Case Card still records all 88.
    """
    rng = np.random.default_rng(seed)
    op_names = set(OPERATING) | {f"{k}_{i}" for i in range(c.n)
                                 for k in OPERATING_PER_BRANCH}
    out = []
    for _ in range(n_variants):
        hw = {k: rng.uniform(*c.bounds[k]) for k in c.param_names
              if k not in op_names}
        for _ in range(per_variant):
            case = dict(hw)
            for k in c.param_names:
                if k in op_names:
                    case[k] = rng.uniform(*c.bounds[k])
            out.append(case)
    return out


def study_realistic(nb: int, n_variants: int, per_variant: int,
                    n_query: int) -> dict:
    """The same arms, on an archive with realistic structure.

    Queries are drawn from the *same* variants -- a new operating point on a
    machine the archive has seen, which is the case the whole idea is for. A
    query from an unseen machine is the `hardware` gate's job, and phase-1d
    already measured that retrieval separates machines on its own.
    """
    c = Circuit(nb)
    cases = variant_cases(c, n_variants, per_variant, seed=1)
    recs, states, sens = [], [], []
    for p in cases:
        r = c.solve(p)
        if not r["converged"]:
            continue
        x = np.asarray(r["x"])
        try:
            s = c.solution_sensitivity(x, p)
        except np.linalg.LinAlgError:
            s = None
        recs.append(p)
        states.append(x)
        sens.append(s)
    states = np.array(states)
    norm = c.normalise(np.array([c.param_vector(p) for p in recs]))

    queries = variant_cases(c, n_variants, max(1, n_query // n_variants), seed=99)
    # same machines, different operating points: re-seed only the operating set
    rng = np.random.default_rng(7)
    op_names = set(OPERATING) | {f"{k}_{i}" for i in range(c.n)
                                 for k in OPERATING_PER_BRANCH}
    queries = []
    for v in range(n_variants):
        base = recs[0] if not recs else None
        src = cases[v * per_variant]
        for _ in range(max(1, n_query // n_variants)):
            q = dict(src)
            for k in op_names:
                q[k] = rng.uniform(*c.bounds[k])
            queries.append(q)

    scale = np.array([1.0 if not nm.startswith("w_") else 50.0
                      for nm in c.state_names])
    arms = ("cold", "nominal", "warm", "first_order", "ranked")
    it = {a: [] for a in arms}
    fails = {a: 0 for a in arms}
    dists = []
    for p in queries:
        v = c.normalise(c.param_vector(p))
        d = np.linalg.norm(norm - v, axis=1)
        j = int(np.argmin(d))
        dists.append(float(d[j]))
        got = {"cold": c.solve(p),
               "nominal": c.solve(p, x0=c.nominal_start(p)),
               "warm": c.solve(p, x0=states[j]),
               "first_order": c.solve(p, x0=c.transfer_start(
                   states[j], sens[j], recs[j], p))}
        cand = np.argsort(d)[:K_RANKED]
        best, best_err = int(cand[0]), np.inf
        for cc in cand:
            if sens[cc] is None:
                continue
            e = float(np.max(np.abs(
                sens[cc] @ (c.param_vector(p) - c.param_vector(recs[cc]))) / scale))
            if e < best_err:
                best, best_err = int(cc), e
        got["ranked"] = c.solve(p, x0=c.transfer_start(
            states[best], sens[best], recs[best], p))
        # per query, keep the count or None -- the comparison below has to be
        # *paired*, and at eight branches the arms fail on very different
        # subsets (cold 114 of 200, ranked 89), so totals taken over each arm's
        # own survivors would be comparing different sets of cases and calling
        # the difference a result. `bench.summarise` pairs for the same reason.
        for a in arms:
            if got[a]["converged"]:
                it[a].append(got[a]["iterations"])
                fails[a] += 0
            else:
                it[a].append(None)
                fails[a] += 1

    def paired(a: str) -> dict:
        both = [(x, y) for x, y in zip(it[a], it["nominal"])
                if x is not None and y is not None]
        if not both:
            return {"vs_nominal_pct": None, "n_compared": 0}
        arm_t = sum(x for x, _ in both)
        nom_t = sum(y for _, y in both)
        return {"vs_nominal_pct": (float(100 * (1 - arm_t / nom_t))
                                   if nom_t else None),
                "n_compared": len(both)}

    ok = {a: [v for v in it[a] if v is not None] for a in arms}
    return {
        "branches": nb, "unknowns": c.n_state, "parameters": c.n_param,
        "effective_dim": len(OPERATING) + len(OPERATING_PER_BRANCH) * nb,
        "variants": n_variants, "archive": len(recs), "n_queries": len(queries),
        "arms": {a: {"mean": float(np.mean(ok[a])) if ok[a] else None,
                     "failures": fails[a], **paired(a)} for a in arms},
        "neighbour_distance_mean": float(np.mean(dists)),
    }


def build_archive(c: Circuit, n: int, seed: int) -> tuple[list, np.ndarray, np.ndarray, list]:
    """Sweep, keep what converged, and record each card's tangent."""
    recs, states, sens = [], [], []
    for p in c.sample_cases(n, seed):
        r = c.solve(p)
        if not r["converged"]:
            continue
        x = np.asarray(r["x"])
        try:
            s = c.solution_sensitivity(x, p)
        except np.linalg.LinAlgError:
            s = None
        recs.append(p)
        states.append(x)
        sens.append(s)
    return recs, np.array(states), c.normalise(
        np.array([c.param_vector(p) for p in recs])), sens


def study_width(nb: int, n_archive: int, n_query: int) -> dict:
    """One manifold width, every arm, on the same archive and the same queries."""
    c = Circuit(nb)
    recs, states, norm, sens = build_archive(c, n_archive, seed=1)
    if len(recs) < 20:
        raise SystemExit(f"n={nb}: only {len(recs)} cases converged")

    scale = np.array([1.0 if not nm.startswith("w_") else 50.0
                      for nm in c.state_names])
    arms = ("cold", "nominal", "warm", "first_order", "ranked")
    it = {a: [] for a in arms}
    fails = {a: 0 for a in arms}
    dists, agree = [], []

    for p in c.sample_cases(n_query, seed=99):
        v = c.normalise(c.param_vector(p))
        d = np.linalg.norm(norm - v, axis=1)
        j = int(np.argmin(d))
        dists.append(float(d[j]))

        got = {
            "cold": c.solve(p),
            "nominal": c.solve(p, x0=c.nominal_start(p)),
            "warm": c.solve(p, x0=states[j]),
            "first_order": c.solve(p, x0=c.transfer_start(
                states[j], sens[j], recs[j], p)),
        }
        # ranked: among the k nearest, the card predicting the smallest start
        # error -- the same signal bench.py ranks on, at this width
        cand = np.argsort(d)[:K_RANKED]
        best, best_err = int(cand[0]), np.inf
        for cc in cand:
            if sens[cc] is None:
                continue
            e = float(np.max(np.abs(
                sens[cc] @ (c.param_vector(p) - c.param_vector(recs[cc]))) / scale))
            if e < best_err:
                best, best_err = int(cc), e
        got["ranked"] = c.solve(p, x0=c.transfer_start(
            states[best], sens[best], recs[best], p))

        for a in arms:
            if got[a]["converged"]:
                it[a].append(got[a]["iterations"])
            else:
                fails[a] += 1
        if got["cold"]["converged"] and got["ranked"]["converged"]:
            agree.append(float(np.max(np.abs(
                np.array(got["cold"]["x"]) - np.array(got["ranked"]["x"])))))

    tot = {a: int(sum(it[a])) for a in arms}
    nomt = tot["nominal"]
    return {
        "branches": nb, "unknowns": c.n_state, "parameters": c.n_param,
        "archive": len(recs), "n_queries": n_query,
        "arms": {a: {"mean": float(np.mean(it[a])) if it[a] else None,
                     "total": tot[a], "failures": fails[a],
                     "vs_nominal_pct": (float(100 * (1 - tot[a] / nomt))
                                        if nomt and a != "nominal" else None)}
                 for a in arms},
        "neighbour_distance_mean": float(np.mean(dists)),
        "max_disagreement": max(agree) if agree else None,
    }


def report_study(rows: list[dict]) -> None:
    print()
    print("--- how each arm degrades as the machine grows ---")
    print(f"  {'branches':>9}{'unknowns':>10}{'params':>8}{'nbr dist':>10}"
          f"{'cold':>8}{'nominal':>9}{'warm':>8}{'+1st':>8}{'+ranked':>9}")
    for r in rows:
        a = r["arms"]
        print(f"  {r['branches']:>9}{r['unknowns']:>10}{r['parameters']:>8}"
              f"{r['neighbour_distance_mean']:>10.3f}"
              f"{a['cold']['mean']:>8.2f}{a['nominal']['mean']:>9.2f}"
              f"{a['warm']['mean']:>8.2f}{a['first_order']['mean']:>8.2f}"
              f"{a['ranked']['mean']:>9.2f}")
    print()
    print(f"  {'':>9}{'':>10}{'':>8}{'':>10}{'reduction vs nominal:':>33}")
    print(f"  {'branches':>9}{'unknowns':>10}{'params':>8}{'':>10}"
          f"{'warm':>16}{'+1st':>8}{'+ranked':>9}")
    for r in rows:
        a = r["arms"]
        print(f"  {r['branches']:>9}{r['unknowns']:>10}{r['parameters']:>8}"
              f"{'':>10}{a['warm']['vs_nominal_pct']:>15.1f}%"
              f"{a['first_order']['vs_nominal_pct']:>7.1f}%"
              f"{a['ranked']['vs_nominal_pct']:>8.1f}%")
    print()
    for r in rows:
        dis = r["max_disagreement"]
        print(f"  n={r['branches']}: archive {r['archive']}, "
              f"failures cold {r['arms']['cold']['failures']} / "
              f"ranked {r['arms']['ranked']['failures']}, "
              f"max |cold-ranked| {dis:.1e}" if dis is not None else "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--widths", type=int, nargs="+", default=[2, 3, 4, 6])
    ap.add_argument("--archive", type=int, default=400)
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--out", type=Path, default=Path("manifold_results.json"))
    args = ap.parse_args()
    print("manifold selftest -- analytic derivatives at every width")
    ok = check_derivatives(tuple(args.widths))
    if not ok:
        print("  derivatives are wrong -- nothing else will be run")
        return 1
    if args.selftest:
        return 0

    rows = []
    for nb in args.widths:
        print(f"  running n={nb} ...", flush=True)
        rows.append(study_width(nb, args.archive, args.queries))
    report_study(rows)
    args.out.write_text(json.dumps(
        {"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "archive": args.archive, "queries": args.queries, "widths": rows},
        indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
