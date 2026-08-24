"""Projection data for the 3D view -- the archive, a matched pair, and the race.

    python viz.py            # writes viz_results.json

This file exists to make one argument visible instead of asserted: *why* a
retrieved state is a good starting guess. Everything it writes is measured from
the same archive `bench.py` benchmarks, and the iteration counts it reports are
cross-checked against `results.json` so a picture can never quote a number the
benchmark does not.

**Which space gets drawn, and why it is not the obvious one.**

The obvious choice is to draw the archive in *parameter* space, since that is
where retrieval happens. Measured, that choice is not defensible: the sweep
samples 7 parameters independently and uniformly, so there is no low-dimensional
structure in the inputs to find. The seven principal axes carry 17.6% down to
10.7% of the variance -- near-equal, i.e. a ball -- the best three capture under
half of it, and distance on a 3D screen correlates with the true 7D distance the
retriever uses at only r ~= 0.66. Drawing that and saying "close on screen means
close to the algorithm" would be false by a third.

*Solution* space is the opposite, and the reason is physics rather than luck.
Three axes carry ~97.5% of the variance and 3D distance tracks true 7D distance
at r ~= 0.999. The seven unknowns are not independent -- they are coupled by the
circuit -- so the solved states lie on a thin sheet inside the 7D box.

That gap **is** the product's argument, in one sentence: the inputs are
irreducibly 7-dimensional, the answers are effectively 2-dimensional, and a
warm start works because a solved neighbour is already on the sheet while a cold
start begins off it. So the cloud is drawn in solution space, the numbers that
carry the claim (the pair's separation) are quoted as true distances rather than
projected ones, and the parameter-space fidelity is written into this file too
-- because the honest caveat is a measurement here, not a disclaimer.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import bench
import model

OUT = Path("viz_results.json")
RESULTS = Path("results.json")
ARCHIVE = Path("archive/cases.jsonl")

#: how many cases the contact sheet draws. Kept small on purpose: the sheet is
#: there to read as a real archive at a glance, while the comparison the demo
#: actually makes is pairwise, and pairwise perception does not survive twenty
#: simultaneous subjects. Twenty tiles are ambient; two are narrated.
N_TILES = 20

#: what the three solution-space axes mean, read off the loadings below. These
#: are labels for a projection that is computed, not hand-placed -- if the
#: archive changes and the loadings change, these strings must be re-checked.
AXIS_MEANING = (
    "load split between the two motor branches (branch a against branch b)",
    "overall pressure and flow level (all seven unknowns moving together)",
    "manifold pressure against everything downstream -- the relief valve's signature",
)


# --- projection -------------------------------------------------------------

def fit_projection(states: np.ndarray) -> dict:
    """PCA on z-scored solution states.

    Z-scoring first is not cosmetic: five of the seven unknowns are pressures in
    bar (order 1e2) and two are shaft speeds in rev/min (order 1e3), so raw PCA
    would report the shafts' units as the dominant physical direction.
    """
    mu = states.mean(axis=0)
    sd = states.std(axis=0)
    sd = np.where(sd == 0.0, 1.0, sd)
    z = (states - mu) / sd
    _u, sv, vt = np.linalg.svd(z - z.mean(axis=0), full_matrices=False)
    var = (sv ** 2) / float((sv ** 2).sum())
    return {"mu": mu, "sd": sd, "basis": vt[:3], "centre": z.mean(axis=0),
            "variance": var}


def project(proj: dict, states: np.ndarray) -> np.ndarray:
    z = (np.atleast_2d(np.asarray(states, dtype=float)) - proj["mu"]) / proj["sd"]
    return (z - proj["centre"]) @ proj["basis"].T


def distance_fidelity(high: np.ndarray, low: np.ndarray) -> float:
    """Correlation between true pairwise distance and projected distance.

    Every pair, not a sample -- 395 cases is 77 815 pairs, which costs nothing
    and removes a seed from a number that appears on a slide.
    """
    iu = np.triu_indices(len(high), k=1)
    d_hi = np.linalg.norm(high[iu[0]] - high[iu[1]], axis=1)
    d_lo = np.linalg.norm(low[iu[0]] - low[iu[1]], axis=1)
    return float(np.corrcoef(d_hi, d_lo)[0, 1])


def parameter_space_fidelity(norm: np.ndarray) -> dict:
    """The projection that was *rejected*, measured rather than asserted.

    Reported so the page can state the caveat with a number behind it, and so
    that anyone who asks "why not draw the space you actually search?" gets the
    measurement instead of an opinion.
    """
    centred = norm - norm.mean(axis=0)
    _u, sv, vt = np.linalg.svd(centred, full_matrices=False)
    var = (sv ** 2) / float((sv ** 2).sum())
    low = centred @ vt[:3].T
    return {
        "variance_pct": [round(float(v) * 100, 2) for v in var],
        "top3_variance_pct": round(float(var[:3].sum()) * 100, 2),
        "distance_fidelity_r": round(distance_fidelity(norm, low), 4),
        "note": "rejected as the layout space -- see this module's docstring",
    }


# --- the contact sheet ------------------------------------------------------

def pick_tiles(xyz: np.ndarray, records: list[dict], n: int) -> list[int]:
    """Farthest-point sampling in the projected cloud, seeded at the centroid.

    Deterministic and spread: taking the first n records would sample one corner
    of the sweep, and taking n at random would repeat near-identical cases. The
    sheet is supposed to look like the range of the archive, so it is chosen to
    cover it.
    """
    centre = xyz.mean(axis=0)
    first = int(np.argmin(np.linalg.norm(xyz - centre, axis=1)))
    chosen = [first]
    d = np.linalg.norm(xyz - xyz[first], axis=1)
    while len(chosen) < min(n, len(xyz)):
        j = int(np.argmax(d))
        chosen.append(j)
        d = np.minimum(d, np.linalg.norm(xyz - xyz[j], axis=1))
    return chosen


def tile_payload(rec: dict, xyz: np.ndarray) -> dict:
    return {
        "id": rec["case_id"],
        "xyz": [round(float(v), 4) for v in xyz],
        "params": {k: float(rec["params"][k]) for k in model.PARAM_NAMES},
        "solution": {k: float(rec["solution"][k]) for k in model.STATE_NAMES},
        "relief_open": bool(rec["regime"]["relief_open"]),
        "relief_flow_share": float(rec["regime"]["relief_flow_share"]),
    }


# --- the race ---------------------------------------------------------------

def race(params: dict, warm_x0, proj: dict) -> dict:
    """Cold, nominal and warm on one query, with every Newton iterate kept.

    Same residual, same Jacobian, same tolerance -- `model.solve`'s contract is
    that the *only* thing differing between these three runs is x0, which is
    exactly what the picture has to show for the comparison to mean anything.
    """
    arms = {
        "cold": model.solve(params, record_path=True),
        "nominal": model.solve(params, x0=model.nominal_start(params),
                               record_path=True),
        "warm": model.solve(params, x0=np.asarray(warm_x0, dtype=float),
                            record_path=True),
    }
    out = {}
    for name, r in arms.items():
        path = np.asarray(r["path"], dtype=float)
        out[name] = {
            "iterations": r["iterations"],
            "converged": r["converged"],
            "status": r["status"],
            "residual_inf": r["residual_inf"],
            "residuals": [float(h) for h in r["history"]],
            "path_state": [[float(v) for v in row] for row in path],
            "path_xyz": [[round(float(v), 4) for v in row]
                         for row in project(proj, path)],
        }
    cold_x = np.asarray(arms["cold"]["x"])
    for name in ("nominal", "warm"):
        dx = np.abs(cold_x - np.asarray(arms[name]["x"]))
        out[name]["agreement_vs_cold"] = {
            "max_dp_bar": float(dx[bench.PRESSURE_IDX].max()),
            "max_dw_rpm": float(dx[bench.SPEED_IDX].max()),
        }
    return out


# --- assembly ---------------------------------------------------------------

def run(archive_path: Path = ARCHIVE, results_path: Path = RESULTS,
        out: Path | None = OUT, n_tiles: int = N_TILES) -> dict:
    records, archive_norm, archive_states = bench.load_archive(archive_path)
    if not results_path.exists():
        raise SystemExit(f"no {results_path} -- run `python bench.py` first")
    res = json.loads(results_path.read_text(encoding="utf-8"))

    proj = fit_projection(archive_states)
    xyz = project(proj, archive_states)

    z_arch = (archive_states - proj["mu"]) / proj["sd"]
    fidelity = distance_fidelity(z_arch, xyz)

    # the pair: the benchmark's own speed-up exemplar, so the picture and the
    # results table are describing the same case rather than two chosen ones
    ex = res["exemplars"]["speedup"]
    q_params = {k: float(ex["params"][k]) for k in model.PARAM_NAMES}
    j, dist = bench.nearest(q_params, archive_norm)
    neighbour = records[j]
    if neighbour["case_id"] != ex["neighbour_id"]:
        raise SystemExit(
            f"retrieval disagrees with {results_path}: recomputed "
            f"{neighbour['case_id']}, recorded {ex['neighbour_id']}")

    arms = race(q_params, archive_states[j], proj)

    # cross-check: the picture's iteration counts must equal the benchmark's
    mismatch = {a: (arms[a]["iterations"], ex[a]["iterations"])
                for a in ("cold", "nominal", "warm")
                if arms[a]["iterations"] != ex[a]["iterations"]}
    if mismatch:
        raise SystemExit(f"iteration counts disagree with {results_path}: {mismatch}")

    q_state = np.asarray(arms["cold"]["path_state"][-1])
    tiles = pick_tiles(xyz, records, n_tiles)

    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": {
            "archive": str(archive_path),
            "archive_size": len(records),
            "n_tiles": len(tiles),
            "layout": "PCA on z-scored solution states (5 pressures, 2 speeds)",
            "retrieval": res["config"]["retrieval"],
            "source_of_truth": str(results_path),
        },
        "projection": {
            "variance_pct": [round(float(v) * 100, 2) for v in proj["variance"]],
            "top3_variance_pct": round(float(proj["variance"][:3].sum()) * 100, 2),
            "distance_fidelity_r": round(fidelity, 4),
            "axes": [
                {"index": i, "variance_pct": round(float(proj["variance"][i]) * 100, 2),
                 "meaning": AXIS_MEANING[i],
                 "loadings": {n: round(float(w), 3)
                              for n, w in zip(model.STATE_NAMES, proj["basis"][i])}}
                for i in range(3)
            ],
        },
        "parameter_space": parameter_space_fidelity(archive_norm),
        "archive": [
            {"id": r["case_id"],
             "xyz": [round(float(v), 4) for v in xyz[i]],
             "relief_open": bool(r["regime"]["relief_open"]),
             "p1": float(r["solution"]["p1"]),
             "w_a": float(r["solution"]["w_a"]),
             "w_b": float(r["solution"]["w_b"])}
            for i, r in enumerate(records)
        ],
        "tiles": [tile_payload(records[i], xyz[i]) for i in tiles],
        "pair": {
            "query": {
                "id": ex["case_id"],
                "params": q_params,
                "solution": {k: float(v) for k, v in zip(model.STATE_NAMES, q_state)},
                "xyz": [round(float(v), 4) for v in project(proj, q_state)[0]],
            },
            "neighbour": tile_payload(neighbour, xyz[j]),
            "setup_distance": float(dist),
            "setup_distance_note": (
                "true Euclidean distance in the normalised 7-parameter space "
                "retrieval searches -- not a distance measured on screen"),
            "state_gap_bar": float(np.abs(
                q_state[bench.PRESSURE_IDX]
                - archive_states[j][bench.PRESSURE_IDX]).max()),
            "state_gap_rpm": float(np.abs(
                q_state[bench.SPEED_IDX]
                - archive_states[j][bench.SPEED_IDX]).max()),
        },
        "race": arms,
        "state_names": list(model.STATE_NAMES),
        "state_units": list(model.STATE_UNITS),
        "param_names": list(model.PARAM_NAMES),
    }

    if out is not None:
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def report(v: dict) -> None:
    p = v["projection"]
    print(f"layout        : {v['config']['layout']}")
    print(f"archive       : {v['config']['archive_size']} cases, "
          f"{v['config']['n_tiles']} on the contact sheet")
    print(f"solution space: 3 axes carry {p['top3_variance_pct']}% of variance, "
          f"distance fidelity r={p['distance_fidelity_r']}")
    for a in p["axes"]:
        print(f"   axis {a['index'] + 1}  {a['variance_pct']:5.1f}%  {a['meaning']}")
    q = v["parameter_space"]
    print(f"param space   : 3 axes carry only {q['top3_variance_pct']}%, "
          f"r={q['distance_fidelity_r']} -- {q['note']}")
    pair = v["pair"]
    print(f"pair          : {pair['query']['id']} -> {pair['neighbour']['id']}, "
          f"setup distance {pair['setup_distance']:.4f}, "
          f"state gap {pair['state_gap_bar']:.1f} bar / "
          f"{pair['state_gap_rpm']:.0f} rev/min")
    r = v["race"]
    print(f"race          : cold {r['cold']['iterations']} iterations, "
          f"nominal {r['nominal']['iterations']}, warm {r['warm']['iterations']} "
          f"-- agreeing to {r['warm']['agreement_vs_cold']['max_dp_bar']:.2e} bar")


def main() -> int:
    report(run())
    print(f"\n  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
