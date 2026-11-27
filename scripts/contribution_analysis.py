# %%
"""Contribution analysis of the LCA cases (EF 3.1 climate change).

Splits each score over the foreground activities (the DPPs: panel, cell, wafer, ...)
and over what they take in from outside the foreground: their direct emissions and their
inputs from the conversion databases or EXIOBASE, each counted with its full upstream
(life-cycle) impact. Inputs from other foreground activities (components) are not
counted at the activity that buys them, but at the level of the component itself, so the
contributions add up to the total score without double counting.

Run in the same session, after SI4 has finished (paste into a new cell), as with
bom_contributions.py. Uses lca and _lu from SI4.
Writes results/contributions.csv and prints a summary per case.
"""

bw.projects.set_current(project_name)  # SI4 ends in the ecoinvent project
lca.switch_method(method_ef31)
lca.fix_dictionaries()

A = lca.technosphere_matrix.tocsc()
# direct impact per unit of each activity, and life-cycle impact per unit of each product
h = np.asarray((lca.characterization_matrix @ lca.biosphere_matrix).sum(axis=0)).ravel()
s = scipy.linalg.lu_solve(_lu, h, trans=1, check_finite=False)

rev_act, rev_prod, _ = lca.reverse_dict()
foreground_keys = [key for key in lca.activity_dict if key[0].startswith(pv_db_name)]
foreground_cols = [lca.activity_dict[key] for key in foreground_keys]
foreground_rows = {lca.product_dict[key] for key in foreground_keys}


def contributions(case, functional_unit):
    lca.redo_lcia(functional_unit)
    x = lca.supply_array
    rows = []
    for col in foreground_cols:
        if x[col] == 0:
            continue
        activity = bw.get_activity(rev_act[col])
        rows.append(
            {
                "case": case,
                "foreground activity": activity["name"],
                "input": "direct emissions",
                "input database": "",
                "input location": "",
                "kg CO2-eq per m2 panel": h[col] * x[col],
            }
        )
        column = A[:, col]
        for row, amount in zip(column.indices, column.data):
            if row in foreground_rows:
                continue  # production exchange or component: counted at its own level
            supplier = bw.get_activity(rev_prod[row])
            rows.append(
                {
                    "case": case,
                    "foreground activity": activity["name"],
                    "input": supplier["name"],
                    "input database": supplier["database"],
                    "input location": supplier.get("location", ""),
                    "kg CO2-eq per m2 panel": -amount * x[col] * s[row],
                }
            )
    df = pd.DataFrame(rows)
    total = df["kg CO2-eq per m2 panel"].sum()
    assert np.isclose(total, lca.score, rtol=1e-6), (case, total, lca.score)
    return df


contribution_table = pd.concat(
    [contributions(case, fu) for case, fu in functional_units.items()],
    ignore_index=True,
)
contribution_table["share of score"] = contribution_table[
    "kg CO2-eq per m2 panel"
] / contribution_table.groupby("case")["kg CO2-eq per m2 panel"].transform("sum")
contribution_table.to_csv(RESULTS_DIR / "contributions.csv", index=False)

with pd.option_context(
    "display.width", 250, "display.max_colwidth", 70, "display.precision", 3
):
    for case in functional_units:
        df = contribution_table[contribution_table["case"] == case]
        print(
            f"\n=== {case}: {df['kg CO2-eq per m2 panel'].sum():.2f} kg CO2-eq per m2"
        )
        print("by foreground activity (DPP level):")
        print(
            df.groupby("foreground activity")[
                ["kg CO2-eq per m2 panel", "share of score"]
            ]
            .sum()
            .sort_values("kg CO2-eq per m2 panel", ascending=False)
        )
        print("largest inputs (summed over foreground activities):")
        print(
            df.groupby("input")[["kg CO2-eq per m2 panel", "share of score"]]
            .sum()
            .sort_values("kg CO2-eq per m2 panel", ascending=False)
            .head(10)
        )

# %%
