#ifndef STR_REQUIRE_DEMO_DEFAULT
   #define STR_REQUIRE_DEMO_DEFAULT true
#endif
#ifndef STR_REQUIRE_BOUND_DEFAULT
   #define STR_REQUIRE_BOUND_DEFAULT false
#endif
#ifndef STR_SAFETY_ENABLED_DEFAULT
   #define STR_SAFETY_ENABLED_DEFAULT false
#endif
#ifndef STR_DEFAULT_PROFILE
   #define STR_DEFAULT_PROFILE STARWAVE_30
#endif
// Magic and profile are both macro-driven so a single-purpose binary can pin
// them with a #define ahead of this include (see ProfitBricks2K.mq5, which
// pins JUNE_2K).  Before this indirection the input initialisers hard-coded
// LATEST_30 / 901018 and the STR_DEFAULT_PROFILE macro was inert: every
// binary silently defaulted to LATEST_30 no matter what it defined.
//
// The shipped defaults reproduce the Starwave / Target account:
//   Profile     = STARWAVE_30  (N=30/side, step=round(anchor/3000,2),
//                               lots 0.01@1-10 / 0.06@11-20 / 0.15@21-30,
//                               ratchet L=2 Dpre=2 Tt=3 D=1, cancel-then-close,
//                               cycle_target_money=25, restart_delay_ms=2000)
//   MagicNumber = 26011001     measured on all 10,844 EA-authored rows of
//                              Starwave_60542_orders_history.csv; the other 19
//                              rows are magic 0 manual operator closes.
#ifndef STR_DEFAULT_MAGIC
   #define STR_DEFAULT_MAGIC 26011001
#endif

#include "StraddleTypes.mqh"
#include "StraddleEngine.mqh"

input group "Replica"
input ENUM_STR_PROFILE Profile = STR_DEFAULT_PROFILE;
input string TradeSymbol = "";
input ulong MagicNumber = STR_DEFAULT_MAGIC;
input bool ReplicaMode = true;
input datetime ReplicaStartTime = 0;
input int InterOrderDelayMs = 100;
input int DeviationPoints = 100;
input bool TelemetryEnabled = true;

input group "Live Twin"
input ENUM_STR_RUNTIME_MODE RuntimeMode = STR_RUNTIME_NORMAL;
input string ShadowCommandFile = "StraddleShadow\\command.csv";
input string ShadowAckFile = "StraddleShadow\\ack.csv";
input int ShadowCommandMaxAgeMs = 2000;
input bool AllowShadowAdoptExistingCycle = false;

input group "Account Safety"
input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT;
input bool RequireBoundAccount = STR_REQUIRE_BOUND_DEFAULT;
input ulong ExpectedAccountLogin = 0;

input group "Optional Safety (disabled in replica baseline)"
input bool SafetyEnabled = STR_SAFETY_ENABLED_DEFAULT;
input double MaxEquityLossPercent = 20.0;
input double MaxGrossLots = 2.20;
input double MaxSpreadPoints = 1000.0;
input double DailyLossLimit = 0.0;

input group "Custom Profile"
// Defaults below are the measured Starwave/Target values, so CUSTOM_PROFILE is
// a Starwave clone out of the box and only the three tier lots (and N, and the
// basket target) need touching to reproduce any of the seven lot ladders the
// operator ran across 119 deployments in Aug 2026:
//   N30 0.01/0.05/0.20   N30 0.01/0.06/0.15   N30 0.01/0.04/0.12
//   N30 0.01/0.03/0.10   N20 0.01/0.03/0.10   N20 0.01/0.04/0.15
//   N20 0.01/0.06/0.15
// Tier boundaries are floor(N/3)+1 and floor(2N/3)+1 -- verified 71/71 on the
// N=30 deployments and 45/45 on the N=20 ones, zero exceptions.
input int CustomLevelsPerSide = 30;
input ENUM_STR_STEP_MODE CustomStepMode = STR_STEP_ANCHOR_DIVISOR;
input double CustomStepValue = 3000.0;
input ENUM_TIMEFRAMES CustomATRTimeframe = PERIOD_M15;
input int CustomATRPeriod = 17;
input int CustomTier1End = 10;
input double CustomLot1 = 0.01;
input int CustomTier2End = 20;
input double CustomLot2 = 0.06;
input double CustomLot3 = 0.15;
input double CustomLockTriggerSteps = 2.0;
input double CustomLockOffsetPrice = 0.2;
input bool CustomActivationUsesTrailingDistance = true;
input double CustomPreTightenTrailDistanceSteps = 2.0;
input double CustomTightenTriggerSteps = 3.0;
input double CustomTrailDistanceSteps = 1.0;
input double CustomCycleTargetPercent = 0.18;
input double CustomCycleTargetMoney = 25.0;
input bool CustomCancelBeforeClose = true;
input int CustomDeploymentFillCooldownSeconds = 0;
input int CustomCloseIntervalSeconds = 0;
input int CustomRestartDelayMs = 2000;
input int CustomRearmDelaySeconds = 0;
input bool CustomStopUpdatesOnTimer = false;
input int CustomStopUpdateIntervalSeconds = 0;
input int CustomMaxStopUpdatesPerPass = 0;
input bool CustomStopScanNewestFirst = true;
// Target EA parity, default ON to match the Starwave binary: the level table
// holds ONE position ticket per (side,level), so a re-fill overwrites the
// pointer and the displaced position is never tracked again -- not trailed, not
// counted in the basket, never swept.  Measured: 153 of 2,468 fills (6.20%)
// were still open at the end of the window, 0/153 ever received an [sl] order,
// 0/146 sweeps left the book flat, and 137/137 same-level overlapping pairs
// have the EARLIER position never closed.  Turn this OFF for a hygienic run
// that closes everything it opens -- that is a DEVIATION from the Target.
input bool CustomReplicaOrphanLeak = true;

CStraddleEngine g_engine;

int OnInit()
  {
   SRuntimeConfig runtime={};
   runtime.runtime_mode=RuntimeMode;
   runtime.symbol=TradeSymbol;
   runtime.magic=MagicNumber;
   runtime.replica_mode=ReplicaMode;
   runtime.start_time=ReplicaStartTime;
   runtime.inter_order_delay_ms=InterOrderDelayMs;
   runtime.require_demo_account=RequireDemoAccount;
   runtime.require_bound_account=RequireBoundAccount;
   runtime.expected_account_login=ExpectedAccountLogin;
   runtime.safety_enabled=SafetyEnabled;
   runtime.max_equity_loss_pct=MaxEquityLossPercent;
   runtime.max_gross_lots=MaxGrossLots;
   runtime.max_spread_points=MaxSpreadPoints;
   runtime.daily_loss_limit=DailyLossLimit;
   runtime.telemetry_enabled=TelemetryEnabled;
   runtime.deviation_points=DeviationPoints;
   runtime.shadow_command_file=ShadowCommandFile;
   runtime.shadow_ack_file=ShadowAckFile;
   runtime.shadow_command_max_age_ms=ShadowCommandMaxAgeMs;
   runtime.allow_shadow_adopt_existing_cycle=
      AllowShadowAdoptExistingCycle;

   SCustomProfileConfig custom={};
   custom.levels_per_side=CustomLevelsPerSide;
   custom.step_mode=CustomStepMode;
   custom.step_value=CustomStepValue;
   custom.atr_timeframe=CustomATRTimeframe;
   custom.atr_period=CustomATRPeriod;
   custom.tier1_end=CustomTier1End;
   custom.lot1=CustomLot1;
   custom.tier2_end=CustomTier2End;
   custom.lot2=CustomLot2;
   custom.lot3=CustomLot3;
   custom.lock_trigger_steps=CustomLockTriggerSteps;
   custom.lock_offset_price=CustomLockOffsetPrice;
   custom.activation_uses_trailing_distance=CustomActivationUsesTrailingDistance;
   custom.pre_tighten_trail_distance_steps=CustomPreTightenTrailDistanceSteps;
   custom.tighten_trigger_steps=CustomTightenTriggerSteps;
   custom.trail_distance_steps=CustomTrailDistanceSteps;
   custom.cycle_target_balance_pct=CustomCycleTargetPercent;
   custom.cycle_target_money=CustomCycleTargetMoney;
   custom.cancel_before_close=CustomCancelBeforeClose;
   custom.deployment_fill_cooldown_seconds=CustomDeploymentFillCooldownSeconds;
   custom.close_interval_seconds=CustomCloseIntervalSeconds;
   custom.restart_delay_ms=CustomRestartDelayMs;
   custom.rearm_delay_seconds=CustomRearmDelaySeconds;
   custom.stop_updates_on_timer=CustomStopUpdatesOnTimer;
   custom.stop_update_interval_seconds=CustomStopUpdateIntervalSeconds;
   custom.max_stop_updates_per_pass=CustomMaxStopUpdatesPerPass;
   custom.stop_scan_newest_first=CustomStopScanNewestFirst;
   custom.replica_orphan_leak=CustomReplicaOrphanLeak;

   if(!g_engine.Initialize(runtime,Profile,custom))
      return INIT_FAILED;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   g_engine.Shutdown();
  }

void OnTick()
  {
   g_engine.OnTick();
  }

void OnTimer()
  {
   g_engine.OnTimer();
  }

void OnTradeTransaction(const MqlTradeTransaction &transaction,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
  {
   g_engine.OnTradeTransaction(transaction,request,result);
  }
