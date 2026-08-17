"""Generate the messy run artifacts the ingest layer has to cope with.

Every fixture is written *from* a known parameter set, so ground truth is exact
and extraction accuracy is measurable rather than eyeballed. The styles are
chosen to span what actually accumulates around a simulation team:

  A  a tidy machine-written solver log            — the easy case
  B  an older solver's banner log, SI units       — needs unit conversion
  C  an engineer's email, English prose           — no key=value anywhere
  D  an engineer's note in Romanian, decimal comma — the Brasov reality
  E  a truncated log with a corrupted line        — must be refused, not guessed

C and D deliberately describe the shaft loads the way a person does ("the
standard fan curves", "sarcina e mica") rather than as coefficients. Those
fields are *not recoverable* from the text, and an honest ingest says so
instead of inventing a number.

    python make_logs.py
"""

from __future__ import annotations

import json
from pathlib import Path

#: (filename, ground-truth params, fields genuinely absent from the text)
FIXTURES: list[tuple[str, dict, list[str], str]] = []


def _add(name: str, params: dict, unrecoverable: list[str], text: str) -> None:
    FIXTURES.append((name, params, unrecoverable, text))


# --- A: tidy machine log ----------------------------------------------------
_add(
    "run-tidy.log",
    {"Q_nom": 62.4, "A_valve_a": 7.85, "A_valve_b": 3.12,
     "c_load_a": 1.42e-05, "c_load_b": 2.61e-05, "p_crack": 187.0, "rho": 863.0},
    [],
    """=== HydroSim 4.2 :: batch runner ===
run id      : SIM-2026-0412
started     : 2026-03-14 22:41:07
model file  : manifold_2motor.hsm
operator    : m.ionescu

[parameters]
Q_nom       = 62.4 L/min
A_valve_a   = 7.85 mm^2
A_valve_b   = 3.12 mm^2
c_load_a    = 1.42e-05 Nm/(rev/min)^2
c_load_b    = 2.61e-05 Nm/(rev/min)^2
p_crack     = 187.0 bar
rho         = 863.0 kg/m^3

[init]
solving steady state ...
  iter  1  residual 4.812e+01
  iter  5  residual 9.330e+00
  iter  8  residual 8.882e+00
initialisation FAILED - line search stalled (alpha < 1e-4)
run aborted after 00:00:03
""",
)

# --- B: legacy banner log, SI and mixed units -------------------------------
_add(
    "run-legacy.log",
    {"Q_nom": 68.18, "A_valve_a": 7.8, "A_valve_b": 6.40,
     "c_load_a": 9.7e-06, "c_load_b": 2.2e-05, "p_crack": 215.0, "rho": 874.0},
    [],
    """ HYDRAULIC NETWORK SOLVER   (build 11.3.0-rc2)
 =============================================
 Case ............................:  nightly/case_0118
 Date ............................:  12-MAR-2026 03:12

 Pump nominal delivery ...........:     4.0908 m3/h
 Metering valve A, orifice area ..:  7.800e-06 m2
 Metering valve B, orifice area ..:      6.400 mm2
 Shaft A quadratic load coeff ....:  9.700e-06
 Shaft B quadratic load coeff ....:  2.200e-05
 Relief cracking setting .........:     215.00 bar
 Working fluid density ...........:      0.874 g/cm3

 *** initialisation did not converge in 60 iterations ***
 *** residual at exit:  1.4471e+01                    ***
""",
)

# --- C: English email, prose only -------------------------------------------
_add(
    "note-email.txt",
    {"Q_nom": 55.0, "A_valve_a": 2.0, "A_valve_b": 11.0,
     "p_crack": 240.0, "rho": 890.0},
    ["c_load_a", "c_load_b"],
    """From: dan.p@___
Subject: re: overnight sweep - case 118 keeps dying

Hi,

Case 118 is the one that died overnight again. Setup was the usual for the
restrictive-A study: pump at about 55 lpm, metering valve A cracked barely
open (roughly 2 mm2, deliberately restrictive), B left wide at 11 mm2. The
relief was set to 240 bar. Oil was cold-ish when we started, call it 890.

Loads were the standard fan curves on both shafts, same as always.

It never gets past initialisation - the solver just sits there and then gives
up. Andrei says he saw the same thing on the low-flow cases last month. Can
you have a look before Friday?

Thanks
""",
)

# --- D: Romanian note, decimal comma ----------------------------------------
_add(
    "note-ro.txt",
    {"Q_nom": 70.0, "A_valve_a": 4.5, "A_valve_b": 9.0,
     "c_load_a": 8e-06, "c_load_b": 2.4e-05, "p_crack": 150.0, "rho": 835.0},
    [],
    """Salut,

Am rulat cazul de vineri, cel cu doua motoare. Debitul pompei a fost pe la
70 l/min, ventilul A deschis la 4,5 mm2 iar ventilul B la 9 mm2. Supapa de
siguranta e reglata la 150 bar. Uleiul era deja cald cand am pornit,
densitatea 835 kg/m3.

Sarcina pe arborele A e mica (c = 8e-6), pe B e mai mare, in jur de 2,4e-05.

Nu converge din start, pica la initializare de fiecare data. Am incercat si
cu pasi mai mici, acelasi lucru. Daca ai timp arunca un ochi.

Multumesc,
Cristi
""",
)

# --- E: truncated log with a corrupted line ---------------------------------
_add(
    "run-truncated.log",
    {"Q_nom": 44.0, "A_valve_a": 5.5, "A_valve_b": 5.5,
     "c_load_a": 1.1e-05, "c_load_b": 1.1e-05, "rho": 850.0},
    ["p_crack"],
    """=== HydroSim 4.2 :: batch runner ===
run id      : SIM-2026-0455

[parameters]
Q_nom       = 44.0 L/min
A_valve_a   = 5.5 mm^2
A_valve_b   = 5.5 mm^2
c_load_a    = 1.1e-05 Nm/(rev/min)^2
c_load_b    = 1.1e-05 Nm/(rev/min)^2
p_crack     = ####  <- NaN written by the sweep driver, see ticket HS-2291
rho         = 850.0 kg/m^3

[init]
solving steady state ...
  iter  1  residual 3.100e+
""",
)


def main() -> None:
    out = Path("logs")
    out.mkdir(exist_ok=True)
    truth = {}
    for name, params, unrecoverable, text in FIXTURES:
        (out / name).write_text(text, encoding="utf-8")
        truth[name] = {"params": params, "unrecoverable": unrecoverable}
    (out / "ground_truth.json").write_text(json.dumps(truth, indent=2),
                                           encoding="utf-8")
    print(f"wrote {len(FIXTURES)} artifacts + ground_truth.json -> {out}/")
    for name, params, unrecoverable, _ in FIXTURES:
        note = f"  ({len(unrecoverable)} field(s) not in the text)" if unrecoverable else ""
        print(f"  {name:20} {len(params)} params{note}")


if __name__ == "__main__":
    main()
