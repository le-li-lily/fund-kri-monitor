from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MonitorResult:
    holdings: pd.DataFrame
    returns: pd.DataFrame
    portfolio_returns: pd.DataFrame
    data_quality: pd.DataFrame
    exposure_summary: pd.DataFrame
    kri_summary: pd.DataFrame
    breach_log: pd.DataFrame
    action_plan: pd.DataFrame
    history: pd.DataFrame
    thresholds: pd.DataFrame
    nav: float
    as_of_date: pd.Timestamp


def load_thresholds(path: str | Path) -> dict[str, dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_positions(path: str | Path) -> pd.DataFrame:
    positions = pd.read_csv(path, parse_dates=["as_of_date"])
    required = {
        "fund_id",
        "as_of_date",
        "asset_id",
        "asset_name",
        "asset_class",
        "market_value",
        "exposure_multiplier",
        "adv_30d",
        "liquidity_days",
    }
    missing = required.difference(positions.columns)
    if missing:
        raise ValueError(f"Positions file missing columns: {sorted(missing)}")
    _validate_positions(positions)
    return positions


def load_asset_returns(path: str | Path) -> pd.DataFrame:
    returns = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    if returns.empty:
        raise ValueError("Returns file has no observations.")
    if returns.index.has_duplicates:
        duplicates = returns.index[returns.index.duplicated()].strftime("%Y-%m-%d").unique().tolist()
        raise ValueError(f"Returns file has duplicate dates: {duplicates}")
    return returns.apply(pd.to_numeric, errors="raise")


def _validate_positions(positions: pd.DataFrame) -> None:
    if positions.empty:
        raise ValueError("Positions file has no holdings.")
    if positions["fund_id"].nunique() != 1:
        raise ValueError("Positions file must contain exactly one fund_id per run.")
    if positions["asset_id"].duplicated().any():
        duplicates = sorted(positions.loc[positions["asset_id"].duplicated(), "asset_id"].unique())
        raise ValueError(f"Positions file has duplicate asset_id rows: {duplicates}")
    for column in ["market_value", "exposure_multiplier", "adv_30d", "liquidity_days"]:
        positions[column] = pd.to_numeric(positions[column], errors="raise")
    if positions["market_value"].isna().any():
        raise ValueError("Positions file contains missing market_value.")
    if (positions["adv_30d"] < 0).any():
        raise ValueError("Positions file contains negative adv_30d.")
    if (positions["liquidity_days"] < 0).any():
        raise ValueError("Positions file contains negative liquidity_days.")


def calculate_portfolio_returns(positions: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    nav = positions["market_value"].sum()
    if nav <= 0:
        raise ValueError("Portfolio NAV must be positive.")

    weights = positions.set_index("asset_id")["market_value"] / nav
    missing_assets = sorted(set(weights.index).difference(returns.columns))
    if missing_assets:
        raise ValueError(f"Returns file missing asset columns: {missing_assets}")

    aligned_returns = returns[weights.index]
    if len(aligned_returns) < 20:
        raise ValueError("At least 20 return observations are required for monitoring.")
    if aligned_returns.isna().any().any():
        missing = aligned_returns.columns[aligned_returns.isna().any()].tolist()
        raise ValueError(f"Returns file contains missing values for assets: {missing}")
    portfolio_returns = aligned_returns.mul(weights, axis=1).sum(axis=1)
    cumulative_nav = (1 + portfolio_returns).cumprod()
    running_peak = cumulative_nav.cummax()
    drawdown = cumulative_nav / running_peak - 1

    return pd.DataFrame(
        {
            "date": portfolio_returns.index,
            "portfolio_return": portfolio_returns.values,
            "cumulative_nav_index": cumulative_nav.values,
            "drawdown": drawdown.values,
        }
    )


def build_exposure_summary(holdings: pd.DataFrame) -> pd.DataFrame:
    nav = holdings["market_value"].sum()
    gross_nav = holdings["market_value"].abs().sum()
    grouped = (
        holdings.groupby("asset_class", as_index=False)
        .agg(
            market_value=("market_value", "sum"),
            gross_exposure=("gross_exposure", "sum"),
            holding_count=("asset_id", "count"),
            liquid_5d_value=("five_day_liquidity_value", "sum"),
        )
        .sort_values("market_value", ascending=False)
    )
    grouped["weight"] = grouped["market_value"] / nav
    grouped["absolute_weight"] = grouped["market_value"].abs() / gross_nav
    grouped["gross_exposure_nav"] = grouped["gross_exposure"] / nav
    grouped["liquid_5d_weight"] = grouped["liquid_5d_value"] / nav
    return grouped


def calculate_kri_summary(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    thresholds: dict[str, dict[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    nav = positions["market_value"].sum()
    gross_nav = positions["market_value"].abs().sum()
    holdings = positions.copy()
    holdings["weight"] = holdings["market_value"] / nav
    holdings["absolute_weight"] = holdings["market_value"].abs() / gross_nav
    holdings["gross_exposure"] = holdings["market_value"].abs() * holdings["exposure_multiplier"].abs()
    holdings["liquid_within_5d"] = holdings["liquidity_days"] <= 5
    holdings["days_to_liquid_by_adv"] = np.where(
        holdings["adv_30d"] > 0,
        holdings["market_value"].abs() / (holdings["adv_30d"] * 0.2),
        np.inf,
    )
    holdings["five_day_liquidity_value"] = np.minimum(
        holdings["market_value"].abs(),
        holdings["adv_30d"].clip(lower=0) * 0.2 * 5,
    )
    holdings.loc[holdings["asset_class"].eq("Cash"), "five_day_liquidity_value"] = holdings["market_value"].abs()
    holdings["stressed_liquidity_value"] = holdings["five_day_liquidity_value"] * 0.75

    portfolio_returns = calculate_portfolio_returns(holdings, returns)
    exposure_summary = build_exposure_summary(holdings)

    recent_returns = portfolio_returns["portfolio_return"].tail(min(20, len(portfolio_returns)))
    equity_weight = holdings.loc[holdings["asset_class"].eq("Equity"), "weight"].sum()
    derivative_equity_weight = holdings.loc[holdings["asset_class"].eq("Derivative"), "weight"].sum() * 0.5
    equity_shock_loss = abs(-0.10 * (equity_weight + derivative_equity_weight))
    asset_class_weights = holdings.groupby("asset_class")["market_value"].sum().abs().div(gross_nav)

    metrics = {
        "var_95_1d": abs(np.percentile(portfolio_returns["portfolio_return"], 5)),
        "concentration": holdings["absolute_weight"].max(),
        "top5_concentration": holdings["absolute_weight"].nlargest(min(5, len(holdings))).sum(),
        "largest_asset_class": asset_class_weights.max(),
        "liquidity_ratio": holdings.loc[holdings["liquid_within_5d"], "market_value"].abs().sum() / gross_nav,
        "stressed_liquidity_ratio": holdings["stressed_liquidity_value"].sum() / nav,
        "illiquid_ratio": holdings.loc[holdings["liquidity_days"] > 10, "market_value"].abs().sum() / gross_nav,
        "max_drawdown": abs(portfolio_returns["drawdown"].min()),
        "volatility_20d": recent_returns.std(ddof=0) * np.sqrt(252),
        "stress_equity_down_10": equity_shock_loss,
        "credit_exposure": holdings.loc[holdings["asset_class"].eq("Credit"), "market_value"].abs().sum() / gross_nav,
        "leverage": holdings["gross_exposure"].sum() / nav,
        "derivative_exposure": holdings.loc[holdings["asset_class"].eq("Derivative"), "gross_exposure"].sum() / nav,
    }

    rows: list[dict[str, Any]] = []
    for metric, value in metrics.items():
        threshold = thresholds[metric]
        warning = float(threshold["warning"])
        limit = float(threshold["limit"])
        comparison = threshold["comparison"]
        status = _status(value, warning, limit, comparison)
        rows.append(
            {
                "metric": metric,
                "category": threshold.get("category", ""),
                "value": value,
                "warning": warning,
                "limit": limit,
                "comparison": comparison,
                "status": status,
                "owner": _owner(metric),
                "recommended_action": _recommended_action(metric),
                "description": threshold.get("description", ""),
                "format": threshold.get("format", "number"),
            }
        )

    kri_summary = pd.DataFrame(rows)
    return holdings, portfolio_returns, exposure_summary, kri_summary


def build_breach_log(kri_summary: pd.DataFrame, fund_id: str, as_of_date: pd.Timestamp) -> pd.DataFrame:
    events = kri_summary.loc[kri_summary["status"].isin(["WATCH", "BREACH"])].copy()
    if events.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "event_id",
                "fund_id",
                "as_of_date",
                "metric",
                "observed_value",
                "warning",
                "limit",
                "comparison",
                "status",
                "owner",
                "recommended_action",
            ]
        )

    events["timestamp"] = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")
    events["event_id"] = events["metric"].map(lambda metric: _event_id(fund_id, metric))
    events["fund_id"] = fund_id
    events["as_of_date"] = as_of_date.strftime("%Y-%m-%d")
    events["observed_value"] = events["value"]
    return events[
        [
            "timestamp",
            "event_id",
            "fund_id",
            "as_of_date",
            "metric",
            "observed_value",
            "warning",
            "limit",
            "comparison",
            "status",
            "owner",
            "recommended_action",
        ]
    ]


def build_action_plan(kri_summary: pd.DataFrame, fund_id: str, as_of_date: pd.Timestamp) -> pd.DataFrame:
    events = kri_summary.loc[kri_summary["status"].isin(["WATCH", "BREACH"])].copy()
    if events.empty:
        return pd.DataFrame(
            columns=["event_id", "priority", "metric", "status", "owner", "due_date", "recommended_action", "evidence"]
        )

    events["priority"] = np.where(events["status"].eq("BREACH"), "High", "Medium")
    events["event_id"] = events["metric"].map(lambda metric: _event_id(fund_id, metric))
    events["due_date"] = events["status"].map(
        {
            "BREACH": as_of_date + pd.offsets.BDay(1),
            "WATCH": as_of_date + pd.offsets.BDay(5),
        }
    )
    events["evidence"] = events.apply(
        lambda row: f"value={row['value']:.4f}, warning={row['warning']:.4f}, limit={row['limit']:.4f}",
        axis=1,
    )
    return events[["event_id", "priority", "metric", "status", "owner", "due_date", "recommended_action", "evidence"]]


def build_history_snapshot(kri_summary: pd.DataFrame, fund_id: str, as_of_date: pd.Timestamp) -> pd.DataFrame:
    history = kri_summary[["metric", "category", "value", "warning", "limit", "status"]].copy()
    history.insert(0, "fund_id", fund_id)
    history.insert(1, "as_of_date", as_of_date.strftime("%Y-%m-%d"))
    history.insert(2, "run_timestamp", pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC"))
    return history


def build_data_quality(
    positions: pd.DataFrame,
    returns: pd.DataFrame,
    nav: float,
    as_of_date: pd.Timestamp,
) -> pd.DataFrame:
    today = pd.Timestamp.today().normalize()
    returns_start = pd.Timestamp(returns.index.min())
    returns_end = pd.Timestamp(returns.index.max())
    data_age_days = max((today - as_of_date.normalize()).days, 0)
    rows = [
        {
            "check": "position_data_age_days",
            "value": data_age_days,
            "status": _quality_status(data_age_days, warning=2, limit=5, comparison="<="),
            "detail": "Position file should be refreshed daily for live monitoring.",
        },
        {
            "check": "return_observation_count",
            "value": len(returns),
            "status": _quality_status(len(returns), warning=60, limit=20, comparison=">="),
            "detail": "Historical risk metrics are more stable with at least 60 observations.",
        },
        {
            "check": "returns_cover_as_of_date",
            "value": returns_end.strftime("%Y-%m-%d"),
            "status": "OK" if returns_end >= as_of_date else "BREACH",
            "detail": "Return history should include the portfolio as-of date or later.",
        },
        {
            "check": "nav_positive",
            "value": nav,
            "status": "OK" if nav > 0 else "BREACH",
            "detail": "NAV must be positive.",
        },
        {
            "check": "position_count",
            "value": len(positions),
            "status": "OK" if len(positions) > 0 else "BREACH",
            "detail": "At least one holding is required.",
        },
        {
            "check": "return_window",
            "value": f"{returns_start:%Y-%m-%d} to {returns_end:%Y-%m-%d}",
            "status": "OK",
            "detail": "Dates used for historical simulation.",
        },
    ]
    return pd.DataFrame(rows)


def update_history_file(history_path: str | Path, snapshot: pd.DataFrame) -> pd.DataFrame:
    path = Path(history_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat([existing, snapshot], ignore_index=True)
        combined = combined.drop_duplicates(subset=["fund_id", "as_of_date", "metric"], keep="last")
    else:
        combined = snapshot
    combined.to_csv(path, index=False)
    return combined


def run_monitor(
    positions_path: str | Path,
    returns_path: str | Path,
    thresholds_path: str | Path,
    history_path: str | Path | None = None,
) -> MonitorResult:
    thresholds_dict = load_thresholds(thresholds_path)
    positions = load_positions(positions_path)
    returns = load_asset_returns(returns_path)
    holdings, portfolio_returns, exposure_summary, kri_summary = calculate_kri_summary(
        positions, returns, thresholds_dict
    )

    fund_id = str(positions["fund_id"].iloc[0])
    as_of_date = pd.Timestamp(positions["as_of_date"].max())
    data_quality = build_data_quality(positions, returns, nav=float(positions["market_value"].sum()), as_of_date=as_of_date)
    breach_log = build_breach_log(kri_summary, fund_id=fund_id, as_of_date=as_of_date)
    action_plan = build_action_plan(kri_summary, fund_id=fund_id, as_of_date=as_of_date)
    snapshot = build_history_snapshot(kri_summary, fund_id=fund_id, as_of_date=as_of_date)
    history = update_history_file(history_path, snapshot) if history_path else snapshot
    thresholds = pd.DataFrame.from_dict(thresholds_dict, orient="index").reset_index(names="metric")

    return MonitorResult(
        holdings=holdings,
        returns=returns.reset_index(),
        portfolio_returns=portfolio_returns,
        data_quality=data_quality,
        exposure_summary=exposure_summary,
        kri_summary=kri_summary,
        breach_log=breach_log,
        action_plan=action_plan,
        history=history,
        thresholds=thresholds,
        nav=float(positions["market_value"].sum()),
        as_of_date=as_of_date,
    )


def _status(value: float, warning: float, limit: float, comparison: str) -> str:
    if comparison == "<=":
        if value > limit:
            return "BREACH"
        if value > warning:
            return "WATCH"
        return "OK"
    if comparison == ">=":
        if value < limit:
            return "BREACH"
        if value < warning:
            return "WATCH"
        return "OK"
    raise ValueError(f"Unsupported comparison operator: {comparison}")


def _quality_status(value: float, warning: float, limit: float, comparison: str) -> str:
    return _status(float(value), float(warning), float(limit), comparison)


def _event_id(fund_id: str, metric: str) -> str:
    clean_fund = fund_id.replace(" ", "_").upper()
    clean_metric = metric.replace(" ", "_").upper()
    return f"{clean_fund}-{clean_metric}"


def _owner(metric: str) -> str:
    owners = {
        "var_95_1d": "Market Risk",
        "max_drawdown": "Market Risk",
        "volatility_20d": "Market Risk",
        "stress_equity_down_10": "Market Risk",
        "concentration": "Portfolio Manager",
        "top5_concentration": "Portfolio Manager",
        "largest_asset_class": "Portfolio Manager",
        "liquidity_ratio": "Liquidity Risk",
        "stressed_liquidity_ratio": "Liquidity Risk",
        "illiquid_ratio": "Liquidity Risk",
        "credit_exposure": "Credit Risk",
        "leverage": "Investment Risk",
        "derivative_exposure": "Derivatives Risk",
    }
    return owners.get(metric, "Risk Management")


def _recommended_action(metric: str) -> str:
    actions = {
        "var_95_1d": "Review market risk drivers and consider hedge or exposure reduction.",
        "concentration": "Escalate issuer concentration and review diversification plan.",
        "top5_concentration": "Check top holdings and document whether concentration is intentional.",
        "largest_asset_class": "Review asset allocation against mandate and rebalance if needed.",
        "liquidity_ratio": "Review redemption coverage and prepare liquidity action plan.",
        "stressed_liquidity_ratio": "Validate sale capacity, raise cash buffer, and identify assets to sell first.",
        "illiquid_ratio": "Assess gating/redemption terms and avoid adding illiquid exposure.",
        "max_drawdown": "Investigate performance drivers and confirm risk appetite alignment.",
        "volatility_20d": "Review recent volatility drivers and update PM risk discussion.",
        "stress_equity_down_10": "Run hedge/reduction scenario for listed equity exposure.",
        "credit_exposure": "Review issuer watchlist, rating trend, spreads, and default-risk concentration.",
        "leverage": "Review gross exposure, derivatives add-ons, and leverage cap remediation.",
        "derivative_exposure": "Check derivative notional, collateral, counterparty, and margin buffer.",
    }
    return actions.get(metric, "Review breach with portfolio manager and document remediation.")
