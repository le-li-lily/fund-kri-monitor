"""Exception lifecycle governance.

The defects these tests lock down were all reproducible in the original code:
an event a risk analyst was actively investigating could be closed by the next
scheduled run, any state could jump to any other state, approvals could be
self-granted, and a state change could be recorded with no rationale and under
any name the caller typed.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from fund_kri_monitor.storage import (
    HUMAN_OWNED_STATES,
    STATE_ACKNOWLEDGED,
    STATE_ACTION_PROPOSED,
    STATE_APPROVED,
    STATE_CLEARED,
    STATE_CLOSED,
    STATE_INVESTIGATING,
    STATE_NEW,
    STATE_OPEN,
    STATE_PENDING_CLOSURE,
    STATE_REOPENED,
    TransitionError,
    persist_result,
    read_event_audit,
    read_open_events,
    resolve_actor,
    update_event_state,
)

BREACH_EVENT = "KRI_FUND-CONCENTRATION"


def _state(db_path, event_id: str) -> str:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT current_state FROM risk_events WHERE event_id = ?", (event_id,)
        ).fetchone()[0]


def _closed_at(db_path, event_id: str):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT closed_at FROM risk_events WHERE event_id = ?", (event_id,)
        ).fetchone()[0]


def _resolved_result(monitor_result):
    """The same result with every breach removed, i.e. all metrics back to OK."""
    return monitor_result.__class__(
        **{
            **{f: getattr(monitor_result, f) for f in monitor_result.__dataclass_fields__},
            "action_plan": monitor_result.action_plan.iloc[0:0],
        }
    )


@pytest.fixture
def seeded_db(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    return db_path


# --- detection -------------------------------------------------------------

def test_new_breach_creates_an_event_in_new_state(seeded_db):
    assert _state(seeded_db, BREACH_EVENT) == STATE_NEW


def test_event_ids_are_stable_across_runs(monitor_result, db_path):
    first = persist_result(monitor_result, db_path=db_path)
    second = persist_result(monitor_result, db_path=db_path)
    assert first.inserted_events > 0
    assert second.inserted_events == 0
    assert second.updated_events == first.inserted_events


def test_second_run_advances_new_to_open(monitor_result, db_path):
    persist_result(monitor_result, db_path=db_path)
    persist_result(monitor_result, db_path=db_path)
    assert _state(db_path, BREACH_EVENT) == STATE_OPEN


# --- the headline defect ---------------------------------------------------

def test_an_event_under_human_investigation_is_not_auto_closed(monitor_result, seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "PM contacted")
    update_event_state(seeded_db, BREACH_EVENT, STATE_INVESTIGATING, "reviewing issuer limits")

    summary = persist_result(_resolved_result(monitor_result), db_path=seeded_db)

    assert _state(seeded_db, BREACH_EVENT) == STATE_PENDING_CLOSURE
    assert summary.pending_closure_events >= 1
    assert _closed_at(seeded_db, BREACH_EVENT) is None, "an unsigned-off event must not carry a closure timestamp"


def test_a_system_owned_event_still_auto_clears(monitor_result, seeded_db):
    assert _state(seeded_db, BREACH_EVENT) == STATE_NEW
    summary = persist_result(_resolved_result(monitor_result), db_path=seeded_db)
    assert _state(seeded_db, BREACH_EVENT) == STATE_CLEARED
    assert summary.cleared_events >= 1
    assert summary.pending_closure_events == 0


@pytest.mark.parametrize("state", sorted(HUMAN_OWNED_STATES))
def test_every_human_owned_state_is_protected_from_auto_closure(monitor_result, seeded_db, state):
    path = {
        STATE_ACKNOWLEDGED: [(STATE_ACKNOWLEDGED, "acknowledged")],
        STATE_INVESTIGATING: [(STATE_ACKNOWLEDGED, "ack"), (STATE_INVESTIGATING, "investigating")],
        STATE_ACTION_PROPOSED: [
            (STATE_ACKNOWLEDGED, "ack"),
            (STATE_INVESTIGATING, "investigating"),
            (STATE_ACTION_PROPOSED, "trim proposed"),
        ],
        STATE_APPROVED: [
            (STATE_ACKNOWLEDGED, "ack"),
            (STATE_INVESTIGATING, "investigating"),
            (STATE_ACTION_PROPOSED, "trim proposed"),
            (STATE_APPROVED, "approved"),
        ],
    }[state]
    for target, comment in path:
        actor = "head_of_risk" if target == STATE_APPROVED else None
        update_event_state(seeded_db, BREACH_EVENT, target, comment, actor=actor)
    assert _state(seeded_db, BREACH_EVENT) == state

    persist_result(_resolved_result(monitor_result), db_path=seeded_db)
    assert _state(seeded_db, BREACH_EVENT) == STATE_PENDING_CLOSURE


def test_pending_closure_requires_an_explicit_human_sign_off(monitor_result, seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack")
    update_event_state(seeded_db, BREACH_EVENT, STATE_INVESTIGATING, "investigating")
    persist_result(_resolved_result(monitor_result), db_path=seeded_db)

    update_event_state(seeded_db, BREACH_EVENT, STATE_CLOSED, "verified resolved, signed off")
    assert _state(seeded_db, BREACH_EVENT) == STATE_CLOSED
    assert _closed_at(seeded_db, BREACH_EVENT) is not None


def test_a_breach_recurring_while_pending_closure_reopens_the_event(monitor_result, seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack")
    persist_result(_resolved_result(monitor_result), db_path=seeded_db)
    assert _state(seeded_db, BREACH_EVENT) == STATE_PENDING_CLOSURE

    persist_result(monitor_result, db_path=seeded_db)
    assert _state(seeded_db, BREACH_EVENT) == STATE_REOPENED


def test_a_breach_recurring_after_closure_reopens_the_event(monitor_result, seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack")
    update_event_state(seeded_db, BREACH_EVENT, STATE_INVESTIGATING, "investigating")
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACTION_PROPOSED, "trim to 9%")
    update_event_state(seeded_db, BREACH_EVENT, STATE_APPROVED, "approved", actor="head_of_risk")
    update_event_state(seeded_db, BREACH_EVENT, STATE_CLOSED, "closed", actor="head_of_risk")

    persist_result(monitor_result, db_path=seeded_db)
    assert _state(seeded_db, BREACH_EVENT) == STATE_REOPENED
    assert _closed_at(seeded_db, BREACH_EVENT) is None


def test_an_ongoing_breach_does_not_reset_a_human_state(monitor_result, seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack")
    update_event_state(seeded_db, BREACH_EVENT, STATE_INVESTIGATING, "investigating")
    persist_result(monitor_result, db_path=seeded_db)
    assert _state(seeded_db, BREACH_EVENT) == STATE_INVESTIGATING


# --- state machine ---------------------------------------------------------

@pytest.mark.parametrize(
    "target",
    [STATE_APPROVED, STATE_CLOSED, STATE_ACTION_PROPOSED, STATE_INVESTIGATING],
)
def test_illegal_jumps_from_new_are_rejected(seeded_db, target):
    with pytest.raises(TransitionError):
        update_event_state(seeded_db, BREACH_EVENT, target, "skipping the workflow")
    assert _state(seeded_db, BREACH_EVENT) == STATE_NEW


def test_a_closed_event_cannot_be_moved_backwards(seeded_db):
    for target, comment, actor in [
        (STATE_ACKNOWLEDGED, "ack", None),
        (STATE_INVESTIGATING, "investigating", None),
        (STATE_ACTION_PROPOSED, "proposed", None),
        (STATE_APPROVED, "approved", "head_of_risk"),
        (STATE_CLOSED, "closed", "head_of_risk"),
    ]:
        update_event_state(seeded_db, BREACH_EVENT, target, comment, actor=actor)

    with pytest.raises(TransitionError, match="not permitted"):
        update_event_state(seeded_db, BREACH_EVENT, STATE_APPROVED, "reopen by stealth")
    assert _state(seeded_db, BREACH_EVENT) == STATE_CLOSED


def test_a_cleared_event_cannot_be_manually_edited(monitor_result, seeded_db):
    persist_result(_resolved_result(monitor_result), db_path=seeded_db)
    assert _state(seeded_db, BREACH_EVENT) == STATE_CLEARED
    with pytest.raises(TransitionError):
        update_event_state(seeded_db, BREACH_EVENT, STATE_INVESTIGATING, "reopen manually")


def test_an_unknown_state_is_rejected(seeded_db):
    with pytest.raises(ValueError, match="Unsupported event state"):
        update_event_state(seeded_db, BREACH_EVENT, "RESOLVED_ISH", "made-up state")


def test_an_unknown_event_is_rejected(seeded_db):
    with pytest.raises(ValueError, match="Unknown event_id"):
        update_event_state(seeded_db, "KRI_FUND-DOES_NOT_EXIST", STATE_ACKNOWLEDGED, "ack")


def test_state_is_case_insensitive(seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, "acknowledged", "lower case input")
    assert _state(seeded_db, BREACH_EVENT) == STATE_ACKNOWLEDGED


# --- four eyes and audit evidence -----------------------------------------

def test_the_proposer_cannot_approve_their_own_action(seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack", actor="analyst")
    update_event_state(seeded_db, BREACH_EVENT, STATE_INVESTIGATING, "investigating", actor="analyst")
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACTION_PROPOSED, "trim to 9%", actor="analyst")

    with pytest.raises(TransitionError, match="Four-eyes"):
        update_event_state(seeded_db, BREACH_EVENT, STATE_APPROVED, "self approval", actor="analyst")
    assert _state(seeded_db, BREACH_EVENT) == STATE_ACTION_PROPOSED

    update_event_state(seeded_db, BREACH_EVENT, STATE_APPROVED, "reviewed", actor="head_of_risk")
    assert _state(seeded_db, BREACH_EVENT) == STATE_APPROVED


@pytest.mark.parametrize("comment", ["", "   ", "\n\t"])
def test_a_state_change_without_a_rationale_is_rejected(seeded_db, comment):
    with pytest.raises(ValueError, match="non-empty comment"):
        update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, comment)
    assert _state(seeded_db, BREACH_EVENT) == STATE_NEW


def test_the_actor_defaults_to_the_operating_system_identity(seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack")
    trail = read_event_audit(seeded_db, BREACH_EVENT)
    manual = trail[trail["action"] == "MANUAL_STATE_CHANGE"].iloc[-1]
    assert manual["actor"] == resolve_actor()


def test_the_audit_trail_records_both_ends_of_every_transition(seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack")
    update_event_state(seeded_db, BREACH_EVENT, STATE_INVESTIGATING, "investigating")
    trail = read_event_audit(seeded_db, BREACH_EVENT)
    manual = trail[trail["action"] == "MANUAL_STATE_CHANGE"]
    assert list(manual["from_state"]) == [STATE_NEW, STATE_ACKNOWLEDGED]
    assert list(manual["to_state"]) == [STATE_ACKNOWLEDGED, STATE_INVESTIGATING]
    assert list(manual["comment"]) == ["ack", "investigating"]


def test_an_instruction_from_another_person_is_attributed_to_both(seeded_db):
    update_event_state(
        seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "logged for the CRO", on_behalf_of="cro"
    )
    trail = read_event_audit(seeded_db, BREACH_EVENT)
    manual = trail[trail["action"] == "MANUAL_STATE_CHANGE"].iloc[-1]
    assert manual["actor"] == resolve_actor()
    assert manual["on_behalf_of"] == "cro"


def test_rejected_transitions_leave_no_audit_entry(seeded_db):
    before = len(read_event_audit(seeded_db, BREACH_EVENT))
    with pytest.raises(TransitionError):
        update_event_state(seeded_db, BREACH_EVENT, STATE_CLOSED, "straight to closed")
    assert len(read_event_audit(seeded_db, BREACH_EVENT)) == before


def test_system_actions_are_recorded_against_the_run(seeded_db):
    trail = read_event_audit(seeded_db, BREACH_EVENT)
    created = trail[trail["action"] == "EVENT_CREATED"].iloc[0]
    assert created["actor"] == "system"
    assert created["run_id"]


def test_update_event_state_returns_the_previous_state(seeded_db):
    assert update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack") == STATE_NEW


# --- reporting view --------------------------------------------------------

def test_open_events_view_excludes_terminal_states(monitor_result, seeded_db):
    persist_result(_resolved_result(monitor_result), db_path=seeded_db)
    events = read_open_events(seeded_db)
    assert STATE_CLEARED not in set(events["current_state"])
    assert STATE_CLOSED not in set(events["current_state"])


def test_pending_closure_events_remain_visible_to_the_risk_team(monitor_result, seeded_db):
    update_event_state(seeded_db, BREACH_EVENT, STATE_ACKNOWLEDGED, "ack")
    persist_result(_resolved_result(monitor_result), db_path=seeded_db)
    events = read_open_events(seeded_db)
    assert BREACH_EVENT in set(events["event_id"])
    assert events.set_index("event_id").loc[BREACH_EVENT, "current_state"] == STATE_PENDING_CLOSURE
