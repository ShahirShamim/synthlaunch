"""Synthetic Control Method, Difference-in-Differences, and placebo inference.

The panel is always handled in *wide* form: a DataFrame indexed by date (ISO-8601
strings, sortable lexicographically) with one column per unit and the metric as
values. SCM weights are fit on the pre-intervention period only.

Statistical notes
-----------------
* Weights W solve  min ||y_pre - X_pre W||^2  s.t.  sum(W)=1, W>=0  (SLSQP).
* The simplex constraint is non-convex-friendly enough that we use several random
  restarts plus a uniform start and keep the best objective — deterministic given
  `seed`, so results are reproducible.
* Inference uses the RMSPE-ratio placebo test (Abadie, Diamond & Hainmueller 2010):
  the test statistic is post/pre MSPE ratio, which self-normalises for pre-fit
  quality, and the empirical p-value is the treated unit's rank among placebos.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import norm

_EPS = 1e-12


def pivot_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Tidy (date, unit_id, metric) -> wide [date x unit_id]. Sorted, float values."""
    wide = df.pivot(index="date", columns="unit_id", values="metric").sort_index()
    wide.index = wide.index.astype(str)
    return wide.astype(float)


def _solve_weights(X_pre: np.ndarray, y_pre: np.ndarray, seed: int = 0,
                   n_restarts: int = 10) -> np.ndarray:
    """Fit donor weights on the pre-period via SLSQP with multiple restarts."""
    J = X_pre.shape[1]

    def loss(w: np.ndarray) -> float:
        r = y_pre - X_pre @ w
        return float(r @ r)

    cons = ({"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)},)
    bounds = [(0.0, 1.0)] * J
    rng = np.random.default_rng(seed)

    starts = [np.full(J, 1.0 / J)]
    for _ in range(n_restarts):
        s = rng.random(J)
        starts.append(s / s.sum())

    best: Optional[object] = None
    for w0 in starts:
        res = minimize(loss, w0, method="SLSQP", bounds=bounds, constraints=cons,
                       options={"maxiter": 1000, "ftol": 1e-12})
        if best is None or res.fun < best.fun:
            best = res

    w = np.clip(best.x, 0.0, None)
    total = w.sum()
    return w / total if total > _EPS else np.full(J, 1.0 / J)


@dataclass
class FitResult:
    treated_unit: str
    intervention_date: str
    dates: list[str]
    donors: list[str]
    weights: dict[str, float]
    treated: list[float]
    synthetic: list[float]
    naive_average: list[float]
    gaps: list[float]
    cumulative_gaps: list[float]
    pre_mspe: float
    post_mspe: float
    rmspe_ratio: float
    att: float
    pct_lift: float
    n_pre: int
    n_post: int
    n_donors: int

    def to_dict(self) -> dict:
        return asdict(self)


def synthetic_control(wide: pd.DataFrame, treated_unit: str, intervention_date: str,
                      donor_pool: Optional[list[str]] = None, seed: int = 0) -> FitResult:
    """Fit a synthetic control for `treated_unit` with treatment at `intervention_date`."""
    dates = [str(d) for d in wide.index]
    pre = np.array([d < intervention_date for d in dates])
    post = ~pre
    if pre.sum() == 0 or post.sum() == 0:
        raise ValueError("intervention_date leaves an empty pre- or post-period")

    donors = donor_pool if donor_pool is not None else [c for c in wide.columns if c != treated_unit]
    donors = [d for d in donors if d != treated_unit]
    if len(donors) < 1:
        raise ValueError("need at least one donor unit")

    y = wide[treated_unit].to_numpy(float)
    X = wide[donors].to_numpy(float)

    w = _solve_weights(X[pre], y[pre], seed=seed)
    synth = X @ w
    gaps = y - synth
    pre_mspe = float(np.mean(gaps[pre] ** 2))
    post_mspe = float(np.mean(gaps[post] ** 2))
    ratio = post_mspe / pre_mspe if pre_mspe > _EPS else float("inf")
    att = float(np.mean(gaps[post]))
    denom = float(np.mean(synth[post]))
    pct = float(att / denom * 100.0) if abs(denom) > _EPS else float("nan")

    cum = np.cumsum(gaps)
    naive = X.mean(axis=1)

    return FitResult(
        treated_unit=treated_unit, intervention_date=intervention_date, dates=dates,
        donors=donors, weights={d: float(round(wi, 6)) for d, wi in zip(donors, w)},
        treated=[float(v) for v in y], synthetic=[float(v) for v in synth],
        naive_average=[float(v) for v in naive], gaps=[float(v) for v in gaps],
        cumulative_gaps=[float(v) for v in cum], pre_mspe=pre_mspe, post_mspe=post_mspe,
        rmspe_ratio=float(ratio), att=att, pct_lift=pct, n_pre=int(pre.sum()),
        n_post=int(post.sum()), n_donors=len(donors),
    )


def did(wide: pd.DataFrame, treated_unit: str, intervention_date: str) -> dict:
    """Difference-in-Differences baseline vs the mean of all donors, with a
    parallel-trends diagnostic (pre-period linear slopes)."""
    dates = [str(d) for d in wide.index]
    pre = np.array([d < intervention_date for d in dates])
    post = ~pre
    y = wide[treated_unit].to_numpy(float)
    donors = [c for c in wide.columns if c != treated_unit]
    ctrl = wide[donors].to_numpy(float).mean(axis=1)

    att = float((y[post].mean() - y[pre].mean()) - (ctrl[post].mean() - ctrl[pre].mean()))

    t = np.arange(len(dates), dtype=float)
    treated_slope = float(np.polyfit(t[pre], y[pre], 1)[0])
    control_slope = float(np.polyfit(t[pre], ctrl[pre], 1)[0])
    return {
        "att": att,
        "treated_pre_slope": treated_slope,
        "control_pre_slope": control_slope,
        "parallel_trends_gap": float(treated_slope - control_slope),
        "control_series": [float(v) for v in ctrl],
    }


def placebo_in_space(wide: pd.DataFrame, treated_unit: str, intervention_date: str,
                     seed: int = 0, prune_mult: float = 20.0) -> dict:
    """Run SCM treating each unit as if it were treated; rank the real treated
    unit's RMSPE ratio to get an empirical p-value.

    `prune_mult` reports a second p-value excluding placebos whose pre-period fit
    is much worse than the treated unit's (pre_mspe > prune_mult * treated pre_mspe),
    following Abadie et al.'s robustness convention.
    """
    units = list(wide.columns)
    base = synthetic_control(wide, treated_unit, intervention_date, seed=seed)

    paths: dict[str, list[float]] = {treated_unit: base.gaps}
    ratios: dict[str, float] = {treated_unit: base.rmspe_ratio}
    pre_mspes: dict[str, float] = {treated_unit: base.pre_mspe}

    for u in units:
        if u == treated_unit:
            continue
        pool = [c for c in units if c not in (u, treated_unit)]
        res = synthetic_control(wide, u, intervention_date, donor_pool=pool, seed=seed)
        paths[u] = res.gaps
        ratios[u] = res.rmspe_ratio
        pre_mspes[u] = res.pre_mspe

    treated_ratio = ratios[treated_unit]
    n = len(units)
    p_value = sum(1 for r in ratios.values() if r >= treated_ratio) / n

    keep = [u for u in units if pre_mspes[u] <= prune_mult * base.pre_mspe]
    p_pruned = (sum(1 for u in keep if ratios[u] >= treated_ratio) / len(keep)) if keep else p_value

    return {
        "dates": base.dates,
        "intervention_date": intervention_date,
        "treated_unit": treated_unit,
        "paths": {u: [float(v) for v in g] for u, g in paths.items()},
        "ratios": {u: float(r) for u, r in ratios.items()},
        "treated_ratio": float(treated_ratio),
        "p_value": float(p_value),
        "p_value_pruned": float(p_pruned),
        "n_units": n,
        "n_kept": len(keep),
        "prune_mult": prune_mult,
    }


def placebo_in_time(wide: pd.DataFrame, treated_unit: str, intervention_date: str,
                    fake_fraction: float = 0.67, seed: int = 0) -> dict:
    """Backdate the treatment to an earlier *pre-period* date; a valid design
    shows ~no effect before the real intervention."""
    dates = [str(d) for d in wide.index]
    pre_dates = [d for d in dates if d < intervention_date]
    if len(pre_dates) < 4:
        return {"available": False, "reason": "too few pre-periods for an in-time placebo"}

    idx = max(1, min(len(pre_dates) - 1, int(len(pre_dates) * fake_fraction)))
    fake_date = pre_dates[idx]
    sub = wide.loc[[d for d in dates if d < intervention_date]]  # only true pre-period
    res = synthetic_control(sub, treated_unit, fake_date, seed=seed)
    return {
        "available": True,
        "fake_date": fake_date,
        "dates": res.dates,
        "gaps": res.gaps,
        "att": res.att,
        "pre_mspe": res.pre_mspe,
        "post_mspe": res.post_mspe,
    }


def compute_confidence(fit: FitResult, placebo: dict) -> dict:
    """Map the statistics to a confidence label with explicit reasons. The AI memo
    must respect this label rather than narrate a cleaner story."""
    reasons: list[str] = []
    p = placebo["p_value"]
    n_donors = fit.n_donors
    n_pre = fit.n_pre

    if n_donors < 5:
        label = "insufficient"
        reasons.append(f"only {n_donors} donor units (<5): the placebo p-value is not meaningful")
    elif n_pre < 8:
        label = "insufficient"
        reasons.append(f"only {n_pre} pre-intervention periods (<8): pre-fit is unreliable")
    elif p <= 0.10 and n_donors >= 10:
        label = "high"
        reasons.append(f"empirical p={p:.3f} with {n_donors} donors")
    elif p <= 0.20:
        label = "medium"
        reasons.append(f"empirical p={p:.3f}")
    else:
        label = "low"
        reasons.append(f"effect not distinguishable from placebo noise (p={p:.3f})")

    return {"confidence": label, "p_value": p, "n_donors": n_donors,
            "n_pre": n_pre, "reasons": reasons}


def effect_intervals(fit: FitResult, placebo: dict, z: float = 1.96) -> dict:
    """Placebo-based uncertainty for the effect.

    The spread of the donor placebo gaps *is* the reference distribution for "no
    effect", so we use it to put a (1−α) interval around the estimate:
      * per-period and cumulative bands from the placebo gap spread at each date;
      * an ATT interval from the standard deviation of the placebo ATTs.
    No parametric noise assumption beyond the placebo cross-section.
    """
    dates = fit.dates
    pre = np.array([d < fit.intervention_date for d in dates])
    post = ~pre
    donor = np.array([g for u, g in placebo["paths"].items() if u != fit.treated_unit], dtype=float)
    gap = np.array(fit.gaps)
    cum = np.cumsum(gap)

    # Drop placebos whose pre-period fit is far worse than the treated unit's — a bad
    # fit produces a large gap everywhere, which is not the noise we want to measure.
    if donor.shape[0] >= 2:
        donor_pre_mspe = (donor[:, pre] ** 2).mean(axis=1)
        keep = donor_pre_mspe <= placebo.get("prune_mult", 20.0) * fit.pre_mspe
        if keep.sum() >= 2:
            donor = donor[keep]
    n = donor.shape[0]

    if n < 2:
        zeros = [0.0] * len(dates)
        return {"available": False, "z": z, "se_att": float("nan"),
                "att": fit.att, "att_low": fit.att, "att_high": fit.att,
                "pct": fit.pct_lift, "pct_low": fit.pct_lift, "pct_high": fit.pct_lift,
                "gap_low": list(gap), "gap_high": list(gap),
                "cum_low": list(cum), "cum_high": list(cum), "_z0": zeros}

    std_t = donor.std(axis=0, ddof=1)
    cum_std_t = np.cumsum(donor, axis=1).std(axis=0, ddof=1)
    se_att = float(donor[:, post].mean(axis=1).std(ddof=1))
    synth_post = float(np.mean(np.array(fit.synthetic)[post]))

    def pct(x: float) -> float:
        return float(x / synth_post * 100.0) if abs(synth_post) > _EPS else float("nan")

    return {
        "available": True, "z": z, "se_att": se_att,
        "att": fit.att, "att_low": fit.att - z * se_att, "att_high": fit.att + z * se_att,
        "pct": fit.pct_lift, "pct_low": pct(fit.att - z * se_att), "pct_high": pct(fit.att + z * se_att),
        "gap_low": [float(v) for v in gap - z * std_t],
        "gap_high": [float(v) for v in gap + z * std_t],
        "cum_low": [float(v) for v in cum - z * cum_std_t],
        "cum_high": [float(v) for v in cum + z * cum_std_t],
    }


def power_mde(fit: FitResult, se_att: float, alpha: float = 0.05,
              powers: tuple[float, ...] = (0.8, 0.9)) -> dict:
    """Minimum Detectable Effect for a test of this shape (length × donor pool).

    Treats the placebo ATT spread as the sampling noise of the estimator. For a
    one-sided test at `alpha` and a target `power`,
        MDE = (z_alpha + z_power) · se_att.
    Lets a user ask, before spending, "could this geo test even detect a 5% lift?"
    """
    post = np.array([d >= fit.intervention_date for d in fit.dates])
    base = abs(float(np.mean(np.array(fit.synthetic)[post])))
    if not np.isfinite(se_att):
        return {"available": False, "reason": "need >=2 donors to estimate noise"}

    z_a = float(norm.ppf(1 - alpha))
    items = []
    for p in powers:
        mde = (z_a + float(norm.ppf(p))) * se_att
        items.append({"power": p, "mde_abs": mde,
                      "mde_pct": float(mde / base * 100.0) if base > _EPS else float("nan")})
    return {
        "available": True, "alpha": alpha, "se_att": se_att,
        "n_post": fit.n_post, "n_donors": fit.n_donors,
        "observed_abs": abs(fit.att), "observed_pct": abs(fit.pct_lift),
        "items": items,
        "powered": bool(abs(fit.att) >= items[0]["mde_abs"]),
    }
