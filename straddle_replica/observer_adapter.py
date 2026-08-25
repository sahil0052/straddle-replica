from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping


UTC = timezone.utc
COMMENT_RE = re.compile(r"^STR ([BS])(\d+)$")


@dataclass(frozen=True)
class ObserverAdapterConfig:
    observer_root: Path
    state_path: Path
    heartbeat_max_age_seconds: float = 5.0
    flat_settlement_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.heartbeat_max_age_seconds <= 0:
            raise ValueError("heartbeat_max_age_seconds must be positive")
        if self.flat_settlement_seconds <= 0:
            raise ValueError("flat_settlement_seconds must be positive")


class ObserverEventAdapter:
    def __init__(self, config: ObserverAdapterConfig) -> None:
        self.config = config
        self._state = self._load_state()

    @property
    def state(self) -> Mapping[str, Any]:
        return self._state

    def _default_state(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": "",
            "initialized": False,
            "waiting_for_flat": False,
            "armed_for_next_cycle": False,
            "suppress_current_cycle": False,
            "flat_observed_since_utc": "",
            "pair_comments": [],
            "seen_order_tickets": [],
            "seen_position_tickets": [],
            "seen_history_order_tickets": [],
            "seen_deal_tickets": [],
            "position_comments": {},
            "position_stop_losses": {},
            "file_offsets": {},
            "next_sequence": 1,
            "history_server_offset_seconds": None,
        }

    def _load_state(self) -> dict[str, Any]:
        path = self.config.state_path
        if not path.exists():
            return self._default_state()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {**self._default_state(), **payload}

    def _persist_state(self) -> None:
        path = self.config.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._state, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _session(self) -> Path:
        pointer = self.config.observer_root / "current-session.json"
        if pointer.exists():
            payload = json.loads(pointer.read_text(encoding="utf-8"))
            session = self.config.observer_root / str(payload["session_id"])
            if session.is_dir():
                return session
        sessions = [
            path.parent
            for path in self.config.observer_root.glob("*/manifest.json")
        ]
        if not sessions:
            raise FileNotFoundError("No target observer session was found")
        return max(
            sessions,
            key=lambda path: (path / "manifest.json").stat().st_mtime_ns,
        )

    @staticmethod
    def _latest_record(paths: list[Path]) -> dict[str, Any]:
        for path in reversed(sorted(paths)):
            latest: dict[str, Any] | None = None
            with path.open(encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if not line.endswith("\n") or not line.strip():
                        continue
                    try:
                        latest = json.loads(line)
                    except json.JSONDecodeError:
                        continue
            if latest is not None:
                return latest
        raise FileNotFoundError("No complete target snapshot was found")

    @staticmethod
    def _ticket(record: Mapping[str, Any]) -> int:
        return int(
            record.get("ticket")
            or record.get("position_id")
            or record.get("identifier")
            or 0
        )

    def _initialize(self) -> None:
        session = self._session()
        history_server_offset_seconds = (
            self._read_history_server_offset_seconds(session)
        )
        snapshot = self._latest_record(
            list(session.glob("snapshots-*.jsonl"))
        )
        orders = [
            row
            for row in snapshot.get("orders", [])
            if COMMENT_RE.fullmatch(str(row.get("comment") or ""))
        ]
        positions = [
            row
            for row in snapshot.get("positions", [])
            if COMMENT_RE.fullmatch(str(row.get("comment") or ""))
        ]
        active = bool(orders or positions)
        self._state.update(
            {
                "session_id": session.name,
                "initialized": True,
                "waiting_for_flat": active,
                "armed_for_next_cycle": not active,
                "suppress_current_cycle": active,
                "flat_observed_since_utc": "",
                "pair_comments": [],
                "seen_order_tickets": sorted(
                    ticket
                    for row in orders
                    if (ticket := self._ticket(row)) > 0
                ),
                "seen_position_tickets": sorted(
                    ticket
                    for row in positions
                    if (ticket := self._ticket(row)) > 0
                ),
                "position_comments": {
                    str(ticket): str(row.get("comment") or "")
                    for row in positions
                    if (ticket := self._ticket(row)) > 0
                },
                "position_stop_losses": {
                    str(ticket): float(row.get("sl") or 0.0)
                    for row in positions
                    if (ticket := self._ticket(row)) > 0
                },
                "file_offsets": {
                    str(path.relative_to(session)): path.stat().st_size
                    for path in session.glob("*.jsonl")
                },
                "history_server_offset_seconds": (
                    history_server_offset_seconds
                ),
            }
        )
        self._persist_state()

    @staticmethod
    def _read_history_server_offset_seconds(session: Path) -> int:
        manifest_path = session / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        time_domains = manifest.get("time_domains") or {}
        try:
            offset = int(
                time_domains.get("history_server_offset_seconds") or 0
            )
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Target observer history server offset is invalid"
            ) from error
        if abs(offset) > 24 * 60 * 60:
            raise RuntimeError(
                "Target observer history server offset is invalid"
            )
        return offset

    @staticmethod
    def _parse_time(value: object) -> datetime:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _validate_heartbeat(
        self,
        session: Path,
        now: datetime,
    ) -> None:
        heartbeat_path = session / "heartbeat.json"
        payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
        if not payload.get("healthy", True) or payload.get("stopped", False):
            raise RuntimeError("Target observer heartbeat is unhealthy")
        captured = self._parse_time(payload["capture_time_utc"])
        age = (now - captured).total_seconds()
        if age < -1 or age > self.config.heartbeat_max_age_seconds:
            raise RuntimeError("Target observer heartbeat is stale")

    def _read_new_jsonl(
        self,
        session: Path,
        pattern: str,
    ) -> list[dict[str, Any]]:
        offsets = self._state["file_offsets"]
        records: list[dict[str, Any]] = []
        for path in sorted(session.glob(pattern)):
            key = str(path.relative_to(session))
            offset = int(offsets.get(key, 0))
            size = path.stat().st_size
            if offset > size:
                offset = 0
            with path.open("rb") as handle:
                handle.seek(offset)
                payload = handle.read()
            complete_bytes = (
                payload.rsplit(b"\n", 1)[0] + b"\n"
                if b"\n" in payload
                else b""
            )
            offsets[key] = offset + len(complete_bytes)
            for raw_line in complete_bytes.splitlines():
                if not raw_line.strip():
                    continue
                try:
                    records.append(
                        json.loads(raw_line.decode("utf-8", errors="ignore"))
                    )
                except json.JSONDecodeError:
                    continue
        return records

    def _next_sequence(self) -> int:
        sequence = int(self._state["next_sequence"])
        self._state["next_sequence"] = sequence + 1
        return sequence

    def _base_event(
        self,
        *,
        time_utc: str,
        kind: str,
        comment: str = "",
    ) -> dict[str, Any]:
        side = ""
        match = COMMENT_RE.fullmatch(comment)
        if match is not None:
            side = "buy" if match.group(1) == "B" else "sell"
        return {
            "session_id": (
                str(self._state["session_id"]) + "-observer"
            ),
            "sequence": 0,
            "time_utc": time_utc,
            "kind": kind,
            "comment": comment,
            "side": side,
            "volume": 0.0,
            "price": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "request_id": 0,
            "retcode": 0,
            "evidence_grade": "BEST_EFFORT",
            "deal_ticket": 0,
            "order_ticket": 0,
            "position_ticket": 0,
            "source": "observer_inferred",
            "capture_limit": "no_originating_request_payload",
        }

    def _boundary_event(self, snapshot: Mapping[str, Any]) -> dict[str, Any]:
        return self._base_event(
            time_utc=str(snapshot["capture_time_utc"]),
            kind="cancel_request",
        )

    def _flat_is_settled(self, snapshot: Mapping[str, Any]) -> bool:
        observed_since = str(
            self._state.get("flat_observed_since_utc") or ""
        )
        observed_at = self._parse_time(snapshot["capture_time_utc"])
        if not observed_since:
            self._state["flat_observed_since_utc"] = (
                observed_at.isoformat()
            )
            return False
        elapsed = (
            observed_at - self._parse_time(observed_since)
        ).total_seconds()
        if elapsed < 0:
            self._state["flat_observed_since_utc"] = (
                observed_at.isoformat()
            )
            return False
        return elapsed >= self.config.flat_settlement_seconds

    def _clear_flat_observation(self) -> None:
        self._state["flat_observed_since_utc"] = ""

    def _pending_event(
        self,
        order: Mapping[str, Any],
        snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        setup_msc = int(order.get("time_setup_msc") or 0)
        time_utc = (
            self._broker_time_utc(setup_msc / 1000.0).isoformat()
            if setup_msc > 0
            else str(snapshot["capture_time_utc"])
        )
        event = self._base_event(
            time_utc=time_utc,
            kind="pending_request",
            comment=str(order.get("comment") or ""),
        )
        event.update(
            {
                "volume": float(
                    order.get("volume_initial")
                    if order.get("volume_initial") is not None
                    else order.get("volume") or 0.0
                ),
                "price": float(order.get("price_open") or 0.0),
                "sl": float(order.get("sl") or 0.0),
                "tp": float(order.get("tp") or 0.0),
                "ticket": self._ticket(order),
                "order_ticket": self._ticket(order),
                "retcode": 10008,
            }
        )
        return event

    def _broker_time_utc(self, timestamp: float) -> datetime:
        offset = int(
            self._state.get("history_server_offset_seconds") or 0
        )
        return datetime.fromtimestamp(timestamp - offset, tz=UTC)

    def _event_time(
        self,
        record: Mapping[str, Any],
        *keys: str,
    ) -> str:
        for key in keys:
            value = int(record.get(key) or 0)
            if value > 0:
                return self._broker_time_utc(value / 1000.0).isoformat()
        value = int(record.get("time") or 0)
        if value > 0:
            return self._broker_time_utc(float(value)).isoformat()
        raise ValueError("Observer history row has no timestamp")

    def _process_history_order(
        self,
        order: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        ticket = self._ticket(order)
        seen = {
            int(value)
            for value in self._state["seen_history_order_tickets"]
        }
        if ticket <= 0 or ticket in seen:
            return None
        seen.add(ticket)
        self._state["seen_history_order_tickets"] = sorted(seen)
        comment = str(order.get("comment") or "")
        state = int(order.get("state") or 0)
        if COMMENT_RE.fullmatch(comment) is None:
            return None
        if state == 4:
            seen_active = {
                int(value) for value in self._state["seen_order_tickets"]
            }
            if ticket in seen_active:
                return None
            if (
                comment in {"STR B1", "STR S1"}
                and self._state["suppress_current_cycle"]
            ):
                return None
            try:
                time_utc = self._event_time(order, "time_setup_msc")
            except ValueError:
                return None
            event = self._base_event(
                time_utc=time_utc,
                kind="pending_request",
                comment=comment,
            )
            event["retcode"] = 10008
            event["capture_limit"] = (
                "pending_request_reconstructed_from_filled_order"
            )
            seen_active.add(ticket)
            self._state["seen_order_tickets"] = sorted(seen_active)
            if self._state["armed_for_next_cycle"] and comment in {
                "STR B1",
                "STR S1",
            }:
                pair_comments = set(self._state["pair_comments"])
                pair_comments.add(comment)
                self._state["pair_comments"] = sorted(pair_comments)
                if pair_comments == {"STR B1", "STR S1"}:
                    self._state["armed_for_next_cycle"] = False
                    self._state["waiting_for_flat"] = True
        elif state in {2, 6}:
            try:
                time_utc = self._event_time(
                    order,
                    "time_done_msc",
                    "time_setup_msc",
                )
            except ValueError:
                return None
            event = self._base_event(
                time_utc=time_utc,
                kind="cancel_request",
                comment=comment,
            )
        else:
            return None
        event.update(
            {
                "ticket": ticket,
                "order_ticket": ticket,
                "volume": float(
                    order.get("volume_initial")
                    if order.get("volume_initial") is not None
                    else order.get("volume_current") or 0.0
                ),
                "price": float(order.get("price_open") or 0.0),
                "sl": float(order.get("sl") or 0.0),
                "tp": float(order.get("tp") or 0.0),
            }
        )
        return event

    def _process_deal(
        self,
        deal: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        deal_ticket = int(deal.get("ticket") or 0)
        seen = {int(value) for value in self._state["seen_deal_tickets"]}
        if deal_ticket <= 0 or deal_ticket in seen:
            return None
        seen.add(deal_ticket)
        self._state["seen_deal_tickets"] = sorted(seen)
        position_id = int(deal.get("position_id") or 0)
        entry = int(deal.get("entry") or 0)
        raw_comment = str(deal.get("comment") or "")
        position_comments = dict(self._state["position_comments"])

        if entry == 0:
            if COMMENT_RE.fullmatch(raw_comment) is None:
                return None
            comment = raw_comment
            if position_id > 0:
                position_comments[str(position_id)] = comment
            kind = "fill"
        else:
            comment = str(position_comments.get(str(position_id)) or "")
            if not comment and COMMENT_RE.fullmatch(raw_comment):
                comment = raw_comment
            if COMMENT_RE.fullmatch(comment) is None:
                return None
            reason = int(deal.get("reason") or 0)
            is_stop = (
                reason == 4
                or raw_comment.lower().startswith("[sl")
            )
            kind = "stop_exit" if is_stop else "close_fill"
        self._state["position_comments"] = position_comments
        try:
            time_utc = self._event_time(deal, "time_msc")
        except ValueError:
            return None
        event = self._base_event(
            time_utc=time_utc,
            kind=kind,
            comment=comment,
        )
        event.update(
            {
                "ticket": position_id,
                "deal": deal_ticket,
                "deal_ticket": deal_ticket,
                "order_ticket": int(deal.get("order") or 0),
                "position_ticket": position_id,
                "volume": float(deal.get("volume") or 0.0),
                "price": float(deal.get("price") or 0.0),
                "commission": float(deal.get("commission") or 0.0),
                "swap": float(deal.get("swap") or 0.0),
                "profit": float(deal.get("profit") or 0.0),
            }
        )
        return event

    def _position_stop_events(
        self,
        positions: list[dict[str, Any]],
        snapshot: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        previous = {
            str(ticket): float(value)
            for ticket, value in dict(
                self._state.get("position_stop_losses") or {}
            ).items()
        }
        current: dict[str, float] = {}
        events: list[dict[str, Any]] = []
        for position in positions:
            ticket = self._ticket(position)
            if ticket <= 0:
                continue
            key = str(ticket)
            stop_loss = float(position.get("sl") or 0.0)
            current[key] = stop_loss
            if key not in previous:
                continue
            if abs(stop_loss - previous[key]) <= 1e-9:
                continue
            comment = str(position.get("comment") or "")
            if COMMENT_RE.fullmatch(comment) is None:
                continue
            event = self._base_event(
                time_utc=str(snapshot["capture_time_utc"]),
                kind="stop_request",
                comment=comment,
            )
            event.update(
                {
                    "ticket": ticket,
                    "position_ticket": ticket,
                    "volume": float(position.get("volume") or 0.0),
                    "price": stop_loss,
                    "sl": stop_loss,
                }
            )
            events.append(event)
        self._state["position_stop_losses"] = current
        return events

    def _process_snapshot(
        self,
        snapshot: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        orders = [
            row
            for row in snapshot.get("orders", [])
            if COMMENT_RE.fullmatch(str(row.get("comment") or ""))
        ]
        positions = [
            row
            for row in snapshot.get("positions", [])
            if COMMENT_RE.fullmatch(str(row.get("comment") or ""))
        ]
        active = bool(orders or positions)
        seen_orders = {
            int(ticket) for ticket in self._state["seen_order_tickets"]
        }
        seen_positions = {
            int(ticket) for ticket in self._state["seen_position_tickets"]
        }
        events: list[dict[str, Any]] = []

        if self._state["suppress_current_cycle"]:
            self._state["position_stop_losses"] = {
                str(ticket): float(row.get("sl") or 0.0)
                for row in positions
                if (ticket := self._ticket(row)) > 0
            }
            seen_orders.update(
                ticket
                for row in orders
                if (ticket := self._ticket(row)) > 0
            )
            seen_positions.update(
                ticket
                for row in positions
                if (ticket := self._ticket(row)) > 0
            )
            if not active and self._flat_is_settled(snapshot):
                events.append(self._boundary_event(snapshot))
                self._state["suppress_current_cycle"] = False
                self._state["waiting_for_flat"] = False
                self._state["armed_for_next_cycle"] = True
                self._state["pair_comments"] = []
                self._clear_flat_observation()
            elif active:
                self._clear_flat_observation()
        elif not active:
            self._state["position_stop_losses"] = {}
            if (
                self._state["waiting_for_flat"]
                and self._flat_is_settled(snapshot)
            ):
                events.append(self._boundary_event(snapshot))
                self._state["waiting_for_flat"] = False
                self._state["armed_for_next_cycle"] = True
                self._state["pair_comments"] = []
                self._clear_flat_observation()
        else:
            self._clear_flat_observation()
            pair_comments = set(self._state["pair_comments"])
            for order in orders:
                ticket = self._ticket(order)
                if ticket <= 0 or ticket in seen_orders:
                    continue
                seen_orders.add(ticket)
                event = self._pending_event(order, snapshot)
                events.append(event)
                if event["comment"] in {"STR B1", "STR S1"}:
                    pair_comments.add(str(event["comment"]))
            seen_positions.update(
                ticket
                for row in positions
                if (ticket := self._ticket(row)) > 0
            )
            events.extend(self._position_stop_events(positions, snapshot))
            self._state["pair_comments"] = sorted(pair_comments)
            if pair_comments == {"STR B1", "STR S1"}:
                self._state["armed_for_next_cycle"] = False
                self._state["waiting_for_flat"] = True

        self._state["seen_order_tickets"] = sorted(seen_orders)
        self._state["seen_position_tickets"] = sorted(seen_positions)
        return events

    def poll(
        self,
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        current = (now or datetime.now(tz=UTC)).astimezone(UTC)
        if not self._state["initialized"]:
            self._initialize()
            return []
        session = self._session()
        if session.name != self._state["session_id"]:
            previous_session_id = str(self._state["session_id"])
            self._validate_heartbeat(session, current)
            self._initialize()
            event = self._base_event(
                time_utc=current.isoformat(),
                kind="observer_session_start",
            )
            event.update(
                {
                    "sequence": self._next_sequence(),
                    "reason": "observer_session_changed",
                    "previous_session_id": previous_session_id,
                }
            )
            self._persist_state()
            return [event]
        self._validate_heartbeat(session, current)
        self._state["history_server_offset_seconds"] = (
            self._read_history_server_offset_seconds(session)
        )
        events: list[dict[str, Any]] = []
        for snapshot in self._read_new_jsonl(
            session,
            "snapshots-*.jsonl",
        ):
            events.extend(self._process_snapshot(snapshot))
        for order in self._read_new_jsonl(
            session,
            "history-orders-*.jsonl",
        ):
            event = self._process_history_order(order)
            if event is not None:
                events.append(event)
        for deal in self._read_new_jsonl(
            session,
            "history-deals-*.jsonl",
        ):
            event = self._process_deal(deal)
            if event is not None:
                events.append(event)
        ordered_events = sorted(
            events,
            key=lambda event: self._parse_time(event["time_utc"]),
        )
        for event in ordered_events:
            event["sequence"] = self._next_sequence()
        self._persist_state()
        return ordered_events
