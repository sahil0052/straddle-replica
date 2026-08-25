from datetime import datetime
from pathlib import Path

from straddle_replica.report import (
    DealRecord,
    DeploymentRecord,
    MT5Report,
    PositionRecord,
)
from straddle_replica import tester_report
from straddle_replica.validation import (
    compare_golden_lifecycle_to_telemetry,
    compare_report_fills_to_tester,
    compare_report_lifecycle_to_telemetry,
)


def report_deal(
    time: datetime,
    deal_id: int,
    direction: str,
    comment: str,
    price: float = 4100.0,
) -> DealRecord:
    return DealRecord(
        row=deal_id,
        time=time,
        deal_id=deal_id,
        symbol="XAUUSD",
        deal_type="buy",
        direction=direction,
        volume=0.01,
        price=price,
        order_id=deal_id,
        commission=0.0,
        fee=0.0,
        swap=0.0,
        profit=0.0,
        balance=20_000.0,
        comment=comment,
    )


def make_tester_deal(
    time: datetime,
    deal_id: int,
    direction: str,
    comment: str,
) -> tester_report.TesterDeal:
    return tester_report.TesterDeal(
        time=time,
        deal_id=deal_id,
        symbol="XAUUSD",
        deal_type="buy",
        direction=direction,
        volume=0.01,
        price=4100.0,
        order_id=deal_id,
        commission=0.0,
        swap=0.0,
        profit=0.0,
        balance=20_000.0,
        comment=comment,
    )


def test_compares_only_fills_from_first_complete_deployment():
    deployment_start = datetime(2026, 7, 30, 0, 5, 28)
    report = MT5Report(
        metadata={},
        closed_positions=(),
        open_positions=(),
        historical_orders=(),
        working_orders=(),
        deals=(
            report_deal(
                datetime(2026, 7, 30, 0, 1),
                1,
                "in",
                "STR B15",
            ),
            report_deal(
                datetime(2026, 7, 30, 0, 6),
                2,
                "in",
                "STR S1",
            ),
            report_deal(
                datetime(2026, 7, 30, 0, 7),
                3,
                "out",
                "[sl 4099.00]",
            ),
        ),
        deployments=(
            DeploymentRecord(
                start=deployment_start,
                end=datetime(2026, 7, 30, 0, 5, 34),
                levels_per_side=30,
                anchor=4100.0,
                step=1.37,
                first_gap=2.74,
                initial_order_count=60,
                profile_hint="LATEST_30",
            ),
        ),
    )
    tester = tester_report.MT5TesterReport(
        orders=(),
        deals=(
            make_tester_deal(
                datetime(2026, 7, 30, 0, 6),
                20,
                "in",
                "STR S1",
            ),
            make_tester_deal(
                datetime(2026, 7, 30, 0, 7),
                21,
                "out",
                "sl 4099.00",
            ),
        ),
    )

    result = compare_report_fills_to_tester(report, tester)

    assert result.report_fills == 1
    assert result.tester_fills == 1
    assert result.fill_alignment.matched_count == 1
    assert result.report_stop_exits == 1
    assert result.tester_stop_exits == 1


def test_compares_position_level_report_lifecycle_to_telemetry(tmp_path: Path):
    start = datetime(2026, 7, 30, 0, 5, 28)
    fill_time = datetime(2026, 7, 30, 0, 6)
    close_time = datetime(2026, 7, 30, 0, 7)
    report = MT5Report(
        metadata={},
        closed_positions=(
            PositionRecord(
                row=1,
                open_time=fill_time,
                position_id=10,
                symbol="XAUUSD",
                side="buy",
                volume=0.01,
                open_price=4100.0,
                stop_loss=4100.2,
                take_profit=None,
                close_time=close_time,
                close_price=4100.2,
                commission=0.0,
                swap=0.0,
                profit=0.2,
                comment="STR B1",
            ),
        ),
        open_positions=(),
        historical_orders=(),
        working_orders=(),
        deals=(
            report_deal(fill_time, 10, "in", "STR B1"),
            report_deal(close_time, 11, "out", "[sl 4100.20]", price=4100.2),
        ),
        deployments=(
            DeploymentRecord(
                start=start,
                end=datetime(2026, 7, 30, 0, 5, 34),
                levels_per_side=30,
                anchor=4100.0,
                step=1.37,
                first_gap=2.74,
                initial_order_count=60,
                profile_hint="LATEST_30",
            ),
        ),
    )
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text(
        "time,kind,comment,side,volume,price,state,level,ticket\n"
        "2026-07-30T00:06:00Z,fill,STR B1,buy,0.01,4100.00,"
        "CYCLE_RUNNING,STR B1,10\n"
        "2026-07-30T00:07:00Z,stop_exit,STR B1,buy,0.01,4100.20,"
        "CYCLE_RUNNING,STR B1,10\n",
        encoding="utf-8",
    )

    result = compare_report_lifecycle_to_telemetry(report, telemetry)

    assert result.expected_count == 2
    assert result.actual_count == 2
    assert result.matched_count == 2
    assert result.is_match


def test_compares_exported_golden_lifecycle_to_telemetry(tmp_path: Path):
    golden = tmp_path / "golden"
    golden.mkdir()
    (golden / "deployments.csv").write_text(
        "start,end,levels_per_side,anchor,step,first_gap,"
        "initial_order_count,profile_hint\n"
        "2026-07-30 00:05:28,2026-07-30 00:05:34,"
        "30,4100,1.37,2.74,60,LATEST_30\n",
        encoding="utf-8",
    )
    (golden / "positions.csv").write_text(
        "row,open_time,position_id,symbol,side,volume,open_price,"
        "stop_loss,take_profit,close_time,close_price,commission,"
        "swap,profit,comment\n"
        "1,2026-07-30 00:06:00,10,XAUUSD,buy,0.01,4100,"
        "4100.2,,2026-07-30 00:07:00,4100.2,0,0,0.2,STR B1\n",
        encoding="utf-8",
    )
    (golden / "deals.csv").write_text(
        "row,time,deal_id,symbol,deal_type,direction,volume,price,"
        "order_id,commission,fee,swap,profit,balance,comment\n"
        "1,2026-07-30 00:06:00,10,XAUUSD,buy,in,0.01,4100,"
        "10,0,0,0,0,20000,STR B1\n"
        "2,2026-07-30 00:07:00,11,XAUUSD,sell,out,0.01,4100.2,"
        "11,0,0,0,0.2,20000,[sl 4100.20]\n",
        encoding="utf-8",
    )
    telemetry = tmp_path / "telemetry.csv"
    telemetry.write_text(
        "time,kind,comment,side,volume,price,state,level,ticket\n"
        "2026-07-30T00:06:00Z,fill,STR B1,buy,0.01,4100.00,"
        "CYCLE_RUNNING,STR B1,10\n"
        "2026-07-30T00:07:00Z,stop_exit,STR B1,buy,0.01,4100.20,"
        "CYCLE_RUNNING,STR B1,10\n",
        encoding="utf-8",
    )

    result = compare_golden_lifecycle_to_telemetry(golden, telemetry)

    assert result.expected_count == 2
    assert result.actual_count == 2
    assert result.matched_count == 2
    assert result.is_match
