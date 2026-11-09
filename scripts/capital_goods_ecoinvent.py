"""Capital goods (infrastructure) contributions in the ecoinvent run (R3, process coverage).

Run in the same session, after SI4 has finished (paste into a new cell). Uses `lca_ei`,
`fu_ecoinvent`, `ei_project_name`, `ecoinvent_name`, `ei_pv_name` and `RESULTS_DIR`.

Capital goods are identified by the unit of their reference product (unit, meter-year,
square meter, ...) plus a few name keywords for machinery measured in kg. Check the
printed list of the largest contributors and adjust CAPITAL_UNITS / CAPITAL_KEYWORDS /
NOT_CAPITAL if needed.

Method (exact and additive):
  contribution of capital good i = d_i * s_i, where
  d_i = amount of i used by all activities that are NOT capital goods, and
  s_i = full life-cycle score per unit of i (including the capital goods it uses itself).
Their sum equals the drop in the score when every link to a capital good is cut, which is
recalculated as a check.

Writes results/capital_goods_ecoinvent.csv.
"""

import numpy as np
import scipy.sparse as sp
from bw2calc.lca import spsolve  # pypardiso if installed, otherwise scipy

CAPITAL_UNITS = {
    "unit",
    "meter",
    "meter-year",
    "square meter",
    "square meter-year",
    "cubic meter-year",
    "kilometer",
    "kilometer-year",
}
CAPITAL_KEYWORDS = ["industrial machine", "building, hall", "building, multi-storey"]
NOT_CAPITAL = ["pallet"]  # 'unit' products that are not capital goods

bw.projects.set_current(ei_project_name)  # SI4 ends here, but make sure
lca_ei.redo_lcia({fu_ecoinvent: 1.0})
lca_ei.fix_dictionaries()

# --- metadata of all ecoinvent activities ----------------------------------------------
meta = {}
for act in bw.Database(ecoinvent_name):
    meta[act.key] = {
        "name": act["name"],
        "reference product": act.get("reference product", ""),
        "location": act["location"],
        "unit": act["unit"],
    }


def is_capital(key):
    m = meta.get(key)
    if m is None:  # foreground (PV LCI ecoinvent) activities
        return False
    label = f"{m['name']} {m['reference product']}".lower()
    if any(word in label for word in NOT_CAPITAL):
        return False
    return m["unit"] in CAPITAL_UNITS or any(word in label for word in CAPITAL_KEYWORDS)


# --- matrices -------------------------------------------------------------------------
T = lca_ei.technosphere_matrix.tocsc()
x = lca_ei.supply_array  # activity levels (columns)
h = np.asarray(
    (lca_ei.characterization_matrix @ lca_ei.biosphere_matrix).sum(axis=0)
).ravel()  # direct characterised emissions per unit of each activity (columns)
score = float(h @ x)

row_of = lca_ei.product_dict  # key -> row
col_of = lca_ei.activity_dict  # key -> column
capital_rows = np.array([i for k, i in row_of.items() if is_capital(k)])
capital_cols = np.array([j for k, j in col_of.items() if is_capital(k)])
foreground_cols = np.array([j for k, j in col_of.items() if k[0] == ei_pv_name])

# s: life-cycle score per unit of each product (rows), from T^T s = h
s = spsolve(T.T.tocsr(), h)

# d: use of each product by non-capital activities, split in foreground / background
inputs = -T  # off-diagonal entries: input of product (row) per unit of activity (column)
non_capital = np.ones(len(x), dtype=bool)
non_capital[capital_cols] = False
is_foreground = np.zeros(len(x), dtype=bool)
is_foreground[foreground_cols] = True
d_fg = inputs @ (x * (non_capital & is_foreground))
d_bg = inputs @ (x * (non_capital & ~is_foreground))

contribution_fg = d_fg[capital_rows] * s[capital_rows]
contribution_bg = d_bg[capital_rows] * s[capital_rows]

# --- check: cut every link to a capital good and recalculate ---------------------------
keep = np.ones(T.shape[0])
keep[capital_rows] = 0.0
diagonal = T.diagonal()
T_cut = (sp.diags(keep) @ T + sp.diags(diagonal * (1 - keep))).tocsc()
x_cut = spsolve(T_cut, lca_ei.demand_array)
score_cut = float(h @ x_cut)

total_capital = contribution_fg.sum() + contribution_bg.sum()
print(f"ecoinvent score:                         {score:8.3f} kg CO2-eq per m2 panel")
print(f"capital goods, total:                    {total_capital:8.3f} ({total_capital / score:.1%})")
print(f"  foreground infrastructure (factories): {contribution_fg.sum():8.3f}")
print(f"  background capital goods:              {contribution_bg.sum():8.3f}")
print(f"check, score with capital goods cut:     {score_cut:8.3f} "
      f"(difference {score - score_cut:.3f} should equal the total)")

# --- table of contributors ------------------------------------------------------------
key_of_row = {i: k for k, i in row_of.items()}
table = pd.DataFrame(
    {
        "name": [meta[key_of_row[i]]["name"] for i in capital_rows],
        "reference product": [meta[key_of_row[i]]["reference product"] for i in capital_rows],
        "location": [meta[key_of_row[i]]["location"] for i in capital_rows],
        "unit": [meta[key_of_row[i]]["unit"] for i in capital_rows],
        "foreground (kg CO2-eq per m2)": contribution_fg,
        "background (kg CO2-eq per m2)": contribution_bg,
    }
)
table["total (kg CO2-eq per m2)"] = (
    table["foreground (kg CO2-eq per m2)"] + table["background (kg CO2-eq per m2)"]
)
table = table[table["total (kg CO2-eq per m2)"].abs() > 0].sort_values(
    "total (kg CO2-eq per m2)", ascending=False
)
table.to_csv(RESULTS_DIR / "capital_goods_ecoinvent.csv", index=False)
with pd.option_context("display.width", 250, "display.max_colwidth", 60, "display.precision", 4):
    print("\nLargest contributors:")
    print(table.head(20).to_string(index=False))

lca_ei.redo_lcia({fu_ecoinvent: 1.0})  # leave lca_ei as it was
