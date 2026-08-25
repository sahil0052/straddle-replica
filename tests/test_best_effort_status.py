from straddle_replica.best_effort_status import build_best_effort_status


def test_observer_mode_never_reports_formal_certification() -> None:
    report = build_best_effort_status(
        account_terms={
            "match": False,
            "mismatches": {
                "account_leverage": {"target": "1000", "demo": "500"},
                "symbol_swap_mode": {"target": "1", "demo": "0"},
            },
        },
        adapter_state={
            "initialized": True,
            "waiting_for_flat": True,
            "next_sequence": 42,
        },
        coordinator_state={
            "skipped_cycles": 0,
            "sequence_gaps": 0,
            "session_restarts": 0,
        },
        comparisons=[
            {
                "status": "PASS",
                "cycle_id": "cycle-1",
                "fidelity": {
                    "strict": {"f1_percent": 91.5},
                    "conditional": {
                        "f1_percent": 100.0,
                        "coverage_percent": 72.25,
                    },
                },
            }
        ],
        source_mode="observer",
    )

    assert report["mode"] == "BEST_EFFORT"
    assert report["formal_certification_eligible"] is False
    assert report["broker_terms"] == [
        "account_leverage",
        "symbol_swap_mode",
    ]
    assert "originating_request_payload" in report["capture_limits"]
    assert report["ea_logic"]["latest_status"] == "PASS"
    assert report["ea_logic"]["paired_cycle_count"] == 1
    assert (
        report["ea_logic"]["strict_lifecycle_fidelity_percent"]
        == 91.5
    )
    assert (
        report["ea_logic"]["conditional_logic_fidelity_percent"]
        == 100.0
    )
    assert report["ea_logic"]["conditional_coverage_percent"] == 72.25


def test_waiting_status_is_explicit_before_first_paired_cycle() -> None:
    report = build_best_effort_status(
        account_terms={"match": True, "mismatches": {}},
        adapter_state={"initialized": True},
        coordinator_state={},
        comparisons=[],
        source_mode="observer",
    )

    assert report["ea_logic"]["latest_status"] == "WAITING"
    assert report["formal_certification_eligible"] is False


def test_commissioning_guard_forces_invalid_status() -> None:
    report = build_best_effort_status(
        account_terms={"match": True, "mismatches": {}},
        adapter_state={"initialized": True},
        coordinator_state={},
        comparisons=[],
        source_mode="observer",
        operational_guard_failures=[
            "demo_slot_capacity_10_below_required_60",
        ],
    )

    assert report["ea_logic"]["latest_status"] == "INVALID"
    assert report["operations"]["guard_failures"] == [
        "demo_slot_capacity_10_below_required_60",
    ]
