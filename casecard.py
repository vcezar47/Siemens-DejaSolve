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

#: multiply a value in this unit by the factor to reach the canonical unit
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
    "bar": 1.0, "bara": 1.0, "barg": 1.0,
    "pa": 1.0e-5, "kpa": 1.0e-2, "mpa": 10.0, "psi": 0.0689476,
    # density -> kg/m^3
    "kg/m3": 1.0, "kg/m^3": 1.0, "kg/m³": 1.0,
    "g/cm3": 1000.0, "g/cm^3": 1000.0, "kg/l": 1000.0, "kg/dm3": 1000.0,
}


def normalise_unit(value: float, unit: str | None) -> tuple[float, str | None]:
    """Convert a value to its canonical unit. Returns (value, unit_as_given)."""
    if not unit:
        return value, None
    key = unit.strip().lower()
    if key in UNIT_FACTORS:
        return value * UNIT_FACTORS[key], unit
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

    @property
    def complete(self) -> bool:
        return not self.missing

    def validate(self) -> list[str]:
        """Physical-plausibility complaints. Empty list means nothing looks wrong.

        This is a sanity gate on *ingest*, distinct from the transfer verifier:
        it catches a mis-parsed unit (an area of 7.8e-06 because m^2 was read as
        mm^2) before the number ever reaches retrieval.
        """
        problems = []
        for name, value in self.params.items():
            if name not in model.PARAM_BOUNDS:
                continue
            lo, hi = model.PARAM_BOUNDS[name]
            if not (lo / 100 <= value <= hi * 100):
                problems.append(
                    f"{name} = {value:.6g} {CANONICAL_UNITS[name]} is off by orders "
                    f"of magnitude (sweep range {lo:g} to {hi:g}) -- likely a unit error")
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
