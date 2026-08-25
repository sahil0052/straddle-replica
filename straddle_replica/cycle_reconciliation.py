from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


UTC = timezone.utc


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _history_time(time_msc: object, offset_seconds: int) -> datetime:
    milliseconds = int(time_msc or 0)
    if milliseconds <= 0:
        raise ValueError("History record is missing a valid millisecond time.")
    return datetime.fromtimestamp(milliseconds / 1000.0, tz=UTC) - timedelta(
        seconds=offset_seconds
    )


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds")


def _position_ticket(event: dict[str, Any]) -> int:
    return int(event.get("position_ticket") or event.get("ticket") or 0)


def _public_copy(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in event.items()
        if not key.startswith("_")
    }


def _record_provenance(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_path": str(event.get("_source_path") or ""),
        "source_line": int(event.get("_source_line") or 0),
    }


def _matching_history_record(
    record: dict[str, Any],
    *,
    expected_magic: int,
    expected_symbol: str,
) -> bool:
    return (
        int(record.get("magic") or 0) == expected_magic
        and str(record.get("symbol") or "") == expected_symbol
    )


def reconcile_cycle_events(
    *,
    raw_events: list[dict[str, Any]],
    history_deals: list[dict[str, Any]],
    history_orders: list[dict[str, Any]],
    cycle_id: str,
    history_server_offset_seconds: int,
    expected_magic: int,
    expected_symbol: str,
) -> dict[str, Any]:
    cycle_events = [
        event
        for event in raw_events
        if str(event.get("cycle_id") or "") == cycle_id
    ]
    if not cycle_events:
        raise ValueError(f"Cycle was not found in the raw archive: {cycle_id}")

    starts = [event for event in cycle_events if event.get("kind") == "cycle_start"]
    completes = [
        event for event in cycle_events if event.get("kind") == "cycle_complete"
    ]
    if len(starts) != 1 or len(completes) != 1:
        raise ValueError(
            "Reconciliation requires exactly one cycle_start and cycle_complete."
        )
    cycle_start = _parse_time(starts[0]["time_utc"])
    cycle_complete = _parse_time(completes[0]["time_utc"])
    if cycle_complete <= cycle_start:
        raise ValueError("Cycle completion must be after cycle start.")

    fills: dict[int, dict[str, Any]] = {}
    for event in cycle_events:
        if event.get("kind") != "fill":
            continue
        position_ticket = _position_ticket(event)
        if position_ticket <= 0:
            raise ValueError("Fill event is missing a position ticket.")
        if position_ticket in fills:
            raise ValueError(
                f"Duplicate fill position ticket in cycle: {position_ticket}"
            )
        fills[position_ticket] = event

    existing_exit_positions = {
        _position_ticket(event)
        for event in cycle_events
        if event.get("kind") in {"stop_exit", "close_fill"}
    }
    existing_exit_positions.discard(0)
    unexpected_exits = existing_exit_positions - fills.keys()
    if unexpected_exits:
        raise ValueError(
            "Exit events without cycle fills: "
            + ", ".join(str(ticket) for ticket in sorted(unexpected_exits))
        )

    missing_positions = set(fills) - existing_exit_positions
    close_deals_by_position: dict[int, list[dict[str, Any]]] = {}
    for deal in history_deals:
        if not _matching_history_record(
            deal,
            expected_magic=expected_magic,
            expected_symbol=expected_symbol,
        ):
            continue
        if int(deal.get("entry") or 0) != 1:
            continue
        if str(deal.get("comment") or "") != "STR CLOSE":
            continue
        position_ticket = int(deal.get("position_id") or 0)
        if position_ticket not in missing_positions:
            continue
        deal_time = _history_time(
            deal.get("time_msc"),
            history_server_offset_seconds,
        )
        if not cycle_start <= deal_time <= cycle_complete:
            continue
        close_deals_by_position.setdefault(position_ticket, []).append(deal)

    orders_by_ticket = {
        int(order.get("ticket") or 0): order
        for order in history_orders
        if _matching_history_record(
            order,
            expected_magic=expected_magic,
            expected_symbol=expected_symbol,
        )
    }

    recovered_events: list[dict[str, Any]] = []
    recovered_deal_tickets: list[int] = []
    for position_ticket in sorted(missing_positions):
        candidates = close_deals_by_position.get(position_ticket, [])
        if len(candidates) != 1:
            raise ValueError(
                "Expected exactly one authoritative history close deal for "
                f"position {position_ticket}, found {len(candidates)}."
            )
        deal = candidates[0]
        close_order_ticket = int(deal.get("order") or 0)
        close_order = orders_by_ticket.get(close_order_ticket)
        if (
            close_order is None
            or int(close_order.get("position_id") or 0) != position_ticket
            or str(close_order.get("comment") or "") != "STR CLOSE"
        ):
            raise ValueError(
                "Missing authoritative close order proof for position "
                f"{position_ticket}."
            )

        fill = fills[position_ticket]
        deal_time = _history_time(
            deal.get("time_msc"),
            history_server_offset_seconds,
        )
        common = {
            "cycle_id": cycle_id,
            "session_id": str(deal.get("_session_id") or "history-backfill"),
            "source_sequence": None,
            "time_utc": _format_time(deal_time),
            "comment": str(fill.get("comment") or ""),
            "side": str(fill.get("side") or ""),
            "volume": float(deal.get("volume") or fill.get("volume") or 0.0),
            "price": float(deal.get("price") or 0.0),
            "sl": 0.0,
            "tp": 0.0,
            "retcode": 0,
            "position_ticket": position_ticket,
            "order_ticket": close_order_ticket,
            "evidence_grade": "AUTHORITATIVE_HISTORY",
            "source": "history_backfill_reconciliation",
            "reconciliation_source": "authoritative_history",
            "capture_limit": (
                "originating_request_payload_unavailable_history_proves_"
                "accepted_close"
            ),
            "provenance": {
                "deal_ticket": int(deal.get("ticket") or 0),
                "deal_source_path": str(deal.get("_source_path") or ""),
                "deal_source_line": int(deal.get("_source_line") or 0),
                "order_ticket": close_order_ticket,
                "order_source_path": str(
                    close_order.get("_source_path") or ""
                ),
                "order_source_line": int(
                    close_order.get("_source_line") or 0
                ),
                "original_fill_source_sequence": int(
                    fill.get("sequence") or 0
                ),
                "original_fill_deal_ticket": int(
                    fill.get("deal_ticket") or fill.get("deal") or 0
                ),
            },
        }
        request = {
            **common,
            "kind": "close_request",
            "deal_ticket": 0,
            "deal": 0,
            "ticket": position_ticket,
            "_sort_priority": 0,
        }
        close_deal_ticket = int(deal.get("ticket") or 0)
        fill_event = {
            **common,
            "kind": "close_fill",
            "deal_ticket": close_deal_ticket,
            "deal": close_deal_ticket,
            "ticket": position_ticket,
            "request_id": 0,
            "commission": float(deal.get("commission") or 0.0),
            "swap": float(deal.get("swap") or 0.0),
            "fee": float(deal.get("fee") or 0.0),
            "profit": float(deal.get("profit") or 0.0),
            "_sort_priority": 1,
        }
        recovered_events.extend([request, fill_event])
        recovered_deal_tickets.append(close_deal_ticket)

    reconciled: list[dict[str, Any]] = []
    for index, event in enumerate(cycle_events):
        copied = _public_copy(event)
        copied["source_sequence"] = int(event.get("sequence") or 0)
        copied["reconciliation_source"] = "raw_archive"
        copied["provenance"] = _record_provenance(event)
        copied["_source_index"] = index
        copied["_sort_priority"] = 0
        reconciled.append(copied)
    for index, event in enumerate(recovered_events, start=len(cycle_events)):
        copied = deepcopy(event)
        copied["_source_index"] = index
        reconciled.append(copied)

    reconciled.sort(
        key=lambda event: (
            _parse_time(event["time_utc"]),
            int(event.get("_sort_priority") or 0),
            int(event.get("source_sequence") or 0),
            int(event.get("_source_index") or 0),
        )
    )
    for ordinal, event in enumerate(reconciled, start=1):
        event["sequence"] = ordinal
        event["reconciled_ordinal"] = ordinal
        event.pop("_sort_priority", None)
        event.pop("_source_index", None)

    counts = Counter(str(event.get("kind") or "") for event in reconciled)
    unresolved_positions = set(fills) - {
        _position_ticket(event)
        for event in reconciled
        if event.get("kind") in {"stop_exit", "close_fill"}
    }
    stop_exit_count = counts["stop_exit"]
    close_fill_count = counts["close_fill"]
    fill_count = counts["fill"]
    raw_close_fill_count = sum(
        1 for event in cycle_events if event.get("kind") == "close_fill"
    )

    return {
        "events": reconciled,
        "summary": {
            "cycle_id": cycle_id,
            "raw_event_count": len(cycle_events),
            "reconciled_event_count": len(reconciled),
            "fill_count": fill_count,
            "stop_exit_count": stop_exit_count,
            "raw_close_fill_count": raw_close_fill_count,
            "recovered_close_request_count": len(recovered_deal_tickets),
            "recovered_close_fill_count": len(recovered_deal_tickets),
            "reconciled_close_fill_count": close_fill_count,
            "unresolved_position_tickets": sorted(unresolved_positions),
            "all_fills_resolved": (
                not unresolved_positions
                and fill_count == stop_exit_count + close_fill_count
            ),
            "lifecycle_conservation": (
                f"{fill_count} = {stop_exit_count} + {close_fill_count}"
            ),
            "recovered_deal_tickets": recovered_deal_tickets,
            "cycle_start_utc": _format_time(cycle_start),
            "cycle_complete_utc": _format_time(cycle_complete),
            "history_server_offset_seconds": history_server_offset_seconds,
        },
    }
