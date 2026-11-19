# %% Monte Carlo analysis (100 runs): full and single LCA, EXIO3H background
# Only the foreground (PV LCI) exchanges have uncertainty: lognormal, from the SD95 in
# SI1 (technosphere and biosphere exchanges, not the characterisation factors). The
# resource conversion activities and EXIO3H have none. Each run therefore samples the
# foreground exchanges and solves only the foreground system. The background enters
# through the life-cycle score per unit of each product the foreground buys, which does
# not change between runs and is calculated once with the existing factorisation.
# Both cases use the same random values in each run.
import scipy.sparse as sp
import stats_arrays
from bw2data.utils import TYPE_DICTIONARY

MC_RUNS = 100
MC_SEED = 2113  # as in the original Activity Browser analysis
mc_cases = {"full LCA": functional_unit_full, "single LCA": functional_unit_single}

lca.switch_method(method_ef31)
lca.redo_lcia(functional_unit_full)
lca.fix_dictionaries()

# Life-cycle score per unit of every product: solve A^T s = h once
h_all = np.asarray(
    (lca.characterization_matrix @ lca.biosphere_matrix).sum(axis=0)
).ravel()
s_all = scipy.linalg.lu_solve(_lu, h_all, trans=1, check_finite=False)

# Foreground: the activities of the PV LCI database
fg_keys = [key for key in lca.activity_dict if key[0] == pv_db_name]
fg_cols = np.array([lca.activity_dict[key] for key in fg_keys])
fg_rows = np.array([lca.product_dict[key] for key in fg_keys])
col_pos = {col: i for i, col in enumerate(fg_cols)}
s_background = s_all.copy()
s_background[fg_rows] = 0.0  # products bought from outside the foreground only

tech = lca.tech_params[np.isin(lca.tech_params["col"], fg_cols)]
bio = lca.bio_params[np.isin(lca.bio_params["col"], fg_cols)]
tech_sign = np.where(tech["type"] == TYPE_DICTIONARY["technosphere"], -1.0, 1.0)
tech_col = np.array([col_pos[c] for c in tech["col"]])
bio_col = np.array([col_pos[c] for c in bio["col"]])
bio_cf = lca.characterization_matrix.diagonal()[bio["row"]]
tech_uncertain = tech["uncertainty_type"] > 1  # 0 and 1: no uncertainty
bio_uncertain = bio["uncertainty_type"] > 1


def foreground_scores(tech_values, bio_values):
    """Score of each case for one set of foreground exchange values."""
    A = sp.coo_matrix(
        (tech_sign * tech_values, (tech["row"], tech_col)),
        shape=(lca.technosphere_matrix.shape[0], len(fg_cols)),
    ).tocsc()
    A_ff = A[fg_rows, :].toarray()
    per_unit = (
        np.bincount(bio_col, weights=bio_cf * bio_values, minlength=len(fg_cols))
        - s_background @ A  # background inputs (inputs are negative in A)
    )
    result = {}
    for case, fu in mc_cases.items():
        demand = np.zeros(len(fg_cols))
        for act, amount in fu.items():
            demand[fg_keys.index(act.key)] = amount
        result[case] = float(per_unit @ np.linalg.solve(A_ff, demand))
    return result


# Checks: the foreground columns match the technosphere matrix, and without
# randomness this reproduces the deterministic scores
A_check = sp.coo_matrix(
    (tech_sign * tech["amount"], (tech["row"], tech_col)),
    shape=(lca.technosphere_matrix.shape[0], len(fg_cols)),
).tocsc()
assert abs(A_check - lca.technosphere_matrix[:, fg_cols]).max() < 1e-12
for case, value in foreground_scores(tech["amount"], bio["amount"]).items():
    assert np.isclose(value, scores[case], rtol=1e-6), (case, value, scores[case])

tech_rng = stats_arrays.MCRandomNumberGenerator(tech[tech_uncertain], seed=MC_SEED)
bio_rng = stats_arrays.MCRandomNumberGenerator(bio[bio_uncertain], seed=MC_SEED + 1)
tech_values, bio_values = tech["amount"].copy(), bio["amount"].copy()
mc_runs = []
for run in range(MC_RUNS):
    tech_values[tech_uncertain] = tech_rng.next()
    bio_values[bio_uncertain] = bio_rng.next()
    mc_runs.append(foreground_scores(tech_values, bio_values))

mc_runs = pd.DataFrame(mc_runs).rename_axis("run")
mc_summary = pd.DataFrame(
    {
        "deterministic": {case: scores[case] for case in mc_cases},
        "mean": mc_runs.mean(),
        "median": mc_runs.median(),
        "standard deviation": mc_runs.std(),
        "2.5th percentile": mc_runs.quantile(0.025),
        "97.5th percentile": mc_runs.quantile(0.975),
    }
)
print(mc_summary)
print(f"full > single in {(mc_runs['full LCA'] > mc_runs['single LCA']).mean():.0%} of runs")
mc_runs.to_csv(RESULTS_DIR / "monte_carlo_runs.csv")
mc_summary.to_csv(RESULTS_DIR / "monte_carlo_summary.csv")
log_time(f"Monte Carlo ({MC_RUNS} runs) done")
