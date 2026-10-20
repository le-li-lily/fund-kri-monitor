from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fund_kri_monitor.storage import (
    MANUAL_TRANSITIONS,
    TransitionError,
    read_event_audit,
    read_open_events,
    resolve_actor,
    update_event_state,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage persisted fund risk events.")
    parser.add_argument("--db", default="outputs/risk_monitor.db", help="Path to SQLite monitoring database.")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List open risk events.")

    states_parser = subparsers.add_parser("states", help="Show the permitted lifecycle transitions.")
    states_parser.set_defaults(command="states")

    audit_parser = subparsers.add_parser("audit", help="Show the full audit trail for one event.")
    audit_parser.add_argument("--event-id", required=True, help="Risk event ID.")

    update_parser = subparsers.add_parser("set-state", help="Update a risk event lifecycle state.")
    update_parser.add_argument("--event-id", required=True, help="Risk event ID, for example KRI_FUND-CONCENTRATION.")
    update_parser.add_argument(
        "--state",
        required=True,
        choices=sorted(MANUAL_TRANSITIONS),
        help="Target lifecycle state.",
    )
    update_parser.add_argument(
        "--comment",
        required=True,
        help="Audit rationale for the change. Mandatory; an undocumented state change is not evidence.",
    )
    update_parser.add_argument(
        "--on-behalf-of",
        default=None,
        help="Record that the change was instructed by another person. The acting identity remains the OS account.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = _resolve(PROJECT_ROOT, args.db)

    if args.command == "list":
        events = read_open_events(db_path)
        if events.empty:
            print("No open risk events.")
            return 0
        for row in events.itertuples(index=False):
            print(
                f"{row.event_id} | {row.status}/{row.current_state} | owner={row.owner} | "
                f"due={row.due_date} | value={row.observed_value:.4f} | action={row.recommended_action}"
            )
        return 0

    if args.command == "states":
        for state in sorted(MANUAL_TRANSITIONS):
            allowed = MANUAL_TRANSITIONS[state]
            targets = ", ".join(sorted(allowed)) if allowed else "(terminal - no manual transition)"
            print(f"{state:<16} -> {targets}")
        return 0

    if args.command == "audit":
        trail = read_event_audit(db_path, args.event_id)
        if trail.empty:
            print(f"No audit entries for {args.event_id}.")
            return 0
        for row in trail.itertuples(index=False):
            on_behalf = f" on behalf of {row.on_behalf_of}" if row.on_behalf_of else ""
            print(
                f"{row.created_at} | {row.action} | {row.from_state or '-'} -> {row.to_state or '-'} | "
                f"{row.actor}{on_behalf} | {row.comment or ''}"
            )
        return 0

    if args.command == "set-state":
        try:
            previous = update_event_state(
                db_path=db_path,
                event_id=args.event_id,
                state=args.state,
                comment=args.comment,
                on_behalf_of=args.on_behalf_of,
            )
        except (TransitionError, ValueError) as exc:
            print(f"Rejected: {exc}", file=sys.stderr)
            return 1
        print(f"{args.event_id}: {previous} -> {args.state.upper()} by {resolve_actor()}.")
        return 0

    return 0


def _resolve(base_dir: Path, path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else base_dir / candidate


if __name__ == "__main__":
    raise SystemExit(main())
