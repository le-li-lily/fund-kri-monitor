from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fund_kri_monitor.alerts import write_alert_summary
from fund_kri_monitor.kri import run_monitor
from fund_kri_monitor.report import write_excel_report
from fund_kri_monitor.storage import persist_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute fund KRI metrics and generate an Excel breach report.")
    parser.add_argument("--positions", default="data/portfolio_positions.csv", help="Path to portfolio positions CSV.")
    parser.add_argument("--returns", default="data/asset_returns.csv", help="Path to asset return history CSV.")
    parser.add_argument("--thresholds", default="config/thresholds.json", help="Path to KRI threshold JSON.")
    parser.add_argument("--output", default="outputs/fund_kri_report.xlsx", help="Path to output Excel report.")
    parser.add_argument("--history", default="outputs/kri_history.csv", help="Path to persistent KRI trend CSV.")
    parser.add_argument("--db", default="outputs/risk_monitor.db", help="Path to SQLite monitoring database.")
    parser.add_argument("--alert-output", default="outputs/latest_alert.md", help="Path to generated alert summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = PROJECT_ROOT
    positions_path = _resolve(base_dir, args.positions)
    returns_path = _resolve(base_dir, args.returns)
    thresholds_path = _resolve(base_dir, args.thresholds)
    output_path = _resolve(base_dir, args.output)
    history_path = _resolve(base_dir, args.history)
    db_path = _resolve(base_dir, args.db)
    alert_path = _resolve(base_dir, args.alert_output)

    result = run_monitor(
        positions_path=positions_path,
        returns_path=returns_path,
        thresholds_path=thresholds_path,
        history_path=history_path,
    )
    report_path = write_excel_report(result, output_path)
    persistence = persist_result(result, db_path=db_path, report_path=report_path)
    alert_output = write_alert_summary(result, alert_path, persistence=persistence)

    breach_count = int((result.kri_summary["status"] == "BREACH").sum())
    watch_count = int((result.kri_summary["status"] == "WATCH").sum())
    data_quality_issues = result.data_quality.loc[result.data_quality["status"].isin(["WATCH", "BREACH"])]
    print(f"Report written: {report_path}")
    print(f"History updated: {history_path}")
    print(f"Database updated: {persistence.db_path}")
    print(f"Alert summary written: {alert_output}")
    print(f"Run ID: {persistence.run_id}")
    print(f"NAV: {result.nav:,.0f}")
    print(f"KRI breaches: {breach_count}")
    print(f"KRI watch items: {watch_count}")
    print(
        "Risk events: "
        f"{persistence.inserted_events} new, {persistence.updated_events} updated, "
        f"{persistence.cleared_events} auto-cleared, "
        f"{persistence.pending_closure_events} pending manual closure"
    )
    if persistence.superseded_rows:
        print(
            f"Superseded {persistence.superseded_rows} detail row(s) from an earlier run "
            f"of the same fund and as-of date."
        )
    if persistence.pending_closure_events:
        print(
            "Events in PENDING_CLOSURE are owned by a person and will not auto-close. "
            "Close them with: python manage_events.py set-state --event-id <id> --state CLOSED --comment '<rationale>'"
        )
    print(f"Data quality issues: {len(data_quality_issues)}")
    if not data_quality_issues.empty:
        print("Data quality alerts:")
        for row in data_quality_issues.itertuples(index=False):
            print(f"- [{row.status}] {row.check}: {row.value} ({row.detail})")
    if breach_count or watch_count:
        print("Open risk events:")
        for row in result.action_plan.itertuples(index=False):
            print(f"- [{row.status}] {row.metric}: {row.recommended_action} Owner={row.owner}, Due={row.due_date:%Y-%m-%d}")


def _resolve(base_dir: Path, path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else base_dir / candidate


if __name__ == "__main__":
    main()
