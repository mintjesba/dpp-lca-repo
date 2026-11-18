"""EXIOBASE products that the NAICS-EXIOBASE concordance links to each NAICS code that
CaML proposes (data/caml_top5_naics.csv).

Inputs
  data/caml_top5_naics.csv                 CaML's top-5 NAICS codes per input description
  data/external/naics2017_exiobase3p.csv   NAICS 2017 -> EXIOBASE 3 products (p01.a, ...)
  si/SI2 - conversions used.xlsx           sheet EXIO3_classifications: hybrid products

The concordance uses the product codes of monetary EXIOBASE (p01.a, ...), SI4 uses those
of EXIOBASE hybrid (C_PARI, ...). They are translated by product name (identical after
lowercasing and ignoring punctuation). EXIOBASE hybrid merges a few groups of products
that have no product of their own name there; those are assigned with the rules in
AGGREGATED below.

Output: results/naics_exio_candidates.csv, one row per NAICS code and linked product.
The concordance gives every link weight 1, so a NAICS code with several rows has
several possible products. The file is regenerated on every run: record choices
elsewhere.

Run in the dpp-lca environment, from the repository root:
    python scripts/naics_exio_candidates.py
"""

import re
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
TOP5 = REPO / "data" / "caml_top5_naics.csv"
CONCORDANCE = REPO / "data" / "external" / "naics2017_exiobase3p.csv"
SI2 = REPO / "si" / "SI2 - conversions used.xlsx"
OUTPUT = REPO / "results" / "naics_exio_candidates.csv"

# Monetary products without a hybrid product of the same name: the hybrid product that
# includes them (concordance code pattern -> hybrid code)
AGGREGATED = {
    r"^p10\.": ("C_CLPT", "coal types and peat -> Coal, lignite and peat"),
    r"^p11\.b": ("C_GASS", "natural gas and NGL -> Natural gas"),
    r"^p23\.1\.": ("C_COPR", "coke oven coke, gas coke, coal tar -> Coke oven products"),
    r"^p23\.20\.": ("C_REFP", "refinery products -> Refined Petroleum"),
    r"^p24\.[d-i]$": (
        "C_CHBI",
        "chemicals nec, charcoal, additives, biofuels -> Chemicals nec; additives and biofuels",
    ),
    r"^p40\.2\.": ("C_BGAS", "derived gases -> Biogas and other gases nec"),
}


def normalise(name):
    return re.sub(r"\W+", " ", str(name).lower()).strip()


def main():
    top5 = pd.read_csv(TOP5, dtype={"naics_code": str})
    conc = pd.read_csv(CONCORDANCE, dtype={"source_code": str})
    hybrid = pd.read_excel(SI2, sheet_name="EXIO3_classifications").drop_duplicates(
        "EXIO3 code"
    )

    # 1. Translate concordance products (p-codes) to hybrid products
    by_name = dict(zip(hybrid["EXIO3 description"].map(normalise), hybrid["EXIO3 code"]))
    conc["EXIO3 code"] = conc["target_name"].map(lambda n: by_name.get(normalise(n)))
    conc["translation"] = conc["EXIO3 code"].notna().map({True: "same name", False: None})
    for pattern, (code, rule) in AGGREGATED.items():
        rows = conc["EXIO3 code"].isna() & conc["target_code"].str.match(pattern)
        conc.loc[rows, "EXIO3 code"] = code
        conc.loc[rows, "translation"] = f"aggregated: {rule}"
    # A product name spelled differently in some rows: use its code from the other rows
    known = (
        conc.dropna(subset=["EXIO3 code"])
        .drop_duplicates("target_code")
        .set_index("target_code")[["EXIO3 code", "translation"]]
    )
    missing = conc["EXIO3 code"].isna() & conc["target_code"].isin(known.index)
    conc.loc[missing, ["EXIO3 code", "translation"]] = known.loc[
        conc.loc[missing, "target_code"]
    ].to_numpy()
    not_translated = conc.loc[conc["EXIO3 code"].isna(), "target_name"].unique()
    if len(not_translated):
        print("Concordance products without a hybrid product:", list(not_translated))

    # 2. The NAICS codes CaML proposes
    naics = (
        top5.groupby("naics_code")
        .agg(
            naics_title=("naics_title", "first"),
            rank_1_for=(
                "activity_text",
                lambda d: "; ".join(d[top5.loc[d.index, "rank"] == 1]),
            ),
            in_top5_of=("activity_text", "nunique"),
        )
        .reset_index()
    )

    # 3. Their links in the concordance
    links = conc.rename(
        columns={
            "source_code": "naics_code",
            "target_code": "exio3 product code",
            "target_name": "exio3 product name",
        }
    )[["naics_code", "exio3 product code", "exio3 product name", "EXIO3 code", "translation"]]
    candidates = naics.merge(links, on="naics_code", how="left")
    candidates = candidates.merge(
        hybrid[["EXIO3 code", "EXIO3 description", "EXIO3 unit"]], on="EXIO3 code", how="left"
    )
    candidates["n hybrid products for this NAICS code"] = candidates.groupby("naics_code")[
        "EXIO3 code"
    ].transform("nunique")
    candidates = candidates.rename(
        columns={
            "rank_1_for": "CaML rank 1 for",
            "in_top5_of": "in top 5 of n descriptions",
        }
    )

    OUTPUT.parent.mkdir(exist_ok=True)
    candidates.to_csv(OUTPUT, index=False)

    per_code = candidates.drop_duplicates("naics_code")
    n = per_code["n hybrid products for this NAICS code"]
    rank_1 = per_code["CaML rank 1 for"] != ""
    print(f"{len(per_code)} NAICS codes ({rank_1.sum()} are CaML's rank 1 for a description)")
    print("hybrid products per NAICS code:", n.value_counts().sort_index().to_dict())
    print("of the rank-1 codes:", n[rank_1].value_counts().sort_index().to_dict())
    print("not in the concordance:", per_code.loc[n == 0, "naics_code"].tolist())
    print(f"written to {OUTPUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
