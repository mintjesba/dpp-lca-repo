"""Draft rows of data/naics_to_exio3h.csv for NAICS codes that are not in it yet.

The table gives one EXIOBASE hybrid product per NAICS code, for the CAML scenario in SI4.
For every NAICS code in CaML's top-5 lists (data/caml_top5_naics.csv) it lists the
hybrid products that the NAICS 2017 - EXIOBASE 3 concordance links to ('EXIO3
candidates'). The concordance uses EXIOBASE product codes (p01.a, ...); they are
translated to hybrid codes (C_PARI, ...) with the principal production table of
EXIOBASE 3 hybrid, which holds both. Products without a hybrid code are dropped.

Draft rule:
- one candidate: taken as 'EXIO3 code', checked = auto
- several: 'EXIO3 code' left empty, checked = no -> choose one by hand, write the
  reason in 'rule' and set checked = yes. Decide per NAICS code, without looking at
  which input description matched it.
Existing rows are never changed.

Run after caml_naics_matching/caml_top5_naics.py has written data/caml_top5_naics.csv:
    python scripts/draft_naics_exio_table.py
"""

from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
CONCORDANCE = REPO / "data" / "external" / "naics2017_exiobase3p.csv"
TOP5 = REPO / "data" / "caml_top5_naics.csv"
TABLE = REPO / "data" / "naics_to_exio3h.csv"
PP_URL = (
    "https://zenodo.org/records/10148587/files/"
    "MR_HIOT_2011_v3_3_18_principal_production.csv"
)
COLUMNS = [
    "naics_code",
    "naics_title",
    "EXIO3 candidates",
    "EXIO3 candidate names",
    "EXIO3 code",
    "rule",
    "checked",
]


def p_to_hybrid_codes(pp_index, concordance_codes):
    """{p01.a: C_PARI, ...}: the index levels holding the two code systems."""
    levels = [pp_index.get_level_values(i).astype(str) for i in range(pp_index.nlevels)]
    hybrid = max(levels, key=lambda v: v.str.startswith("C_").mean())
    p_codes = max(levels, key=lambda v: v.isin(concordance_codes).mean())
    if not p_codes.isin(concordance_codes).any():
        raise ValueError("No EXIOBASE product codes (p01.a, ...) in the principal production")
    return dict(zip(p_codes, hybrid))


def main():
    conc = pd.read_csv(CONCORDANCE, dtype={"source_code": str})
    pp_index = pd.read_csv(PP_URL, header=[0, 1, 2, 3, 4, 5, 6, 7]).T.index
    conc["hybrid_code"] = conc["target_code"].map(
        p_to_hybrid_codes(pp_index, set(conc["target_code"]))
    )
    conc = conc.dropna(subset=["hybrid_code"]).drop_duplicates(
        ["source_code", "hybrid_code"]
    )
    # Census titles end in 'T' where the NAICS manual has a footnote
    conc["source_name"] = conc["source_name"].str.replace(r"(?<=[a-z)])T$", "", regex=True)

    top5 = pd.read_csv(TOP5, dtype={"naics_code": str})
    needed = set(top5["naics_code"])

    table = (
        pd.read_csv(TABLE, dtype={"naics_code": str})
        if TABLE.exists()
        else pd.DataFrame(columns=COLUMNS)
    )
    drafts = []
    for code in sorted(needed - set(table["naics_code"])):
        linked = conc[conc["source_code"] == code]
        row = {
            "naics_code": code,
            "naics_title": linked["source_name"].iloc[0] if len(linked) else "",
            "EXIO3 candidates": "; ".join(linked["hybrid_code"]),
            "EXIO3 candidate names": "; ".join(linked["target_name"]),
        }
        if len(linked) == 1:
            row.update(
                {"EXIO3 code": linked["hybrid_code"].iloc[0], "rule": "only candidate"}
            )
            row["checked"] = "auto"
        else:
            row["rule"] = "no candidate" if linked.empty else "to choose"
            row["checked"] = "no"
        drafts.append(row)

    table = pd.concat([table, pd.DataFrame(drafts, columns=COLUMNS)], ignore_index=True)
    table.sort_values("naics_code").to_csv(TABLE, index=False)

    top_1 = set(top5.loc[top5["rank"] == 1, "naics_code"])
    to_check = table[(table["checked"] == "no") & table["naics_code"].isin(top_1)]
    print(f"{len(drafts)} NAICS codes added to {TABLE.name}")
    print(f"{len(to_check)} codes matched by CaML (top 1) still to choose:")
    print(to_check[["naics_code", "naics_title", "EXIO3 candidates"]].to_string(index=False))


if __name__ == "__main__":
    main()
