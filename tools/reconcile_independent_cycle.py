from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.cycle_reconciliation import (  # noqa: E402
    reconcile_cycle_events,
)


UTC = timezone.utc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _load_jsonl(paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                record = json.loads(stripped)
                record["_source_path"] = str(path.resolve())
                record["_source_line"] = line_number
                records.append(record)
    return records


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _source_manifest(paths: list[Path]) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path.resolve()),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in paths
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument(
        "--history-deals",
        required=True,
        type=Path,
        action="append",
    )
    parser.add_argument(
        "--history-orders",
        required=True,
        type=Path,
        action="append",
    )
    parser.add_argument(
        "--history-server-offset-seconds",
        required=True,
        type=int,
    )
    parser.add_argument("--magic", required=True, type=int)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--output-events", required=True, type=Path)
    parser.add_argument("--output-assessment", required=True, type=Path)
    args = parser.parse_args(argv)

    inputs = [
        args.archive,
        *args.history_deals,
        *args.history_orders,
    ]
    for path in inputs:
        if not path.is_file():
            parser.error(f"Input file was not found: {path}")

    input_paths = {path.resolve() for path in inputs}
    output_paths = {
        args.output_events.resolve(),
        args.output_assessment.resolve(),
    }
    if len(output_paths) != 2:
        parser.error("Output event and assessment paths must be different.")
    if input_paths & output_paths:
        parser.error("Outputs must not overwrite raw evidence inputs.")

    raw_hash_before = _sha256(args.archive)
    result = reconcile_cycle_events(
        raw_events=_load_jsonl([args.archive]),
        history_deals=_load_jsonl(args.history_deals),
        history_orders=_load_jsonl(args.history_orders),
        cycle_id=args.cycle_id,
        history_server_offset_seconds=args.history_server_offset_seconds,
        expected_magic=args.magic,
        expected_symbol=args.symbol,
    )

    event_content = "".join(
        json.dumps(event, sort_keys=True) + "\n"
        for event in result["events"]
    )
    _atomic_write(args.output_events, event_content)
    raw_hash_after = _sha256(args.archive)
    raw_unchanged = raw_hash_after == raw_hash_before
    if not raw_unchanged:
        raise RuntimeError("Raw archive changed during reconciliation.")

    recovered = int(
        result["summary"]["recovered_close_fill_count"]
    )
    assessment = {
        "schema_version": 1,
        "assessed_at_utc": datetime.now(UTC).isoformat(),
        "status": (
            "NETWORK_GAP_RECOVERED_FROM_HISTORY"
            if recovered
            else "RAW_ARCHIVE_ALREADY_COMPLETE"
        ),
        "cycle_id": args.cycle_id,
        "raw_archive": {
            "path": str(args.archive.resolve()),
            "sha256": raw_hash_before,
            "bytes": args.archive.stat().st_size,
            "unchanged_after_reconciliation": raw_unchanged,
        },
        "history_deal_sources": _source_manifest(args.history_deals),
        "history_order_sources": _source_manifest(args.history_orders),
        "reconciled_events": {
            "path": str(args.output_events.resolve()),
            "sha256": _sha256(args.output_events),
            "bytes": args.output_events.stat().st_size,
        },
        "summary": result["summary"],
        "provenance_contract": {
            "raw_archive_rewritten": False,
            "recovered_events_are_derived": True,
            "recovered_close_requires_matching_deal_and_order": True,
            "history_server_offset_seconds": (
                args.history_server_offset_seconds
            ),
            "expected_magic": args.magic,
            "expected_symbol": args.symbol,
        },
    }
    _atomic_write(
        args.output_assessment,
        json.dumps(assessment, indent=2, sort_keys=True) + "\n",
    )
    print(
        json.dumps(
            {
                "status": assessment["status"],
                "cycle_id": args.cycle_id,
                "recovered_close_fills": recovered,
                "lifecycle_conservation": result["summary"][
                    "lifecycle_conservation"
                ],
                "output_events": str(args.output_events.resolve()),
                "output_assessment": str(
                    args.output_assessment.resolve()
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
