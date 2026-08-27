from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "mql5" / "StraddleReplica.mq5"
REAL_MAIN = ROOT / "mql5" / "StraddleReplicaReal.mq5"
APP = ROOT / "mql5" / "include" / "StraddleReplicaApp.mqh"
PROFILE_CATALOG = ROOT / "mql5" / "include" / "ProfileCatalog.mqh"
ENGINE = ROOT / "mql5" / "include" / "StraddleEngine.mqh"
GATEWAY = ROOT / "mql5" / "include" / "TradeGateway.mqh"
BUILD_SCRIPT = ROOT / "scripts" / "build.ps1"
INSTALL_SCRIPT = ROOT / "scripts" / "install_ea.ps1"
TESTER_CONFIG = ROOT / "tester" / "latest_30.ini"
TYPES = ROOT / "mql5" / "include" / "StraddleTypes.mqh"


def app_source() -> str:
    assert APP.exists(), f"Missing shared EA application include: {APP}"
    return APP.read_text(encoding="utf-8")


def test_main_ea_exposes_required_inputs_and_event_handlers():
    source = app_source()

    for required in (
        "input ENUM_STR_PROFILE Profile = LATEST_30",
        "input ulong MagicNumber = 901018",
        "input bool ReplicaMode = true",
        "input datetime ReplicaStartTime = 0",
        "input int InterOrderDelayMs = 100",
        "input double CustomPreTightenTrailDistanceSteps = 2.0",
        "input double CustomTightenTriggerSteps = 3.0",
        "input bool CustomActivationUsesTrailingDistance = false",
        "input bool CustomStopUpdatesOnTimer = false",
        "input int CustomRearmDelaySeconds = 0",
        "input int CustomStopUpdateIntervalSeconds = 0",
        "input int CustomMaxStopUpdatesPerPass = 0",
        "input bool CustomStopScanNewestFirst = false",
        "input bool SafetyEnabled = STR_SAFETY_ENABLED_DEFAULT",
        "input double CustomLockOffsetPrice = 0.2",
        "input double CustomCycleTargetMoney = 0.0",
        "input bool CustomCancelBeforeClose = false",
        "input int CustomDeploymentFillCooldownSeconds = 0",
        "input int CustomCloseIntervalSeconds = 0",
        "input int CustomRestartDelayMs = 3000",
        "int OnInit()",
        "void OnTick()",
        "void OnTimer()",
        "void OnTradeTransaction(",
    ):
        assert required in source


def test_profile_catalog_contains_all_observed_profiles():
    source = PROFILE_CATALOG.read_text(encoding="utf-8")

    for profile in (
        "HISTORICAL_50",
        "HISTORICAL_60",
        "AGGRESSIVE_30",
        "LOW_RISK_30",
        "LATEST_30",
    ):
        assert profile in source
    assert "config.anchor_divisor = 3000.0" in source
    assert "config.anchor_divisor = 6000.0" in source
    assert "STR_STEP_ATR" in source
    assert "config.atr_timeframe=PERIOD_M15" in source
    assert "config.atr_period=17" in source
    assert "config.atr_timeframe=PERIOD_M5" in source
    assert "config.atr_period=44" in source
    assert "config.trail_distance_steps=1.0" in source


def test_engine_requires_hedging_and_uses_millisecond_timer():
    source = ENGINE.read_text(encoding="utf-8")

    assert "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING" in source
    assert "EventSetMillisecondTimer" in source
    assert "CYCLE_DEPLOYING" in source
    assert "CYCLE_RUNNING" in source
    assert "CYCLE_CLOSING" in source
    assert "CYCLE_CANCELING" in source
    assert "CYCLE_RESTARTING" in source
    assert "iATR(" in source
    assert "CopyBuffer(" in source
    assert "TimeCurrent()-m_restart_started_at" in source
    assert "TimeCurrent()<m_runtime.start_time" in source


def test_ea_fails_closed_outside_the_selected_demo_account():
    main = app_source()
    engine = ENGINE.read_text(encoding="utf-8")
    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(
        encoding="utf-8"
    )

    assert "input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT" in main
    assert "input ulong ExpectedAccountLogin = 0" in main
    assert "runtime.require_demo_account=RequireDemoAccount" in main
    assert "runtime.expected_account_login=ExpectedAccountLogin" in main
    assert "bool              require_demo_account;" in types
    assert "ulong             expected_account_login;" in types
    assert "ACCOUNT_TRADE_MODE_DEMO" in engine
    assert "AccountInfoInteger(ACCOUNT_TRADE_MODE)" in engine
    assert "m_runtime.expected_account_login>0" in engine
    assert "AccountInfoInteger(ACCOUNT_LOGIN)" in engine
    assert "m_runtime.expected_account_login==0" in engine


def test_demo_and_real_wrappers_share_app_with_distinct_account_defaults():
    assert REAL_MAIN.exists(), f"Missing real-account EA wrapper: {REAL_MAIN}"
    demo = MAIN.read_text(encoding="utf-8")
    real = REAL_MAIN.read_text(encoding="utf-8")
    app = app_source()

    assert "#define STR_REQUIRE_DEMO_DEFAULT true" in demo
    assert '#include "include/StraddleReplicaApp.mqh"' in demo
    assert "#define STR_REQUIRE_DEMO_DEFAULT false" in real
    assert "#define STR_REQUIRE_BOUND_DEFAULT false" in real
    assert "#define STR_SAFETY_ENABLED_DEFAULT false" in real
    assert '#include "include/StraddleReplicaApp.mqh"' in real
    assert "input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT" in app
    assert "input bool RequireBoundAccount = STR_REQUIRE_BOUND_DEFAULT" in app
    assert "input bool SafetyEnabled = STR_SAFETY_ENABLED_DEFAULT" in app
    assert "runtime.require_demo_account=RequireDemoAccount" in app


def test_engine_restores_realized_state_and_emits_canonical_telemetry():
    source = ENGINE.read_text(encoding="utf-8")

    assert 'GlobalVariableGet(GlobalKey("balance"))' in source
    assert "m_deal_ledger.TryRecalculate(" in source
    assert "OwnedPositionCount()>0 ||" in source
    assert "m_cycle_exit_deal_count>0" in source
    assert '"utc_time","server_time","cycle_id","command_seq"' in source
    assert '"kind","comment","side","volume","price","sl","tp"' in source


def test_trade_transactions_log_position_level_fills_and_exits():
    source = ENGINE.read_text(encoding="utf-8")

    assert "DEAL_POSITION_ID" in source
    assert "HistoryOrderGetString(position_id,ORDER_COMMENT)" in source
    assert 'WriteTelemetry("fill"' in source
    assert 'WriteTelemetry("stop_exit"' in source
    assert 'WriteTelemetry("close_fill"' in source
    assert "PositionSelectByTicket(request.position)" in source
    assert "PositionGetString(POSITION_COMMENT)" in source
    request_comment = source[
        source.index("string RequestComment") : source.index(
            "void LogTradeRequest"
        )
    ]
    assert request_comment.index("request.position") < request_comment.index(
        "request.comment"
    )


def test_stop_exit_detection_uses_authoritative_deal_reason():
    source = ENGINE.read_text(encoding="utf-8")
    deal_processor = source.split(
        "bool ProcessSelectedDeal", 1
    )[1].split("void ProcessPendingDeals", 1)[0]

    assert "DEAL_REASON" in deal_processor
    assert "DEAL_REASON_SL" in deal_processor
    assert (
        "exit_reason==DEAL_REASON_SL"
        in deal_processor
    )


def test_deal_callback_retries_when_history_is_temporarily_unavailable():
    source = ENGINE.read_text(encoding="utf-8")
    transaction_handler = source.split(
        "void OnTradeTransaction", 1
    )[1]
    timer_handler = source.split("void OnTimer", 1)[1].split(
        "void OnTradeTransaction", 1
    )[0]

    assert "QueuePendingDeal(transaction.deal)" in transaction_handler
    assert "void ProcessPendingDeals(void)" in source
    assert "ProcessSelectedDeal(deal_ticket)" in source
    assert timer_handler.index("ProcessPendingDeals();") < (
        timer_handler.index("switch(m_state)")
    )
    assert "DEAL_TIME" in source


def test_rearm_gate_uses_authoritative_broker_milliseconds():
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    deal_processor = engine.split(
        "bool ProcessSelectedDeal", 1
    )[1].split("void ProcessPendingDeals", 1)[0]
    schedule = engine.split(
        "void ScheduleLevelRearm", 1
    )[1].split("bool DealMetadataReady", 1)[0]

    assert "long              rearm_after_msc;" in types
    assert "long CurrentServerMs(void) const" in engine
    assert "tick.time_msc" in engine
    assert "const long exit_time_msc=0" in schedule
    assert "m_profile.rearm_delay_seconds*1000" in schedule
    assert "CurrentServerMs()<level_state.rearm_after_msc" in engine
    assert "DEAL_TIME_MSC" in deal_processor


def test_deal_processing_waits_for_complete_exit_metadata():
    engine = ENGINE.read_text(encoding="utf-8")
    readiness = engine.split(
        "bool DealMetadataReady", 1
    )[1].split("void QueueMissingHistoryDeals", 1)[0]
    transaction_handler = engine.split(
        "void OnTradeTransaction", 1
    )[1]

    assert "DEAL_TIME_MSC" in readiness
    assert "DEAL_REASON" in readiness
    assert "DEAL_COMMENT" in readiness
    assert "PositionCommentFromDeal(deal_ticket)" in readiness
    assert "STR_DEAL_METADATA_SETTLE_MS" in readiness
    assert "!DealMetadataReady(transaction.deal)" in transaction_handler
    assert "QueuePendingDeal(transaction.deal)" in transaction_handler


def test_exit_metadata_defers_ambiguous_client_reason_during_settle_window():
    engine = ENGINE.read_text(encoding="utf-8")
    readiness = engine.split(
        "bool DealMetadataReady", 1
    )[1].split("long CurrentUtcMs", 1)[0]
    exit_readiness = readiness.split(
        "if(entry==DEAL_ENTRY_OUT", 1
    )[1]

    assert "reason_value==DEAL_REASON_CLIENT" in exit_readiness
    assert "metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS" in exit_readiness
    assert exit_readiness.index(
        "reason_value==DEAL_REASON_CLIENT"
    ) < exit_readiness.index("return true;")


def test_timer_reconciles_deals_missing_from_trade_callbacks():
    engine = ENGINE.read_text(encoding="utf-8")
    reconciliation = engine.split(
        "void QueueMissingHistoryDeals", 1
    )[1].split("void ProcessPendingDeals", 1)[0]
    timer_handler = engine.split("void OnTimer", 1)[1].split(
        "void OnTradeTransaction", 1
    )[0]

    assert "LoadProcessedDealsFromTelemetry" in engine
    assert "HistorySelect(" in reconciliation
    assert "HistoryDealsTotal()" in reconciliation
    assert "STR_HISTORY_RECONCILE_LOOKBACK_MS" in reconciliation
    assert "m_history_reconcile_seeded" in reconciliation
    assert "DealAlreadyProcessed(deal_ticket)" in reconciliation
    assert "QueuePendingDeal(deal_ticket)" in reconciliation
    assert timer_handler.index("QueueMissingHistoryDeals();") < (
        timer_handler.index("ProcessPendingDeals();")
    )


def test_latest_profile_uses_observed_cancel_close_restart_lifecycle():
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    latest_profile = profile.split("case LATEST_30:", 1)[1].split(
        "case CUSTOM_PROFILE:", 1
    )[0]
    engine = ENGINE.read_text(encoding="utf-8")
    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(
        encoding="utf-8"
    )

    assert "cycle_target_money" in types
    assert "cancel_before_close" in types
    assert "deployment_fill_cooldown_seconds" in types
    assert "close_interval_seconds" in types
    assert "config.cycle_target_money=30.0" in latest_profile
    assert "config.cancel_before_close=true" in latest_profile
    assert "config.deployment_fill_cooldown_seconds=20" in latest_profile
    assert "config.close_interval_seconds=20" in latest_profile
    assert "config.restart_delay_ms=20000" in latest_profile
    assert "config.rearm_delay_seconds=20" in latest_profile
    assert "config.stop_scan_newest_first=true" in latest_profile
    assert "config.stop_updates_on_timer=true" in latest_profile
    assert "config.max_stop_updates_per_pass=1" in latest_profile
    assert "m_profile.cancel_before_close ? CYCLE_CANCELING : CYCLE_CLOSING" in engine
    assert "m_profile.cycle_target_money" in engine

    # The 20 s sweep gate lives in ONE shared helper, and every close path is
    # required to route through it.  This used to be an inline
    # "TimeCurrent()-m_last_close_at<m_profile.close_interval_seconds" test in
    # CloseOnePosition() only, which left the CYCLE_RESTARTING drain unpaced --
    # a rejected close dropped the engine into CYCLE_RESTARTING with positions
    # still open and it then hammered them at the 100 ms timer period.  Commit
    # 6c340b5 hoisted the gate into CloseIntervalElapsed() and made both callers
    # use it.  Measured after the fix on account 25954110 (2026-08-26, 28
    # intra-sweep gaps): min 19.199 s, median 19.995 s, max 22.995 s, zero gaps
    # under 19 s and zero under 1 s.
    assert "bool CloseIntervalElapsed(void) const" in engine
    assert (
        "return TimeCurrent()-m_last_close_at>=m_profile.close_interval_seconds"
        in engine
    )
    assert engine.count("CloseIntervalElapsed()") >= 2, (
        "both CloseOnePosition() and the CYCLE_RESTARTING drain must gate on the "
        "shared pacing helper"
    )
    assert "if(OwnedPositionCount()>0 && !CloseIntervalElapsed())" in engine
    restart_drain = engine.split("case CYCLE_RESTARTING:", 1)[1].split(
        "case CYCLE_HALTED:", 1
    )[0]
    assert "if(CloseIntervalElapsed())" in restart_drain
    assert "TryCloseOneOwnedPosition()" in restart_drain


def test_alignment_hold_blocks_any_cycle_start_until_release():
    engine = ENGINE.read_text(encoding="utf-8")

    assert "string AlignmentHoldFileName(void) const" in engine
    assert "bool AlignmentHoldActive(void) const" in engine
    assert 'LogLifecycleEvent("alignment_hold"' in engine
    assert 'LogLifecycleEvent("alignment_release"' in engine
    idle_handler = engine.split("void OnTick(void)", 1)[1].split(
        "void OnTimer(void)",
        1,
    )[0]
    restart_handler = engine.split("case CYCLE_RESTARTING:", 1)[1].split(
        "case CYCLE_HALTED:",
        1,
    )[0]
    assert "AlignmentHoldActive()" in idle_handler
    assert "AlignmentHoldActive()" in restart_handler


def test_flat_detection_bypasses_position_close_interval():
    engine = ENGINE.read_text(encoding="utf-8")
    close_handler = engine.split("void CloseOnePosition", 1)[1].split(
        "bool TryCancelOneOwnedOrder", 1
    )[0]
    close_interval_guard = close_handler.split(
        "if(", 1
    )[1].split("return;", 1)[0]

    assert "OwnedPositionCount()>0" in close_interval_guard


def test_flat_restart_state_restores_without_replaying_old_cycle_levels():
    engine = ENGINE.read_text(encoding="utf-8")
    assert "datetime RestartStartedAtFromTelemetry" in engine
    telemetry_fallback = engine.split(
        "datetime RestartStartedAtFromTelemetry", 1
    )[1].split("bool RestoreCycle", 1)[0]
    restore = engine.split("bool RestoreCycle", 1)[1].split(
        "void PersistCycle", 1
    )[0]
    persistence = engine.split("void PersistCycle", 1)[1].split(
        "void PersistShadowSequence", 1
    )[0]
    initialize = engine.split("bool Initialize(", 1)[1].split(
        "void Shutdown", 1
    )[0]

    assert "bool flat_restart=" in restore
    assert "saved_state==CYCLE_RESTARTING" in restore
    assert restore.index("saved_state==CYCLE_RESTARTING") < restore.index(
        "ArmMissingLevelsAfterRestore();"
    )
    assert 'fields[2]!=m_cycle_id' in telemetry_fallback
    assert 'fields[4]!="cycle_complete"' in telemetry_fallback
    assert "StringToTime(fields[1])" in telemetry_fallback
    assert 'GlobalKey("restart_started_at")' in restore
    assert "persisted_restart_started_at" in restore
    assert "RestartStartedAtFromTelemetry()" in restore
    assert (
        "m_restart_started_at=persisted_restart_started_at;"
        in restore
    )
    assert 'GlobalKey("restart_started_at")' in persistence
    assert (
        "GlobalVariableSet("
        'GlobalKey("restart_started_at")'
        in "".join(persistence.split())
    )
    assert (
        'GlobalVariableDel(GlobalKey("restart_started_at"));'
        in persistence
    )
    assert "bool has_persisted_restart=" in initialize
    assert "(has_owned_cycle || has_persisted_restart)" in initialize


def test_latest_profile_applies_proven_m15_trend_rescue_state_machine():
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    latest_profile = profile.split("case LATEST_30:", 1)[1].split(
        "case CUSTOM_PROFILE:", 1
    )[0]
    engine = ENGINE.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    timer_handler = engine.split("void OnTimer", 1)[1].split(
        "void OnTradeTransaction", 1
    )[0]

    for field in (
        "trend_rescue_enabled",
        "trend_rescue_timeframe",
        "trend_rescue_bars",
        "trend_rescue_minimum_pending_levels",
        "trend_rescue_move_price",
        "trend_rescue_drawdown_money",
        "trend_rescue_volume_multiplier",
    ):
        assert field in types
    assert "bool              trend_rescue_replacement;" in types

    for setting in (
        "config.trend_rescue_enabled=true",
        "config.trend_rescue_timeframe=PERIOD_M15",
        "config.trend_rescue_bars=6",
        "config.trend_rescue_minimum_pending_levels=3",
        "config.trend_rescue_move_price=20.0",
        # 400.0, not 800.0.  Commit 5b2a830 ("Forensics Q2 Complete") measured the
        # Target's own rescue trigger and moved the drawdown floor from the
        # originally-guessed 800.0 down to the observed 400.0; this assertion was
        # left behind.  The parameter is dormant in practice -- rescue-leg count is
        # 0 in both the Target's 17,632-position book and in our live accounts --
        # so it is pinned here to stop it drifting, not because it fires.
        "config.trend_rescue_drawdown_money=400.0",
        "config.trend_rescue_volume_multiplier=2.0",
    ):
        assert setting in latest_profile

    assert "int TrendRescueSide(void) const" in engine
    assert (
        "iClose(m_runtime.symbol,"
        "m_profile.trend_rescue_timeframe,"
        "m_profile.trend_rescue_bars)"
    ) in engine
    assert "OwnedFloatingProfit()>-m_profile.trend_rescue_drawdown_money" in engine
    assert "bool TryCancelOneTrendRescueOrder" in engine
    assert "void PlaceOneTrendRescueReplacement" in engine
    assert "void ProcessTrendRescue" in engine
    assert "m_profile.trend_rescue_volume_multiplier" in engine
    assert "m_profile.deployment_fill_cooldown_seconds" in engine
    assert timer_handler.index("ProcessTrendRescue();") < timer_handler.index(
        "RearmOneMissingLevel();"
    )
    for manifest_field in (
        '"profile_trend_rescue_enabled"',
        '"profile_trend_rescue_timeframe"',
        '"profile_trend_rescue_bars"',
        '"profile_trend_rescue_minimum_pending_levels"',
        '"profile_trend_rescue_move_price"',
        '"profile_trend_rescue_drawdown_money"',
        '"profile_trend_rescue_volume_multiplier"',
    ):
        assert manifest_field in engine


def test_wholesale_trend_rescue_levels_latch_double_volume_for_later_rearms():
    engine = ENGINE.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    cancellation = engine.split(
        "bool TryCancelTrendRescueLevel", 1
    )[1].split("bool TryCancelOneTrendRescueOrder", 1)[0]
    rearm = engine.split(
        "void RearmOneMissingLevel", 1
    )[1].split("double OwnedFloatingProfit", 1)[0]
    persistence = engine.split(
        "bool RestoreCycle", 1
    )[1].split("void PersistCycle", 1)[0]

    assert "bool              trend_rescue_latched;" in types
    assert "ulong             m_buy_trend_rescue_latched_mask;" in engine
    assert "ulong             m_sell_trend_rescue_latched_mask;" in engine
    assert "level_state.trend_rescue_latched=true;" in cancellation
    assert (
        "m_buy_trend_rescue_latched_mask|=TrendRescueBit(index);"
        in cancellation
    )
    assert (
        "m_sell_trend_rescue_latched_mask|=TrendRescueBit(index);"
        in cancellation
    )
    assert "m_buy_levels[index].trend_rescue_latched ||" in rearm
    assert "m_sell_levels[index].trend_rescue_latched ||" in rearm
    assert 'GlobalKey("buy_trend_rescue_latched_mask")' in persistence
    assert 'GlobalKey("sell_trend_rescue_latched_mask")' in persistence


def test_active_positions_receive_one_shot_trend_rescue_rearm():
    engine = ENGINE.read_text(encoding="utf-8")
    rearm = engine.split(
        "void RearmOneMissingLevel", 1
    )[1].split("double OwnedFloatingProfit", 1)[0]
    marker = engine.split(
        "void MarkTrendRescuePositionRearms", 1
    )[1].split("void ClearTrendRescuePositionRearm", 1)[0]
    process = engine.split(
        "void ProcessTrendRescue", 1
    )[1].split("double OwnedGrossLots", 1)[0]
    persistence = engine.split(
        "bool RestoreCycle", 1
    )[1].split("void PersistShadowSequence", 1)[0]

    assert "ulong             m_buy_trend_rescue_rearm_mask;" in engine
    assert "ulong             m_sell_trend_rescue_rearm_mask;" in engine
    assert "m_buy_levels[index].has_position" in marker
    assert "m_sell_levels[index].has_position" in marker
    assert "MarkTrendRescuePositionRearms(trigger_side>0);" in process
    assert "TrendRescuePositionRearmPending(true,index)" in rearm
    assert "TrendRescuePositionRearmPending(false,index)" in rearm
    assert "TrendRescueSide()>0" not in rearm
    assert "TrendRescueSide()<0" not in rearm
    assert "if(PlaceLevel(m_buy_levels[index]))" in rearm
    assert "ClearTrendRescuePositionRearm(true,index);" in rearm
    assert "if(PlaceLevel(m_sell_levels[index]))" in rearm
    assert "ClearTrendRescuePositionRearm(false,index);" in rearm
    assert 'GlobalKey("buy_trend_rescue_rearm_mask")' in persistence
    assert 'GlobalKey("sell_trend_rescue_rearm_mask")' in persistence


def test_trend_rescue_trigger_is_consumed_until_it_clears_or_reverses():
    engine = ENGINE.read_text(encoding="utf-8")
    process = engine.split(
        "void ProcessTrendRescue", 1
    )[1].split("double OwnedGrossLots", 1)[0]
    persistence = engine.split(
        "bool RestoreCycle", 1
    )[1].split("void PersistShadowSequence", 1)[0]

    assert "int               m_trend_rescue_consumed_side;" in engine
    assert "int trigger_side=TrendRescueSide();" in process
    assert "trigger_side==m_trend_rescue_consumed_side" in process
    assert "if(trigger_side==0 && m_trend_rescue_consumed_side!=0)" in process
    assert "m_trend_rescue_consumed_side=0;" in process
    assert "m_trend_rescue_consumed_side=trigger_side;" in process
    assert 'GlobalKey("trend_rescue_consumed_side")' in persistence


def test_trend_rescue_requires_three_base_pending_levels() -> None:
    engine = ENGINE.read_text(encoding="utf-8")
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    latest_profile = profile.split("case LATEST_30:", 1)[1].split(
        "case CUSTOM_PROFILE:", 1
    )[0]
    pending_gate = engine.split(
        "bool HasTrendRescueBasePending", 1
    )[1].split("bool TryCancelTrendRescueLevel", 1)[0]

    assert (
        "int               trend_rescue_minimum_pending_levels;"
        in types
    )
    assert (
        "config.trend_rescue_minimum_pending_levels=3"
        in latest_profile
    )
    assert "int matching_levels=0;" in pending_gate
    assert "matching_levels++;" in pending_gate
    assert (
        "matching_levels>="
        "m_profile.trend_rescue_minimum_pending_levels"
        in "".join(pending_gate.split())
    )


def test_deployment_pauses_after_entry_fill_and_restores_the_cooldown():
    engine = ENGINE.read_text(encoding="utf-8")
    deploy = engine.split("void DeployOne(void)", 1)[1].split(
        "void RearmOneMissingLevel", 1
    )[0]
    deal_processor = engine.split(
        "bool ProcessSelectedDeal", 1
    )[1].split("void ProcessPendingDeals", 1)[0]
    restore = engine.split("bool RestoreCycle(void)", 1)[1].split(
        "void PersistCycle(void)", 1
    )[0]
    persist = engine.split("void PersistCycle(void)", 1)[1].split(
        "void ClearPersistence(void)", 1
    )[0]
    clear = engine.split("void ClearPersistence(void)", 1)[1].split(
        "void PersistShadowSequence", 1
    )[0]

    assert "datetime          m_last_entry_fill_at;" in engine
    assert "m_profile.deployment_fill_cooldown_seconds>0" in deploy
    assert (
        "TimeCurrent()-m_last_entry_fill_at<"
        "m_profile.deployment_fill_cooldown_seconds"
    ) in deploy
    assert (
        "m_last_entry_fill_at=(datetime)(deal_time_msc/1000);"
        in deal_processor
    )
    assert 'GlobalKey("last_entry_fill_at")' in restore
    assert 'GlobalKey("last_entry_fill_at")' in persist
    assert 'GlobalKey("last_entry_fill_at")' in clear


def test_invalid_price_during_deployment_cancels_the_partial_grid():
    engine = ENGINE.read_text(encoding="utf-8")
    deploy = engine.split("void DeployOne(void)", 1)[1].split(
        "void RearmOneMissingLevel", 1
    )[0]

    assert "m_gateway.LastRetcode()==TRADE_RETCODE_INVALID_PRICE" in deploy
    assert "m_state=CYCLE_CANCELING" in deploy
    assert '"deployment_price_rejected"' in deploy
    assert '"deployment_abort"' in deploy
    assert "PersistCycle();" in deploy


def test_restart_state_cleans_residual_exposure_before_becoming_idle():
    engine = ENGINE.read_text(encoding="utf-8")
    start_cycle = engine.split("bool StartCycle(void)", 1)[1].split(
        "void DeployOne(void)", 1
    )[0]
    restarting = engine.split("case CYCLE_RESTARTING:", 1)[1].split(
        "case CYCLE_HALTED:", 1
    )[0]

    assert "OwnedOrderCount()>0 || OwnedPositionCount()>0" in start_cycle
    assert "TryCancelOneOwnedOrder()" in restarting
    assert "TryCloseOneOwnedPosition()" in restarting
    assert restarting.index("TryCancelOneOwnedOrder()") < restarting.index(
        "TryCloseOneOwnedPosition()"
    )
    assert restarting.index("OwnedPositionCount()>0") < restarting.index(
        "TimeCurrent()-m_restart_started_at"
    )


def test_latest_activation_uses_observed_two_step_trailing_formula():
    main = app_source()
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    scheduler = (
        ROOT / "mql5" / "include" / "StopScheduler.mqh"
    ).read_text(encoding="utf-8")
    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(
        encoding="utf-8"
    )

    assert "CustomActivationUsesTrailingDistance" in main
    assert "activation_uses_trailing_distance" in types
    assert "config.activation_uses_trailing_distance=true" in profile
    assert "m_profile" in engine
    assert "profile.activation_uses_trailing_distance" in scheduler
    assert "profile.pre_tighten_trail_distance_steps*step" in scheduler
    assert "CustomLockOffsetPrice" in main
    assert "lock_offset_price" in types
    assert "config.lock_offset_price=0.2" in profile


def test_latest_profile_uses_observed_two_stage_trailing():
    main = app_source()
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    scheduler = (
        ROOT / "mql5" / "include" / "StopScheduler.mqh"
    ).read_text(encoding="utf-8")
    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(
        encoding="utf-8"
    )

    assert "pre_tighten_trail_distance_steps" in types
    assert "tighten_trigger_steps" in types
    assert "CustomPreTightenTrailDistanceSteps" in main
    assert "CustomTightenTriggerSteps" in main
    assert "config.pre_tighten_trail_distance_steps=2.0" in profile
    assert "config.tighten_trigger_steps=3.0" in profile
    assert "favorable_steps>=profile.tighten_trigger_steps" in scheduler
    assert "profile.pre_tighten_trail_distance_steps" in scheduler


def test_custom_profile_can_override_recent_lifecycle_for_calibration():
    main = app_source()
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(
        encoding="utf-8"
    )

    assert "custom.cycle_target_money=CustomCycleTargetMoney" in main
    assert "custom.cancel_before_close=CustomCancelBeforeClose" in main
    assert (
        "custom.deployment_fill_cooldown_seconds="
        "CustomDeploymentFillCooldownSeconds"
    ) in main
    assert "custom.close_interval_seconds=CustomCloseIntervalSeconds" in main
    assert "custom.restart_delay_ms=CustomRestartDelayMs" in main
    assert (
        "custom.stop_update_interval_seconds="
        "CustomStopUpdateIntervalSeconds"
    ) in main
    assert "custom.max_stop_updates_per_pass=CustomMaxStopUpdatesPerPass" in main
    assert "custom.stop_scan_newest_first=CustomStopScanNewestFirst" in main
    assert "custom.stop_updates_on_timer=CustomStopUpdatesOnTimer" in main
    assert (
        "custom.activation_uses_trailing_distance="
        "CustomActivationUsesTrailingDistance"
    ) in main
    assert "custom.rearm_delay_seconds=CustomRearmDelaySeconds" in main
    assert (
        "custom.pre_tighten_trail_distance_steps="
        "CustomPreTightenTrailDistanceSteps"
    ) in main
    assert "custom.tighten_trigger_steps=CustomTightenTriggerSteps" in main
    assert "config.cycle_target_money=custom.cycle_target_money" in profile
    assert "config.cancel_before_close=custom.cancel_before_close" in profile
    assert (
        "config.deployment_fill_cooldown_seconds="
        "custom.deployment_fill_cooldown_seconds"
    ) in profile
    assert "config.close_interval_seconds=custom.close_interval_seconds" in profile
    assert "config.restart_delay_ms=custom.restart_delay_ms" in profile
    assert (
        "config.stop_update_interval_seconds="
        "custom.stop_update_interval_seconds"
    ) in profile
    assert (
        "config.max_stop_updates_per_pass="
        "custom.max_stop_updates_per_pass"
    ) in profile
    assert "config.stop_scan_newest_first=custom.stop_scan_newest_first" in profile
    assert "config.stop_updates_on_timer=custom.stop_updates_on_timer" in profile
    assert (
        "config.activation_uses_trailing_distance="
        "custom.activation_uses_trailing_distance"
    ) in profile
    assert "config.rearm_delay_seconds=custom.rearm_delay_seconds" in profile
    assert (
        "config.pre_tighten_trail_distance_steps="
        "custom.pre_tighten_trail_distance_steps"
    ) in profile
    assert "config.tighten_trigger_steps=custom.tighten_trigger_steps" in profile
    assert "cycle_target_money" in types


def test_stop_update_cadence_and_selection_are_calibratable():
    engine = ENGINE.read_text(encoding="utf-8")
    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(
        encoding="utf-8"
    )

    assert "stop_update_interval_seconds" in types
    assert "max_stop_updates_per_pass" in types
    assert "stop_scan_newest_first" in types
    assert "stop_updates_on_timer" in types
    assert "rearm_delay_seconds" in types
    assert "rearm_after" in types
    assert "m_last_stop_update_at" in engine
    assert "m_profile.stop_update_interval_seconds" in engine
    assert "m_profile.max_stop_updates_per_pass" in engine
    assert "m_profile.stop_scan_newest_first" in engine
    assert "m_profile.stop_updates_on_timer" in engine
    assert "if(!m_profile.stop_updates_on_timer)" in engine
    assert "if(m_profile.stop_updates_on_timer)" in engine
    assert "CurrentServerMs()<level_state.rearm_after_msc" in engine
    assert "m_profile.rearm_delay_seconds" in engine


def test_atr_restore_calculates_step_before_reconstructing_anchor():
    source = ENGINE.read_text(encoding="utf-8")
    restore_cycle = source.split("bool RestoreCycle(void)", 1)[1].split(
        "void PersistCycle(void)", 1
    )[0]

    branch_marker = "else if(m_profile.step_mode==STR_STEP_ATR)"
    assert branch_marker in restore_cycle
    atr_branch = restore_cycle.split(branch_marker, 1)[1].split("else", 1)[0]

    assert atr_branch.index("m_step=CalculateStep(price);") < atr_branch.index(
        "m_anchor=NormalizePrice("
    )
    assert "if(m_step<=0.0)" in atr_branch


def test_initialization_fails_closed_when_owned_cycle_cannot_be_restored():
    source = ENGINE.read_text(encoding="utf-8")
    initialize = source.split("bool Initialize(", 1)[1].split(
        "void Shutdown(void)", 1
    )[0]

    owned_cycle_check = (
        "bool has_owned_cycle=(OwnedOrderCount()>0 || OwnedPositionCount()>0);"
    )
    restore_guard = (
        "if((has_owned_cycle || has_persisted_restart) &&\n"
        "         !adopted_existing_shadow_cycle &&\n"
        "         !RestoreCycle())"
    )

    assert owned_cycle_check in initialize
    assert restore_guard in initialize
    assert "if(!AdoptExistingShadowCycle())" in initialize
    assert initialize.index(restore_guard) < initialize.index(
        "EventSetMillisecondTimer"
    )


def test_gateway_manages_positions_by_ticket():
    source = GATEWAY.read_text(encoding="utf-8")

    assert "request.position = position_ticket" in source
    assert "TRADE_ACTION_SLTP" in source
    assert "TRADE_ACTION_REMOVE" in source
    assert "TRADE_ACTION_PENDING" in source
    assert "OpenMarket" in source


def test_gateway_reconciles_accepted_pending_order_when_ordersend_returns_false():
    source = GATEWAY.read_text(encoding="utf-8")
    send = source.split(
        "bool Send(MqlTradeRequest &request", 1
    )[1].split("public:", 1)[0]

    assert "ulong FindMatchingPendingOrder(" in source
    assert send.count("FindMatchingPendingOrder(request)") >= 2
    assert "result.retcode=TRADE_RETCODE_PLACED;" in source
    assert "result.order=matching_order;" in source
    assert "OrderSend reconciled accepted pending order" in source
    assert send.index("FindMatchingPendingOrder(request)") < send.index(
        "OrderSend(request,result)"
    )


def test_gateway_reconciles_accepted_position_close_when_ordersend_returns_false():
    source = GATEWAY.read_text(encoding="utf-8")
    send = source.split(
        "bool Send(MqlTradeRequest &request", 1
    )[1].split("public:", 1)[0]

    assert "bool ReconcileAcceptedPositionClose(" in source
    assert "position_volume_before" in send
    assert "request.action==TRADE_ACTION_DEAL" in send
    assert "request.position>0" in send
    assert "PositionSelectByTicket(request.position)" in send
    assert "PositionGetDouble(POSITION_VOLUME)" in send
    assert "ReconcileAcceptedPositionClose(" in send
    assert "OrderSend reconciled accepted position close" in source


def test_historical_profiles_convert_crossed_levels_to_recovery_orders():
    engine = ENGINE.read_text(encoding="utf-8")
    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(
        encoding="utf-8"
    )

    assert '"STR ORB"' in engine
    assert '"STR ORS"' in engine
    assert "IsHistoricalProfile" in engine
    assert 'LogEvent("deferred"' in engine
    assert "recovery_done" in types
    assert "!level_state.recovery_done" in engine


def test_profile_presets_exist_with_expected_defaults():
    expected = {
        "historical_50.set": "Profile=0",
        "historical_60.set": "Profile=1",
        "aggressive_30.set": "Profile=2",
        "low_risk_30.set": "Profile=3",
        "latest_30.set": "Profile=4",
    }
    for filename, profile_line in expected.items():
        content = (ROOT / "profiles" / filename).read_text(encoding="utf-8-sig")
        assert profile_line in content
        assert "ReplicaMode=true" in content
        assert "SafetyEnabled=false" in content


def test_build_install_and_real_tick_tester_configuration_exist():
    build = BUILD_SCRIPT.read_text(encoding="utf-8")
    install = INSTALL_SCRIPT.read_text(encoding="utf-8")
    tester = TESTER_CONFIG.read_text(encoding="utf-8")

    assert "MetaEditor64.exe" in build
    assert "/compile:" in build
    assert "StraddleReplica.ex5" in install
    assert "Expert=StraddleReplica\\StraddleReplica.ex5" in tester
    assert "Model=4" in tester
    assert "Profile=4" in tester


def test_replica_exposes_fail_closed_shadow_mode_inputs():
    source = app_source()
    types = TYPES.read_text(encoding="utf-8")

    assert "ENUM_STR_RUNTIME_MODE" in types
    assert "STR_RUNTIME_NORMAL" in types
    assert "STR_RUNTIME_SHADOW" in types
    assert "RuntimeMode" in source
    assert "ShadowCommandFile" in source
    assert "ShadowAckFile" in source
    assert "ShadowCommandMaxAgeMs" in source


def test_shadow_mode_has_command_poll_reset_and_exact_cycle_start():
    engine = ENGINE.read_text(encoding="utf-8")

    assert "PollShadowCommand" in engine
    assert "BeginShadowReset" in engine
    assert "StartShadowCycle" in engine
    assert "shadow_reset_complete" in engine
    assert "shadow_start_rejected" in engine


def test_shadow_command_sequence_and_cycle_identity_survive_restart():
    engine = ENGINE.read_text(encoding="utf-8")

    assert 'GlobalKey("shadow_seq")' in engine
    assert "PersistShadowSequence" in engine
    assert "RestoreShadowSequence" in engine
    assert "ReadShadowAckState" in engine
    assert "restored_shadow_cycle" in engine
    assert "m_cycle_id=restored_shadow_cycle" in engine
    assert "restored_shadow_status" in engine
    assert 'restored_shadow_status=="RESETTING"' in engine
    assert "m_shadow_reset_active=true" in engine


def test_shadow_mode_can_guardedly_adopt_existing_demo_cycle():
    app = APP.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")

    assert (
        "input bool AllowShadowAdoptExistingCycle = false"
        in app
    )
    assert "runtime.allow_shadow_adopt_existing_cycle" in app
    assert (
        "bool              allow_shadow_adopt_existing_cycle;"
        in types
    )
    assert "AdoptExistingShadowCycle" in engine
    assert 'WriteShadowAck("ADOPTED"' in engine
    assert "existing_cycle_adoption_disabled" in engine
    assert '"runtime_shadow_adopt_existing_cycle"' in engine


def test_replica_telemetry_uses_real_utc_and_preserves_server_time():
    engine = ENGINE.read_text(encoding="utf-8")

    assert "TimeToStruct(TimeGMT(),utc_time)" in engine
    assert '"utc_time","server_time"' in engine
    assert "TimeToStruct(TimeTradeServer(),server_time)" in engine


def test_replica_writes_account_and_symbol_terms_manifest():
    engine = ENGINE.read_text(encoding="utf-8")

    assert "WriteRuntimeManifest" in engine
    assert "ACCOUNT_LIMIT_ORDERS" in engine
    assert "ACCOUNT_LEVERAGE" in engine
    assert "SYMBOL_TRADE_TICK_VALUE" in engine
    assert "SYMBOL_TRADE_TICK_VALUE_PROFIT" in engine
    assert "SYMBOL_TRADE_TICK_VALUE_LOSS" in engine
    assert "SYMBOL_TRADE_CONTRACT_SIZE" in engine
    assert "SYMBOL_SWAP_LONG" in engine
    assert "SYMBOL_SWAP_SHORT" in engine


def test_runtime_manifest_fingerprints_effective_shadow_parameters():
    engine = ENGINE.read_text(encoding="utf-8")

    for required in (
        '"runtime_mode"',
        '"runtime_magic"',
        '"runtime_inter_order_delay_ms"',
        '"runtime_deviation_points"',
        '"runtime_shadow_command_max_age_ms"',
        '"profile"',
        '"profile_levels_per_side"',
        '"profile_step_mode"',
        '"profile_fixed_step"',
        '"profile_anchor_divisor"',
        '"profile_cycle_target_money"',
        '"profile_cancel_before_close"',
        '"profile_deployment_fill_cooldown_seconds"',
        '"profile_close_interval_seconds"',
        '"profile_restart_delay_ms"',
        '"profile_rearm_delay_seconds"',
        "profile_lot_",
    ):
        assert required in engine


def test_cycle_realized_is_rebuilt_from_unique_history_deals():
    engine = ENGINE.read_text(encoding="utf-8")
    ledger = ROOT / "mql5" / "include" / "CycleDealLedger.mqh"
    assert ledger.exists()
    ledger_source = ledger.read_text(encoding="utf-8")

    assert '#include "CycleDealLedger.mqh"' in engine
    assert "long              m_cycle_started_msc;" in engine
    assert 'GlobalKey("start_msc")' in engine
    assert "m_deal_ledger.TryRecalculate(" in engine
    assert "m_cycle_realized+=" not in engine
    assert "DEAL_TIME_MSC" in ledger_source
    assert "DEAL_ENTRY_OUT" in ledger_source
    assert "DEAL_ENTRY_OUT_BY" in ledger_source
    assert "DEAL_ENTRY_INOUT" in ledger_source
    assert "DEAL_FEE" in ledger_source


def test_restore_hydrates_identity_and_accounting_before_logging():
    engine = ENGINE.read_text(encoding="utf-8")
    restore = engine.split("bool RestoreCycle(void)", 1)[1].split(
        "void PersistCycle", 1
    )[0]

    reconcile_index = restore.index("ReconcileLevels();")
    assert restore.index('GlobalKey("event_seq")') < reconcile_index
    assert restore.index('GlobalKey("realized")') < reconcile_index
    assert restore.index('CycleIdFromUtc("local"') < reconcile_index
    assert restore.index("m_deal_ledger.TryRecalculate(") < reconcile_index
    assert "ReconcileLevels(false);" in restore


def test_realized_restore_uses_persisted_exit_count_until_history_is_ready():
    engine = ENGINE.read_text(encoding="utf-8")
    ledger = (
        ROOT / "mql5" / "include" / "CycleDealLedger.mqh"
    ).read_text(encoding="utf-8")

    assert "bool TryRecalculate(" in ledger
    assert "int &exit_deal_count" in ledger
    assert "int               m_cycle_exit_deal_count;" in engine
    assert 'GlobalKey("realized_count")' in engine
    assert "recalculated_count>=persisted_realized_count" in engine


def test_normal_cycles_have_identity_sequence_and_basket_snapshot():
    engine = ENGINE.read_text(encoding="utf-8")

    assert "ulong             m_event_sequence;" in engine
    assert "string NewCycleId(" in engine
    assert 'GlobalKey("event_seq")' in engine
    assert '"schema_version","event_sequence","event_id"' in engine
    assert '"deal_ticket","order_ticket","position_ticket"' in engine
    assert '"cycle_realized","floating_profit","cycle_net"' in engine
    assert '"basket_target","evidence_grade"' in engine
    assert 'LogLifecycleEvent("rearm_eligible"' in engine
    assert 'LogLifecycleEvent("basket_trigger"' in engine
    assert 'LogLifecycleEvent("cycle_complete"' in engine
    assert 'LogLifecycleEvent("cycle_restart"' in engine


def test_duplicate_active_level_identity_blocks_new_placement():
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")

    assert "int               active_order_count;" in types
    assert "int               active_position_count;" in types
    assert "bool              duplicate_identity;" in types
    assert "DetectDuplicateLevelIdentity" in engine
    assert '"duplicate_level_identity"' in engine
    assert "if(level_state.duplicate_identity)" in engine


def test_same_ticket_order_position_transition_is_one_level_identity():
    engine = ENGINE.read_text(encoding="utf-8")
    detector = engine.split(
        "void DetectDuplicateLevelIdentity", 1
    )[1].split("void ReconcileLevels", 1)[0]

    assert "int entity_count=" in detector
    assert "level_state.active_order_count==1" in detector
    assert "level_state.active_position_count==1" in detector
    assert "level_state.order_ticket==level_state.position_ticket" in detector
    assert "entity_count=1;" in detector
    assert "bool duplicate=(entity_count>1);" in detector


def test_rearm_requires_explicit_stop_exit_eligibility():
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    schedule = engine.split("void ScheduleLevelRearm", 1)[1].split(
        "long CurrentUtcMs", 1
    )[0]
    rearm = engine.split("void RearmOneMissingLevel", 1)[1].split(
        "double OwnedFloatingProfit", 1
    )[0]

    assert "bool              rearm_requested;" in types
    assert "rearm_requested=true" in schedule
    assert "m_buy_levels[index].rearm_requested" in rearm
    assert "m_sell_levels[index].rearm_requested" in rearm
    assert "ArmMissingLevelsAfterRestore" in engine


def test_stop_exit_metadata_waits_for_parseable_level_identity():
    engine = ENGINE.read_text(encoding="utf-8")
    readiness = engine.split("bool DealMetadataReady", 1)[1].split(
        "long CurrentUtcMs", 1
    )[0]

    assert "bool stop_exit=(" in readiness
    assert "if(stop_exit &&" in readiness
    assert "!ParseLevelComment(" in readiness
    assert "level_comment," in readiness
    assert "return false;" in readiness


def test_duplicate_deal_callbacks_are_processed_once():
    engine = ENGINE.read_text(encoding="utf-8")
    deal_processor = engine.split(
        "bool ProcessSelectedDeal", 1
    )[1].split("void ProcessPendingDeals", 1)[0]

    assert "ulong             m_last_processed_deal_ticket;" in engine
    assert "ulong             m_processed_deal_tickets[];" in engine
    assert "bool DealAlreadyProcessed(" in engine
    assert "void RememberProcessedDeal(" in engine
    assert "DealAlreadyProcessed(deal_ticket)" in deal_processor
    assert "RememberProcessedDeal(deal_ticket)" in deal_processor


def test_processed_deal_restore_reads_variable_width_telemetry_by_line():
    engine = ENGINE.read_text(encoding="utf-8")
    loader = engine.split(
        "void LoadProcessedDealsFromTelemetry", 1
    )[1].split("int OwnedOrderCount", 1)[0]

    assert "FileIsLineEnding(handle)" in loader
    assert "if(field_count<=22)" in loader
    assert "for(;field_count<30" not in loader


def test_stop_request_comment_falls_back_to_position_history():
    engine = ENGINE.read_text(encoding="utf-8")
    request_comment = engine.split("string RequestComment", 1)[1].split(
        "void LogTradeRequest", 1
    )[0]

    assert "HistoryOrderSelect(request.position)" in request_comment
    assert "HistoryOrderGetString(request.position,ORDER_COMMENT)" in request_comment


def test_trade_transaction_reconcile_defers_duplicate_reporting():
    engine = ENGINE.read_text(encoding="utf-8")
    transaction_handler = engine.split("void OnTradeTransaction", 1)[1]

    assert (
        "void ReconcileLevels(const bool report_duplicates=true)"
        in engine
    )
    assert "if(report_duplicates)" in engine
    assert "ReconcileLevels(false);" in transaction_handler


def test_normal_cycle_identity_and_sequence_survive_terminal_restart():
    engine = ENGINE.read_text(encoding="utf-8")

    assert "datetime          m_cycle_started_utc;" in engine
    assert "string CycleIdFromUtc(" in engine
    assert 'GlobalKey("start_utc")' in engine
    assert (
        'm_cycle_id=CycleIdFromUtc("local",m_cycle_started_utc);'
        in engine
    )
    assert 'GlobalVariableSet(GlobalKey("event_seq")' in engine
    assert "GlobalVariablesFlush();" in engine


def test_basket_trigger_uses_pure_evaluator():
    engine = ENGINE.read_text(encoding="utf-8")

    assert '#include "BasketEvaluator.mqh"' in engine
    assert "CBasketEvaluator m_basket_evaluator;" in engine
    assert "SBasketSnapshot basket=" in engine
    assert "if(basket.triggered)" in engine


def test_stop_formula_is_isolated_from_position_iteration():
    engine = ENGINE.read_text(encoding="utf-8")
    scheduler = ROOT / "mql5" / "include" / "StopScheduler.mqh"
    assert scheduler.exists()
    source = scheduler.read_text(encoding="utf-8")

    assert '#include "StopScheduler.mqh"' in engine
    assert "CStopScheduler m_stop_scheduler;" in engine
    assert "m_stop_scheduler.Calculate(" in engine
    assert "bool Calculate(" in source
    assert "tighten_trigger_steps" in source
    assert "pre_tighten_trail_distance_steps" in source


def test_bound_account_and_safe_rearm_guards_exist():
    app = APP.read_text(encoding="utf-8")
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")

    assert "input bool RequireBoundAccount = STR_REQUIRE_BOUND_DEFAULT" in app
    assert "input bool SafetyEnabled = STR_SAFETY_ENABLED_DEFAULT" in app
    assert "bool              require_bound_account;" in types
    assert "runtime.require_bound_account=RequireBoundAccount" in app
    assert "m_runtime.require_bound_account" in engine
    assert "ExposureAllowsRearm" in engine
    assert '"safety_rearm_blocked"' in engine
