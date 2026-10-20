from __future__ import annotations

import getpass
import os
import socket
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .kri import MonitorResult

STATE_NEW = "NEW"
STATE_OPEN = "OPEN"
STATE_ACKNOWLEDGED = "ACKNOWLEDGED"
STATE_INVESTIGATING = "INVESTIGATING"
STATE_ACTION_PROPOSED = "ACTION_PROPOSED"
STATE_APPROVED = "APPROVED"
STATE_PENDING_CLOSURE = "PENDING_CLOSURE"
STATE_CLOSED = "CLOSED"
STATE_CLEARED = "CLEARED"
STATE_REOPENED = "REOPENED"

# States a human has taken ownership of. A metric returning to OK must never
# auto-close these: the remediation they represent is tracked independently of
# whether the underlying number happens to have moved back inside its limit.
HUMAN_OWNED_STATES = frozenset(
    {STATE_ACKNOWLEDGED, STATE_INVESTIGATING, STATE_ACTION_PROPOSED, STATE_APPROVED}
)
TERMINAL_STATES = frozenset({STATE_CLOSED, STATE_CLEARED})

MANUAL_TRANSITIONS: dict[str, frozenset[str]] = {
    STATE_NEW: frozenset({STATE_OPEN, STATE_ACKNOWLEDGED}),
    STATE_OPEN: frozenset({STATE_ACKNOWLEDGED}),
    STATE_ACKNOWLEDGED: frozenset({STATE_INVESTIGATING, STATE_ACTION_PROPOSED}),
    STATE_INVESTIGATING: frozenset({STATE_ACTION_PROPOSED}),
    STATE_ACTION_PROPOSED: frozenset({STATE_APPROVED, STATE_INVESTIGATING}),
    STATE_APPROVED: frozenset({STATE_CLOSED}),
    STATE_REOPENED: frozenset({STATE_ACKNOWLEDGED, STATE_INVESTIGATING}),
    STATE_PENDING_CLOSURE: frozenset({STATE_CLOSED, STATE_INVESTIGATING}),
    STATE_CLEARED: frozenset(),
    STATE_CLOSED: frozenset(),
}

ALL_STATES = frozenset(MANUAL_TRANSITIONS) | {STATE_PENDING_CLOSURE}

DETAIL_TABLES = {
    "kri_results": ("fund_id", "as_of_date", "metric"),
    "data_quality_results": ("fund_id", "as_of_date", "check_name"),
    "holdings_snapshots": ("fund_id", "as_of_date", "asset_id"),
}


class TransitionError(ValueError):
    """Raised when a lifecycle transition is not permitted."""


@dataclass(frozen=True)
class PersistenceSummary:
    db_path: Path
    run_id: str
    inserted_events: int
    updated_events: int
    cleared_events: int
    pending_closure_events: int
    superseded_rows: int


def resolve_actor() -> str:
    """Identity of the operating-system account performing the change.

    Deliberately not caller-supplied: a free-text actor lets anyone record a
    change under any name, which makes the audit trail worthless as evidence.
    """
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER") or "unknown"


def persist_result(
    result: MonitorResult,
    db_path: str | Path,
    report_path: str | Path | None = None,
) -> PersistenceSummary:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fund_id = str(result.holdings["fund_id"].iloc[0])
    as_of_date = result.as_of_date.strftime("%Y-%m-%d")
    run_timestamp = _now()
    run_id = f"{fund_id}-{as_of_date}-{pd.Timestamp.now(tz='UTC').strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    with closing(sqlite3.connect(path)) as conn:
        _init_schema(conn)
        superseded = _supersede_previous_runs(conn, fund_id, as_of_date, run_id, run_timestamp)
        _insert_run(conn, result, run_id, fund_id, as_of_date, run_timestamp, report_path)
        _append_dataframe(conn, "kri_results", _with_run_columns(result.kri_summary, run_id, fund_id, as_of_date))
        _append_dataframe(conn, "data_quality_results", _with_run_columns(result.data_quality, run_id, fund_id, as_of_date))
        _append_dataframe(conn, "holdings_snapshots", _with_run_columns(result.holdings, run_id, fund_id, as_of_date))
        counts = _upsert_risk_events(conn, result, run_id, fund_id, as_of_date, run_timestamp)
        conn.commit()

    return PersistenceSummary(
        db_path=path,
        run_id=run_id,
        inserted_events=counts["inserted"],
        updated_events=counts["updated"],
        cleared_events=counts["cleared"],
        pending_closure_events=counts["pending_closure"],
        superseded_rows=superseded,
    )


def update_event_state(
    db_path: str | Path,
    event_id: str,
    state: str,
    comment: str,
    actor: str | None = None,
    on_behalf_of: str | None = None,
) -> str:
    target = state.upper()
    if target not in ALL_STATES:
        raise ValueError(f"Unsupported event state: {state}. Use one of {sorted(ALL_STATES)}.")
    if not comment or not comment.strip():
        raise ValueError("A non-empty comment is required: every state change must record its rationale.")

    acting_user = actor or resolve_actor()
    timestamp = _now()

    with closing(sqlite3.connect(db_path)) as conn:
        _init_schema(conn)
        row = conn.execute(
            "SELECT current_state FROM risk_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Unknown event_id: {event_id}")
        current = row[0]
        _assert_manual_transition(current, target)
        if target == STATE_APPROVED:
            _assert_four_eyes(conn, event_id, acting_user)

        closed = timestamp if target in TERMINAL_STATES else None
        conn.execute(
            """
            UPDATE risk_events
               SET current_state = ?, updated_at = ?,
                   closed_at = CASE WHEN ? IS NULL THEN closed_at ELSE ? END
             WHERE event_id = ?
            """,
            (target, timestamp, closed, closed, event_id),
        )
        _insert_audit(
            conn,
            event_id=event_id,
            run_id=None,
            action="MANUAL_STATE_CHANGE",
            actor=acting_user,
            comment=comment.strip(),
            from_state=current,
            to_state=target,
            on_behalf_of=on_behalf_of,
        )
        conn.commit()
    return current


def read_open_events(db_path: str | Path) -> pd.DataFrame:
    with closing(sqlite3.connect(db_path)) as conn:
        _init_schema(conn)
        return pd.read_sql_query(
            """
            SELECT event_id, fund_id, metric, status, current_state, owner, due_date,
                   observed_value, warning, limit_value, first_seen, last_seen, recommended_action
              FROM risk_events
             WHERE current_state NOT IN (?, ?)
             ORDER BY CASE status WHEN 'BREACH' THEN 1 WHEN 'WATCH' THEN 2 ELSE 3 END, due_date
            """,
            conn,
            params=(STATE_CLOSED, STATE_CLEARED),
        )


def read_event_audit(db_path: str | Path, event_id: str) -> pd.DataFrame:
    with closing(sqlite3.connect(db_path)) as conn:
        _init_schema(conn)
        return pd.read_sql_query(
            """
            SELECT created_at, action, actor, on_behalf_of, from_state, to_state, comment, run_id
              FROM event_audit_log
             WHERE event_id = ?
             ORDER BY audit_id
            """,
            conn,
            params=(event_id,),
        )


def _assert_manual_transition(current: str, target: str) -> None:
    allowed = MANUAL_TRANSITIONS.get(current)
    if allowed is None:
        raise TransitionError(
            f"Event is in state {current}, which does not permit manual changes."
        )
    if target not in allowed:
        permitted = ", ".join(sorted(allowed)) if allowed else "none"
        raise TransitionError(
            f"Transition {current} -> {target} is not permitted. Allowed from {current}: {permitted}."
        )


def _assert_four_eyes(conn: sqlite3.Connection, event_id: str, approver: str) -> None:
    row = conn.execute(
        """
        SELECT actor FROM event_audit_log
         WHERE event_id = ? AND to_state = ?
         ORDER BY audit_id DESC LIMIT 1
        """,
        (event_id, STATE_ACTION_PROPOSED),
    ).fetchone()
    if row and row[0] == approver:
        raise TransitionError(
            f"Four-eyes control: {approver} proposed the action and cannot also approve it."
        )


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS monitor_runs (
            run_id TEXT PRIMARY KEY,
            fund_id TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            run_timestamp TEXT NOT NULL,
            nav REAL NOT NULL,
            report_path TEXT,
            breach_count INTEGER NOT NULL,
            watch_count INTEGER NOT NULL,
            data_quality_issue_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS kri_results (
            run_id TEXT NOT NULL,
            fund_id TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            metric TEXT NOT NULL,
            category TEXT,
            value REAL,
            warning REAL,
            limit_value REAL,
            comparison TEXT,
            status TEXT,
            owner TEXT,
            recommended_action TEXT,
            description TEXT,
            format TEXT
        );

        CREATE TABLE IF NOT EXISTS data_quality_results (
            run_id TEXT NOT NULL,
            fund_id TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            check_name TEXT,
            value TEXT,
            status TEXT,
            detail TEXT
        );

        CREATE TABLE IF NOT EXISTS holdings_snapshots (
            run_id TEXT NOT NULL,
            fund_id TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            asset_id TEXT,
            asset_name TEXT,
            asset_class TEXT,
            market_value REAL,
            exposure_multiplier REAL,
            adv_30d REAL,
            liquidity_days REAL,
            weight REAL,
            absolute_weight REAL,
            gross_exposure REAL,
            liquid_within_5d INTEGER,
            days_to_liquid_by_adv REAL,
            five_day_liquidity_value REAL,
            stressed_liquidity_value REAL
        );

        CREATE TABLE IF NOT EXISTS risk_events (
            event_id TEXT PRIMARY KEY,
            fund_id TEXT NOT NULL,
            metric TEXT NOT NULL,
            status TEXT NOT NULL,
            severity TEXT NOT NULL,
            current_state TEXT NOT NULL,
            owner TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            due_date TEXT,
            observed_value REAL,
            warning REAL,
            limit_value REAL,
            recommended_action TEXT,
            evidence TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            closed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS event_audit_log (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            run_id TEXT,
            action TEXT NOT NULL,
            actor TEXT NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    _add_missing_columns(conn, "monitor_runs", {"superseded_by_run_id": "TEXT", "superseded_at": "TEXT"})
    _add_missing_columns(
        conn,
        "event_audit_log",
        {"from_state": "TEXT", "to_state": "TEXT", "on_behalf_of": "TEXT", "os_user": "TEXT", "hostname": "TEXT"},
    )
    _enforce_detail_uniqueness(conn)


def _add_missing_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, sql_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def _enforce_detail_uniqueness(conn: sqlite3.Connection) -> None:
    for table, key in DETAIL_TABLES.items():
        index_name = f"ux_{table}"
        columns = ", ".join(key)
        try:
            conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})")
        except sqlite3.IntegrityError:
            # Legacy database written before reruns were idempotent: collapse each
            # key group to its most recently inserted row, then enforce the index.
            conn.execute(
                f"DELETE FROM {table} WHERE rowid NOT IN "
                f"(SELECT MAX(rowid) FROM {table} GROUP BY {columns})"
            )
            conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})")


def _supersede_previous_runs(
    conn: sqlite3.Connection,
    fund_id: str,
    as_of_date: str,
    new_run_id: str,
    timestamp: str,
) -> int:
    removed = 0
    for table in DETAIL_TABLES:
        cursor = conn.execute(
            f"DELETE FROM {table} WHERE fund_id = ? AND as_of_date = ?", (fund_id, as_of_date)
        )
        removed += max(cursor.rowcount, 0)
    conn.execute(
        """
        UPDATE monitor_runs
           SET superseded_by_run_id = ?, superseded_at = ?
         WHERE fund_id = ? AND as_of_date = ? AND superseded_by_run_id IS NULL
        """,
        (new_run_id, timestamp, fund_id, as_of_date),
    )
    return removed


def _insert_run(
    conn: sqlite3.Connection,
    result: MonitorResult,
    run_id: str,
    fund_id: str,
    as_of_date: str,
    run_timestamp: str,
    report_path: str | Path | None,
) -> None:
    breach_count = int((result.kri_summary["status"] == "BREACH").sum())
    watch_count = int((result.kri_summary["status"] == "WATCH").sum())
    dq_count = int(result.data_quality["status"].isin(["WATCH", "BREACH"]).sum())
    conn.execute(
        """
        INSERT INTO monitor_runs (
            run_id, fund_id, as_of_date, run_timestamp, nav, report_path,
            breach_count, watch_count, data_quality_issue_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            fund_id,
            as_of_date,
            run_timestamp,
            float(result.nav),
            str(report_path) if report_path else None,
            breach_count,
            watch_count,
            dq_count,
        ),
    )


def _with_run_columns(df: pd.DataFrame, run_id: str, fund_id: str, as_of_date: str) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "run_id", run_id)
    if "fund_id" in out.columns:
        out["fund_id"] = fund_id
    else:
        out.insert(1, "fund_id", fund_id)
    if "as_of_date" in out.columns:
        out["as_of_date"] = as_of_date
    else:
        out.insert(2, "as_of_date", as_of_date)
    return out


def _append_dataframe(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> None:
    out = df.copy()
    out = out.rename(columns={"limit": "limit_value", "check": "check_name"})
    for column in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[column]):
            out[column] = out[column].dt.strftime("%Y-%m-%d")
        else:
            out[column] = out[column].map(_sqlite_value)
    out.to_sql(table, conn, if_exists="append", index=False)


def _upsert_risk_events(
    conn: sqlite3.Connection,
    result: MonitorResult,
    run_id: str,
    fund_id: str,
    as_of_date: str,
    timestamp: str,
) -> dict[str, int]:
    inserted = 0
    updated = 0
    current_events = result.action_plan.copy()
    current_event_ids = set(current_events["event_id"].tolist()) if not current_events.empty else set()

    if not current_events.empty:
        metrics = result.kri_summary.set_index("metric")
        for row in current_events.itertuples(index=False):
            metric_row = metrics.loc[row.metric]
            existing = conn.execute(
                "SELECT current_state FROM risk_events WHERE event_id = ?", (row.event_id,)
            ).fetchone()
            severity = "HIGH" if row.status == "BREACH" else "MEDIUM"
            due_date = pd.Timestamp(row.due_date).strftime("%Y-%m-%d")
            if existing:
                previous_state = existing[0]
                next_state = _state_on_rebreach(previous_state)
                conn.execute(
                    """
                    UPDATE risk_events
                       SET status = ?, severity = ?, current_state = ?, owner = ?, last_seen = ?,
                           as_of_date = ?, due_date = ?, observed_value = ?, warning = ?,
                           limit_value = ?, recommended_action = ?, evidence = ?, updated_at = ?,
                           closed_at = NULL
                     WHERE event_id = ?
                    """,
                    (
                        row.status,
                        severity,
                        next_state,
                        row.owner,
                        timestamp,
                        as_of_date,
                        due_date,
                        float(metric_row["value"]),
                        float(metric_row["warning"]),
                        float(metric_row["limit"]),
                        row.recommended_action,
                        row.evidence,
                        timestamp,
                        row.event_id,
                    ),
                )
                action = "EVENT_REOPENED" if next_state == STATE_REOPENED else "EVENT_UPDATED"
                comment = (
                    f"{row.status} re-detected after closure" if next_state == STATE_REOPENED
                    else f"{row.status} still active"
                )
                _insert_audit(
                    conn, row.event_id, run_id, action, "system", comment,
                    from_state=previous_state, to_state=next_state,
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO risk_events (
                        event_id, fund_id, metric, status, severity, current_state, owner,
                        first_seen, last_seen, as_of_date, due_date, observed_value, warning,
                        limit_value, recommended_action, evidence, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row.event_id,
                        fund_id,
                        row.metric,
                        row.status,
                        severity,
                        STATE_NEW,
                        row.owner,
                        timestamp,
                        timestamp,
                        as_of_date,
                        due_date,
                        float(metric_row["value"]),
                        float(metric_row["warning"]),
                        float(metric_row["limit"]),
                        row.recommended_action,
                        row.evidence,
                        timestamp,
                        timestamp,
                    ),
                )
                _insert_audit(
                    conn, row.event_id, run_id, "EVENT_CREATED", "system", f"{row.status} detected",
                    from_state=None, to_state=STATE_NEW,
                )
                inserted += 1

    resolved = _resolve_absent_events(conn, run_id, current_event_ids, timestamp)
    return {"inserted": inserted, "updated": updated, **resolved}


def _state_on_rebreach(previous_state: str) -> str:
    if previous_state in TERMINAL_STATES or previous_state == STATE_PENDING_CLOSURE:
        return STATE_REOPENED
    if previous_state == STATE_NEW:
        return STATE_OPEN
    return previous_state


def _resolve_absent_events(
    conn: sqlite3.Connection,
    run_id: str,
    current_event_ids: set[str],
    timestamp: str,
) -> dict[str, int]:
    rows = conn.execute(
        "SELECT event_id, current_state FROM risk_events WHERE current_state NOT IN (?, ?, ?)",
        (STATE_CLOSED, STATE_CLEARED, STATE_PENDING_CLOSURE),
    ).fetchall()
    cleared = 0
    pending = 0
    for event_id, state in rows:
        if event_id in current_event_ids:
            continue
        if state in HUMAN_OWNED_STATES:
            conn.execute(
                """
                UPDATE risk_events
                   SET status = 'OK', current_state = ?, updated_at = ?
                 WHERE event_id = ?
                """,
                (STATE_PENDING_CLOSURE, timestamp, event_id),
            )
            _insert_audit(
                conn, event_id, run_id, "EVENT_PENDING_CLOSURE", "system",
                "Metric returned to OK while remediation was owned by a user; "
                "explicit sign-off required before closure.",
                from_state=state, to_state=STATE_PENDING_CLOSURE,
            )
            pending += 1
        else:
            conn.execute(
                """
                UPDATE risk_events
                   SET status = 'OK', current_state = ?, updated_at = ?, closed_at = ?
                 WHERE event_id = ?
                """,
                (STATE_CLEARED, timestamp, timestamp, event_id),
            )
            _insert_audit(
                conn, event_id, run_id, "EVENT_CLEARED", "system", "Metric returned to OK",
                from_state=state, to_state=STATE_CLEARED,
            )
            cleared += 1
    return {"cleared": cleared, "pending_closure": pending}


def _insert_audit(
    conn: sqlite3.Connection,
    event_id: str,
    run_id: str | None,
    action: str,
    actor: str,
    comment: str,
    from_state: str | None = None,
    to_state: str | None = None,
    on_behalf_of: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO event_audit_log (
            event_id, run_id, action, actor, comment, created_at,
            from_state, to_state, on_behalf_of, os_user, hostname
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            run_id,
            action,
            actor,
            comment,
            _now(),
            from_state,
            to_state,
            on_behalf_of,
            resolve_actor(),
            socket.gethostname(),
        ),
    )


def _now() -> str:
    return pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S UTC")


def _sqlite_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if value == float("inf") or value == float("-inf"):
        return None
    return value
