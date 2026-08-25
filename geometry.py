"""The same circuit, with pipe runs that are real — an experiment.

`static/index.html` carries a disclaimer: *"the layout is illustrative — the
model is lumped and has no geometry."* It is honest and it is a real
limitation. Pipe colour is the solved pressure **at a node**, and between two
nodes the drawing invents a route that the solver knows nothing about. Draw the
same circuit with the pipes twice as long and every number stays identical.

This module asks what it would take for that sentence to be false. Not by
drawing better — by making length and bore *drive the answer*:

    pump ─[line L0,D0]─ p1 ─┬───────────── relief ──> tank
                            ├─[line La,Da]─ p1a ─ valve_a ─ p2a ─ MOTOR a ─
                            │                  p3a ─[line Ra,Dra]─ p4a ─ ret ─> tank
                            └─[line Lb,Db]─ p1b ─ valve_b ─ p2b ─ MOTOR b ─
                                               p3b ─[line Rb,Drb]─ p4b ─ ret ─> tank

Five pipe runs, each with a length and a bore, each dropping pressure through
Darcy–Weisbach. That takes the state from 7 unknowns to **12** and the Case
Card from 7 parameters to **18** — the 7 swept ones, fluid viscosity (which a
lumped orifice circuit never needed), and 10 geometric ones.

**Why this is not the base circuit with extra decoration.** A line is a
genuinely different nonlinearity from an orifice. The orifice law is
`Q ~ sqrt(dp)` everywhere. A line is *linear* in `dp` while the flow is laminar
and reverts to a `dp^(4/7)` power law once it goes turbulent, so the same
element changes character across the operating envelope, and where it changes
depends on the bore. That is the physics reason a real hydraulic engineer
cares about line sizing at all.

**What this is for.** Two things the project already measured now collide:
phase-1c found that a distance metric degrades as the Case Card widens, and
phase-1d found that recording hardware makes retrieval separate machines by
itself. Geometry is *both* — it is 10 more real parameters, and it is what
makes two otherwise-identical manifolds different machines. So the question
this module exists to answer is not "does warm-starting still work" (it should)
but **"can retrieval still tell two machines apart when the difference is
plumbing?"**

    python geometry.py --selftest     # the Jacobian, against central differences
    python geometry.py                # sweep, then warm-start on fresh cases

Nothing here is imported by `run_all.py`, `bench.py` or `model.py`. The frozen
Phase 1 numbers do not know this file exists.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import model

# --- the line element -------------------------------------------------------
#
# Darcy-Weisbach, written in the direction the residual needs. The node balance
# sums *flows*, so every element has to be Q(dp) — but Darcy-Weisbach is
# naturally dp(Q), and the friction factor depends on Reynolds number, which
# depends on Q. Rather than nest a solve inside the residual (which would hide
# the geometry behind a black box and cost a Newton iteration every evaluation),
# both regimes are inverted analytically and blended:
#
#   laminar    Hagen-Poiseuille, Q = G dp          exact, linear
#   turbulent  Blasius f = 0.3164 Re^-0.25, which inverts in closed form
#              to Q = K dp^(4/7)
#
# and the two are composed as resistances in series, 1/Q = 1/Q_lam + 1/Q_turb.
# That is smooth, it is the more restrictive of the two everywhere, and it has
# the right asymptotes: laminar dominates as dp -> 0 (because dp << dp^(4/7)
# there), turbulent dominates once dp is large. No regime switch, no `if`.

#: 4/7 = 1/1.75, the Blasius exponent inverted. Named because the number is
#: meaningless on sight and wrong by a factor that no test would catch.
M_TURB = 4.0 / 7.0

#: Regularisation of |dp|, in bar — and it is set to `model.P_REG` for exactly
#: the reason that constant exists, which was not obvious until the Jacobian
#: check failed and was right to.
#:
#: The composite is linear through the origin whatever this is (near dp = 0,
#: Q ~ G*s*(dp/s) = G*dp and the s cancels), so it looks like a free parameter.
#: It is not. The turbulent branch carries s^(4/7), whose *second* derivative
#: diverges at the origin, so with this set small the slope falls ~13% between
#: dp = 0 and dp = 1e-3 bar. That is a kink in all but name: Newton's local
#: model is quadratic, and a curvature that large inside a step it might take
#: is the same failure the orifice law's P_REG was introduced to prevent.
#: At 1e-3 bar the curvature is bounded, and a pressure drop below 1e-3 bar
#: across a pipe run is not a physically meaningful quantity anyway.
DP_REG_LINE = model.P_REG


def line_coeffs(L: float, D: float, rho: float, mu: float) -> tuple[float, float]:
    """Laminar conductance G [L/min per bar] and turbulent K [L/min per bar^(4/7)].

    `L` in metres, `D` in millimetres, `rho` in kg/m^3, `mu` in Pa s. Both
    coefficients are pure functions of the geometry and the fluid, so they are
    computed once per element per evaluation and shared with the derivative.
    """
    d_si = D * 1e-3
    a_si = np.pi * d_si * d_si / 4.0
    # Hagen-Poiseuille, converted to L/min per bar with D in mm
    g_lam = (6e-3 * np.pi / 128.0) * D ** 4 / (mu * L)
    # Blasius, inverted: v = (dp_pa * C)^(4/7)
    c = 2.0 * d_si ** 1.25 / (0.3164 * mu ** 0.25 * rho ** 0.75 * L)
    k_turb = 60000.0 * a_si * (1e5 * c) ** M_TURB
    return g_lam, k_turb


def line_flow(dp, L: float, D: float, rho: float, mu: float):
    """Flow [L/min] through a pipe run of length `L` and bore `D` under `dp` [bar]."""
    g, k = line_coeffs(L, D, rho, mu)
    s = np.sqrt(dp * dp + DP_REG_LINE * DP_REG_LINE)
    a = g * s
    b = k * s ** M_TURB
    return (a * b / (a + b)) * (dp / s)


def d_line_flow(dp, L: float, D: float, rho: float, mu: float):
    """d(line_flow)/d(dp). Equals the laminar conductance G at the origin."""
    g, k = line_coeffs(L, D, rho, mu)
    s = np.sqrt(dp * dp + DP_REG_LINE * DP_REG_LINE)
    a = g * s
    b = k * s ** M_TURB
    q = a * b / (a + b)
    # 1/Q = 1/A + 1/B  =>  dQ/ds = Q^2 (A'/A^2 + B'/B^2)
    dq_ds = q * q * (1.0 / (g * s * s) + M_TURB / (k * s ** (M_TURB + 1.0)))
    return dq_ds * (dp * dp) / (s * s) + q * DP_REG_LINE ** 2 / s ** 3


def line_param_derivs(dp, L: float, D: float, rho: float, mu: float
                      ) -> tuple[float, float, float, float]:
    """d(line_flow)/d(L, D, rho, mu) — the geometry half of dF/dp.

    Both coefficients are pure power laws in the four, which is what makes this
    tractable analytically rather than another finite difference:

        G  ~  D^4 / (mu L)                 laminar, Hagen-Poiseuille
        K  ~  D^(19/7) mu^(-1/7) rho^(-3/7) L^(-4/7)     Blasius, inverted

    so every derivative is the coefficient times a constant over the variable.
    The flow then depends on the two through
    ``dQ/dG = Q^2 dp / (G^2 s^2)`` and ``dQ/dK = Q^2 dp / (K^2 s^(m+1))``,
    both of which fall out of ``1/Q = 1/A + 1/B``.
    """
    g, k = line_coeffs(L, D, rho, mu)
    s = np.sqrt(dp * dp + DP_REG_LINE * DP_REG_LINE)
    a = g * s
    b = k * s ** M_TURB
    qm = a * b / (a + b)

    # d(flow)/d(coefficient), sharing the qm^2 factor
    dq_dg = qm * qm / (g * g * s) * (dp / s)
    dq_dk = qm * qm / (k * k * s ** M_TURB) * (dp / s)

    dq_dL = dq_dg * (-g / L) + dq_dk * (-M_TURB * k / L)
    dq_dD = dq_dg * (4.0 * g / D) + dq_dk * ((2.0 + 5.0 / 7.0) * k / D)
    dq_drho = dq_dk * (-(3.0 / 7.0) * k / rho)          # G carries no rho
    dq_dmu = dq_dg * (-g / mu) + dq_dk * (-(1.0 / 7.0) * k / mu)
    return float(dq_dL), float(dq_dD), float(dq_drho), float(dq_dmu)


def reynolds(q_lmin, D: float, rho: float, mu: float) -> float:
    """Reynolds number of `q_lmin` in a bore of `D` mm — reported, never solved on.

    Only used to say afterwards which regime a converged line actually sat in.
    Nothing in the residual branches on it; that is the point of the blend.
    """
    d_si = D * 1e-3
    a_si = np.pi * d_si * d_si / 4.0
    v = abs(q_lmin) / 60000.0 / a_si
    return float(rho * v * d_si / mu)


# --- the circuit ------------------------------------------------------------

#: 12 unknowns. Five more than the base circuit, and every one of them exists
#: because a pipe has two ends that are no longer the same pressure.
STATE_NAMES = ("p0", "p1", "p1a", "p2a", "p3a", "p4a", "w_a",
               "p1b", "p2b", "p3b", "p4b", "w_b")
STATE_UNITS = ("bar",) * 6 + ("rev/min",) + ("bar",) * 4 + ("rev/min",)

P0, P1, P1A, P2A, P3A, P4A, WA, P1B, P2B, P3B, P4B, WB = range(12)

PRESSURE_IDX = [P0, P1, P1A, P2A, P3A, P4A, P1B, P2B, P3B, P4B]
SPEED_IDX = [WA, WB]

#: The geometry, as parameters. Lengths in metres, bores in millimetres.
#: Per branch rather than shared, because two branches of the same manifold
#: having different pipe runs is the ordinary case, not the exotic one -- and
#: it is exactly the asymmetry a symmetric test would never catch.
GEOM_NAMES = ("L_supply", "D_supply",
              "L_line_a", "D_line_a", "L_line_b", "D_line_b",
              "L_ret_a", "D_ret_a", "L_ret_b", "D_ret_b")

#: dynamic viscosity, which a pure-orifice circuit never needed: the orifice
#: law is inertia-dominated and carries only density. A line is viscous, so
#: the fluid gains a second property the moment the model gains length.
FLUID_NAMES = ("mu",)

PARAM_NAMES = tuple(model.PARAM_NAMES) + FLUID_NAMES + GEOM_NAMES

PARAM_BOUNDS = {
    **model.PARAM_BOUNDS,
    "mu": (0.012, 0.055),        # Pa s -- ISO VG 22 hot to VG 46 cold
    "L_supply": (0.4, 4.0),      # m
    "D_supply": (12.0, 25.0),    # mm
    "L_line_a": (0.3, 3.5),
    "D_line_a": (8.0, 20.0),
    "L_line_b": (0.3, 3.5),
    "D_line_b": (8.0, 20.0),
    "L_ret_a": (0.4, 4.0),
    "D_ret_a": (10.0, 25.0),
    "L_ret_b": (0.4, 4.0),
    "D_ret_b": (10.0, 25.0),
}

#: A pipe run's geometry, keyed to the two nodes it joins. This table *is* the
#: topology -- the residual and the Jacobian both walk it, so a line cannot be
#: added to one and forgotten in the other.
LINES = (
    ("supply", P0, P1, "L_supply", "D_supply"),
    ("line_a", P1, P1A, "L_line_a", "D_line_a"),
    ("line_b", P1, P1B, "L_line_b", "D_line_b"),
    ("ret_a", P3A, P4A, "L_ret_a", "D_ret_a"),
    ("ret_b", P3B, P4B, "L_ret_b", "D_ret_b"),
)


def residual(x, p: dict) -> np.ndarray:
    """Flow imbalance [L/min] at the 10 nodes, torque imbalance [Nm] at 2 shafts."""
    rho, mu = float(p["rho"]), float(p["mu"])
    h = model.hardware(p)
    ha, hb = model.shaft_hw(h, "a"), model.shaft_hw(h, "b")
    kt_a, kd_a = ha["D_mot"] / (20.0 * np.pi), ha["D_mot"] / 1000.0
    kt_b, kd_b = hb["D_mot"] / (20.0 * np.pi), hb["D_mot"] / 1000.0

    q = {name: line_flow(x[i] - x[j], p[lk], p[dk], rho, mu)
         for name, i, j, lk, dk in LINES}

    g_va = model.orifice_gain(p["A_valve_a"], rho, h["cd"])
    g_vb = model.orifice_gain(p["A_valve_b"], rho, h["cd"])
    g_ra = model.orifice_gain(ha["A_ret"], rho, h["cd"])
    g_rb = model.orifice_gain(hb["A_ret"], rho, h["cd"])
    g_rel = model.orifice_gain(h["A_relief_max"], rho, h["cd"])

    q_pump = p["Q_nom"] - x[P0] / h["R_leak"]
    q_rel = (g_rel * model.relief_opening(x[P1], p["p_crack"], h["relief_band"])
             * model.f_dp(x[P1] - model.P_TANK))
    q_va = g_va * model.f_dp(x[P1A] - x[P2A])
    q_vb = g_vb * model.f_dp(x[P1B] - x[P2B])
    q_ma = kd_a * x[WA] + ha["leak_mot"] * (x[P2A] - x[P3A])
    q_mb = kd_b * x[WB] + hb["leak_mot"] * (x[P2B] - x[P3B])
    q_reta = g_ra * model.f_dp(x[P4A] - model.P_TANK)
    q_retb = g_rb * model.f_dp(x[P4B] - model.P_TANK)

    return np.array([
        q_pump - q["supply"],                                   # pump outlet
        q["supply"] - q["line_a"] - q["line_b"] - q_rel,        # manifold
        q["line_a"] - q_va,                                     # valve a inlet
        q_va - q_ma,                                            # motor a inlet
        q_ma - q["ret_a"],                                      # motor a outlet
        q["ret_a"] - q_reta,                                    # return a
        (x[P2A] - x[P3A]) * kt_a - model.load_torque(
            x[WA], p["c_load_a"], ha["t_coul"], ha["t_stat"],
            ha["w_strib"], ha["b_visc"]),
        q["line_b"] - q_vb,                                     # valve b inlet
        q_vb - q_mb,                                            # motor b inlet
        q_mb - q["ret_b"],                                      # motor b outlet
        q["ret_b"] - q_retb,                                    # return b
        (x[P2B] - x[P3B]) * kt_b - model.load_torque(
            x[WB], p["c_load_b"], hb["t_coul"], hb["t_stat"],
            hb["w_strib"], hb["b_visc"]),
    ])


def jacobian(x, p: dict) -> np.ndarray:
    """Analytic Jacobian, 12x12. Checked against central differences by --selftest."""
    rho, mu = float(p["rho"]), float(p["mu"])
    h = model.hardware(p)
    ha, hb = model.shaft_hw(h, "a"), model.shaft_hw(h, "b")
    kt_a, kd_a = ha["D_mot"] / (20.0 * np.pi), ha["D_mot"] / 1000.0
    kt_b, kd_b = hb["D_mot"] / (20.0 * np.pi), hb["D_mot"] / 1000.0
    lk_a, lk_b = ha["leak_mot"], hb["leak_mot"]

    d = {name: d_line_flow(x[i] - x[j], p[lk], p[dk], rho, mu)
         for name, i, j, lk, dk in LINES}

    d_va = model.orifice_gain(p["A_valve_a"], rho, h["cd"]) * model.df_dp(x[P1A] - x[P2A])
    d_vb = model.orifice_gain(p["A_valve_b"], rho, h["cd"]) * model.df_dp(x[P1B] - x[P2B])
    d_ra = model.orifice_gain(ha["A_ret"], rho, h["cd"]) * model.df_dp(x[P4A] - model.P_TANK)
    d_rb = model.orifice_gain(hb["A_ret"], rho, h["cd"]) * model.df_dp(x[P4B] - model.P_TANK)

    band = h["relief_band"]
    g_rel = model.orifice_gain(h["A_relief_max"], rho, h["cd"])
    op = model.relief_opening(x[P1], p["p_crack"], band)
    dop = model.d_relief_opening(x[P1], p["p_crack"], band)
    d_rel = g_rel * (dop * model.f_dp(x[P1] - model.P_TANK)
                     + op * model.df_dp(x[P1] - model.P_TANK))

    J = np.zeros((12, 12))

    # every line contributes +d to its upstream column and -d to its downstream
    # one, in whichever rows it enters -- walked from LINES so the topology is
    # stated once
    def line_into(row: int, name: str, sign: float) -> None:
        _n, i, j, _lk, _dk = next(l for l in LINES if l[0] == name)
        J[row, i] += sign * d[name]
        J[row, j] -= sign * d[name]

    line_into(0, "supply", -1.0)                       # F0 = q_pump - q_supply
    J[0, P0] += -1.0 / h["R_leak"]

    line_into(1, "supply", +1.0)                       # F1 = supply - a - b - rel
    line_into(1, "line_a", -1.0)
    line_into(1, "line_b", -1.0)
    J[1, P1] += -d_rel

    line_into(2, "line_a", +1.0)                       # F2 = line_a - q_va
    J[2, P1A] += -d_va
    J[2, P2A] += d_va

    J[3, P1A] = d_va                                   # F3 = q_va - q_ma
    J[3, P2A] = -d_va - lk_a
    J[3, P3A] = lk_a
    J[3, WA] = -kd_a

    line_into(4, "ret_a", -1.0)                        # F4 = q_ma - q_ret_a
    J[4, P2A] += lk_a
    J[4, P3A] += -lk_a
    J[4, WA] += kd_a

    line_into(5, "ret_a", +1.0)                        # F5 = ret_a - q_reta
    J[5, P4A] += -d_ra

    J[6, P2A] = kt_a                                   # F6 = shaft a
    J[6, P3A] = -kt_a
    J[6, WA] = -model.d_load_torque(x[WA], p["c_load_a"], ha["t_coul"],
                                    ha["t_stat"], ha["w_strib"], ha["b_visc"])

    line_into(7, "line_b", +1.0)                       # F7 = line_b - q_vb
    J[7, P1B] += -d_vb
    J[7, P2B] += d_vb

    J[8, P1B] = d_vb                                   # F8 = q_vb - q_mb
    J[8, P2B] = -d_vb - lk_b
    J[8, P3B] = lk_b
    J[8, WB] = -kd_b

    line_into(9, "ret_b", -1.0)                        # F9 = q_mb - q_ret_b
    J[9, P2B] += lk_b
    J[9, P3B] += -lk_b
    J[9, WB] += kd_b

    line_into(10, "ret_b", +1.0)                       # F10 = ret_b - q_retb
    J[10, P4B] += -d_rb

    J[11, P2B] = kt_b                                  # F11 = shaft b
    J[11, P3B] = -kt_b
    J[11, WB] = -model.d_load_torque(x[WB], p["c_load_b"], hb["t_coul"],
                                     hb["t_stat"], hb["w_strib"], hb["b_visc"])
    return J


COLD_START = np.zeros(12)


def nominal_start(p: dict) -> np.ndarray:
    """The same three rules of thumb as `model.nominal_start`, plus the lines.

    The lines are *not* estimated -- they are assumed lossless, which is what a
    competent engineer guessing by hand would do. That is deliberate: it is the
    baseline the geometry has to beat, and letting the nominal guess know about
    pipe losses would be handing it the answer this circuit exists to test.
    """
    h = model.hardware(p)
    p1 = float(p["p_crack"])
    p3 = model.P_TANK
    p2 = model.P_TANK + 0.5 * (p1 - model.P_TANK)

    def speed(s: str) -> float:
        hs = model.shaft_hw(h, s)
        kt = hs["D_mot"] / (20.0 * np.pi)
        t_avail = max(p2 - p3, 0.0) * kt - hs["t_coul"]
        c_load = p[f"c_load_{s}"]
        if t_avail <= 0.0:
            return 0.0
        if c_load <= 0.0:
            return model.W_NOMINAL_MAX
        return float(min(np.sqrt(t_avail / c_load), model.W_NOMINAL_MAX))

    return np.array([p1, p1, p1, p2, p3, p3, speed("a"),
                     p1, p2, p3, p3, speed("b")], dtype=float)


def solve(p: dict, x0=None, tol: float = model.TOL,
          max_iter: int = model.MAX_ITER) -> dict:
    """Damped Newton, identical in structure to `model.solve` — only the system differs."""
    x = np.array(COLD_START if x0 is None else x0, dtype=float)
    F = residual(x, p)
    r = float(np.max(np.abs(F)))
    history = [r]
    iters, status = 0, "converged"

    while r > tol:
        if iters >= max_iter:
            status = "max_iter"
            break
        try:
            dx = np.linalg.solve(jacobian(x, p), -F)
        except np.linalg.LinAlgError:
            status = "singular_jacobian"
            break
        alpha = 1.0
        while True:
            x_new = x + alpha * dx
            F_new = residual(x_new, p)
            r_new = float(np.max(np.abs(F_new)))
            if np.isfinite(r_new) and r_new < (1.0 - 1e-4 * alpha) * r:
                break
            alpha *= 0.5
            if alpha < model.MIN_ALPHA:
                status = "line_search_stall"
                break
        if status != "converged":
            break
        x, F, r = x_new, F_new, r_new
        iters += 1
        history.append(r)
        if not np.all(np.isfinite(x)) or np.max(np.abs(x)) > model.DIVERGED_AT:
            status = "diverged"
            break

    return {"converged": status == "converged", "status": status,
            "iterations": iters, "residual_inf": r,
            "x": np.asarray(x).tolist(), "history": history}


# --- case bookkeeping -------------------------------------------------------

def param_vector(p: dict) -> np.ndarray:
    return np.array([p[k] for k in PARAM_NAMES], dtype=float)


def normalise(vec) -> np.ndarray:
    lo = np.array([PARAM_BOUNDS[k][0] for k in PARAM_NAMES])
    hi = np.array([PARAM_BOUNDS[k][1] for k in PARAM_NAMES])
    return (np.atleast_2d(np.asarray(vec, dtype=float)) - lo) / (hi - lo)


def sample_cases(n: int, seed: int) -> list[dict]:
    rng = np.random.default_rng(seed)
    u = np.empty((n, len(PARAM_NAMES)))
    for j in range(len(PARAM_NAMES)):
        u[:, j] = (rng.permutation(n) + rng.random(n)) / n
    lo = np.array([PARAM_BOUNDS[k][0] for k in PARAM_NAMES])
    hi = np.array([PARAM_BOUNDS[k][1] for k in PARAM_NAMES])
    return [dict(zip(PARAM_NAMES, row)) for row in lo + u * (hi - lo)]


def line_report(x, p: dict) -> list[dict]:
    """What each pipe run actually did — the numbers the drawing could not show.

    This is the payoff for the physics: a pressure *drop along a run*, and the
    regime the run sat in. Neither exists in a lumped model, so neither could
    ever have been drawn honestly before.
    """
    rho, mu = float(p["rho"]), float(p["mu"])
    out = []
    for name, i, j, lk, dk in LINES:
        dp = float(x[i] - x[j])
        q = float(line_flow(dp, p[lk], p[dk], rho, mu))
        re = reynolds(q, p[dk], rho, mu)
        out.append({"line": name, "length_m": float(p[lk]), "bore_mm": float(p[dk]),
                    "dp_bar": dp, "q_lmin": q, "reynolds": re,
                    "regime": "laminar" if re < 2300 else "turbulent"})
    return out


# --- the invariant, before any number is quoted -----------------------------

def central_jacobian(x, p: dict, rel_step: float = 1e-6) -> np.ndarray:
    n = len(x)
    J = np.zeros((n, n))
    for j in range(n):
        h = rel_step * max(abs(x[j]), 1.0)
        xp, xm = np.array(x, float), np.array(x, float)
        xp[j] += h
        xm[j] -= h
        J[:, j] = (residual(xp, p) - residual(xm, p)) / (2.0 * h)
    return J


def check_jacobian(n_cases: int = 40, seed: int = 7, tol: float = 1e-5) -> int:
    """Same discipline as `selftest.py`: this circuit's Jacobian is hand-derived
    across 12 rows and five shared pipe elements, and a transcription slip there
    would not crash -- it would quietly change the iteration counts this module
    is built to report."""
    rng = np.random.default_rng(seed)
    cases = sample_cases(n_cases, seed)
    worst, where = 0.0, ""

    def ladder(top: float) -> list[float]:
        """A strictly descending pressure ladder, pump outlet down to return.

        Sampled this way rather than independently for the reason `selftest.py`
        states: every element here is regularised near dp = 0, and a state with
        two adjacent nodes at the same pressure puts an element exactly on its
        kink, where a central difference measures the regularisation instead of
        the derivative. A real circuit never sits there -- flow only goes
        downhill -- so sampling a ladder is both the physical case and the one
        the check can actually read.
        """
        out, v = [], top
        for _ in range(6):
            out.append(v)
            v *= rng.uniform(0.55, 0.9)
        return out

    for i, p in enumerate(cases):
        a, b = ladder(rng.uniform(60.0, 240.0)), ladder(rng.uniform(60.0, 240.0))
        # p0 and p1 are shared by both branches; a's ladder supplies them
        x = np.array([a[0], a[1], a[2], a[3], a[4], a[5],
                      rng.uniform(80.0, 1600.0),
                      b[2], b[3], b[4], b[5],
                      rng.uniform(80.0, 1600.0)])
        Ja, Jn = jacobian(x, p), central_jacobian(x, p)
        scale = np.maximum(np.abs(Ja), np.abs(Jn))
        scale[scale < 1e-9] = 1.0
        rel = np.abs(Ja - Jn) / scale
        if rel.max() > worst:
            worst = float(rel.max())
            r, c = np.unravel_index(rel.argmax(), rel.shape)
            where = f"case {i}, J[{r},{c}] (d F[{r}] / d {STATE_NAMES[c]})"
    ok = worst <= tol
    print(f"  {'PASS' if ok else 'FAIL'}  analytic Jacobian == central differences"
          f"   worst relative error {worst:.2e}  ({where})")
    return int(ok)


# --- does the archive still pay when the machine has plumbing? --------------

def run(n_archive: int, n_query: int, out: Path | None) -> dict:
    """Sweep, archive what converged, then warm-start fresh cases from it."""
    print(f"sweeping {n_archive} cases on the geometry circuit ...", flush=True)
    kept, failed = [], 0
    for i, p in enumerate(sample_cases(n_archive, seed=1)):
        r = solve(p)
        if r["converged"]:
            kept.append({"case_id": f"geo-{i:04d}", "params": p, "x": r["x"],
                         "iterations": r["iterations"]})
        else:
            failed += 1
    if not kept:
        raise SystemExit("nothing converged -- the circuit or the bounds are wrong")

    norm = normalise(np.array([param_vector(k["params"]) for k in kept]))
    states = np.array([k["x"] for k in kept])
    print(f"  archive {len(kept)} kept, {failed} failed")

    queries = sample_cases(n_query, seed=99)
    arms = {"cold": [], "nominal": [], "warm": []}
    fails = {"cold": 0, "nominal": 0, "warm": 0}
    agree, dists = [], []
    for p in queries:
        q = normalise(param_vector(p))
        d = np.linalg.norm(norm - q, axis=1)
        j = int(np.argmin(d))
        dists.append(float(d[j]))
        got = {"cold": solve(p), "nominal": solve(p, x0=nominal_start(p)),
               "warm": solve(p, x0=states[j])}
        for k, r in got.items():
            if r["converged"]:
                arms[k].append(r["iterations"])
            else:
                fails[k] += 1
        if got["cold"]["converged"] and got["warm"]["converged"]:
            dx = np.abs(np.array(got["cold"]["x"]) - np.array(got["warm"]["x"]))
            agree.append(float(dx[PRESSURE_IDX].max()))

    tot = {k: int(sum(v)) for k, v in arms.items()}
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "circuit": "geometry", "unknowns": 12,
        "parameters": {"total": len(PARAM_NAMES), "geometric": len(GEOM_NAMES)},
        "archive": {"n": n_archive, "kept": len(kept), "failed": failed},
        "n_queries": n_query,
        "arms": {k: {"mean_iterations": float(np.mean(v)) if v else None,
                     "total_iterations": tot[k], "failures": fails[k]}
                 for k, v in arms.items()},
        "iteration_reduction_vs_nominal_pct": (
            float(100 * (1 - tot["warm"] / tot["nominal"])) if tot["nominal"] else None),
        "iteration_reduction_vs_cold_pct": (
            float(100 * (1 - tot["warm"] / tot["cold"])) if tot["cold"] else None),
        "agreement_max_dp_bar": max(agree) if agree else None,
        "neighbour_distance": {"mean": float(np.mean(dists)),
                               "max": float(np.max(dists))},
        "example_lines": line_report(states[0], kept[0]["params"]),
    }
    if out is not None:
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def retrieval_experiment(n_archive: int, n_query: int) -> dict:
    """Does retrieval still work when the difference between machines is plumbing?

    The question this module was built for. Four arms and two controls, because
    on an 18-parameter card "the archive helped" and "the index helped" are
    different claims and only one of them is interesting:

      * **random archived state** -- the floor. On the base circuit phase-1c
        found this beats the nominal guess on its own, because every archived
        state is a plausible operating point. If that holds here, the index is
        contributing nothing and the metric numbers are noise.
      * **oracle** -- solve from *every* archived state, take the cheapest. The
        real bound, defined by cost rather than by a distance in a space that
        mixes bar with rev/min. An earlier draft used the latter and it came
        out *worse* than the parameter metric, which is how it announced
        itself as not a bound at all.

    Between them, three metrics: the whole card, the 7 lumped parameters with
    geometry ignored, and geometry alone.
    """
    arch = [(p, r["x"]) for p, r in
            ((p, solve(p)) for p in sample_cases(n_archive, seed=1))
            if r["converged"]]
    states = np.array([x for _p, x in arch])
    lo = np.array([PARAM_BOUNDS[k][0] for k in PARAM_NAMES])
    hi = np.array([PARAM_BOUNDS[k][1] for k in PARAM_NAMES])
    N = (np.array([param_vector(p) for p, _x in arch]) - lo) / (hi - lo)

    metrics = {
        "all 18 params": list(range(len(PARAM_NAMES))),
        "7 lumped only": [PARAM_NAMES.index(k) for k in model.PARAM_NAMES],
        "11 geometry+fluid": [PARAM_NAMES.index(k)
                              for k in GEOM_NAMES + FLUID_NAMES],
    }
    labels = list(metrics) + ["nominal", "random archived state", "oracle"]
    tot = dict.fromkeys(labels, 0)
    found_oracle = dict.fromkeys(metrics, 0)
    rng = np.random.default_rng(3)

    for p in sample_cases(n_query, seed=99):
        v = (param_vector(p) - lo) / (hi - lo)
        # cost of starting from each archived state -- the oracle needs all of
        # them anyway, so every arm is scored off one table rather than
        # re-solving per arm
        costs = np.array([r["iterations"] if r["converged"] else 10 ** 6
                          for r in (solve(p, x0=s) for s in states)])
        best = int(costs.min())
        tot["oracle"] += best
        for label, idx in metrics.items():
            j = int(np.argmin(np.linalg.norm(N[:, idx] - v[idx], axis=1)))
            tot[label] += int(costs[j])
            found_oracle[label] += int(costs[j] == best)
        tot["random archived state"] += int(costs[rng.integers(len(arch))])
        rn = solve(p, x0=nominal_start(p))
        tot["nominal"] += rn["iterations"] if rn["converged"] else 0

    nom = tot["nominal"]
    return {
        "archive": len(arch), "n_queries": n_query,
        "arms": {k: {"total_iterations": tot[k],
                     "vs_nominal_pct": (float(100 * (1 - tot[k] / nom))
                                        if nom and k != "nominal" else None),
                     "found_oracle_pick": found_oracle.get(k)}
                 for k in labels},
    }


def report_retrieval(o: dict) -> None:
    print()
    print(f"--- can retrieval tell two machines apart when the difference is "
          f"plumbing? ---")
    print(f"  archive {o['archive']} · {o['n_queries']} fresh queries")
    print(f"  {'arm':28}{'total iters':>13}{'vs nominal':>12}{'= oracle':>12}")
    order = ["nominal", "random archived state", "7 lumped only",
             "11 geometry+fluid", "all 18 params", "oracle"]
    for k in order:
        a = o["arms"][k]
        pct = "--" if a["vs_nominal_pct"] is None else f"{a['vs_nominal_pct']:.1f}%"
        fo = ("" if a["found_oracle_pick"] is None
              else f"{a['found_oracle_pick']}/{o['n_queries']}")
        print(f"  {k:28}{a['total_iterations']:>13}{pct:>12}{fo:>12}")


def report(o: dict) -> None:
    print()
    print(f"--- geometry circuit: {o['unknowns']} unknowns, "
          f"{o['parameters']['total']} parameters "
          f"({o['parameters']['geometric']} geometric) ---")
    print(f"  archive {o['archive']['kept']}/{o['archive']['n']} kept "
          f"({o['archive']['failed']} failed) · {o['n_queries']} fresh queries")
    print(f"  {'arm':10}{'mean iters':>12}{'total':>9}{'failures':>10}")
    for k in ("cold", "nominal", "warm"):
        a = o["arms"][k]
        m = f"{a['mean_iterations']:.2f}" if a["mean_iterations"] is not None else "--"
        print(f"  {k:10}{m:>12}{a['total_iterations']:>9}{a['failures']:>10}")
    vn = o["iteration_reduction_vs_nominal_pct"]
    vc = o["iteration_reduction_vs_cold_pct"]
    print(f"  warm vs nominal: {vn:.1f}%   vs cold: {vc:.1f}%")
    if o["agreement_max_dp_bar"] is not None:
        print(f"  cold and warm agree to {o['agreement_max_dp_bar']:.2e} bar")
    print(f"  mean neighbour distance {o['neighbour_distance']['mean']:.3f} "
          f"in an {o['parameters']['total']}-D unit cube")
    print()
    print("  what the lines actually did, on one archived case:")
    print(f"  {'line':9}{'L (m)':>8}{'bore':>7}{'dp (bar)':>11}"
          f"{'Q (L/min)':>11}{'Re':>9}  regime")
    for l in o["example_lines"]:
        print(f"  {l['line']:9}{l['length_m']:>8.2f}{l['bore_mm']:>7.1f}"
              f"{l['dp_bar']:>11.3f}{l['q_lmin']:>11.2f}{l['reynolds']:>9.0f}"
              f"  {l['regime']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true",
                    help="check the analytic Jacobian and stop")
    ap.add_argument("--retrieval", action="store_true",
                    help="also run the retrieval-metric experiment (slow: it "
                         "solves every query from every archived state to get "
                         "an honest oracle)")
    ap.add_argument("--archive", type=int, default=300)
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--out", type=Path, default=Path("geometry_results.json"))
    args = ap.parse_args()

    print("geometry circuit selftest")
    if not check_jacobian():
        print("  Jacobian is wrong -- not running anything else")
        return 1
    if args.selftest:
        return 0
    payload = run(args.archive, args.queries, args.out)
    report(payload)
    if args.retrieval:
        payload["retrieval"] = retrieval_experiment(args.archive, args.queries)
        report_retrieval(payload["retrieval"])
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
