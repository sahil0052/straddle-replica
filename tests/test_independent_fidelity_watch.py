from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (
    ROOT
    / "scripts"
    / "install_independent_fidelity_watch_task.ps1"
)
TOOL = ROOT / "tools" / "watch_independent_fidelity.py"


def test_run_once_uses_persisted_cycle_exclusions(
    tmp_path,
    monkeypatch,
) -> None:
    watch = importlib.import_module(
        "tools.watch_independent_fidelity"
    )
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps(
            {
                "active_build_id": "build-1",
                "active_deployed_utc": "2026-08-12T16:00:00Z",
                "qualification_started_utc": None,
                "excluded_target_cycle_ids": ["target-bad"],
                "excluded_candidate_cycle_ids": ["candidate-bad"],
            }
        ),
        encoding="utf-8",
    )
    captured: list[str] = []

    def fake_compare(arguments):
        captured.extend(arguments)
        return 2

    monkeypatch.setattr(
        watch.compare_independent_cycles,
        "main",
        fake_compare,
    )
    monkeypatch.setattr(
        watch,
        "load_demo_telemetry_events",
        lambda _: [],
    )

    result = watch.run_once(
        qualification_state=qualification,
        target_events=tmp_path / "target.jsonl",
        candidate_telemetry=tmp_path / "candidate.csv",
        reports_dir=tmp_path / "reports",
        pairing="ordinal",
        max_start_gap_seconds=86400,
        normalized_price_tolerance=0.02,
    )

    assert result["status"] == "WAITING_FOR_CLEAN_CYCLE_START"
    assert result["pair_count"] == 0
    assert "--exclude-target-cycle-id" in captured
    assert "target-bad" in captured
    assert "--exclude-candidate-cycle-id" in captured
    assert "candidate-bad" in captured
    assert "2026-08-12T16:00:00Z" in captured
    assert "--target-start-grace-seconds" in captured
    grace_index = captured.index("--target-start-grace-seconds")
    assert captured[grace_index + 1] == "5.0"


def test_first_clean_candidate_start_sets_qualification_window(
    tmp_path,
    monkeypatch,
) -> None:
    watch = importlib.import_module(
        "tools.watch_independent_fidelity"
    )
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps(
            {
                "active_build_id": "build-1",
                "active_deployed_utc": "2026-08-12T16:00:00Z",
                "qualification_started_utc": None,
                "active_cycle_id": "candidate-bad",
                "active_cycle_eligible": False,
                "excluded_candidate_cycle_ids": ["candidate-bad"],
                "excluded_target_cycle_ids": [],
            }
        ),
        encoding="utf-8",
    )
    captured: list[str] = []
    monkeypatch.setattr(
        watch,
        "load_demo_telemetry_events",
        lambda _: [
            {
                "kind": "cycle_start",
                "cycle_id": "candidate-bad",
                "time_utc": "2026-08-12T18:00:00Z",
            },
            {
                "kind": "cycle_start",
                "cycle_id": "candidate-clean",
                "time_utc": "2026-08-12T19:00:00Z",
            },
        ],
        raising=False,
    )

    def fake_compare(arguments):
        captured.extend(arguments)
        return 2

    monkeypatch.setattr(
        watch.compare_independent_cycles,
        "main",
        fake_compare,
    )

    watch.run_once(
        qualification_state=qualification,
        target_events=tmp_path / "target.jsonl",
        candidate_telemetry=tmp_path / "candidate.csv",
        reports_dir=tmp_path / "reports",
        pairing="ordinal",
        max_start_gap_seconds=86400,
        normalized_price_tolerance=0.02,
    )

    state = json.loads(qualification.read_text(encoding="utf-8"))
    assert state["qualification_started_utc"] == (
        "2026-08-12T19:00:00Z"
    )
    assert state["active_cycle_id"] == "candidate-clean"
    assert state["active_cycle_eligible"] is True
    assert "2026-08-12T19:00:00Z" in captured


def test_alignment_controller_policy_waits_for_validated_start(
    tmp_path,
    monkeypatch,
) -> None:
    watch = importlib.import_module(
        "tools.watch_independent_fidelity"
    )
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps(
            {
                "active_build_id": "build-2",
                "active_deployed_utc": "2026-08-12T18:00:00Z",
                "qualification_started_utc": None,
                "qualification_start_policy": "alignment_controller",
                "active_cycle_id": "candidate-excluded",
                "active_cycle_eligible": False,
                "excluded_candidate_cycle_ids": [
                    "candidate-excluded"
                ],
                "excluded_target_cycle_ids": [],
            }
        ),
        encoding="utf-8",
    )
    comparator_called = False

    def fake_compare(arguments):
        nonlocal comparator_called
        comparator_called = True
        return 2

    monkeypatch.setattr(
        watch.compare_independent_cycles,
        "main",
        fake_compare,
    )
    monkeypatch.setattr(
        watch,
        "load_demo_telemetry_events",
        lambda _: [
            {
                "kind": "cycle_start",
                "cycle_id": "candidate-unvalidated",
                "time_utc": "2026-08-12T19:00:00Z",
            }
        ],
    )

    result = watch.run_once(
        qualification_state=qualification,
        target_events=tmp_path / "target.jsonl",
        candidate_telemetry=tmp_path / "candidate.csv",
        reports_dir=tmp_path / "reports",
        pairing="ordinal",
        max_start_gap_seconds=2.0,
        normalized_price_tolerance=0.02,
    )

    state = json.loads(qualification.read_text(encoding="utf-8"))
    assert result["status"] == "WAITING_FOR_ALIGNED_CYCLE_START"
    assert comparator_called is False
    assert state["qualification_started_utc"] is None
    assert state["active_cycle_id"] == "candidate-excluded"
    assert state["active_cycle_eligible"] is False


def test_run_once_updates_evidence_based_qualification(
    tmp_path,
    monkeypatch,
) -> None:
    watch = importlib.import_module(
        "tools.watch_independent_fidelity"
    )
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps(
            {
                "active_build_id": "build-1",
                "active_deployed_utc": "2026-08-12T16:00:00Z",
                "qualification_started_utc": None,
                "complete_paired_cycles": 0,
                "evidence_based_fidelity_percent": None,
                "qualified_at_or_above_95_percent": False,
                "qualified_at_or_above_99_percent": False,
            }
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"

    def fake_compare(arguments):
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "0001-pair.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "build_id": "build-1",
                    "certification_started_utc": (
                        "2026-08-12T16:00:00Z"
                    ),
                    "fidelity": {
                        "strict": {"f1_percent": 96.0},
                        "conditional": {
                            "f1_percent": 100.0,
                            "coverage_percent": 97.0,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(
        watch.compare_independent_cycles,
        "main",
        fake_compare,
    )
    monkeypatch.setattr(
        watch,
        "load_demo_telemetry_events",
        lambda _: [],
    )

    result = watch.run_once(
        qualification_state=qualification,
        target_events=tmp_path / "target.jsonl",
        candidate_telemetry=tmp_path / "candidate.csv",
        reports_dir=reports,
        pairing="ordinal",
        max_start_gap_seconds=86400,
        normalized_price_tolerance=0.02,
    )

    state = json.loads(qualification.read_text(encoding="utf-8"))
    assert result["status"] == "QUALIFIED_AT_OR_ABOVE_95"
    assert result["evidence_based_fidelity_percent"] == 96.0
    assert state["complete_paired_cycles"] == 1
    assert state["evidence_based_fidelity_percent"] == 96.0
    assert state["qualified_at_or_above_95_percent"] is True
    assert state["qualified_at_or_above_99_percent"] is False


def test_run_once_rejects_low_conditional_coverage(
    tmp_path,
    monkeypatch,
) -> None:
    watch = importlib.import_module(
        "tools.watch_independent_fidelity"
    )
    qualification = tmp_path / "qualification.json"
    qualification.write_text(
        json.dumps(
            {
                "active_build_id": "build-1",
                "active_deployed_utc": "2026-08-12T16:00:00Z",
                "qualification_started_utc": None,
                "complete_paired_cycles": 0,
                "evidence_based_fidelity_percent": None,
                "qualified_at_or_above_95_percent": False,
                "qualified_at_or_above_99_percent": False,
            }
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"

    def fake_compare(arguments):
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "0001-pair.json").write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "build_id": "build-1",
                    "certification_started_utc": (
                        "2026-08-12T16:00:00Z"
                    ),
                    "fidelity": {
                        "strict": {"f1_percent": 100.0},
                        "conditional": {
                            "f1_percent": 100.0,
                            "coverage_percent": 20.0,
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(
        watch.compare_independent_cycles,
        "main",
        fake_compare,
    )
    monkeypatch.setattr(
        watch,
        "load_demo_telemetry_events",
        lambda _: [],
    )

    result = watch.run_once(
        qualification_state=qualification,
        target_events=tmp_path / "target.jsonl",
        candidate_telemetry=tmp_path / "candidate.csv",
        reports_dir=reports,
        pairing="ordinal",
        max_start_gap_seconds=86400,
        normalized_price_tolerance=0.02,
    )

    state = json.loads(qualification.read_text(encoding="utf-8"))
    assert result["status"] == "BELOW_95"
    assert result["evidence_based_fidelity_percent"] == 20.0
    assert result["conditional_coverage_percent"] == 20.0
    assert state["qualified_at_or_above_95_percent"] is False
    assert state["qualified_at_or_above_99_percent"] is False


def test_main_once_writes_watcher_health(
    tmp_path,
    monkeypatch,
) -> None:
    watch = importlib.import_module(
        "tools.watch_independent_fidelity"
    )
    health = tmp_path / "watch-health.json"
    expected = {
        "status": "WAITING_FOR_COMPLETE_PAIR",
        "pair_count": 0,
        "fail_count": 0,
        "evidence_based_fidelity_percent": None,
        "qualified_at_or_above_95_percent": False,
        "qualified_at_or_above_99_percent": False,
        "comparator_exit_code": 2,
        "build_id": "build-1",
        "certification_started_utc": "2026-08-12T16:00:00Z",
    }
    monkeypatch.setattr(watch, "run_once", lambda **kwargs: expected)

    exit_code = watch.main(
        [
            "--qualification-state",
            str(tmp_path / "qualification.json"),
            "--target-events",
            str(tmp_path / "target.jsonl"),
            "--candidate-telemetry",
            str(tmp_path / "candidate.csv"),
            "--reports-dir",
            str(tmp_path / "reports"),
            "--health",
            str(health),
            "--pairing",
            "ordinal",
            "--max-start-gap-seconds",
            "86400",
            "--once",
        ]
    )

    payload = json.loads(health.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "WAITING_FOR_COMPLETE_PAIR"
    assert payload["pair_count"] == 0
    assert payload["updated_at_utc"].endswith("+00:00")


def test_installer_registers_read_only_fidelity_watcher() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "StraddleIndependentFidelityWatch" in source
    assert "watch_independent_fidelity.py" in source
    assert "qualification-state.json" in source
    assert "target-cycles.jsonl" in source
    assert "candidate-telemetry.csv" in source
    assert "formal-comparison-reports" in source
    assert "fidelity-watch-health.json" in source
    assert '"--pairing", "ordinal"' in source
    assert '"--max-start-gap-seconds", "2.0"' in source
    assert "-MultipleInstances IgnoreNew" in source
    assert "Start-ScheduledTask" in source
    assert "ssh" not in source.lower()
    assert "docker" not in source.lower()
    assert "terminal64.exe" not in source.lower()


def test_tool_can_run_directly_as_scheduled_script() -> None:
    completed = subprocess.run(
        [sys.executable, str(TOOL), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--qualification-state" in completed.stdout
