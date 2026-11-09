"""Attribute the change in the full LCA result to the SI2 values changed since the last
commit (RC 1b). Run in the same session, after SI4 has finished, e.g. by pasting this
into a new cell in the interactive window. Writes results/attribution_si2_changes.csv.
"""

# %% Attribution: which SI2 changes moved the full LCA result (EF 3.1)
# Conversion factors in the last commit (RC 1b) for the rows changed since.
# Each change is a pure factor change, so: change = amount x impact per unit x (1 - old/new).
old_cf = {
    "natural gas, burned in industrial furnace low-NOx >100kW": 2.0512820512820512e-08,
    "transport, freight, rail": 2.336e-07,
    "transport, transoceanic freight ship": 2.336e-07,
    "treatment, PV cell production effluent, to wastewater treatment, class 3": 0.0,
    "treatment, sewage, from residence, to wastewater treatment, class 2": 0.0,
    "treatment, sewage, to wastewater treatment, class 2": 0.0,
    "heat, at cogen 1MWe lean burn, allocation exergy": 0.0,
}
new_cf = res_conv.set_index("description")["conversion factor"]

bw.projects.set_current(project_name)  # SI4 ends in the ecoinvent project

lca.switch_method(method_ef31)
lca.redo_lcia(functional_unit_full)
lca.fix_dictionaries()
total_now = lca.score
supply = {key: lca.supply_array[i] for key, i in lca.activity_dict.items()}

rows = []
for conv_act in resconv_db:
    name = conv_act["name"]
    if name not in old_cf or not new_cf[name]:
        continue
    amount = supply.get(conv_act.key, 0.0)  # resource units per m2 panel
    lca.redo_lcia({conv_act.key: 1.0})
    per_unit = lca.score
    ratio = old_cf[name] / new_cf[name]
    rows.append(
        {
            "resource": name,
            "location": conv_act["location"],
            "unit": conv_act["unit"],
            "amount per m2 panel": amount,
            "kg CO2-eq per unit (now)": per_unit,
            "contribution before": amount * per_unit * ratio,
            "contribution now": amount * per_unit,
            "change": amount * per_unit * (1 - ratio),
        }
    )

attribution = pd.DataFrame(rows).sort_values("change")
print(attribution.to_string(index=False))
print(f"\nSum of changes: {attribution['change'].sum():.2f} kg CO2-eq; full LCA now {total_now:.2f}")
attribution.to_csv(RESULTS_DIR / "attribution_si2_changes.csv", index=False)
