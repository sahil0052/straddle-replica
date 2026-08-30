#ifndef STRADDLE_REPLICA_TYPES_MQH
#define STRADDLE_REPLICA_TYPES_MQH

#define STR_MAX_LEVELS 60

enum ENUM_STR_PROFILE
  {
   HISTORICAL_50 = 0,
   HISTORICAL_60 = 1,
   AGGRESSIVE_30 = 2,
   LOW_RISK_30 = 3,
   LATEST_30 = 4,
   CUSTOM_PROFILE = 5,
   JUNE_2K = 6,
   STARWAVE_30 = 7,
   STARWAVE_20 = 8
  };

enum ENUM_STR_STEP_MODE
  {
   STR_STEP_FIXED = 0,
   STR_STEP_ANCHOR_DIVISOR = 1,
   STR_STEP_ATR = 2
  };

enum ENUM_STR_RUNTIME_MODE
  {
   STR_RUNTIME_NORMAL = 0,
   STR_RUNTIME_SHADOW = 1
  };

enum ENUM_CYCLE_STATE
  {
   CYCLE_IDLE = 0,
   CYCLE_DEPLOYING = 1,
   CYCLE_RUNNING = 2,
   CYCLE_CLOSING = 3,
   CYCLE_CANCELING = 4,
   CYCLE_RESTARTING = 5,
   CYCLE_HALTED = 6
  };

struct SProfileConfig
  {
   ENUM_STR_PROFILE profile;
   int               levels_per_side;
   ENUM_STR_STEP_MODE step_mode;
   double            fixed_step;
   double            anchor_divisor;
   ENUM_TIMEFRAMES   atr_timeframe;
   int               atr_period;
   double            atr_multiplier;
   double            lots[STR_MAX_LEVELS];
   double            lock_trigger_steps;
   double            lock_offset_price;
   bool              activation_uses_trailing_distance;
   double            pre_tighten_trail_distance_steps;
   double            tighten_trigger_steps;
   double            trail_distance_steps;
   double            cycle_target_balance_pct;
   double            cycle_target_money;
   bool              cancel_before_close;
   int               deployment_fill_cooldown_seconds;
   int               close_interval_seconds;
   int               restart_delay_ms;
   int               rearm_delay_seconds;
   int               stop_update_interval_seconds;
   int               max_stop_updates_per_pass;
   bool              stop_scan_newest_first;
   bool              stop_updates_on_timer;
   bool              trend_rescue_enabled;
   ENUM_TIMEFRAMES   trend_rescue_timeframe;
   int               trend_rescue_bars;
   int               trend_rescue_minimum_pending_levels;
   double            trend_rescue_move_price;
   double            trend_rescue_drawdown_money;
   double            trend_rescue_volume_multiplier;
  };

struct SCustomProfileConfig
  {
   int               levels_per_side;
   ENUM_STR_STEP_MODE step_mode;
   double            step_value;
   ENUM_TIMEFRAMES   atr_timeframe;
   int               atr_period;
   int               tier1_end;
   double            lot1;
   int               tier2_end;
   double            lot2;
   double            lot3;
   double            lock_trigger_steps;
   double            lock_offset_price;
   bool              activation_uses_trailing_distance;
   double            pre_tighten_trail_distance_steps;
   double            tighten_trigger_steps;
   double            trail_distance_steps;
   double            cycle_target_balance_pct;
   double            cycle_target_money;
   bool              cancel_before_close;
   int               deployment_fill_cooldown_seconds;
   int               close_interval_seconds;
   int               restart_delay_ms;
   int               rearm_delay_seconds;
   int               stop_update_interval_seconds;
   int               max_stop_updates_per_pass;
   bool              stop_scan_newest_first;
   bool              stop_updates_on_timer;
  };

struct SRuntimeConfig
  {
   ENUM_STR_RUNTIME_MODE runtime_mode;
   string            symbol;
   ulong             magic;
   bool              replica_mode;
   datetime          start_time;
   int               inter_order_delay_ms;
   bool              require_demo_account;
   bool              require_bound_account;
   ulong             expected_account_login;
   bool              safety_enabled;
   double            max_equity_loss_pct;
   double            max_gross_lots;
   double            max_spread_points;
   double            daily_loss_limit;
   bool              telemetry_enabled;
   int               deviation_points;
   string            shadow_command_file;
   string            shadow_ack_file;
   int               shadow_command_max_age_ms;
   bool              allow_shadow_adopt_existing_cycle;
  };

struct SShadowCommand
  {
   int               schema_version;
   ulong             command_seq;
   string            command;
   string            cycle_id;
   string            profile;
   double            anchor;
   double            step;
   long              target_start_utc_ms;
   long              expires_utc_ms;
  };

struct SLevelState
  {
   bool              is_buy;
   int               level;
   double            target_price;
   double            volume;
   bool              has_pending;
   bool              has_position;
   int               active_order_count;
   int               active_position_count;
   bool              duplicate_identity;
   bool              recovery_done;
   ulong             order_ticket;
   ulong             position_ticket;
   bool              rearm_requested;
   long              rearm_after_msc;
   bool              trend_rescue_replacement;
   bool              trend_rescue_latched;
  };

#endif
