from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from typing import Any

from .shadow_transport import FileShadowTransport, ShadowTransport


UTC = timezone.utc


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


@dataclass(frozen=True)
class ShadowCommand:
    schema_version: int
    command_seq: int
    command: str
    cycle_id: str
    profile: str
    anchor: float
    step: float
    target_start_utc_ms: int
    expires_utc_ms: int


@dataclass(frozen=True)
class ShadowCoordinatorConfig:
    command_path: Path
    ack_path: Path
    state_path: Path
    target_archive_path: Path | None = None
    observe_only: bool = True
    command_ttl_ms: int = 2_000
    pair_window_ms: int = 1_000

    def __post_init__(self) -> None:
        if self.command_ttl_ms < 1:
            raise ValueError("command_ttl_ms must be positive")
        if self.pair_window_ms < 1:
            raise ValueError("pair_window_ms must be positive")


def read_shadow_command(path: Path) -> ShadowCommand:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError("Shadow command file must contain one command")
    row = rows[0]
    return ShadowCommand(
        schema_version=int(row["schema_version"]),
        command_seq=int(row["command_seq"]),
        command=row["command"],
        cycle_id=row["cycle_id"],
        profile=row["profile"],
        anchor=float(row["anchor"]),
        step=float(row["step"]),
        target_start_utc_ms=int(row["target_start_utc_ms"]),
        expires_utc_ms=int(row["expires_utc_ms"]),
    )


def _side_from_comment(comment: str) -> str:
    if comment.startswith("STR B"):
        return "buy"
    if comment.startswith("STR S"):
        return "sell"
    return ""


def _request_accepted(event: dict[str, Any]) -> bool:
    return int(event.get("retcode") or 0) in {
        0,
        10008,
        10009,
        10010,
    }


def load_probe_events(
    root: Path,
    *,
    minimum_sequence: int = 0,
    expected_session_id: str = "",
) -> list[dict[str, Any]]:
    transaction_paths = list(root.glob("transactions-*.csv"))
    session_root = root
    if not transaction_paths:
        grouped: dict[Path, list[Path]] = {}
        for path in root.glob("**/transactions-*.csv"):
            grouped.setdefault(path.parent, []).append(path)
        if not grouped:
            return []
        session_root = max(
            grouped,
            key=lambda path: (
                max(item.stat().st_mtime_ns for item in grouped[path]),
                path.name,
            ),
        )
        transaction_paths = grouped[session_root]
    session_id = session_root.name
    effective_minimum = (
        minimum_sequence
        if not expected_session_id or expected_session_id == session_id
        else 0
    )
    events: list[dict[str, Any]] = []
    for path in sorted(transaction_paths):
        try:
            handle = path.open(
                encoding="utf-8",
                errors="ignore",
                newline="",
            )
        except OSError:
            continue
        with handle:
            for row in csv.DictReader(handle):
                try:
                    sequence = int(row.get("sequence") or 0)
                    time_utc = str(row.get("utc_time") or "")
                    _parse_time(time_utc)
                except (TypeError, ValueError):
                    continue
                if sequence <= effective_minimum:
                    continue
                kind = str(row.get("event_kind") or "")
                if not kind:
                    continue
                comment = str(
                    row.get("entity_comment")
                    or row.get("request_comment")
                    or ""
                )
                price_key = (
                    "request_sl"
                    if kind == "stop_request"
                    else "request_price"
                )
                try:
                    event = {
                        "session_id": session_id,
                        "sequence": sequence,
                        "time_utc": time_utc,
                        "kind": kind,
                        "comment": comment,
                        "side": _side_from_comment(comment),
                        "volume": float(
                            row.get("request_volume") or 0.0
                        ),
                        "price": float(row.get(price_key) or 0.0),
                        "sl": float(row.get("request_sl") or 0.0),
                        "tp": float(row.get("request_tp") or 0.0),
                        "request_id": int(
                            row.get("result_request_id") or 0
                        ),
                        "retcode": int(
                            row.get("result_retcode") or 0
                        ),
                        "evidence_grade": "FORMAL",
                        "order_ticket": int(
                            row.get("trans_order") or 0
                        ),
                        "position_ticket": int(
                            row.get("trans_position")
                            or row.get("request_position")
                            or 0
                        ),
                        "deal_ticket": int(
                            row.get("trans_deal") or 0
                        ),
                    }
                    if kind in {"fill", "stop_exit", "close_fill"}:
                        event.update(
                            {
                                "volume": float(
                                    row.get("trans_volume") or 0.0
                                ),
                                "price": float(
                                    row.get("trans_price") or 0.0
                                ),
                                "ticket": int(
                                    row.get("trans_position")
                                    or row.get("request_position")
                                    or 0
                                ),
                                "deal": int(row.get("trans_deal") or 0),
                                "commission": float(
                                    row.get("deal_commission") or 0.0
                                ),
                                "swap": float(
                                    row.get("deal_swap") or 0.0
                                ),
                                "profit": float(
                                    row.get("deal_profit") or 0.0
                                ),
                            }
                        )
                except (TypeError, ValueError):
                    continue
                events.append(event)
    return sorted(events, key=lambda event: int(event["sequence"]))


class ShadowCoordinator:
    def __init__(
        self,
        config: ShadowCoordinatorConfig,
        transport: ShadowTransport | None = None,
    ) -> None:
        self.config = config
        self.transport = transport or FileShadowTransport(
            config.command_path,
            config.ack_path,
        )
        self._state = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        acknowledgement = self.transport.read_ack()
        acknowledged_sequence = max(
            0,
            int(acknowledgement["command_seq"]),
        )
        return {
            "schema_version": 1,
            "target_session_id": "",
            "last_target_sequence": 0,
            "last_target_time_utc": "",
            "last_command_seq": acknowledged_sequence,
            "current_cycle_id": "",
            "b1": None,
            "s1": None,
            "prestart_events": [],
            "reset_sent": False,
            "pending_reset_command_seq": 0,
            "skipped_cycles": 0,
            "sequence_gaps": 0,
            "session_restarts": 0,
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.config.state_path.exists():
            return self._default_state()
        payload = json.loads(
            self.config.state_path.read_text(encoding="utf-8")
        )
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

    def _archive_events(
        self,
        events: list[dict[str, Any]],
        cycle_id: str,
    ) -> None:
        path = self.config.target_archive_path
        if path is None or not events:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(
                    json.dumps(
                        {**event, "cycle_id": cycle_id},
                        sort_keys=True,
                    )
                    + "\n"
                )

    def _new_command(
        self,
        *,
        command: str,
        now: datetime,
        cycle_id: str = "",
        anchor: float = 0.0,
        step: float = 0.0,
        target_start: datetime | None = None,
    ) -> ShadowCommand:
        sequence = int(self._state["last_command_seq"]) + 1
        start = target_start or now
        return ShadowCommand(
            schema_version=1,
            command_seq=sequence,
            command=command,
            cycle_id=cycle_id,
            profile="LATEST_30",
            anchor=anchor,
            step=step,
            target_start_utc_ms=_epoch_ms(start),
            expires_utc_ms=_epoch_ms(
                now + timedelta(milliseconds=self.config.command_ttl_ms)
            ),
        )

    def _emit(
        self,
        command: ShadowCommand,
        result: dict[str, int],
    ) -> None:
        result["commands_observed"] += 1
        if self.config.observe_only:
            return
        self.transport.write_command(asdict(command))
        self._state["last_command_seq"] = command.command_seq
        result["commands_written"] += 1

    def _maybe_start(
        self,
        *,
        now: datetime,
        result: dict[str, int],
    ) -> str | None:
        b1 = self._state.get("b1")
        s1 = self._state.get("s1")
        if not isinstance(b1, dict) or not isinstance(s1, dict):
            return None
        b1_time = _parse_time(b1["time_utc"])
        s1_time = _parse_time(s1["time_utc"])
        pair_delta_ms = abs(_epoch_ms(s1_time) - _epoch_ms(b1_time))
        arrival_age_ms = abs(
            _epoch_ms(now) - max(_epoch_ms(b1_time), _epoch_ms(s1_time))
        )
        if (
            pair_delta_ms > self.config.pair_window_ms
            or arrival_age_ms > self.config.pair_window_ms
        ):
            self._state["skipped_cycles"] += 1
            result["skipped_cycles"] += 1
            self._state["b1"] = None
            self._state["s1"] = None
            self._state["prestart_events"] = []
            return None
        ack = self.transport.read_ack()
        expected_reset = int(
            self._state.get("pending_reset_command_seq") or 0
        )
        stale_ack = (
            not self.config.observe_only
            and expected_reset > 0
            and int(ack["command_seq"]) != expected_reset
        )
        if ack["status"] != "FLAT" or stale_ack:
            self._state["skipped_cycles"] += 1
            result["skipped_cycles"] += 1
            self._state["b1"] = None
            self._state["s1"] = None
            self._state["prestart_events"] = []
            return None

        start = min(b1_time, s1_time)
        cycle_id = (
            start.strftime("%Y%m%dT%H%M%S")
            + f"{int(start.microsecond / 1000):03d}Z"
            + f"-{max(int(b1['sequence']), int(s1['sequence']))}"
        )
        buy_price = float(b1["price"])
        sell_price = float(s1["price"])
        command = self._new_command(
            command="START",
            now=now,
            cycle_id=cycle_id,
            anchor=round((buy_price + sell_price) / 2.0, 10),
            step=round((buy_price - sell_price) / 2.0, 10),
            target_start=start,
        )
        self._emit(command, result)
        self._state["current_cycle_id"] = cycle_id
        self._state["reset_sent"] = False
        self._state["pending_reset_command_seq"] = 0
        self._state["b1"] = None
        self._state["s1"] = None
        prestart_events = self._state.get("prestart_events")
        archived_start = (
            prestart_events
            if isinstance(prestart_events, list) and prestart_events
            else [b1, s1]
        )
        self._state["prestart_events"] = []
        self._archive_events(
            sorted(
                archived_start,
                key=lambda event: int(event.get("sequence") or 0),
            ),
            cycle_id,
        )
        return cycle_id

    def _accept_event_cursor(
        self,
        event: dict[str, Any],
        result: dict[str, int],
    ) -> bool:
        session_id = str(
            event.get("session_id")
            or self._state.get("target_session_id")
            or "legacy"
        )
        active_session = str(self._state.get("target_session_id") or "")
        if active_session != session_id:
            if active_session:
                result["session_restarts"] += 1
                self._state["session_restarts"] += 1
                cycle_id = str(
                    self._state.get("current_cycle_id") or ""
                )
                if cycle_id:
                    self._archive_events(
                        [
                            {
                                "session_id": session_id,
                                "sequence": int(
                                    event.get("sequence") or 0
                                ),
                                "time_utc": str(
                                    event.get("time_utc") or ""
                                ),
                                "kind": "cycle_invalid",
                                "comment": "",
                                "reason": "probe_session_restart",
                            }
                        ],
                        cycle_id,
                    )
                self._state["current_cycle_id"] = ""
                self._state["b1"] = None
                self._state["s1"] = None
                self._state["prestart_events"] = []
                self._state["reset_sent"] = False
                self._state["pending_reset_command_seq"] = 0
            self._state["target_session_id"] = session_id
            self._state["last_target_sequence"] = 0

        sequence = int(event.get("sequence") or 0)
        previous = int(self._state["last_target_sequence"])
        if sequence <= previous:
            return False
        gap = max(0, sequence - previous - 1)
        if gap:
            result["sequence_gaps"] += gap
            self._state["sequence_gaps"] += gap
        self._state["last_target_sequence"] = sequence
        self._state["last_target_time_utc"] = str(
            event.get("time_utc") or ""
        )
        return True

    def _mark_current_cycle_complete(
        self,
        event: dict[str, Any],
    ) -> None:
        cycle_id = str(self._state.get("current_cycle_id") or "")
        if not cycle_id:
            return
        self._archive_events(
            [
                {
                    "session_id": str(event.get("session_id") or ""),
                    "sequence": int(event.get("sequence") or 0),
                    "time_utc": str(event.get("time_utc") or ""),
                    "kind": "cycle_complete",
                    "comment": "",
                    "side": "",
                    "volume": 0.0,
                    "price": 0.0,
                    "sl": 0.0,
                    "tp": 0.0,
                    "request_id": 0,
                    "retcode": 0,
                }
            ],
            cycle_id,
        )
        self._state["current_cycle_id"] = ""

    def process_events(
        self,
        events: list[dict[str, Any]],
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        current = (now or datetime.now(tz=UTC)).astimezone(UTC)
        result = {
            "commands_written": 0,
            "commands_observed": 0,
            "skipped_cycles": 0,
            "sequence_gaps": 0,
            "session_restarts": 0,
        }
        for event in sorted(
            events,
            key=lambda item: (
                str(item.get("time_utc") or ""),
                int(item.get("sequence") or 0),
            ),
        ):
            if not self._accept_event_cursor(event, result):
                continue
            kind = str(event.get("kind") or "")
            comment = str(event.get("comment") or "")

            if (
                kind in {"cancel_request", "close_request"}
                and not self._state["reset_sent"]
            ):
                reset_command = self._new_command(
                    command="RESET",
                    now=current,
                )
                self._emit(reset_command, result)
                if not self.config.observe_only:
                    self._state[
                        "pending_reset_command_seq"
                    ] = reset_command.command_seq
                self._state["reset_sent"] = True

            is_start_level = (
                kind == "pending_request"
                and comment in {"STR B1", "STR S1"}
            )
            active_cycle_id = str(
                self._state.get("current_cycle_id") or ""
            )
            collect_start_pair = (
                is_start_level
                and (
                    not active_cycle_id
                    or bool(self._state["reset_sent"])
                )
            )
            if collect_start_pair:
                if self._state["reset_sent"]:
                    self._mark_current_cycle_complete(event)
                self._state["prestart_events"].append(event)
                if _request_accepted(event):
                    self._state[
                        "b1" if comment == "STR B1" else "s1"
                    ] = event
            else:
                if active_cycle_id:
                    self._archive_events([event], active_cycle_id)
            self._maybe_start(now=current, result=result)

        self._persist_state()
        return result

    @property
    def last_target_sequence(self) -> int:
        return int(self._state["last_target_sequence"])

    @property
    def target_session_id(self) -> str:
        return str(self._state.get("target_session_id") or "")
