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
        "input ENUM_STR_PROFILE Profile = STR_DEFAULT_PROFILE",
        "#define STR_DEFAULT_PROFILE STARWAVE_30",
        "input ulong MagicNumber = STR_DEFAULT_MAGIC",
        "#define STR_DEFAULT_MAGIC 26011001",
        "input bool ReplicaMode = true",
        "input datetime ReplicaStartTime = 0",
        "input int InterOrderDelayMs = 100",
        "input double CustomPreTightenTrailDistanceSteps = 2.0",
        "input double CustomTightenTriggerSteps = 3.0",
        # The five defaults below used to carry pre-Starwave placeholder values
        # (false / false / 0.0 / false / 3000).  They are now the measured
        # Starwave/Target settings, so CUSTOM_PROFILE is a Starwave clone out of
        # the box and only the tier lots and N need touching to reproduce any of
        # the seven observed lot ladders.
        #
        # CustomCycleTargetMoney was the sixth and last placeholder: it shipped
        # 25.0 while ProfileCatalog.mqh (case STARWAVE_30) brackets the measured
        # basket target to (26.41, 26.51] from the 3-cycle censored run over
        # 2026-08-24 19:22..19:49 -- a bracket that EXCLUDES 25.0.  Because
        # cycle_target_money is the EA's only exit, the placeholder banked every
        # CUSTOM_PROFILE basket 5.66% early.  This assertion and STARWAVE_30's
        # catalogue value are tied together by
        # test_custom_basket_target_default_matches_the_starwave_catalogue.
        "input bool CustomActivationUsesTrailingDistance = true",
        "input bool CustomStopUpdatesOnTimer = false",
        "input int CustomRearmDelaySeconds = 0",
        "input int CustomStopUpdateIntervalSeconds = 0",
        "input int CustomMaxStopUpdatesPerPass = 0",
        "input bool CustomStopScanNewestFirst = true",
        "input bool SafetyEnabled = STR_SAFETY_ENABLED_DEFAULT",
        "input double CustomLockOffsetPrice = 0.2",
        "input double CustomCycleTargetMoney = 26.5",
        "input bool CustomCancelBeforeClose = true",
        "input int CustomDeploymentFillCooldownSeconds = 0",
        "input int CustomCloseIntervalSeconds = 0",
        "input int CustomRestartDelayMs = 2000",
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
        "JUNE_2K",
        "STARWAVE_30",
        "STARWAVE_20",
        "STARWAVE_30_HIGH",
        "STARWAVE_30_MID",
        "STARWAVE_20_WIDE",
        "STARWAVE_20_LIGHT",
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
        "case STARWAVE_30:", 1
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
    assert "if(CyclePositionCount()>0 && !CloseIntervalElapsed())" in engine
    restart_drain = engine.split("case CYCLE_RESTARTING:", 1)[1].split(
        "case CYCLE_HALTED:", 1
    )[0]
    assert "if(CloseIntervalElapsed())" in restart_drain
    assert "TryCloseOneOwnedPosition()" in restart_drain


def test_latest_profile_serializes_stop_moves_on_the_same_twenty_second_clock():
    """The 2026-07-24 change paced the STOPS too, not just the flatten sweep.

    This was implemented as a half-measure for a long time: close_interval_seconds
    went to 20 while stop_update_interval_seconds stayed at 0, which made the
    replica post-break on the flatten and pre-break on the stops.

    The proof is by elimination on PRICE TWINS -- pairs of positions whose armed
    stop prices agree within 0.05 on the same side.  Two live stops sitting at the
    same price must be taken out by the SAME tick, so a twin pair that exits far
    apart cannot have had both stops live at that price; the second was moved there
    only after the first was already gone.

        twin pairs        n    med gap   <0.1s apart   15-25 s apart
        TARGET pre    18700      0.00s         16265              11
        TARGET post     252     20.13s             0             165
        OURS             68      0.01s            47               1

    Zero of 252 post-break twins fire together and 165 land in the 15-25 s bucket.
    The pre-break book is the control: same stop mathematics, no serialization,
    87% of twins inside 100 ms -- which is exactly what an interval of 0 produces
    and exactly what our own book shows.

    Corroborated on the whole stop population: the post-break Target has 0 of 841
    consecutive stop-outs closer than 100 ms (minimum gap 0.2890 s) where we have
    43 of 341 (12.61%); and consecutive stop-out gaps in the 5-200 s band land
    within 0.5 s of a x20 multiple for 320 of 498 post-break Target gaps (64.3%,
    mode exactly x1) against 170 of 3034 pre-break (5.6%).

    Do NOT re-derive this value from the pooled whole Target book.  Pooled it reads
    52% sub-100 ms and appears to endorse an interval of 0, but that figure is 94%
    pre-break rows and inverts on the comparable slice.
    """
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    latest_profile = profile.split("case LATEST_30:", 1)[1].split(
        "case STARWAVE_30:", 1
    )[0]
    stop_updater = engine.split("void UpdatePositionStops(void)", 1)[1].split(
        "void CheckCycleTargets", 1
    )[0]

    assert "config.stop_update_interval_seconds=20;" in latest_profile, (
        "the post-break Target moves at most one stop per 20 s -- 0 of 841 "
        "consecutive stop-outs under 100 ms and 252 price-twin pairs at median "
        "20.13 s; an interval of 0 reproduces the PRE-break regime instead"
    )
    assert "config.stop_update_interval_seconds=0;" not in latest_profile

    # The consuming gate, and the fact that the clock is stamped BEFORE the scan --
    # so a pass that finds nothing to tighten still spends its slot.  That makes the
    # rate "at most one stop move per 20 s", which is the shape the Target shows
    # (mostly exactly 20 s with an 80-of-252 tail beyond 25 s).
    assert "m_profile.stop_update_interval_seconds>0 &&" in stop_updater
    assert (
        "now-m_last_stop_update_at<m_profile.stop_update_interval_seconds"
        in stop_updater
    )
    assert stop_updater.index("m_last_stop_update_at=now;") < stop_updater.index(
        "for(int offset=0;offset<position_total;offset++)"
    )
    # One modification per pass, newest first, driven off the timer.
    assert "config.max_stop_updates_per_pass=1" in latest_profile
    assert "config.stop_scan_newest_first=true" in latest_profile
    assert "config.stop_updates_on_timer=true" in latest_profile


def test_flatten_sweep_walks_the_position_list_newest_first():
    """The flatten sweep must be LIFO, because the Target's is.

    tools/forensics/sweep_lifo.py measures the Target's pair-inversion rate --
    the fraction of leg pairs closed in reverse-of-open order -- at 0.983 over
    its 29 post-break sweeps, with 14 of 29 in EXACTLY reverse-of-open order and
    0 of 29 in open order.  Pre-break: 0.853, with 60 exactly reverse and 1
    exactly forward out of 219.  MT5 appends new positions to the end of the
    list, so a DESCENDING index walk closes newest-first and reproduces that;
    an ascending walk is FIFO, which the Target essentially never does.

    Commit 9a0cf62 flipped this to ascending on the stated grounds that the
    Target closes in ascending GRID LEVEL order, citing an audit_sweep_order.py
    that does not exist in this repository.  That claim does not reproduce.
    tools/forensics/sweep_level_order.py reads each Target flatten leg's level
    straight off the Target's own position comment ("STR B7" matches 99.3% of its
    17,632 positions and 100.0% of the 1,097 post-break ones) and finds median
    rho(close order, level) = -0.086 over 219 pre-break sweeps and -0.400 over 29
    post-break, with outer-first sweeps outnumbering inner-first 13 to 2 in the
    post-break regime.  There is no ascending rule to match; if anything the sign
    points the other way.  This test pins the direction that IS measured.
    """
    engine = ENGINE.read_text(encoding="utf-8")

    body = engine.split("bool TryCloseOneOwnedPosition(void)", 1)[1].split(
        "void CloseOnePosition(void)", 1
    )[0]
    assert "for(int index=PositionsTotal()-1;index>=0;index--)" in body, (
        "the flatten sweep must walk the position list DESCENDING (newest first / "
        "LIFO); the Target's inversion rate is 0.983 post-break with 0 of 29 "
        "sweeps in open order -- see tools/forensics/sweep_lifo.py"
    )
    assert "for(int index=0;index<PositionsTotal();index++)" not in body, (
        "an ascending walk makes the sweep FIFO, which the Target does not do"
    )
    # The anti-stall cursor must survive the direction, otherwise a quote-rejected
    # ticket blocks the basket instead of costing one pacing interval.
    assert "if(owned<=m_close_skip)" in body
    assert "m_close_skip++" in body


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

    # The pacing gate must be conditional on there being something left to close,
    # so a sweep that has already emptied the book falls straight through to flat
    # detection instead of idling for another close_interval_seconds.
    #
    # The counter is the CYCLE-scoped one, not the book-wide one: with
    # replica_orphan_leak on, the orphans the Target abandons are still in the
    # book forever, so OwnedPositionCount() never returns to 0 and the sweep
    # would never see itself as finished.  CyclePositionCount() falls back to
    # OwnedPositionCount() when the leak is off, so the non-leak profiles are
    # unaffected.
    assert "CyclePositionCount()>0" in close_interval_guard
    assert "OwnedPositionCount()" not in close_interval_guard


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
        "case STARWAVE_30:", 1
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
    # Cycle-scoped, like the basket: the rescue's drawdown floor has to measure
    # the same float the basket target measures, otherwise with the orphan leak on
    # the abandoned positions' permanent negative float would hold the rescue
    # armed forever.  CycleFloatingProfit() == OwnedFloatingProfit() when the leak
    # is off.  (The parameter is dormant either way -- STR AVB/AVS and STR ORB/ORS
    # are absent from the entire Target tape, so its rescue never fired.)
    assert "CycleFloatingProfit()>-m_profile.trend_rescue_drawdown_money" in engine
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
        "case STARWAVE_30:", 1
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


def test_rejected_deployment_level_is_deferred_to_one_tail_retry_then_abandoned():
    """Target-EA parity: ONE retry at the tail of the same burst, then abandon.

    DIV-5.  The 901018 tape carries ZERO rejected orders in 54,742 -- state is
    only ever filled (35,430) or canceled (19,312) -- so a refused level leaves
    no row behind and the retry can only be read off DISPATCH ORDER.  It is
    plainly visible there: 70 of the 285 recovered deployment bursts dispatch a
    level-1 leg AFTER the highest level of the burst (HISTORICAL_60 68 of 78,
    HISTORICAL_50 2 of 101, STARWAVE_30 0 of 103), and every one of
    HISTORICAL_60's 71 adjacent-rank inversions is S60 -> S1 (x37), S60 -> B1
    (x31) or S1 -> B1 (x3).

    Three facts pin that to the EA's own dispatch rather than to the reader or
    to a re-arm folded into the burst:
      * timestamps and tickets are strictly monotone across every swap -- 0
        swaps share a millisecond, 0 have non-monotone tickets, and the tickets
        run consecutively (20216347/48/49/50);
      * the gap from the last first-pass leg to the retry leg is ONE
        inter_order_delay_ms tick (110/113/111/111/117/116 ms on the first six
        HISTORICAL_60 bursts), not the ~12 s a fresh burst would cost;
      * the retry lands on the EXACT original lattice price.  Burst 2026-07-02
        21:52:35 has B60=4148.27 and S60=4093.07, so anchor=4120.67 and
        step=55.20/120=0.46, and its tail leg is B1 at 4121.13 = anchor+step.

    The first-pass refusal is the broker minimum stop distance, which is why
    level 1 -- one step from the anchor -- is the level affected: 0 of 66 bursts
    below step 0.60 are clean against 202 of 208 (97.12%) at or above 0.70, and
    within HISTORICAL_60 the clean bursts run 0.70..0.78 and the deferred ones
    0.37..0.64 with zero overlap.

    Retry ONCE: 7 of 78 HISTORICAL_60 bursts and 2 of 103 STARWAVE_30 bursts end
    with no level-1 leg at all, so the second attempt may also fail and the level
    is then abandoned for the cycle.  And it must never abort -- the three
    incomplete Starwave lattices (2026-08-21 with S15..S25 missing, 08-24
    scattered, 08-27 only S1) each traded on as-is for days.
    """
    engine = ENGINE.read_text(encoding="utf-8")
    deploy = function_body(engine, "void DeployOne(void)")

    # The abort-and-re-anchor path is still gone.
    assert "m_gateway.LastRetcode()==TRADE_RETCODE_INVALID_PRICE" not in deploy
    assert "m_state=CYCLE_CANCELING" not in deploy
    assert '"deployment_abort"' not in deploy

    # A second slot space, appended at the tail of the SAME burst.
    assert "int sweep_slots=m_profile.levels_per_side*2;" in deploy
    assert "int retry_slots=sweep_slots*2;" in deploy
    assert "if(m_deploy_index>=retry_slots)" in deploy
    assert "bool retry_pass=(m_deploy_index>=sweep_slots);" in deploy
    assert (
        "int slot=(retry_pass ? m_deploy_index-sweep_slots : m_deploy_index);"
        in deploy
    )

    # A failure defers and advances; it never stalls on the same level.
    assert '"deployment_level_rejected"' in deploy
    assert '"deployment_skip"' in deploy
    assert '"deployment_level_retried"' in deploy
    assert '"_deferred"' in deploy
    assert '"_retry_abandoned"' in deploy
    assert deploy.index('"deployment_skip"') < deploy.rindex("m_deploy_index++;")
    assert "PersistCycle();" in deploy

    # Exactly one retry: the mark is cleared BEFORE the second attempt, so a
    # second failure abandons the level instead of queueing a third pass.
    assert deploy.count("deploy_deferred=false;") == 2
    assert deploy.index("deploy_deferred=false;") < deploy.index(
        "bool placed=(is_buy ? PlaceLevel("
    )

    # Degenerate guard: a sweep that armed nothing re-anchors instead of idling.
    assert '"deployment_empty"' in deploy
    assert "m_state=CYCLE_RESTARTING;" in deploy
    assert "m_restart_started_at=TimeCurrent();" in deploy


def test_deployment_retry_pass_never_repends_a_level_that_already_placed():
    """The retry is driven by an explicit mark, not by "is this slot empty?".

    Deciding the retry from level live-state would misfire on exactly the
    profiles that matter.  Level 1 is the closest pending to the anchor and
    routinely FILLS during the 12 s burst itself; ReconcileLevels() then clears
    has_pending and sets has_position, and on a replica_orphan_leak profile
    PlaceLevel()'s guard (!OrphanLeakActive() && level_state.has_position) does
    not fire -- so an emptiness test would arm a SECOND pending at the tail of
    every burst and destroy STARWAVE_30's measured 103/103 clean interleave.
    The mark is therefore set ONLY on a genuine first-pass placement failure.
    """
    engine = ENGINE.read_text(encoding="utf-8")
    deploy = function_body(engine, "void DeployOne(void)")

    # Set on failure, and only on the first pass.
    assert deploy.count("deploy_deferred=true;") == 2
    guard = deploy.index("if(!retry_pass)")
    reason = deploy.index("string reject_reason=StringFormat(")
    for mark in (
        "m_buy_levels[level_index].deploy_deferred=true;",
        "m_sell_levels[level_index].deploy_deferred=true;",
    ):
        assert guard < deploy.index(mark) < reason

    # The mark, not level live-state, decides whether a retry slot is attempted.
    assert "!DeployDeferred(m_deploy_index-sweep_slots)" in deploy
    code = "\n".join(
        line for line in deploy.splitlines() if not line.lstrip().startswith("//")
    )
    assert "has_pending" not in code
    assert "has_position" not in code

    helper = function_body(engine, "bool DeployDeferred(const int slot) const")
    assert "m_buy_levels[level_index].deploy_deferred" in helper
    assert "m_sell_levels[level_index].deploy_deferred" in helper
    assert "if(level_index<0 || level_index>=m_profile.levels_per_side)" in helper


def test_clean_deployment_burst_completes_on_the_tick_it_always_did():
    """The 2N retry slots are consumed in-tick when nothing was deferred.

    One timer tick per skipped retry slot would put the tail leg ~12 s after S60
    on a 60-level burst.  The tape says one tick: the S60 -> tail-leg gap is
    110..117 ms, and STARWAVE_30's 103 clean bursts show no extra dispatch at
    all.  So the fast-forward has to run inside the same call, ahead of both the
    completion guard and the fill cooldown's early return.
    """
    engine = ENGINE.read_text(encoding="utf-8")
    deploy = function_body(engine, "void DeployOne(void)")

    loop = "while(m_deploy_index>=sweep_slots &&"
    assert loop in deploy
    assert "m_deploy_index<retry_slots &&" in deploy
    assert "!DeployDeferred(m_deploy_index-sweep_slots))" in deploy
    assert deploy.index(loop) < deploy.index("if(m_deploy_index>=retry_slots)")
    assert deploy.index(loop) < deploy.index(
        "if(m_profile.deployment_fill_cooldown_seconds>0 &&"
    )

    # The old completion test against the first-pass width alone is gone.
    assert "m_deploy_index>=m_profile.levels_per_side*2" not in deploy

    # Widening the cursor's range is only safe because nothing outside
    # DeployOne() compares or advances it -- every other site resets it to 0.
    others = engine.replace(deploy, "")
    assert "m_deploy_index++" not in others
    assert "m_deploy_index>" not in others
    assert "m_deploy_index<" not in others


def test_deploy_deferred_mark_survives_reconcile_and_dies_at_cycle_boundaries():
    """Per-cycle state that must outlive the in-burst reconcile passes.

    ReconcileLevels() runs repeatedly DURING the burst and rewrites has_pending /
    has_position as level 1 fills; the mark has to survive that or the tail retry
    could never fire at all.  ClearLiveFlags() therefore must not touch it, and
    ResetLevelState() -- the cycle boundary -- must clear it on both sides.
    """
    engine = ENGINE.read_text(encoding="utf-8")
    reset = function_body(engine, "void ResetLevelState(void)")
    assert reset.count("deploy_deferred=false;") == 2

    live = function_body(engine, "void ClearLiveFlags(void)")
    assert "deploy_deferred" not in live

    types = TYPES.read_text(encoding="utf-8")
    assert "bool              deploy_deferred;" in function_body(
        types, "struct SLevelState"
    )


def test_restart_state_cleans_residual_exposure_before_becoming_idle():
    engine = ENGINE.read_text(encoding="utf-8")
    start_cycle = engine.split("bool StartCycle(void)", 1)[1].split(
        "void DeployOne(void)", 1
    )[0]
    restarting = engine.split("case CYCLE_RESTARTING:", 1)[1].split(
        "case CYCLE_HALTED:", 1
    )[0]

    # Cycle-scoped on the position half, book-wide on the order half.  The Target
    # opened 149+ cycles while its orphan residue ratcheted 6 -> 148, so its
    # "am I flat?" test cannot have been book-wide: the very first orphan would
    # have blocked every later cycle forever.  Pendings are never orphaned, so
    # OwnedOrderCount() stays.
    assert "OwnedOrderCount()>0 || CyclePositionCount()>0" in start_cycle
    assert "TryCancelOneOwnedOrder()" in restarting
    assert "TryCloseOneOwnedPosition()" in restarting
    assert restarting.index("TryCancelOneOwnedOrder()") < restarting.index(
        "TryCloseOneOwnedPosition()"
    )
    assert restarting.index("CyclePositionCount()>0") < restarting.index(
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
    """The re-arm gate: hygienic when the leak is off, Target-exact when it is on.

    Audit D6.  The Target re-arms a level whenever that level has no pending,
    subject only to PendingPriceIsValid() and RearmDelayElapsed() -- there is no
    "the position from the last fill must have closed first" condition.  One rule
    explains all four measured buckets of the 1,120 mid-cycle re-arms uniformly
    (969 SL-gated, 87 with the position still open, 3 closed some other way, 59
    with no in-cycle fill at all), and it is what mints the orphans: the re-fill
    overwrites the level's single position pointer.

    Both halves are pinned.  The non-leak branch keeps the explicit
    rearm_requested && !has_position eligibility, so the hygienic profiles are
    unchanged; the leak branch returns true on the has-no-pending test alone.  The
    three hard vetoes (already pending, mid trend-rescue swap, duplicate identity)
    apply either way -- none of them is a Target-parity condition, they are
    internal consistency guards.
    """
    types = TYPES.read_text(encoding="utf-8")
    engine = ENGINE.read_text(encoding="utf-8")
    schedule = engine.split("void ScheduleLevelRearm", 1)[1].split(
        "long CurrentUtcMs", 1
    )[0]
    eligible = function_body(engine, "bool RearmEligible(const SLevelState &level_state) const")
    rearm = engine.split("void RearmOneMissingLevel", 1)[1].split(
        "double OwnedFloatingProfit", 1
    )[0]

    assert "bool              rearm_requested;" in types
    assert "rearm_requested=true" in schedule

    # the hygienic gate survives, unchanged, behind the leak switch
    assert "return(level_state.rearm_requested && !level_state.has_position);" in eligible
    # ...and is bypassed entirely when reproducing the Target
    assert "if(OrphanLeakActive())" in eligible
    assert eligible.index("if(OrphanLeakActive())") < eligible.index(
        "level_state.rearm_requested"
    )
    # the vetoes come first, so leak mode never re-arms a level that already has
    # a live pending, is mid trend-rescue replacement, or is quarantined
    for veto in (
        "level_state.has_pending",
        "level_state.trend_rescue_replacement",
        "level_state.duplicate_identity",
    ):
        assert veto in eligible
        assert eligible.index(veto) < eligible.index("if(OrphanLeakActive())")

    # both sides route through the shared predicate rather than testing the flag
    # inline, so there is exactly one place the gate can be got wrong
    assert "RearmEligible(m_buy_levels[index])" in rearm
    assert "RearmEligible(m_sell_levels[index])" in rearm
    assert "rearm_requested" not in rearm
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


def test_starwave_profiles_enforce_unpaced_burst_execution_and_clean_geometry():
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")
    
    # 1. STARWAVE_30 verification
    sw30 = profile.split("case STARWAVE_30:", 1)[1].split("case STARWAVE_20:", 1)[0]
    assert "config.levels_per_side=30;" in sw30
    assert "config.anchor_divisor=3000.0;" in sw30
    assert "config.close_interval_seconds=0;" in sw30
    assert "config.stop_update_interval_seconds=0;" in sw30
    assert "config.rearm_delay_seconds=0;" in sw30
    assert "config.restart_delay_ms=2000;" in sw30
    assert "config.deployment_fill_cooldown_seconds=0;" in sw30
    assert "config.stop_updates_on_timer=false;" in sw30
    assert "config.trend_rescue_enabled=false;" in sw30
    assert "SetLotTier(config,1,10,0.01);" in sw30
    assert "SetLotTier(config,11,20,0.06);" in sw30
    assert "SetLotTier(config,21,30,0.15);" in sw30
    # Basket target = the epoch's censored bracket (26.41, 26.51], banked p50 26.29
    assert "config.cycle_target_money=26.5;" in sw30

    # 2. STARWAVE_20 verification
    sw20 = profile.split("case STARWAVE_20:", 1)[1].split("case STARWAVE_30_HIGH:", 1)[0]
    assert "config.levels_per_side=20;" in sw20
    assert "config.anchor_divisor=3000.0;" in sw20
    assert "config.close_interval_seconds=0;" in sw20
    assert "config.stop_update_interval_seconds=0;" in sw20
    assert "config.rearm_delay_seconds=0;" in sw20
    assert "config.restart_delay_ms=2000;" in sw20
    assert "config.deployment_fill_cooldown_seconds=0;" in sw20
    assert "config.stop_updates_on_timer=false;" in sw20
    assert "config.trend_rescue_enabled=false;" in sw20
    assert "SetLotTier(config,1,6,0.01);" in sw20
    assert "SetLotTier(config,7,13,0.04);" in sw20
    assert "SetLotTier(config,14,20,0.15);" in sw20
    # 52-cycle epoch, the largest observed regime: bracket (6.45, 6.75], p50 6.40
    assert "config.cycle_target_money=6.5;" in sw20


def test_starwave_epoch_profiles_match_the_observed_lot_ladders():
    """Every fully-resolved Starwave lot ladder in the target tape has a profile.

    Ladders were recovered from 145 sweep-delimited cycles in
    Starwave_60542_detailed_trades.csv.  Tier boundaries obey the canonical
    floor(N/3)+1 / floor(2N/3)+1 rule, which is what pins N: a tier-2 boundary
    at 11 with a tier-3 boundary at 21 admits only N in {30,31}; a boundary pair
    of 7/14 admits only N=20.
    """
    profile = PROFILE_CATALOG.read_text(encoding="utf-8")

    # epoch 2026-08-21 14:35 -> 08-24 13:35, 10 cycles, deepest fill L23
    high = profile.split("case STARWAVE_30_HIGH:", 1)[1].split("case STARWAVE_30_MID:", 1)[0]
    assert "config.levels_per_side=30;" in high
    assert "SetLotTier(config,1,10,0.01);" in high
    assert "SetLotTier(config,11,20,0.05);" in high
    assert "SetLotTier(config,21,30,0.20);" in high
    assert "config.cycle_target_money=26.5;" in high

    # epoch 2026-08-26 17:20 -> 08-27 08:35, 18 cycles, bracket (11.33, 11.98]
    mid = profile.split("case STARWAVE_30_MID:", 1)[1].split("case STARWAVE_20_WIDE:", 1)[0]
    assert "config.levels_per_side=30;" in mid
    assert "SetLotTier(config,1,10,0.01);" in mid
    assert "SetLotTier(config,11,20,0.04);" in mid
    assert "SetLotTier(config,21,30,0.15);" in mid
    assert "config.cycle_target_money=12.0;" in mid

    # epochs 2026-08-28 17:13 -> 21:56, 13 cycles, bracket (27.73, 28.64]
    wide = profile.split("case STARWAVE_20_WIDE:", 1)[1].split("case STARWAVE_20_LIGHT:", 1)[0]
    assert "config.levels_per_side=20;" in wide
    assert "SetLotTier(config,1,6,0.01);" in wide
    assert "SetLotTier(config,7,13,0.06);" in wide
    assert "SetLotTier(config,14,20,0.15);" in wide
    assert "config.cycle_target_money=28.5;" in wide

    # epoch 2026-08-27 09:26 -> 11:03, 3 cycles, deepest fill L7.  This is the
    # last uncovered ladder: after folding manual partial-close fragments back
    # onto their parent position_id, it is the single (level, lot) pair in the
    # whole tape that no other Starwave profile reproduces.
    light = profile.split("case STARWAVE_20_LIGHT:", 1)[1].split("case CUSTOM_PROFILE:", 1)[0]
    assert "config.levels_per_side=20;" in light
    assert "SetLotTier(config,1,6,0.01);" in light
    assert "SetLotTier(config,7,13,0.03);" in light
    assert "SetLotTier(config,14,20,0.15);" in light
    assert "config.cycle_target_money=17.8;" in light

    # All Starwave epochs share one execution profile: unpaced 0s bursts, no
    # timer-driven stop updates, 2s restart, newest-first stop scan, no rescue.
    for body in (high, mid, wide, light):
        assert "config.step_mode=STR_STEP_ANCHOR_DIVISOR;" in body
        assert "config.anchor_divisor=3000.0;" in body
        assert "config.trail_distance_steps=1.0;" in body
        assert "config.lock_trigger_steps=2.0;" in body
        assert "config.pre_tighten_trail_distance_steps=2.0;" in body
        assert "config.tighten_trigger_steps=3.0;" in body
        assert "config.activation_uses_trailing_distance=true;" in body
        assert "config.cancel_before_close=true;" in body
        assert "config.close_interval_seconds=0;" in body
        assert "config.stop_update_interval_seconds=0;" in body
        assert "config.stop_updates_on_timer=false;" in body
        assert "config.max_stop_updates_per_pass=0;" in body
        assert "config.rearm_delay_seconds=0;" in body
        assert "config.restart_delay_ms=2000;" in body
        assert "config.deployment_fill_cooldown_seconds=0;" in body
        assert "config.stop_scan_newest_first=true;" in body
        assert "config.trend_rescue_enabled=false;" in body
        assert "return true;" in body


def test_standalone_sources_mirror_the_starwave_profile_catalog():
    """The all-in-one builds must carry the identical profile table."""
    catalog = PROFILE_CATALOG.read_text(encoding="utf-8")
    region = catalog.split("case STARWAVE_30:", 1)[1].split("case CUSTOM_PROFILE:", 1)[0]
    normalized = "\n".join(line.rstrip() for line in region.splitlines())

    types = (ROOT / "mql5" / "include" / "StraddleTypes.mqh").read_text(encoding="utf-8")
    enum = types.split("enum ENUM_STR_PROFILE", 1)[1].split("};", 1)[0]
    for name in ("STARWAVE_30_HIGH = 9", "STARWAVE_30_MID = 10", "STARWAVE_20_WIDE = 11", "STARWAVE_20_LIGHT = 12"):
        assert name in enum

    for standalone in ("ProfitBricks2K.mq5", "ProfitBricks2K_AllInOne.mq5"):
        text = (ROOT / "mql5" / standalone).read_text(encoding="utf-8")
        mirrored = text.split("case STARWAVE_30:", 1)[1].split("case CUSTOM_PROFILE:", 1)[0]
        mirrored = "\n".join(line.rstrip() for line in mirrored.splitlines())
        assert mirrored == normalized, f"{standalone} profile table drifted from the catalog"
        for name in ("STARWAVE_30_HIGH = 9", "STARWAVE_30_MID = 10", "STARWAVE_20_WIDE = 11", "STARWAVE_20_LIGHT = 12"):
            assert name in text
        assert "config.cycle_target_money=25.0;" not in text
        assert "config.cycle_target_money=15.0;" not in text


def test_june_2k_pins_the_pre_break_pacing_family_at_a_one_second_restart():
    """JUNE_2K is unpaced like Starwave but restarts on a 1 s floor, not 2 s.

    The implementation specification asks for restart_delay_ms = 2000 on
    STARWAVE_30, STARWAVE_20 *and* JUNE_2K.  The first two are measured that
    way; JUNE_2K is not.  JUNE_2K reproduces the pre-2026-07-24 regime, whose
    restart floor measures 1.17 s with 64/68 gaps under 4.5 s, while the
    Starwave window (2026-08-21..08-29) measures floor(next_deploy)-floor(flat)
    = 2 s on 96 cycles and 3 s on 6, i.e. 102/148 = 68.9%.

    The engine waits (restart_delay_ms+999)/1000 WHOLE seconds against a
    whole-second TimeCurrent(), so 1000 yields a 1 s floor and 2000 a 2 s
    floor.  Aligning JUNE_2K on 2000 would therefore contradict its own epoch.
    This test exists so that the split is machine-enforced rather than resting
    on the in-source comment: before it, JUNE_2K was pinned only by its enum
    membership.
    """
    carriers = {
        "ProfileCatalog.mqh": PROFILE_CATALOG.read_text(encoding="utf-8"),
        "ProfitBricks2K.mq5": (ROOT / "mql5" / "ProfitBricks2K.mq5").read_text(encoding="utf-8"),
        "ProfitBricks2K_AllInOne.mq5": (
            ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5"
        ).read_text(encoding="utf-8"),
    }

    for name, text in carriers.items():
        body = text.split("case JUNE_2K:", 1)[1].split("case LATEST_30:", 1)[0]

        # Geometry: same lattice law as every modern profile.
        assert "config.levels_per_side=30;" in body, name
        assert "config.step_mode=STR_STEP_ANCHOR_DIVISOR;" in body, name
        assert "config.anchor_divisor=3000.0;" in body, name

        # Unpaced burst execution, shared with the Starwave family.
        assert "config.close_interval_seconds=0;" in body, name
        assert "config.stop_update_interval_seconds=0;" in body, name
        assert "config.stop_updates_on_timer=false;" in body, name
        assert "config.max_stop_updates_per_pass=0;" in body, name
        assert "config.rearm_delay_seconds=0;" in body, name
        assert "config.deployment_fill_cooldown_seconds=0;" in body, name

        # The deliberate divergence, plus the citation that justifies it.
        assert "config.restart_delay_ms=1000;" in body, name
        assert "config.restart_delay_ms=2000;" not in body, name
        assert "deliberately NOT the 2000" in body, name
        assert "restart floor 1.17 s, 64/68 under 4.5 s" in body, name

        # The $2,000-capital lot ladder (spec 6.3).
        assert "SetLotTier(config,1,15,0.01);" in body, name
        assert "SetLotTier(config,16,25,0.03);" in body, name
        assert "SetLotTier(config,26,30,0.06);" in body, name

        # Two-stage ratchet identical to Starwave: activate +2, tighten at +3.
        assert "config.lock_trigger_steps=2.0;" in body, name
        assert "config.pre_tighten_trail_distance_steps=2.0;" in body, name
        assert "config.tighten_trigger_steps=3.0;" in body, name
        assert "config.trail_distance_steps=1.0;" in body, name
        assert "config.activation_uses_trailing_distance=true;" in body, name


def test_engine_pins_mid_anchor_tick_driven_stops_and_whole_second_restart():
    """The four engine-side clauses the profile table cannot express.

    * anchor = mid, normalized  (spec 1.1)
    * the deployment/pacing timer is inter_order_delay_ms, floored at 20 ms,
      which is what makes InterOrderDelayMs = 100 the ~112 ms observed cadence
      (spec 1.4)
    * stop_updates_on_timer = false routes the trailing ratchet through OnTick,
      and the interval / per-pass guards test > 0 so that the profile's zeros
      mean "every tick" and "unconstrained" rather than "never" (spec 3)
    * the restart wait is (restart_delay_ms+999)/1000 WHOLE seconds, the
      integer division that makes 1000 a 1 s floor and 2000 a 2 s floor
      (spec 5.2 step 3)

    Asserted on the modular engine and on both standalone builds, since the
    all-in-one files are generated copies of the includes
    (tools/bundle_standalone.py) and a stale generation would go unnoticed here
    without the assertion.
    """
    carriers = {
        "StraddleEngine.mqh": ENGINE.read_text(encoding="utf-8"),
        "ProfitBricks2K.mq5": (ROOT / "mql5" / "ProfitBricks2K.mq5").read_text(encoding="utf-8"),
        "ProfitBricks2K_AllInOne.mq5": (
            ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5"
        ).read_text(encoding="utf-8"),
    }

    for name, text in carriers.items():
        assert "m_anchor=NormalizePrice((tick.bid+tick.ask)/2.0);" in text, name
        assert "int timer_ms=MathMax(20,m_runtime.inter_order_delay_ms);" in text, name
        assert "if(!EventSetMillisecondTimer(timer_ms))" in text, name
        assert "if(!m_profile.stop_updates_on_timer)" in text, name
        assert "if(m_profile.stop_update_interval_seconds>0 &&" in text, name
        assert "if(m_profile.max_stop_updates_per_pass>0 &&" in text, name
        assert "(m_profile.restart_delay_ms+999)/1000)" in text, name


# ---------------------------------------------------------------------------
# replica_orphan_leak: the Target EA's single-pointer level table
#
# The Target's SLevelState holds ONE position ticket per (side,level).  A re-fill
# overwrites the pointer and the displaced position is never tracked again: not
# trailed, not counted in the basket, never closed by the sweep.  Measured on the
# Starwave tape (audit D6/D7): 153 of 2,468 fills (6.20%) were still open at the
# end of the window, 0/153 ever received an [sl] order, 0/146 sweeps left the
# book flat, and 137/137 same-level overlapping pairs have the EARLIER position
# never closed.  These tests pin the reproduction of that behaviour, because it
# is the single largest behavioural divergence that was found between the two
# EAs and the easiest one to "fix" back out by accident.
# ---------------------------------------------------------------------------

# Every built-in profile that reconstructs the real Target binary, and every one
# that does not.  The leak is a property of the BINARY, not of the pacing epoch,
# so it spans both the June-2026 and the August-2026 regimes.
LEAK_PROFILES = (
    "JUNE_2K",
    "LATEST_30",
    "STARWAVE_30",
    "STARWAVE_20",
    "STARWAVE_30_HIGH",
    "STARWAVE_30_MID",
    "STARWAVE_20_WIDE",
    "STARWAVE_20_LIGHT",
)
NO_LEAK_PROFILES = ("HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30")


def profile_case_bodies(text: str) -> dict[str, str]:
    """Split LoadProfileConfig's switch into {profile name: case body}."""
    switch = text.split("bool LoadProfileConfig(", 1)[1]
    labels = [name for name in LEAK_PROFILES + NO_LEAK_PROFILES] + ["CUSTOM_PROFILE"]
    positions = sorted(
        (switch.index(f"case {name}:"), name)
        for name in labels
        if f"case {name}:" in switch
    )
    bodies = {}
    for index, (start, name) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(switch)
        bodies[name] = switch[start:end]
    return bodies


def function_body(text: str, signature: str) -> str:
    """The braced body that follows `signature`, found by brace counting.

    Splitting on a fixed indented "\\n  }" is not safe in these sources: the
    modular includes use 3-space class members with 5-space bodies while the
    standalone concatenation preserves that, and several bodies contain nested
    blocks at the same indentation.  Counting braces is indentation-agnostic.
    """
    assert signature in text, f"missing signature: {signature}"
    cursor = text.index(signature) + len(signature)
    start = text.index("{", cursor)
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated body for: {signature}")


def test_types_declare_the_orphan_leak_flag_on_both_profile_structs():
    """SProfileConfig and SCustomProfileConfig both carry the flag.

    SCustomProfileConfig is what CUSTOM_PROFILE fills from the EA inputs, so
    without the second declaration the only off-switch would not exist.
    """
    types = TYPES.read_text(encoding="utf-8")
    assert types.count("bool              replica_orphan_leak;") == 2, types.count(
        "bool              replica_orphan_leak;"
    )

    profile_struct = types.split("struct SProfileConfig", 1)[1].split("};", 1)[0]
    custom_struct = types.split("struct SCustomProfileConfig", 1)[1].split("};", 1)[0]
    assert "bool              replica_orphan_leak;" in profile_struct
    assert "bool              replica_orphan_leak;" in custom_struct

    # The evidence lives next to the declaration so the flag cannot be mistaken
    # for a tidy-up knob and switched off as "obviously a bug".
    assert "153 of 2,468" in profile_struct
    assert "0/146 sweeps left the book flat" in profile_struct
    assert "not closed by the sweep" in profile_struct

    # And the cross-validation that makes it a BUILD switch instead of a
    # measurement artifact: one instrument, one overlap rule, run on both tapes.
    # 901018 gates re-arm on !has_position in every era it ran, including its own
    # STARWAVE_30 era; the August Starwave build does not.
    assert "0 of 11,549" in profile_struct
    assert "118 of 1,075" in profile_struct
    assert "0/2,233" in profile_struct
    assert "ORDER_REASON_EXPERT" in profile_struct

    # The leak IS the single-pointer level table, so the level struct must keep
    # one ticket, not a list.
    level_struct = types.split("struct SLevelState", 1)[1].split("};", 1)[0]
    assert "ulong             position_ticket;" in level_struct
    assert "bool              has_position;" in level_struct
    assert "position_tickets[" not in level_struct


def test_profile_catalog_pins_the_orphan_leak_per_profile():
    """False by default, true on every Target reconstruction, false on legacy."""
    catalog = PROFILE_CATALOG.read_text(encoding="utf-8")

    # ResetProfile is the baseline every case starts from: hygienic, so a new
    # profile has to opt in to the leak explicitly.
    reset_body = function_body(catalog, "void ResetProfile(")
    assert "config.replica_orphan_leak=false;" in reset_body

    bodies = profile_case_bodies(catalog)
    for name in LEAK_PROFILES:
        assert name in bodies, name
        assert "config.replica_orphan_leak=true;" in bodies[name], name
    for name in NO_LEAK_PROFILES:
        assert name in bodies, name
        # Legacy/experimental profiles are not reconstructions of the Target
        # binary, so they inherit ResetProfile's hygienic false.
        assert "replica_orphan_leak" not in bodies[name], name

    # CUSTOM_PROFILE is routed through LoadCustomProfile, which is the one and
    # only place the flag can be turned off from the EA inputs.
    custom_body = catalog.split("bool LoadCustomProfile(", 1)[1]
    assert "config.replica_orphan_leak=custom.replica_orphan_leak;" in custom_body
    assert "only escape hatch" in custom_body


def test_app_exposes_the_orphan_leak_input_and_wires_it():
    source = app_source()
    assert "input bool CustomReplicaOrphanLeak = true;" in source
    assert "custom.replica_orphan_leak=CustomReplicaOrphanLeak;" in source
    # Default ON matches the Starwave binary; the comment records why, and that
    # turning it off is a deliberate DEVIATION rather than a bug fix.
    assert "DEVIATION from the Target" in source


def value_after(text: str, prefix: str) -> str:
    """The literal between `prefix` and the next `;`.

    Used to compare a declared default against the catalogue value it is
    supposed to mirror, rather than asserting one spelling of one number in two
    places and hoping both get edited together.
    """
    assert prefix in text, f"missing prefix: {prefix}"
    return text.split(prefix, 1)[1].split(";", 1)[0].strip()


def test_custom_basket_target_default_matches_the_starwave_catalogue():
    """CustomCycleTargetMoney must equal STARWAVE_30's measured basket target.

    cycle_target_money is the EA's ONLY exit (CheckCycleTargets), and the Custom
    block is documented as "the measured Starwave/Target values, so
    CUSTOM_PROFILE is a Starwave clone out of the box".  It nevertheless shipped
    25.0 while the catalogue brackets the measured target to (26.41, 26.51] from
    the 3-cycle censored run over 2026-08-24 19:22..19:49 -- an interval that
    EXCLUDES 25.0, i.e. a 5.66% early bank on every single basket.  It was the
    last surviving placeholder in that block.  This test ties the input default
    to the catalogue value so the two can never drift apart again.
    """
    app = app_source()
    catalog = PROFILE_CATALOG.read_text(encoding="utf-8")

    app_default = float(value_after(app, "input double CustomCycleTargetMoney = "))
    starwave = float(
        value_after(
            profile_case_bodies(catalog)["STARWAVE_30"], "config.cycle_target_money="
        )
    )
    assert app_default == starwave, (app_default, starwave)

    # The measured bracket itself, half-open on the low side.
    assert 26.41 < app_default <= 26.51, app_default
    assert app_default != 25.0, "the pre-Starwave placeholder is back"

    # The plumbing that makes the default reach the evaluator at all:
    # input -> SCustomProfileConfig -> SProfileConfig -> CheckCycleTargets.
    assert "custom.cycle_target_money=CustomCycleTargetMoney;" in app
    custom_body = catalog.split("bool LoadCustomProfile(", 1)[1]
    assert "config.cycle_target_money=custom.cycle_target_money;" in custom_body
    assert "m_profile.cycle_target_money>0.0" in ENGINE.read_text(encoding="utf-8")

    # Provenance sits next to the default so it cannot be "tidied" back to a
    # round number by someone who reads 26.5 as an oddity.
    assert "(26.41, 26.51]" in app

    # Anti-drift: both generated standalones must carry the corrected default.
    for name in ("ProfitBricks2K.mq5", "ProfitBricks2K_AllInOne.mq5"):
        text = (ROOT / "mql5" / name).read_text(encoding="utf-8")
        assert "input double CustomCycleTargetMoney = 26.5;" in text, name
        assert "input double CustomCycleTargetMoney = 25.0;" not in text, name


def test_engine_reproduces_the_target_orphan_leak():
    """The eight engine mechanisms that make a displaced position vanish.

    Dropping the re-arm gate alone is INERT: ReconcileLevels() rebuilds
    has_position from the live book on every pass, so a displaced position would
    be re-adopted on the very next reconcile and then trailed and swept.  The
    leak therefore needs a persistent orphan set plus a newest-per-level rule
    inside the reconcile itself, and it needs the sweep, the trail and the basket
    to be scoped to the tracked set.  All of it is asserted on the modular engine
    and on both generated standalones.
    """
    carriers = {
        "StraddleEngine.mqh": ENGINE.read_text(encoding="utf-8"),
        "ProfitBricks2K.mq5": (ROOT / "mql5" / "ProfitBricks2K.mq5").read_text(encoding="utf-8"),
        "ProfitBricks2K_AllInOne.mq5": (
            ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5"
        ).read_text(encoding="utf-8"),
    }

    for name, text in carriers.items():
        # (1) The orphan set is engine state, not level state, so it outlives
        # every cycle boundary -- a displaced position stays untracked for good.
        assert "ulong             m_orphan_tickets[];" in text, name
        assert "int               m_orphan_count;" in text, name
        assert "bool OrphanLeakActive(void) const" in text, name
        assert "return(m_profile.replica_orphan_leak);" in text, name

        # (2) Newest-per-level inside the reconcile: the higher ticket wins and
        # the loser is orphaned, which is what a single-pointer overwrite does.
        assert "if(OrphanLeakActive() && IsOrphanTicket(ticket))" in text, name
        assert "void AdoptPositionIntoLevel(" in text, name
        assert "bool incoming_is_newer=(ticket>level_state.position_ticket);" in text, name
        assert "PruneClosedOrphanTickets();" in text, name

        # (3) A live position no longer blocks a fresh pending on its level --
        # this is the mechanism that creates orphans in the first place.
        assert "(!OrphanLeakActive() && level_state.has_position)" in text, name

        # (4) Re-arm any level with no pending, subject only to
        # PendingPriceIsValid()/RearmDelayElapsed(); no !has_position gate.
        assert "bool RearmEligible(const SLevelState &level_state) const" in text, name
        assert "return(level_state.rearm_requested && !level_state.has_position);" in text, name

        # (5) The sweep closes only tracked positions, in exact reverse-of-ticket
        # LIFO (measured 3718/3718).
        assert "return TryCloseOneTrackedPosition();" in text, name
        assert "bool TryCloseOneTrackedPosition(void)" in text, name

        # (6) Orphans are never trailed: 0/153 ever received an [sl] order.
        assert "void UpdateTrackedPositionStops(const MqlTick &tick)" in text, name
        assert "bool TrailSelectedPosition(const MqlTick &tick,const ulong ticket)" in text, name
        assert "UpdateTrackedPositionStops(tick);" in text, name

        # (7) The basket sums only tracked positions, and the open-position gate
        # counts only tracked ones.
        assert "double floating=CycleFloatingProfit();" in text, name
        assert "int open_pos_count=CyclePositionCount();" in text, name
        assert "int CyclePositionCount(void) const" in text, name
        assert "double CycleFloatingProfit(void) const" in text, name

        # (8) One pending + one position on the same level is the normal steady
        # state under the leak, so duplicate-identity must score the two entity
        # kinds independently instead of summing them.
        assert "entity_count=MathMax(" in text, name

        # Two accounting families, not one repointed function: safety and the
        # flat-book guards stay book-wide on purpose (counting orphans is the
        # conservative choice there).
        assert "int OwnedPositionCount(void) const" in text, name
        assert "double OwnedFloatingProfit(void) const" in text, name

        # A cycle boundary must not silently release a tracked ticket back into
        # the tracked set: both start paths orphan whatever is still pointed at.
        assert text.count("OrphanRemainingTrackedPositions();") == 2, name
        # Reset in the constructor and in Initialize() only -- NOT in
        # ResetLevelState(), which runs at every cycle start.
        assert text.count("ResetOrphanTickets();") == 2, name
        reset_level_state = function_body(text, "void ResetLevelState(void)")
        assert "ResetOrphanTickets" not in reset_level_state, name

        # Selection safety: RememberOrphanTicket() writes telemetry, and
        # WriteTelemetry() calls CycleFloatingProfit(), which walks the book with
        # PositionSelectByTicket().  Every property of the selected position must
        # therefore be read BEFORE it, or the level records another position's
        # volume.  This ordering was a real bug once; keep it pinned.
        adopt = function_body(text, "void AdoptPositionIntoLevel(")
        volume_read = adopt.index("double volume=PositionGetDouble(POSITION_VOLUME);")
        orphan_call = adopt.index("RememberOrphanTicket(displaced,LevelCommentOf(level_state));")
        assert volume_read < orphan_call, name
        # ...and it must be read exactly once, so neither branch re-reads it from
        # whatever position the telemetry write left selected.
        assert adopt.count("PositionGetDouble(POSITION_VOLUME)") == 1, name
        assert adopt.count("level_state.volume=volume;") == 2, name


# ---------------------------------------------------------------------------
# Standalone generation: the all-in-one builds are OUTPUT, never edited by hand
#
# mql5/ProfitBricks2K.mq5 and mql5/ProfitBricks2K_AllInOne.mq5 are mechanical
# concatenations of the eight includes.  They were hand-mirrored for a long time
# and had silently drifted 33 lines behind mql5/include (12 in StraddleTypes.mqh,
# 21 in ProfileCatalog.mqh) -- which means both standalones were shipping WITHOUT
# the replica_orphan_leak field and WITHOUT the eight profile assignments that
# turn the Target's orphan leak on.  They compiled with zero errors and were
# silently a different EA.  Nothing in the suite would have caught it: every other
# assertion here reads the modular includes.
#
# tools/bundle_standalone.py is now the only writer, and this test is the thing
# that makes forgetting to run it a red suite instead of a shipped divergence.
# ---------------------------------------------------------------------------


def test_standalone_builds_are_current_generated_copies_of_the_includes():
    from tools import bundle_standalone

    expected = bundle_standalone.build_from_worktree()
    for target in bundle_standalone.TARGETS:
        actual = target.read_text(encoding="utf-8")
        assert actual == expected, (
            f"{target.name} is stale: regenerate with "
            f"`python tools/bundle_standalone.py --write`.\n"
            f"{bundle_standalone.first_divergence(expected, actual)}"
        )

    # Both binaries differ only by their compile-time #define pins, and those live
    # in the header block the bundler copies verbatim -- so as generated from the
    # same header they are byte-identical.  If they ever legitimately diverge, the
    # bundler needs a per-target header, not a hand edit.
    assert len({target.read_bytes() for target in bundle_standalone.TARGETS}) == 1

    # Every include must be represented, and no live #include may survive the
    # inlining (an unresolved one would make the "standalone" build fail to
    # compile outside mql5/include).
    for filename, label in bundle_standalone.SECTIONS:
        assert f"// SECTION: {label}" in expected, filename
    assert '\n#include "' not in expected
    assert expected.count(bundle_standalone.PLACEHOLDER) >= len(
        bundle_standalone.SECTIONS
    ) - 1

    # The header still carries this pair's parity pins.  ProfitBricks2K is the
    # JUNE_2K/901018 build; changing either is a behavioural change, not a
    # packaging one.
    header = "\n".join(bundle_standalone.header_of(expected))
    assert "#define STR_DEFAULT_PROFILE JUNE_2K" in header
    assert "#define STR_DEFAULT_MAGIC 901018" in header
    assert "#property" in header


def test_standalone_generator_round_trips_the_committed_tree():
    """The transform is reversible against git HEAD, so it cannot be self-serving.

    build_from_worktree() reads the header out of the file it is about to
    overwrite, so a bundler bug plus a matching bad file would agree with each
    other.  --verify closes that loop by rebuilding HEAD's committed standalone
    from HEAD's committed includes and demanding byte equality.
    """
    import subprocess

    from tools import bundle_standalone

    def show(rev_path: str) -> str:
        return subprocess.run(
            ["git", "show", rev_path],
            cwd=bundle_standalone.ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")

    head = show("HEAD:mql5/ProfitBricks2K.mq5")
    sources = {
        name: show(f"HEAD:mql5/include/{name}")
        for name, _ in bundle_standalone.SECTIONS
    }
    rebuilt = bundle_standalone.bundle(bundle_standalone.header_of(head), sources)
    assert rebuilt == head, bundle_standalone.first_divergence(head, rebuilt)


def test_basket_close_comment_is_per_profile_and_empty_for_the_atr_builds():
    """DIV-3: the sweep comment is a build fingerprint, so it must be per-profile.

    ReportHistory-901018 spans two Target builds and they stamp the basket sweep
    differently.  Inside the two ATR eras every basket close carries an EMPTY
    comment -- 1,392 in HISTORICAL_50 (2026.06.23 16:17 - 2026.07.02 15:18) and
    1,332 in HISTORICAL_60 (to the 2026.07.13 12:28 changeover) -- and not one
    carries "STR CLOSE".  Every one of the 1,010 "STR CLOSE" closes falls in the
    anchor-divisor eras instead (AGGRESSIVE_30 9, LOW_RISK_30 11, STARWAVE_30
    990).  The two families are one mechanism: 2732/2732 and 1010/1010 of the
    orders resolve to DEAL_ENTRY_OUT deals, and both run the same ~105 ms machine
    cadence as the pending lattice (p50 105 ms and 111 ms against 103 ms).
    """
    types = TYPES.read_text(encoding="utf-8")
    assert types.count("bool              stamp_close_comment;") == 1

    catalog = PROFILE_CATALOG.read_text(encoding="utf-8")
    reset = function_body(catalog, "void ResetProfile(SProfileConfig &config)")
    assert "config.stamp_close_comment=true;" in reset

    bodies = profile_case_bodies(catalog)
    empty_comment = {
        name
        for name, body in bodies.items()
        if "config.stamp_close_comment=false;" in body
    }
    assert empty_comment == {"HISTORICAL_50", "HISTORICAL_60"}, sorted(empty_comment)
    for name in LEAK_PROFILES + ("AGGRESSIVE_30", "LOW_RISK_30", "CUSTOM_PROFILE"):
        assert "stamp_close_comment" not in bodies[name], name

    # LoadCustomProfile has no operator input for this: it calls ResetProfile
    # first, so CUSTOM_PROFILE inherits the live "STR CLOSE" behaviour.
    custom = function_body(
        catalog, "bool LoadCustomProfile(const SCustomProfileConfig &custom,SProfileConfig &config)"
    )
    assert "ResetProfile(config);" in custom
    assert "stamp_close_comment" not in custom


def test_both_close_sites_route_through_the_profile_close_comment():
    """Neither sweep path may hard-code the literal.

    TryCloseOneTrackedPosition is the leak-mode sweep and TryCloseOneOwnedPosition
    the book-wide one; a literal left in either would silently stamp "STR CLOSE"
    on a HISTORICAL_50/HISTORICAL_60 run and diverge from the tape.
    """
    for path in (
        ENGINE,
        ROOT / "mql5" / "ProfitBricks2K.mq5",
        ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5",
    ):
        text = path.read_text(encoding="utf-8")
        assert 'ClosePosition(ticket,"STR CLOSE")' not in text, path.name
        assert text.count("ClosePosition(ticket,CloseComment())") == 2, path.name
        helper = function_body(text, "string CloseComment(void) const")
        assert 'return(m_profile.stamp_close_comment ? "STR CLOSE" : "");' in helper

        for signature in (
            "bool TryCloseOneTrackedPosition(void)",
            "bool TryCloseOneOwnedPosition(void)",
        ):
            body = function_body(text, signature)
            assert "ClosePosition(ticket,CloseComment())" in body, (path.name, signature)
            assert '"STR CLOSE"' not in body, (path.name, signature)


def div4_carriers() -> dict[str, str]:
    """The three files that must agree on the activation law."""
    return {
        "ProfileCatalog.mqh": PROFILE_CATALOG.read_text(encoding="utf-8"),
        "ProfitBricks2K.mq5": (ROOT / "mql5" / "ProfitBricks2K.mq5").read_text(
            encoding="utf-8"
        ),
        "ProfitBricks2K_AllInOne.mq5": (
            ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5"
        ).read_text(encoding="utf-8"),
    }


def test_activation_law_is_the_trailing_distance_on_every_built_in_profile():
    """DIV-4: the first stop is market -/+ pre_tighten*step, never entry +/- 0.20.

    StopScheduler.Calculate activates once favorable_steps >= lock_trigger_steps
    and then picks between two mutually exclusive laws.  The false branch writes
    entry + dir*lock_offset_price = entry +/- 0.20 FIRST, and the monotonic
    returns at the end of Calculate only ever improve a stop, so under it
    dir*(sl-open) can never be smaller than 0.20 and 0.20 must be a razor atom.
    ReportHistory-901018 falsifies both claims in the two eras that used to
    inherit the false branch, scored with each cycle's own step over every
    position carrying an S/L: 351 of HISTORICAL_50's 4,094 (8.57%) and 1,068 of
    HISTORICAL_60's 7,952 (13.43%) land strictly inside (0,0.20), both with a
    minimum of +0.01, zero negatives, and no atom at 0.20 (0.19/0.20/0.21 =
    22/18/17 and 47/57/55, against busiest single cents of 26 and 78).

    So the flag is true on all twelve built-in profiles AND on ResetProfile's
    default, which leaves lock_offset_price reachable only through
    CUSTOM_PROFILE.  Asserted on the modular catalog and both standalone builds,
    since a stale generation would otherwise keep shipping the falsified branch.
    """
    built_in = LEAK_PROFILES + NO_LEAK_PROFILES
    assert len(built_in) == 12, built_in

    for name, text in div4_carriers().items():
        assert "config.activation_uses_trailing_distance=false;" not in text, name

        reset = function_body(text, "void ResetProfile(SProfileConfig &config)")
        assert "config.activation_uses_trailing_distance=true;" in reset, name

        bodies = profile_case_bodies(text)
        for profile in built_in:
            assert (
                "config.activation_uses_trailing_distance=true;" in bodies[profile]
            ), (name, profile)
            # lock_offset_price is dead on every built-in path: no case body
            # touches it, so only ResetProfile's 0.2 and LoadCustomProfile's
            # operator copy remain.  (CUSTOM_PROFILE is the last case, so its
            # slice absorbs LoadCustomProfile -- excluded from this loop.)
            assert "lock_offset_price=" not in bodies[profile], (name, profile)

        custom = function_body(
            text,
            "bool LoadCustomProfile(const SCustomProfileConfig "
            "&custom,SProfileConfig &config)",
        )
        assert (
            "config.activation_uses_trailing_distance="
            "custom.activation_uses_trailing_distance" in custom
        ), name
        assert "config.lock_offset_price=custom.lock_offset_price;" in custom, name


def test_atr_profiles_keep_the_single_stage_trail_collapse():
    """HISTORICAL_50/HISTORICAL_60 must NOT gain trail_distance_steps=1.0.

    Those two set no trail distance at all, so they inherit ResetProfile's 2.0,
    which equals pre_tighten_trail_distance_steps.  Calculate's tighten ternary
    then picks the same distance on both sides of tighten_trigger_steps and the
    two-stage ratchet collapses into a single-stage 2.0-step trail.  That is what
    the tape shows: the locked distance dir*(sl-open)/step fills the band [1,2)
    smoothly -- 951/4094 = 23.23% and 1832/7952 = 23.04%, neighbour-density
    ratios 0.883 and 0.920 -- where STARWAVE_30 puts 0 of 2,809 in [1.00,1.98)
    (its eight apparent members all sit at locked 1.985-2.000, one cent of
    step-inference error under the Stage-2 boundary).  Copying the modern
    profiles' 1.0 into these two would carve a trough that is not in the data,
    so the omission is load-bearing and pinned here with its own evidence.
    """
    for name, text in div4_carriers().items():
        reset = function_body(text, "void ResetProfile(SProfileConfig &config)")
        assert "config.pre_tighten_trail_distance_steps=2.0;" in reset, name
        assert "config.trail_distance_steps=2.0;" in reset, name

        bodies = profile_case_bodies(text)
        for profile in ("HISTORICAL_50", "HISTORICAL_60"):
            body = bodies[profile]
            assert "config.trail_distance_steps=" not in body, (name, profile)
            assert "config.pre_tighten_trail_distance_steps=" not in body, (
                name,
                profile,
            )
            assert "config.tighten_trigger_steps=" not in body, (name, profile)
        for profile in LEAK_PROFILES + ("AGGRESSIVE_30", "LOW_RISK_30"):
            assert "config.trail_distance_steps=1.0;" in bodies[profile], (
                name,
                profile,
            )

        # The measurement, and the instruction not to "fix" it, stay in source.
        assert "23.23%" in bodies["HISTORICAL_50"], name
        assert "Do not copy trail_distance_steps=1.0 here" in bodies["HISTORICAL_50"], (
            name
        )
        assert "23.04%, neighbour-density ratio 0.920" in bodies["HISTORICAL_60"], name
        assert "351  (8.57%)" in bodies["HISTORICAL_50"], name
        assert "1,068 (13.43%)" in bodies["HISTORICAL_60"], name
        # AGGRESSIVE_30/LOW_RISK_30 carry the flag by parsimony (n=29 each).  The
        # nine impossible negatives in AGGRESSIVE_30 used to be recorded as an
        # open anomaly ("flagged not legislated", suspected step/anchor
        # attribution error).  They are now RESOLVED as operator-authored writes
        # on five independent discriminants, so the comment must state the
        # resolution -- and must NOT re-suggest an attribution error, which would
        # invite someone to "fix" the step inference that is in fact correct.
        assert "by parsimony, not by direct measurement" in bodies["AGGRESSIVE_30"], name
        assert "Resolved, no longer open" in bodies["AGGRESSIVE_30"], name
        assert "OPERATOR-" in bodies["AGGRESSIVE_30"], name
        assert "not an attribution error" in bodies["AGGRESSIVE_30"], name
        assert "flagged not legislated" not in bodies["AGGRESSIVE_30"], name
        assert "by parsimony, as AGGRESSIVE_30 above" in bodies["LOW_RISK_30"], name


def test_stop_scheduler_keeps_the_fixed_offset_branch_as_an_operator_escape_hatch():
    """The falsified branch stays reachable through CUSTOM_PROFILE only.

    DIV-4 kills the false branch on every built-in profile, but the operator
    input still exists, so Calculate must keep both arms of the ternary and the
    app must keep defaulting the input to the measured law.
    """
    scheduler = (ROOT / "mql5" / "include" / "StopScheduler.mqh").read_text(
        encoding="utf-8"
    )
    for text in (scheduler,) + tuple(
        body
        for name, body in div4_carriers().items()
        if name != "ProfileCatalog.mqh"
    ):
        assert "profile.activation_uses_trailing_distance" in text
        assert "profile.pre_tighten_trail_distance_steps*step" in text
        assert "entry+direction*profile.lock_offset_price" in text

    app = app_source()
    assert "input bool CustomActivationUsesTrailingDistance = true;" in app
    assert (
        "custom.activation_uses_trailing_distance=CustomActivationUsesTrailingDistance;"
        in app
    )


# ---------------------------------------------------------------------------
# DIV-6: liquidation phase order.
#
# BeginClose picks the order with one ternary: cancel_before_close true routes
# CANCELING -> CLOSING -> RESTARTING, false routes CLOSING -> CANCELING ->
# RESTARTING.  Four legacy profiles inherited ResetProfile's false, which is
# refuted by ReportHistory-901018: over its 271 terminal liquidations 259 are
# strictly cancel-first and exactly one is close-first, and that one is a hand
# flatten.  These tests pin the repaired setting together with its measurement,
# because the field is one boolean per case and a silent revert is invisible.
# ---------------------------------------------------------------------------

# The order is now universal across every built-in profile, so the DIV-6 set is
# the whole catalog rather than a partition like LEAK_PROFILES.  Named separately
# so that adding a profile without the field fails here rather than at runtime.
CANCEL_FIRST_PROFILES = LEAK_PROFILES + NO_LEAK_PROFILES


def test_every_built_in_profile_liquidates_cancel_first():
    """DIV-6: all twelve cases set cancel_before_close, on all three carriers.

    Measured on ReportHistory-901018 by ordering each cycle's terminal cancels
    and closes on (time, order id) and reading which class comes first:

        era              liquidations  cancel-first  close-first  interleaved
        HISTORICAL_50              95            95            0            0
        HISTORICAL_60              72            71            1            0
        AGGRESSIVE_30               2             1            0            1
        LOW_RISK_30                 1             1            0            0
        STARWAVE_30               101            91            0           10

    The single close-first cycle (169) and the single interleaved one (171) are
    hand flattens, identified independently of any timing by the 12 `close by`
    (PositionCloseBy) orders -- an API with no call site in this EA.  On the
    operator-free complement the four eras that inherited false are 168/168.
    """
    for name, text in div4_carriers().items():
        reset = function_body(text, "void ResetProfile(SProfileConfig &config)")
        assert "config.cancel_before_close=false;" in reset, name

        bodies = profile_case_bodies(text)
        assert len(CANCEL_FIRST_PROFILES) == 12, CANCEL_FIRST_PROFILES
        for profile in CANCEL_FIRST_PROFILES:
            assert profile in bodies, (name, profile)
            assert "config.cancel_before_close=true;" in bodies[profile], (
                name,
                profile,
            )
            # Nothing may set it back to false on a built-in path.  (CUSTOM_PROFILE
            # is the last case, so its slice absorbs LoadCustomProfile and is
            # excluded from this loop -- that body legitimately copies the input.)
            assert "config.cancel_before_close=false;" not in bodies[profile], (
                name,
                profile,
            )

        custom = function_body(
            text,
            "bool LoadCustomProfile(const SCustomProfileConfig "
            "&custom,SProfileConfig &config)",
        )
        assert "config.cancel_before_close=custom.cancel_before_close;" in custom, name


def test_div6_repaired_profiles_carry_their_measurement_in_source():
    """The four repaired cases must keep the census that forced the change.

    Each of the four is a different strength of evidence and the comments say so
    rather than all claiming the same thing: HISTORICAL_50 is 95/95 direct,
    HISTORICAL_60 is 71/71 direct plus the handoff quantisation, and
    AGGRESSIVE_30 / LOW_RISK_30 are n=1 apiece and inherit the order from their
    neighbours by the same parsimony argument DIV-4 uses.  A future reader who
    only sees `=true;` has no way to tell a measurement from a guess.
    """
    for name, text in div4_carriers().items():
        bodies = profile_case_bodies(text)

        h50 = bodies["HISTORICAL_50"]
        assert "liquidation phase order, measured (DIV-6)" in h50, name
        assert "259 of 271 cycles are strictly cancel-first" in h50, name
        assert "close by" in h50, name
        assert "PositionCloseBy has" in h50, name
        assert "168/168 =" in h50, name
        # The cross-boundary attribution check, which is what stops the census
        # being explained away as cancels bleeding into the next cycle.
        assert "106 of 19,312 cancels (0.55%)" in h50, name

        h60 = bodies["HISTORICAL_60"]
        assert "DIV-6, the largest single-era cohort" in h60, name
        assert "72 terminal liquidations, 71" in h60, name
        assert "strictly cancel-first and 1 close-first" in h60, name
        assert "this era is 71/71" in h60, name
        # The handoff is one OnTimer period because CancelOneOrder assigns
        # CYCLE_CLOSING and RETURNS instead of closing in the same tick.
        assert "min 97 ms" in h60, name
        assert "243/256 = 94.92% inside [95,135) ms" in h60, name

        aggressive = bodies["AGGRESSIVE_30"]
        assert "DIV-6, by the same probe and by the same parsimony argument" in aggressive, name
        assert "cycle 170" in aggressive, name
        assert "cycle 171" in aggressive, name
        assert "95/95" in aggressive and "71/71" in aggressive, name

        low_risk = bodies["LOW_RISK_30"]
        assert "DIV-6: this era's single terminal liquidation is cancel-first" in low_risk, name
        assert "1/1" in low_risk, name

        # DIV-4 and DIV-6 sit next to each other in all four bodies; neither
        # rewrite may swallow the other's comment.
        for profile in ("HISTORICAL_50", "HISTORICAL_60", "AGGRESSIVE_30", "LOW_RISK_30"):
            assert "DIV-4" in bodies[profile], (name, profile)
            assert "DIV-6" in bodies[profile], (name, profile)


def test_engine_implements_both_liquidation_orders_and_converges_on_restart():
    """No engine change was needed for DIV-6, and this is why.

    BeginClose already branches on the flag, and each phase handler already hands
    off to the other phase when the flag says so, so the two orders are
    symmetric and both terminate in CYCLE_RESTARTING:

        true   BeginClose -> CANCELING -> (drained) -> CLOSING -> RESTARTING
        false  BeginClose -> CLOSING   -> (flat)    -> CANCELING -> RESTARTING

    Two properties are pinned beyond the branch itself.  CancelOneOrder assigns
    CYCLE_CLOSING and RETURNS rather than closing in the same tick, which is what
    makes the measured cancel->close handoff exactly one OnTimer period (min
    97 ms, 243/256 in [95,135) ms).  And a HALT deliberately ignores the flag:
    BeginClose(halt_after=true) goes straight to CYCLE_CLOSING and the CANCELING
    phase runs afterwards, so an aborted cycle still leaves no live pendings.
    """
    engine = ENGINE.read_text(encoding="utf-8")
    for text in (engine, *(t for n, t in div4_carriers().items() if n != "ProfileCatalog.mqh")):
        begin = function_body(text, "void BeginClose(const string reason,const bool halt_after)")
        assert "ENUM_CYCLE_STATE replica_close_state=" in begin
        assert "(m_profile.cancel_before_close ? CYCLE_CANCELING : CYCLE_CLOSING)" in begin
        assert "m_state=(halt_after ? CYCLE_CLOSING : replica_close_state);" in begin

        close_phase = function_body(text, "void CloseOnePosition(void)")
        assert "if(!m_halted && m_profile.cancel_before_close)" in close_phase
        assert "m_state=CYCLE_RESTARTING;" in close_phase
        assert "m_state=CYCLE_CANCELING;" in close_phase

        cancel_phase = function_body(text, "void CancelOneOrder(void)")
        assert "m_profile.cancel_before_close &&" in cancel_phase
        assert "CyclePositionCount()>0" in cancel_phase
        assert "m_state=CYCLE_CLOSING;" in cancel_phase
        # The handoff returns instead of falling through into a close.
        assert "PersistCycle();\n         return;" in cancel_phase
        assert "m_state=CYCLE_RESTARTING;" in cancel_phase
        assert "m_state=CYCLE_HALTED;" in cancel_phase

        # Which order is live is published, so a tape can be attributed later.
        assert 'FileWrite(handle,"profile_cancel_before_close"' in text
        assert "(int)m_profile.cancel_before_close);" in text

