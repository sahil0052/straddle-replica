from pathlib import Path

from straddle_replica.tester_report import parse_mt5_tester_report


def test_parses_mt5_tester_orders_and_deals(tmp_path: Path):
    report_path = tmp_path / "tester.htm"
    report_path.write_text(
        """
        <html><body><table>
        <tr><th><b>Orders</b></th></tr>
        <tr>
          <td>2026.07.30 00:05:28</td><td>2</td><td>XAUUSD</td>
          <td>buy stop</td><td>0.01 / 0.01</td><td>4074.64</td>
          <td></td><td></td><td>2026.07.30 00:12:44</td>
          <td>filled</td><td>STR B1</td>
        </tr>
        <tr><th><b>Deals</b></th></tr>
        <tr>
          <td>2026.07.30 00:12:44</td><td>11</td><td>XAUUSD</td>
          <td>buy</td><td>in</td><td>0.01</td><td>4075.26</td>
          <td>2</td><td>0.00</td><td>0.00</td><td>0.00</td>
          <td>19280.00</td><td>STR B1</td>
        </tr>
        </table></body></html>
        """,
        encoding="utf-16",
    )

    report = parse_mt5_tester_report(report_path)

    assert len(report.orders) == 1
    assert report.orders[0].comment == "STR B1"
    assert report.orders[0].filled_volume == 0.01
    assert len(report.deals) == 1
    assert report.deals[0].direction == "in"
    assert report.deals[0].price == 4075.26


def test_reads_real_mt5_utf16_tester_report_when_available():
    report_path = Path(
        r"C:\Program Files\MetaTrader 5\StraddleReplica_recent_latest_30.htm"
    )
    if not report_path.exists():
        return

    report = parse_mt5_tester_report(report_path)

    assert len(report.orders) == 2_076
    assert len(report.deals) == 1_310
    assert sum(deal.direction == "in" for deal in report.deals) == 655
    assert sum(deal.comment == "STR CLOSE" for deal in report.deals) == 138
