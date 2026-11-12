# %% This code is adapted from https://github.com/amazon-science/carbon-assessment-with-ml/blob/main/caml/generate_ranked_preds.ipynb

# %%
# Use a GPU instance if possible, the code can take a few minutes to run otherwise.
from tqdm import tqdm
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer, util

from caml.eio import naics

# folder for files
REPO = Path(__file__).resolve().parents[1]

# %% Read descriptions from SI file
SI2_FILE_LOCATION = REPO / "si" / "SI2 - conversions used.xlsx"

resources = pd.read_excel(SI2_FILE_LOCATION, sheet_name="resources")
descriptions = resources["description"].to_list()

to_remove = [
    "photovoltaic cell, single-Si, at plant",  # CAML analysis only uses "full" case
    "photovoltaic cell factory",  # capital goods are excluded
    "photovoltaic panel factory",  # capital goods are excluded
    "wafer factory",  # capital goods are excluded
]
for descr in to_remove:
    descriptions.remove(descr)

# %% This cell fixes an HTTP error as the CAML default looks up the NAICS data online,
# which is blocked by the census server.
from pathlib import Path

naics.naics_file = REPO / "data" / "external" / "2017_NAICS_Index_File.xlsx"

# %% set up the NAICS list (copied from CAML file)
naics_df = naics.get_naics_data()
naics_list = naics_df.naics_desc.values
print(len(naics_list))
naics_df.head()

# %% set up the model
model = SentenceTransformer("all-mpnet-base-v2")
activity_embedding = model.encode(descriptions)
naics_embedding = model.encode(naics_list)
cosine_scores = util.cos_sim(activity_embedding, naics_embedding)
sorted_cs, indices = cosine_scores.sort(dim=1, descending=True)

# %% Ranked list per description, as in CaML's notebook, grouped by NAICS code and saved
ranked_lists = []
for activity_ix in tqdm(range(len(descriptions))):
    activity_text = descriptions[activity_ix]
    sorted_activity_cs = sorted_cs[activity_ix].cpu().numpy()
    naics_ix = indices[activity_ix].cpu().numpy()

    similarity_scores = pd.DataFrame(index=np.arange(20))
    for i in range(20):
        similarity_scores.loc[i, "cosine_score"] = float(
            "{:.8f}".format(sorted_activity_cs[i])
        )
        similarity_scores.loc[i, "naics_code"] = naics_df.loc[
            naics_ix[i], "naics_code"
        ]  # added
        similarity_scores.loc[i, "bea_code"] = naics_df.loc[naics_ix[i], "bea_code"]
        similarity_scores.loc[i, "naics_desc"] = naics_df.loc[naics_ix[i], "naics_desc"]
        similarity_scores.loc[i, "naics_title"] = naics_df.loc[
            naics_ix[i], "naics_title"
        ]

    similarity_scores["activity_text"] = activity_text
    aggregated_scores = similarity_scores.groupby(
        "naics_code"
    ).first()  # was "bea_code"
    aggregated_scores["votes"] = similarity_scores.groupby(
        "naics_code"
    ).size()  # was "bea_code"
    aggregated_scores = (
        aggregated_scores.sort_values(["cosine_score", "votes"], ascending=False)
        .reset_index()
        .head()
    )
    aggregated_scores["rank"] = np.arange(1, len(aggregated_scores) + 1)
    ranked_lists.append(aggregated_scores)

# %% Save: one row per description and rank
top5 = pd.concat(ranked_lists, ignore_index=True)
top5["naics_code"] = top5["naics_code"].astype(int)  # .loc stored it as a float
columns = [
    "activity_text",
    "rank",
    "naics_code",
    "naics_desc",
    "naics_title",
    "bea_code",
    "cosine_score",
    "votes",
]
top5[columns].to_csv(REPO / "data" / "caml_top5_naics.csv", index=False)
