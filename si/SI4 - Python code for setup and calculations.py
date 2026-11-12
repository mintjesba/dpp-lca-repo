# %% Import modules
# data handling
import pandas as pd
import numpy as np

# lca
import brightway2 as bw
import bw2calc
import scipy.linalg

# timing of the main steps
import time

_t_start = time.perf_counter()


def log_time(step):
    print(f"[{time.perf_counter() - _t_start:6.0f} s] {step}")


print("Sparse solver:", bw2calc.lca.spsolve.__module__)  # 'pypardiso...' if installed

# %% files
# Paths are resolved relative to this script, so it runs from any working directory.
from pathlib import Path

try:
    SI_DIR = Path(__file__).resolve().parent
except NameError:  # interactive cell execution without __file__
    SI_DIR = Path.cwd()

RESULTS_DIR = SI_DIR.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

conv_table_filename = SI_DIR / "SI2 - conversions used.xlsx"
dpps_filename = SI_DIR / "SI1 - DPP LCI information.xlsx"

# %% Create or set BW2 project with EXIO3H background and biosphere database
# This assumes the project with name "exiobase_in_bw" is set up with EXIOBASE 3 Hybrid
# -> https://github.com/mintjesba/exio3_in_brightway2
project_name = "dpp_lca"

if project_name not in bw.projects:
    bw.projects.set_current("exiobase_in_bw")
    bw.projects.copy_project(project_name)

bw.projects.set_current(project_name)

# %% Instantiate BW databases
# delete earlier runs
for db_name in [
    "PV LCI",
    "PV LCI CAML",
    "PV LCI CAML HITL",
    "resource conversion",
    "resource conversion CAML",
    "resource conversion CAML HITL",
]:
    if db_name in bw.databases:
        del bw.databases[db_name]

# For the primary data from PVPS T12
pv_db_name = "PV LCI"
pv_db = bw.Database(pv_db_name)

# For the conversion to EXIOBASE 3H
resconv_db_name = "resource conversion"
resconv_db = bw.Database(resconv_db_name)

# %% Set up biosphere conversion
bs_conv = pd.read_excel(conv_table_filename, sheet_name="emissions")

# %% Load DPPs
with pd.ExcelFile(dpps_filename) as dpp_file:
    dpps = {sn: pd.read_excel(dpp_file, sheet_name=sn) for sn in dpp_file.sheet_names}

# %% Generate activities and exchanges to conversion database
pv_activities = {}
res_conversion_activities = {}

for dppnr, dpp in enumerate(dpps.copy().values()):
    dpp = dpp.copy()[dpp["value"] != 0]

    # Split DPP into product, component, resources, direct emissions
    product_row = dpp.query("type == 'product'").copy()
    components = dpp.query("type == 'component'").copy()
    resources = dpp.query("type == 'resource'").copy()
    emissions = dpp.query("type == 'direct emission'").copy()

    # Create activity for DPP with product information
    product = product_row.iloc[0]
    key = (pv_db_name, f"{product['description']} - {product['location']}")
    name = product["description"]
    unit = product["unit"]
    location = product["location"]

    # Add an activity for this DPP
    pv_activities[key] = {
        "name": f"{name} - {location}",
        "unit": unit,
        "reference product": name,
        "location": location,
        "type": "process",
    }

    # Generate exchanges
    exchanges_df = pd.DataFrame()  # empty dataframe

    # generate exchange keys
    def row_to_key(row):
        name = f"{row['description']} - {row['location']}"

        if row["type"] in ["product", "component"]:
            return (pv_db_name, name)  # connect to activity in pv_db database

        if row["type"] == "resource":
            return (resconv_db_name, name)  # connect to activity in conversion database

        # if neither, then we have a biosphere flow, so connect to key in biosphere database
        uuid_idx = (bs_conv["description"] == row["description"]) & (
            bs_conv["compartment"] == row["location"]
        )

        uuid = bs_conv.loc[uuid_idx, "biosphere3 UUID"].iloc[0]
        return ("biosphere3", uuid)

    # generate keys to connect to for every entry
    exchanges_df["input"] = dpp.apply(row_to_key, axis=1)

    # set name, amount, unit
    exchanges_df["name"] = dpp["description"]
    exchanges_df["location"] = dpp["location"]
    exchanges_df["amount"] = dpp["value"]
    exchanges_df["unit"] = dpp["unit"]

    # set type of exchange
    def row_to_type(row):
        if row["type"] == "product":
            return "production"

        if row["type"] == "direct emission":
            return "biosphere"

        return "technosphere"

    exchanges_df["type"] = dpp.apply(row_to_type, axis=1)

    # set uncertainty
    is_product_or_component = dpp["type"].isin(["product", "component"])

    exchanges_df["uncertainty type"] = 2

    # products and components get no uncertainty
    exchanges_df.loc[is_product_or_component, "uncertainty type"] = 0

    # negative amounts get no uncertainty (as this breaks the MC analysis)
    exchanges_df.loc[exchanges_df["amount"] < 0, "uncertainty type"] = 0

    # SD95 to uncertainty of lognormal
    exchanges_df.loc[~is_product_or_component, "loc"] = np.log(dpp["value"])
    exchanges_df.loc[~is_product_or_component, "scale"] = np.log(
        dpp["SD95"] ** (1 / 1.96)
    )

    exchanges = list(exchanges_df.T.to_dict().values())
    exchanges = [{k: v for k, v in x.items() if v == v} for x in exchanges]

    pv_activities[key]["exchanges"] = exchanges

    # for every resource that needs to be converted, the conversion database should have
    # an activity that connects the resource to its appropriate background categories in
    # EXIOBASE
    def add_conversion_activity(row):
        if row["input"][0] in (pv_db_name, "biosphere3"):
            return

        key = row["input"]
        name = row["name"]
        unit = row["unit"]
        location = row["location"]

        activity = {
            "name": name,
            "unit": unit,
            "reference product": name,
            "location": location,
            "type": "process",
            "exchanges": [
                {
                    "input": key,
                    "type": "production",
                    "unit": unit,
                    "name": name,
                    "location": location,
                    "amount": 1.0,
                    "uncertainty type": 0,
                }
            ],
        }
        res_conversion_activities[key] = activity
        return

    exchanges_df.apply(add_conversion_activity, axis=1)

# %% Write activities to database.
resconv_db.write(res_conversion_activities)
pv_db.write(pv_activities)

resconv_db.copy("resource conversion CAML")
resconv_db.copy("resource conversion CAML HITL")  # CAML with a reviewer (simulated)
log_time("PV LCI and resource conversion databases written")

# %% Set up conversion database
# %%% Load conversions from file
res_conv = pd.read_excel(conv_table_filename, sheet_name="resources")
res_conv_caml = pd.read_excel(conv_table_filename, sheet_name="caml_mapping")
bs_conv = pd.read_excel(conv_table_filename, sheet_name="emissions")
country_conv = pd.read_excel(conv_table_filename, sheet_name="locations", index_col=0)

bom_info = pd.read_excel(conv_table_filename, sheet_name="BoM", nrows=10)

# %%% Load principal production (used as distribution key) from EXIOBASE Zenodo
exio3h_pp = pd.read_csv(
    "https://zenodo.org/records/10148587/files/MR_HIOT_2011_v3_3_18_principal_production.csv",
    header=[0, 1, 2, 3, 4, 5, 6, 7],
).T

exio3h_pp_by_prod = exio3h_pp.droplevel([1, 2, 3, 4, 5])[0]

# %%% Create a mapping from EXIO3H products to activities and to activity names
# Associating EXIO3H products to activities
exio3h_act_prod = (
    exio3h_pp.droplevel([0, 1, 2, 4, 5, 7])  # keep codes only
    .index.to_frame()
    .reset_index(drop=True)
    .drop_duplicates()
    .set_index(1)
)

# create a dict in the form {'C_WOOD': 'A_WOOD', ...}
prod_act_map = exio3h_act_prod.T.to_dict(orient="records")[0]

# Associating EXIO3H products to activity names
exio3h_name_prod = (
    exio3h_pp.droplevel([0, 1, 2, 3, 5, 7])  # keep codes only
    .index.to_frame()
    .reset_index(drop=True)
    .drop_duplicates()
    .set_index(1)
)

# create a dict in the form {'C_WOOD': 'wood', ...}
prod_name_map = exio3h_name_prod.T.to_dict(orient="records")[0]

# %%% Electricity grid mixes (Our World in Data, 2011)
# EXIOBASE 3 hybrid has no grid-electricity product: so we implement a grid mix based on
# external data.
GRID_ELECTRICITY = "electricity, medium voltage, at grid"
GRID_MIX_YEAR = 2011
grid_mix_filename = SI_DIR.parent / "data" / "owid_grid_mix.csv"

OWID_TO_EXIO3 = {
    "Coal": "C_POWC",  # Electricity by coal
    "Gas": "C_POWG",  # Electricity by gas
    "Oil": "C_POWP",  # Electricity by petroleum and other oil derivatives
    "Nuclear": "C_POWN",  # Electricity by nuclear
    "Hydropower": "C_POWH",  # Electricity by hydro
    "Wind": "C_POWW",  # Electricity by wind
    "Solar": "C_POWS",  # Electricity by solar photovoltaic
    "Bioenergy": "C_POWB",  # Electricity by biomass and waste
    "Other renewables": "C_POWM",  # Electricity by Geothermal
}
OWID_TO_DPP_LOCATION = {"CHN": "CN", "DEU": "DE", "NOR": "NO", "KOR": "KR", "USA": "US"}

owid = pd.read_csv(grid_mix_filename)
unmapped = set(owid.columns) - {"Entity", "Code", "Year"} - set(OWID_TO_EXIO3)
if unmapped:
    raise ValueError(f"OWID sources without an EXIOBASE category: {unmapped}")

owid = owid[owid["Year"] == GRID_MIX_YEAR]
generation = owid.set_index(owid["Code"].map(OWID_TO_DPP_LOCATION))[list(OWID_TO_EXIO3)]
generation = generation[generation.index.notna()]

# share of each EXIOBASE electricity product per DPP location (sums to 1)
grid_shares = generation.div(generation.sum(axis=1), axis=0).rename(
    columns=OWID_TO_EXIO3
)

# table for SI2 (sheet 'grid_mix')
grid_mix_table = grid_shares.T
grid_mix_table.insert(
    0, "EXIO3 description", [prod_name_map[p] for p in grid_mix_table.index]
)
grid_mix_table.index.name = "EXIO3 code"
grid_mix_table.to_csv(RESULTS_DIR / "grid_mix.csv")


def regions_for(location):
    """EXIO3H regions for a DPP location, using the 'locations' sheet of SI2."""
    if location not in country_conv.columns:
        return [location]
    return country_conv.index[country_conv.loc[:, location] != 0].to_list()


# %%% CaML: match the input descriptions to NAICS codes
# Automated matching step of the 'CAML' scenario, with CaML (Balaji et al., 2023;
# https://github.com/amazon-science/carbon-assessment-with-ml, Apache 2.0 license)
# The matching itself runs in its own environment (caml_naics_matching/, see its
# README) and writes data/caml_top5_naics.csv: CaML's ranked list for each input
# description, grouped by NAICS code, with the 5 best NAICS codes. Rank 1 is CaML's match.
CAML_TOP_K = 5

caml_top5 = pd.read_csv(SI_DIR.parent / "data" / "caml_top5_naics.csv")
caml_top5 = caml_top5.sort_values(["activity_text", "rank"])
caml_matches = (
    caml_top5.groupby("activity_text", sort=False)
    .agg(
        naics_code=("naics_code", "first"),
        naics_desc=("naics_desc", "first"),
        cosine_score=("cosine_score", "first"),
        top_codes=("naics_code", lambda codes: "; ".join(str(c) for c in codes)),
    )
    .rename(columns={"top_codes": f"top {CAML_TOP_K} NAICS codes"})
    .rename_axis("description")
    .reset_index()
)

# Same NAICS codes as in SI2 'CAML to NAICS codes'?
caml_si2 = pd.read_excel(conv_table_filename, sheet_name="CAML to NAICS codes")
naics_in_si2 = caml_matches["description"].map(
    caml_si2.dropna(subset=["description"]).set_index("description")["naics_code"]
)
in_si2 = naics_in_si2.notna()
print(
    f"CaML: {(caml_matches['naics_code'] == naics_in_si2)[in_si2].sum()} of "
    f"{in_si2.sum()} NAICS codes as in SI2 ({(~in_si2).sum()} descriptions not in SI2)"
)

# %%% NAICS codes to EXIOBASE products
# One EXIOBASE hybrid product per NAICS code, from data/naics_to_exio3h.csv. That table
# lists, per NAICS code, the hybrid products the NAICS-EXIOBASE concordance links to
# ('EXIO3 candidates') and the one chosen by hand ('EXIO3 code', with the reason in
# 'rule'). New NAICS codes are added as drafts with scripts/draft_naics_exio_table.py.
naics_exio_file = SI_DIR.parent / "data" / "naics_to_exio3h.csv"
naics_exio = (
    pd.read_csv(naics_exio_file, dtype={"naics_code": str}).set_index("naics_code")
    if naics_exio_file.exists()
    else pd.DataFrame()
)

top_k_codes = caml_matches[f"top {CAML_TOP_K} NAICS codes"].str.split("; ")
missing = {c for codes in top_k_codes for c in codes} - set(naics_exio.index)
if missing:
    raise ValueError(
        f"{len(missing)} NAICS codes are not in data/naics_to_exio3h.csv: "
        "run scripts/draft_naics_exio_table.py and check the new rows"
    )
caml_matches["EXIO3 code"] = (
    caml_matches["naics_code"].astype(str).map(naics_exio["EXIO3 code"])
)

# The CAML LCA uses SI2 'caml_mapping', whose codes come from column E of
# 'CAML to NAICS codes': check that it holds the same products
si2_codes = caml_matches["description"].map(
    res_conv_caml.set_index("description")["EXIO3 code"]
)
outdated = caml_matches["EXIO3 code"].fillna(0) != si2_codes.fillna(0)
if outdated.any():
    print(
        f"{outdated.sum()} inputs have another product in SI2 'caml_mapping': paste the "
        "'EXIO3 code' column of results/caml_naics_matches.csv into column E of "
        "'CAML to NAICS codes'"
    )

# %%% Human in the loop, simulated (CaML top 5)
# A reviewer who knows the manual mapping chooses from the EXIOBASE products the
# concordance links to CaML's top-5 NAICS codes. The reviewer takes the manual product
# if it is among them, excludes the input if the manual mapping excludes it, and keeps
# CaML's top 1 otherwise. This is an upper bound for a real reviewer.
manual_codes = caml_matches["description"].map(
    res_conv.set_index("description")["EXIO3 code"]
)
candidates = [
    {p for code in codes for p in str(naics_exio.at[code, "EXIO3 candidates"]).split("; ")}
    for codes in top_k_codes
]


def reviewer_choice(description, manual, found):
    if pd.isnull(manual) or manual in (0, "0", "NA()", "#NA()"):
        return "excludes input"
    if description == GRID_ELECTRICITY:  # manual mapping: grid mix of C_POW* products
        hit = any(p.startswith("C_POW") and p not in ("C_POWT", "C_POWD") for p in found)
    else:
        hit = manual in found
    return "takes manual product" if hit else "keeps CaML top 1"


caml_matches["EXIO3 code, manual mapping"] = manual_codes
caml_matches[f"EXIO3 candidates in top {CAML_TOP_K}"] = [
    "; ".join(sorted(c)) for c in candidates
]
caml_matches["reviewer"] = [
    reviewer_choice(d, m, c)
    for d, m, c in zip(caml_matches["description"], manual_codes, candidates)
]
caml_matches.to_csv(RESULTS_DIR / "caml_naics_matches.csv", index=False)

compared = caml_matches["reviewer"] != "excludes input"
automated_ok = caml_matches["EXIO3 code"] == manual_codes
print(
    f"Automated (top 1): {(automated_ok & compared).sum()} of {compared.sum()} inputs "
    "in the same EXIOBASE product as the manual mapping\n"
    f"Reviewer (top {CAML_TOP_K}): {caml_matches['reviewer'].value_counts().to_dict()}"
)

# Mapping for the CAML HITL LCA: the manual mapping (including its exclusions) where
# the reviewer uses it, the CAML mapping otherwise
reviewed = set(
    caml_matches.loc[caml_matches["reviewer"] != "keeps CaML top 1", "description"]
)
res_conv_caml_hitl = pd.concat(
    [
        res_conv[res_conv["description"].isin(reviewed)],
        res_conv_caml[~res_conv_caml["description"].isin(reviewed)],
    ],
    ignore_index=True,
)
CAML_HITL_GRID_MIX = GRID_ELECTRICITY in reviewed


# %% Load databases for resource conversion and CAML resource conversion
resconv_db_name = "resource conversion"
resconv_db = bw.Database(resconv_db_name)

resconv_caml_db_name = "resource conversion CAML"
resconv_caml_db = bw.Database(resconv_caml_db_name)

resconv_caml_hitl_db_name = "resource conversion CAML HITL"
resconv_caml_hitl_db = bw.Database(resconv_caml_hitl_db_name)

# %%% For each activity in the resource conversion database, link to the converted
# EXIOBASE activities for both  the manual and the CAML conversion
for db, conv in zip(
    [resconv_db, resconv_caml_db, resconv_caml_hitl_db],
    [res_conv, res_conv_caml, res_conv_caml_hitl],
):
    for act in db:
        name = act["name"]
        location = act["location"]

        conv_row = conv[conv["description"] == name].copy().iloc[0]

        EXIO_code = conv_row["EXIO3 code"]

        if (
            pd.isnull(EXIO_code)
            or EXIO_code == "NA()"
            or EXIO_code == "#NA()"
            or EXIO_code == 0
        ):
            continue

        # Grid electricity (manual mapping only, also in the CAML HITL database if the
        # reviewer takes the manual mapping): link to the country's 2011 grid mix of
        # EXIOBASE electricity products instead of a single category
        uses_grid_mix = db.name == resconv_db_name or (
            db.name == resconv_caml_hitl_db_name and CAML_HITL_GRID_MIX
        )
        if uses_grid_mix and name == GRID_ELECTRICITY:
            regions = regions_for(location)
            if location not in grid_shares.index or len(regions) != 1:
                raise ValueError(
                    f"No grid mix for location {location}: add it to "
                    f"{grid_mix_filename.name} and OWID_TO_DPP_LOCATION"
                )
            for product, share in grid_shares.loc[location].items():
                if share == 0:
                    continue
                act.new_exchange(
                    input=("EXIO3H", f"{prod_act_map[product]} - {regions[0]}"),
                    amount=conv_row["conversion factor"] * share,  # TJ per kWh
                    type="technosphere",
                    name=prod_name_map[product],
                    location=regions[0],
                    unit="TJ",
                    **{"uncertainty type": 0},
                ).save()
            continue

        EXIO_unit = conv_row["EXIO3 unit"]
        EXIO_key = ("EXIO3H", prod_act_map[EXIO_code])

        exchanges = pd.Series()
        exchanges["input"] = EXIO_key
        exchanges["type"] = "technosphere"
        exchanges["name"] = prod_name_map[EXIO_code]

        def get_country_disagg(location):
            if location not in country_conv.columns:
                return [location]

            return country_conv.index[country_conv.loc[:, location] != 0].to_list()

        exchanges["location"] = get_country_disagg(location)

        def get_distribution_factor(row, location):
            conversion_factor = row["conversion factor"]
            if len(location) == 1:
                return [conversion_factor]

            this_code_pps = exio3h_pp_by_prod.xs(row["EXIO3 code"], level=1)
            relevant_pps = this_code_pps[location]
            relevant_pps_sum = relevant_pps.sum()
            distribution_factor = conversion_factor * (relevant_pps / relevant_pps_sum)

            return distribution_factor.to_list()

        exchanges["amount"] = get_distribution_factor(conv_row, exchanges["location"])

        exchanges["uncertainty type"] = 0

        exchanges_df = (
            exchanges.to_frame()
            .T.explode(["location", "amount"])
            .reset_index(drop=True)
        )

        def add_loc_to_key(row):
            key = row["input"]
            location = row["location"]
            return (key[0], key[1] + " - " + location)

        exchanges_df["input"] = exchanges_df.apply(add_loc_to_key, axis=1)

        exchanges = list(exchanges_df.T.to_dict().values())
        exchanges = [{k: v for k, v in x.items() if v == v} for x in exchanges]

        # add exchanges to activity in conversion database
        for ex in exchanges:
            act.new_exchange(**ex).save()

log_time("resource conversion linked to EXIO3H")

# %% Set up copy of PV LCI linked to CAML mapping
pvlci = bw.Database("PV LCI")

pv_lci_caml = pvlci.copy("PV LCI CAML")
pv_lci_caml_hitl = pvlci.copy("PV LCI CAML HITL")

# relink from "resource conversion" to "resource conversion CAML" (and CAML HITL)
for pv_copy, conv_db in [
    (pv_lci_caml, resconv_caml_db),
    (pv_lci_caml_hitl, resconv_caml_hitl_db),
]:
    for act in pv_copy:
        for exc in act.exchanges():
            if exc.input.key[0] == "resource conversion":
                exc.input = conv_db.get(exc.input.key[1])
                exc.save()

# %% Set up primary LCA (full LCA, EXIO3H background)
pvlci = bw.Database("PV LCI")
exio3h = bw.Database("EXIO3H")

pv_panel = pvlci.search("photovoltaic panel, single-Si")[0]
functional_unit_full = {pv_panel: 1.0}

method_ef31 = ("EF v3.1", "climate change", "global warming potential (GWP100)")


# %% Set up BoM LCA with EXIO3H background
pv_panel_bom_no_location = pv_panel.copy()
pv_panel_bom_no_location["code"] = "photovoltaic panel BoM - no location info"
pv_panel_bom_no_location["name"] = "photovoltaic panel BoM - no location info"
pv_panel_bom_no_location.save()

# delete technosphere and biosphere exchanges
[
    exc.delete()
    for exc in pv_panel_bom_no_location.exchanges()
    if exc["type"] in ["technosphere", "biosphere"]
]

pv_panel_bom_with_location = pv_panel_bom_no_location.copy()
pv_panel_bom_with_location["code"] = "photovoltaic panel BoM - with location info"
pv_panel_bom_with_location["name"] = "photovoltaic panel BoM - with location info"
pv_panel_bom_with_location.save()


# add technosphere exchanges per BoM line
def add_exchange_from_bom_row_no_location(row):
    input_code = f"{prod_act_map[row['EXIO3 code']]} - CN"
    amount = row["mass per m2 panel"]

    pv_panel_bom_no_location.new_exchange(
        input=exio3h.get(input_code), amount=amount, type="technosphere"
    ).save()


def add_exchange_from_bom_row_with_location(row):
    product = row["EXIO3 code"]
    regions = regions_for(row["location"])  # e.g. RER -> European EXIO3H regions
    if len(regions) == 1:
        shares = pd.Series(1.0, index=regions)
    else:  # split by production of this product, as for the full inventory
        output = exio3h_pp_by_prod.xs(product, level=1).groupby(level=0).sum()[regions]
        shares = output / output.sum()
    for region, share in shares.items():
        pv_panel_bom_with_location.new_exchange(
            input=exio3h.get(f"{prod_act_map[product]} - {region}"),
            amount=row["mass per m2 panel"] * share,
            type="technosphere",
        ).save()


bom_info.apply(add_exchange_from_bom_row_no_location, axis=1)
bom_info.apply(add_exchange_from_bom_row_with_location, axis=1)


# %% set up BoM LCA
functional_unit_bom = {pv_panel_bom_no_location: 1.0}
functional_unit_bom_location = {pv_panel_bom_with_location: 1.0}

# %% Set up single-process LCA
pv_panel_single = pv_panel.copy()
pv_panel_single["code"] = "single LCI photovoltaic panel - CN"
pv_panel_single["name"] = "single LCI photovoltaic panel - CN"
pv_panel_single.save()
# %%
# get PV cell input and change to EXIO category
pv_cell_exchange = [ex for ex in pv_panel_single.exchanges()][1]
pv_cell_exchange.input = exio3h.get("A_ELMA - CN")
pv_cell_exchange["name"] = "single LCI photovoltaic panel"

# get conversion factor from conversions file
conv_factor = res_conv[
    res_conv["description"] == "photovoltaic cell, single-Si, at plant"
]["conversion factor"].iloc[0]

# update relevant fields for new exchange
pv_cell_exchange["amount"] = pv_cell_exchange["amount"] * conv_factor
pv_cell_exchange["unit"] = "tonnes"

# uncertainty information
pv_cell_exchange["uncertainty type"] = 2  # lognormal, as this is no longer a component

amount = pv_cell_exchange["amount"]
sd95 = 1.243456651  # copied from source file
pv_cell_exchange["loc"] = np.log(amount)
pv_cell_exchange["scale"] = np.log(sd95 ** (1 / 1.96))

pv_cell_exchange.save()

# set up LCA
functional_unit_single = {pv_panel_single: 1.0}


# %% set up CAML LCA
pv_panel_caml = pv_lci_caml.search("photovoltaic panel single-Si")[0]
functional_unit_caml = {pv_panel_caml: 1.0}

pv_panel_caml_hitl = pv_lci_caml_hitl.search("photovoltaic panel single-Si")[0]
functional_unit_caml_hitl = {pv_panel_caml_hitl: 1.0}

# %% Set up LCA with IPCC2013
method_IPCC = ("IPCC 2013", "climate change", "global warming potential (GWP100)")

# %% Get LCA results
# One LCA object for all product systems: the EXIO3H matrices are loaded and the
# technosphere matrix is factorised once, then re-solved for each functional unit.
log_time("product systems set up")

functional_units = {
    "full LCA": functional_unit_full,
    "BoM LCA": functional_unit_bom,
    "BoM LCA (with location)": functional_unit_bom_location,
    "single LCA": functional_unit_single,
    "CAML LCA": functional_unit_caml,
    "CAML LCA (reviewer, top 5)": functional_unit_caml_hitl,
}
all_demands = {k: v for fu in functional_units.values() for k, v in fu.items()}

lca = bw.LCA(all_demands, method_ef31)
lca.load_lci_data()
lca.build_demand_array()
log_time("matrices loaded")

# EXIO3H is an input-output table, so its technosphere matrix is nearly dense. Sparse
# solvers (scipy/pypardiso) are very slow on it, so it is factorised as a dense matrix
# (LU decomposition, ~0.5 GB of memory) once. bw2calc uses `lca.solver` for every
# subsequent (re)calculation.
_lu = scipy.linalg.lu_factor(
    lca.technosphere_matrix.toarray(), overwrite_a=True, check_finite=False
)
lca.solver = lambda demand: scipy.linalg.lu_solve(_lu, demand, check_finite=False)
log_time("technosphere factorised")

lca.lci_calculation()
lca.lcia()

scores = {}
for name, fu in functional_units.items():
    lca.redo_lcia(fu)  # reuses the factorisation
    scores[name] = lca.score
    print(f"Score for {name} generated.")

# %% Foreground only (R3) (no background database included)
lca.redo_lcia(functional_unit_full)
lca.fix_dictionaries()
foreground_cols = {
    key: j for key, j in lca.activity_dict.items() if key[0] == pv_db_name
}
direct = {
    key[1]: lca.characterized_inventory[:, j].sum()
    for key, j in foreground_cols.items()
}
scores["foreground only"] = sum(direct.values())
print("Score for foreground only generated.")

# IPCC 2013: same inventory, only the characterisation factors change
lca.switch_method(method_IPCC)
lca.redo_lcia(functional_unit_full)
scores["IPCC LCA"] = lca.score
print("Score for IPCC LCA generated.")
log_time("EXIO3H scores done")

pd.Series(scores).to_csv(RESULTS_DIR / "scores.csv")

# %% Set up ecoinvent LCA
# This assumes the "dpp_lca_ecoinvent" project is set up with ecoinvent310-cutoff
ei_project_name = "dpp_lca_ecoinvent"
bw.projects.set_current(ei_project_name)

ei_pv_name = "PV LCI ecoinvent"
ei_pv_db = bw.Database(ei_pv_name)

ecoinvent_name = "ecoinvent-3.10-cutoff"
ei = bw.Database(ecoinvent_name)

# %%% Load ecoinvent conversion
eco_conv = pd.read_excel(conv_table_filename, sheet_name="ecoinvent_map")

# %% Generate activities
ei_pv_activities = {}

for dppnr, dpp in enumerate(dpps.copy().values()):
    dpp = dpp.copy()[dpp["value"] != 0]

    # Split DPP into product, component, resources, direct emissions
    product_row = dpp.query("type == 'product'").copy()
    components = dpp.query("type == 'component'").copy()
    resources = dpp.query("type == 'resource'").copy()
    emissions = dpp.query("type == 'direct emission'").copy()

    # Create activity for DPP with product information
    product = product_row.iloc[0]
    key = (ei_pv_name, f"{product['description']} - {product['location']}")
    name = product["description"]
    unit = product["unit"]
    location = product["location"]

    # Add an activity for this DPP
    ei_pv_activities[key] = {
        "name": name,
        "unit": unit,
        "reference product": name,
        "location": location,
        "type": "process",
    }

    # Generate exchanges
    exchanges_df = pd.DataFrame()  # empty dataframe

    # generate exchange keys
    def row_to_key(row):
        name = f"{row['description']} - {row['location']}"

        if row["type"] in ["product", "component"]:
            return (ei_pv_name, name)

        if row["type"] == "resource":
            uuid_idx = (eco_conv["description"] == row["description"]) & (
                eco_conv["location"] == row["location"]
            )
            key_str = eco_conv.loc[uuid_idx, "ecoinvent UUID"].iloc[0]
            uuid = key_str.split(", ")[1][1:-2]
            return (ecoinvent_name, uuid)

        uuid_idx = (bs_conv["description"] == row["description"]) & (
            bs_conv["compartment"] == row["location"]
        )

        uuid = bs_conv.loc[uuid_idx, "biosphere3 UUID"].iloc[0]
        return ("biosphere3", uuid)

    exchanges_df["input"] = dpp.apply(row_to_key, axis=1)

    # set name, amount, unit
    exchanges_df["name"] = dpp["description"]
    exchanges_df["location"] = dpp["location"]
    exchanges_df["amount"] = dpp["value"]
    exchanges_df["unit"] = dpp["unit"]

    # set type
    def row_to_type(row):
        if row["type"] == "product":
            return "production"

        if row["type"] == "direct emission":
            return "biosphere"

        return "technosphere"

    exchanges_df["type"] = dpp.apply(row_to_type, axis=1)

    # set uncertainty
    is_product_or_component = dpp["type"].isin(["product", "component"])

    exchanges_df["uncertainty type"] = 2

    # products and components get no uncertainty
    exchanges_df.loc[is_product_or_component, "uncertainty type"] = 0

    # negative amounts get no uncertainty (as this breaks the MC analysis)
    exchanges_df.loc[exchanges_df["amount"] < 0, "uncertainty type"] = 0
    exchanges_df.loc[~is_product_or_component, "loc"] = np.log(dpp["value"])
    exchanges_df.loc[~is_product_or_component, "scale"] = np.log(dpp["SD95"]) / 1.96

    exchanges = list(exchanges_df.T.to_dict().values())
    exchanges = [{k: v for k, v in x.items() if v == v} for x in exchanges]

    ei_pv_activities[key]["exchanges"] = exchanges

ei_pv_db.write(ei_pv_activities)

# %% Set up ecoinvent LCA
fu_ecoinvent = ei_pv_db.search("photovoltaic panel, single-Si CN")[0]
method_ecoinvent = ("EF v3.1", "climate change", "global warming potential (GWP100)")
lca_ei = bw.LCA({fu_ecoinvent: 1.0}, method_ecoinvent)
lca_ei.lci()
lca_ei.lcia()

scores["ecoinvent LCA"] = lca_ei.score
log_time("ecoinvent score done")

# %% Export results to Excel file
results = pd.DataFrame(scores, index=["score (kg CO2-eq GWP100)"]).T
results.to_csv(RESULTS_DIR / "results.csv")
# results.to_excel("SI3 - LCA Results.xlsx", sheet_name="LCA Scores")

# %% Monte Carlo analysis was separately performed in Activity Browser using these
# databases. Random seed 2113, randomisation for technosphere and biosphere, not for
# CFs and  parameters.
