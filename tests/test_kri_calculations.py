"""Golden-value regression for the KRI calculation core.

The expected values below were captured from the sample portfolio and
hand-checked against the formulas in the technical review. They are the
contract: if a refactor moves any of them the change must be deliberate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

GOLDEN_METRICS = {
    "var_95_1d": 0.018935499999999997,
    "concentration": 0.22,
    "top5_concentration": 0.8300000000000001,
    "largest_asset_class": 0.54,
    "liquidity_ratio": 0.875,
    "stressed_liquidity_ratio": 0.65625,
    "illiquid_ratio": 0.09,
    "max_drawdown": 0.06397575586823556,
    "volatility_20d": 0.1461404157137922,
    "stress_equity_down_10": 0.055749999999999994,
    "credit_exposure": 0.13,
    "leverage": 1.07,
    "derivative_exposure": 0.105,
}

GOLDEN_STATUSES = {
    "var_95_1d": "OK",
    "concentration": "BREACH",
    "top5_concentration": "BREACH",
    "largest_asset_class": "WATCH",
    "liquidity_ratio": "OK",
    "stressed_liquidity_ratio": "OK",
    "illiquid_ratio": "OK",
    "max_drawdown": "WATCH",
    "volatility_20d": "OK",
    "stress_equity_down_10": "WATCH",
    "credit_exposure": "OK",
    "leverage": "OK",
    "derivative_exposure": "OK",
}


@pytest.fixture
def metrics(reference_result) -> dict[str, float]:
    return dict(zip(reference_result.kri_summary["metric"], reference_result.kri_summary["value"]))


@pytest.fixture
def statuses(reference_result) -> dict[str, str]:
    return dict(zip(reference_result.kri_summary["metric"], reference_result.kri_summary["status"]))


def test_nav_matches_sum_of_market_values(reference_result):
    assert reference_result.nav == pytest.approx(10_000_000.0)
    assert reference_result.nav == pytest.approx(reference_result.holdings["market_value"].sum())


def test_all_expected_metrics_are_produced(metrics):
    assert set(metrics) == set(GOLDEN_METRICS)


@pytest.mark.parametrize("metric", sorted(GOLDEN_METRICS))
def test_metric_golden_value(metrics, metric):
    assert metrics[metric] == pytest.approx(GOLDEN_METRICS[metric], rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("metric", sorted(GOLDEN_STATUSES))
def test_metric_golden_status(statuses, metric):
    assert statuses[metric] == GOLDEN_STATUSES[metric]


def test_breach_log_contains_only_hard_limit_breaches(reference_result):
    """The breach register is a regulatory record; a watch item is not a breach."""
    breaches = set(reference_result.kri_summary.loc[reference_result.kri_summary["status"] == "BREACH", "metric"])
    assert set(reference_result.breach_log["metric"]) == breaches
    assert set(reference_result.breach_log["status"]) == {"BREACH"}


def test_watch_list_contains_only_early_warnings(reference_result):
    watches = set(reference_result.kri_summary.loc[reference_result.kri_summary["status"] == "WATCH", "metric"])
    assert set(reference_result.watch_list["metric"]) == watches
    assert set(reference_result.watch_list["status"]) == {"WATCH"}


def test_breach_log_and_watch_list_are_disjoint(reference_result):
    assert not set(reference_result.breach_log["metric"]) & set(reference_result.watch_list["metric"])


def test_breach_log_plus_watch_list_equals_the_action_plan(reference_result):
    combined = set(reference_result.breach_log["metric"]) | set(reference_result.watch_list["metric"])
    assert combined == set(reference_result.action_plan["metric"])


def test_both_logs_keep_their_columns_when_empty(reference_result):
    """An empty register must still have its schema, or the Excel sheet loses its headers."""
    from fund_kri_monitor.kri import build_breach_log, build_watch_list

    clean = reference_result.kri_summary.assign(status="OK")
    for builder in (build_breach_log, build_watch_list):
        frame = builder(clean, fund_id="KRI_FUND", as_of_date=reference_result.as_of_date)
        assert frame.empty
        assert list(frame.columns) == list(reference_result.breach_log.columns)


def test_action_plan_covers_every_watch_and_breach(reference_result):
    flagged = set(
        reference_result.kri_summary.loc[
            reference_result.kri_summary["status"].isin(["WATCH", "BREACH"]), "metric"
        ]
    )
    assert set(reference_result.action_plan["metric"]) == flagged


def test_var_equals_fifth_percentile_of_portfolio_returns(reference_result, metrics):
    expected = abs(np.percentile(reference_result.portfolio_returns["portfolio_return"], 5))
    assert metrics["var_95_1d"] == pytest.approx(expected)


def test_concentration_equals_largest_absolute_weight(reference_result, metrics):
    holdings = reference_result.holdings
    expected = holdings["market_value"].abs().max() / holdings["market_value"].abs().sum()
    assert metrics["concentration"] == pytest.approx(expected)


def test_leverage_equals_gross_exposure_over_nav(reference_result, metrics):
    holdings = reference_result.holdings
    expected = holdings["gross_exposure"].sum() / reference_result.nav
    assert metrics["leverage"] == pytest.approx(expected)


def test_derivative_multiplier_is_applied_to_gross_exposure(reference_result):
    swap = reference_result.holdings.set_index("asset_id").loc["IRS_SWAP"]
    assert swap["gross_exposure"] == pytest.approx(swap["market_value"] * swap["exposure_multiplier"])
    assert swap["gross_exposure"] == pytest.approx(1_050_000.0)


def test_stressed_liquidity_is_a_haircut_of_headline_liquidity(metrics):
    assert metrics["stressed_liquidity_ratio"] == pytest.approx(metrics["liquidity_ratio"] * 0.75)


def test_exposure_summary_weights_sum_to_one(reference_result):
    assert reference_result.exposure_summary["weight"].sum() == pytest.approx(1.0)


def test_drawdown_series_is_non_positive(reference_result):
    assert (reference_result.portfolio_returns["drawdown"] <= 1e-12).all()


def test_max_drawdown_is_absolute_value_of_worst_drawdown(reference_result, metrics):
    worst = reference_result.portfolio_returns["drawdown"].min()
    assert metrics["max_drawdown"] == pytest.approx(abs(worst))


def test_history_snapshot_has_one_row_per_metric(reference_result):
    assert len(reference_result.history) == len(GOLDEN_METRICS)
    assert reference_result.history["metric"].is_unique


def test_as_of_date_is_taken_from_the_position_file(reference_result):
    assert reference_result.as_of_date == pd.Timestamp("2024-12-31")
