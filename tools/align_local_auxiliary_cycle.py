from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Callable


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.cycle_alignment import (  # noqa: E402
    AlignmentPlan,
    COMPLETE_KINDS,
    RESTART_KINDS,
    candidate_freeze_ready,
    next_target_restart,
    parse_utc,
    plan_target_aligned_launch,
    validate_bound_demo_preset,
)
from straddle_replica.live_twin import (  # noqa: E402
    load_demo_telemetry_events,
    load_jsonl_events,
)


UTC = timezone.utc
POWERSHELL = Path(
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
EXPECTED_COMMENTS = {
    f"STR {side}{level}"
    for level in range(1, 31)
    for side in ("B", "S")
}
ACCEPTED_RETCODES = {0, 10008, 10009, 10010}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        **payload,
        "updated_at_utc": datetime.now(tz=UTC).isoformat(),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(output, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _write_alignment_hold(
    path: Path,
    *,
    candidate_cycle_id: str,
    active_ex5_sha256: str,
    created_at_utc: datetime,
) -> None:
    _write_json_atomic(
        path,
        {
            "status": "HOLD",
            "candidate_cycle_id": candidate_cycle_id,
            "active_ex5_sha256": active_ex5_sha256.upper(),
            "created_at_utc": parse_utc(created_at_utc).isoformat(),
        },
    )


def _release_alignment_hold(path: Path) -> None:
    path.with_suffix(path.suffix + ".tmp").unlink(missing_ok=True)
    path.unlink(missing_ok=True)


def _resolve_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise RuntimeError(f"{label} is missing: {resolved}")
    return resolved


def _validate_independent_flat_proof(
    path: Path,
    *,
    expected_login: int,
    maximum_age_seconds: int,
    now_utc: datetime | None = None,
) -> datetime:
    proof = json.loads(path.read_text(encoding="utf-8"))
    account = proof.get("account") or {}
    sync = proof.get("read_only_broker_sync") or {}
    process_safety = proof.get("process_safety") or {}
    if int(account.get("login") or 0) != expected_login:
        raise RuntimeError(
            "Independent flat proof has an unexpected account login"
        )
    if (
        "positions_total" not in sync
        or "orders_total" not in sync
        or sync.get("flat") is not True
        or int(sync.get("positions_total") or 0) != 0
        or int(sync.get("orders_total") or 0) != 0
    ):
        raise RuntimeError(
            "Independent flat proof must show zero positions and "
            "zero orders"
        )
    if sync.get("terminal_trade_allowed") is not False:
        raise RuntimeError(
            "Independent flat proof terminal trade_allowed must be false"
        )
    if sync.get("start_config_experts_enabled") is not False:
        raise RuntimeError(
            "Independent flat proof source must have Experts disabled"
        )
    if sync.get("start_config_allow_live_trading") is not False:
        raise RuntimeError(
            "Independent flat proof source must disable live trading"
        )
    required_true = (
        "read_only_tester_terminal_stopped",
        "exact_auxiliary_trading_terminal_stopped",
    )
    for field in required_true:
        if process_safety.get(field) is not True:
            raise RuntimeError(
                f"Independent flat proof safety field must be true: {field}"
            )
    required_false = (
        "alignment_controller_process_running",
        "orders_or_positions_modified",
        "trade_methods_invoked",
    )
    for field in required_false:
        if process_safety.get(field) is not False:
            raise RuntimeError(
                f"Independent flat proof safety field must be false: {field}"
            )
    captured_text = (
        sync.get("sync_time_utc") or proof.get("assessed_at_utc")
    )
    if not captured_text:
        raise RuntimeError(
            "Independent flat proof has no capture timestamp"
        )
    captured_at = parse_utc(captured_text)
    now = parse_utc(now_utc or datetime.now(tz=UTC))
    age_seconds = (now - captured_at).total_seconds()
    if age_seconds < -1.0 or age_seconds > maximum_age_seconds:
        raise RuntimeError(
            "Independent flat proof is stale: "
            f"age_seconds={age_seconds:.3f}"
        )
    return captured_at


def _install_staged_ex5(
    *,
    active_ex5_path: Path,
    expected_active_ex5_sha256: str,
    staged_ex5_path: Path,
    expected_staged_ex5_sha256: str,
) -> str:
    active_hash = _sha256(active_ex5_path)
    staged_hash = _sha256(staged_ex5_path)
    expected_active = expected_active_ex5_sha256.upper()
    expected_staged = expected_staged_ex5_sha256.upper()
    if staged_hash != expected_staged:
        raise RuntimeError("Staged EX5 SHA256 mismatch")
    if active_hash == expected_staged:
        return active_hash
    if active_hash != expected_active:
        raise RuntimeError("Active EX5 SHA256 mismatch")

    temporary = active_ex5_path.with_suffix(
        active_ex5_path.suffix + ".staged.tmp"
    )
    temporary.unlink(missing_ok=True)
    shutil.copy2(staged_ex5_path, temporary)
    if _sha256(temporary) != expected_staged:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Copied staged EX5 SHA256 mismatch")
    os.replace(temporary, active_ex5_path)
    deployed_hash = _sha256(active_ex5_path)
    if deployed_hash != expected_staged:
        raise RuntimeError("Deployed EX5 SHA256 mismatch")
    return deployed_hash


def _activate_staged_qualification(
    *,
    path: Path,
    candidate_cycle_id: str,
    staged_ex5_path: Path,
    staged_ex5_sha256: str,
    staged_package_path: Path,
    staged_package_sha256: str,
    deployed_at_utc: datetime,
) -> None:
    state = json.loads(path.read_text(encoding="utf-8"))
    excluded = [
        str(cycle_id)
        for cycle_id in (
            state.get("excluded_candidate_cycle_ids") or []
        )
    ]
    if candidate_cycle_id not in excluded:
        excluded.append(candidate_cycle_id)
    state.update(
        {
            "active_build_id": staged_ex5_sha256.lower(),
            "active_deployed_utc": deployed_at_utc.isoformat(),
            "active_cycle_id": candidate_cycle_id,
            "active_cycle_eligible": False,
            "excluded_candidate_cycle_ids": excluded,
            "qualification_started_utc": None,
            "qualification_start_policy": "alignment_controller",
            "complete_paired_cycles": 0,
            "evidence_based_fidelity_percent": None,
            "strict_lifecycle_fidelity_percent": None,
            "conditional_logic_fidelity_percent": None,
            "conditional_coverage_percent": None,
            "qualified_at_or_above_95_percent": False,
            "qualified_at_or_above_99_percent": False,
            "staged_status": (
                "DEPLOYED_AT_NATURAL_FLAT_WAITING_FOR_ALIGNED_CYCLE"
            ),
            "active_ex5_path": str(staged_ex5_path),
            "active_package_path": str(staged_package_path),
            "active_package_sha256": staged_package_sha256.lower(),
        }
    )
    _write_json_atomic(path, state)


def _record_alignment_qualification(
    *,
    path: Path,
    previous_candidate_cycle_id: str,
    candidate_cycle_id: str,
    candidate_start_utc: datetime,
    target_cycle_id: str,
    aligned: bool,
) -> None:
    state = json.loads(path.read_text(encoding="utf-8"))
    excluded = [
        str(cycle_id)
        for cycle_id in (
            state.get("excluded_candidate_cycle_ids") or []
        )
    ]
    if previous_candidate_cycle_id not in excluded:
        excluded.append(previous_candidate_cycle_id)
    if not aligned and candidate_cycle_id not in excluded:
        excluded.append(candidate_cycle_id)
    state.update(
        {
            "active_cycle_id": candidate_cycle_id,
            "active_cycle_eligible": aligned,
            "active_target_cycle_id": target_cycle_id,
            "active_target_cycle_eligible": aligned,
            "excluded_candidate_cycle_ids": excluded,
            "qualification_started_utc": (
                candidate_start_utc.isoformat() if aligned else None
            ),
            "staged_status": (
                "ALIGNED_QUALIFICATION_CYCLE_ACTIVE"
                if aligned
                else "ALIGNMENT_OUTSIDE_TOLERANCE_CYCLE_EXCLUDED"
            ),
        }
    )
    _write_json_atomic(path, state)


def _powershell(
    script: str,
    *,
    environment: dict[str, str],
) -> str:
    process_environment = os.environ.copy()
    process_environment.update(environment)
    completed = subprocess.run(
        [
            str(POWERSHELL),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        env=process_environment,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            "PowerShell process guard failed "
            f"({completed.returncode}): {detail[:300]}"
        )
    return completed.stdout.strip()


def _exact_terminal_processes(terminal_path: Path) -> list[dict[str, Any]]:
    output = _powershell(
        """
$target=[System.IO.Path]::GetFullPath(
  [Environment]::GetEnvironmentVariable('STR_ALIGN_TERMINAL')
)
$rows=@(
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -eq 'terminal64.exe' -and
      $_.ExecutablePath -and
      [System.IO.Path]::GetFullPath($_.ExecutablePath) -ieq $target
    } |
    Select-Object ProcessId,ExecutablePath,CreationDate
)
ConvertTo-Json -Compress -InputObject $rows
""",
        environment={"STR_ALIGN_TERMINAL": str(terminal_path)},
    )
    if not output:
        return []
    decoded = json.loads(output)
    if isinstance(decoded, dict):
        return [decoded]
    return list(decoded)


def _stop_exact_terminal(process_id: int) -> None:
    _powershell(
        """
$pidValue=[int][Environment]::GetEnvironmentVariable('STR_ALIGN_PID')
$process=Get-Process -Id $pidValue -ErrorAction Stop
[void]$process.CloseMainWindow()
if(-not $process.WaitForExit(10000)) {
  Stop-Process -Id $pidValue -Force -ErrorAction Stop
  Wait-Process -Id $pidValue -Timeout 10 -ErrorAction SilentlyContinue
}
""",
        environment={"STR_ALIGN_PID": str(process_id)},
    )


def _start_terminal(
    terminal_path: Path,
    startup_config: Path,
) -> subprocess.Popen[bytes]:
    creation_flags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    return subprocess.Popen(
        [
            str(terminal_path),
            "/portable",
            f"/config:{startup_config}",
        ],
        cwd=terminal_path.parent,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )


def _ensure_exact_terminal_running(
    terminal_path: Path,
    startup_config: Path,
    *,
    poll_seconds: float,
) -> int:
    processes = _exact_terminal_processes(terminal_path)
    if len(processes) > 1:
        raise RuntimeError(
            "Multiple exact-path auxiliary terminals are running"
        )
    if len(processes) == 1:
        return int(processes[0]["ProcessId"])

    _start_terminal(terminal_path, startup_config)
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        processes = _exact_terminal_processes(terminal_path)
        if len(processes) > 1:
            raise RuntimeError(
                "Multiple exact-path auxiliary terminals started"
            )
        if len(processes) == 1:
            return int(processes[0]["ProcessId"])
        time.sleep(poll_seconds)
    raise RuntimeError("Auxiliary terminal did not start within 20 seconds")


def _event_time(event: dict[str, Any]) -> datetime:
    return parse_utc(event["time_utc"])


def _cycle_events(
    events: list[dict[str, Any]],
    cycle_id: str,
) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if str(event.get("cycle_id") or "") == cycle_id
    ]


def _cycle_has_restart(
    events: list[dict[str, Any]],
    cycle_id: str,
) -> bool:
    return any(
        str(event.get("kind") or "") in RESTART_KINDS
        for event in _cycle_events(events, cycle_id)
    )


def _latest_event_summary(
    events: list[dict[str, Any]],
    cycle_id: str,
) -> dict[str, Any]:
    matching = _cycle_events(events, cycle_id)
    if not matching:
        return {}
    latest = max(
        matching,
        key=lambda event: (
            _event_time(event),
            int(event.get("sequence") or 0),
        ),
    )
    return {
        "last_event_kind": latest.get("kind"),
        "last_event_utc": latest.get("time_utc"),
        "last_event_sequence": latest.get("sequence"),
        "cycle_realized": latest.get("cycle_realized"),
        "floating_profit": latest.get("floating_profit"),
        "cycle_net": latest.get("cycle_net"),
    }


def _candidate_freeze_source(
    events: list[dict[str, Any]],
    *,
    cycle_id: str,
    independent_flat_at_utc: datetime | None,
) -> str:
    if independent_flat_at_utc is not None:
        return "independent_flat_proof"
    if candidate_freeze_ready(events, cycle_id=cycle_id):
        return "candidate_telemetry"
    return ""


def _terminal_process_to_stop(
    processes: list[dict[str, Any]],
    *,
    freeze_source: str,
) -> int:
    if freeze_source == "independent_flat_proof":
        if processes:
            raise RuntimeError(
                "Auxiliary trading terminal must remain stopped when "
                "independent flat proof is used"
            )
        return 0
    if freeze_source == "candidate_telemetry":
        if len(processes) != 1:
            raise RuntimeError(
                "Expected exactly one exact-path auxiliary terminal, "
                f"found {len(processes)}"
            )
        return int(processes[0]["ProcessId"])
    raise RuntimeError(f"Unknown candidate freeze source: {freeze_source}")


def _target_restart_event(
    events: list[dict[str, Any]],
    plan: AlignmentPlan,
) -> dict[str, Any] | None:
    candidates = [
        event
        for event in events
        if str(event.get("cycle_id") or "") == plan.target_cycle_id
        and str(event.get("kind") or "") in RESTART_KINDS
        and event.get("time_utc")
        and _event_time(event) >= plan.target_complete_utc
    ]
    return min(candidates, key=_event_time, default=None)


def _next_candidate_start(
    events: list[dict[str, Any]],
    *,
    excluded_cycle_id: str,
    after_utc: datetime,
) -> dict[str, Any] | None:
    starts = [
        event
        for event in events
        if str(event.get("kind") or "") == "cycle_start"
        and str(event.get("cycle_id") or "")
        and str(event.get("cycle_id") or "") != excluded_cycle_id
        and event.get("time_utc")
        and _event_time(event) >= after_utc
    ]
    return min(starts, key=_event_time, default=None)


def _target_new_cycle_id(
    events: list[dict[str, Any]],
    *,
    completed_cycle_id: str,
    restart_utc: datetime,
) -> str:
    candidates = [
        event
        for event in events
        if str(event.get("cycle_id") or "")
        and str(event.get("cycle_id") or "") != completed_cycle_id
        and event.get("time_utc")
        and _event_time(event) >= restart_utc
    ]
    if not candidates:
        return ""
    return str(min(candidates, key=_event_time).get("cycle_id") or "")


def _event_identity(event: dict[str, Any]) -> str:
    event_id = str(event.get("event_id") or "")
    if event_id:
        return event_id
    return "|".join(
        str(event.get(field) or "")
        for field in (
            "request_id",
            "order_ticket",
            "ticket",
            "sequence",
            "time_utc",
        )
    )


def _initial_grid(
    events: list[dict[str, Any]],
    cycle_id: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    slots: dict[str, dict[str, Any]] = {}
    duplicate_slots: set[str] = set()
    eligible_rearms: Counter[str] = Counter()
    used_rearms: Counter[str] = Counter()
    seen_request_identities: set[str] = set()
    for event in sorted(
        _cycle_events(events, cycle_id),
        key=lambda item: (
            _event_time(item),
            int(item.get("sequence") or 0),
        ),
    ):
        kind = str(event.get("kind") or "")
        comment = str(event.get("comment") or "")
        if comment not in EXPECTED_COMMENTS:
            continue
        if kind == "stop_exit":
            eligible_rearms[comment] += 1
            continue
        if kind != "pending_request":
            continue
        if int(event.get("retcode") or 0) not in ACCEPTED_RETCODES:
            continue
        identity = _event_identity(event)
        if identity in seen_request_identities:
            continue
        seen_request_identities.add(identity)
        if comment in slots:
            if used_rearms[comment] >= eligible_rearms[comment]:
                duplicate_slots.add(comment)
            used_rearms[comment] += 1
            continue
        slots[comment] = event
    return slots, sorted(duplicate_slots)


def _initial_slots(
    events: list[dict[str, Any]],
    cycle_id: str,
) -> dict[str, dict[str, Any]]:
    return _initial_grid(events, cycle_id)[0]


def _anchor(slots: dict[str, dict[str, Any]]) -> float | None:
    buy = slots.get("STR B1")
    sell = slots.get("STR S1")
    if buy is None or sell is None:
        return None
    return (float(buy.get("price") or 0.0) + float(
        sell.get("price") or 0.0
    )) / 2.0


class _CachedEvents:
    def __init__(
        self,
        path: Path,
        loader: Callable[[Path], list[dict[str, Any]]],
    ) -> None:
        self.path = path
        self.loader = loader
        self.identity: tuple[int, int] | None = None
        self.events: list[dict[str, Any]] = []

    def load(self) -> list[dict[str, Any]]:
        stat = self.path.stat()
        identity = (stat.st_mtime_ns, stat.st_size)
        if identity != self.identity:
            self.events = self.loader(self.path)
            self.identity = identity
        return self.events


def _validate_runtime(
    *,
    terminal_path: Path,
    startup_config: Path,
    preset_path: Path,
    expected_demo_login: int,
    active_ex5_path: Path,
    expected_active_ex5_sha256: str,
    expected_staged_ex5_sha256: str,
) -> str:
    if terminal_path.name.lower() != "terminal64.exe":
        raise RuntimeError("The dedicated executable must be terminal64.exe")
    startup = startup_config.read_text(
        encoding="utf-8",
        errors="ignore",
    )
    if "Expert=StraddleReplica\\StraddleReplica" not in startup:
        raise RuntimeError("Startup config does not load StraddleReplica")
    preset = preset_path.read_text(encoding="utf-8", errors="ignore")
    validate_bound_demo_preset(
        preset,
        expected_login=expected_demo_login,
    )
    active_hash = _sha256(active_ex5_path)
    if active_hash not in {
        expected_active_ex5_sha256.upper(),
        expected_staged_ex5_sha256.upper(),
    }:
        raise RuntimeError("Active EX5 SHA256 mismatch")
    return active_hash


def _frozen_deployment_utc(
    state: dict[str, Any],
    *,
    candidate_cycle_id: str,
    active_ex5_sha256: str,
    staged_ex5_sha256: str,
) -> datetime | None:
    staged_hash = staged_ex5_sha256.lower()
    if (
        active_ex5_sha256.lower() != staged_hash
        or str(state.get("active_build_id") or "").lower()
        != staged_hash
        or str(state.get("active_cycle_id") or "")
        != candidate_cycle_id
        or bool(state.get("active_cycle_eligible"))
        or state.get("qualification_started_utc")
        or state.get("qualification_start_policy")
        != "alignment_controller"
        or state.get("staged_status")
        != "DEPLOYED_AT_NATURAL_FLAT_WAITING_FOR_ALIGNED_CYCLE"
        or not state.get("active_deployed_utc")
    ):
        return None
    return parse_utc(state["active_deployed_utc"])


def _viable_alignment_plan(
    events: list[dict[str, Any]],
    *,
    frozen_at_utc: datetime,
    startup_lead_seconds: float,
    now_utc: datetime,
) -> tuple[AlignmentPlan | None, list[str]]:
    cutoff = parse_utc(frozen_at_utc)
    now = parse_utc(now_utc)
    missed: list[str] = []
    while True:
        plan = plan_target_aligned_launch(
            events,
            frozen_at_utc=cutoff,
            startup_lead_seconds=startup_lead_seconds,
        )
        if plan is None:
            return None, missed
        if plan.launch_at_utc > now:
            return plan, missed
        missed.append(plan.target_cycle_id)
        cutoff = plan.target_complete_utc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate-telemetry",
        required=True,
        type=Path,
    )
    parser.add_argument("--candidate-cycle-id", required=True)
    parser.add_argument("--target-events", required=True, type=Path)
    parser.add_argument("--terminal-path", required=True, type=Path)
    parser.add_argument("--startup-config", required=True, type=Path)
    parser.add_argument("--preset-path", required=True, type=Path)
    parser.add_argument("--expected-demo-login", required=True, type=int)
    parser.add_argument("--active-ex5-path", required=True, type=Path)
    parser.add_argument(
        "--expected-active-ex5-sha256",
        required=True,
    )
    parser.add_argument(
        "--staged-ex5-path",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--expected-staged-ex5-sha256",
        required=True,
    )
    parser.add_argument(
        "--staged-package-path",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--expected-staged-package-sha256",
        required=True,
    )
    parser.add_argument(
        "--qualification-state",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--alignment-hold-path",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--independent-flat-proof",
        type=Path,
    )
    parser.add_argument(
        "--flat-proof-max-age-seconds",
        type=int,
        default=30,
    )
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument(
        "--race-guard-seconds",
        type=float,
        default=0.35,
    )
    parser.add_argument(
        "--startup-lead-seconds",
        type=float,
        default=4.5,
    )
    parser.add_argument(
        "--start-observation-seconds",
        type=float,
        default=180.0,
    )
    parser.add_argument(
        "--start-tolerance-seconds",
        type=float,
        default=2.0,
    )
    args = parser.parse_args(argv)
    if args.poll_seconds < 0.1:
        parser.error("--poll-seconds must be at least 0.1")
    if args.race_guard_seconds < 0.1:
        parser.error("--race-guard-seconds must be at least 0.1")
    if args.startup_lead_seconds < 0:
        parser.error("--startup-lead-seconds must be non-negative")
    if args.start_observation_seconds <= 0:
        parser.error("--start-observation-seconds must be positive")
    if args.flat_proof_max_age_seconds < 1:
        parser.error("--flat-proof-max-age-seconds must be positive")

    candidate_telemetry = _resolve_file(
        args.candidate_telemetry,
        "Candidate telemetry",
    )
    target_events_path = _resolve_file(
        args.target_events,
        "Target event archive",
    )
    terminal_path = _resolve_file(
        args.terminal_path,
        "Dedicated auxiliary terminal",
    )
    startup_config = _resolve_file(
        args.startup_config,
        "Auxiliary startup config",
    )
    preset_path = _resolve_file(
        args.preset_path,
        "Auxiliary preset",
    )
    active_ex5_path = _resolve_file(
        args.active_ex5_path,
        "Active auxiliary EX5",
    )
    staged_ex5_path = _resolve_file(
        args.staged_ex5_path,
        "Staged auxiliary EX5",
    )
    staged_package_path = _resolve_file(
        args.staged_package_path,
        "Staged auxiliary package",
    )
    qualification_state_path = _resolve_file(
        args.qualification_state,
        "Auxiliary qualification state",
    )
    independent_flat_proof_path = (
        None
        if args.independent_flat_proof is None
        else _resolve_file(
            args.independent_flat_proof,
            "Independent flat proof",
        )
    )
    alignment_hold_path = args.alignment_hold_path.resolve()
    if not alignment_hold_path.name:
        raise RuntimeError("Alignment hold path must name a file")
    staged_hash = _sha256(staged_ex5_path)
    if staged_hash != args.expected_staged_ex5_sha256.upper():
        raise RuntimeError("Staged EX5 SHA256 mismatch")
    staged_package_hash = _sha256(staged_package_path)
    if (
        staged_package_hash
        != args.expected_staged_package_sha256.upper()
    ):
        raise RuntimeError("Staged package SHA256 mismatch")
    health_path = args.health.resolve()
    active_hash = _validate_runtime(
        terminal_path=terminal_path,
        startup_config=startup_config,
        preset_path=preset_path,
        expected_demo_login=args.expected_demo_login,
        active_ex5_path=active_ex5_path,
        expected_active_ex5_sha256=(
            args.expected_active_ex5_sha256
        ),
        expected_staged_ex5_sha256=(
            args.expected_staged_ex5_sha256
        ),
    )

    candidate_capture = _CachedEvents(
        candidate_telemetry,
        load_demo_telemetry_events,
    )
    target_capture = _CachedEvents(
        target_events_path,
        load_jsonl_events,
    )
    candidate_cycle_id = str(args.candidate_cycle_id)
    last_health_write = 0.0
    qualification_state = json.loads(
        qualification_state_path.read_text(encoding="utf-8")
    )
    frozen_at_utc = _frozen_deployment_utc(
        qualification_state,
        candidate_cycle_id=candidate_cycle_id,
        active_ex5_sha256=active_hash,
        staged_ex5_sha256=staged_hash,
    )
    terminal_process_id = 0
    if frozen_at_utc is not None:
        if not alignment_hold_path.is_file():
            if _exact_terminal_processes(terminal_path):
                raise RuntimeError(
                    "Alignment hold is missing while the prewarmed "
                    "auxiliary terminal is running"
                )
            _write_alignment_hold(
                alignment_hold_path,
                candidate_cycle_id=candidate_cycle_id,
                active_ex5_sha256=active_hash,
                created_at_utc=frozen_at_utc,
            )
        terminal_process_id = _ensure_exact_terminal_running(
            terminal_path,
            startup_config,
            poll_seconds=args.poll_seconds,
        )
        _write_json_atomic(
            health_path,
            {
                "status": (
                    "RESUMED_STAGED_BUILD_PREWARMED_"
                    "WAITING_FOR_TARGET_RESTART"
                ),
                "candidate_cycle_id": candidate_cycle_id,
                "frozen_at_utc": frozen_at_utc.isoformat(),
                "alignment_hold_path": str(alignment_hold_path),
                "terminal_process_id": terminal_process_id,
                "active_ex5_sha256": active_hash,
                "staged_package_sha256": staged_package_hash,
            },
        )
    else:
        independent_flat_at_utc = (
            None
            if independent_flat_proof_path is None
            else _validate_independent_flat_proof(
                independent_flat_proof_path,
                expected_login=args.expected_demo_login,
                maximum_age_seconds=(
                    args.flat_proof_max_age_seconds
                ),
            )
        )
        freeze_source = ""
        while True:
            candidate_events = candidate_capture.load()
            if _cycle_has_restart(candidate_events, candidate_cycle_id):
                _write_json_atomic(
                    health_path,
                    {
                        "status": "ABORTED_CYCLE_ALREADY_RESTARTED",
                        "candidate_cycle_id": candidate_cycle_id,
                        "active_ex5_sha256": active_hash,
                    },
                )
                return 2
            freeze_source = _candidate_freeze_source(
                candidate_events,
                cycle_id=candidate_cycle_id,
                independent_flat_at_utc=independent_flat_at_utc,
            )
            if freeze_source:
                break
            if time.monotonic() - last_health_write >= 1.0:
                _write_json_atomic(
                    health_path,
                    {
                        "status": "WAITING_FOR_AUXILIARY_FLAT",
                        "candidate_cycle_id": candidate_cycle_id,
                        "active_ex5_sha256": active_hash,
                        "staged_ex5_sha256": staged_hash,
                        **_latest_event_summary(
                            candidate_events,
                            candidate_cycle_id,
                        ),
                    },
                )
                last_health_write = time.monotonic()
            time.sleep(args.poll_seconds)

        time.sleep(args.race_guard_seconds)
        candidate_capture.identity = None
        candidate_events = candidate_capture.load()
        if _cycle_has_restart(candidate_events, candidate_cycle_id):
            _write_json_atomic(
                health_path,
                {
                    "status": "ABORTED_RESTART_RACE",
                    "candidate_cycle_id": candidate_cycle_id,
                    "active_ex5_sha256": active_hash,
                },
            )
            return 3
        if freeze_source == "independent_flat_proof":
            assert independent_flat_proof_path is not None
            independent_flat_at_utc = (
                _validate_independent_flat_proof(
                    independent_flat_proof_path,
                    expected_login=args.expected_demo_login,
                    maximum_age_seconds=(
                        args.flat_proof_max_age_seconds
                    ),
                )
            )
        elif not candidate_freeze_ready(
            candidate_events,
            cycle_id=candidate_cycle_id,
        ):
            _write_json_atomic(
                health_path,
                {
                    "status": "ABORTED_RESTART_RACE",
                    "candidate_cycle_id": candidate_cycle_id,
                    "active_ex5_sha256": active_hash,
                },
            )
            return 3
        processes = _exact_terminal_processes(terminal_path)
        stopped_process_id = _terminal_process_to_stop(
            processes,
            freeze_source=freeze_source,
        )
        if stopped_process_id:
            _stop_exact_terminal(stopped_process_id)
        if _exact_terminal_processes(terminal_path):
            raise RuntimeError(
                "Exact-path auxiliary terminal remained running after stop"
            )
        active_hash = _install_staged_ex5(
            active_ex5_path=active_ex5_path,
            expected_active_ex5_sha256=(
                args.expected_active_ex5_sha256
            ),
            staged_ex5_path=staged_ex5_path,
            expected_staged_ex5_sha256=(
                args.expected_staged_ex5_sha256
            ),
        )
        frozen_at_utc = datetime.now(tz=UTC)
        _write_alignment_hold(
            alignment_hold_path,
            candidate_cycle_id=candidate_cycle_id,
            active_ex5_sha256=active_hash,
            created_at_utc=frozen_at_utc,
        )
        _activate_staged_qualification(
            path=qualification_state_path,
            candidate_cycle_id=candidate_cycle_id,
            staged_ex5_path=staged_ex5_path,
            staged_ex5_sha256=active_hash,
            staged_package_path=staged_package_path,
            staged_package_sha256=staged_package_hash,
            deployed_at_utc=frozen_at_utc,
        )
        terminal_process_id = _ensure_exact_terminal_running(
            terminal_path,
            startup_config,
            poll_seconds=args.poll_seconds,
        )
        _write_json_atomic(
            health_path,
            {
                "status": (
                    "STAGED_BUILD_DEPLOYED_PREWARMED_"
                    "WAITING_FOR_TARGET_RESTART"
                ),
                "candidate_cycle_id": candidate_cycle_id,
                "frozen_at_utc": frozen_at_utc.isoformat(),
                "stopped_process_id": stopped_process_id,
                "terminal_process_id": terminal_process_id,
                "alignment_hold_path": str(alignment_hold_path),
                "active_ex5_sha256": active_hash,
                "staged_package_sha256": staged_package_hash,
                "candidate_freeze_source": freeze_source,
                "independent_flat_proof_utc": (
                    None
                    if independent_flat_at_utc is None
                    else independent_flat_at_utc.isoformat()
                ),
            },
        )

    target_restart: dict[str, Any] | None = None
    last_health_write = 0.0
    while target_restart is None:
        target_events = target_capture.load()
        target_restart = next_target_restart(
            target_events,
            after_utc=frozen_at_utc,
        )
        if target_restart is not None:
            break
        processes = _exact_terminal_processes(terminal_path)
        if (
            len(processes) != 1
            or int(processes[0]["ProcessId"]) != terminal_process_id
        ):
            raise RuntimeError(
                "Prewarmed auxiliary terminal identity changed"
            )
        if not alignment_hold_path.is_file():
            raise RuntimeError(
                "Alignment hold disappeared before target restart"
            )
        if _sha256(active_ex5_path) != active_hash:
            raise RuntimeError("Active EX5 changed while waiting")
        if time.monotonic() - last_health_write >= 1.0:
            _write_json_atomic(
                health_path,
                {
                    "status": (
                        "STAGED_BUILD_DEPLOYED_PREWARMED_"
                        "WAITING_FOR_TARGET_RESTART"
                    ),
                    "candidate_cycle_id": candidate_cycle_id,
                    "frozen_at_utc": frozen_at_utc.isoformat(),
                    "terminal_process_id": terminal_process_id,
                    "alignment_hold_path": str(alignment_hold_path),
                    "active_ex5_sha256": active_hash,
                },
            )
            last_health_write = time.monotonic()
        time.sleep(args.poll_seconds)

    processes = _exact_terminal_processes(terminal_path)
    if (
        len(processes) != 1
        or int(processes[0]["ProcessId"]) != terminal_process_id
    ):
        raise RuntimeError(
            "Prewarmed auxiliary terminal identity changed at release"
        )
    if _sha256(active_ex5_path) != active_hash:
        raise RuntimeError("Active EX5 changed while waiting")
    target_start_utc = _event_time(target_restart)
    target_completed_cycle_id = str(
        target_restart.get("cycle_id") or ""
    )
    released_at_utc = datetime.now(tz=UTC)
    _release_alignment_hold(alignment_hold_path)
    _write_json_atomic(
        health_path,
        {
            "status": "TARGET_RESTART_SEEN_ALIGNMENT_HOLD_RELEASED",
            "candidate_cycle_id": candidate_cycle_id,
            "target_completed_cycle_id": target_completed_cycle_id,
            "target_restart_utc": target_start_utc.isoformat(),
            "alignment_hold_released_utc": (
                released_at_utc.isoformat()
            ),
            "terminal_process_id": terminal_process_id,
            "active_ex5_sha256": active_hash,
        },
    )

    deadline = time.monotonic() + args.start_observation_seconds
    candidate_start: dict[str, Any] | None = None
    target_new_cycle = ""
    target_slots: dict[str, dict[str, Any]] = {}
    candidate_slots: dict[str, dict[str, Any]] = {}
    target_duplicate_slots: list[str] = []
    candidate_duplicate_slots: list[str] = []
    while time.monotonic() < deadline:
        target_events = target_capture.load()
        candidate_events = candidate_capture.load()
        candidate_start = _next_candidate_start(
            candidate_events,
            excluded_cycle_id=candidate_cycle_id,
            after_utc=frozen_at_utc,
        )
        target_new_cycle = _target_new_cycle_id(
            target_events,
            completed_cycle_id=target_completed_cycle_id,
            restart_utc=target_start_utc,
        )
        if target_new_cycle:
            target_slots, target_duplicate_slots = _initial_grid(
                target_events,
                target_new_cycle,
            )
        if candidate_start is not None:
            candidate_slots, candidate_duplicate_slots = _initial_grid(
                candidate_events,
                str(candidate_start.get("cycle_id") or ""),
            )
        if (
            candidate_start is not None
            and (
                target_duplicate_slots
                or candidate_duplicate_slots
                or (
                    len(target_slots) == 60
                    and len(candidate_slots) == 60
                )
            )
        ):
            break
        time.sleep(args.poll_seconds)

    if candidate_start is None:
        _write_json_atomic(
            health_path,
            {
                "status": "START_OBSERVATION_INCOMPLETE",
                "candidate_cycle_id": candidate_cycle_id,
                "target_completed_cycle_id": target_completed_cycle_id,
                "target_restart_seen": True,
                "candidate_start_seen": False,
                "terminal_process_id": terminal_process_id,
                "active_ex5_sha256": active_hash,
            },
        )
        return 4

    candidate_start_utc = _event_time(candidate_start)
    start_delta_seconds = (
        candidate_start_utc - target_start_utc
    ).total_seconds()
    target_anchor = _anchor(target_slots)
    candidate_anchor = _anchor(candidate_slots)
    anchor_delta = (
        None
        if target_anchor is None or candidate_anchor is None
        else candidate_anchor - target_anchor
    )
    complete_initial_grids = (
        set(target_slots) == EXPECTED_COMMENTS
        and set(candidate_slots) == EXPECTED_COMMENTS
        and not target_duplicate_slots
        and not candidate_duplicate_slots
    )
    aligned = (
        abs(start_delta_seconds) <= args.start_tolerance_seconds
        and complete_initial_grids
    )
    new_candidate_cycle_id = str(
        candidate_start.get("cycle_id") or ""
    )
    _record_alignment_qualification(
        path=qualification_state_path,
        previous_candidate_cycle_id=candidate_cycle_id,
        candidate_cycle_id=new_candidate_cycle_id,
        candidate_start_utc=candidate_start_utc,
        target_cycle_id=target_new_cycle,
        aligned=aligned,
    )
    _write_json_atomic(
        health_path,
        {
            "status": (
                "ALIGNED_CYCLE_STARTED"
                if aligned
                else "ALIGNED_CYCLE_STARTED_DUPLICATE_SLOTS"
                if target_duplicate_slots or candidate_duplicate_slots
                else "ALIGNED_CYCLE_STARTED_INCOMPLETE_GRID"
                if not complete_initial_grids
                else "ALIGNED_CYCLE_STARTED_OUTSIDE_TOLERANCE"
            ),
            "previous_candidate_cycle_id": candidate_cycle_id,
            "candidate_cycle_id": new_candidate_cycle_id,
            "target_completed_cycle_id": target_completed_cycle_id,
            "target_cycle_id": target_new_cycle,
            "target_start_utc": target_start_utc.isoformat(),
            "candidate_start_utc": candidate_start_utc.isoformat(),
            "candidate_minus_target_start_seconds": (
                start_delta_seconds
            ),
            "start_tolerance_seconds": args.start_tolerance_seconds,
            "target_anchor": target_anchor,
            "candidate_anchor": candidate_anchor,
            "candidate_minus_target_anchor": anchor_delta,
            "target_initial_unique_slots": len(target_slots),
            "candidate_initial_unique_slots": len(candidate_slots),
            "target_duplicate_slots": target_duplicate_slots,
            "candidate_duplicate_slots": candidate_duplicate_slots,
            "complete_initial_grids": complete_initial_grids,
            "terminal_process_id": terminal_process_id,
            "active_ex5_sha256": active_hash,
        },
    )
    return 0 if aligned else 5


if __name__ == "__main__":
    raise SystemExit(main())
