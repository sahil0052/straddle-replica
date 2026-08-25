from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from straddle_replica.cycle_reconciliation import reconcile_cycle_events


UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
RECONCILE_TOOL = ROOT / "tools" / "reconcile_independent_cycle.py"


def _server_time_msc(utc_value: str, offset_seconds: int = 7200) -> int:
    parsed = datetime.fromisoformat(utc_value.replace("Z", "+00:00"))
    return int((parsed.timestamp() + offset_seconds) * 1000)


def _raw_event(
    sequence: int,
    time_utc: str,
    kind: str,
    *,
    comment: str = "",
    side: str = "",
    position_ticket: int = 0,
    deal_ticket: int = 0,
) -> dict[str, object]:
    return {
        "cycle_id": "cycle-1",
        "session_id": "observer-session",
        "sequence": sequence,
        "time_utc": time_utc,
        "kind": kind,
        "comment": comment,
        "side": side,
        "volume": 0.01 if comment else 0.0,
        "price": 4400.0,
        "position_ticket": position_ticket,
        "deal_ticket": deal_ticket,
        "retcode": 0,
        "_source_path": "target-cycles.jsonl",
        "_source_line": sequence,
    }


def test_reconcile_cycle_recovers_missing_history_close_with_provenance() -> None:
    raw_events = [
        _raw_event(1, "2026-08-17T10:00:00Z", "cycle_start"),
        _raw_event(
            2,
            "2026-08-17T10:00:10Z",
            "fill",
            comment="STR B1",
            side="buy",
            position_ticket=101,
            deal_ticket=1001,
        ),
        _raw_event(
            3,
            "2026-08-17T10:00:20Z",
            "fill",
            comment="STR B2",
            side="buy",
            position_ticket=102,
            deal_ticket=1002,
        ),
        _raw_event(
            4,
            "2026-08-17T10:00:30Z",
            "fill",
            comment="STR S1",
            side="sell",
            position_ticket=103,
            deal_ticket=1003,
        ),
        _raw_event(
            5,
            "2026-08-17T10:00:35Z",
            "stop_exit",
            comment="STR B1",
            side="buy",
            position_ticket=101,
            deal_ticket=2001,
        ),
        _raw_event(
            6,
            "2026-08-17T10:00:36Z",
            "close_request",
            comment="STR B2",
            side="buy",
            position_ticket=102,
        ),
        _raw_event(
            7,
            "2026-08-17T10:00:36Z",
            "close_fill",
            comment="STR B2",
            side="buy",
            position_ticket=102,
            deal_ticket=2002,
        ),
        _raw_event(8, "2026-08-17T10:01:00Z", "cycle_complete"),
        _raw_event(9, "2026-08-17T10:01:20Z", "cycle_restart"),
    ]
    history_deals = [
        {
            "ticket": 2003,
            "order": 3003,
            "position_id": 103,
            "time_msc": _server_time_msc("2026-08-17T10:00:40Z"),
            "entry": 1,
            "type": 0,
            "magic": 26011001,
            "symbol": "XAUUSD",
            "comment": "STR CLOSE",
            "volume": 0.01,
            "price": 4398.5,
            "profit": -1.25,
            "commission": 0.0,
            "swap": 0.0,
            "fee": 0.0,
            "_source_path": "history-deals.jsonl",
            "_source_line": 12,
        }
    ]
    history_orders = [
        {
            "ticket": 3003,
            "position_id": 103,
            "time_done_msc": _server_time_msc("2026-08-17T10:00:40Z"),
            "magic": 26011001,
            "symbol": "XAUUSD",
            "comment": "STR CLOSE",
            "volume_initial": 0.01,
            "_source_path": "history-orders.jsonl",
            "_source_line": 15,
        }
    ]

    result = reconcile_cycle_events(
        raw_events=raw_events,
        history_deals=history_deals,
        history_orders=history_orders,
        cycle_id="cycle-1",
        history_server_offset_seconds=7200,
        expected_magic=26011001,
        expected_symbol="XAUUSD",
    )

    assert result["summary"]["fill_count"] == 3
    assert result["summary"]["stop_exit_count"] == 1
    assert result["summary"]["raw_close_fill_count"] == 1
    assert result["summary"]["recovered_close_fill_count"] == 1
    assert result["summary"]["reconciled_close_fill_count"] == 2
    assert result["summary"]["all_fills_resolved"] is True
    assert result["summary"]["lifecycle_conservation"] == "3 = 1 + 2"

    recovered = [
        event
        for event in result["events"]
        if event.get("reconciliation_source") == "authoritative_history"
    ]
    assert [event["kind"] for event in recovered] == [
        "close_request",
        "close_fill",
    ]
    assert all(event["comment"] == "STR S1" for event in recovered)
    assert all(event["position_ticket"] == 103 for event in recovered)
    assert recovered[1]["deal_ticket"] == 2003
    assert recovered[1]["order_ticket"] == 3003
    assert recovered[1]["evidence_grade"] == "AUTHORITATIVE_HISTORY"
    assert recovered[1]["provenance"]["deal_source_line"] == 12
    assert recovered[1]["provenance"]["order_source_line"] == 15

    assert [event["sequence"] for event in result["events"]] == list(
        range(1, len(result["events"]) + 1)
    )
    raw_copies = [
        event
        for event in result["events"]
        if event.get("reconciliation_source") == "raw_archive"
    ]
    assert [event["source_sequence"] for event in raw_copies] == list(
        range(1, 10)
    )


def test_reconcile_cycle_refuses_history_close_without_order_proof() -> None:
    raw_events = [
        _raw_event(1, "2026-08-17T10:00:00Z", "cycle_start"),
        _raw_event(
            2,
            "2026-08-17T10:00:10Z",
            "fill",
            comment="STR B1",
            side="buy",
            position_ticket=101,
            deal_ticket=1001,
        ),
        _raw_event(3, "2026-08-17T10:01:00Z", "cycle_complete"),
    ]
    history_deals = [
        {
            "ticket": 2001,
            "order": 3001,
            "position_id": 101,
            "time_msc": _server_time_msc("2026-08-17T10:00:40Z"),
            "entry": 1,
            "magic": 26011001,
            "symbol": "XAUUSD",
            "comment": "STR CLOSE",
            "volume": 0.01,
            "price": 4398.5,
            "_source_path": "history-deals.jsonl",
            "_source_line": 2,
        }
    ]

    with pytest.raises(
        ValueError,
        match="authoritative close order proof",
    ):
        reconcile_cycle_events(
            raw_events=raw_events,
            history_deals=history_deals,
            history_orders=[],
            cycle_id="cycle-1",
            history_server_offset_seconds=7200,
            expected_magic=26011001,
            expected_symbol="XAUUSD",
        )


def test_reconciliation_cli_preserves_raw_archive_and_writes_assessment(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "target-cycles.jsonl"
    deals = tmp_path / "history-deals.jsonl"
    orders = tmp_path / "history-orders.jsonl"
    output_events = tmp_path / "reconciled.jsonl"
    output_assessment = tmp_path / "assessment.json"

    raw_events = [
        _raw_event(1, "2026-08-17T10:00:00Z", "cycle_start"),
        _raw_event(
            2,
            "2026-08-17T10:00:10Z",
            "fill",
            comment="STR B1",
            side="buy",
            position_ticket=101,
            deal_ticket=1001,
        ),
        _raw_event(3, "2026-08-17T10:01:00Z", "cycle_complete"),
        _raw_event(4, "2026-08-17T10:01:20Z", "cycle_restart"),
    ]
    for event in raw_events:
        event.pop("_source_path", None)
        event.pop("_source_line", None)
    archive.write_text(
        "".join(json.dumps(event) + "\n" for event in raw_events),
        encoding="utf-8",
    )
    deals.write_text(
        json.dumps(
            {
                "ticket": 2001,
                "order": 3001,
                "position_id": 101,
                "time_msc": _server_time_msc("2026-08-17T10:00:40Z"),
                "entry": 1,
                "type": 1,
                "magic": 26011001,
                "symbol": "XAUUSD",
                "comment": "STR CLOSE",
                "volume": 0.01,
                "price": 4398.5,
                "profit": -1.25,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    orders.write_text(
        json.dumps(
            {
                "ticket": 3001,
                "position_id": 101,
                "time_done_msc": _server_time_msc(
                    "2026-08-17T10:00:40Z"
                ),
                "magic": 26011001,
                "symbol": "XAUUSD",
                "comment": "STR CLOSE",
                "volume_initial": 0.01,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before_hash = hashlib.sha256(archive.read_bytes()).hexdigest()

    completed = subprocess.run(
        [
            str(Path(__import__("sys").executable)),
            str(RECONCILE_TOOL),
            "--archive",
            str(archive),
            "--cycle-id",
            "cycle-1",
            "--history-deals",
            str(deals),
            "--history-orders",
            str(orders),
            "--history-server-offset-seconds",
            "7200",
            "--magic",
            "26011001",
            "--symbol",
            "XAUUSD",
            "--output-events",
            str(output_events),
            "--output-assessment",
            str(output_assessment),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == before_hash
    reconciled = [
        json.loads(line)
        for line in output_events.read_text(encoding="utf-8").splitlines()
    ]
    assert len(reconciled) == 6
    assessment = json.loads(output_assessment.read_text(encoding="utf-8"))
    assert assessment["status"] == "NETWORK_GAP_RECOVERED_FROM_HISTORY"
    assert assessment["raw_archive"]["sha256"] == before_hash.upper()
    assert assessment["raw_archive"]["unchanged_after_reconciliation"] is True
    assert assessment["summary"]["lifecycle_conservation"] == "1 = 0 + 1"
