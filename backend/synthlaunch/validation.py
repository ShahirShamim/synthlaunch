"""Data-contract validation for the SynthLaunch tidy panel format.

Tidy CSV: one row per (unit, date) with columns ``date`` (ISO-8601), ``unit_id``
(string), ``metric`` (numeric). Column names are configurable via ``columns`` so
users can map their own headers without renaming files.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

MIN_PRE_PERIODS = 8
MIN_DONORS = 2  # >=1 treated + >=2 donors => >=3 units


@dataclass
class ValidationReport:
    ok: bool = True
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    info: dict = field(default_factory=dict)

    def err(self, code: str, msg: str, **extra):
        self.ok = False
        self.errors.append({"code": code, "message": msg, **extra})

    def warn(self, code: str, msg: str, **extra):
        self.warnings.append({"code": code, "message": msg, **extra})

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "info": self.info}


def normalise(df: pd.DataFrame, columns: dict | None = None) -> pd.DataFrame:
    """Rename user columns to the canonical (date, unit_id, metric)."""
    columns = columns or {}
    rename = {columns.get("date", "date"): "date",
              columns.get("unit_id", "unit_id"): "unit_id",
              columns.get("metric", "metric"): "metric"}
    return df.rename(columns=rename)


def validate(df: pd.DataFrame, columns: dict | None = None) -> ValidationReport:
    r = ValidationReport()
    df = normalise(df, columns)

    # 1. required columns
    missing = [c for c in ("date", "unit_id", "metric") if c not in df.columns]
    if missing:
        r.err("missing_columns", f"missing required column(s): {missing}",
              found=list(df.columns))
        return r

    df = df[["date", "unit_id", "metric"]].copy()
    df["date"] = df["date"].astype(str)
    df["unit_id"] = df["unit_id"].astype(str)

    # 2. metric numeric & finite
    df["metric"] = pd.to_numeric(df["metric"], errors="coerce")
    bad = df[df["metric"].isna()]
    if len(bad):
        first = bad.iloc[0]
        r.err("metric_not_numeric",
              f"metric must be numeric and non-null; {len(bad)} bad cell(s)",
              first_bad={"unit_id": first["unit_id"], "date": first["date"]})

    # 3. dates parseable
    parsed = pd.to_datetime(df["date"], errors="coerce")
    if parsed.isna().any():
        bd = df.loc[parsed.isna(), "date"].iloc[0]
        r.err("date_unparseable", f"date(s) not ISO-8601 parseable, e.g. {bd!r}")

    # 4. duplicate (unit_id, date)
    dup = df.duplicated(subset=["unit_id", "date"], keep=False)
    if dup.any():
        d = df[dup].iloc[0]
        r.err("duplicate_rows",
              f"{int(dup.sum())} duplicate (unit_id, date) row(s)",
              first_duplicate={"unit_id": d["unit_id"], "date": d["date"]})

    units = sorted(df["unit_id"].unique().tolist())
    dates = sorted(df["date"].unique().tolist())
    r.info.update({"n_units": len(units), "units": units,
                   "n_dates": len(dates), "date_range": [dates[0], dates[-1]] if dates else []})

    # 5. cohort size
    if len(units) < 1 + MIN_DONORS:
        r.err("too_few_units",
              f"need >=1 treated + >={MIN_DONORS} donor units; found {len(units)}")
    elif len(units) < 6:
        r.warn("small_donor_pool",
               f"{len(units)} units total: with <5 donors the placebo p-value is unreliable")

    # 6. balanced panel — every unit present at every date
    if not r.errors:
        counts = df.groupby("unit_id")["date"].nunique()
        expected = len(dates)
        unbalanced = counts[counts != expected]
        if len(unbalanced):
            u = unbalanced.index[0]
            have = set(df[df["unit_id"] == u]["date"])
            missing_date = next((d for d in dates if d not in have), None)
            r.err("unbalanced_panel",
                  f"unit {u!r} is missing date(s); panel must be balanced",
                  example_missing_cell={"unit_id": u, "date": missing_date})

    return r


def check_intervention(df: pd.DataFrame, treated_unit: str, intervention_date: str,
                       columns: dict | None = None) -> ValidationReport:
    """Validity gates that depend on the chosen treated unit + locked date."""
    r = ValidationReport()
    df = normalise(df, columns)
    dates = sorted(df["date"].astype(str).unique().tolist())
    units = set(df["unit_id"].astype(str).unique())

    if treated_unit not in units:
        r.err("unknown_treated_unit", f"treated unit {treated_unit!r} not in panel")
        return r

    pre = [d for d in dates if d < intervention_date]
    post = [d for d in dates if d >= intervention_date]
    if not pre:
        r.err("no_pre_period", "intervention date is at/before the first observation")
    if not post:
        r.err("no_post_period", "intervention date is at/after the last observation")
    if len(pre) < MIN_PRE_PERIODS:
        r.warn("few_pre_periods",
               f"{len(pre)} pre-periods (<{MIN_PRE_PERIODS}): synthetic fit may be unreliable")

    r.info.update({"n_pre": len(pre), "n_post": len(post),
                   "n_donors": len(units) - 1})
    return r
