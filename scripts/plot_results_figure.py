# %%
"""Figure 1: climate change impacts of 1 m2 PV panel per requirement (R1-R5).

Reads the results written by SI4 (results/results.csv) and, if present, the Monte Carlo
summary (results/monte_carlo_summary.csv), and writes results/figure_1_results.png/.pdf.

Each requirement compares the baseline (full value chain LCI, EXIOBASE 3 hybrid, manual
mapping, EF 3.1) with one or more alternative implementations. Run after SI4:

    python scripts/plot_results_figure.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"

BASELINE = "full LCA"

# requirement -> [(case in results.csv, x-axis label), ...]; the first entry is the
# baseline, the others are alternative implementations
REQUIREMENTS = {
    "R1": [
        (BASELINE, "LCI"),
        ("BoM LCA", "BoM"),
        ("BoM LCA (with location)", "BoM +\nlocation"),
    ],
    "R2": [(BASELINE, "full\nvalue\nchain"), ("single LCA", "single\nprocess")],
    "R3": [(BASELINE, "EXIO3H"), ("ecoinvent LCA", "eco-\ninvent")],
    "R4": [
        (BASELINE, "manual"),
        ("CAML LCA", "ML-\nbased"),
        ("CAML LCA (reviewer, top 5)", "ML +\nreviewer"),
    ],
    "R5": [(BASELINE, "EF3.1"), ("IPCC LCA", "IPCC\n2013")],
}

# colours of the original figure: blue = baseline, orange = alternative
STYLE = {
    "baseline": {"facecolor": "#dae8fc", "edgecolor": "#4a78b5"},
    "alternative": {"facecolor": "#ffe6cc", "edgecolor": "#d79b00"},
}
REQUIREMENT_COLOUR = "#a50f15"
BAR_WIDTH = 0.6
GROUP_GAP = 0.6  # extra space between requirements, on top of the bar spacing

scores = pd.read_csv(RESULTS_DIR / "results.csv", index_col=0).iloc[:, 0]

# 95% intervals from the Monte Carlo runs (basic uncertainty), where available
mc_file = RESULTS_DIR / "monte_carlo_summary.csv"
mc = pd.read_csv(mc_file, index_col=0) if mc_file.exists() else None

fig, ax = plt.subplots(figsize=(9, 4.2))
drawn_intervals = False

x = 0.0
ticks, tick_labels, separators = [], [], []
for requirement, cases in REQUIREMENTS.items():
    group_start = x
    for i, (case, label) in enumerate(cases):
        role = "baseline" if i == 0 else "alternative"
        value = scores[case]
        ax.bar(x, value, width=BAR_WIDTH, linewidth=1.2, **STYLE[role])

        ticks.append(x)
        tick_labels.append(label)
        x += 1
    ax.text(
        group_start - 0.35,
        0.97,
        requirement,
        transform=ax.get_xaxis_transform(),
        ha="left",
        va="top",
        fontsize=12,
        fontweight="bold",
        color=REQUIREMENT_COLOUR,
    )
    separators.append(x - 1 + (1 + GROUP_GAP) / 2)
    x += GROUP_GAP

for sep in separators[:-1]:
    ax.axvline(sep, color="black", linewidth=1)

ax.set_xlim(-0.5 - GROUP_GAP / 2, separators[-1])
top = scores[[c for cs in REQUIREMENTS.values() for c, _ in cs]].max()
if mc is not None:
    top = max(top, mc["97.5th percentile"].max())
ax.set_ylim(0, top * 1.2)  # headroom for the requirement labels
ax.set_xticks(ticks, tick_labels, fontsize=9)
ax.set_ylabel("climate change impacts\n(kg CO$_2$-eq. GWP100)")
ax.tick_params(axis="x", length=0)

legend_handles = [
    plt.Rectangle((0, 0), 1, 1, linewidth=1.2, **STYLE["baseline"]),
    plt.Rectangle((0, 0), 1, 1, linewidth=1.2, **STYLE["alternative"]),
]
legend_labels = ["baseline", "alternative"]
if drawn_intervals:
    legend_handles.append(
        plt.Line2D([], [], color="#444444", marker="_", markersize=8, linewidth=1)
    )
    legend_labels.append("95% interval (Monte Carlo)")
ax.legend(
    legend_handles,
    legend_labels,
    loc="upper center",
    bbox_to_anchor=(0.5, -0.2),
    ncol=len(legend_labels),
    frameon=False,
    fontsize=9,
)

fig.tight_layout()
for suffix in ("png", "pdf"):
    fig.savefig(
        RESULTS_DIR / f"figure_1_results.{suffix}", dpi=300, bbox_inches="tight"
    )
print(f"Figure written to {RESULTS_DIR / 'figure_1_results.png'}")


# %%
