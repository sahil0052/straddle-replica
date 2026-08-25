from pathlib import Path
import json
import subprocess
import sys

from straddle_replica.account_terms import compare_account_terms


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "compare_account_terms.py"
REQUIRED = {
    "account_server": "AchieverGlobalMarkets-Server",
    "account_leverage": "500",
    "account_currency": "USD",
    "account_margin_mode": "2",
    "account_limit_orders": "60",
    "symbol": "XAUUSD",
    "symbol_digits": "2",
    "symbol_tick_size": "0.01",
    "symbol_tick_value": "1.0",
    "symbol_tick_value_profit": "1.0",
    "symbol_tick_value_loss": "1.0",
    "symbol_contract_size": "100.0",
    "symbol_volume_min": "0.01",
    "symbol_volume_max": "100.0",
    "symbol_volume_step": "0.01",
    "symbol_stops_level": "0",
    "symbol_freeze_level": "0",
    "symbol_filling_mode": "3",
    "symbol_swap_mode": "1",
    "symbol_swap_long": "-10.0",
    "symbol_swap_short": "5.0",
    "symbol_swap_rollover3days": "3",
}


def write_manifest(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "key,value\n"
        + "".join(f"{key},{value}\n" for key, value in values.items()),
        encoding="utf-8",
    )


def test_matching_account_terms_pass() -> None:
    result = compare_account_terms(REQUIRED, dict(REQUIRED))

    assert result["match"] is True
    assert result["mismatches"] == {}


def test_account_terms_fail_closed_for_missing_or_different_values() -> None:
    demo = dict(REQUIRED)
    demo["account_leverage"] = "100"
    del demo["symbol_swap_short"]

    result = compare_account_terms(REQUIRED, demo)

    assert result["match"] is False
    assert result["mismatches"]["account_leverage"] == {
        "target": "500",
        "demo": "100",
    }
    assert result["mismatches"]["symbol_swap_short"] == {
        "target": "5.0",
        "demo": None,
    }


def test_account_terms_load_from_probe_manifests(tmp_path: Path) -> None:
    target = tmp_path / "target.csv"
    demo = tmp_path / "demo.csv"
    write_manifest(target, REQUIRED)
    write_manifest(demo, REQUIRED)

    result = compare_account_terms(target, demo)

    assert result["match"] is True
    assert result["checked_keys"] == sorted(REQUIRED)


def test_account_terms_cli_fails_closed_on_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "target.csv"
    demo = tmp_path / "demo.csv"
    output = tmp_path / "comparison.json"
    write_manifest(target, REQUIRED)
    changed = dict(REQUIRED)
    changed["symbol_tick_size"] = "0.1"
    write_manifest(demo, changed)

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--target",
            str(target),
            "--demo",
            str(demo),
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["match"] is False
    assert "symbol_tick_size" in result["mismatches"]
