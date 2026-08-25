from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


COMMON_FILES = (
    "wineprefix/drive_c/users/mt5/AppData/Roaming/MetaQuotes/"
    "Terminal/Common/Files"
)
TELEMETRY_NAME = "StraddleReplicaV2_901018_XAUUSD.csv"
MANIFEST_NAME = "StraddleReplicaV2_901018_XAUUSD_manifest.csv"
TELEMETRY_HEADER_PREFIX = b"utc_time,server_time,cycle_id,"
MANIFEST_HEADER = b"key,value\n"
PREFIX_HASH_BYTES = 4096
REMOTE_SYNC_SCRIPT = b"""\
set -eu
remote_size=$(wc -c < "$TELEMETRY_PATH")
manifest_size=$(wc -c < "$MANIFEST_PATH")
remote_prefix_sha=$(
  head -c 4096 "$TELEMETRY_PATH" | sha256sum | awk '{print $1}'
)
mode=append
start=$LOCAL_SIZE
if [ "$LOCAL_SIZE" -eq 0 ] || \
   [ "$LOCAL_SIZE" -gt "$remote_size" ] || \
   [ "$LOCAL_PREFIX_SHA" != "$remote_prefix_sha" ]; then
  mode=full
  start=0
fi
delta=$((remote_size - start))
printf 'SRP1 %s %s %s %s\\n' \
  "$mode" "$remote_size" "$delta" "$manifest_size"
if [ "$delta" -gt 0 ]; then
  tail -c "+$((start + 1))" "$TELEMETRY_PATH" | head -c "$delta"
fi
head -c "$manifest_size" "$MANIFEST_PATH"
"""
UTC = timezone.utc


def _validate_csv_snapshot(
    path: Path,
    *,
    expected_header: bytes,
    prefix: bool = False,
) -> None:
    if path.stat().st_size <= len(expected_header):
        raise ValueError(f"{path.name} is empty or incomplete")
    with path.open("rb") as handle:
        header = handle.readline()
        handle.seek(-1, os.SEEK_END)
        final_byte = handle.read(1)
    if final_byte != b"\n":
        raise ValueError(
            f"{path.name} must end with a complete newline"
        )
    normalized_header = header.rstrip(b"\r\n")
    normalized_expected = expected_header.rstrip(b"\r\n")
    header_matches = (
        normalized_header.startswith(normalized_expected)
        if prefix
        else normalized_header == normalized_expected
    )
    if not header_matches:
        raise ValueError(f"{path.name} has an unexpected CSV header")


def _local_telemetry_state(path: Path) -> tuple[int, str]:
    if not path.exists():
        return 0, hashlib.sha256(b"").hexdigest()
    try:
        _validate_csv_snapshot(
            path,
            expected_header=TELEMETRY_HEADER_PREFIX,
            prefix=True,
        )
    except (OSError, ValueError):
        return 0, hashlib.sha256(b"").hexdigest()
    size = path.stat().st_size
    with path.open("rb") as handle:
        prefix = handle.read(min(PREFIX_HASH_BYTES, size))
    return size, hashlib.sha256(prefix).hexdigest()


def _copy_remote_snapshot(
    *,
    ssh_alias: str,
    remote_base: str,
    local_size: int,
    local_prefix_sha: str,
    destination: Path,
) -> None:
    telemetry_path = remote_base + "/" + TELEMETRY_NAME
    manifest_path = remote_base + "/" + MANIFEST_NAME
    command = [
        "ssh",
        "-T",
        "-q",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ConnectionAttempts=1",
        ssh_alias,
        "env",
        f"LOCAL_SIZE={local_size}",
        f"LOCAL_PREFIX_SHA={local_prefix_sha}",
        f"TELEMETRY_PATH={telemetry_path}",
        f"MANIFEST_PATH={manifest_path}",
        "sh",
        "-s",
    ]
    with destination.open("wb") as output:
        completed = subprocess.run(
            command,
            input=REMOTE_SYNC_SCRIPT,
            stdout=output,
            stderr=subprocess.DEVNULL,
            timeout=45,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            "Candidate evidence copy failed "
            f"with exit code {completed.returncode}"
        )


def _copy_exact(source, destination, byte_count: int) -> None:
    remaining = byte_count
    while remaining:
        chunk = source.read(min(1024 * 1024, remaining))
        if not chunk:
            raise ValueError("Candidate evidence snapshot is truncated")
        destination.write(chunk)
        remaining -= len(chunk)


def _materialize_snapshot(
    *,
    bundle_path: Path,
    telemetry_output: Path,
    telemetry_stage: Path,
    manifest_stage: Path,
    local_size: int,
) -> dict[str, int | str]:
    with bundle_path.open("rb") as bundle:
        header = bundle.readline(256)
        try:
            magic, mode, remote_size_text, delta_text, manifest_text = (
                header.decode("ascii").strip().split()
            )
            remote_size = int(remote_size_text)
            delta_size = int(delta_text)
            manifest_size = int(manifest_text)
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError(
                "Candidate evidence snapshot has an invalid frame"
            ) from error
        if magic != "SRP1" or mode not in {"append", "full"}:
            raise ValueError(
                "Candidate evidence snapshot has an invalid frame"
            )
        if min(remote_size, delta_size, manifest_size) < 0:
            raise ValueError(
                "Candidate evidence snapshot has an invalid size"
            )
        if mode == "append":
            if (
                not telemetry_output.exists()
                or telemetry_output.stat().st_size != local_size
                or remote_size - local_size != delta_size
            ):
                raise ValueError(
                    "Candidate telemetry append base changed during sync"
                )
            shutil.copyfile(telemetry_output, telemetry_stage)
            telemetry_mode = "ab"
        else:
            if remote_size != delta_size:
                raise ValueError(
                    "Candidate full telemetry snapshot size is inconsistent"
                )
            telemetry_mode = "wb"
        with telemetry_stage.open(telemetry_mode) as telemetry:
            _copy_exact(bundle, telemetry, delta_size)
        with manifest_stage.open("wb") as manifest:
            _copy_exact(bundle, manifest, manifest_size)
        if bundle.read(1):
            raise ValueError(
                "Candidate evidence snapshot has trailing bytes"
            )
    return {
        "telemetry_bytes": remote_size,
        "manifest_bytes": manifest_size,
        "transferred_telemetry_bytes": delta_size,
        "transfer_mode": mode,
    }


def sync_once(
    *,
    ssh_alias: str,
    remote_root: str,
    telemetry_output: Path,
    manifest_output: Path,
) -> dict[str, int]:
    telemetry_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    telemetry_stage = telemetry_output.with_suffix(
        telemetry_output.suffix + ".sync.tmp"
    )
    manifest_stage = manifest_output.with_suffix(
        manifest_output.suffix + ".sync.tmp"
    )
    bundle_stage = telemetry_output.with_suffix(
        telemetry_output.suffix + ".sync.bundle.tmp"
    )
    remote_base = remote_root.rstrip("/") + "/" + COMMON_FILES
    local_size, local_prefix_sha = _local_telemetry_state(
        telemetry_output
    )
    try:
        _copy_remote_snapshot(
            ssh_alias=ssh_alias,
            remote_base=remote_base,
            local_size=local_size,
            local_prefix_sha=local_prefix_sha,
            destination=bundle_stage,
        )
        result = _materialize_snapshot(
            bundle_path=bundle_stage,
            telemetry_output=telemetry_output,
            telemetry_stage=telemetry_stage,
            manifest_stage=manifest_stage,
            local_size=local_size,
        )
        _validate_csv_snapshot(
            telemetry_stage,
            expected_header=TELEMETRY_HEADER_PREFIX,
            prefix=True,
        )
        _validate_csv_snapshot(
            manifest_stage,
            expected_header=MANIFEST_HEADER,
        )
        os.replace(telemetry_stage, telemetry_output)
        os.replace(manifest_stage, manifest_output)
        return result
    finally:
        bundle_stage.unlink(missing_ok=True)
        telemetry_stage.unlink(missing_ok=True)
        manifest_stage.unlink(missing_ok=True)


def _write_health(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh-alias", required=True)
    parser.add_argument("--remote-root", required=True)
    parser.add_argument("--telemetry-output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--health", required=True, type=Path)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_seconds < 0.5:
        parser.error("--poll-seconds must be at least 0.5")

    while True:
        try:
            result = sync_once(
                ssh_alias=args.ssh_alias,
                remote_root=args.remote_root,
                telemetry_output=args.telemetry_output,
                manifest_output=args.manifest_output,
            )
            health = {
                "status": "RUNNING",
                "updated_at_utc": datetime.now(tz=UTC).isoformat(),
                **result,
            }
            _write_health(args.health, health)
            if args.once:
                print(json.dumps(result, sort_keys=True))
                return 0
        except (
            OSError,
            RuntimeError,
            ValueError,
            subprocess.SubprocessError,
        ) as error:
            _write_health(
                args.health,
                {
                    "status": "WAITING_FOR_SOURCE",
                    "updated_at_utc": datetime.now(tz=UTC).isoformat(),
                    "error_type": type(error).__name__,
                    "error": str(error),
                },
            )
            if args.once:
                return 1
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
