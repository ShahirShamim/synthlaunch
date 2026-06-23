"""Data-contract tests."""
import pandas as pd

from synthlaunch import datasets, validation


def test_bundled_datasets_pass():
    for ds_id in ("prop99_california", "brexit_uk", "synthetic_marketplace", "marketing_geolift"):
        rep = validation.validate(datasets.get_dataframe(ds_id))
        assert rep.ok, rep.errors


def test_detects_duplicate_rows():
    df = pd.DataFrame({"date": ["2020-01-01", "2020-01-01", "2020-02-01"],
                       "unit_id": ["A", "A", "A"], "metric": [1.0, 2.0, 3.0]})
    rep = validation.validate(df)
    assert not rep.ok
    assert any(e["code"] == "duplicate_rows" for e in rep.errors)


def test_detects_unbalanced_panel():
    # B is missing 2020-02-01
    df = pd.DataFrame({
        "date": ["2020-01-01", "2020-02-01", "2020-01-01"],
        "unit_id": ["A", "A", "B"], "metric": [1.0, 2.0, 3.0]})
    rep = validation.validate(df)
    assert not rep.ok
    codes = {e["code"] for e in rep.errors}
    assert "unbalanced_panel" in codes or "too_few_units" in codes


def test_detects_non_numeric_metric():
    df = pd.DataFrame({"date": ["2020-01-01", "2020-02-01"],
                       "unit_id": ["A", "A"], "metric": ["x", "2.0"]})
    rep = validation.validate(df)
    assert not rep.ok
    assert any(e["code"] == "metric_not_numeric" for e in rep.errors)


def test_column_mapping():
    df = pd.DataFrame({"t": ["2020-01-01"], "city": ["A"], "rev": [1.0]})
    norm = validation.normalise(df, {"date": "t", "unit_id": "city", "metric": "rev"})
    assert {"date", "unit_id", "metric"} <= set(norm.columns)


def test_intervention_gate_flags_unknown_unit():
    df = datasets.get_dataframe("prop99_california")
    rep = validation.check_intervention(df, "Atlantis", "1989-01-01")
    assert not rep.ok
    assert any(e["code"] == "unknown_treated_unit" for e in rep.errors)
