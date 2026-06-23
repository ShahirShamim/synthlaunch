"""Statistical-robustness tests: ground-truth recovery, reproducibility, and the
canonical California Prop 99 result."""
import numpy as np

from synthlaunch import datasets, scm


def _wide(ds_id):
    return scm.pivot_panel(datasets.get_dataframe(ds_id))


def test_recovers_known_effect_on_synthetic():
    """synthetic_marketplace has a known injected ATT of ~-9.54 on London."""
    wide = _wide("synthetic_marketplace")
    fit = scm.synthetic_control(wide, "London", "2025-01-01")
    assert fit.att < 0
    assert -13 < fit.att < -6                      # near the injected -9.54
    assert fit.pct_lift < 0
    w = fit.weights
    # the true counterfactual was 0.5 Berlin + 0.3 Madrid + 0.2 Amsterdam
    assert w["Berlin"] + w["Madrid"] + w["Amsterdam"] > 0.6
    assert abs(sum(w.values()) - 1.0) < 1e-6
    assert all(v >= -1e-9 for v in w.values())


def test_weights_satisfy_simplex():
    wide = _wide("prop99_california")
    fit = scm.synthetic_control(wide, "California", "1989-01-01")
    assert abs(sum(fit.weights.values()) - 1.0) < 1e-6
    assert all(v >= -1e-9 for v in fit.weights.values())


def test_placebo_pvalue_reproducible():
    wide = _wide("prop99_california")
    a = scm.placebo_in_space(wide, "California", "1989-01-01")
    b = scm.placebo_in_space(wide, "California", "1989-01-01")
    assert a["p_value"] == b["p_value"]
    assert a["treated_ratio"] == b["treated_ratio"]


def test_prop99_significant_negative_effect():
    """California's per-capita cigarette sales fell sharply and it sits in the
    extreme tail of the placebo RMSPE-ratio distribution.

    Note: this MVP uses *outcome-only* SCM (no predictor covariates), which yields
    California at rank ~3 of 39 (empirical p ~ 0.08) and ATT ~ -19 packs. The
    canonical Abadie/Diamond/Hainmueller result (rank 1, p ~ 0.026) additionally
    matches on income/price/age/beer predictors — a documented fast-follow.
    """
    wide = _wide("prop99_california")
    fit = scm.synthetic_control(wide, "California", "1989-01-01")
    placebo = scm.placebo_in_space(wide, "California", "1989-01-01")
    assert fit.att < -10                        # strong negative effect (~ -19 packs)
    assert placebo["p_value"] <= 0.10           # California in the top ~8% of 39 units
    conf = scm.compute_confidence(fit, placebo)
    assert conf["confidence"] in {"high", "medium"}


def test_brexit_uk_negative_post_2016_drift():
    """UK tracks its synthetic twin pre-2016, then drifts below it. Annual data
    gives a visible-but-modest shortfall (not strongly significant) — an honest
    real-world result, presented as such in the UI."""
    wide = _wide("brexit_uk")
    fit = scm.synthetic_control(wide, "United Kingdom", "2016-01-01")
    assert fit.pre_mspe < 2.0          # good pre-fit on the rebased index
    assert fit.att < 0                 # UK below its synthetic after 2016
    # by 2019 the gap should be more negative than at the 2016 launch
    gap = dict(zip(fit.dates, fit.gaps))
    assert gap["2019-01-01"] < gap["2016-01-01"]


def test_in_time_placebo_small_before_treatment():
    wide = _wide("synthetic_marketplace")
    res = scm.placebo_in_time(wide, "London", "2025-01-01")
    assert res["available"]
    fit = scm.synthetic_control(wide, "London", "2025-01-01")
    # a fake earlier treatment should show a far smaller effect than the real one
    assert abs(res["att"]) < abs(fit.att)


def test_effect_intervals_structure_and_significance():
    # structural checks on the real (heavy-tailed) Prop 99 placebo distribution
    wide = _wide("prop99_california")
    fit = scm.synthetic_control(wide, "California", "1989-01-01")
    ci = scm.effect_intervals(fit, scm.placebo_in_space(wide, "California", "1989-01-01"))
    assert ci["available"]
    assert ci["att_low"] < fit.att < ci["att_high"]      # CI brackets the point estimate
    assert ci["se_att"] > 0
    assert len(ci["cum_low"]) == len(fit.dates) == len(ci["gap_high"])

    # on the clean synthetic panel the effect is significant: 95% CI excludes 0
    sw = _wide("synthetic_marketplace")
    sf = scm.synthetic_control(sw, "London", "2025-01-01")
    sci = scm.effect_intervals(sf, scm.placebo_in_space(sw, "London", "2025-01-01"))
    assert sci["att_high"] < 0


def test_marketing_geolift_positive_and_powered():
    """The geo-lift demo has a known +20% lift (~14.6k ATT/week). The engine should
    recover a clearly positive, significant, well-powered effect."""
    wide = _wide("marketing_geolift")
    fit = scm.synthetic_control(wide, "Manchester", "2025-01-13")
    placebo = scm.placebo_in_space(wide, "Manchester", "2025-01-13")
    ci = scm.effect_intervals(fit, placebo)
    power = scm.power_mde(fit, ci["se_att"])
    assert fit.att > 5000                     # strong positive lift (~14.6k)
    assert ci["att_low"] > 0                  # 95% CI excludes 0
    assert power["powered"] is True
    assert scm.compute_confidence(fit, placebo)["confidence"] in {"high", "medium"}


def test_power_mde_math_and_flag():
    wide = _wide("prop99_california")
    fit = scm.synthetic_control(wide, "California", "1989-01-01")
    ci = scm.effect_intervals(fit, scm.placebo_in_space(wide, "California", "1989-01-01"))
    power = scm.power_mde(fit, ci["se_att"])
    assert power["available"]
    assert power["items"][0]["mde_abs"] > 0
    assert power["items"][1]["mde_abs"] > power["items"][0]["mde_abs"]  # 90% needs bigger effect
    # the flag is consistent with the MDE it reports
    assert power["powered"] == (abs(fit.att) >= power["items"][0]["mde_abs"])


def test_did_runs_and_reports_parallel_trends():
    wide = _wide("prop99_california")
    res = scm.did(wide, "California", "1989-01-01")
    assert "att" in res and "parallel_trends_gap" in res
    assert res["att"] < 0
