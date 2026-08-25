from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any


UTC = timezone.utc


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _accepted(event: dict[str, Any]) -> bool:
    return int(event.get("retcode") or 0) in {
        0,
        10008,
        10009,
        10010,
    }


@dataclass(frozen=True)
class IndependentCycleArchiveConfig:
    state_path: Path
    archive_path: Path
    pair_window_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.pair_window_seconds <= 0:
            raise ValueError("pair_window_seconds must be positive")


class IndependentCycleArchive:
    def __init__(self, config: IndependentCycleArchiveConfig) -> None:
        self.config = config
        self._state = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": "",
            "last_sequence": 0,
            "sequence_gaps": 0,
            "session_restarts": 0,
            "current_cycle_id": "",
            "last_completed_cycle_id": "",
            "pending_start": [],
            "basket_triggered": False,
        }

    def _load_state(self) -> dict[str, Any]:
        if not self.config.state_path.exists():
            return self._default_state()
        payload = json.loads(
            self.config.state_path.read_text(encoding="utf-8")
        )
        return {**self._default_state(), **payload}

    def _persist(self) -> None:
        path = self.config.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(self._state, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)

    def _append(
        self,
        event: dict[str, Any],
        cycle_id: str,
    ) -> None:
        self.config.archive_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config.archive_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {**event, "cycle_id": cycle_id},
                    sort_keys=True,
                )
                + "\n"
            )

    def _synthetic(
        self,
        source: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        return {
            "session_id": str(source.get("session_id") or ""),
            "sequence": int(source.get("sequence") or 0),
            "time_utc": str(source.get("time_utc") or ""),
            "kind": kind,
            "comment": "",
            "side": "",
            "volume": 0.0,
            "price": 0.0,
            "sl": 0.0,
            "tp": 0.0,
            "retcode": 0,
            "evidence_grade": "BEST_EFFORT",
            "source": "observer_inferred",
        }

    def _accept_cursor(self, event: dict[str, Any]) -> bool:
        session_id = str(event.get("session_id") or "legacy")
        active_session = str(self._state["session_id"])
        if active_session and active_session != session_id:
            cycle_id = str(self._state["current_cycle_id"])
            if cycle_id:
                invalid = self._synthetic(event, "cycle_invalid")
                invalid["reason"] = "observer_session_changed"
                self._append(invalid, cycle_id)
            self._state.update(
                {
                    "session_restarts": int(
                        self._state["session_restarts"]
                    )
                    + 1,
                    "last_sequence": 0,
                    "current_cycle_id": "",
                    "pending_start": [],
                    "basket_triggered": False,
                }
            )
        self._state["session_id"] = session_id
        sequence = int(event.get("sequence") or 0)
        previous = int(self._state["last_sequence"])
        if sequence <= previous:
            return False
        if previous and sequence > previous + 1:
            self._state["sequence_gaps"] = int(
                self._state["sequence_gaps"]
            ) + sequence - previous - 1
        self._state["last_sequence"] = sequence
        return True

    def _try_start(self) -> int:
        pending = list(self._state["pending_start"])
        b1 = next(
            (
                event
                for event in pending
                if event.get("comment") == "STR B1"
                and _accepted(event)
            ),
            None,
        )
        s1 = next(
            (
                event
                for event in pending
                if event.get("comment") == "STR S1"
                and _accepted(event)
            ),
            None,
        )
        if b1 is None or s1 is None:
            return 0
        first = min(
            _parse_time(b1["time_utc"]),
            _parse_time(s1["time_utc"]),
        )
        last = max(
            _parse_time(b1["time_utc"]),
            _parse_time(s1["time_utc"]),
        )
        if (
            last - first
        ).total_seconds() > self.config.pair_window_seconds:
            self._state["pending_start"] = []
            return 0
        cycle_id = (
            first.strftime("%Y%m%dT%H%M%S")
            + f"{first.microsecond // 1000:03d}Z"
            + f"-target-{max(int(b1['sequence']), int(s1['sequence']))}"
        )
        previous = str(self._state["last_completed_cycle_id"])
        if previous:
            self._append(
                self._synthetic(b1, "cycle_restart"),
                previous,
            )
        start_event = self._synthetic(b1, "cycle_start")
        start_event["price"] = (
            float(b1.get("price") or 0.0)
            + float(s1.get("price") or 0.0)
        ) / 2.0
        self._append(start_event, cycle_id)
        for event in sorted(
            pending,
            key=lambda item: (
                str(item.get("time_utc") or ""),
                int(item.get("sequence") or 0),
            ),
        ):
            self._append(event, cycle_id)
        self._state.update(
            {
                "current_cycle_id": cycle_id,
                "last_completed_cycle_id": "",
                "pending_start": [],
                "basket_triggered": False,
            }
        )
        return len(pending) + 1

    def _append_close_request(
        self,
        event: dict[str, Any],
        cycle_id: str,
    ) -> None:
        close_request = self._synthetic(event, "close_request")
        close_request.update(
            {
                "comment": str(event.get("comment") or ""),
                "side": str(event.get("side") or ""),
                "volume": float(event.get("volume") or 0.0),
                "price": float(event.get("price") or 0.0),
                "position_ticket": int(
                    event.get("position_ticket")
                    or event.get("ticket")
                    or 0
                ),
            }
        )
        self._append(close_request, cycle_id)

    def process_events(
        self,
        events: list[dict[str, Any]],
    ) -> dict[str, int]:
        archived = 0
        for event in sorted(
            events,
            key=lambda item: (
                str(item.get("time_utc") or ""),
                int(item.get("sequence") or 0),
            ),
        ):
            if not self._accept_cursor(event):
                continue
            kind = str(event.get("kind") or "")
            comment = str(event.get("comment") or "")
            cycle_id = str(self._state["current_cycle_id"])
            is_start = kind == "pending_request" and comment in {
                "STR B1",
                "STR S1",
            }
            if not cycle_id:
                if is_start:
                    self._state["pending_start"].append(event)
                    archived += self._try_start()
                continue

            if (
                kind
                in {"cancel_request", "close_request", "close_fill"}
                and not self._state["basket_triggered"]
            ):
                basket_trigger = self._synthetic(
                    event,
                    "basket_trigger",
                )
                basket_trigger.update(
                    {
                        "comparison_class": (
                            "BROKER_ACCEPTANCE_PROXY"
                        ),
                        "capture_limit": (
                            "basket_trigger_inferred_from_first_"
                            "broker_close_or_cancel"
                        ),
                    }
                )
                self._append(basket_trigger, cycle_id)
                self._state["basket_triggered"] = True
                archived += 1
            if kind == "close_fill":
                self._append_close_request(event, cycle_id)
                archived += 1
            if kind == "cancel_request" and not comment:
                self._append(
                    self._synthetic(event, "cycle_complete"),
                    cycle_id,
                )
                self._state.update(
                    {
                        "last_completed_cycle_id": cycle_id,
                        "current_cycle_id": "",
                        "pending_start": [],
                        "basket_triggered": False,
                    }
                )
                archived += 1
                continue
            self._append(event, cycle_id)
            archived += 1
        self._persist()
        return {
            "archived_events": archived,
            "sequence_gaps": int(self._state["sequence_gaps"]),
            "session_restarts": int(self._state["session_restarts"]),
        }
