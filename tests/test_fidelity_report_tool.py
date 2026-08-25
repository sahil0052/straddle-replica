import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "build_fidelity_report.py"


def test_report_tool_writes_json_markdown_and_mismatch_register(
    tmp_path: Path,
) -> None:
    cycle = tmp_path / "cycle-1.json"
    cycle.write_text(
        json.dumps(
            {
                "cycle_id": "cycle-1",
                "status": "FAIL",
                "logic_status": "FAIL",
                "execution_status": "DIFFERENT",
                "evidence_grade": "BEST_EFFORT",
                "fidelity": {
                    "strict": {"f1_percent": 55.25},
                    "conditional": {
                        "f1_percent": 90.0,
                        "coverage_percent": 60.0,
                    },
                },
                "deterministic_mismatches": [
                    {
                        "category": "decision_sequence",
                        "key": ["stop_request", "STR B1", 1],
                    }
                ],
                "execution_mismatches": [
                    {
                        "category": "execution",
                        "key": ["fill", "STR B1", 1],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--comparison",
            str(cycle),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output / "fidelity-summary.json").exists()
    assert (output / "fidelity-summary.md").exists()
    register = json.loads(
        (output / "mismatch-register.json").read_text(encoding="utf-8")
    )
    assert register["earliest_deterministic"]["category"] == (
        "decision_sequence"
    )
