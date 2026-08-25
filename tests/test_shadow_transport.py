from pathlib import PurePosixPath
import subprocess

import pytest

from straddle_replica.shadow_transport import (
    OpenSshShadowTransport,
    RemoteShadowPaths,
    validate_remote_path,
)


ROOT = PurePosixPath("/opt/straddle-fidelity-candidate")


def test_remote_paths_are_confined_to_candidate_root() -> None:
    paths = RemoteShadowPaths(
        root=ROOT,
        command=ROOT / "common/StraddleShadow/command.csv",
        ack=ROOT / "common/StraddleShadow/ack.csv",
    )

    assert validate_remote_path(paths.root, paths.command) == paths.command
    assert validate_remote_path(paths.root, paths.ack) == paths.ack


def test_remote_path_escape_is_rejected() -> None:
    for escaped in (
        PurePosixPath("/opt/straddle-replica-demo/command.csv"),
        ROOT / "../straddle-replica-demo/command.csv",
    ):
        with pytest.raises(ValueError, match="candidate root"):
            validate_remote_path(ROOT, escaped)


def test_openssh_transport_uses_only_candidate_cat_scp_and_mv(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append([str(value) for value in args])
        stdout = ""
        if args[0] == "ssh" and str(args[2]).startswith("cat -- "):
            stdout = (
                "schema_version,command_seq,status,cycle_id\n"
                "1,7,FLAT,cycle-1\n"
            )
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=stdout,
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    paths = RemoteShadowPaths(
        root=ROOT,
        command=ROOT / "common/StraddleShadow/command.csv",
        ack=ROOT / "common/StraddleShadow/ack.csv",
    )
    transport = OpenSshShadowTransport(
        ssh_alias="candidate-vps",
        paths=paths,
    )

    assert transport.read_ack()["status"] == "FLAT"
    transport.write_command(
        {
            "schema_version": 1,
            "command_seq": 8,
            "command": "RESET",
        }
    )

    scp = next(call for call in calls if call[0] == "scp")
    assert scp[-1] == (
        "candidate-vps:/opt/straddle-fidelity-candidate/common/"
        "StraddleShadow/command.csv.tmp"
    )
    remote_commands = [
        call[2] for call in calls if call[0] == "ssh"
    ]
    assert all(
        command.startswith("cat -- ") or command.startswith("mv -f -- ")
        for command in remote_commands
    )
    joined = " ".join(" ".join(call) for call in calls)
    for forbidden in (
        "docker",
        "systemctl",
        "kill",
        " rm ",
        "/opt/straddle-replica-demo",
    ):
        assert forbidden not in joined
