"""The Phase 1 gate figure, drawn from results.json — nothing is hard-coded.

    python sweep.py && python bench.py && python plot_convergence.py

Panels:
  A  one case, residual per Newton iteration, all three starting guesses —
     same final residual, different number of steps
  B  all query cases, distribution of iteration counts
  C  how much of it depends on the quality of the solver's Jacobian

Three arms throughout: the flat cold start, the nominal guess built from the
case setup, and the archive warm start. The nominal arm is on every panel
because a figure that only shows cold vs warm overstates the case.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLD = "#c0392b"
NOMINAL = "#e69f00"
WARM = "#1f77b4"


def draw(results: dict, out: Path) -> None:
    s = results["summary"]
    cfg = results["config"]
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(15, 4.6))

    # --- A: one case, residual per iteration ------------------------------
    ex = results["exemplars"]["speedup"]
    hc, hw = ex["history"]["cold"], ex["history"]["warm"]
    hn = ex["history"].get("nominal")
    ax1.semilogy(range(len(hc)), hc, "o-", color=COLD, label=f"cold start ({len(hc)-1} iters)")
    if hn:
        ax1.semilogy(range(len(hn)), hn, "^-", color=NOMINAL,
                     label=f"nominal guess ({len(hn)-1} iters)")
    ax1.semilogy(range(len(hw)), hw, "s-", color=WARM, label=f"warm start ({len(hw)-1} iters)")
    ax1.axhline(cfg["tol"], color="k", ls=":", lw=1)
    ax1.text(0.98, cfg["tol"] * 1.6, f"tolerance {cfg['tol']:g}", ha="right",
             va="bottom", fontsize=8, transform=ax1.get_yaxis_transform())
    ax1.set_xlabel("Newton iteration")
    ax1.set_ylabel("residual, max-norm")
    ax1.set_title(f"A · one case ({ex['case_id']})\nsame equations, same tolerance, "
                  "three starting guesses", fontsize=10)
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.3)

    # --- B: distribution over all query cases -----------------------------
    ok = [c for c in results["cases"]
          if c["cold"]["converged"] and c["warm"]["converged"]]
    ci = np.array([c["cold"]["iterations"] for c in ok])
    wi = np.array([c["warm"]["iterations"] for c in ok])
    ni = np.array([c["nominal"]["iterations"] for c in results["cases"]
                   if c["nominal"]["converged"] and c["warm"]["converged"]])
    top = max(ci.max(), wi.max(), ni.max() if len(ni) else 0)
    bins = np.arange(0, top + 2) - 0.5
    ax2.hist(ci, bins=bins, alpha=0.6, color=COLD, label=f"cold (mean {ci.mean():.1f})")
    if len(ni):
        ax2.hist(ni, bins=bins, alpha=0.6, color=NOMINAL,
                 label=f"nominal (mean {ni.mean():.1f})")
    ax2.hist(wi, bins=bins, alpha=0.6, color=WARM, label=f"warm (mean {wi.mean():.1f})")
    ax2.set_xlabel("Newton iterations to converge")
    ax2.set_ylabel("cases")
    vn_pct = s["warm_vs_nominal"]["iteration_reduction_pct"]
    vn_txt = "--" if vn_pct is None else f"{vn_pct:.0f}%"
    ax2.set_title(f"B · {len(ci)} fresh cases vs an archive of "
                  f"{cfg['archive_size']}\n{s['iteration_reduction_pct']:.0f}% fewer than "
                  f"cold, {vn_txt} fewer than nominal", fontsize=10)
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.3, axis="y")

    # --- C: does the result survive a worse Jacobian? ---------------------
    rows = results.get("jacobian_sensitivity", [])
    if rows:
        y = np.arange(len(rows))
        ax3.barh(y - 0.26, [r["cold_failures"] for r in rows], height=0.24,
                 color=COLD, label="cold start")
        ax3.barh(y, [r.get("nominal_failures", 0) for r in rows], height=0.24,
                 color=NOMINAL, label="nominal guess")
        ax3.barh(y + 0.26, [r["warm_failures"] for r in rows], height=0.24,
                 color=WARM, label="warm start")
        ax3.set_yticks(y)
        ax3.set_yticklabels([r["label"].replace(", ", ",\n") for r in rows], fontsize=8)
        ax3.invert_yaxis()
        ax3.set_xlabel(f"runs that never converged (of {rows[0]['n']})")
        ax3.set_title("C · non-convergence under a worse Jacobian,\n"
                      "and how much of it a nominal guess already fixes",
                      fontsize=10)
        ax3.legend(fontsize=9)
        ax3.grid(alpha=0.3, axis="x")

    a = s["agreement"]
    fig.suptitle(
        f"Déjà Solve -- warm-starting the initialisation solve from the nearest archived case    "
        f"|    answers agree to {a['max_dp_bar']:.0e} bar / {a['max_dw_rpm']:.0e} rev/min "
        f"across all {a['n_compared']} cases",
        fontsize=11, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print(f"  -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", type=Path, default=Path("results.json"))
    ap.add_argument("--out", type=Path, default=Path("figs/convergence.png"))
    args = ap.parse_args()
    if not args.results.exists():
        raise SystemExit(f"no {args.results} -- run `python bench.py` first")
    draw(json.loads(args.results.read_text(encoding="utf-8")), args.out)


if __name__ == "__main__":
    main()
