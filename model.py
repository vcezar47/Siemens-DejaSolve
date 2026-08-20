"""Hydraulic manifold driving two motors — physics and the initialisation solve.

Circuit (gauge pressures in bar, flows in L/min, speeds in rev/min):

        pump ──┬───────────────────────────── relief valve ──> tank
               │
              [p1]  manifold
               ├─ valve_a ─[p2a]─ MOTOR a ─[p3a]─ return ─> tank
               └─ valve_b ─[p2b]─ MOTOR b ─[p3b]─ return ─> tank

Each motor drives a quadratic load (fan/pump-like) through a friction
interface. Unknowns are five pressures and two shaft speeds:

    x = [p1, p2a, p3a, w_a, p2b, p3b, w_b]

Steady state is a 7x7 nonlinear algebraic system — flow balance at each
hydraulic node, torque balance at each shaft. This is the *initialisation
problem* a system simulator solves before its first time step, and it is what
Déjà Solve warm-starts. Warm-starting changes only the guess handed to Newton;
it does not change the physics of the case.

Two things make it genuinely hard, and both are ordinary mechatronics:

* turbulent orifice flow, Q ~ sign(dp)*sqrt(|dp|), whose slope blows up as
  dp -> 0 — so a guess with every node at the same pressure sits on the worst
  spot of the curve;
* **Stribeck friction**, where breakaway torque decays to Coulomb torque as
  the shaft picks up speed. That decaying branch has negative slope, so the
  torque balance can have three roots and the basin of attraction around the
  operating point is narrow. A cold guess falls outside it often.
"""

from __future__ import annotations

import numpy as np

# --- fixed circuit constants (not swept: these are "the hardware") ----------
P_TANK = 0.0          # bar, gauge
A_RET = 10.0          # mm^2, return line restriction
A_RELIEF_MAX = 25.0   # mm^2, relief valve area fully open
RELIEF_BAND = 15.0    # bar, cracking -> fully open
R_LEAK = 62.5         # bar per L/min of pump leakage (~4 L/min at 250 bar)
CD = 0.7              # discharge coefficient
P_REG = 1.0e-3        # bar, laminar/turbulent transition of the orifice law

D_MOT = 32.0          # cm^3/rev, motor displacement
LEAK_MOT = 0.02       # L/min per bar, cross-port leakage
T_COUL = 4.0          # Nm, Coulomb (kinetic) friction torque
T_STAT = 14.0         # Nm, breakaway torque   (Stribeck needs T_STAT > T_COUL)
W_STRIB = 60.0        # rev/min, Stribeck velocity
W_REG = 5.0           # rev/min, zero-velocity regularisation
B_VISC = 2.0e-3       # Nm per rev/min, viscous drag

#: torque per bar of motor pressure drop, T[Nm] = dp[bar] * K_TORQUE
K_TORQUE = D_MOT / (20.0 * np.pi)
#: flow per rev/min of shaft speed, Q[L/min] = w[rev/min] * K_DISP
K_DISP = D_MOT / 1000.0


#: Circuit constants a case may *state* instead of inheriting. Everything here
#: is a real physical property of real hardware -- a discharge coefficient, a
#: breakaway torque, a cross-port leakage -- and every one of them was a module
#: constant until an engineer pointed out that a real model carries hundreds of
#: parameters rather than seven (§0b).
#:
#: With the seven swept parameters this takes a Case Card to **25 physical
#: parameters**, and the two branches stop being forced to be identical
#: hardware, which is the part that makes it more than a longer list: shaft a
#: and shaft b can now be different motors with different friction.
#:
#: **Defaults are preserved exactly.** A case that states none of these solves
#: bit-identically to the same case before they were promoted -- asserted by
#: `selftest.py`, and by the phase-1 summary hash, which must not move.
HARDWARE = {
    # shared by the whole circuit
    "cd": CD,
    "R_leak": R_LEAK,
    "A_relief_max": A_RELIEF_MAX,
    "relief_band": RELIEF_BAND,
    # per branch -- the two need not be the same hardware any more
    "D_mot_a": D_MOT, "D_mot_b": D_MOT,
    "A_ret_a": A_RET, "A_ret_b": A_RET,
    "leak_mot_a": LEAK_MOT, "leak_mot_b": LEAK_MOT,
    "t_coul_a": T_COUL, "t_coul_b": T_COUL,
    "t_stat_a": T_STAT, "t_stat_b": T_STAT,
    "w_strib_a": W_STRIB, "w_strib_b": W_STRIB,
    "b_visc_a": B_VISC, "b_visc_b": B_VISC,
}


def hardware(p: dict) -> dict:
    """Resolve every circuit constant for this case: stated, or the default.

    ``D_mot`` stays a valid shorthand for "both motors", because `fold.py`
    builds its variant circuit that way and every Phase 2 number was measured
    through it. Removing the shorthand would silently re-point that experiment.
    """
    h = {k: float(p.get(k, v)) for k, v in HARDWARE.items()}
    if "D_mot" in p:
        h["D_mot_a"] = h["D_mot_b"] = float(p["D_mot"])
    return h


def shaft_hw(h: dict, s: str) -> dict:
    """The per-branch constants for shaft `s`, keyed without the suffix."""
    return {"D_mot": h[f"D_mot_{s}"], "A_ret": h[f"A_ret_{s}"],
            "leak_mot": h[f"leak_mot_{s}"], "t_coul": h[f"t_coul_{s}"],
            "t_stat": h[f"t_stat_{s}"], "w_strib": h[f"w_strib_{s}"],
            "b_visc": h[f"b_visc_{s}"]}


def motor_constants(p: dict) -> tuple[float, float]:
    """Torque and displacement constants for this case's motor.

    Displacement is hardware, so it normally comes from the module constant.
    A case may override it with ``D_mot`` to describe a circuit built around a
    different motor — which is how the fold variant in ``fold.py`` is built
    without disturbing the base circuit or anything measured on it.
    """
    d = p.get("D_mot", D_MOT)
    return d / (20.0 * np.pi), d / 1000.0

#: the swept case setup, in a fixed order — this is the retrieval feature vector
PARAM_NAMES = (
    "Q_nom",       # L/min    pump nominal delivery
    "A_valve_a",   # mm^2     metering valve, branch a
    "A_valve_b",   # mm^2     metering valve, branch b
    "c_load_a",    # Nm per (rev/min)^2   quadratic load on motor a
    "c_load_b",    # Nm per (rev/min)^2   quadratic load on motor b
    "p_crack",     # bar      relief valve cracking pressure
    "rho",         # kg/m^3   fluid density
)

PARAM_BOUNDS = {
    "Q_nom": (30.0, 90.0),
    "A_valve_a": (0.6, 12.0),
    "A_valve_b": (0.6, 12.0),
    "c_load_a": (0.7e-5, 3.0e-5),
    "c_load_b": (0.7e-5, 3.0e-5),
    "p_crack": (120.0, 260.0),
    "rho": (800.0, 900.0),
}

STATE_NAMES = ("p1", "p2a", "p3a", "w_a", "p2b", "p3b", "w_b")
STATE_UNITS = ("bar", "bar", "bar", "rev/min", "bar", "bar", "rev/min")

#: the default guess a tool uses when it knows nothing about the case — every
#: node at tank pressure, every shaft at rest. This is the "start from zero"
#: that the whole project is about.
COLD_START = np.zeros(7)

#: ceiling on the nominal guess, so a degenerate case setup cannot hand Newton
#: a starting speed no shaft in this circuit could reach
W_NOMINAL_MAX = 5000.0     # rev/min


def nominal_start(p: dict) -> np.ndarray:
    """The guess a *competent* tool makes from the case setup alone.

    ``COLD_START`` is a flat start -- every node at tank pressure, every shaft
    at rest. It is the weakest defensible baseline, and it is weak here for a
    reason this module already documents: equal pressures put every orifice on
    the worst spot of the sqrt curve, and zero speed sits in the Stribeck
    regularisation. Measuring a warm start against it overstates the win.

    This is the stronger baseline. Still no archive and still no solve -- only
    the case parameters and three rules of thumb:

      * the pump runs against the relief valve, so the manifold sits at
        ``p_crack``;
      * about half of that is metered away across the branch valve, and the
        return line is near tank;
      * each shaft settles where motor torque balances its quadratic load,
        less Coulomb friction.

    It costs no residual evaluation, so any iteration it saves is free. Both
    baselines are reported, because the gap between them *is* a result: it
    separates "warm start beats starting from nothing" from "warm start beats
    a good engineering guess", and only the second claim is interesting.
    """
    h = hardware(p)
    p1 = float(p["p_crack"])
    p3 = P_TANK
    p2 = P_TANK + 0.5 * (p1 - P_TANK)

    def speed(s: str) -> float:
        hs = shaft_hw(h, s)
        kt = hs["D_mot"] / (20.0 * np.pi)
        t_avail = max(p2 - p3, 0.0) * kt - hs["t_coul"]
        c_load = p[f"c_load_{s}"]
        if t_avail <= 0.0:
            return 0.0
        if c_load <= 0.0:
            return W_NOMINAL_MAX
        return float(min(np.sqrt(t_avail / c_load), W_NOMINAL_MAX))

    return np.array([p1, p2, p3, speed("a"),
                     p2, p3, speed("b")], dtype=float)


# --- constitutive relations -------------------------------------------------

def orifice_gain(area_mm2: float, rho: float, cd: float = CD) -> float:
    """Coefficient k such that Q[L/min] = k * f_dp(dp[bar]) for a sharp orifice."""
    return 6e4 * cd * area_mm2 * 1e-6 * np.sqrt(2e5 / rho)


def f_dp(dp):
    """Regularised sqrt pressure-flow law: -> sign(dp)*sqrt(|dp|) away from 0."""
    return dp / (dp * dp + P_REG * P_REG) ** 0.25


def df_dp(dp):
    """d/d(dp) of :func:`f_dp`. Equals 1/sqrt(P_REG) at the origin."""
    q = dp * dp + P_REG * P_REG
    return (0.5 * dp * dp + P_REG * P_REG) * q ** -1.25


def relief_opening(p1: float, p_crack: float,
                   band: float = RELIEF_BAND) -> float:
    """Fraction of relief valve area open — C1-smooth ramp over the band."""
    s = (p1 - p_crack) / band
    s = min(max(s, 0.0), 1.0)
    return s * s * (3.0 - 2.0 * s)


def d_relief_opening(p1: float, p_crack: float,
                     band: float = RELIEF_BAND) -> float:
    s = (p1 - p_crack) / band
    if s <= 0.0 or s >= 1.0:
        return 0.0
    return 6.0 * s * (1.0 - s) / band


# The friction constants are arguments with module defaults rather than reads
# of the module: every existing caller keeps working untouched, and a case that
# gives shaft a a different motor from shaft b gets the right curve on each.
# W_REG stays global on purpose -- it is numerical regularisation, not hardware.

def friction(w, t_coul: float = T_COUL, t_stat: float = T_STAT,
             w_strib: float = W_STRIB):
    """Stribeck friction torque [Nm] on a shaft turning at w [rev/min]."""
    return (t_coul + (t_stat - t_coul) * np.exp(-(w / w_strib) ** 2)) * np.tanh(w / W_REG)


def d_friction(w, t_coul: float = T_COUL, t_stat: float = T_STAT,
               w_strib: float = W_STRIB):
    """d/dw of :func:`friction`. Negative over part of the range — that is the
    Stribeck dip, and it is why this problem has more than one root."""
    env = t_coul + (t_stat - t_coul) * np.exp(-(w / w_strib) ** 2)
    d_env = (t_stat - t_coul) * np.exp(-(w / w_strib) ** 2) * (-2.0 * w / w_strib ** 2)
    t = np.tanh(w / W_REG)
    # sech^2 written as 1 - tanh^2 so it cannot overflow at large |w|
    return d_env * t + env * (1.0 - t * t) / W_REG


def load_torque(w, c_load, t_coul: float = T_COUL, t_stat: float = T_STAT,
                w_strib: float = W_STRIB, b_visc: float = B_VISC):
    """Total resisting torque: friction + viscous drag + quadratic load."""
    return friction(w, t_coul, t_stat, w_strib) + b_visc * w + c_load * w * abs(w)


def d_load_torque(w, c_load, t_coul: float = T_COUL, t_stat: float = T_STAT,
                  w_strib: float = W_STRIB, b_visc: float = B_VISC):
    return d_friction(w, t_coul, t_stat, w_strib) + b_visc + 2.0 * c_load * abs(w)


# --- residual and Jacobian --------------------------------------------------

def residual(x, p: dict) -> np.ndarray:
    """Flow imbalance [L/min] at the 5 nodes, torque imbalance [Nm] at 2 shafts."""
    p1, p2a, p3a, wa, p2b, p3b, wb = x
    rho = p["rho"]
    h = hardware(p)
    ha, hb = shaft_hw(h, "a"), shaft_hw(h, "b")
    kt_a, kd_a = ha["D_mot"] / (20.0 * np.pi), ha["D_mot"] / 1000.0
    kt_b, kd_b = hb["D_mot"] / (20.0 * np.pi), hb["D_mot"] / 1000.0
    g_va = orifice_gain(p["A_valve_a"], rho, h["cd"])
    g_vb = orifice_gain(p["A_valve_b"], rho, h["cd"])
    g_ra = orifice_gain(ha["A_ret"], rho, h["cd"])
    g_rb = orifice_gain(hb["A_ret"], rho, h["cd"])
    g_rel = orifice_gain(h["A_relief_max"], rho, h["cd"])

    q_pump = p["Q_nom"] - p1 / h["R_leak"]
    q_rel = (g_rel * relief_opening(p1, p["p_crack"], h["relief_band"])
             * f_dp(p1 - P_TANK))
    q_va = g_va * f_dp(p1 - p2a)
    q_vb = g_vb * f_dp(p1 - p2b)

    q_ma = kd_a * wa + ha["leak_mot"] * (p2a - p3a)
    q_mb = kd_b * wb + hb["leak_mot"] * (p2b - p3b)
    q_ra = g_ra * f_dp(p3a - P_TANK)
    q_rb = g_rb * f_dp(p3b - P_TANK)

    return np.array([
        q_pump - q_va - q_vb - q_rel,                       # manifold node
        q_va - q_ma,                                        # motor a inlet
        q_ma - q_ra,                                        # motor a outlet
        (p2a - p3a) * kt_a - load_torque(                   # shaft a
            wa, p["c_load_a"], ha["t_coul"], ha["t_stat"],
            ha["w_strib"], ha["b_visc"]),
        q_vb - q_mb,                                        # motor b inlet
        q_mb - q_rb,                                        # motor b outlet
        (p2b - p3b) * kt_b - load_torque(                   # shaft b
            wb, p["c_load_b"], hb["t_coul"], hb["t_stat"],
            hb["w_strib"], hb["b_visc"]),
    ])


def jacobian(x, p: dict) -> np.ndarray:
    """Analytic Jacobian.

    Analytic rather than finite-difference on purpose: the orifice law varies
    on a scale of P_REG = 1e-3 bar near the origin and the friction law on a
    scale of W_REG = 5 rev/min, and a finite-difference step of the usual size
    steps straight over both. It also makes the benchmark honest — the solver
    is given the exact derivative and *still* fails from a cold guess.
    """
    p1, p2a, p3a, wa, p2b, p3b, wb = x
    rho = p["rho"]
    h = hardware(p)
    ha, hb = shaft_hw(h, "a"), shaft_hw(h, "b")
    kt_a, kd_a = ha["D_mot"] / (20.0 * np.pi), ha["D_mot"] / 1000.0
    kt_b, kd_b = hb["D_mot"] / (20.0 * np.pi), hb["D_mot"] / 1000.0
    g_va = orifice_gain(p["A_valve_a"], rho, h["cd"])
    g_vb = orifice_gain(p["A_valve_b"], rho, h["cd"])
    g_ra = orifice_gain(ha["A_ret"], rho, h["cd"])
    g_rb = orifice_gain(hb["A_ret"], rho, h["cd"])
    g_rel = orifice_gain(h["A_relief_max"], rho, h["cd"])

    d_va = g_va * df_dp(p1 - p2a)
    d_vb = g_vb * df_dp(p1 - p2b)
    d_ra = g_ra * df_dp(p3a - P_TANK)
    d_rb = g_rb * df_dp(p3b - P_TANK)

    band = h["relief_band"]
    op = relief_opening(p1, p["p_crack"], band)
    dop = d_relief_opening(p1, p["p_crack"], band)
    d_rel = g_rel * (dop * f_dp(p1 - P_TANK) + op * df_dp(p1 - P_TANK))

    lk_a, lk_b = ha["leak_mot"], hb["leak_mot"]

    J = np.zeros((7, 7))
    # manifold: pump - valve_a - valve_b - relief
    J[0, 0] = -1.0 / h["R_leak"] - d_va - d_vb - d_rel
    J[0, 1] = d_va
    J[0, 4] = d_vb
    # motor a inlet: q_va - q_ma
    J[1, 0] = d_va
    J[1, 1] = -d_va - lk_a
    J[1, 2] = lk_a
    J[1, 3] = -kd_a
    # motor a outlet: q_ma - q_ra
    J[2, 1] = lk_a
    J[2, 2] = -lk_a - d_ra
    J[2, 3] = kd_a
    # shaft a torque balance
    J[3, 1] = kt_a
    J[3, 2] = -kt_a
    J[3, 3] = -d_load_torque(wa, p["c_load_a"], ha["t_coul"], ha["t_stat"],
                             ha["w_strib"], ha["b_visc"])
    # motor b inlet
    J[4, 0] = d_vb
    J[4, 4] = -d_vb - lk_b
    J[4, 5] = lk_b
    J[4, 6] = -kd_b
    # motor b outlet
    J[5, 4] = lk_b
    J[5, 5] = -lk_b - d_rb
    J[5, 6] = kd_b
    # shaft b torque balance
    J[6, 4] = kt_b
    J[6, 5] = -kt_b
    J[6, 6] = -d_load_torque(wb, p["c_load_b"], hb["t_coul"], hb["t_stat"],
                             hb["w_strib"], hb["b_visc"])
    return J


# --- the solve --------------------------------------------------------------

TOL = 1e-8          # max-norm of the residual (L/min on nodes, Nm on shafts)
MAX_ITER = 60
MIN_ALPHA = 1e-4    # backtracking floor
DIVERGED_AT = 1e7

#: textbook forward-difference step, sqrt(machine epsilon)
FD_STEP = 1.49e-8


def jacobian_fd(x, p: dict, F0, step: float = FD_STEP) -> np.ndarray:
    """Forward-difference Jacobian — what a solver gets when a component in the
    library does not supply analytic derivatives.

    The step size matters far more here than it looks. The orifice law varies
    on a scale of P_REG = 1e-3 bar and the friction law on W_REG = 5 rev/min,
    so a step much larger than the textbook sqrt(eps) steps over the very
    features that make the problem hard, and the resulting search direction is
    wrong in exactly the region where it needs to be right. ``bench.py``
    reports the sensitivity rather than picking a step that flatters anyone.
    """
    n = len(x)
    J = np.empty((n, n))
    for j in range(n):
        h = step * max(1.0, abs(x[j]))
        xp = np.array(x, dtype=float)
        xp[j] += h
        J[:, j] = (residual(xp, p) - F0) / h
    return J


def solve(p: dict, x0=None, tol: float = TOL, max_iter: int = MAX_ITER,
          jac_mode: str = "analytic", fd_step: float = FD_STEP) -> dict:
    """Damped Newton with backtracking line search on the steady-state system.

    The *only* thing that ever differs between a cold and a warm run is ``x0``.
    Same residual, same Jacobian, same tolerance, same solver — so a converged
    warm run and a converged cold run agree to tolerance, and the only things
    that move are the iteration count and whether it converges at all.

    ``jac_mode`` selects an exact analytic Jacobian or a finite-difference one.
    Analytic is the conservative choice for this project: it is the best case
    for the cold-start baseline, so any advantage measured against it is real.
    """
    x = np.array(COLD_START if x0 is None else x0, dtype=float)
    F = residual(x, p)
    r = float(np.max(np.abs(F)))
    history = [r]
    iters = 0
    status = "converged"

    while r > tol:
        if iters >= max_iter:
            status = "max_iter"
            break
        J = (jacobian(x, p) if jac_mode == "analytic"
             else jacobian_fd(x, p, F, fd_step))
        try:
            dx = np.linalg.solve(J, -F)
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
            if alpha < MIN_ALPHA:
                status = "line_search_stall"
                break
        if status != "converged":
            break

        x, F, r = x_new, F_new, r_new
        iters += 1
        history.append(r)

        if not np.all(np.isfinite(x)) or np.max(np.abs(x)) > DIVERGED_AT:
            status = "diverged"
            break

    return {
        "converged": status == "converged",
        "status": status,
        "iterations": iters,
        "residual_inf": r,
        "x": np.asarray(x).tolist(),
        "history": history,
    }


# --- case bookkeeping -------------------------------------------------------

def param_vector(p: dict) -> np.ndarray:
    return np.array([p[k] for k in PARAM_NAMES], dtype=float)


def normalise(vec) -> np.ndarray:
    """Map param vectors into the unit cube using the sweep bounds, so that
    'nearest case' means something across parameters with different units."""
    lo = np.array([PARAM_BOUNDS[k][0] for k in PARAM_NAMES])
    hi = np.array([PARAM_BOUNDS[k][1] for k in PARAM_NAMES])
    return (np.atleast_2d(np.asarray(vec, dtype=float)) - lo) / (hi - lo)


# --- dynamic stability -----------------------------------------------------
#
# The steady state solved above is the equilibrium of a dynamic system: oil
# compressibility gives each node a pressure state, each shaft has inertia.
# Writing that system as  dx/dt = S * F(x)  with S a positive diagonal scaling
# lets us ask whether a converged root is an *operating point* at all.
#
# This matters because Newton will happily converge onto a root sitting on the
# Stribeck downslope, where d(load torque)/dw < 0. Such a root satisfies the
# equations to 1e-8 and is dynamically unstable — no real machine ever sits
# there. It is the concrete form "silently wrong" takes in this model.

BULK = 15000.0      # bar, effective bulk modulus of the oil
V_NODE = 0.5        # L, lumped volume at each pressure node
J_SHAFT = 0.05      # kg m^2, shaft + load inertia


def dynamic_scales() -> np.ndarray:
    """Diagonal S mapping residuals to state derivatives, in units per second.

    Pressure rows: dp/dt [bar/s]      = (BULK / (60 * V)) * Q_net [L/min]
    Shaft rows:    dw/dt [rev/min/s]  = (60 / (2*pi*J)) * T_net [Nm]
    """
    s = np.empty(7)
    s[[0, 1, 2, 4, 5]] = BULK / (60.0 * V_NODE)
    s[[3, 6]] = 60.0 / (2.0 * np.pi * J_SHAFT)
    return s


def stability(x, p: dict) -> dict:
    """Eigenvalues of the linearised dynamics at a converged steady state."""
    A = dynamic_scales()[:, None] * jacobian(x, p)
    eig = np.linalg.eigvals(A)
    max_real = float(np.max(eig.real))
    return {
        "stable": bool(max_real < 0.0),
        "max_real_eig": max_real,
        "unstable_shafts": [
            name for name, i in (("a", 3), ("b", 6))
            if d_load_torque(float(x[i]), p[f"c_load_{name}"],
                             **{k: shaft_hw(hardware(p), name)[k] for k in
                                ("t_coul", "t_stat", "w_strib", "b_visc")}) < 0.0
        ],
    }


def shaft_regime(w: float) -> str:
    """Which part of the friction curve a shaft has settled on."""
    if abs(w) < 2.0 * W_REG:
        return "stuck"
    if abs(w) < W_STRIB:
        return "stribeck"      # the negative-slope branch
    return "viscous"


def regime(x, p: dict) -> dict:
    """Qualitative operating regime of a converged solution.

    Cheap to compute, and exactly the kind of 'useful information from a
    successful simulation' the archive exists to keep. Phase 2's verifier gates
    transfer on it: two cases with nearby parameters but different regimes are
    not safe to warm-start from each other.
    """
    p1 = float(x[0])
    op = relief_opening(p1, p["p_crack"])
    q_rel = orifice_gain(A_RELIEF_MAX, p["rho"]) * op * f_dp(p1 - P_TANK)
    return {
        "relief_open": bool(op > 1e-9),
        "relief_fraction": float(op),
        "relief_flow_share": float(q_rel / p["Q_nom"]) if p["Q_nom"] else 0.0,
        "p_manifold": p1,
        "shaft_a": shaft_regime(float(x[3])),
        "shaft_b": shaft_regime(float(x[6])),
    }
