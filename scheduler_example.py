from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> int:
    command = [
        sys.executable,
        str(PROJECT_ROOT / "run_monitor.py"),
        "--positions",
        "data/portfolio_positions.csv",
        "--returns",
        "data/asset_returns.csv",
        "--thresholds",
        "config/thresholds.json",
        "--output",
        "outputs/fund_kri_report.xlsx",
        "--history",
        "outputs/kri_history.csv",
        "--db",
        "outputs/risk_monitor.db",
        "--alert-output",
        "outputs/latest_alert.md",
    ]
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    (PROJECT_ROOT / "outputs").mkdir(exist_ok=True)
    (PROJECT_ROOT / "outputs" / "last_scheduler_stdout.log").write_text(result.stdout, encoding="utf-8")
    (PROJECT_ROOT / "outputs" / "last_scheduler_stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        print("Risk monitor failed. See outputs/last_scheduler_stderr.log")
        return result.returncode
    print("Risk monitor completed. See outputs/latest_alert.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
