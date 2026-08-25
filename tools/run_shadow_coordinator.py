from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import sys
import time


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from straddle_replica.shadow_coordinator import (  # noqa: E402
    ShadowCoordinator,
    ShadowCoordinatorConfig,
    load_probe_events,
)
from straddle_replica.observer_adapter import (  # noqa: E402
    ObserverAdapterConfig,
    ObserverEventAdapter,
)
from straddle_replica.shadow_transport import (  # noqa: E402
    OpenSshShadowTransport,
    RemoteShadowPaths,
)


def _write_health(
    path: Path | None,
    payload: dict[str, object],
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _utc_now_text() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--target-probe-root", type=Path)
    source.add_argument("--target-observer-root", type=Path)
    parser.add_argument("--observer-state-path", type=Path)
    parser.add_argument(
        "--heartbeat-max-age-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument("--command-path", type=Path)
    parser.add_argument("--ack-path", type=Path)
    parser.add_argument("--remote-ssh-alias")
    parser.add_argument(
        "--remote-root",
        default="/opt/straddle-fidelity-candidate",
    )
    parser.add_argument("--remote-command-path")
    parser.add_argument("--remote-ack-path")
    parser.add_argument("--state-path", required=True, type=Path)
    parser.add_argument("--target-archive-path", required=True, type=Path)
    parser.add_argument("--command-ttl-ms", type=int, default=2_000)
    parser.add_argument("--pair-window-ms", type=int, default=1_000)
    parser.add_argument("--poll-ms", type=int, default=100)
    parser.add_argument("--retry-ms", type=int, default=1_000)
    parser.add_argument("--health-path", type=Path)
    parser.add_argument("--active", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_ms < 20:
        parser.error("--poll-ms must be at least 20")
    if args.retry_ms < 20:
        parser.error("--retry-ms must be at least 20")
    if args.target_observer_root and args.observer_state_path is None:
        parser.error(
            "--observer-state-path is required with "
            "--target-observer-root"
        )
    transport = None
    command_path = args.command_path
    ack_path = args.ack_path
    if args.remote_ssh_alias:
        if not args.remote_command_path or not args.remote_ack_path:
            parser.error(
                "--remote-command-path and --remote-ack-path are "
                "required with --remote-ssh-alias"
            )
        expected_root = PurePosixPath(
            "/opt/straddle-fidelity-candidate"
        )
        remote_root = PurePosixPath(args.remote_root)
        if remote_root != expected_root:
            parser.error(
                "Remote shadow candidate root must be "
                "/opt/straddle-fidelity-candidate"
            )
        try:
            transport = OpenSshShadowTransport(
                ssh_alias=args.remote_ssh_alias,
                paths=RemoteShadowPaths(
                    root=remote_root,
                    command=PurePosixPath(args.remote_command_path),
                    ack=PurePosixPath(args.remote_ack_path),
                ),
            )
        except ValueError as error:
            parser.error(str(error))
        command_path = command_path or Path("remote-command.csv")
        ack_path = ack_path or Path("remote-ack.csv")
    elif command_path is None or ack_path is None:
        parser.error(
            "--command-path and --ack-path are required without "
            "--remote-ssh-alias"
        )

    coordinator = ShadowCoordinator(
        ShadowCoordinatorConfig(
            command_path=command_path,
            ack_path=ack_path,
            state_path=args.state_path,
            target_archive_path=args.target_archive_path,
            observe_only=not args.active,
            command_ttl_ms=args.command_ttl_ms,
            pair_window_ms=args.pair_window_ms,
        ),
        transport=transport,
    )
    adapter = (
        ObserverEventAdapter(
            ObserverAdapterConfig(
                observer_root=args.target_observer_root,
                state_path=args.observer_state_path,
                heartbeat_max_age_seconds=(
                    args.heartbeat_max_age_seconds
                ),
            )
        )
        if args.target_observer_root is not None
        else None
    )
    while True:
        try:
            events = (
                adapter.poll()
                if adapter is not None
                else load_probe_events(
                    args.target_probe_root,
                    minimum_sequence=coordinator.last_target_sequence,
                    expected_session_id=coordinator.target_session_id,
                )
            )
            result = coordinator.process_events(events)
        except (
            FileNotFoundError,
            OSError,
            RuntimeError,
            json.JSONDecodeError,
        ) as error:
            _write_health(
                args.health_path,
                {
                    "status": "WAITING_FOR_TARGET",
                    "updated_at_utc": _utc_now_text(),
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            if args.once:
                raise
            time.sleep(args.retry_ms / 1000.0)
            continue
        _write_health(
            args.health_path,
            {
                "status": "RUNNING",
                "updated_at_utc": _utc_now_text(),
                **result,
            },
        )
        if args.once:
            print(json.dumps(result, sort_keys=True))
            return 0
        time.sleep(args.poll_ms / 1000.0)


if __name__ == "__main__":
    raise SystemExit(main())
