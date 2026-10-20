from __future__ import annotations

from pathlib import Path

import pandas as pd

from .kri import MonitorResult
from .storage import PersistenceSummary, read_open_events


def write_alert_summary(
    result: MonitorResult,
    output_path: str | Path,
    persistence: PersistenceSummary | None = None,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fund_id = str(result.holdings["fund_id"].iloc[0])
    breach_count = int((result.kri_summary["status"] == "BREACH").sum())
    watch_count = int((result.kri_summary["status"] == "WATCH").sum())
    data_quality = result.data_quality.loc[result.data_quality["status"].isin(["WATCH", "BREACH"])]

    lines = [
        f"# Fund Risk Monitoring Alert - {fund_id}",
        "",
        f"- As of date: {result.as_of_date:%Y-%m-%d}",
        f"- Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- NAV: {result.nav:,.0f}",
        f"- KRI breaches: {breach_count}",
        f"- KRI watch items: {watch_count}",
        f"- Data quality issues: {len(data_quality)}",
    ]

    if persistence:
        lines.extend(
            [
                f"- Database: {persistence.db_path}",
                f"- Run ID: {persistence.run_id}",
                f"- New events: {persistence.inserted_events}",
                f"- Updated events: {persistence.updated_events}",
                f"- Auto-cleared events: {persistence.cleared_events}",
                f"- Events pending manual closure: {persistence.pending_closure_events}",
            ]
        )

    if not data_quality.empty:
        lines.extend(["", "## Data Quality Alerts"])
        for row in data_quality.itertuples(index=False):
            lines.append(f"- **{row.status}** `{row.check}` = `{row.value}` - {row.detail}")

    lifecycle_events = read_open_events(persistence.db_path) if persistence else pd.DataFrame()
    if not lifecycle_events.empty:
        lines.extend(["", "## Open Risk Events"])
        for row in lifecycle_events.itertuples(index=False):
            lines.append(
                f"- **{row.status}/{row.current_state}** `{row.event_id}` | owner: {row.owner} | "
                f"due: {row.due_date} | {row.recommended_action}"
            )
            lines.append(
                f"  Evidence: value={row.observed_value:.4f}, warning={row.warning:.4f}, limit={row.limit_value:.4f}"
            )
    elif not result.action_plan.empty:
        lines.extend(["", "## Open Risk Events"])
        for row in result.action_plan.itertuples(index=False):
            due_date = pd.Timestamp(row.due_date).strftime("%Y-%m-%d")
            lines.append(
                f"- **{row.status}** `{row.event_id}` | owner: {row.owner} | due: {due_date} | {row.recommended_action}"
            )
            lines.append(f"  Evidence: {row.evidence}")

    if result.action_plan.empty and data_quality.empty:
        lines.extend(["", "No open KRI or data quality alerts."])

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
