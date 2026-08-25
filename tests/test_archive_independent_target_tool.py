from __future__ import annotations

import json

from tools import archive_independent_target


def test_write_health_retries_temporary_replace_denial(
    tmp_path,
    monkeypatch,
) -> None:
    health_path = tmp_path / "archive-health.json"
    real_replace = archive_independent_target.os.replace
    attempts = 0

    def temporarily_denied(source, destination) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporary Windows file lock")
        real_replace(source, destination)

    monkeypatch.setattr(
        archive_independent_target.os,
        "replace",
        temporarily_denied,
    )

    archive_independent_target._write_health(
        health_path,
        {"status": "RUNNING"},
    )

    assert attempts == 2
    assert json.loads(health_path.read_text(encoding="utf-8")) == {
        "status": "RUNNING"
    }
