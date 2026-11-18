"""Attribute the change in the CAML LCA result to the changes in SI2 'caml_mapping'.

Run in the same session after SI4 has finished (paste into a new cell of the interactive
window). It uses SI4's objects: lca, method_ef31, functional_unit_caml, project_name,
resconv_caml_db, res_conv_caml, prod_act_map, country_conv, exio3h_pp_by_prod and
RESULTS_DIR. Writes results/attribution_caml_changes.csv.

The previous mapping is the 'caml_mapping' sheet of SI2 as used up to 16 November
(only the rows that changed; code None = not linked, factor None = no conversion).
For each changed input: contribution = amount per m2 panel x impact of its EXIOBASE link,
with the link built the same way as in SI4 (regional split by principal production).
"""

OLD_CAML_MAPPING = {
    'alkylbenzene sulfonate, linear, petrochemical, at plant': ('C_CHBI', 0.001),
    'aluminium alloy, AlMg3, at plant': ('C_CONS', 0.0),
    'ceramic tiles, at regional storage': ('C_TDRT', 0.0),
    'charcoal, at plant': ('C_WOOD', 0.001),
    'chromium steel 18/8, at plant': ('C_STEL', 0.001),
    'copper, at regional storage': ('C_COPP', 0.001),
    'diode, unspecified, at plant': ('C_TDRT', 0.0),
    'disposal, used mineral oil, 10% water, to hazardous waste incineration': ('C_INCO', 0.001),
    'electricity, at cogen 1MWe lean burn, allocation exergy': ('C_CONS', 1.2e-07),
    'electricity, hydropower, at run-of-river power plant': ('C_CONS', 1.2e-07),
    'electricity, medium voltage, at grid': ('C_CONS', 1.2e-07),
    'graphite, at plant': ('C_ONMM', 0.001),
    'hard coal coke, at plant': ('C_CLPT', 3.7037037037037037e-05),
    'heat, at cogen 1MWe lean burn, allocation exergy': (None, None),
    'lead, at regional storage': ('C_FABM', 0.001),
    'natural gas, burned in industrial furnace low-NOx >100kW': ('C_GASS', 2.2271714922048998e-05),
    'nitric acid, 50% in H2O, at plant': ('C_CHBI', 0.001),
    'oxygen, liquid, at plant': ('C_WATR', 7e-10),
    'phosphoryl chloride, at plant': ('C_NFER', 0.001),
    'photovoltaic cell factory': (None, 0.0),
    'photovoltaic panel factory': (None, 0.0),
    'polyethylene terephthalate, granulate, amorphous, at plant': ('C_CHBI', 0.001),
    'polyethylene, HDPE, granulate, at plant': ('C_PLAS', 0.001),
    'polyvinylfluoride film, at plant': ('C_CHBI', 0.001),
    'potassium hydroxide, at regional storage': ('C_CHBI', 0.001),
    'refrigerant R134a, at plant': ('C_ELMA', 0.001),
    'silane, at plant': ('C_ONMM', 0.001),
    'silica sand, at plant': ('C_ONMM', 0.001),
    'silicone plant': ('C_CONS', 0.0),
    'silicone product, at plant': ('C_ONMM', 0.001),
    'soap, at plant': ('C_RUBP', 0.001),
    'solar glass, low-iron, at regional storage': ('C_TDRT', 0.0),
    'tempering, flat glass': ('C_GLAS', 0.001),
    'tin, at regional storage': ('C_LZTP', 0.001),
    'treatment, PV cell production effluent, to wastewater treatment, class 3': ('C_WATR', 7e-10),
    'treatment, sewage, from residence, to wastewater treatment, class 2': ('C_WASO', 0.0),
    'treatment, sewage, to wastewater treatment, class 2': ('C_WASO', 0.0),
    'wire drawing, copper': ('C_COPP', 0.001),
}

bw.projects.set_current(project_name)  # SI4 ends in the ecoinvent project
lca.switch_method(method_ef31)
lca.redo_lcia(functional_unit_caml)
lca.fix_dictionaries()
caml_now = lca.score
supply = {key: lca.supply_array[i] for key, i in lca.activity_dict.items()}


def regions_of(location):
    if location not in country_conv.columns:
        return [location]
    return country_conv.index[country_conv.loc[:, location] != 0].to_list()


def link_score(code, factor, location):
    """Impact per unit of input of a link to EXIOBASE product `code` (as SI4 builds it)."""
    if code is None or factor is None or pd.isna(factor) or factor == 0:
        return 0.0
    regions = regions_of(location)
    if len(regions) == 1:
        shares = pd.Series(1.0, index=regions)
    else:
        pp = exio3h_pp_by_prod.xs(code, level=1)[regions]
        shares = pp / pp.sum()
    demand = {
        ("EXIO3H", f"{prod_act_map[code]} - {region}"): factor * share
        for region, share in shares.items()
        if share
    }
    lca.redo_lcia(demand)
    return lca.score


new_map = res_conv_caml.drop_duplicates("description").set_index("description")
rows = []
for act in resconv_caml_db:
    name = act["name"]
    if name not in OLD_CAML_MAPPING:
        continue
    amount = supply.get(act.key, 0.0)
    old_code, old_factor = OLD_CAML_MAPPING[name]
    new_code = new_map.at[name, "EXIO3 code"] if name in new_map.index else None
    new_factor = new_map.at[name, "conversion factor"] if name in new_map.index else None
    new_code = None if pd.isna(new_code) or new_code in (0, "0") else new_code
    lca.redo_lcia({act.key: 1.0})
    per_unit_now = lca.score  # what SI4 actually linked
    rows.append(
        {
            "input": name,
            "location": act["location"],
            "unit": act["unit"],
            "amount per m2 panel": amount,
            "before": f"{old_code} x {old_factor}",
            "now": f"{new_code} x {new_factor}",
            "contribution before": amount * link_score(old_code, old_factor, act["location"]),
            "contribution now": amount * per_unit_now,
            "check: rebuilt now": amount * link_score(new_code, new_factor, act["location"]),
        }
    )

attribution = pd.DataFrame(rows)
attribution["change"] = attribution["contribution now"] - attribution["contribution before"]
attribution = attribution.sort_values("change")
with pd.option_context("display.width", 250, "display.max_colwidth", 55):
    print(attribution.drop(columns="check: rebuilt now").to_string(index=False))
mismatch = (attribution["contribution now"] - attribution["check: rebuilt now"]).abs().max()
print(f"\nSum of changes: {attribution['change'].sum():.2f} kg CO2-eq; CAML LCA now {caml_now:.2f}")
print(f"Check (rebuilt links vs SI4's links), largest difference: {mismatch:.2e}")
attribution.to_csv(RESULTS_DIR / "attribution_caml_changes.csv", index=False)
lca.redo_lcia(functional_unit_caml)
