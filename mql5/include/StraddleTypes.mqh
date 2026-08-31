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
   STARWAVE_20 = 8,
   STARWAVE_30_HIGH = 9,
   STARWAVE_30_MID = 10,
   STARWAVE_20_WIDE = 11,
   STARWAVE_20_LIGHT = 12
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
   // Basket-close comment literal is a BUILD fingerprint, not a different
   // action.  On the ReportHistory-901018 tape the June/early-July build sent
   // basket closes with NO comment (2,724 of them inside the HISTORICAL_50 and
   // HISTORICAL_60 eras, zero carrying "STR CLOSE") while the anchor-divisor
   // build stamped "STR CLOSE" on all 1,010 of its closes (AGGRESSIVE_30 9,
   // LOW_RISK_30 11, STARWAVE_30 990).  Every order in both families produced a
   // DEAL_ENTRY_OUT deal and both run the same ~105 ms machine cadence, so the
   // two are one mechanism under two builds.  See parity audit DIV-3.
   bool              stamp_close_comment;
   int               deployment_fill_cooldown_seconds;
   int               close_interval_seconds;
   int               restart_delay_ms;
   int               rearm_delay_seconds;
   int               stop_update_interval_seconds;
   int               max_stop_updates_per_pass;
   bool              stop_scan_newest_first;
   bool              stop_updates_on_timer;
   // Target EA parity: the level table owns exactly ONE position ticket per
   // (side,level) and a re-fill OVERWRITES it, so the displaced position is
   // never tracked again -- it is not trailed, not counted in the basket, and
   // not closed by the sweep.  Measured on the Starwave tape: 153 of 2,468
   // fills (6.20%) were still open at the end of the window, 148 of them
   // survived at least one complete basket sweep and 66 survived 61 or more,
   // 137/137 same-level overlapping pairs have the EARLIER position never
   // closed, 0/146 sweeps left the book flat (residue ratchets 6 -> 148), and
   // 0/153 orphans ever received an [sl] order despite 1-9 days of XAUUSD
   // movement.  See ProfitBricks parity audit D6/D7.
   //
   // CROSS-VALIDATED against the 901018 tape with ONE instrument and one overlap
   // rule (tmp/a901_orphan.py, tmp/asw_orphan.py), which is what makes this a
   // BUILD switch rather than a measurement artifact.  Re-arm pendings dispatched
   // over a level that STILL HELD a position: 901018 0 of 11,549 (HISTORICAL_50
   // 0/2,847, HISTORICAL_60 0/6,422, AGGRESSIVE_30 0/29, LOW_RISK_30 0/18, and
   // even its own STARWAVE_30 era 0/2,233) versus Starwave 118 of 1,075 -- all
   // 118 ORDER_REASON_EXPERT on magic 26011001, so the operator is excluded.  Of
   // those 118, 85 were canceled at the sweep and 33 filled while the old
   // position was still open.  Same-slot OVERLAPPING re-fills: 0 of 10,475 vs 27
   // of 952.  The residue reproduces D6/D7 exactly at 153/2,468, and 142 of the
   // 153 outlived a later deployment (max 147 boundaries), so they are not merely
   // the final open basket.  Starwave's first deal is 2026-08-21, after the
   // 901018 tape ends 2026-07-30: the leak is the NEWER behaviour, hence true on
   // the profiles that model the August build and false on the four 901018-only
   // eras.  Both counts are LOWER bounds -- the probes group by (cycle,side,level)
   // and so ignore orphans displaced by a re-arm that fills in a later cycle.
   bool              replica_orphan_leak;
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
   bool              replica_orphan_leak;
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
   // Set when the interleaved first pass of the deployment burst failed to arm
   // this level, cleared when the single retry pass appended at the tail of the
   // same burst either arms it or abandons it.  See DeployOne().
   bool              deploy_deferred;
   ulong             order_ticket;
   ulong             position_ticket;
   bool              rearm_requested;
   long              rearm_after_msc;
   bool              trend_rescue_replacement;
   bool              trend_rescue_latched;
  };

#endif
