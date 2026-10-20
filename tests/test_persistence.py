"""Persistence must be idempotent.

Rerunning the monitor for the same fund and as-of date is routine: a data fix
arrives, someone reruns, the scheduler retries. Before the fix each rerun
appended a second copy of every row, so a trend chart built from the database
double-counted the day. These tests pin the corrected behaviour.
"""

from __future__ import annotations

import sqlite3

import pytest

from fund_kri_monitor.storage import persist_result


def _count(db_path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_first_run_writes_one_row_per_metric(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    assert _count(db_path, "kri_results") == len(monitor_result.kri_summary)
    assert _count(db_path, "data_quality_results") == len(monitor_result.data_quality)
    assert _count(db_path, "holdings_snapshots") == len(monitor_result.holdings)


def test_rerunning_the_same_day_does_not_duplicate_detail_rows(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    baseline = {t: _count(db_path, t) for t in ("kri_results", "data_quality_results", "holdings_snapshots")}

    for _ in range(4):
        persist_result(monitor_result, db_path=db_path)

    for table, expected in baseline.items():
        assert _count(db_path, table) == expected, f"{table} grew on rerun"


def test_rerun_reports_the_rows_it_superseded(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    second = persist_result(monitor_result, db_path=db_path)
    expected = len(monitor_result.kri_summary) + len(monitor_result.data_quality) + len(monitor_result.holdings)
    assert second.superseded_rows == expected


def test_first_run_supersedes_nothing(monitor_result, db_path):
    assert persist_result(monitor_result, db_path=db_path).superseded_rows == 0


def test_run_ids_are_unique_even_within_the_same_second(monitor_result, db_path):
    run_ids = {persist_result(monitor_result, db_path=db_path).run_id for _ in range(10)}
    assert len(run_ids) == 10


def test_every_run_is_retained_as_an_audit_record(monitor_result, db_path):
    for _ in range(3):
        persist_result(monitor_result, db_path=db_path)
    assert _count(db_path, "monitor_runs") == 3


def test_superseded_runs_are_stamped(monitor_result, db_path):
    for _ in range(3):
        persist_result(monitor_result, db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        superseded = conn.execute(
            "SELECT COUNT(*) FROM monitor_runs WHERE superseded_by_run_id IS NOT NULL"
        ).fetchone()[0]
        live = conn.execute(
            "SELECT COUNT(*) FROM monitor_runs WHERE superseded_by_run_id IS NULL"
        ).fetchone()[0]
    assert (superseded, live) == (2, 1)


def test_detail_rows_belong_to_the_surviving_run(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    latest = persist_result(monitor_result, db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        run_ids = {r[0] for r in conn.execute("SELECT DISTINCT run_id FROM kri_results")}
    assert run_ids == {latest.run_id}


def test_unique_indexes_are_installed(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        indexes = {
            row[1]
            for table in ("kri_results", "data_quality_results", "holdings_snapshots")
            for row in conn.execute(f"PRAGMA index_list({table})")
            if row[2] == 1
        }
    assert len(indexes) >= 3


def test_duplicate_detail_rows_are_rejected_at_the_database_level(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM kri_results LIMIT 1").fetchone()
        placeholders = ",".join("?" * len(row))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"INSERT INTO kri_results VALUES ({placeholders})", row)


def test_legacy_database_with_duplicates_is_deduplicated_on_upgrade(monitor_result, db_path):
    """Databases written by the pre-fix code already contain duplicates."""
    persist_result(monitor_result, db_path=db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP INDEX IF EXISTS ux_kri_results")
        conn.execute(
            "CREATE TABLE tmp AS SELECT * FROM kri_results"
        )
        conn.execute("INSERT INTO kri_results SELECT * FROM tmp")
        conn.execute("DROP TABLE tmp")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM kri_results").fetchone()[0] == 26

    persist_result(monitor_result, db_path=db_path)
    assert _count(db_path, "kri_results") == len(monitor_result.kri_summary)
