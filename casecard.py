"""The Case Card — the structured record every run artifact becomes.

The archive can only retrieve what it can compare, and run artifacts share no
schema: one team's solver writes `Q_nom = 62.4 L/min`, an older build writes
`Pump nominal delivery ... 4.09 m3/h`, and an engineer writes "pump at about
55 lpm" in an email. A Case Card is what all three have to turn into.

Two things matter more than the field list:

* **Canonical units.** Everything is normalised on the way in — L/min, mm^2,
  bar, kg/m^3 — because a retrieval layer comparing 4.09 against 62.4 is worse
  than no retrieval layer.
* **Explicit absence.** A field that was not in the artifact is recorded as
  missing, never guessed. "The standard fan curves" is not a load coefficient,
  and a Case Card that invents one poisons the archive for every future case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

import model

#: the domain this Case Card schema and this archive describe. A Case Card is
#: not a universal record -- it is a record *of a kind of model*, and the seven
#: canonical fields below only mean anything inside this one.
DOMAIN = "hydraulic-1d"

#: Signatures of artifacts from a *different* kind of model. Detected rather
#: than assumed, because the alternative is worse than useless: a NASTRAN deck
#: states a material density, `SYNONYMS` maps "density" onto `rho`, and without
#: this check the pipeline would cheerfully record aluminium at 2.7e-09 as the
#: hydraulic fluid density and carry on. The unit gate would catch that one by
#: luck. It would not catch a value that happened to look plausible.
#:
#: This is the adapter boundary, made explicit. The three layers above the
#: solver are domain-agnostic; the *schema* is not, and pretending otherwise is
#: how a "universal" tool produces confident nonsense.
FOREIGN_DOMAINS = {
    "structural-3d-fe": {
        "label": "3D structural FE (NX Nastran deck)",
        "markers": ("GRID", "CQUAD4", "CTETRA", "CHEXA", "PSHELL", "PSOLID",
                    "MAT1", "SPC1", "CBUSH", "BEGIN BULK", "ENDDATA"),
        "min_markers": 4,
    },
}


def detect_domain(text: str) -> tuple[str, dict[str, str]]:
    """Which kind of model produced this artifact, and what can be read of it.

    Returns the domain key and a few human-readable facts. The facts exist to
    make a refusal *specific*: "this is a 3D structural deck, 4812 elements,
    linear static" is a different sentence from "I could not read your file",
    and only one of them tells an engineer what to do next.
    """
    upper = text.upper()
    for key, spec in FOREIGN_DOMAINS.items():
        hits = [m for m in spec["markers"] if m in upper]
        if len(hits) >= spec["min_markers"]:
            return key, _read_foreign(text, key, hits)
    return DOMAIN, {}


def _read_foreign(text: str, domain: str, hits: list[str]) -> dict[str, str]:
    """Read what is legible in a foreign artifact without pretending to use it."""
    facts: dict[str, str] = {"markers_seen": ", ".join(sorted(hits))}
    if domain != "structural-3d-fe":
        return facts

    sol = re.search(r"^\s*SOL\s+(\d+)", text, re.M)
    if sol:
        facts["solution_sequence"] = f"SOL {sol.group(1)}"
    title = re.search(r"^\s*TITLE\s*=\s*(.+)$", text, re.M)
    if title:
        facts["title"] = title.group(1).strip()

    # NASTRAN small-field: 8-column fields, and "2.70-9" means 2.70e-9
    mat = re.search(r"^MAT1\s+(\S+)\s+(\S+)\s+(\S*)\s+(\S+)", text, re.M)
    if mat:
        facts["youngs_modulus"] = mat.group(2)
        facts["poisson_ratio"] = mat.group(4)
    shell = re.search(r"^PSHELL\s+\S+\s+\S+\s+(\S+)", text, re.M)
    if shell:
        facts["shell_thickness"] = shell.group(1)

    for card in ("GRID", "CQUAD4", "CTETRA", "CHEXA"):
        n = len(re.findall(rf"^{card}\b", text, re.M))
        if n:
            facts[f"{card.lower()}_count"] = str(n)
    return facts


#: canonical unit for each swept parameter
CANONICAL_UNITS = {
    "Q_nom": "L/min",
    "A_valve_a": "mm^2",
    "A_valve_b": "mm^2",
    "c_load_a": "Nm/(rev/min)^2",
    "c_load_b": "Nm/(rev/min)^2",
    "p_crack": "bar",
    "rho": "kg/m^3",
}

#: units for the 18 promoted hardware constants (§0b, `model.HARDWARE`) --
#: circuit properties a case may *state* instead of inheriting the default.
#: Unlike the seven above, a card that states none of these is still
#: complete: `model.PARAM_NAMES` -- what `complete` and `missing` check
#: against -- was never widened to include them, on purpose. They are an
#: override, not a measurement the artifact is expected to report.
HARDWARE_UNITS = {
    "cd": "",                       # dimensionless
    "R_leak": "bar/(L/min)",
    "A_relief_max": "mm^2",
    "relief_band": "bar",
    "D_mot_a": "cm^3/rev", "D_mot_b": "cm^3/rev",
    "A_ret_a": "mm^2", "A_ret_b": "mm^2",
    "leak_mot_a": "L/min/bar", "leak_mot_b": "L/min/bar",
    "t_coul_a": "Nm", "t_coul_b": "Nm",
    "t_stat_a": "Nm", "t_stat_b": "Nm",
    "w_strib_a": "rev/min", "w_strib_b": "rev/min",
    "b_visc_a": "Nm/(rev/min)", "b_visc_b": "Nm/(rev/min)",
}

#: both together, for the code that treats a Case Card's up-to-25 possible
#: fields uniformly and does not care which of the two groups a name is from
#: -- ingest's extraction schema, and `validate`'s unit-error message.
ALL_UNITS = {**CANONICAL_UNITS, **HARDWARE_UNITS}

#: multiply a value in this unit by the factor to reach the canonical unit.
#: "bara" is deliberately absent -- see UNIT_OFFSETS below, it is not a
#: multiplicative conversion.
UNIT_FACTORS = {
    # flow -> L/min
    "l/min": 1.0, "lpm": 1.0, "l/m": 1.0, "litre/min": 1.0,
    "m3/h": 1000.0 / 60.0, "m^3/h": 1000.0 / 60.0, "m3/hr": 1000.0 / 60.0,
    "m3/s": 60000.0, "m^3/s": 60000.0,
    # area -> mm^2
    "mm2": 1.0, "mm^2": 1.0, "mm²": 1.0,
    "cm2": 100.0, "cm^2": 100.0, "cm²": 100.0,
    "m2": 1.0e6, "m^2": 1.0e6, "m²": 1.0e6,
    # pressure -> bar
    "bar": 1.0, "barg": 1.0,
    "pa": 1.0e-5, "kpa": 1.0e-2, "mpa": 10.0, "psi": 0.0689476,
    # density -> kg/m^3
    "kg/m3": 1.0, "kg/m^3": 1.0, "kg/m³": 1.0,
    "g/cm3": 1000.0, "g/cm^3": 1000.0, "kg/l": 1000.0, "kg/dm3": 1000.0,
}

#: units needing an *additive* correction, applied instead of (never in
#: addition to) UNIT_FACTORS. Just one: "bara" is bar *absolute*, and this
#: model works in gauge pressure throughout (P_TANK = 0.0 bar gauge, model.py).
#: Absolute and gauge differ by local atmospheric pressure, not by a scale
#: factor -- folding "bara" into UNIT_FACTORS at 1.0, what this used to do,
#: silently read every absolute-pressure artifact about one bar too high.
#: Standard atmosphere (1.01325 bar) is the conventional reference absent a
#: stated local value.
UNIT_OFFSETS = {"bara": -1.01325}

#: '^2'/'2' and '³'/'3' are the same unit written two ways ("kg/dm^3" vs
#: "kg/dm3", "m^3/h" vs "m3/h"), and a table entry for only one spelling used
#: to mean the other one fell through `normalise_unit`'s "unrecognised -> pass
#: through unconverted" branch -- accepted silently, at the wrong scale,
#: which is precisely the failure the Units gate downstream exists to catch.
#: Matching on a normalised key closes every such gap at once rather than
#: hardcoding each missing sibling as it is found.
_SUPERSCRIPTS = str.maketrans({"²": "2", "³": "3", "^": ""})


def _norm_unit_key(key: str) -> str:
    return key.translate(_SUPERSCRIPTS)


_UNIT_FACTORS_NORM = {_norm_unit_key(k): v for k, v in UNIT_FACTORS.items()}
_UNIT_OFFSETS_NORM = {_norm_unit_key(k): v for k, v in UNIT_OFFSETS.items()}


def normalise_unit(value: float, unit: str | None) -> tuple[float, str | None]:
    """Convert a value to its canonical unit. Returns (value, unit_as_given)."""
    if not unit:
        return value, None
    key = _norm_unit_key(unit.strip().lower())
    if key in _UNIT_OFFSETS_NORM:
        return value + _UNIT_OFFSETS_NORM[key], unit
    if key in _UNIT_FACTORS_NORM:
        return value * _UNIT_FACTORS_NORM[key], unit
    return value, unit


def parse_number(raw: str) -> float | None:
    """Parse a number written the way people actually write them.

    Handles scientific notation and the European decimal comma ("4,5"), which
    is the single most common way a Romanian-language note breaks a naive
    float() — and which appears in the fixtures for exactly that reason.
    """
    s = raw.strip().replace(" ", "")
    if re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})+,\d+", s):      # 1.234,56
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"[-+]?\d+,\d+([eE][-+]?\d+)?", s):   # 4,5 / 2,4e-05
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


@dataclass
class CaseCard:
    """One run artifact, structured. `params` is always in canonical units."""

    case_id: str
    source: dict = field(default_factory=dict)
    params: dict[str, float] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    notes: str = ""
    units: dict[str, str] = field(default_factory=lambda: dict(CANONICAL_UNITS))
    #: which kind of model produced this artifact. Anything other than DOMAIN
    #: means the seven canonical fields do not apply to it at all.
    domain: str = DOMAIN
    #: what was legible in a foreign artifact, kept so a refusal can be specific
    foreign: dict[str, str] = field(default_factory=dict)

    @property
    def foreign_domain(self) -> bool:
        return self.domain != DOMAIN

    @property
    def complete(self) -> bool:
        return not self.missing

    def validate(self) -> list[str]:
        """Physical-plausibility complaints. Empty list means nothing looks wrong.

        This is a sanity gate on *ingest*, distinct from the transfer verifier:
        it catches a mis-parsed unit (an area of 7.8e-06 because m^2 was read as
        mm^2) before the number ever reaches retrieval.

        Checks the 18 promoted hardware constants too, against
        ``model.HARDWARE_BOUNDS`` rather than ``PARAM_BOUNDS`` -- they were
        unreachable here before ingest could put them on a card at all, which
        is a gap worth naming: a stated ``relief_band = 0`` or ``cd = 0`` would
        have sailed through this gate and then divided by zero in
        ``relief_opening()`` / ``orifice_gain()`` the first time the case was
        solved.
        """
        problems = []
        for name, value in self.params.items():
            bounds = model.PARAM_BOUNDS.get(name, model.HARDWARE_BOUNDS.get(name))
            if bounds is None:
                continue
            lo, hi = bounds
            if not (lo / 100 <= value <= hi * 100):
                unit = f" {ALL_UNITS[name]}" if ALL_UNITS[name] else ""
                problems.append(
                    f"{name} = {value:.6g}{unit} is off by orders of magnitude "
                    f"(plausible range {lo:g} to {hi:g}) -- likely a unit error")
        return problems

    def to_dict(self) -> dict:
        d = asdict(self)
        d["complete"] = self.complete
        return d

    def summary(self) -> str:
        lines = [f"Case Card  {self.case_id}",
                 f"  source   {self.source.get('artifact', '?')} "
                 f"(via {self.source.get('ingested_by', '?')})"]
        for name in model.PARAM_NAMES:
            if name in self.params:
                raw = self.provenance.get(name, "")
                raw = f"   <- {raw!r}" if raw else ""
                lines.append(f"  {name:11} {self.params[name]:>12.6g} "
                             f"{CANONICAL_UNITS[name]:<16}{raw}")
            else:
                lines.append(f"  {name:11} {'MISSING':>12}")
        if self.notes:
            lines.append(f"  note     {self.notes[:70]}")
        return "\n".join(lines)
