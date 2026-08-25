from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import tempfile
from typing import Any, Protocol


@dataclass(frozen=True)
class RemoteShadowPaths:
    root: PurePosixPath
    command: PurePosixPath
    ack: PurePosixPath


def validate_remote_path(
    root: PurePosixPath,
    path: PurePosixPath,
) -> PurePosixPath:
    if not root.is_absolute() or not path.is_absolute():
        raise ValueError("Remote shadow path is outside candidate root")
    if ".." in path.parts:
        raise ValueError("Remote shadow path is outside candidate root")
    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "Remote shadow path is outside candidate root"
        ) from error
    if path == root:
        raise ValueError("Remote shadow path is outside candidate root")
    return path


class ShadowTransport(Protocol):
    def read_ack(self) -> dict[str, Any]: ...

    def write_command(self, payload: dict[str, Any]) -> None: ...


class FileShadowTransport:
    def __init__(self, command_path: Path, ack_path: Path) -> None:
        self.command_path = command_path
        self.ack_path = ack_path

    def read_ack(self) -> dict[str, Any]:
        if not self.ack_path.exists():
            return {"status": "UNKNOWN", "command_seq": 0, "cycle_id": ""}
        with self.ack_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows[-1] if rows else {
            "status": "UNKNOWN",
            "command_seq": 0,
            "cycle_id": "",
        }

    def write_command(self, payload: dict[str, Any]) -> None:
        temporary = self.command_path.with_suffix(".csv.tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(payload))
            writer.writeheader()
            writer.writerow(payload)
        temporary.replace(self.command_path)


class OpenSshShadowTransport:
    def __init__(
        self,
        *,
        ssh_alias: str,
        paths: RemoteShadowPaths,
    ) -> None:
        self.ssh_alias = ssh_alias
        self.paths = paths
        validate_remote_path(paths.root, paths.command)
        validate_remote_path(paths.root, paths.ack)

    def _ssh(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["ssh", self.ssh_alias, command],
            capture_output=True,
            text=True,
            check=False,
        )

    def read_ack(self) -> dict[str, Any]:
        command = f"cat -- {shlex.quote(str(self.paths.ack))}"
        completed = self._ssh(command)
        if completed.returncode != 0:
            return {"status": "UNKNOWN", "command_seq": 0, "cycle_id": ""}
        rows = list(csv.DictReader(completed.stdout.splitlines()))
        return rows[-1] if rows else {
            "status": "UNKNOWN",
            "command_seq": 0,
            "cycle_id": "",
        }

    def write_command(self, payload: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "command.csv"
            with local.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=tuple(payload))
                writer.writeheader()
                writer.writerow(payload)
            remote_tmp = self.paths.command.with_suffix(".csv.tmp")
            validate_remote_path(self.paths.root, remote_tmp)
            subprocess.run(
                [
                    "scp",
                    str(local),
                    f"{self.ssh_alias}:{remote_tmp}",
                ],
                check=True,
            )
            completed = self._ssh(
                "mv -f -- "
                f"{shlex.quote(str(remote_tmp))} "
                f"{shlex.quote(str(self.paths.command))}"
            )
            if completed.returncode != 0:
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    completed.args,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )
