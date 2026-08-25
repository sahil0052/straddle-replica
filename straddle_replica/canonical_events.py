from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping


UTC = timezone.utc
COMMENT_RE = re.compile(r"^STR ([BS])(\d+)$")
EXECUTION_KINDS = {"fill", "stop_exit", "close_fill"}


@dataclass(frozen=True)
class CanonicalizationResult:
    events: tuple[dict[str, Any], ...]
    duplicate_event_ids: tuple[str, ...]
    invalid_rows: int


def _number(row: Mapping[str, Any], *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return float(value)
    return 0.0


def _integer(row: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return int(value)
    return 0


def _level(row: Mapping[str, Any], parsed: int | None) -> int:
    value = row.get("level")
    if value in (None, ""):
        return int(parsed or 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(parsed or 0)


def _parse_comment(comment: str) -> tuple[str, int | None]:
    match = COMMENT_RE.fullmatch(comment)
    if match is None:
        return "", None
    return ("buy" if match.group(1) == "B" else "sell", int(match.group(2)))


def _time(value: object) -> str:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _fallback_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def canonicalize_event(
    row: Mapping[str, Any],
    *,
    source: str,
    evidence_grade: str,
    session_id: str,
) -> dict[str, Any]:
    kind = str(row.get("kind") or row.get("event_kind") or "")
    raw_comment = str(
        row.get("comment") or row.get("entity_comment") or ""
    )
    level_identity = str(row.get("level") or "")
    reason = str(row.get("reason") or "")
    if (
        COMMENT_RE.fullmatch(raw_comment) is None
        and COMMENT_RE.fullmatch(level_identity) is not None
    ):
        comment = level_identity
        if not reason:
            reason = raw_comment
    else:
        comment = raw_comment
    side, level = _parse_comment(comment)
    deal_ticket = _integer(row, "deal_ticket", "deal")
    legacy_ticket = _integer(row, "ticket")
    order_ticket = _integer(row, "order_ticket", "order")
    position_ticket = _integer(row, "position_ticket", "position")
    if kind in {"pending_request", "cancel_request"} and order_ticket == 0:
        order_ticket = legacy_ticket
    if kind in EXECUTION_KINDS and position_ticket == 0:
        position_ticket = legacy_ticket
    request_id = _integer(row, "request_id")
    sequence = _integer(row, "event_sequence", "sequence")
    cycle_id = str(row.get("cycle_id") or "")
    effective_session = str(row.get("session_id") or session_id)
    accepted_price = _number(
        row,
        "accepted_price",
        "price" if kind in EXECUTION_KINDS else "__missing__",
    )
    requested_price = _number(
        row,
        "requested_price",
        "price" if kind not in EXECUTION_KINDS else "__missing__",
    )
    if deal_ticket:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"deal:{deal_ticket}:{kind}"
        )
    elif request_id:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"request:{request_id}:{kind}"
        )
    elif order_ticket:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"order:{order_ticket}:{kind}"
        )
    elif sequence:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"sequence:{sequence}:{kind}"
        )
    else:
        identity = (
            f"{source}:{effective_session}:{cycle_id}:"
            f"hash:{_fallback_id(row)}"
        )
    return {
        "schema_version": 1,
        "event_id": identity,
        "source": source,
        "evidence_grade": evidence_grade,
        "session_id": effective_session,
        "cycle_id": cycle_id,
        "sequence": sequence,
        "time_utc": _time(row.get("time_utc") or row.get("utc_time")),
        "server_time": str(row.get("server_time") or ""),
        "kind": kind,
        "comment": comment,
        "reason": reason,
        "side": str(row.get("side") or side),
        "level": _level(row, level),
        "volume": _number(row, "volume"),
        "requested_price": requested_price,
        "accepted_price": accepted_price,
        "sl": _number(row, "sl"),
        "tp": _number(row, "tp"),
        "order_ticket": order_ticket,
        "position_ticket": position_ticket,
        "deal_ticket": deal_ticket,
        "request_id": request_id,
        "retcode": _integer(row, "retcode"),
        "commission": _number(row, "commission"),
        "swap": _number(row, "swap"),
        "fee": _number(row, "fee"),
        "profit": _number(row, "profit"),
        "cycle_realized": _number(row, "cycle_realized"),
        "floating_profit": _number(row, "floating_profit"),
        "cycle_net": _number(row, "cycle_net"),
        "basket_target": _number(row, "basket_target"),
    }


def canonicalize_events(
    rows: Iterable[Mapping[str, Any]],
    *,
    source: str,
    evidence_grade: str,
    session_id: str,
) -> CanonicalizationResult:
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates: set[str] = set()
    invalid = 0
    for row in rows:
        try:
            event = canonicalize_event(
                row,
                source=source,
                evidence_grade=evidence_grade,
                session_id=session_id,
            )
        except (TypeError, ValueError):
            invalid += 1
            continue
        if event["event_id"] in seen:
            duplicates.add(event["event_id"])
            continue
        seen.add(event["event_id"])
        events.append(event)
    events.sort(key=lambda event: (event["time_utc"], event["sequence"]))
    return CanonicalizationResult(
        events=tuple(events),
        duplicate_event_ids=tuple(sorted(duplicates)),
        invalid_rows=invalid,
    )
