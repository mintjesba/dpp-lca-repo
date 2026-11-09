"""R1 diagnostics: contribution of each BoM line to climate change, for the BoM without
origin information (all China) and with the origins of the full inventory.

Run in the same session, after SI4 has finished (paste into a new cell).
Writes results/bom_contributions.csv (per line and region) and prints a summary per
material.
"""

bw.projects.set_current(project_name)  # SI4 ends in the ecoinvent project
lca.switch_method(method_ef31)
act_prod_map = {a: p for p, a in prod_act_map.items()}

rows = []
for variant, bom_act in [
    ("no location", bw.get_activity(pv_panel_bom_no_location.key)),
    ("with location", bw.get_activity(pv_panel_bom_with_location.key)),
]:
    for exc in bom_act.technosphere():
        activity_code, region = exc.input.key[1].split(" - ")
        lca.redo_lcia({exc.input.key: exc["amount"]})
        rows.append(
            {
                "variant": variant,
                "EXIO3 code": act_prod_map[activity_code],
                "region": region,
                "mass (kg per m2 panel)": exc["amount"] * 1000,  # tonnes -> kg
                "kg CO2-eq per m2 panel": lca.score,
            }
        )

contributions = pd.DataFrame(rows)
contributions.to_csv(RESULTS_DIR / "bom_contributions.csv", index=False)

summary = contributions.pivot_table(
    index="EXIO3 code",
    columns="variant",
    values=["mass (kg per m2 panel)", "kg CO2-eq per m2 panel"],
    aggfunc="sum",
)
summary[("kg CO2-eq per kg", "no location")] = (
    summary[("kg CO2-eq per m2 panel", "no location")]
    / summary[("mass (kg per m2 panel)", "no location")]
)
summary[("kg CO2-eq per kg", "with location")] = (
    summary[("kg CO2-eq per m2 panel", "with location")]
    / summary[("mass (kg per m2 panel)", "with location")]
)
summary[("change", "kg CO2-eq per m2 panel")] = (
    summary[("kg CO2-eq per m2 panel", "with location")]
    - summary[("kg CO2-eq per m2 panel", "no location")]
)
summary = summary.sort_values(("change", "kg CO2-eq per m2 panel"))
with pd.option_context("display.width", 250, "display.max_columns", None, "display.precision", 3):
    print(summary)
    print("\nTotals:", contributions.groupby("variant")["kg CO2-eq per m2 panel"].sum().round(2).to_dict())
    masses = summary["mass (kg per m2 panel)"]
    print("Mass check (should be identical):", (masses["no location"] - masses["with location"]).abs().max())
