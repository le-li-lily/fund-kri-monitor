"""Input-validation behaviour of the loaders.

Each test states what a real fund-accounting extract can plausibly contain and
asserts that the system either rejects it loudly or handles it correctly.
Silent acceptance of malformed data is the failure mode being guarded against.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fund_kri_monitor.kri import (
    calculate_portfolio_returns,
    load_asset_returns,
    load_positions,
    run_monitor,
)


def _write(tmp_path, frame: pd.DataFrame, name: str = "positions.csv"):
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return path


def test_valid_file_loads(positions_path):
    assert len(load_positions(positions_path)) == 8


def test_missing_required_column_is_rejected(tmp_path, positions_frame):
    path = _write(tmp_path, positions_frame.drop(columns=["adv_30d"]))
    with pytest.raises(ValueError, match="missing columns"):
        load_positions(path)


def test_empty_position_file_is_rejected(tmp_path, positions_frame):
    path = _write(tmp_path, positions_frame.iloc[0:0])
    with pytest.raises(ValueError, match="no holdings"):
        load_positions(path)


def test_multiple_fund_ids_are_rejected(tmp_path, positions_frame):
    frame = positions_frame.copy()
    frame.loc[frame.index[-1], "fund_id"] = "OTHER_FUND"
    path = _write(tmp_path, frame)
    with pytest.raises(ValueError, match="exactly one fund_id"):
        load_positions(path)


def test_duplicate_asset_id_is_rejected(tmp_path, positions_frame):
    frame = pd.concat([positions_frame, positions_frame.iloc[[0]]], ignore_index=True)
    path = _write(tmp_path, frame)
    with pytest.raises(ValueError, match="duplicate asset_id"):
        load_positions(path)


def test_negative_adv_is_rejected(tmp_path, positions_frame):
    frame = positions_frame.copy()
    frame.loc[frame.index[0], "adv_30d"] = -1
    path = _write(tmp_path, frame)
    with pytest.raises(ValueError, match="negative adv_30d"):
        load_positions(path)


def test_negative_liquidity_days_is_rejected(tmp_path, positions_frame):
    frame = positions_frame.copy()
    frame.loc[frame.index[0], "liquidity_days"] = -5
    path = _write(tmp_path, frame)
    with pytest.raises(ValueError, match="negative liquidity_days"):
        load_positions(path)


def test_missing_market_value_is_rejected(tmp_path, positions_frame):
    frame = positions_frame.copy()
    frame.loc[frame.index[0], "market_value"] = None
    path = _write(tmp_path, frame)
    with pytest.raises(ValueError, match="missing market_value"):
        load_positions(path)


def test_non_numeric_market_value_is_rejected(tmp_path, positions_frame):
    frame = positions_frame.copy()
    frame["market_value"] = frame["market_value"].astype(object)
    frame.loc[frame.index[0], "market_value"] = "n/a"
    path = _write(tmp_path, frame)
    with pytest.raises(ValueError):
        load_positions(path)


def test_zero_adv_is_accepted_because_private_assets_do_not_trade(positions_path):
    positions = load_positions(positions_path)
    assert (positions["adv_30d"] == 0).any()


def test_duplicate_return_dates_are_rejected(tmp_path, returns_path):
    returns = pd.read_csv(returns_path)
    doubled = pd.concat([returns, returns.iloc[[0]]], ignore_index=True)
    path = tmp_path / "returns.csv"
    doubled.to_csv(path, index=False)
    with pytest.raises(ValueError, match="duplicate dates"):
        load_asset_returns(path)


def test_empty_return_file_is_rejected(tmp_path, returns_path):
    returns = pd.read_csv(returns_path).iloc[0:0]
    path = tmp_path / "returns.csv"
    returns.to_csv(path, index=False)
    with pytest.raises(ValueError, match="no observations"):
        load_asset_returns(path)


def test_short_return_history_is_rejected(tmp_path, positions_path, returns_path):
    positions = load_positions(positions_path)
    returns = load_asset_returns(returns_path).head(10)
    with pytest.raises(ValueError, match="At least 20 return observations"):
        calculate_portfolio_returns(positions, returns)


def test_asset_without_a_return_series_is_rejected(tmp_path, positions_path, returns_path):
    positions = load_positions(positions_path)
    returns = load_asset_returns(returns_path).drop(columns=["NVDA"])
    with pytest.raises(ValueError, match="missing asset columns"):
        calculate_portfolio_returns(positions, returns)


def test_gap_in_a_return_series_is_rejected(tmp_path, positions_path, returns_path):
    positions = load_positions(positions_path)
    returns = load_asset_returns(returns_path)
    returns.iloc[3, returns.columns.get_loc("HY_CREDIT")] = None
    with pytest.raises(ValueError, match="missing values for assets"):
        calculate_portfolio_returns(positions, returns)


def test_zero_nav_is_rejected(tmp_path, positions_path, returns_path):
    positions = load_positions(positions_path)
    positions["market_value"] = 0.0
    returns = load_asset_returns(returns_path)
    with pytest.raises(ValueError, match="NAV must be positive"):
        calculate_portfolio_returns(positions, returns)


def test_short_position_does_not_crash_the_run(tmp_path, positions_frame, returns_path, thresholds_path):
    """A short derivative leg is ordinary in a real fund and must not break the run."""
    frame = positions_frame.copy()
    frame.loc[frame["asset_id"] == "IRS_SWAP", "market_value"] = -350000
    path = _write(tmp_path, frame)
    result = run_monitor(
        positions_path=path,
        returns_path=returns_path,
        thresholds_path=thresholds_path,
        history_path=tmp_path / "history.csv",
    )
    assert result.nav == pytest.approx(9_300_000.0)
    metrics = dict(zip(result.kri_summary["metric"], result.kri_summary["value"]))
    # NAV < gross NAV once a position is short, so leverage must exceed the long-only case.
    assert metrics["leverage"] > 1.07


def test_single_holding_portfolio_reports_full_concentration(
    tmp_path, positions_frame, returns_path, thresholds_path
):
    frame = positions_frame[positions_frame["asset_id"] == "AAPL"].copy()
    frame.loc[:, "market_value"] = 10_000_000
    path = _write(tmp_path, frame)
    result = run_monitor(
        positions_path=path,
        returns_path=returns_path,
        thresholds_path=thresholds_path,
        history_path=tmp_path / "history.csv",
    )
    metrics = dict(zip(result.kri_summary["metric"], result.kri_summary["value"]))
    assert metrics["concentration"] == pytest.approx(1.0)
    assert metrics["top5_concentration"] == pytest.approx(1.0)
    statuses = dict(zip(result.kri_summary["metric"], result.kri_summary["status"]))
    assert statuses["concentration"] == "BREACH"
