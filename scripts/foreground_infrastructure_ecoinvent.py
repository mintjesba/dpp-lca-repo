"""Foreground infrastructure in the ecoinvent run (R3, process coverage).

The EXIOBASE route excludes the four infrastructure inputs of the DPPs (cell factory,
panel factory, wafer factory, silicone plant); the ecoinvent route includes them. This
quantifies their contribution to the ecoinvent result.

Run in the same session, after SI4 has finished (paste into a new cell).
Writes results/foreground_infrastructure_ecoinvent.csv.
"""

FOREGROUND_INFRASTRUCTURE = [
    "photovoltaic cell factory",
    "photovoltaic panel factory",
    "wafer factory",
    "silicone plant",
]

bw.projects.set_current(ei_project_name)  # SI4 ends here, but make sure
lca_ei.redo_lcia({fu_ecoinvent: 1.0})
lca_ei.fix_dictionaries()
total = lca_ei.score
supply = {key: lca_ei.supply_array[i] for key, i in lca_ei.activity_dict.items()}

rows = []
for act in bw.Database(ei_pv_name):
    for exc in act.technosphere():
        if exc.get("name") in FOREGROUND_INFRASTRUCTURE:
            amount = supply.get(act.key, 0.0) * exc["amount"]  # units per m2 panel
            lca_ei.redo_lcia({exc.input.key: amount})
            rows.append(
                {
                    "process": act["name"],
                    "location": act["location"],
                    "infrastructure": exc["name"],
                    "units per m2 panel": amount,
                    "kg CO2-eq per m2 panel": lca_ei.score,
                }
            )
lca_ei.redo_lcia({fu_ecoinvent: 1.0})  # leave lca_ei as it was

infrastructure = pd.DataFrame(rows).sort_values("kg CO2-eq per m2 panel", ascending=False)
infrastructure.to_csv(RESULTS_DIR / "foreground_infrastructure_ecoinvent.csv", index=False)
print(infrastructure.to_string(index=False))
fg_total = infrastructure["kg CO2-eq per m2 panel"].sum()
print(f"\nForeground infrastructure: {fg_total:.3f} of {total:.3f} kg CO2-eq per m2 panel "
      f"({fg_total / total:.1%})")
