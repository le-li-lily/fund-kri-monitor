# Fund KRI Monitor

Automated Python pipeline for fund key risk indicator monitoring. The project simulates a daily risk-management workflow: load holdings and return data, calculate KRIs, compare them with warning and hard-limit thresholds, create an action plan, persist a trend history, maintain a SQLite exception lifecycle database, and generate an Excel pack for PM/risk committee review.

## Features

- Computes practical KRIs across market, liquidity, concentration, credit, leverage, and derivatives risk:
  - 1-day 95% historical VaR
  - largest position concentration
  - top five concentration
  - largest asset class exposure
  - liquidity ratio for assets liquid within five business days
  - stressed five-day liquidity ratio
  - illiquid asset ratio
  - historical max drawdown
  - annualised 20-day volatility
  - simple equity shock stress loss
  - credit exposure
  - gross leverage
  - derivative gross exposure
- Uses configurable warning and hard-limit thresholds in `config/thresholds.json`.
- Classifies every KRI as `OK`, `WATCH`, or `BREACH`.
- Creates owner-based remediation actions with due dates.
- Checks basic data quality, including stale position data and return history coverage.
- Persists daily snapshots to `outputs/kri_history.csv`.
- Persists production-style run history and exception lifecycle to `outputs/risk_monitor.db`.
- Generates a Markdown alert summary in `outputs/latest_alert.md`.
- Provides an event-management CLI for acknowledging, investigating, approving, and closing events.
- Produces an Excel workbook with:
  - color-coded KRI status table
  - data quality checks
  - breach register, scoped to hard-limit failures only
  - watch list of early warnings still inside appetite
  - owner/action remediation tracker
  - asset-class exposure summary
  - holdings detail
  - portfolio return and drawdown history
  - trend history
  - threshold reference sheet

## Project Structure

```text
fund_kri_monitor/
  config/thresholds.json
  data/asset_returns.csv
  data/portfolio_positions.csv
  outputs/
  outputs/kri_history.csv
  outputs/risk_monitor.db
  outputs/latest_alert.md
  src/fund_kri_monitor/kri.py
  src/fund_kri_monitor/report.py
  src/fund_kri_monitor/storage.py
  src/fund_kri_monitor/alerts.py
  tests/
  run_monitor.py
  manage_events.py
  scheduler_example.py
  requirements.txt
  requirements-dev.txt
  pytest.ini
```

## Quick Start

```bash
cd fund_kri_monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_monitor.py
```

If your system Python already has `pandas`, `numpy`, and `openpyxl`, you can run `python run_monitor.py` directly.

The generated workbook is saved to:

```text
outputs/fund_kri_report.xlsx
outputs/kri_history.csv
outputs/risk_monitor.db
outputs/latest_alert.md
```

## Input Data

`data/portfolio_positions.csv` expects one row per holding:

- `fund_id`
- `as_of_date`
- `asset_id`
- `asset_name`
- `asset_class`
- `market_value`
- `exposure_multiplier`
- `adv_30d`
- `liquidity_days`

`data/asset_returns.csv` expects one date column and one return column per `asset_id`.

## Custom Run

```bash
python run_monitor.py \
  --positions data/portfolio_positions.csv \
  --returns data/asset_returns.csv \
  --thresholds config/thresholds.json \
  --output outputs/fund_kri_report.xlsx \
  --history outputs/kri_history.csv \
  --db outputs/risk_monitor.db \
  --alert-output outputs/latest_alert.md
```

## Notes

This is a practical monitoring workflow prototype. The VaR calculation uses historical simulation based on supplied asset return history and current portfolio weights. The stress test is deliberately simple so the workflow is easy to inspect; production use would replace it with official risk-model shocks, verified data feeds, fund accounting extracts, order-management feeds, approval statuses, and persistent exception lifecycle management.

## Daily Operating Workflow

1. Update `data/portfolio_positions.csv` after NAV/position close.
2. Update `data/asset_returns.csv` from market data.
3. Run `python run_monitor.py`.
4. Review console alerts for immediate `WATCH` and `BREACH` items.
5. Open `outputs/fund_kri_report.xlsx` and check `KRI Summary`, `Data Quality`, `Breach Log`, `Watch List`, and `Action Plan`.
6. Review `outputs/latest_alert.md` for a copy/paste-ready alert summary.
7. Track repeated or deteriorating issues through `outputs/kri_history.csv`, `outputs/risk_monitor.db`, or the workbook `Trend History` sheet.

## Exception Lifecycle

Each open KRI event is stored in SQLite with a stable `event_id`, such as `KRI_FUND-CONCENTRATION`. Repeated runs update the same event until the metric clears or a user closes it.

List open events:

```bash
python manage_events.py list
```

Move an event through the lifecycle:

```bash
python manage_events.py set-state \
  --event-id KRI_FUND-CONCENTRATION \
  --state ACKNOWLEDGED \
  --comment "PM contacted; remediation plan requested."
```

Show the permitted transitions, or the audit trail for one event:

```bash
python manage_events.py states
python manage_events.py audit --event-id KRI_FUND-CONCENTRATION
```

Supported states:

```text
NEW ─┬─> OPEN ──> ACKNOWLEDGED ─┬─> INVESTIGATING ──> ACTION_PROPOSED ──> APPROVED ──> CLOSED
     └─> ACKNOWLEDGED           └─> ACTION_PROPOSED

REOPENED        ──> ACKNOWLEDGED | INVESTIGATING    (breach recurred after closure)
PENDING_CLOSURE ──> CLOSED | INVESTIGATING          (metric cleared, human sign-off outstanding)
CLEARED, CLOSED ──> terminal; no manual transition
```

Three controls are enforced on every manual change:

- **Legal transitions only.** Anything outside the map above is rejected with a `TransitionError`, so an event cannot jump from `NEW` straight to `APPROVED`, and a `CLOSED` event cannot be quietly moved backwards.
- **Mandatory rationale.** `--comment` is required and must be non-empty. An undocumented state change is not evidence.
- **Identity is not caller-supplied.** The actor is resolved from the operating-system account. Use `--on-behalf-of` to record that someone else instructed the change; the acting identity still stands. Approving an action you proposed yourself is rejected by the four-eyes check.

An event that a person has taken ownership of (`ACKNOWLEDGED`, `INVESTIGATING`, `ACTION_PROPOSED`, `APPROVED`) is **never** closed automatically. If the underlying metric returns to `OK`, the run moves the event to `PENDING_CLOSURE` and leaves `closed_at` empty until a person signs it off. Only events still in a system-owned state (`NEW`, `OPEN`, `REOPENED`) auto-clear.

Audit records are saved in the SQLite `event_audit_log` table, with the previous and new state, the acting identity, the rationale, and the run that triggered any system action.

## SQLite Tables

The production-style database contains:

- `monitor_runs`: one row per monitoring run, retained permanently. A rerun of the same fund and as-of date stamps the earlier run with `superseded_by_run_id` and `superseded_at` rather than deleting it.
- `kri_results`: KRI values, unique on `(fund_id, as_of_date, metric)`.
- `data_quality_results`: data quality checks, unique on `(fund_id, as_of_date, check_name)`.
- `holdings_snapshots`: enriched holdings, unique on `(fund_id, as_of_date, asset_id)`.
- `risk_events`: current lifecycle state for each monitored event.
- `event_audit_log`: system and manual event updates, including `from_state`, `to_state`, `actor`, `on_behalf_of`, `os_user`, and `hostname`.

Reruns are idempotent. Running the monitor five times for the same as-of date leaves exactly one detail row per key, so a trend series built from the database cannot double-count a day. A database written by an earlier version that already contains duplicates is deduplicated on first use, keeping the most recently inserted row in each group.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The suite covers golden-value regression for all thirteen indicators, loader and validation edge cases (short positions, single-holding portfolios, duplicate keys, missing return series, insufficient history), persistence idempotency, and the full exception-lifecycle control set.

## Scheduling

For a simple daily batch wrapper:

```bash
python scheduler_example.py
```

For cron, an example entry would be:

```text
30 7 * * 1-5 cd /path/to/fund_kri_monitor && /path/to/python run_monitor.py
```

In Airflow or Prefect, call `run_monitor.py` as the task entry point and archive `outputs/fund_kri_report.xlsx`, `outputs/latest_alert.md`, and `outputs/risk_monitor.db`.

The sample files use historical dates for demonstration, so the `Data Quality` tab may flag stale position data when run today. Replace the sample CSVs with current daily extracts for live monitoring.
