# %%
"""Readable contribution tables for Supplementary Information 3.

Builds four DataFrames from results/contributions.csv (written by contribution_analysis.py
after SI4) and the mappings in SI2, and saves them as sheets of
results/contribution_tables.xlsx. All values in kg CO2-eq. (EF 3.1) per m2 of PV panel.

- levels:  contribution per level of the value chain (R2, R4)
- top_inputs:  the largest inputs per case, with their EXIOBASE category
- bom_bridge:  difference between the BoM and full value-chain results (R1)
- matching:  inputs whose contribution differs between the manual and CAML mappings (R4)

    python scripts/contribution_tables.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
SI2 = ROOT / "si" / "SI2 - conversions used.xlsx"

VALUE = "kg CO2-eq per m2 panel"
TOP_N = 15
GRID = "electricity, medium voltage, at grid"
PANEL = "photovoltaic panel, single-Si, at plant"
CAML_CASES = {
    "CAML LCA": "caml_automated",
    "CAML LCA (reviewer, top 5)": "caml_human_in_the_loop",
}

# value-chain levels, from product to raw material
LEVELS = {
    "photovoltaic panel": "PV panel",
    "photovoltaic cell": "PV cell",
    "single-Si wafer": "single-Si wafer",
    "CZ single crystalline silicon": "CZ silicon",
    "silicon, production mix": "silicon production mix",
    "silicon, solar grade": "solar-grade silicon",
    "MG-silicon": "MG silicon",
}

contributions = pd.read_csv(RESULTS_DIR / "contributions.csv")
contributions["input"] = contributions["input"].fillna("direct emissions")
contributions["process"] = (
    contributions["foreground activity"].str.rsplit(" - ", n=1).str[0]
)
mapping = {
    sheet: pd.read_excel(SI2, sheet_name=sheet).set_index("description")
    for sheet in ["manual", *CAML_CASES.values()]
}


def by_case(case):
    return contributions[contributions["case"] == case]


# ---------------------------------------------------------------------------- levels
def level(row):
    if row["case"] == "single LCA":  # the cell is a direct EXIOBASE input of the panel
        return "PV cell" if row["input database"] == "EXIO3H" else "PV panel"
    return next(
        (
            label
            for prefix, label in LEVELS.items()
            if row["process"].startswith(prefix)
        ),
        row["process"],
    )


cases = ["full LCA", "single LCA", *CAML_CASES]
data = contributions[contributions["case"].isin(cases)].assign(
    level=lambda df: df.apply(level, axis=1)
)
levels = data.pivot_table(index="level", columns="case", values=VALUE, aggfunc="sum")
levels = levels.reindex(index=list(LEVELS.values()), columns=cases)
levels.loc["total"] = levels.sum()


# ---------------------------------------------------------------------------- top inputs
def linked_to(case, input_name, database):
    """EXIOBASE category (code) that an input is linked to in this case."""
    if input_name == "direct emissions":
        return "direct emissions of the DPP process"
    if input_name == GRID:
        return "grid mix (SI2, 'grid_mix')"
    if database == "EXIO3H":  # BoM materials and the single-process cell
        return "EXIOBASE activity (linked directly)"
    sheet = CAML_CASES.get(case, "manual")
    row = mapping[sheet].loc[input_name]
    return f"{row['EXIO3 description']} ({row['EXIO3 code']})"


def top_inputs_for(case):
    df = (
        by_case(case)
        .groupby(["input", "input database"], dropna=False)[VALUE]
        .sum()
        .reset_index()
        .query(f"`{VALUE}` != 0")
        .sort_values(VALUE, ascending=False)
    )
    df["linked to"] = [
        linked_to(case, i, d) for i, d in zip(df["input"], df["input database"])
    ]
    top = df.head(TOP_N)[["input", "linked to", VALUE]]
    rest = df.iloc[TOP_N:]
    if len(rest):
        top.loc[len(top)] = [f"other ({len(rest)} inputs)", "", rest[VALUE].sum()]
    top.loc[len(top)] = ["total", "", df[VALUE].sum()]
    top["share of score"] = top[VALUE] / df[VALUE].sum()
    return top.assign(case=case).set_index(["case", "input"])


top_inputs = pd.concat(top_inputs_for(case) for case in contributions["case"].unique())


# ---------------------------------------------------------------------------- R1 bridge
PLASTICS = (
    "ethylvinylacetate",
    "polyethylene",
    "polyvinylfluoride",
    "polyamide",
    "plastic",
)
BOM_MATERIALS = {
    "Aluminium": "aluminium",
    "glass": "glass",
    "Precious": "silver / metallisation paste",
    "Plastics": "plastics",
    "Chemicals": "silicon",
    "Copper": "copper and tin",
    "tin": "copper and tin",
}


def bridge_group(row):
    name, on_panel = row["input"], row["process"].startswith(PANEL)
    if row["case"].startswith("BoM"):
        return next(
            (g for key, g in BOM_MATERIALS.items() if key in name), "other materials"
        )
    if name == "direct emissions":
        return "processing: direct emissions"
    if name.startswith("electricity"):
        return (
            "processing: electricity, panel"
            if on_panel
            else "processing: electricity, Si-wafer-cell chain"
        )
    if "metallization paste" in name:
        return "silver / metallisation paste"
    if on_panel and "aluminium" in name:
        return "aluminium"
    if on_panel and ("solar glass" in name or "tempering" in name):
        return "glass"
    if on_panel and any(p in name for p in PLASTICS):
        return "plastics"
    if name.startswith(("copper, at", "tin, at")):
        return "copper and tin"
    return "processing: other inputs"


bom_cases = ["full LCA", "BoM LCA", "BoM LCA (with location)"]
data = contributions[contributions["case"].isin(bom_cases)].assign(
    group=lambda df: df.apply(bridge_group, axis=1)
)
bom_bridge = data.pivot_table(
    index="group", columns="case", values=VALUE, aggfunc="sum", fill_value=0
)
bom_bridge = bom_bridge[bom_cases]
bom_bridge = bom_bridge[bom_bridge.abs().sum(axis=1) > 0].sort_index(
    key=lambda idx: ~idx.str.startswith("processing")  # processing rows first
)
bom_bridge.loc["total"] = bom_bridge.sum()
bom_bridge["difference, BoM"] = bom_bridge["BoM LCA"] - bom_bridge["full LCA"]
bom_bridge["difference, BoM with location"] = (
    bom_bridge["BoM LCA (with location)"] - bom_bridge["full LCA"]
)


# ---------------------------------------------------------------------------- R4 matching
def outcome(input_name, sheet):
    manual_code = mapping["manual"]["EXIO3 code"].get(input_name)
    row = mapping[sheet].loc[input_name]
    if pd.isna(row["conversion factor"]):
        return "dropped"
    return "same" if row["EXIO3 code"] == manual_code else "remapped"


per_input = pd.DataFrame(
    {
        case: by_case(case).groupby("input")[VALUE].sum()
        for case in ["full LCA", *CAML_CASES]
    }
).fillna(0)
# keep inputs whose contribution differs in either CAML case (grid electricity uses the grid
# mix in all cases)
differs = (
    per_input[list(CAML_CASES)]
    .sub(per_input["full LCA"], axis=0)
    .abs()
    .gt(0.005)
    .any(axis=1)
)
inputs = per_input.index[differs & (per_input.index != GRID)]

matching = pd.DataFrame(
    {
        "manual code": mapping["manual"]["EXIO3 code"].reindex(inputs),
        "baseline": per_input.loc[inputs, "full LCA"],
    }
)
for case, sheet in CAML_CASES.items():
    matching[f"{case}: code"] = mapping[sheet]["EXIO3 code"].reindex(inputs)
    matching[f"{case}: outcome"] = [outcome(i, sheet) for i in inputs]
    matching[case] = per_input.loc[inputs, case]
    matching[f"{case}: difference"] = matching[case] - matching["baseline"]
matching = matching.sort_values(f"{next(iter(CAML_CASES))}: difference").rename_axis(
    "input"
)

matching_summary = pd.DataFrame(
    {
        case: matching.groupby(f"{case}: outcome")[f"{case}: difference"].sum()
        for case in CAML_CASES
    }
).fillna(0)
matching_summary.loc["total"] = matching_summary.sum()


if __name__ == "__main__":
    with pd.ExcelWriter(RESULTS_DIR / "contribution_tables.xlsx") as writer:
        levels.round(2).to_excel(writer, sheet_name="levels")
        top_inputs.round(3).to_excel(writer, sheet_name="top inputs")
        bom_bridge.round(2).to_excel(writer, sheet_name="R1 BoM vs full LCI")
        matching.round(2).to_excel(writer, sheet_name="R4 matching")
        matching_summary.round(2).to_excel(writer, sheet_name="R4 matching summary")
    print(f"Written: {RESULTS_DIR / 'contribution_tables.xlsx'}")

# %%
