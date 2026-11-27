# %%
"""Monte Carlo figure: spread of the climate change results of the full value chain and
single-process models.

Reads the Monte Carlo runs written by SI4 (results/monte_carlo_runs.csv) and the
deterministic scores (results/results.csv). Writes
- results/figure_monte_carlo.png/.pdf
- results/monte_carlo_dispersion.csv: dispersion measures with bootstrap 95% intervals

(a) distribution of the Monte Carlo results per case (box: interquartile range, centre
    line: median, whiskers: 2.5th-97.5th percentile, i.e. the 95% interval), with the
    deterministic score shown separately;
(b) relative spread, as three dispersion measures. Each measure is shown with a
    bootstrap 95% confidence interval, which reflects the limited number of runs.

Run after SI4:

    python scripts/plot_monte_carlo_figure.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"

N_BOOTSTRAP = 10_000
SEED = 2113
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


# dispersion measures, all relative so that cases with different scores can be compared
def coefficient_of_variation(x):
    return np.std(x, ddof=1, axis=-1) / np.mean(x, axis=-1)


def iqr_over_median(x):
    q25, q50, q75 = np.percentile(x, [25, 50, 75], axis=-1)
    return (q75 - q25) / q50


def interval95_over_median(x):
    q025, q50, q975 = np.percentile(x, [2.5, 50, 97.5], axis=-1)
    return (q975 - q025) / q50


MEASURES = {
    "coefficient of\nvariation": coefficient_of_variation,
    "interquartile range\n/ median": iqr_over_median,
    "95% interval width\n/ median": interval95_over_median,
}

runs = pd.read_csv(RESULTS_DIR / "monte_carlo_runs.csv", index_col=0)
deterministic = pd.read_csv(RESULTS_DIR / "results.csv", index_col=0).iloc[:, 0]
cases = [case for case in CASES if case in runs.columns]
n_runs = len(runs)

# bootstrap the dispersion measures: resample the runs with replacement
rng = np.random.default_rng(SEED)
resample = rng.integers(0, n_runs, size=(N_BOOTSTRAP, n_runs))
rows = []
for case in cases:
    values = runs[case].to_numpy()
    for measure, function in MEASURES.items():
        estimates = function(values[resample])
        low, high = np.percentile(estimates, [2.5, 97.5])
        rows.append(
            {
                "case": case,
                "measure": measure.replace("\n", " "),
                "value": function(values),
                "bootstrap 2.5th percentile": low,
                "bootstrap 97.5th percentile": high,
            }
        )
dispersion = pd.DataFrame(rows)
dispersion.to_csv(RESULTS_DIR / "monte_carlo_dispersion.csv", index=False)

fig, (ax_a, ax_b) = plt.subplots(
    1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [1, 1.4]}
)

# (a) distributions of the Monte Carlo results with the deterministic scores
positions = np.arange(len(cases))
boxes = ax_a.boxplot(
    [runs[case] for case in cases],
    positions=positions,
    widths=0.55,
    whis=(2.5, 97.5),
    patch_artist=True,
    medianprops={"color": INK, "linewidth": 1.5},
    whiskerprops={"color": INK, "linewidth": 1},
    capprops={"color": INK, "linewidth": 1},
    flierprops={
        "marker": "o",
        "markersize": 3,
        "markerfacecolor": "none",
        "markeredgecolor": INK,
        "markeredgewidth": 0.6,
    },
)
for box, case in zip(boxes["boxes"], cases):
    box.set(**STYLE[CASES[case][1]], linewidth=1.2)
    if case.endswith(SOURCE_SUFFIX):
        box.set_hatch(SOURCE_HATCH)
ax_a.scatter(
    positions + 0.42,
    [deterministic[case.removesuffix(SOURCE_SUFFIX)] for case in cases],
    marker="D",
    s=28,
    color=INK,
    zorder=3,
)
ax_a.set_xticks(positions, [CASES[case][0] for case in cases], fontsize=9)
ax_a.set_xlim(-0.6, len(cases) - 0.3)
ax_a.set_ylim(0, None)
ax_a.set_ylabel("climate change impacts\n(kg CO$_2$-eq. GWP100)")
ax_a.set_title("(a)", fontsize=11)
ax_a.grid(axis="y", color="#e5e5e5", linewidth=0.8)
ax_a.set_axisbelow(True)

# (b) relative spread per dispersion measure, with bootstrap 95% confidence intervals
offsets = (np.arange(len(cases)) - (len(cases) - 1) / 2) * 0.18
for offset, case in zip(offsets, cases):
    model = CASES[case][1]
    is_source = case.endswith(SOURCE_SUFFIX)
    data = dispersion[dispersion["case"] == case]
    x = np.arange(len(MEASURES)) + offset
    ax_b.errorbar(
        x,
        data["value"] * 100,
        yerr=[
            (data["value"] - data["bootstrap 2.5th percentile"]) * 100,
            (data["bootstrap 97.5th percentile"] - data["value"]) * 100,
        ],
        fmt="s" if is_source else "o",
        markersize=5,
        markerfacecolor="white" if is_source else STYLE[model]["edgecolor"],
        markeredgecolor=STYLE[model]["edgecolor"],
        markeredgewidth=1.5,
        ecolor=STYLE[model]["edgecolor"],
        elinewidth=1.2,
        capsize=3,
        linestyle="none",
    )
ax_b.set_xticks(np.arange(len(MEASURES)), list(MEASURES), fontsize=9)
ax_b.set_xlim(-0.5, len(MEASURES) - 0.5)
ax_b.set_ylim(0, None)
ax_b.set_ylabel("relative spread (%)")
ax_b.set_title("(b)", fontsize=11)
ax_b.grid(axis="y", color="#e5e5e5", linewidth=0.8)
ax_b.set_axisbelow(True)
for boundary in np.arange(len(MEASURES) - 1) + 0.5:
    ax_b.axvline(boundary, color="#cccccc", linewidth=0.8)

# shared legend
handles = [
    plt.Rectangle((0, 0), 1, 1, linewidth=1.2, **STYLE["full"]),
    plt.Rectangle((0, 0), 1, 1, linewidth=1.2, **STYLE["single"]),
]
labels = ["full value chain", "single process"]
if any(case.endswith(SOURCE_SUFFIX) for case in cases):
    handles.append(
        plt.Rectangle(
            (0, 0),
            1,
            1,
            facecolor="white",
            edgecolor=INK,
            hatch=SOURCE_HATCH,
            linewidth=1,
        )
    )
    labels.append("source-data SD95\n(a: hatched; b: open square)")
handles.append(
    plt.Line2D([], [], marker="D", color=INK, linestyle="none", markersize=6)
)
labels.append("deterministic score")
fig.legend(
    handles,
    labels,
    loc="lower center",
    ncol=len(labels),
    frameon=False,
    fontsize=9,
    bbox_to_anchor=(0.5, -0.02),
)

fig.tight_layout(rect=(0, 0.1, 1, 1))
for suffix in ("png", "pdf"):
    fig.savefig(
        RESULTS_DIR / f"figure_monte_carlo.{suffix}", dpi=300, bbox_inches="tight"
    )

print(f"{n_runs} Monte Carlo runs per case")
print(
    dispersion.assign(value=dispersion["value"].round(4))
    .pivot(index="case", columns="measure", values="value")
    .loc[cases]
    .to_string()
)
print(f"Figure written to {RESULTS_DIR / 'figure_monte_carlo.png'}")

# %%
