#ifndef STR_REQUIRE_DEMO_DEFAULT
   #define STR_REQUIRE_DEMO_DEFAULT true
#endif
#ifndef STR_REQUIRE_BOUND_DEFAULT
   #define STR_REQUIRE_BOUND_DEFAULT false
#endif
#ifndef STR_SAFETY_ENABLED_DEFAULT
   #define STR_SAFETY_ENABLED_DEFAULT false
#endif

#include "StraddleTypes.mqh"
#include "StraddleEngine.mqh"

input group "Replica"
input ENUM_STR_PROFILE Profile = LATEST_30;
input string TradeSymbol = "";
input ulong MagicNumber = 901018;
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
input bool CustomActivationUsesTrailingDistance = false;
input double CustomPreTightenTrailDistanceSteps = 2.0;
input double CustomTightenTriggerSteps = 3.0;
input double CustomTrailDistanceSteps = 1.0;
input double CustomCycleTargetPercent = 0.18;
input double CustomCycleTargetMoney = 0.0;
input bool CustomCancelBeforeClose = false;
input int CustomDeploymentFillCooldownSeconds = 0;
input int CustomCloseIntervalSeconds = 0;
input int CustomRestartDelayMs = 3000;
input int CustomRearmDelaySeconds = 0;
input bool CustomStopUpdatesOnTimer = false;
input int CustomStopUpdateIntervalSeconds = 0;
input int CustomMaxStopUpdatesPerPass = 0;
input bool CustomStopScanNewestFirst = false;

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
