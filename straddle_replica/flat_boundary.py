from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping


UTC = timezone.utc


def read_last_two_jsonl(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    block_size = 64 * 1024
    with path.open("rb") as stream:
        stream.seek(0, 2)
        position = stream.tell()
        buffer = b""
        while position > 0:
            size = min(block_size, position)
            position -= size
            stream.seek(position)
            buffer = stream.read(size) + buffer
            lines = buffer.splitlines()
            complete_lines = lines if position == 0 else lines[1:]
            nonempty = [
                line
                for line in complete_lines
                if line.strip()
            ]
            if len(nonempty) >= 2:
                return (
                    json.loads(nonempty[-2].decode("utf-8")),
                    json.loads(nonempty[-1].decode("utf-8")),
                )
    raise ValueError(f"fewer than two JSONL records: {path}")


def _parse_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _snapshot_is_flat(snapshot: Mapping[str, Any]) -> bool:
    return not snapshot.get("positions") and not snapshot.get("orders")


def evaluate_freeze_readiness(
    *,
    heartbeat: Mapping[str, Any],
    manifest: Mapping[str, Any],
    previous_snapshot: Mapping[str, Any],
    latest_snapshot: Mapping[str, Any],
    observer_state: Mapping[str, Any],
    archive_state: Mapping[str, Any],
    qualification_state: Mapping[str, Any],
    now_utc: datetime,
    expected_login: int,
    expected_server: str,
    expected_active_build_id: str,
    expected_staged_build_id: str,
    max_heartbeat_age_seconds: float,
    minimum_flat_confirmation_seconds: float,
) -> dict[str, Any]:
    reasons: list[str] = []
    now = now_utc.astimezone(UTC)
    heartbeat_time = _parse_utc(heartbeat["capture_time_utc"])
    heartbeat_age = (now - heartbeat_time).total_seconds()
    previous_time = _parse_utc(previous_snapshot["capture_time_utc"])
    latest_time = _parse_utc(latest_snapshot["capture_time_utc"])
    flat_confirmation_seconds = (
        latest_time - previous_time
    ).total_seconds()

    if not heartbeat.get("healthy") or heartbeat.get("stopped"):
        reasons.append("heartbeat_unhealthy")
    if not heartbeat.get("read_only_verified"):
        reasons.append("heartbeat_not_read_only")
    if heartbeat_age < 0 or heartbeat_age > max_heartbeat_age_seconds:
        reasons.append("heartbeat_stale")
    if (
        int(heartbeat.get("positions_total") or 0) != 0
        or int(heartbeat.get("orders_total") or 0) != 0
    ):
        reasons.append("heartbeat_not_flat")

    account = dict(manifest.get("account") or {})
    terminal = dict(manifest.get("terminal") or {})
    safety = dict(manifest.get("safety") or {})
    if (
        int(account.get("login") or 0) != expected_login
        or str(account.get("server") or "") != expected_server
    ):
        reasons.append("account_identity_mismatch")
    if (
        account.get("trade_allowed") is not False
        or terminal.get("trade_allowed") is not False
        or not terminal.get("connected")
        or safety.get("account_trade_allowed") is not False
        or safety.get("collector_has_trading_api") is not False
        or safety.get("require_read_only") is not True
    ):
        reasons.append("read_only_safety_mismatch")
    if str(manifest.get("session_id") or "") != str(
        heartbeat.get("session_id") or ""
    ):
        reasons.append("observer_session_mismatch")

    if not _snapshot_is_flat(previous_snapshot):
        reasons.append("previous_snapshot_not_flat")
    if not _snapshot_is_flat(latest_snapshot):
        reasons.append("latest_snapshot_not_flat")
    if int(latest_snapshot.get("sequence") or 0) <= int(
        previous_snapshot.get("sequence") or 0
    ):
        reasons.append("flat_snapshots_not_consecutive")
    if flat_confirmation_seconds < minimum_flat_confirmation_seconds:
        reasons.append("flat_confirmation_too_short")
    if abs((heartbeat_time - latest_time).total_seconds()) > (
        max_heartbeat_age_seconds
    ):
        reasons.append("snapshot_not_fresh")

    if (
        observer_state.get("waiting_for_flat") is not True
        or observer_state.get("suppress_current_cycle") is not True
        or observer_state.get("armed_for_next_cycle") is not False
        or str(observer_state.get("session_id") or "")
        != str(heartbeat.get("session_id") or "")
    ):
        reasons.append("observer_not_waiting_for_excluded_cycle_flat")
    if (
        int(archive_state.get("sequence_gaps") or 0) != 0
        or str(archive_state.get("current_cycle_id") or "")
    ):
        reasons.append("archive_state_not_clean")

    active_cycle_id = str(
        qualification_state.get("active_cycle_id") or ""
    )
    excluded_cycles = {
        str(value)
        for value in (
            qualification_state.get("excluded_candidate_cycle_ids")
            or []
        )
    }
    if (
        qualification_state.get("active_cycle_eligible") is not False
        or not active_cycle_id
        or active_cycle_id not in excluded_cycles
    ):
        reasons.append("active_cycle_not_excluded")
    if (
        str(qualification_state.get("active_build_id") or "")
        != expected_active_build_id
    ):
        reasons.append("active_build_mismatch")
    if (
        str(qualification_state.get("staged_build_id") or "")
        != expected_staged_build_id
        or str(qualification_state.get("staged_status") or "")
        != "LOCAL_VERIFIED_AWAITING_NATURAL_FLAT_BOUNDARY"
    ):
        reasons.append("staged_build_not_ready")
    if (
        int(qualification_state.get("complete_paired_cycles") or 0)
        != 0
        or qualification_state.get("evidence_based_fidelity_percent")
        is not None
    ):
        reasons.append("qualification_state_unexpected")

    return {
        "ready": not reasons,
        "reasons": reasons,
        "heartbeat_age_seconds": round(heartbeat_age, 6),
        "flat_confirmation_seconds": round(
            flat_confirmation_seconds,
            6,
        ),
        "previous_snapshot_sequence": int(
            previous_snapshot.get("sequence") or 0
        ),
        "latest_snapshot_sequence": int(
            latest_snapshot.get("sequence") or 0
        ),
    }


def freeze_remote_candidate(
    *,
    run_ssh: Callable[[str], str],
    expected_active_ex5_sha256: str,
) -> dict[str, Any]:
    container = "straddle-fidelity-independent-demo"
    terminal_ex5 = (
        "/opt/straddle-fidelity-independent-demo/terminal/"
        "MQL5/Experts/StraddleReplica/StraddleReplica.ex5"
    )
    fingerprint = run_ssh(
        "docker inspect --format "
        "'{{.Id}}|{{.State.Status}}|{{.RestartCount}}|"
        "{{.State.OOMKilled}}' "
        f"{container}"
    ).strip()
    fields = fingerprint.split("|")
    if len(fields) != 4:
        raise RuntimeError("candidate container fingerprint is invalid")
    container_id, status, restart_count, oom_killed = fields
    if (
        status != "running"
        or restart_count != "0"
        or oom_killed.lower() != "false"
    ):
        raise RuntimeError(
            "candidate container health is not clean: "
            f"{fingerprint}"
        )

    vnc = run_ssh(
        f"docker port {container} 5900/tcp"
    ).strip()
    if vnc != "127.0.0.1:15925":
        raise RuntimeError(f"candidate VNC binding mismatch: {vnc}")

    mt5_start = run_ssh(
        "docker inspect --format "
        "'{{range .Config.Env}}{{println .}}{{end}}' "
        f"{container} | grep '^MT5_START='"
    ).strip()
    if mt5_start != "MT5_START=1":
        raise RuntimeError(
            f"candidate MT5_START mismatch: {mt5_start}"
        )

    hash_output = run_ssh(f"sha256sum {terminal_ex5}").strip()
    active_hash = hash_output.split(maxsplit=1)[0].lower()
    if active_hash != expected_active_ex5_sha256.lower():
        raise RuntimeError(
            "active EX5 hash mismatch: "
            f"expected {expected_active_ex5_sha256}, got {active_hash}"
        )

    stopped = run_ssh(
        f"docker stop --time 1 {container}"
    ).strip()
    if stopped != container:
        raise RuntimeError(
            f"candidate container stop was not acknowledged: {stopped}"
        )
    return {
        "container_id": container_id,
        "active_ex5_sha256": active_hash,
        "stopped": True,
    }
