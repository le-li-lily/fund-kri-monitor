# Fund KRI Monitoring Project - Supervisor Brief

## 1. Executive Summary

This project is a Python-based fund risk monitoring prototype designed to simulate a daily risk management workflow for an investment fund. It monitors key risk indicators across market risk, liquidity risk, concentration risk, credit exposure, leverage, derivatives exposure, and data quality.

The system has been upgraded from a simple Excel reporting script into a production-style MVP with:

- Automated KRI calculation
- Warning and breach classification
- Data quality controls
- Excel risk report generation
- Persistent historical tracking
- SQLite-based risk event lifecycle management
- Audit log for manual event updates
- Markdown alert summary for email or Teams/Slack distribution
- Scheduler wrapper for future automation

The objective is to demonstrate how daily fund risk monitoring can move from static reporting to an active, traceable, and auditable risk control process.

## 2. Business Purpose

The monitoring process is designed to answer four practical risk management questions:

1. Is the fund currently within its risk appetite and limits?
2. Are there early warning signals before a hard breach occurs?
3. Who owns each risk issue and what action is required?
4. Can we prove historically when an issue was detected, updated, escalated, and closed?

This is important because fund risk monitoring should not only produce reports. It should support timely escalation, documented remediation, and clear accountability.

## 3. Scope of Current Prototype

The prototype currently monitors the following indicators:

| Risk Area | Indicators |
|---|---|
| Market Risk | 1-day 95% historical VaR, max drawdown, annualised 20-day volatility |
| Stress Testing | Estimated loss under 10% listed-equity shock |
| Concentration | Largest holding concentration, top five concentration, largest asset class exposure |
| Liquidity | 5-day liquidity ratio, stressed 5-day liquidity ratio, illiquid asset ratio |
| Credit | Credit exposure as percentage of gross NAV |
| Leverage | Gross leverage |
| Derivatives | Derivative gross exposure |
| Data Quality | Position data freshness, return history coverage, return observation count, NAV positivity |

Each KRI is classified as:

- `OK`: within normal operating range
- `WATCH`: early warning threshold triggered
- `BREACH`: hard limit breached

## 4. Current System Workflow

The daily workflow is:

1. Load fund holdings from `data/portfolio_positions.csv`.
2. Load historical returns from `data/asset_returns.csv`.
3. Validate input data quality.
4. Calculate KRI metrics.
5. Compare results against configurable thresholds in `config/thresholds.json`.
6. Generate Excel report.
7. Persist results to SQLite database.
8. Update or create risk events.
9. Generate alert summary.
10. Allow risk users to acknowledge, investigate, approve, or close events through CLI.

## 5. Key Outputs

The system produces the following outputs:

| Output | Purpose |
|---|---|
| `outputs/fund_kri_report.xlsx` | Formal Excel report for risk review or committee pack |
| `outputs/kri_history.csv` | Flat-file historical KRI trend log |
| `outputs/risk_monitor.db` | SQLite database containing runs, KRIs, events, and audit trail |
| `outputs/latest_alert.md` | Email/Teams-ready summary of current alerts |
| `outputs/last_scheduler_stdout.log` | Scheduler run log |
| `outputs/last_scheduler_stderr.log` | Scheduler error log |

The Excel workbook contains:

- KRI Summary
- Data Quality
- Breach Log
- Action Plan
- Exposure Summary
- Holdings
- Portfolio Returns
- Thresholds
- Trend History

## 6. Exception Lifecycle

The project includes a simple risk event lifecycle. Each KRI event receives a stable event ID, for example:

```text
KRI_FUND-CONCENTRATION
```

This ensures repeated daily breaches update the same event rather than creating duplicated issues.

Supported lifecycle states:

```text
NEW -> OPEN -> ACKNOWLEDGED -> INVESTIGATING -> ACTION_PROPOSED -> APPROVED -> CLOSED
```

Example command:

```bash
python manage_events.py set-state \
  --event-id KRI_FUND-CONCENTRATION \
  --state ACKNOWLEDGED \
  --actor risk_analyst \
  --comment "PM contacted; remediation plan requested."
```

All manual state changes are saved in the `event_audit_log` table.

## 7. Current Demonstration Result

Using the sample portfolio, the latest run produced:

| Item | Result |
|---|---:|
| NAV | 10,000,000 |
| KRI Breaches | 2 |
| KRI Watch Items | 3 |
| Data Quality Issues | 2 |

Open risk events include:

- Concentration breach
- Top five concentration breach
- Largest asset class watch item
- Max drawdown watch item
- Equity stress loss watch item

Data quality alerts include:

- Position data is stale because the sample file uses `2024-12-31` as the as-of date.
- Return history has only 21 observations, which is acceptable for demonstration but too short for production-quality VaR and volatility analysis.

## 8. Production Readiness Assessment

The current project is a strong MVP, but not yet a fully production-grade risk platform.

| Area | Current Status | Production Enhancement Needed |
|---|---|---|
| Data Source | CSV sample files | Connect to fund accounting, OMS, market data, and reference data systems |
| Storage | SQLite | PostgreSQL or enterprise database |
| Alerts | Markdown alert file | SMTP, Teams, Slack, or workflow notification integration |
| Scheduling | Python scheduler wrapper | Cron, Airflow, Prefect, Control-M, or enterprise scheduler |
| Exception Workflow | CLI-based lifecycle | Web dashboard with permissions and approvals |
| Audit Trail | SQLite audit log | Controlled access, immutable logs, maker-checker workflow |
| Risk Models | Simplified historical and stress calculations | Approved VaR, factor model, liquidity model, derivative Greeks, model validation |
| Access Control | Local file-based | User authentication and role-based permissions |

## 9. Recommended Next Steps

Recommended implementation roadmap:

### Phase 1: Controlled Internal Pilot

- Replace sample CSVs with daily fund accounting exports.
- Keep SQLite for initial pilot.
- Review generated Excel and alert summary with Risk and PM teams.
- Confirm threshold calibration.
- Add real owner mapping by fund and metric.

### Phase 2: Operationalization

- Add automated scheduled run.
- Add email or Teams notification.
- Store reports in a controlled shared folder.
- Add daily run success/failure monitoring.
- Add exception aging and overdue escalation.

### Phase 3: Production Architecture

- Move storage from SQLite to PostgreSQL.
- Add web dashboard for event management.
- Add user permissions and approval workflow.
- Connect official data feeds.
- Add model validation and VaR backtesting.

### Phase 4: Advanced Risk Coverage

- Add issuer-level and counterparty-level aggregation.
- Add credit rating migration monitoring.
- Add liquidity stress scenarios by redemption assumption.
- Add derivative Greeks and collateral monitoring.
- Add benchmark-relative risk metrics such as tracking error and beta.

## 10. Conclusion

This prototype demonstrates a practical and scalable approach to fund risk monitoring. It already covers the core daily control loop:

```text
Data -> Validation -> KRI Calculation -> Threshold Check -> Alert -> Event Tracking -> Audit Trail
```

The main value is that risk issues are no longer only reported. They are converted into trackable events with owners, due dates, lifecycle states, and audit history.

With integration to official data sources, scheduled execution, and a formal approval interface, this project can evolve into a lightweight but effective production risk monitoring tool.
