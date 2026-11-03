# Requirements to leverage digital product passports for automated environmental impact assessments — code and data

<!-- TODO: add badges once available, e.g. Zenodo DOI and licence -->

This repository contains the data, code and results for:

> Mintjes, B. A., Li, C., Hischier, R., Bouman, E. A., Bootoo, G., Muller, S., Cunha, S., Moran, D. D., Merciai, S., Tukker, A., & Mogollón, J. M. (TODO: year). *Requirements to leverage digital product passports for automated environmental impact assessments.* TODO: journal. TODO: DOI.

It implements a proof of concept in which life cycle inventory (LCI) data stored in Digital Product Passport (DPP) entries is linked to a background table (EXIOBASE 3 hybrid) to automatically calculate the cradle-to-gate climate change impact of a single-crystalline silicon PV panel. TODO: one or two more sentences.

## Repository structure

```
.
├── README.md              this file
├── environment.yml        conda environment
├── CITATION.cff           citation metadata (used by GitHub and Zenodo)
├── si/                    supplementary information as submitted with the article
│   ├── SI1 - DPP LCI information.xlsx            simulated DPP entries (from IEA PVPS T12)
│   ├── SI2 - conversions used.xlsx               mappings to EXIOBASE 3 hybrid / ecoinvent / biosphere3
│   ├── SI3 - LCA Results.xlsx                    deterministic and Monte Carlo results
│   └── SI4 - Python code for setup and calculations.py
├── data/external/         external data that cannot be redistributed (not tracked by git)
└── results/               output from re-running the code (not tracked by git)
```

| Article element | Produced by | Output |
|---|---|---|
| Baseline, R1 (BoM), R2 (single process), R4 (CAML), R5 (IPCC 2013) | `si/SI4 …py` | `SI3`, sheet `LCA Scores` |
| R3 (ecoinvent background) | `si/SI4 …py`, ecoinvent section | `SI3`, sheet `LCA Scores` |
| Monte Carlo (Figure 5) | TODO: script or Activity Browser (see below) | `SI3`, sheet `MC results` |
| CAML matching (R4) | TODO | `SI2`, sheets `CAML to NAICS codes`, `caml_mapping` |
| Figures 4 and 5 | TODO | TODO |

## Requirements

### Software

Install the environment with [conda](https://docs.conda.io) or [mamba](https://mamba.readthedocs.io):

```bash
conda env create -f environment.yml
conda activate dpp-lca
```

This installs Python 3.11 with the legacy Brightway 2 stack (brightway2 2.4.6: bw2data 3.6.6, bw2calc 1.8.2, bw2io 0.8.12) and Activity Browser 2.11.2. The code uses the Brightway 2 API, so it does not run with Brightway 2.5.

<!-- TODO: after a full re-run, export the exact environment and commit it:
     conda env export --no-builds > environment.lock.yml -->

### External data

These datasets are not included in this repository:

| Data | Version | Source | Licence |
|---|---|---|---|
| EXIOBASE 3 hybrid | v3.3.18 (2011) | [doi:10.5281/zenodo.10148587](https://doi.org/10.5281/zenodo.10148587) | CC BY 4.0 |
| ecoinvent | 3.10, cut-off | [ecoinvent.org](https://ecoinvent.org) (licence required) | proprietary |
| LCIA methods (EF v3.1, EF v3.1 EN15804, IPCC 2013) | TODO | TODO: e.g. ecoinvent 3.10 LCIA implementation via bw2io | TODO |
| IEA PVPS Task 12 LCI data (source of SI1) | Frischknecht et al. (2020) | [doi:10.2172/1561526](https://doi.org/10.2172/1561526) | TODO |

The code also downloads `MR_HIOT_2011_v3_3_18_principal_production.csv` from the EXIOBASE Zenodo record at run time.

## Reproducing the results

### 1. Set up the Brightway projects

1. **EXIOBASE 3 hybrid project (`exiobase_in_bw`).** Import EXIOBASE 3 hybrid into Brightway with [exio3_in_brightway2](https://github.com/mintjesba/exio3_in_brightway2) (TODO: commit hash or release). TODO: describe the steps and which biosphere and LCIA methods are installed.
2. **ecoinvent project (`dpp_lca_ecoinvent`).** TODO: describe the import of ecoinvent 3.10 cut-off and the LCIA methods.

### 2. Run the calculations

```bash
conda activate dpp-lca
python "si/SI4 - Python code for setup and calculations.py"
```

The script can also be run cell by cell (`# %%`) in VS Code, Spyder or Jupyter. File paths are resolved relative to the script.

TODO: say where results are written (e.g. `results/`) and how they map onto SI3.

### 3. Monte Carlo analysis

TODO: describe how to reproduce the Monte Carlo runs. The current SI4 notes that they were run in Activity Browser on the same databases with:

- 100 iterations
- random seed 2113
- uncertainty sampled for technosphere and biosphere exchanges, not for characterisation factors or parameters

### 4. CAML matching

TODO: describe the CAML version (modified or unmodified), model, NAICS concordance and how `SI2` sheets `CAML to NAICS codes`, `caml_EXIO_matching` and `caml_mapping` were produced.

## Known deviations from the submitted version

TODO: list changes made during revision (e.g. corrected location mapping CN, conversion factors, grid mix), with the commit or release in which they were made.

## Citation

If you use this code or data, please cite the article (see above) and this repository (see `CITATION.cff`, or use “Cite this repository” on GitHub).

## Licence

TODO: choose licences, for example:
- code: MIT or BSD-3-Clause
- data in `si/` (own work): CC BY 4.0, provided that the IEA PVPS T12 terms allow redistribution of the derived inventory in SI1

## Funding

This research was funded by the CE-RISE project under the Horizon Europe programme, Grant Agreement number 101092281.

## Contact

Berend Mintjes — b.a.mintjes@cml.leidenuniv.nl — Institute of Environmental Sciences (CML), Leiden University
