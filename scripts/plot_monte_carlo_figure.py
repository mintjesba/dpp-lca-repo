"""Monte Carlo figure: spread of the climate change results of the full value chain and
single-process models.

Reads the Monte Carlo runs written by SI4 (results/monte_carlo_runs.csv) and the
deterministic scores (results/results.csv). Writes
- results/figure_monte_carlo.png/.pdf
- results/monte_carlo_statistics.csv: deterministic score and Monte Carlo statistics per
  case (for SI3)

(a) Monte Carlo results per case, with the deterministic score shown separately;
(b) the same results divided by their median, to compare the relative spread.
Box: interquartile range; centre line: median; whiskers: 2.5th-97.5th percentile (95%
interval); circles: runs outside the 95% interval.

Run after SI4:

    python scripts/plot_monte_carlo_figure.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"

SOURCE_SUFFIX = " (source SD95)"

# case in monte_carlo_runs.csv -> (x-axis label, model); cases not in the file are skipped
CASES = {
    "full LCA": ("full\nvalue chain", "full"),
    "single LCA": ("single\nprocess", "single"),
    "full LCA" + SOURCE_SUFFIX: ("full\nvalue chain\n(source SD95)", "full"),
    "single LCA" + SOURCE_SUFFIX: ("single\nprocess\n(source SD95)", "single"),
}

# colours of figure 1: blue = full value chain (baseline), orange = single process
STYLE = {
    "full": {"facecolor": "#dae8fc", "edgecolor": "#4a78b5"},
    "single": {"facecolor": "#ffe6cc", "edgecolor": "#d79b00"},
}
SOURCE_HATCH = "///"
INK = "#333333"

runs = pd.read_csv(RESULTS_DIR / "monte_carlo_runs.csv", index_col=0)
deterministic = pd.read_csv(RESULTS_DIR / "results.csv", index_col=0).iloc[:, 0]
cases = [case for case in CASES if case in runs.columns]
runs = runs[cases]
n_runs = len(runs)

# statistics per case (SI3): the deterministic score is not a Monte Carlo statistic
statistics = pd.DataFrame(
    {
        "deterministic score": [deterministic[c.removesuffix(SOURCE_SUFFIX)] for c in cases],
        "mean": runs.mean(),
        "median": runs.median(),
        "standard deviation": runs.std(),
        "coefficient of variation": runs.std() / runs.mean(),
        "2.5th percentile": runs.quantile(0.025),
        "25th percentile": runs.quantile(0.25),
        "75th percentile": runs.quantile(0.75),
        "97.5th percentile": runs.quantile(0.975),
    },
    index=cases,
)
statistics["interquartile range / median"] = (
    statistics["75th percentile"] - statistics["25th percentile"]
) / statistics["median"]
statistics.index.name = f"case ({n_runs} Monte Carlo runs)"
statistics.to_csv(RESULTS_DIR / "monte_carlo_statistics.csv")


def boxplot(ax, data):
    positions = np.arange(len(cases))
    boxes = ax.boxplot(
        data,
        positions=positions,
        widths=0.55,
        whis=(2.5, 97.5),
        patch_artist=True,
        medianprops={"color": INK, "linewidth": 1.5},
        whiskerprops={"color": INK, "linewidth": 1},
        capprops={"color": INK, "linewidth": 1},
        flierprops={"marker": "o", "markersize": 3, "markerfacecolor": "none",
                    "markeredgecolor": INK, "markeredgewidth": 0.6},
    )
    for box, case in zip(boxes["boxes"], cases):
        box.set(**STYLE[CASES[case][1]], linewidth=1.2)
        if case.endswith(SOURCE_SUFFIX):
            box.set_hatch(SOURCE_HATCH)
    ax.set_xticks(positions, [CASES[case][0] for case in cases], fontsize=9)
    ax.set_xlim(-0.6, len(cases) - 0.4)
    ax.grid(axis="y", color="#e5e5e5", linewidth=0.8)
    ax.set_axisbelow(True)
    return positions


fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(9, 4.4))

# (a) absolute values, with the deterministic scores next to the boxes
positions = boxplot(ax_a, [runs[case] for case in cases])
ax_a.scatter(positions + 0.4, statistics["deterministic score"], marker="D", s=28,
             color=INK, zorder=3)
ax_a.set_ylim(0, None)
ax_a.set_ylabel("climate change impacts\n(kg CO$_2$-eq. GWP100)")
ax_a.set_title("(a)", fontsize=11)

# (b) relative to the median of each case
boxplot(ax_b, [runs[case] / runs[case].median() for case in cases])
ax_b.axhline(1, color="#999999", linewidth=0.8, zorder=0)
ax_b.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
ax_b.set_ylabel("Monte Carlo results relative to their median")
ax_b.set_title("(b)", fontsize=11)

# shared legend
handles = [
    plt.Rectangle((0, 0), 1, 1, linewidth=1.2, **STYLE["full"]),
    plt.Rectangle((0, 0), 1, 1, linewidth=1.2, **STYLE["single"]),
]
labels = ["full value chain", "single process"]
if any(case.endswith(SOURCE_SUFFIX) for case in cases):
    handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor=INK,
                                 hatch=SOURCE_HATCH, linewidth=1))
    labels.append("source-data SD95")
handles.append(plt.Line2D([], [], marker="D", color=INK, linestyle="none", markersize=6))
labels.append("deterministic score")
fig.legend(handles, labels, loc="lower center", ncol=len(labels), frameon=False,
           fontsize=9, bbox_to_anchor=(0.5, -0.01))

fig.tight_layout(rect=(0, 0.07, 1, 1))
for suffix in ("png", "pdf"):
    fig.savefig(RESULTS_DIR / f"figure_monte_carlo.{suffix}", dpi=300, bbox_inches="tight")

print(statistics.round(4).T.to_string())
print(f"Figure written to {RESULTS_DIR / 'figure_monte_carlo.png'}")
