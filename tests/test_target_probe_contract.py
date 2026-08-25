from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "mql5" / "StraddleTargetProbe.mq5"
BUILD_SCRIPT = ROOT / "scripts" / "build_target_probe.ps1"


def test_target_probe_is_passive_and_same_terminal_compatible() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "OnTradeTransaction" in source
    assert "MqlTradeRequest" in source
    assert "MqlTradeResult" in source
    assert "TRANSACTION_QUEUE_CAPACITY" in source
    assert "TargetProbe" in source
    assert "GetTickCount64()" in source[
        source.index("string NewSessionName") : source.index(
            "int OpenAppendText"
        )
    ]
    assert "ACCOUNT_TRADE_ALLOWED is true" not in source
    assert "OrderSend(" not in source
    assert "OrderSendAsync(" not in source
    assert "PositionClose(" not in source
    assert "#include <Trade/Trade.mqh>" not in source


def test_target_probe_captures_request_result_and_account_terms() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "request_id" in source
    assert "result_retcode" in source
    assert "request_comment" in source
    assert "ACCOUNT_LIMIT_ORDERS" in source
    assert "ACCOUNT_LEVERAGE" in source
    assert "SYMBOL_TRADE_TICK_SIZE" in source
    assert "SYMBOL_TRADE_TICK_VALUE" in source
    assert "SYMBOL_TRADE_TICK_VALUE_PROFIT" in source
    assert "SYMBOL_TRADE_TICK_VALUE_LOSS" in source
    assert "SYMBOL_TRADE_CONTRACT_SIZE" in source
    assert "SYMBOL_SWAP_LONG" in source
    assert "SYMBOL_SWAP_SHORT" in source
    assert "dropped_transactions" in source
    assert "probe_build_id" in source
    assert "latest30-live-twin-v1" in source
    assert "PositionSelectByTicket(request.position)" in source
    assert "PositionGetString(POSITION_COMMENT)" in source
    entity_comment = source[
        source.index("string EntityComment") : source.index(
            "ulong EntityMagic"
        )
    ]
    assert entity_comment.index("request.position") < entity_comment.index(
        "request.comment"
    )


def test_target_probe_has_a_reproducible_build_script() -> None:
    script = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "StraddleTargetProbe.mq5" in script
    assert "StraddleTargetProbe.ex5" in script
    assert "0 errors" in script
    assert "0 warnings" in script
