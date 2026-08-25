from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


UTC = timezone.utc


def _parse_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _manifest(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            str(row["key"]): str(row["value"])
            for row in csv.DictReader(handle)
        }


def _heartbeat(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_independent_readiness(
    *,
    target_heartbeat: Path,
    candidate_heartbeat: Path,
    candidate_manifest: Path,
    candidate_telemetry: Path,
    expected_login: int,
    max_age_seconds: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    if expected_login <= 0 or max_age_seconds <= 0:
        raise ValueError("Expected login and max age must be positive")
    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    failures: list[str] = []
    for name, path in (
        ("target", target_heartbeat),
        ("candidate", candidate_heartbeat),
    ):
        payload = _heartbeat(path)
        captured = _parse_time(payload["capture_time_utc"])
        age = (current - captured).total_seconds()
        if age < -1 or age > max_age_seconds:
            failures.append(f"{name}_heartbeat_stale")
        if not payload.get("healthy"):
            failures.append(f"{name}_heartbeat_unhealthy")
        if payload.get("stopped"):
            failures.append(f"{name}_collector_stopped")
        if not payload.get("read_only_verified"):
            failures.append(f"{name}_read_only_not_verified")
        if int(payload.get("dropped_transactions") or 0) != 0:
            failures.append(f"{name}_dropped_transactions")

    manifest = _manifest(candidate_manifest)
    required = {
        "runtime_mode": "0",
        "runtime_magic": "901018",
        "runtime_require_demo_account": "1",
        "runtime_expected_account_login": str(expected_login),
        "profile": "4",
        "profile_levels_per_side": "30",
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            failures.append(f"manifest_{key}")

    with candidate_telemetry.open(
        encoding="utf-8",
        errors="ignore",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        failures.append("telemetry_empty")
        telemetry_age = None
        accepted_slots: list[str] = []
    else:
        timestamps = [
            _parse_time(row.get("utc_time") or row.get("time"))
            for row in rows
            if row.get("utc_time") or row.get("time")
        ]
        if timestamps:
            latest = max(timestamps)
            telemetry_age = (current - latest).total_seconds()
            if telemetry_age < -1 or telemetry_age > max_age_seconds:
                failures.append("telemetry_stale")
        else:
            telemetry_age = None
            failures.append("telemetry_timestamp_missing")
        accepted_slots = [
            str(row.get("comment") or "")
            for row in rows
            if row.get("kind") == "pending_request"
            and int(row.get("retcode") or 0)
            in {0, 10008, 10009, 10010}
        ]
        if not any(row.get("kind") == "cycle_start" for row in rows):
            failures.append("telemetry_cycle_start_missing")
        if len(set(accepted_slots)) < 60:
            failures.append("telemetry_initial_slots_incomplete")

    return {
        "ready": not failures,
        "failures": sorted(set(failures)),
        "expected_login": expected_login,
        "telemetry_age_seconds": telemetry_age,
        "accepted_initial_slots": len(set(accepted_slots)),
    }
