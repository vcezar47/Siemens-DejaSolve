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

**Not every refusal is the same kind of statement**, and the two engineers
interviewed on 19 Aug were explicit about which one they want: *generate a
report and give out a warning, and leave it up to the engineer to proceed with
the simulation or not.* So a verdict carries a **severity** as well as a
decision:

  * ``warn``  -- a judgement about *transferring* a state. The system is
    unsure, not certain. It reports, recommends against, and lets the engineer
    override. Every gate-1 rule here is of this kind except ``hardware``.
  * ``block`` -- a statement of *fact* about the data or the physics: the
    source case is a different circuit, or the converged root is one no machine
    can sit at. There is nothing for an engineer to decide, so no override is
    offered.

The line is: **the engineer decides what to do with a risk; the system decides
what is a fact.** It falls exactly where the two gates already sat -- before
the solve the verifier is *estimating*, after the solve it is *measuring*.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

import model

#: absolute pressure floor -- below this the orifice law stops describing the
#: fluid, so a converged state down here is outside the model's validity
P_CAVITATION = -0.9   # bar gauge


#: How far two cases' hardware may differ and still count as the same machine.
#: Not a physics judgement -- it is manufacturing scatter. Two units built to
#: one drawing are never bit-identical, and an exact-match rule discovers that
#: the hard way: `wide_sweep.py --tolerance 0.02` refuses **200 of 200**
#: transfers, including every same-machine one, which is a gate nobody would
#: keep switched on.
#:
#: 5% is a stated assumption rather than a tuned constant, and `wide_sweep.py`
#: measures the thing that would make it wrong -- the band at which a genuinely
#: different design starts being admitted as the same machine.
#:
#: **Aggregate, not per-constant, and that distinction is the whole rule.** The
#: obvious form -- refuse if *any* constant is out of band -- is a multiple
#: comparisons problem: with 18 constants each carrying independent scatter, the
#: chance that at least one exceeds the band is high even when every one is
#: within tolerance. Measured: at 2% scatter the per-constant form refused 150
#: of 200 same-machine transfers. Comparing the *norm* of the relative
#: difference averages the scatter instead of taking its worst draw, so the rule
#: stops degrading as the parameter count grows -- the same failure mode
#: `dimensionality.py` finds in the coverage rule, caught here before shipping.
HARDWARE_REL_TOL = 0.05

#: rules where "proceed anyway" is not a judgement an engineer can make. A
#: source case on different hardware satisfies different equations -- reusing
#: its state is a category error, not a risk to be weighed.
BLOCKING_RULES = frozenset({"hardware"})


@dataclass
class Verdict:
    admit: bool
    rule: str
    reason: str
    details: dict = field(default_factory=dict)
    #: ok | warn | block -- derived from the rule unless stated explicitly
    severity: str = ""

    def __post_init__(self) -> None:
        if not self.severity:
            self.severity = ("ok" if self.admit
                             else "block" if self.rule in BLOCKING_RULES
                             else "warn")

    @property
    def overridable(self) -> bool:
        """May an engineer accept this verdict's risk and proceed regardless?"""
        return self.severity == "warn"

    def __str__(self) -> str:
        tag = {"ok": "ADMIT", "warn": "WARN ", "block": "BLOCK"}[self.severity]
        return f"{tag} [{self.rule}] {self.reason}"


# --- cheap regime estimates (no solve allowed) ------------------------------

def estimate_regime(p: dict) -> dict:
    """Closed-form bounds on the regime a case will settle into.

    At rest the motors pass only leakage, so the pump deadheads against the
    relief valve and the manifold sits at roughly the cracking pressure. That
    fixes the torque available to break the shafts away, and bounds the flow
    the branches can absorb once turning — which in turn says whether the
    relief valve has to stay open. Both are inequalities, not predictions.

    The top-level ``stall_torque_Nm`` / ``can_break_away`` / ``breakaway_margin``
    treat the motor and friction constants as shared across both branches --
    true of every case in this archive before the 18 hardware constants were
    promoted (§0b), and left exactly as they were computed then: this is what
    `agent_select.py`'s physics ranker reads, and changing what these three
    keys mean would silently move an already-measured result out from under it.

    ``breakaway`` is the per-shaft version gate 1 below actually needs. Since
    the promotion, the two branches can have independent motors (``D_mot_a`` /
    ``D_mot_b``), independent breakaway torque (``t_stat_a`` / ``t_stat_b``)
    and independent Coulomb friction (``t_coul_a`` / ``t_coul_b``) -- so a
    single circuit-wide "can it break away" is a category error the moment
    shaft a and shaft b would answer it differently, which is exactly the case
    the gate below used to refuse unconditionally: whichever shaft disagreed
    with the shared estimate failed its comparison, so a source case with one
    shaft turning and one stuck could never be admitted no matter what
    ``can_break_away`` said.
    """
    k_torque, k_disp = model.motor_constants(p)
    p_stall = min(p["p_crack"] + model.RELIEF_BAND, p["Q_nom"] * model.R_LEAK)
    tq_stall = p_stall * k_torque

    # ceiling on shaft speed: all stall torque spent against the quadratic load
    surplus = max(tq_stall - model.T_COUL, 0.0)
    w_ceiling = {s: float(np.sqrt(surplus / p[f"c_load_{s}"])) for s in ("a", "b")}
    q_absorbable = k_disp * (w_ceiling["a"] + w_ceiling["b"])
    q_available = p["Q_nom"] - p_stall / model.R_LEAK

    breakaway = {}
    for s in ("a", "b"):
        hs = model.shaft_hw(model.hardware(p), s)
        k_t_s, _ = model.motor_constants(p, s)
        tq_s = p_stall * k_t_s
        surplus_s = max(tq_s - hs["t_coul"], 0.0)
        breakaway[s] = {
            "stall_torque_Nm": float(tq_s),
            "can_break_away": bool(tq_s > hs["t_stat"]),
            "breakaway_margin": (float(tq_s / hs["t_stat"])
                                 if hs["t_stat"] else float("inf")),
            "w_ceiling": float(np.sqrt(surplus_s / p[f"c_load_{s}"])),
        }

    return {
        "stall_pressure_bar": p_stall,
        "stall_torque_Nm": tq_stall,
        "can_break_away": bool(tq_stall > model.T_STAT),
        "breakaway_margin": tq_stall / model.T_STAT,
        "w_ceiling": w_ceiling,
        "relief_must_open": bool(q_absorbable < q_available),
        "breakaway": breakaway,
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
        """May the query legitimately start from the source case's state?

        Everything decided here is an *estimate* made before any solve, so all
        of it is advisory (``warn``) except the hardware check -- see the
        severity note in the module docstring.
        """
        est = estimate_regime(query)
        src_regime = source["regime"]
        src_params = source["params"]
        det = {"estimate": est, "distance": distance,
               "coverage_radius": self.coverage_radius}

        # -- same circuit? transferring a state between different hardware is
        #    not a physics judgement call, it is a category error.
        #
        #    Every promoted constant is compared, not just the motor: once a
        #    case can state its own breakaway torque or cross-port leakage, two
        #    cases agreeing on the seven swept parameters can still be different
        #    machines. Cases that state none of them resolve to the defaults on
        #    both sides, so an archive built before the promotion behaves
        #    exactly as it did.
        q_hw, s_hw = model.hardware(query), model.hardware(src_params)
        rel = {k: abs(q_hw[k] - s_hw[k]) / max(abs(q_hw[k]), abs(s_hw[k]), 1e-30)
               for k in q_hw}
        spread = float(np.sqrt(np.mean(np.square(list(rel.values())))))
        det["hardware_spread"] = spread
        if spread > HARDWARE_REL_TOL:
            k = max(rel, key=rel.get)
            return Verdict(False, "hardware",
                           f"source case is a different circuit: hardware differs "
                           f"by {spread:.0%} overall, worst is {k} at "
                           f"{s_hw[k]:g} there against {q_hw[k]:g} here", det)


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
        #
        # Checked per shaft, against that shaft's own breakaway estimate. It
        # used to compare both shafts against one circuit-wide `can_break_away`,
        # so a source case with shaft a turning and shaft b stuck failed one of
        # the two comparisons whatever that shared estimate said -- refusing
        # every mixed-state transfer unconditionally, not just the ones that
        # actually disagree.
        for s in ("a", "b"):
            bw = est["breakaway"][s]
            src_spinning = src_regime[f"shaft_{s}"] != "stuck"
            if bw["can_break_away"] != src_spinning:
                if src_spinning:
                    return Verdict(False, "breakaway",
                                   f"shaft {s} cannot break away here "
                                   f"({bw['stall_torque_Nm']:.1f} Nm available vs "
                                   f"{model.shaft_hw(model.hardware(query), s)['t_stat']:.0f} "
                                   f"Nm needed), but the source case has it turning", det)
                return Verdict(False, "breakaway",
                               f"shaft {s} breaks away here "
                               f"({bw['stall_torque_Nm']:.1f} Nm available), but the "
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
                           "describe this", det, severity="block")

        st = model.stability(x, p)
        det["stability"] = st
        if not st["stable"]:
            shafts = ", ".join(st["unstable_shafts"]) or "hydraulic"
            return Verdict(False, "unstable",
                           f"converged onto a dynamically unstable root "
                           f"(shaft {shafts} sits on the friction downslope); "
                           "the equations are satisfied but no machine runs here",
                           det, severity="block")

        return Verdict(True, "ok", "stable operating point", det)
