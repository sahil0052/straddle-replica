from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable
import zipfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.flat_boundary import (  # noqa: E402
    evaluate_freeze_readiness,
    freeze_remote_candidate,
    read_last_two_jsonl,
)


UTC = timezone.utc
SSH_ALIAS = "nishahomes-vps"
CONTAINER = "straddle-fidelity-independent-demo"


def _parse_utc(value: object) -> datetime:
    parsed = datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _zip_entry_sha256(path: Path, entry_name: str) -> str:
    digest = hashlib.sha256()
    with zipfile.ZipFile(path) as archive:
        with archive.open(entry_name) as stream:
            for block in iter(
                lambda: stream.read(1024 * 1024),
                b"",
            ):
                digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_evidence(
    *,
    candidate_root: Path,
    observer_state_path: Path,
    archive_state_path: Path,
    qualification_state_path: Path,
) -> dict[str, Any]:
    current = _load_json(candidate_root / "current-session.json")
    session_dir = Path(str(current["session_dir"])).resolve()
    root = candidate_root.resolve()
    if root not in session_dir.parents:
        raise RuntimeError(
            f"candidate session escaped observer root: {session_dir}"
        )
    snapshot_files = sorted(session_dir.glob("snapshots-*.jsonl"))
    if not snapshot_files:
        raise RuntimeError("candidate snapshot stream is missing")
    previous_snapshot, latest_snapshot = read_last_two_jsonl(
        snapshot_files[-1]
    )
    return {
        "session_dir": str(session_dir),
        "heartbeat": _load_json(session_dir / "heartbeat.json"),
        "manifest": _load_json(session_dir / "manifest.json"),
        "previous_snapshot": previous_snapshot,
        "latest_snapshot": latest_snapshot,
        "observer_state": _load_json(observer_state_path),
        "archive_state": _load_json(archive_state_path),
        "qualification_state": _load_json(
            qualification_state_path
        ),
    }


def _run_ssh(command: str) -> str:
    completed = subprocess.run(
        ["ssh", SSH_ALIAS, command],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"candidate SSH command failed ({completed.returncode}): "
            f"{detail[:300]}"
        )
    return completed.stdout.strip()


def _restart_old_candidate() -> None:
    result = _run_ssh(f"docker start {CONTAINER}")
    if result.strip() != CONTAINER:
        raise RuntimeError(
            "old candidate container restart was not acknowledged"
        )


def _post_stop_flat_confirmation(
    *,
    stopped_at_utc: datetime,
    candidate_root: Path,
    observer_state_path: Path,
    archive_state_path: Path,
    qualification_state_path: Path,
    timeout_seconds: float,
    load_evidence: Callable[..., dict[str, Any]] = _load_evidence,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    latest_evidence: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            latest_evidence = load_evidence(
                candidate_root=candidate_root,
                observer_state_path=observer_state_path,
                archive_state_path=archive_state_path,
                qualification_state_path=qualification_state_path,
            )
        except (
            KeyError,
            OSError,
            RuntimeError,
            ValueError,
            json.JSONDecodeError,
        ):
            sleep(0.2)
            continue
        heartbeat = latest_evidence["heartbeat"]
        previous = latest_evidence["previous_snapshot"]
        latest = latest_evidence["latest_snapshot"]
        non_flat = bool(
            heartbeat.get("positions_total")
            or heartbeat.get("orders_total")
            or previous.get("positions")
            or previous.get("orders")
            or latest.get("positions")
            or latest.get("orders")
        )
        if non_flat:
            return False, latest_evidence
        if _parse_utc(latest["capture_time_utc"]) > stopped_at_utc:
            return True, latest_evidence
        sleep(0.2)
    return False, latest_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate-root",
        type=Path,
        default=Path(
            r"D:\MT5IndependentCandidateData\isolated-live"
        ),
    )
    parser.add_argument(
        "--observer-state",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--archive-state",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--qualification-state",
        type=Path,
        required=True,
    )
    parser.add_argument("--health", type=Path, required=True)
    parser.add_argument(
        "--staged-package",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--expected-staged-package-sha256",
        required=True,
    )
    parser.add_argument(
        "--expected-active-ex5-sha256",
        required=True,
    )
    parser.add_argument(
        "--expected-staged-ex5-sha256",
        required=True,
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=0.25,
    )
    parser.add_argument(
        "--max-heartbeat-age-seconds",
        type=float,
        default=5.0,
    )
    args = parser.parse_args(argv)
    if args.poll_seconds < 0.1:
        parser.error("--poll-seconds must be at least 0.1")

    package_hash = _sha256(args.staged_package)
    embedded_hash = _zip_entry_sha256(
        args.staged_package,
        "candidate/StraddleReplica.ex5",
    )
    if (
        package_hash.lower()
        != args.expected_staged_package_sha256.lower()
    ):
        raise RuntimeError("staged package SHA256 mismatch")
    if (
        embedded_hash.lower()
        != args.expected_staged_ex5_sha256.lower()
    ):
        raise RuntimeError("staged EX5 SHA256 mismatch")

    last_health_write = 0.0
    while True:
        now = datetime.now(tz=UTC)
        try:
            evidence = _load_evidence(
                candidate_root=args.candidate_root,
                observer_state_path=args.observer_state,
                archive_state_path=args.archive_state,
                qualification_state_path=args.qualification_state,
            )
            qualification = evidence["qualification_state"]
            if str(qualification.get("staged_status") or "") not in {
                "LOCAL_VERIFIED_AWAITING_NATURAL_FLAT_BOUNDARY",
            }:
                _write_json_atomic(
                    args.health,
                    {
                        "status": "STAGED_BUILD_NO_LONGER_WAITING",
                        "updated_at_utc": now.isoformat(),
                        "staged_status": qualification.get(
                            "staged_status"
                        ),
                    },
                )
                return 0
            readiness = evaluate_freeze_readiness(
                heartbeat=evidence["heartbeat"],
                manifest=evidence["manifest"],
                previous_snapshot=evidence["previous_snapshot"],
                latest_snapshot=evidence["latest_snapshot"],
                observer_state=evidence["observer_state"],
                archive_state=evidence["archive_state"],
                qualification_state=qualification,
                now_utc=now,
                expected_login=110971967,
                expected_server="MetaQuotes-Demo",
                expected_active_build_id=(
                    args.expected_active_ex5_sha256
                ),
                expected_staged_build_id=(
                    args.expected_staged_ex5_sha256
                ),
                max_heartbeat_age_seconds=(
                    args.max_heartbeat_age_seconds
                ),
                minimum_flat_confirmation_seconds=0.25,
            )
            if not readiness["ready"]:
                if time.monotonic() - last_health_write >= 1.0:
                    _write_json_atomic(
                        args.health,
                        {
                            "status": (
                                "WAITING_FOR_NATURAL_FLAT_BOUNDARY"
                            ),
                            "updated_at_utc": now.isoformat(),
                            "reasons": readiness["reasons"],
                            "positions_total": evidence[
                                "heartbeat"
                            ].get("positions_total"),
                            "orders_total": evidence[
                                "heartbeat"
                            ].get("orders_total"),
                            "active_cycle_id": qualification.get(
                                "active_cycle_id"
                            ),
                            "active_build_id": qualification.get(
                                "active_build_id"
                            ),
                            "staged_build_id": qualification.get(
                                "staged_build_id"
                            ),
                            "staged_package_sha256": package_hash,
                        },
                    )
                    last_health_write = time.monotonic()
                time.sleep(args.poll_seconds)
                continue

            freeze_started = datetime.now(tz=UTC)
            frozen = freeze_remote_candidate(
                run_ssh=_run_ssh,
                expected_active_ex5_sha256=(
                    args.expected_active_ex5_sha256
                ),
            )
            confirmed, post_stop = _post_stop_flat_confirmation(
                stopped_at_utc=freeze_started,
                candidate_root=args.candidate_root,
                observer_state_path=args.observer_state,
                archive_state_path=args.archive_state,
                qualification_state_path=args.qualification_state,
                timeout_seconds=8.0,
            )
            if not confirmed:
                _restart_old_candidate()
                _write_json_atomic(
                    args.health,
                    {
                        "status": (
                            "FLAT_RACE_ABORTED_OLD_CONTAINER_RESTARTED"
                        ),
                        "updated_at_utc": datetime.now(
                            tz=UTC
                        ).isoformat(),
                        "container_id": frozen["container_id"],
                        "positions_total": dict(
                            post_stop.get("heartbeat") or {}
                        ).get("positions_total"),
                        "orders_total": dict(
                            post_stop.get("heartbeat") or {}
                        ).get("orders_total"),
                    },
                )
                time.sleep(2.0)
                continue

            _write_json_atomic(
                args.health,
                {
                    "status": "FLAT_BOUNDARY_FROZEN",
                    "updated_at_utc": datetime.now(
                        tz=UTC
                    ).isoformat(),
                    "frozen_at_utc": freeze_started.isoformat(),
                    "container_name": CONTAINER,
                    "container_id": frozen["container_id"],
                    "active_ex5_sha256": frozen[
                        "active_ex5_sha256"
                    ],
                    "staged_ex5_sha256": embedded_hash,
                    "staged_package": str(
                        args.staged_package.resolve()
                    ),
                    "staged_package_sha256": package_hash,
                    "positions_total": 0,
                    "orders_total": 0,
                    "ready_for_deployment": True,
                },
            )
            return 0
        except (
            KeyError,
            OSError,
            RuntimeError,
            ValueError,
            json.JSONDecodeError,
            subprocess.SubprocessError,
            zipfile.BadZipFile,
        ) as error:
            _write_json_atomic(
                args.health,
                {
                    "status": "WAITING_FOR_SAFE_EVIDENCE",
                    "updated_at_utc": datetime.now(
                        tz=UTC
                    ).isoformat(),
                    "error_type": type(error).__name__,
                    "error": str(error)[:500],
                },
            )
            time.sleep(max(args.poll_seconds, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
