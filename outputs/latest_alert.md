# Fund Risk Monitoring Alert - KRI_FUND

- As of date: 2024-12-31
- Generated: 2026-10-20 23:58:01
- NAV: 10,000,000
- KRI breaches: 2
- KRI watch items: 3
- Data quality issues: 2
- Database: outputs/risk_monitor.db
- Run ID: KRI_FUND-2024-12-31-20261020215801-df2766c3
- New events: 5
- Updated events: 0
- Auto-cleared events: 0
- Events pending manual closure: 0

## Data Quality Alerts
- **BREACH** `position_data_age_days` = `658` - Position file should be refreshed daily for live monitoring.
- **WATCH** `return_observation_count` = `21` - Historical risk metrics are more stable with at least 60 observations.

## Open Risk Events
- **BREACH/NEW** `KRI_FUND-CONCENTRATION` | owner: Portfolio Manager | due: 2025-01-01 | Escalate issuer concentration and review diversification plan.
  Evidence: value=0.2200, warning=0.1500, limit=0.2000
- **BREACH/NEW** `KRI_FUND-TOP5_CONCENTRATION` | owner: Portfolio Manager | due: 2025-01-01 | Check top holdings and document whether concentration is intentional.
  Evidence: value=0.8300, warning=0.6500, limit=0.7500
- **WATCH/NEW** `KRI_FUND-LARGEST_ASSET_CLASS` | owner: Portfolio Manager | due: 2025-01-07 | Review asset allocation against mandate and rebalance if needed.
  Evidence: value=0.5400, warning=0.4500, limit=0.5500
- **WATCH/NEW** `KRI_FUND-MAX_DRAWDOWN` | owner: Market Risk | due: 2025-01-07 | Investigate performance drivers and confirm risk appetite alignment.
  Evidence: value=0.0640, warning=0.0600, limit=0.0800
- **WATCH/NEW** `KRI_FUND-STRESS_EQUITY_DOWN_10` | owner: Market Risk | due: 2025-01-07 | Run hedge/reduction scenario for listed equity exposure.
  Evidence: value=0.0557, warning=0.0400, limit=0.0600
