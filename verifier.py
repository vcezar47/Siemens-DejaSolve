"""Layer 3 — the verifier: decide whether reusing a solved case is legitimate.

Retrieval answers *which case is nearest*. That is not the same question as
*may I start from it*, and the Phase 1 benchmark shows why: the correlation
between setup distance and what the transfer actually costs is 0.18. Parameter
similarity is a weak proxy for physical transferability, so the gate is built
out of cheap physics rather than out of a distance threshold.

Two gates, at two moments:

**Before the solve** — compare the *recorded* regime of the source case against
a cheap estimate of the query's regime. No solve is allowed here: the estimates
use closed-form bounds only, because a gate that costs a solve is pointless.

**After the solve** — check the converged state is admissible. This is the one
that catches silent wrongness: a root sitting on the Stribeck downslope is
dynamically unstable, satisfies the equations to 1e-8, and is not an operating
point any machine can occupy. Newton cannot tell. The eigenvalues can.

Every refusal carries one line of plain English, because a gate an engineer
cannot argue with is a gate they will switch off.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

import model

#: absolute pressure floor -- below this the orifice law stops describing the
#: fluid, so a converged state down here is outside the model's validity
P_CAVITATION = -0.9   # bar gauge


@dataclass
class Verdict:
    admit: bool
    rule: str
    reason: str
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{'ADMIT ' if self.admit else 'REFUSE'} [{self.rule}] {self.reason}"


# --- cheap regime estimates (no solve allowed) ------------------------------

def estimate_regime(p: dict) -> dict:
    """Closed-form bounds on the regime a case will settle into.

    At rest the motors pass only leakage, so the pump deadheads against the
    relief valve and the manifold sits at roughly the cracking pressure. That
    fixes the torque available to break the shafts away, and bounds the flow
    the branches can absorb once turning — which in turn says whether the
    relief valve has to stay open. Both are inequalities, not predictions.
    """
    k_torque, k_disp = model.motor_constants(p)
    p_stall = min(p["p_crack"] + model.RELIEF_BAND, p["Q_nom"] * model.R_LEAK)
    tq_stall = p_stall * k_torque

    # ceiling on shaft speed: all stall torque spent against the quadratic load
    surplus = max(tq_stall - model.T_COUL, 0.0)
    w_ceiling = {s: float(np.sqrt(surplus / p[f"c_load_{s}"])) for s in ("a", "b")}
    q_absorbable = k_disp * (w_ceiling["a"] + w_ceiling["b"])
    q_available = p["Q_nom"] - p_stall / model.R_LEAK

    return {
        "stall_pressure_bar": p_stall,
        "stall_torque_Nm": tq_stall,
        "can_break_away": bool(tq_stall > model.T_STAT),
        "breakaway_margin": tq_stall / model.T_STAT,
        "w_ceiling": w_ceiling,
        "relief_must_open": bool(q_absorbable < q_available),
    }


class Verifier:
    """Gates transfers into a given archive.

    The envelope and the coverage radius are read off the archive itself rather
    than tuned: the verifier refuses to vouch for anything further out than the
    archive's own sampling, because beyond that it has no evidence.
    """

    def __init__(self, records: list[dict], coverage_percentile: float = 99.0):
        self.records = records
        params = np.array([[r["params"][k] for k in model.PARAM_NAMES] for r in records])
        self.lo, self.hi = params.min(axis=0), params.max(axis=0)
        self.coverage_radius = self._coverage_radius(params, coverage_percentile)

    @staticmethod
    def _coverage_radius(params: np.ndarray, pct: float) -> float:
        """How far apart the archive's own cases are — its resolution.

        A query further from every archived case than the archive's cases are
        from each other is extrapolation, whatever the parameters look like.
        """
        norm = model.normalise(params)
        d = np.linalg.norm(norm[:, None, :] - norm[None, :, :], axis=-1)
        np.fill_diagonal(d, np.inf)
        return float(np.percentile(d.min(axis=1), pct))

    # --- gate 1: before the solve -----------------------------------------

    def check_transfer(self, query: dict, source: dict, distance: float) -> Verdict:
        """May the query legitimately start from the source case's state?"""
        est = estimate_regime(query)
        src_regime = source["regime"]
        src_params = source["params"]
        det = {"estimate": est, "distance": distance,
               "coverage_radius": self.coverage_radius}

        # -- same circuit? transferring a state between different hardware is
        #    not a physics judgement call, it is a category error
        q_d = query.get("D_mot", model.D_MOT)
        s_d = src_params.get("D_mot", model.D_MOT)
        if abs(q_d - s_d) > 1e-9:
            return Verdict(False, "hardware",
                           f"source case is a different circuit "
                           f"({s_d:g} cm3/rev motor, query is {q_d:g})", det)

        # -- inside the archive's parameter envelope?
        vec = model.param_vector(query)
        for i, name in enumerate(model.PARAM_NAMES):
            if vec[i] < self.lo[i] or vec[i] > self.hi[i]:
                return Verdict(False, "envelope",
                               f"{name} = {vec[i]:.4g} is outside the archive "
                               f"({self.lo[i]:.4g} to {self.hi[i]:.4g})", det)

        # -- close enough that the archive has anything to say?
        if distance > self.coverage_radius:
            return Verdict(False, "coverage",
                           f"nearest case is {distance:.2f} away, beyond the "
                           f"archive's own {self.coverage_radius:.2f} spacing", det)

        # -- do the shafts do the same *kind* of thing in both cases?
        for s in ("a", "b"):
            src_spinning = src_regime[f"shaft_{s}"] != "stuck"
            if est["can_break_away"] != src_spinning:
                if src_spinning:
                    return Verdict(False, "breakaway",
                                   f"shaft {s} cannot break away here "
                                   f"({est['stall_torque_Nm']:.1f} Nm available vs "
                                   f"{model.T_STAT:.0f} Nm needed), but the source "
                                   f"case has it turning", det)
                return Verdict(False, "breakaway",
                               f"shaft {s} breaks away here "
                               f"({est['stall_torque_Nm']:.1f} Nm available), but the "
                               f"source case has it stuck", det)

        # -- same hydraulic regime?
        if est["relief_must_open"] and not src_regime["relief_open"]:
            return Verdict(False, "relief",
                           "the relief valve has to be open here, but it is shut "
                           "in the source case -- different hydraulic regime", det)

        return Verdict(True, "ok",
                       f"same regime, {distance:.2f} away in setup space", det)

    # --- gate 2: after the solve ------------------------------------------

    @staticmethod
    def check_solution(x, p: dict) -> Verdict:
        """Is this converged root an operating point at all?"""
        x = np.asarray(x, dtype=float)
        det = {}

        pressures = x[[0, 1, 2, 4, 5]]
        if np.min(pressures) < P_CAVITATION:
            return Verdict(False, "cavitation",
                           f"converged with {np.min(pressures):.1f} bar in the "
                           "circuit -- below vapour pressure, the model does not "
                           "describe this", det)

        st = model.stability(x, p)
        det["stability"] = st
        if not st["stable"]:
            shafts = ", ".join(st["unstable_shafts"]) or "hydraulic"
            return Verdict(False, "unstable",
                           f"converged onto a dynamically unstable root "
                           f"(shaft {shafts} sits on the friction downslope); "
                           "the equations are satisfied but no machine runs here",
                           det)

        return Verdict(True, "ok", "stable operating point", det)
