//+------------------------------------------------------------------+
//|                                              ProfitBricks2K.mq5 |
//|                                  Copyright 2026, Antigravity Team |
//|                                https://github.com/sahil0052      |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Antigravity StraddleReplica Team"
#property link      "https://github.com/sahil0052/straddle-replica"
#property version   "1.00"
#property description "ProfitBricks 2K - Standalone All-In-One EA (June 2026 $2k Scalper)"
#property description "Calibrated for $2k-$5k capital: 0.01 (L1-15), 0.03 (L16-25), 0.06 (L26-30), 0s instant trailing stops."

#define STR_REQUIRE_DEMO_DEFAULT false
#define STR_REQUIRE_BOUND_DEFAULT false
#define STR_SAFETY_ENABLED_DEFAULT false
#define STR_DEFAULT_PROFILE JUNE_2K
// This standalone is the June-2026 $2k artifact, so it pins both the profile
// and the magic of that regime (account 901018).  The shared modular build
// defaults to STARWAVE_30 / 26011001 instead -- see StraddleReplicaApp.mqh.
#define STR_DEFAULT_MAGIC 901018



// ====================================================================
// SECTION: StraddleTypes.mqh
// ====================================================================

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


// ====================================================================
// SECTION: ProfileCatalog.mqh
// ====================================================================

#ifndef STRADDLE_REPLICA_PROFILE_CATALOG_MQH
#define STRADDLE_REPLICA_PROFILE_CATALOG_MQH

// included inline

void ResetProfile(SProfileConfig &config)
  {
   config.levels_per_side=0;
   config.step_mode=STR_STEP_FIXED;
   config.fixed_step=0.0;
   config.anchor_divisor=0.0;
   config.atr_timeframe=PERIOD_M15;
   config.atr_period=14;
   config.atr_multiplier=0.0;
   config.lock_trigger_steps=2.0;
   config.lock_offset_price=0.2;
   // DIV-4: measured law, not a neutral default.  Every profile in this catalog
   // now sets this true and every one of them is backed by tape (see the
   // evidence blocks in HISTORICAL_50 and HISTORICAL_60), so the default is
   // true as well -- a profile added later without the line inherits the law
   // that the target's binary actually runs instead of the one it does not.
   // lock_offset_price survives only because SCustomProfileConfig exposes it as
   // an operator input; with this default it is unreachable on every built-in
   // path, which is exactly what StopScheduler's comment block predicts.
   config.activation_uses_trailing_distance=true;
   config.pre_tighten_trail_distance_steps=2.0;
   config.tighten_trigger_steps=3.0;
   config.trail_distance_steps=2.0;
   config.cycle_target_balance_pct=0.18;
   config.cycle_target_money=0.0;
   config.cancel_before_close=false;
   config.stamp_close_comment=true;
   config.deployment_fill_cooldown_seconds=0;
   config.close_interval_seconds=0;
   config.restart_delay_ms=3000;
   config.rearm_delay_seconds=0;
   config.stop_update_interval_seconds=0;
   config.max_stop_updates_per_pass=0;
   config.stop_scan_newest_first=false;
   config.stop_updates_on_timer=false;
   config.replica_orphan_leak=false;
   config.trend_rescue_enabled=false;
   config.trend_rescue_timeframe=PERIOD_M15;
   config.trend_rescue_bars=6;
   config.trend_rescue_minimum_pending_levels=0;
   config.trend_rescue_move_price=0.0;
   config.trend_rescue_drawdown_money=0.0;
   config.trend_rescue_volume_multiplier=1.0;
   ArrayInitialize(config.lots,0.0);
  }

void SetLotTier(SProfileConfig &config,const int first_level,const int last_level,const double volume)
  {
   for(int level=first_level;level<=last_level && level<=STR_MAX_LEVELS;level++)
      config.lots[level-1]=volume;
  }

bool LoadProfileConfig(const ENUM_STR_PROFILE profile,SProfileConfig &config)
  {
   ResetProfile(config);
   config.profile=profile;

   switch(profile)
     {
      case HISTORICAL_50:
         config.levels_per_side=50;
         config.step_mode=STR_STEP_ATR;
         config.atr_timeframe=PERIOD_M15;
         config.atr_period=17;
         config.atr_multiplier=0.10422410545583288;
         config.cycle_target_balance_pct=0.63;
         // The build that ran this regime sent basket closes with NO comment.
         // ReportHistory-901018, 2026.06.23 16:17 - 2026.07.02 15:18: 1,392
         // empty-comment market orders, every one resolving to a DEAL_ENTRY_OUT
         // deal, and not a single "STR CLOSE" anywhere in the era.
         config.stamp_close_comment=false;
         // ---- liquidation phase order, measured (DIV-6) ----------------------
         // ResetProfile defaults this flag to false, which sends BeginClose()
         // straight to CYCLE_CLOSING and flattens the basket before cancelling
         // the surviving pendings.  The tape does the opposite in every era.
         // tmp/a901_cancel_order.py attributes each cancelled grid pending to a
         // cycle by its end_time, splits that cycle's basket closes into
         // liquidation groups at a 60 s gap, takes the terminal group, and
         // classifies the phase order three ways (mutually exclusive):
         //
         //   era               cycles  CANCEL_FIRST  CLOSE_FIRST  INTERLEAVED
         //   HISTORICAL_50         95            95            0            0
         //   HISTORICAL_60         72            71            1            0
         //   AGGRESSIVE_30          2             1            0            1
         //   LOW_RISK_30            1             1            0            0
         //   STARWAVE_30          101            91            0           10
         //
         // 259 of 271 cycles are strictly cancel-first and exactly ONE is
         // close-first -- and that one (cycle 169) is a manual operator flatten,
         // identified by a `close by` order 0.232 s earlier.  PositionCloseBy has
         // no call site in this EA, so those 12 orders date hand actions
         // independently of anything being measured here.  Excluding the two
         // operator sweeps, the four eras that inherited false are 168/168 =
         // 100.00% cancel-first.  Cross-boundary attribution was checked rather
         // than assumed: 106 of 19,312 cancels (0.55%) end in a later cycle than
         // their placement, which cannot manufacture a 168-cycle result.
         config.cancel_before_close=true;
         // ---- activation law, measured (DIV-4) -------------------------------
         // ResetProfile defaults this flag to false, which routes activation
         // down StopScheduler's "entry+direction*lock_offset_price" branch and
         // writes the FIRST stop at exactly entry +/- 0.20 price.  Because
         // every later write must be strictly better (the monotonic returns at
         // the end of Calculate), that branch makes a hard prediction:
         // dir*(sl-open) can never be less than 0.20, and 0.20 must be a razor
         // atom.  ReportHistory-901018 falsifies both for this era:
         //
         //   n=4094 positions carrying an S/L, scored with their own cycle step
         //   dir*(sl-open) strictly inside (0,0.20):  351  (8.57%)  <- forbidden
         //   minimum dir*(sl-open):                  +0.01
         //   at 0.19 / 0.20 / 0.21:                   22 / 18 / 17  <- no atom
         //   dir*(sl-open) < 0:                         0
         //
         // 0.20 carries less mass than 0.19 does; the busiest single cent in the
         // era holds 26.  HISTORICAL_60 repeats it at n=7952: 1,068 inside
         // (0,0.20), min +0.01, 47/57/55 across 0.19/0.20/0.21.  So the target's
         // binary activates at the trailing distance, not at a fixed offset.
         config.activation_uses_trailing_distance=true;
         // Deliberately NOT setting trail_distance_steps: this era inherits
         // ResetProfile's 2.0, which equals pre_tighten_trail_distance_steps,
         // so the tighten ternary picks the same distance on both sides of
         // tighten_trigger_steps and the two-stage ratchet collapses into a
         // single-stage 2.0-step trail.  That is what the tape shows -- the
         // locked-distance histogram has NO structural trough (band [1,2)
         // holds 951/4094 = 23.23%, and 23.04% for HISTORICAL_60, against
         // 0/2809 for STARWAVE_30).  Do not copy trail_distance_steps=1.0 here
         // from the modern profiles; it would carve a trough that isn't there.
         SetLotTier(config,1,15,0.01);
         SetLotTier(config,16,25,0.03);
         SetLotTier(config,26,50,0.06);
         return true;

      case HISTORICAL_60:
         config.levels_per_side=60;
         config.step_mode=STR_STEP_ATR;
         config.atr_timeframe=PERIOD_M5;
         config.atr_period=44;
         config.atr_multiplier=0.09188197447190301;
         config.cycle_target_balance_pct=0.42;
         // Same build as HISTORICAL_50, same empty close comment: 1,332
         // empty-comment DEAL_ENTRY_OUT closes between 2026.07.02 16:28 and
         // the 2026.07.13 12:28 changeover, zero "STR CLOSE".
         config.stamp_close_comment=false;
         // DIV-6, the largest single-era cohort: 72 terminal liquidations, 71
         // strictly cancel-first and 1 close-first, and the close-first one is
         // cycle 169 -- a hand flatten with a `close by` 0.232 s before it.  On
         // the operator-free complement this era is 71/71.  The same probe also
         // shows the handoff is quantised: over 256 operator-free CANCEL_FIRST
         // sweeps the lead from last cancel to first close has min 97 ms and
         // 243/256 = 94.92% inside [95,135) ms -- one OnTimer period, which is
         // what CancelOneOrder() assigning CYCLE_CLOSING and RETURNING predicts.
         config.cancel_before_close=true;
         // DIV-4, same measurement as HISTORICAL_50 and the larger of the two
         // cohorts: n=7952 positions with an S/L, 1,068 (13.43%) carry
         // dir*(sl-open) strictly inside (0,0.20) -- unreachable if activation
         // wrote entry+lock_offset_price -- minimum +0.01, zero negative, and
         // 0.20 is unremarkable against its neighbours (0.19:47  0.20:57
         // 0.21:55) where the era's busiest single cent holds 78.
         config.activation_uses_trailing_distance=true;
         // As in HISTORICAL_50: trail_distance_steps is left at ResetProfile's
         // 2.0 on purpose so the ratchet stays single-stage.  Measured band
         // [1,2) occupancy 1832/7952 = 23.04%, neighbour-density ratio 0.920 --
         // a smooth distribution with no tighten step in it.
         SetLotTier(config,1,15,0.01);
         SetLotTier(config,16,45,0.02);
         SetLotTier(config,46,60,0.05);
         return true;

      case AGGRESSIVE_30:
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor = 6000.0;
         config.trail_distance_steps=1.0;
         // DIV-4 by parsimony, not by direct measurement.  This regime ran for
         // ~90 minutes on 2026.07.13 (2 deployments, 29 positions with an S/L),
         // which is far too little to falsify an activation law on its own: 2
         // raws inside (0,0.20), 1 at 0.20.  But the activation branch is a
         // single code path in a single binary, and the two eras that bracket
         // this one -- HISTORICAL_60 before it, STARWAVE_30 after -- both
         // demand the trailing-distance branch on 7,952 and 2,809 positions
         // respectively.  Nothing supports the binary switching its activation
         // rule for 90 minutes and switching back, so it inherits the law.
         config.activation_uses_trailing_distance=true;
         // DIV-6, by the same probe and by the same parsimony argument.  This
         // era authored exactly ONE terminal liquidation of its own (cycle 170)
         // and it is cancel-first; its other sweep (cycle 171) is a hand flatten
         // with a `close by` 0.109 s before it, scrambled ticket order and 2 ms
         // gaps.  n=1 proves nothing alone, but the flag is a single field read
         // by a single binary and the eras on both sides of this one are 95/95
         // and 71/71 cancel-first, so it inherits the order.
         config.cancel_before_close=true;
         // Resolved, no longer open: 9 of this era's 28 attested S/L positions
         // score dir*(sl-open) < 0, worst -10.559 steps (-7.18 in PRICE), which
         // NEITHER activation branch can produce -- substituting a market-
         // anchored write into its own gate gives locked = favorable - D >= 0
         // for EVERY market price, so a negative is outside the range of the
         // function, not an unlikely draw from it.  These nine are OPERATOR-
         // authored, not an attribution error: the broker-attested [sl X] price
         // equals the position field to the cent in all 28 rows (so nothing was
         // stale), re-measuring from the burst lattice clears 0 of 9, solving
         // each shared-price group for the market it implies passes the gate for
         // only 0/3, 0/2 and 5-of-9 members (a real broadcast passes for all),
         // the violating prices are 16x more whole-dollar and 6.6x more
         // round-10c than the era's population, and two of them sit 0.109 s and
         // 30 s from a `close by`.  See parity audit DIV-6 / section 3.1.
         SetLotTier(config,1,10,0.08);
         SetLotTier(config,11,20,0.41);
         SetLotTier(config,21,30,0.82);
         return true;

      case LOW_RISK_30:
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor = 3000.0;
         config.trail_distance_steps=1.0;
         // DIV-4 by parsimony, as AGGRESSIVE_30 above: one deployment, 29
         // positions with an S/L, minimum dir*(sl-open) = +0.20 exactly with a
         // single position there.  At n=29 on a one-cent price grid that is not
         // evidence for the fixed-offset branch, and this era's ratchet DOES
         // show the two-stage trough the modern profiles show (band [1,2)
         // occupancy 0/29), so it is the same build family as STARWAVE_30.
         config.activation_uses_trailing_distance=true;
         // DIV-6: this era's single terminal liquidation is cancel-first (1/1,
         // no operator marker anywhere near it), and it is the same build family
         // as STARWAVE_30, which carries the flag explicitly.
         config.cancel_before_close=true;
         SetLotTier(config,1,10,0.01);
         SetLotTier(config,11,20,0.02);
         SetLotTier(config,21,30,0.05);
         return true;

      case JUNE_2K:
         // Target EA parity: initial $2,000 growth regime (June 23 - July 02, 2026).
         // Turned $2,000 into $4,059 in 3.5 days with 2,313 micro-trades (85% win rate).
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor=3000.0;
         config.trail_distance_steps=1.0;
         config.lock_trigger_steps=2.0;
         config.pre_tighten_trail_distance_steps=2.0;
         config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
         config.cycle_target_money=30.0;
         config.cancel_before_close=true;
         // Unpaced high-frequency micro-scalping (burst execution).
         //
         // restart_delay_ms is 1000 here and deliberately NOT the 2000 carried by
         // the six STARWAVE profiles.  Both numbers are measured; they belong to
         // different epochs of the same EA:
         //
         //   pre-2026-07-24 (this regime)   restart floor 1.17 s, 64/68 under 4.5 s
         //   Starwave 2026-08-21..08-29     floor(next_deploy)-floor(flat) = 2 s on
         //                                  96 cycles and 3 s on 6, 102/148 = 68.9%
         //
         // The engine waits (restart_delay_ms+999)/1000 WHOLE seconds against a
         // whole-second TimeCurrent(), so 1000 yields a 1 s floor (observed 1.17 s
         // once tick lag is added) and 2000 yields a 2 s floor.  Raising this to
         // 2000 would contradict the pre-break floor, so do not "align" it with
         // the Starwave profiles.
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=1000;
         config.deployment_fill_cooldown_seconds=0;
         // Target EA parity: single-pointer level table, so a re-fill orphans the
         // displaced position permanently (see SLevelState/replica_orphan_leak).
         // This is a property of the BINARY, not of the pacing epoch, so every
         // profile that reconstructs the real EA carries it.
         config.replica_orphan_leak=true;
         // Lot schedule for $2k: 0.01 at L1-15, 0.03 at L16-25, 0.06 at L26-30
         SetLotTier(config,1,15,0.01);
         SetLotTier(config,16,25,0.03);
         SetLotTier(config,26,30,0.06);
         // Trend rescue
         config.trend_rescue_enabled=true;
         config.trend_rescue_timeframe=PERIOD_M15;
         config.trend_rescue_bars=6;
         config.trend_rescue_minimum_pending_levels=0;
         config.trend_rescue_move_price=20.0;
         config.trend_rescue_drawdown_money=400.0;
         config.trend_rescue_volume_multiplier=2.0;
         return true;

      case LATEST_30:
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
          // Target EA parity: forensic audit of ReportHistory-901018 final regime
          // (99 grid deployments, Jul 14-30) measured anchor/step median=3000.1
          // (range 2989-3011, all deviation explained by 0.01 price rounding).
          config.anchor_divisor = 3000.0;
          config.trail_distance_steps=1.0;
          // Target EA parity: SL-lock profit distribution across 287 winners
          // closed at SL is continuous on [0,1) steps, has a hard GAP on (1,2),
          // and is continuous again on [2,~8]. Zero losers ever closed at SL
          // (SL is never placed below entry). The unique trailing model that
          // reproduces all three facts:
          //   - activate at 2.0 favorable steps, SL = market - 2.0 steps
          //     (first lock is exactly breakeven, never sub-entry)
          //   - pre-tighten trail distance 2.0 steps -> SL profits in [0,1)
          //   - tighten at 3.0 favorable steps to 1.0-step trail -> profits >= 2
          //   - runners keep the fixed 1.0-step trail (max observed 7.96 steps,
          //     profit = peak - 1 step; no further tightening)
          config.lock_trigger_steps=2.0;
          config.pre_tighten_trail_distance_steps=2.0;
          config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
          // Target EA parity: positive final-regime cycle nets cluster at a
          // median of $29.40 with the bulk of exits landing between $25-$33.
          config.cycle_target_money=30.0;
         config.cancel_before_close=true;
         // Target EA parity: THE 20-SECOND PACING FAMILY.
         // The Target EA's operator raised all four pacing knobs from 0 to 20 in a
         // single change on 2026-07-24 midday. The flatten close mode proves the
         // date: 69 consecutive burst-close sweeps (Jul 14 -> Jul 24 09:10), then 32
         // consecutive paced sweeps (Jul 24 15:48 -> Jul 30 17:10). That is 2 runs
         // where a state-dependent rule on a 69/32 split would give ~45, so it is a
         // settings change, not a runtime condition. Measured on each side:
         //
         //   knob                     before Jul 24         after Jul 24
         //   close_interval_seconds   0.106 s/close         20.19 s/close
         //   rearm_delay_seconds      no floor, 42/1196     floor 19.80 s, only
         //                            delays under 4.5 s    2/581 under 19 s
         //   restart_delay_ms         floor 1.17 s,         floor 20.91 s,
         //                            64/68 under 4.5 s     32/32 over 20.9 s
         //   deploy_fill_cooldown     gap after an in-burst gap after an in-burst
         //                            fill = 0.13 s         fill = 20.17 s
         //
         // Parity must track the LATER configuration, so all four are 20.
         //
         // The cooldown is the strongest of the four: across 32 post-break
         // deployments, burst span = 6.12 s + 19.898 s * (in-burst fills) with a max
         // residual of 0.66 s over fill counts {0,1,2,3,7,10}, and the 6.12 s
         // intercept over 59 placement gaps re-derives InterOrderDelayMs = 100
         // independently. Causally, 25 of 25 gaps that follow an in-burst fill are
         // >= 15 s while 0 of 1863 gaps that do not are, so the pause is attached to
         // the fill rather than to the clock.
         //
         // rearm_delay_seconds was previously 5 on the strength of a modal bucket
         // ("490 of 2,370 re-arms in the first 5 s"). That reading pooled the two
         // regimes: a delay parameter shows up as a FLOOR, not a spike, because the
         // re-arms that expose it are the ones where price was already back at the
         // level and only the timer was holding them. 5 is refuted on both sides of
         // the break. A 5 s delay sampled by a 20 s evaluation clock is refuted too:
         // that scatters across 20/40/60 s, but the post-break counts are 48 near
         // 20 s against 5 near 40 s and 5 near 60 s.
         //
         // All four sit ~0.1-0.9 s off a round 20.00 because the engine compares a
         // whole-second TimeCurrent() against the threshold and samples it on a
         // 100 ms timer; the sign of the offset depends on which timestamp the
         // report exposes (close_time is pre-fill, so re-arms read 19.8).
         config.deployment_fill_cooldown_seconds=20;
         config.close_interval_seconds=20;
         config.restart_delay_ms=20000;
         config.rearm_delay_seconds=20;
         // Target EA parity: same binary as JUNE_2K/STARWAVE_*, therefore the same
         // single-pointer level table.  The 2026-07-24 change moved four pacing
         // knobs; it did not change how positions are tracked.
         config.replica_orphan_leak=true;
          config.stop_scan_newest_first=true;
          config.max_stop_updates_per_pass=1;
          // Target EA parity: the 2026-07-24 change was a GLOBAL 20 s serialization of
          // every trade action, not just the flatten sweep. The trailing stops moved
          // onto the same clock, and that is provable by elimination on PRICE TWINS --
          // pairs of positions whose armed stop prices agree within 0.05 on the same
          // side. Two live stops at the same price MUST be taken by the same tick, so
          // any twin pair that exits far apart cannot have had both stops live at that
          // price; the second was moved there only after the first was already gone.
          //
          //   twin pairs        n      med gap   <0.1s apart   15-25 s apart
          //   TARGET pre    18700        0.00s        16265              11
          //   TARGET post     252       20.13s            0             165
          //   OURS            342        0.01s           47               1
          //
          // Zero of 252 post-break twins fire together and 165 land in the 15-25 s
          // bucket: one stop moves per 20 s. The pre-break book is the control -- same
          // stop mathematics, no serialization, 87% of twins fire inside 100 ms, which
          // is precisely the behaviour an interval of 0 produces and precisely what our
          // own book shows. Corroborated on the whole stop population: consecutive
          // stop-out gaps in the 5-200 s band land within 0.5 s of a x20 multiple for
          // 320 of 498 post-break Target gaps (64.3%, mode exactly x1) against 170 of
          // 3034 pre-break (5.6%) and 6 of 105 of ours (5.7%); and the post-break
          // Target has 0 of 841 consecutive stop-outs closer than 100 ms (minimum gap
          // 0.2890 s) where we have 43 of 341 (12.61%).
          //
          // Do NOT justify a value here from the whole Target book: pooled, it reads
          // 52% sub-100 ms and appears to endorse an interval of 0, but that number is
          // 94% pre-break rows and inverts on the comparable slice.
          //
          // The gate lives at StraddleEngine.mqh:2582 and stamps m_last_stop_update_at
          // before scanning, so a pass that finds nothing to tighten still spends the
          // slot -- the rate is "at most one stop move per 20 s". That is the right
          // shape: the Target's twin gaps are mostly exactly 20 s with a 80-of-252 tail
          // beyond 25 s, which is what burnt slots look like.
          config.stop_update_interval_seconds=20;
          config.stop_updates_on_timer=true;
          config.trend_rescue_enabled=true;
          // Target EA parity: the rescue fired in 6 of the 100 final-regime cycles
          // (3 before the Jul-24 break, 3 after -- so these knobs did NOT change
          // with the pacing family). 125 rescue orders total. The decision instant
          // for all measurements below is the FIRST cancel of a trend-side base
          // pending that is later re-placed at 2x -- not the first 2x placement,
          // which happens many ticks later because TryCancelOneTrendRescueOrder
          // returns early until the whole trend side has been pulled.
          config.trend_rescue_timeframe=PERIOD_M15;
          // Target EA parity: 6 is the unique argmax over lookbacks {2,4,6,8,10,
          // 12,16,24} -- only at 6 do all six events clear move_price (min 19.85,
          // 0.75% under and inside reconstruction error, since a "bar close" here
          // is the last trade print in the bucket rather than the true OHLC close).
          // Every other lookback lets a real event fire below the threshold.
          config.trend_rescue_bars=6;
          // Target EA parity: trend-side base pendings at the decision instant were
          // 3 16 10 6 19 11. The minimum sits exactly ON the threshold with zero
          // margin -- the signature of a real gate rather than a fitted one.
          config.trend_rescue_minimum_pending_levels=3;
          config.trend_rescue_move_price=20.0;
          // Target EA parity: 400 is the corner of the falsifier plateau. Asking the
          // question a LATCH requires -- did floating reach -X at or before the first
          // observable action, evaluated only at trade prints where the mark is exact
          // -- the count of cycles that go true without rescuing falls monotonically
          // 12 -> 4 across -300 -> -400, sits FLAT at 4 through -440, and only drops
          // at -460 by buying two impossible negative leads (the EA acting before its
          // own gate opened). Zero missed events anywhere below -520.
          //
          // Because floating is exactly linear in the mark, the mark each event would
          // have needed for floating to touch -400 is closed-form; 4 of 6 sit within
          // a few points of it at the decision instant, inside the local 6 h range:
          //   cyc 197 float -398.82, needed 0.17 pts (mark 2 s old; crossed -400
          //           5.4 s after the sweep began)      cyc 252 -382.85, 1.01 pts
          //   cyc 250 -375.51, 4.08 pts (mark 196 s stale)  cyc 244 -77.92, 6.44 pts
          //   cyc 234 already -759.25          cyc 187 22.98 pts, 10.5-min print gap
          // The residual is 1 falsifier in 94 (cyc 253) and it goes true with only
          // 14.6 min of cycle left; 3 of the other 4 are blocked by move_price
          // (moves of -17.70, +16.71, +15.60).
          //
          // NOTE: this threshold is BOUNDED, not point-identified. The report carries
          // no tick feed -- the reconstructed mark is the set of trade prints, fresh
          // for only 0.3% of the timeline (median gap 32 s, p90 388 s, max 49 h).
          config.trend_rescue_drawdown_money=400.0;
          // Target EA parity: rescue replacements trade at exactly 2x the tier
          // volume in the dataset (0.12 = 2x0.06 at L11-20, 0.30 = 2x0.15 at L21-30).
          // The cancel count EQUALS the trend-side pending count in every event
          // measurable (3/3, 11/11, 20/20, 12/12): the rescue pulls every surviving
          // base pending on the trend side and re-places it at 2x. Cancel-to-cancel
          // gaps of 0.10-0.12 s re-derive InterOrderDelayMs=100 a fourth independent
          // way (after deployment gaps, flatten sweeps, and the cooldown intercept).
          config.trend_rescue_volume_multiplier=2.0;
          // Target EA parity: final-regime (Jul 14-30) lot schedule measured
          // from every order the Target EA placed in that window:
         // Target EA parity: final-regime (Jul 14-30) lot schedule measured
         // from every order the Target EA placed in that window:
         //   L1-10 -> 0.01 (10,940 orders), L11-20 -> 0.06 (2,624 orders),
         //   L21-30 -> 0.15 (378 orders). Zero exceptions at base volume.
         SetLotTier(config,1,10,0.01);
         SetLotTier(config,11,20,0.06);
         SetLotTier(config,21,30,0.15);
         return true;

      case STARWAVE_30:
         // Starwave (60542) Parity: 30-level burst execution profile (Aug 2026).
         // 0s unpaced micro-scalping, 100ms inter-order delay, instant tick SL updates.
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor=3000.0;
         config.trail_distance_steps=1.0;
         config.lock_trigger_steps=2.0;
         config.pre_tighten_trail_distance_steps=2.0;
         config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
         // Basket target: epoch 2026-08-24 15:34 -> 2026-08-25 04:06 (20 cycles).
         // Banked value p25/p50/p75 = 22.24/26.29/27.82; the 3-cycle censored
         // bracket over 08-24 19:22..19:49 pins it to (26.41, 26.51].
         config.cycle_target_money=26.5;
         config.cancel_before_close=true;
         // 0s burst execution (unpaced)
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=2000;
         config.deployment_fill_cooldown_seconds=0;
         config.stop_scan_newest_first=true;
         // Lot schedule (N30): 0.01 (L1-10), 0.06 (L11-20), 0.15 (L21-30)
         SetLotTier(config,1,10,0.01);
         SetLotTier(config,11,20,0.06);
         SetLotTier(config,21,30,0.15);
         // Trend rescue disabled
         config.trend_rescue_enabled=false;
         return true;

      case STARWAVE_20:
         // Starwave (60542) Parity: 20-level burst execution profile (Aug 2026).
         // Compact grid, 0s unpaced micro-scalping, 100ms inter-order delay.
         config.levels_per_side=20;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor=3000.0;
         config.trail_distance_steps=1.0;
         config.lock_trigger_steps=2.0;
         config.pre_tighten_trail_distance_steps=2.0;
         config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
         // Basket target: epoch 2026-08-27 11:44 -> 2026-08-28 16:18, the single
         // largest observed regime (52 cycles).  Banked value p25/p50/p75 =
         // 4.34/6.40/11.63; the 7-cycle censored bracket pins it to (6.45, 6.75].
         config.cycle_target_money=6.5;
         config.cancel_before_close=true;
         // 0s burst execution (unpaced)
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=2000;
         config.deployment_fill_cooldown_seconds=0;
         config.stop_scan_newest_first=true;
         // Lot schedule (N20): 0.01 (L1-6), 0.04 (L7-13), 0.15 (L14-20)
         SetLotTier(config,1,6,0.01);
         SetLotTier(config,7,13,0.04);
         SetLotTier(config,14,20,0.15);
         // Trend rescue disabled
         config.trend_rescue_enabled=false;
         return true;

      case STARWAVE_30_HIGH:
         // Starwave (60542) Parity: 30-level heavy-tail ladder (2026-08-21 14:35
         // -> 2026-08-24 13:35, 10 cycles, deepest fill L23).  Identical geometry
         // and execution cadence to STARWAVE_30; only the lot ladder is heavier.
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor=3000.0;
         config.trail_distance_steps=1.0;
         config.lock_trigger_steps=2.0;
         config.pre_tighten_trail_distance_steps=2.0;
         config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
         // Banked value p25/p50/p75 = 26.43/26.67/30.37 -- the same target the
         // next epoch used, so the operator retuned lots here, not the target.
         config.cycle_target_money=26.5;
         config.cancel_before_close=true;
         // 0s burst execution (unpaced)
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=2000;
         config.deployment_fill_cooldown_seconds=0;
         config.replica_orphan_leak=true;
         config.stop_scan_newest_first=true;
         // Lot schedule (N30): 0.01 (L1-10), 0.05 (L11-20), 0.20 (L21-30).
         // Tier boundaries 11/21 are the canonical floor(N/3)+1 / floor(2N/3)+1.
         SetLotTier(config,1,10,0.01);
         SetLotTier(config,11,20,0.05);
         SetLotTier(config,21,30,0.20);
         // Trend rescue disabled
         config.trend_rescue_enabled=false;
         return true;

      case STARWAVE_30_MID:
         // Starwave (60542) Parity: 30-level light ladder / low target (2026-08-26
         // 17:20 -> 2026-08-27 08:35, 18 cycles, deepest fill L18).  The third
         // tier was never reached in this epoch; it inherits 0.15 from the
         // observed N30 sibling (STARWAVE_30) rather than being invented.
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor=3000.0;
         config.trail_distance_steps=1.0;
         config.lock_trigger_steps=2.0;
         config.pre_tighten_trail_distance_steps=2.0;
         config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
         // Banked value p25/p50/p75 = 7.62/13.56/14.90; the 4-cycle censored
         // bracket over 08-27 02:33..04:28 pins it to (11.33, 11.98].
         config.cycle_target_money=12.0;
         config.cancel_before_close=true;
         // 0s burst execution (unpaced)
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=2000;
         config.deployment_fill_cooldown_seconds=0;
         config.replica_orphan_leak=true;
         config.stop_scan_newest_first=true;
         // Lot schedule (N30): 0.01 (L1-10), 0.04 (L11-20), 0.15 (L21-30, inferred)
         SetLotTier(config,1,10,0.01);
         SetLotTier(config,11,20,0.04);
         SetLotTier(config,21,30,0.15);
         // Trend rescue disabled
         config.trend_rescue_enabled=false;
         return true;

      case STARWAVE_20_WIDE:
         // Starwave (60542) Parity: 20-level heavy mid-tier / high target
         // (2026-08-28 17:13 -> 21:56, 13 cycles across two epochs, deepest L12).
         // Third tier never reached; inherits 0.15 from STARWAVE_20.
         config.levels_per_side=20;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor=3000.0;
         config.trail_distance_steps=1.0;
         config.lock_trigger_steps=2.0;
         config.pre_tighten_trail_distance_steps=2.0;
         config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
         // Banked value p25/p50/p75 = 28.64/30.19/46.28; the censored bracket on
         // the 08-28 19:42+ epoch pins it to (27.73, 28.64].
         config.cycle_target_money=28.5;
         config.cancel_before_close=true;
         // 0s burst execution (unpaced)
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=2000;
         config.deployment_fill_cooldown_seconds=0;
         config.replica_orphan_leak=true;
         config.stop_scan_newest_first=true;
         // Lot schedule (N20): 0.01 (L1-6), 0.06 (L7-13), 0.15 (L14-20, inferred)
         SetLotTier(config,1,6,0.01);
         SetLotTier(config,7,13,0.06);
         SetLotTier(config,14,20,0.15);
         // Trend rescue disabled
         config.trend_rescue_enabled=false;
         return true;

      case STARWAVE_20_LIGHT:
         // Starwave (60542) Parity: 20-level light mid-tier (2026-08-27 09:26 ->
         // 11:03, 3 cycles, deepest fill L7).  This is the only configured lot
         // ladder in the target tape that no other profile reproduces: after
         // folding every manual partial-close fragment back onto its parent
         // position_id, 2326 of 2327 level-tagged positions are covered by the
         // other Starwave profiles and this ladder is the single remainder.
         config.levels_per_side=20;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor=3000.0;
         config.trail_distance_steps=1.0;
         config.lock_trigger_steps=2.0;
         config.pre_tighten_trail_distance_steps=2.0;
         config.tighten_trigger_steps=3.0;
         config.activation_uses_trailing_distance=true;
         // Only 3 cycles, so no censored bracket survives the >=3-mark filter;
         // the target is the banked-value median (p25/p50/p75 = 14.30/17.80/22.95).
         config.cycle_target_money=17.8;
         config.cancel_before_close=true;
         // 0s burst execution (unpaced)
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=2000;
         config.deployment_fill_cooldown_seconds=0;
         config.replica_orphan_leak=true;
         config.stop_scan_newest_first=true;
         // Lot schedule (N20): 0.01 (L1-6), 0.03 (L7-13), 0.15 (L14-20, inferred).
         // N is not uniquely pinned here: only the tier-2 boundary was observed
         // (b2=7 => N in {18,19,20}) because tier 3 was never reached.  N=20 is
         // taken from the epoch that starts 41 minutes later the same day, whose
         // observed pair b2=7 / b3=14 admits N=20 uniquely.
         SetLotTier(config,1,6,0.01);
         SetLotTier(config,7,13,0.03);
         SetLotTier(config,14,20,0.15);
         // Trend rescue disabled
         config.trend_rescue_enabled=false;
         return true;

      case CUSTOM_PROFILE:
         return false;
     }
   return false;
  }

bool LoadCustomProfile(const SCustomProfileConfig &custom,SProfileConfig &config)
  {
   if(custom.levels_per_side<1 || custom.levels_per_side>STR_MAX_LEVELS)
      return false;
   if(custom.tier1_end<1 || custom.tier1_end>custom.levels_per_side)
      return false;
   if(custom.tier2_end<custom.tier1_end || custom.tier2_end>custom.levels_per_side)
      return false;
   if(custom.lot1<=0.0 || custom.lot2<=0.0 || custom.lot3<=0.0 || custom.step_value<=0.0)
      return false;
   if(custom.lock_trigger_steps<=0.0 ||
      custom.lock_offset_price<0.0 ||
      custom.pre_tighten_trail_distance_steps<=0.0 ||
      custom.tighten_trigger_steps<custom.lock_trigger_steps ||
      custom.trail_distance_steps<=0.0)
      return false;
   if(custom.step_mode==STR_STEP_ATR && custom.atr_period<2)
      return false;
   if(custom.deployment_fill_cooldown_seconds<0 ||
      custom.close_interval_seconds<0 ||
      custom.restart_delay_ms<0 ||
      custom.rearm_delay_seconds<0 ||
      custom.stop_update_interval_seconds<0 ||
      custom.max_stop_updates_per_pass<0)
      return false;

   ResetProfile(config);
   config.profile=CUSTOM_PROFILE;
   config.levels_per_side=custom.levels_per_side;
   config.step_mode=custom.step_mode;
   if(custom.step_mode==STR_STEP_FIXED)
      config.fixed_step=custom.step_value;
   else if(custom.step_mode==STR_STEP_ANCHOR_DIVISOR)
      config.anchor_divisor=custom.step_value;
   else
     {
      config.atr_timeframe=custom.atr_timeframe;
      config.atr_period=custom.atr_period;
      config.atr_multiplier=custom.step_value;
     }
   config.lock_trigger_steps=custom.lock_trigger_steps;
   config.lock_offset_price=custom.lock_offset_price;
   config.activation_uses_trailing_distance=custom.activation_uses_trailing_distance;
   config.pre_tighten_trail_distance_steps=custom.pre_tighten_trail_distance_steps;
   config.tighten_trigger_steps=custom.tighten_trigger_steps;
   config.trail_distance_steps=custom.trail_distance_steps;
   config.cycle_target_balance_pct=custom.cycle_target_balance_pct;
   config.cycle_target_money=custom.cycle_target_money;
   config.cancel_before_close=custom.cancel_before_close;
   config.deployment_fill_cooldown_seconds=custom.deployment_fill_cooldown_seconds;
   config.close_interval_seconds=custom.close_interval_seconds;
   config.restart_delay_ms=custom.restart_delay_ms;
   config.rearm_delay_seconds=custom.rearm_delay_seconds;
   config.stop_update_interval_seconds=custom.stop_update_interval_seconds;
   config.max_stop_updates_per_pass=custom.max_stop_updates_per_pass;
   config.stop_scan_newest_first=custom.stop_scan_newest_first;
   config.stop_updates_on_timer=custom.stop_updates_on_timer;
   // CUSTOM_PROFILE is the only escape hatch from Target-parity orphan
   // tracking: every built-in reconstruction of the real EA hard-codes
   // replica_orphan_leak=true, so an operator who wants the sweep to flatten
   // EVERYTHING carrying the magic must run CUSTOM_PROFILE with this false.
   config.replica_orphan_leak=custom.replica_orphan_leak;
   SetLotTier(config,1,custom.tier1_end,custom.lot1);
   SetLotTier(config,custom.tier1_end+1,custom.tier2_end,custom.lot2);
   SetLotTier(config,custom.tier2_end+1,custom.levels_per_side,custom.lot3);
   return true;
  }

#endif


// ====================================================================
// SECTION: StopScheduler.mqh
// ====================================================================

#ifndef STRADDLE_STOP_SCHEDULER_MQH
#define STRADDLE_STOP_SCHEDULER_MQH

// included inline

class CStopScheduler
  {
public:
   bool Calculate(const ENUM_POSITION_TYPE type,
                  const double entry,
                  const double current_sl,
                  const double bid,
                  const double ask,
                  const double step,
                  const double tick_size,
                  const int digits,
                  const double point,
                  const long stops_level,
                  const SProfileConfig &profile,
                  double &desired) const
     {
      if(step<=0.0 || tick_size<=0.0 || digits<0 || point<=0.0)
         return false;
      double market=(type==POSITION_TYPE_BUY ? bid : ask);
      double direction=(type==POSITION_TYPE_BUY ? 1.0 : -1.0);
      double favorable_steps=direction*(market-entry)/step;
      double minimum_distance=(double)stops_level*point;

      // ---------------------------------------------------------------------
      // TWO-STAGE RATCHET.  Under LATEST_30: lock_trigger=2.0,
      // pre_tighten_trail=2.0, tighten_trigger=3.0, trail_distance=1.0.
      //
      // The branches below make the locked-in profit STRUCTURALLY BANDED:
      //
      //   peak == 2.0            -> SL at breakeven         -> locks  ~0.0
      //   peak in (2.0, 3.0)     -> SL = peak - 2.0         -> locks in (0.0,1.0)
      //   peak >= 3.0            -> SL = peak - 1.0         -> locks at >= 2.0
      //
      // so a locked value between 1.0 and 2.0 is unreachable THROUGH THE
      // TRAILING BRANCH: it would need a peak in (3.0,4.0) with the 2.0
      // distance still applied, but at peak >= 3.0 the ternary below has
      // already switched to 1.0.  The one door into the band is the ACTIVATION
      // branch, which applies pre_tighten unconditionally -- see the Starwave
      // note below -- so the band is a deep trough, not a vacuum.  Either way
      // the configuration is falsifiable by a single histogram.
      //
      // VERIFIED against the Target's 2,480 final-regime SL closures using the
      // broker's OWN attestation of the level that fired -- the price inside the
      // exit order's "[sl <price>]" comment (tools/forensics/attested_stop.py).
      // That instrument needs no SL reconstruction, no mark, and no spread
      // model.  Measured density per 0.05 step across the wall:
      //
      //   [0.50,1.00) 43.3 | [1.00,1.25) 0.0 | [1.25,1.50) 0.0 | [1.50,1.75) 0.0
      //   [1.75,1.90)  0.0 | [1.90,1.95) 0.0 | [1.95,2.00) 8.0 | [2.00,2.05) 56.0
      //
      // The forbidden band (1.00,1.95) is EXACTLY EMPTY -- 0 of 2,480 -- with
      // large mass immediately on both sides.  The only residue is 8 stops in
      // [1.95,2.00), and each is 0, 1 or 2 ticks below 2.0000 (tick 0.01 on a
      // step of ~1.36 = 0.735% of a step): that is the NormalizeDouble/MathRound
      // quantisation and the stops_level clamp below, not a rule difference.
      //
      // The instrument matters.  Measured on FILL price instead, 138 of 2,480
      // (5.6%) appear in the band -- that is stop-fill slippage, which no
      // parameter controls.  The band fills up monotonically as the measurement
      // degrades: attested 0.32% -> position field 0.32% -> fill 5.56%.  Do not
      // re-derive the ratchet from close prices and conclude the band leaks.
      //
      // Monotonicity also verified on the same population: the position's final
      // stop_loss equals the attested fired level in 99.8% of cases, is tighter
      // in 0.1% (a later ratchet write) and looser in 0.1% (<= 0.105 steps,
      // clamp noise).  A loosening write would contradict the return conditions
      // at the bottom of this function; effectively none occur.
      //
      // ACTIVATION IS NOT EXACT BREAKEVEN, and must not be "corrected" to it.
      // Because the gate is polled (100 ms timer), the tick that first satisfies
      // favorable_steps >= 2.0 has usually already overshot to 2.0 + e, so the
      // written stop lands at entry + e*step.  Measured on attested prices:
      // median +0.124 steps, p10 +0.029, p90 +0.222, and 0 of 317 sit at exact
      // breakeven.  The distribution is STRICTLY POSITIVE, which is the
      // signature of a late poll -- a lock_offset_price rule would give a
      // constant, and a pre_tighten != lock_trigger would allow negatives.
      // This offset is emergent from polling, not a parameter: leave it alone.
      //
      // INDEPENDENTLY RE-VERIFIED ON THE STARWAVE ACCOUNT (magic 26011001,
      // XAUUSD.u, 2026-08-21..28), all 1,311 attested SL closures, offset of the
      // fired level above entry in units of that cycle's step:
      //
      //   [0,1) 541 | [1.00,1.95) 19 | [1.95,2.00) 4 | >=2.0 746 | <0 1
      //
      // Quarter-step buckets: 158/131/137/114 below the wall, 4/8/6/6 inside it,
      // 155/107/110/87 above -- a 20-30x trough exactly where the two branches
      // forbid mass.  That confirms lock_trigger=2, pre_tighten=2,
      // tighten_trigger=3, trail_distance=1 on the Starwave data alone, without
      // reusing any Target measurement.
      //
      // The 23 in-band residuals are NOT a rule difference, and must not be
      // "fixed":
      //   * 3 of them (1.987, 1.994, 1.987) are one cent of step-inference error
      //     away from exactly 2.0 -- step is recovered as round(anchor/3000,2),
      //     so a 0.01 error moves a 2.000 ratio to 1.987.
      //   * the rest (1.12 .. 1.82) are the activation branch doing its job: it
      //     applies pre_tighten UNCONDITIONALLY, so a first poll that already
      //     finds favorable_steps in [3,4) writes entry + (favorable-2)*step,
      //     i.e. straight into the band.  The next poll ratchets it out again,
      //     so only positions hit within about one poll of activation are ever
      //     observed there -- 1.45% of closures here.  Starwave's activation
      //     overshoot is ~1.8x the Target's (below), which is why the Target
      //     shows 0 of 2,480 and Starwave shows 19 of 1,311.
      // The stops_level clamp is ruled out as the cause: an active clamp would
      // pin market-sl to a constant, and the >=2.0 mass is spread across
      // [2.0,4.75+) instead.
      //
      // THE ACTIVATION RULE ITSELF IS SETTLED BY THE SAME DATA.  The two
      // candidates in the ternary below predict different left edges:
      //   (false) entry + lock_offset_price -> a razor spike at exactly 0.20
      //           PRICE, and ZERO mass in (0,0.20).
      //   (true)  market - pre_tighten*step -> continuous mass from 0+, spread
      //           set by the poll overshoot, nothing special at 0.20.
      // Measured on Starwave: only 4 of 1,311 sit within +-0.005 of 0.20 price
      // (chance level -- neighbouring 0.01 buckets hold as many), while 79 sit
      // strictly inside (0.005,0.195), a region the false branch forbids
      // outright.  Dispersion is also tighter in step units than in price units
      // (CV 0.6051 vs 0.6057 on Starwave, whose steps only span 1.49-1.56;
      // 0.5375 vs 0.6875 on the 901018 cohort whose steps span 0.37-0.50+,
      // where the test has real power).  So activation_uses_trailing_distance is
      // TRUE for the target, and lock_offset_price is now dead code on EVERY
      // built-in profile: the ReportHistory-901018 tape settles the two eras
      // that used to inherit the false branch (DIV-4).  Scored with each cycle's
      // own step over all positions carrying an S/L, dir*(sl-open) lands
      // strictly inside (0,0.20) -- a region the false branch cannot reach,
      // since it writes 0.20 first and only ever improves -- for 351 of
      // HISTORICAL_50's 4,094 and 1,068 of HISTORICAL_60's 7,952, both with a
      // minimum of +0.01 and no atom at 0.20 (0.19/0.20/0.21 = 22/18/17 and
      // 47/57/55).  ProfileCatalog's ResetProfile therefore defaults the flag to
      // true, and the false branch below survives only as a CUSTOM_PROFILE
      // operator escape hatch.
      // Starwave activation overshoot, offsets under 0.5 step, n=289:
      // p10 +0.058 / p50 +0.226 / p90 +0.455 steps, and 0 at exact breakeven --
      // same strictly-positive polling signature as the Target, just slower.
      //
      // A single-stage 1.0-step trail is ruled out for the modern profiles by
      // the same locked-distance histogram: it would fill the (1.0,2.0) band,
      // and STARWAVE_30 puts 0 of 2,809 positions in [1.00,1.98).  The two ATR
      // profiles are the opposite case -- they inherit pre_tighten == trail ==
      // 2.0, which collapses the ternary into a single-stage 2.0-step trail, and
      // their bands are correspondingly smooth (23.23% and 23.04% in [1,2)).
      // ---------------------------------------------------------------------

      // Gate: no stop exists until price has moved favorably by
      // lock_trigger_steps (2.0 under LATEST_30 -- NOT 1.0; trail_distance_steps
      // is the 1.0, and it applies only after the tighten, in the else-branch
      // ternary below).
      if(favorable_steps<profile.lock_trigger_steps)
         return false;

      if(current_sl<=0.0 || (type==POSITION_TYPE_BUY ? current_sl<entry : current_sl>entry))
        {
         desired=(
            profile.activation_uses_trailing_distance
            ? market-direction*
              profile.pre_tighten_trail_distance_steps*step
            : entry+direction*profile.lock_offset_price
         );
        }
      else
        {
         double distance=(
            favorable_steps>=profile.tighten_trigger_steps
            ? profile.trail_distance_steps
            : profile.pre_tighten_trail_distance_steps
         );
         desired=market-direction*distance*step;
        }

      desired=NormalizeDouble(
         MathRound(desired/tick_size)*tick_size,
         digits
      );

      if(type==POSITION_TYPE_BUY)
        {
         desired=MathMin(desired,bid-minimum_distance);
         return (current_sl<=0.0 ? desired<bid : desired>current_sl);
        }
      else
        {
         desired=MathMax(desired,ask+minimum_distance);
         return (current_sl<=0.0 ? desired>ask : desired<current_sl);
        }
     }
  };

#endif


// ====================================================================
// SECTION: BasketEvaluator.mqh
// ====================================================================

#ifndef STRADDLE_BASKET_EVALUATOR_MQH
#define STRADDLE_BASKET_EVALUATOR_MQH

struct SBasketSnapshot
  {
   double realized;
   double floating;
   double net;
   double target;
   bool   triggered;
  };

class CBasketEvaluator
  {
public:
   SBasketSnapshot Evaluate(const double realized,
                            const double floating,
                            const double target,
                            const bool has_traded,
                            const int open_positions = 1) const
     {
      SBasketSnapshot snapshot={};
      snapshot.realized=realized;
      snapshot.floating=floating;
      snapshot.net=realized+floating;
      snapshot.target=target;
      snapshot.triggered=(
         (has_traded || open_positions > 0) &&
         open_positions > 0 &&
         target>0.0 &&
         snapshot.net>=target
      );
      return snapshot;
     }
  };

#endif


// ====================================================================
// SECTION: CycleDealLedger.mqh
// ====================================================================

#ifndef STRADDLE_CYCLE_DEAL_LEDGER_MQH
#define STRADDLE_CYCLE_DEAL_LEDGER_MQH

class CCycleDealLedger
  {
private:
   ulong  m_magic;
   string m_symbol;

public:
   void Configure(const ulong magic,const string symbol)
     {
      m_magic=magic;
      m_symbol=symbol;
     }

   bool TryRecalculate(const long cycle_started_msc,
                       double &total,
                       int &exit_deal_count) const
     {
      total=0.0;
      exit_deal_count=0;
      if(cycle_started_msc<=0)
         return false;
      datetime from=(datetime)(cycle_started_msc/1000);
      if(!HistorySelect(from,TimeCurrent()))
         return false;
      for(int index=0;index<HistoryDealsTotal();index++)
        {
         ulong ticket=HistoryDealGetTicket(index);
         if(ticket==0)
            continue;
         if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=m_magic ||
            HistoryDealGetString(ticket,DEAL_SYMBOL)!=m_symbol ||
            (long)HistoryDealGetInteger(ticket,DEAL_TIME_MSC)<
               cycle_started_msc)
            continue;
         ENUM_DEAL_ENTRY entry=
            (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY);
         if(entry!=DEAL_ENTRY_OUT &&
            entry!=DEAL_ENTRY_OUT_BY &&
            entry!=DEAL_ENTRY_INOUT)
            continue;
         exit_deal_count++;
         total+=HistoryDealGetDouble(ticket,DEAL_PROFIT)
               +HistoryDealGetDouble(ticket,DEAL_SWAP)
               +HistoryDealGetDouble(ticket,DEAL_COMMISSION)
               +HistoryDealGetDouble(ticket,DEAL_FEE);
        }
      return true;
     }

   double Recalculate(const long cycle_started_msc) const
     {
      double total=0.0;
      int exit_deal_count=0;
      if(!TryRecalculate(cycle_started_msc,total,exit_deal_count))
         return 0.0;
      return total;
     }
  };

#endif


// ====================================================================
// SECTION: TradeGateway.mqh
// ====================================================================

#ifndef STRADDLE_REPLICA_TRADE_GATEWAY_MQH
#define STRADDLE_REPLICA_TRADE_GATEWAY_MQH

class CTradeGateway
  {
private:
   string            m_symbol;
   ulong             m_magic;
   int               m_deviation_points;
   uint              m_last_retcode;
   ulong             m_last_order;
   ulong             m_last_deal;

   ENUM_ORDER_TYPE_FILLING MarketFillingMode(void) const
     {
      long filling=(long)SymbolInfoInteger(m_symbol,SYMBOL_FILLING_MODE);
      if((filling & SYMBOL_FILLING_FOK)==SYMBOL_FILLING_FOK)
         return ORDER_FILLING_FOK;
      if((filling & SYMBOL_FILLING_IOC)==SYMBOL_FILLING_IOC)
         return ORDER_FILLING_IOC;
      return ORDER_FILLING_RETURN;
     }

   // Pending orders are ALWAYS sent with ORDER_FILLING_RETURN, never with
   // MarketFillingMode().  This is measured, not stylistic.
   //
   // Cross-tab of Starwave_60542_orders_history.csv (10,863 orders, magic
   // 26011001) on comment x type x type_filling:
   //
   //   comment      type          type_filling             n
   //   STR B#/S#    4 BUY_STOP    2 RETURN              4257
   //   STR B#/S#    5 SELL_STOP   2 RETURN              4279
   //   STR CLOSE    0 BUY         0 FOK                  524
   //   STR CLOSE    1 SELL        0 FOK                  473
   //   [sl <price>] 0 BUY         1 IOC                  674
   //   [sl <price>] 1 SELL        1 IOC                  637
   //
   // All 8,536 Target pendings carry type_filling=2; not one carries 0 or 1.
   // The Target's own market closes carry 0 (FOK), which is what
   // MarketFillingMode() returns on a symbol advertising SYMBOL_FILLING_FOK --
   // so OpenMarket/ClosePosition keep using it and match.  IOC appears only on
   // broker-generated stop-out orders, which the EA does not author.
   //
   // MQL5 also specifies RETURN as the mode used for the four pending order
   // types regardless of SYMBOL_FILLING_MODE, so sending FOK on a
   // TRADE_ACTION_PENDING request is not merely a fingerprint divergence: on a
   // broker that does not advertise FOK for pendings it is retcode 10030
   // (Unsupported filling mode) and the lattice never deploys.
   ENUM_ORDER_TYPE_FILLING PendingFillingMode(void) const
     {
      return ORDER_FILLING_RETURN;
     }

   bool IsSuccessful(const MqlTradeResult &result) const
     {
      return(result.retcode==TRADE_RETCODE_DONE ||
             result.retcode==TRADE_RETCODE_PLACED ||
             result.retcode==TRADE_RETCODE_DONE_PARTIAL);
     }

   ulong FindMatchingPendingOrder(
      const MqlTradeRequest &request
   ) const
     {
      if(request.action!=TRADE_ACTION_PENDING)
         return 0;
      double tick_size=SymbolInfoDouble(
         request.symbol,
         SYMBOL_TRADE_TICK_SIZE
      );
      if(tick_size<=0.0)
         tick_size=SymbolInfoDouble(request.symbol,SYMBOL_POINT);
      double volume_step=SymbolInfoDouble(
         request.symbol,
         SYMBOL_VOLUME_STEP
      );
      if(volume_step<=0.0)
         volume_step=SymbolInfoDouble(request.symbol,SYMBOL_VOLUME_MIN);
      for(int index=OrdersTotal()-1;index>=0;index--)
        {
         ulong ticket=OrderGetTicket(index);
         if(ticket==0 ||
            (ulong)OrderGetInteger(ORDER_MAGIC)!=request.magic ||
            OrderGetString(ORDER_SYMBOL)!=request.symbol ||
            (ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE)!=request.type ||
            OrderGetString(ORDER_COMMENT)!=request.comment ||
            MathAbs(
               OrderGetDouble(ORDER_VOLUME_INITIAL)-request.volume
            )>volume_step/2.0 ||
            MathAbs(
               OrderGetDouble(ORDER_PRICE_OPEN)-request.price
            )>tick_size/2.0)
            continue;
         return ticket;
        }
      return 0;
     }

   bool ReconcileAcceptedPendingOrder(
      MqlTradeResult &result,
      const ulong matching_order,
      const int send_error
   )
     {
      if(matching_order==0)
         return false;
      result.retcode=TRADE_RETCODE_PLACED;
      result.order=matching_order;
      result.deal=0;
      m_last_retcode=result.retcode;
      m_last_order=matching_order;
      m_last_deal=0;
      PrintFormat(
         "[STR] OrderSend reconciled accepted pending order "
         "error=%d order=%I64u",
         send_error,
         matching_order
      );
      return true;
     }

   bool ReconcileAcceptedPositionClose(
      MqlTradeResult &result,
      const MqlTradeRequest &request,
      const double position_volume_before,
      const int send_error
   )
     {
      if(request.action!=TRADE_ACTION_DEAL ||
         request.position==0 ||
         position_volume_before<=0.0)
         return false;
      bool position_exists=PositionSelectByTicket(request.position);
      double position_volume_after=(
         position_exists
         ? PositionGetDouble(POSITION_VOLUME)
         : 0.0
      );
      double volume_step=SymbolInfoDouble(
         request.symbol,
         SYMBOL_VOLUME_STEP
      );
      if(volume_step<=0.0)
         volume_step=SymbolInfoDouble(
            request.symbol,
            SYMBOL_VOLUME_MIN
         );
      if(position_exists &&
         position_volume_after>=position_volume_before-volume_step/2.0)
         return false;
      result.retcode=(
         position_exists
         ? TRADE_RETCODE_DONE_PARTIAL
         : TRADE_RETCODE_DONE
      );
      result.order=0;
      result.deal=0;
      m_last_retcode=result.retcode;
      m_last_order=0;
      m_last_deal=0;
      PrintFormat(
         "[STR] OrderSend reconciled accepted position close "
         "error=%d position=%I64u before=%.8f after=%.8f",
         send_error,
         request.position,
         position_volume_before,
         position_volume_after
      );
      return true;
     }

   bool Send(MqlTradeRequest &request,MqlTradeResult &result,const bool check_request)
     {
      m_last_retcode=0;
      m_last_order=0;
      m_last_deal=0;
      double position_volume_before=0.0;
      if(request.action==TRADE_ACTION_DEAL &&
         request.position>0 &&
         PositionSelectByTicket(request.position))
         position_volume_before=PositionGetDouble(POSITION_VOLUME);
      ulong matching_order=FindMatchingPendingOrder(request);
      if(ReconcileAcceptedPendingOrder(result,matching_order,0))
         return true;
      if(check_request)
        {
         MqlTradeCheckResult check={};
         if(!OrderCheck(request,check))
           {
            m_last_retcode=check.retcode;
            PrintFormat("[STR] OrderCheck failed retcode=%u comment=%s",check.retcode,check.comment);
            return false;
           }
        }
      ResetLastError();
      if(!OrderSend(request,result))
        {
         int send_error=GetLastError();
         for(int attempt=0;attempt<3 && matching_order==0;attempt++)
           {
            if(attempt>0)
               Sleep(25);
            matching_order=FindMatchingPendingOrder(request);
           }
         if(ReconcileAcceptedPendingOrder(
               result,
               matching_order,
               send_error
            ))
            return true;
         for(int attempt=0;attempt<3;attempt++)
           {
            if(attempt>0)
               Sleep(25);
            if(ReconcileAcceptedPositionClose(
                  result,
                  request,
                  position_volume_before,
                  send_error
               ))
               return true;
           }
         m_last_retcode=result.retcode;
         PrintFormat("[STR] OrderSend failed error=%d retcode=%u comment=%s",
                     send_error,result.retcode,result.comment);
         return false;
        }
      m_last_retcode=result.retcode;
      m_last_order=result.order;
      m_last_deal=result.deal;
      if(!IsSuccessful(result))
        {
         PrintFormat("[STR] Trade request rejected retcode=%u comment=%s",result.retcode,result.comment);
         return false;
        }
      return true;
     }

public:
                     CTradeGateway(void)
     {
      m_symbol="";
      m_magic=0;
      m_deviation_points=50;
      m_last_retcode=0;
      m_last_order=0;
      m_last_deal=0;
     }

   void              Initialize(const string symbol,const ulong magic,const int deviation_points)
     {
      m_symbol=symbol;
      m_magic=magic;
      m_deviation_points=deviation_points;
     }

   double            NormalizePrice(const double value) const
     {
      double tick_size=SymbolInfoDouble(m_symbol,SYMBOL_TRADE_TICK_SIZE);
      int digits=(int)SymbolInfoInteger(m_symbol,SYMBOL_DIGITS);
      if(tick_size<=0.0)
         tick_size=SymbolInfoDouble(m_symbol,SYMBOL_POINT);
      return NormalizeDouble(MathRound(value/tick_size)*tick_size,digits);
     }

   double            NormalizeVolume(const double value) const
     {
      double minimum=SymbolInfoDouble(m_symbol,SYMBOL_VOLUME_MIN);
      double maximum=SymbolInfoDouble(m_symbol,SYMBOL_VOLUME_MAX);
      double step=SymbolInfoDouble(m_symbol,SYMBOL_VOLUME_STEP);
      if(step<=0.0)
         step=minimum;
      double normalized=MathRound(value/step)*step;
      normalized=MathMax(minimum,MathMin(maximum,normalized));
      return NormalizeDouble(normalized,8);
     }

   bool              PlaceStop(const bool is_buy,
                               const double volume,
                               const double price,
                               const string comment)
     {
      MqlTradeRequest request={};
      MqlTradeResult result={};
      request.action=TRADE_ACTION_PENDING;
      request.magic=m_magic;
      request.symbol=m_symbol;
      request.volume=NormalizeVolume(volume);
      request.price=NormalizePrice(price);
      request.sl=0.0;
      request.tp=0.0;
      request.deviation=m_deviation_points;
      request.type=(is_buy ? ORDER_TYPE_BUY_STOP : ORDER_TYPE_SELL_STOP);
      request.type_filling=PendingFillingMode();
      request.type_time=ORDER_TIME_GTC;
      request.comment=comment;
      return Send(request,result,true);
     }

   bool              ModifyPosition(const ulong position_ticket,const double stop_loss)
     {
      if(!PositionSelectByTicket(position_ticket))
         return false;
      MqlTradeRequest request={};
      MqlTradeResult result={};
      request.action=TRADE_ACTION_SLTP;
      request.magic=m_magic;
      request.symbol=PositionGetString(POSITION_SYMBOL);
      request.position = position_ticket;
      request.sl=NormalizePrice(stop_loss);
      request.tp=PositionGetDouble(POSITION_TP);
      return Send(request,result,false);
     }

   bool              OpenMarket(const bool is_buy,
                                const double volume,
                                const string comment)
     {
      MqlTick tick={};
      if(!SymbolInfoTick(m_symbol,tick))
         return false;
      MqlTradeRequest request={};
      MqlTradeResult result={};
      request.action=TRADE_ACTION_DEAL;
      request.magic=m_magic;
      request.symbol=m_symbol;
      request.volume=NormalizeVolume(volume);
      request.deviation=m_deviation_points;
      request.type_filling=MarketFillingMode();
      request.type=(is_buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL);
      request.price=(is_buy ? tick.ask : tick.bid);
      request.comment=comment;
      return Send(request,result,true);
     }

   bool              ClosePosition(const ulong position_ticket,const string comment)
     {
      if(!PositionSelectByTicket(position_ticket))
         return false;
      string symbol=PositionGetString(POSITION_SYMBOL);
      double volume=PositionGetDouble(POSITION_VOLUME);
      ENUM_POSITION_TYPE position_type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      MqlTick tick={};
      if(!SymbolInfoTick(symbol,tick))
         return false;

      MqlTradeRequest request={};
      MqlTradeResult result={};
      request.action=TRADE_ACTION_DEAL;
      request.magic=m_magic;
      request.symbol=symbol;
      request.position = position_ticket;
      request.volume=NormalizeVolume(volume);
      request.deviation=m_deviation_points;
      request.type_filling=MarketFillingMode();
      request.type=(position_type==POSITION_TYPE_BUY ? ORDER_TYPE_SELL : ORDER_TYPE_BUY);
      request.price=(request.type==ORDER_TYPE_BUY ? tick.ask : tick.bid);
      request.comment=comment;
      return Send(request,result,true);
     }

   bool              DeleteOrder(const ulong order_ticket)
     {
      if(!OrderSelect(order_ticket))
         return false;
      MqlTradeRequest request={};
      MqlTradeResult result={};
      request.action=TRADE_ACTION_REMOVE;
      request.magic=m_magic;
      request.symbol=OrderGetString(ORDER_SYMBOL);
      request.order=order_ticket;
      return Send(request,result,false);
     }

   uint              LastRetcode(void) const { return m_last_retcode; }
   ulong             LastOrder(void) const { return m_last_order; }
   ulong             LastDeal(void) const { return m_last_deal; }
  };

#endif


// ====================================================================
// SECTION: StraddleEngine.mqh
// ====================================================================

#ifndef STRADDLE_REPLICA_ENGINE_MQH
#define STRADDLE_REPLICA_ENGINE_MQH

// included inline
// included inline
// included inline
// included inline
// included inline
// included inline

#define STR_PENDING_DEAL_CAPACITY 256
#define STR_DEAL_METADATA_SETTLE_MS 5000
#define STR_HISTORY_RECONCILE_INTERVAL_MS 1000
#define STR_HISTORY_RECONCILE_LOOKBACK_MS 900000

class CStraddleEngine
  {
private:
   SRuntimeConfig    m_runtime;
   SProfileConfig    m_profile;
   CTradeGateway     m_gateway;
   CCycleDealLedger  m_deal_ledger;
   CBasketEvaluator m_basket_evaluator;
   CStopScheduler m_stop_scheduler;
   ENUM_CYCLE_STATE m_state;
   SLevelState       m_buy_levels[STR_MAX_LEVELS];
   SLevelState       m_sell_levels[STR_MAX_LEVELS];
   double            m_anchor;
   double            m_step;
   double            m_tick_size;
   double            m_point;
   double            m_cycle_start_balance;
   double            m_cycle_realized;
   int               m_cycle_exit_deal_count;
   datetime          m_cycle_started_at;
   datetime          m_cycle_started_utc;
   long              m_cycle_started_msc;
   ulong             m_cycle_started_ms;
   datetime          m_restart_started_at;
   datetime          m_last_close_at;
   // How many owned positions TryCloseOneOwnedPosition() steps over before it
   // makes its single close attempt.  This exists so that ONE close request per
   // tick and "a stalled ticket must not block the basket" can both hold at
   // once; see the comment on TryCloseOneOwnedPosition for why that mattered.
   int               m_close_skip;
   datetime          m_last_entry_fill_at;
   datetime          m_last_stop_update_at;
   int               m_deploy_index;
   bool              m_has_traded;
   bool              m_halted;
   // Which guard set m_halted, carried forward so the TERMINAL "halted" event can
   // name it.  BeginClose() logs the reason on "close_begin", but it is also called
   // for every ordinary $30 basket exit, so the log holds hundreds of close_begin
   // lines and only one of them is fatal -- and the flatten sweep in between takes
   // one position per timer tick, so the two lines can be far apart.  Without this,
   // an operator finding the EA parked in CYCLE_HALTED cannot tell WHICH limit
   // killed it.  Kept in lockstep with m_halted at the single assignment site.
   string            m_halt_reason;
   string            m_telemetry_file;
   int               m_atr_handle;
   string            m_cycle_id;
   ulong             m_shadow_last_command_seq;
   ulong             m_event_sequence;
   ulong             m_last_processed_deal_ticket;
   ulong             m_processed_deal_tickets[];
   int               m_processed_deal_count;
   ulong             m_pending_deal_tickets[STR_PENDING_DEAL_CAPACITY];
   int               m_pending_deal_count;
   ulong             m_last_history_reconcile_ms;
   bool              m_history_reconcile_seeded;
   bool              m_shadow_reset_active;
   int               m_trend_rescue_side;
   bool              m_trend_rescue_replacing;
   ulong             m_trend_rescue_mask;
   ulong             m_buy_trend_rescue_latched_mask;
   ulong             m_sell_trend_rescue_latched_mask;
   ulong             m_buy_trend_rescue_rearm_mask;
   ulong             m_sell_trend_rescue_rearm_mask;
   int               m_trend_rescue_consumed_side;
   bool              m_alignment_hold_logged;
   // Target EA parity (SProfileConfig.replica_orphan_leak): position tickets that
   // were DISPLACED from the level table by a later fill on the same
   // (side,level).  The Target's level table holds one ulong per level, so a
   // re-fill overwrites the pointer and the older position becomes invisible to
   // the EA forever: not trailed, not counted in the basket, never swept.  We
   // reproduce that by remembering the displaced tickets and excluding them from
   // every cycle-scoped operation.  Entries are pruned once the ticket is no
   // longer live (a broker/manual close), and MT5 tickets never recycle, so the
   // list is bounded by the number of positions the operator leaves open.
   ulong             m_orphan_tickets[];
   int               m_orphan_count;

   string GlobalKey(const string suffix) const
     {
      return StringFormat("STR_%I64u_%s_%s",m_runtime.magic,m_runtime.symbol,suffix);
     }

   string AlignmentHoldFileName(void) const
     {
      return StringFormat(
         "StraddleAlignmentHold_%I64u_%I64u_%s.json",
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
         m_runtime.magic,
         m_runtime.symbol
      );
     }

   bool AlignmentHoldActive(void) const
     {
      return FileIsExist(AlignmentHoldFileName(),FILE_COMMON);
     }

   string CycleIdFromUtc(const string prefix,
                         const datetime cycle_started_utc) const
      {
       MqlDateTime utc={};
       TimeToStruct(cycle_started_utc,utc);
       return StringFormat(
          "%s-%I64u-%04d%02d%02dT%02d%02d%02dZ",
         prefix,
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
         utc.year,utc.mon,utc.day,utc.hour,utc.min,utc.sec
       );
      }

   string NewCycleId(const string prefix) const
      {
       return CycleIdFromUtc(prefix,TimeGMT());
      }

   ulong NextEventSequence(void)
      {
       m_event_sequence++;
       GlobalVariableSet(GlobalKey("event_seq"),(double)m_event_sequence);
       GlobalVariablesFlush();
       return m_event_sequence;
      }

   string EventId(const string kind,
                  const ulong sequence,
                  const ulong deal_ticket) const
     {
      if(deal_ticket>0)
         return StringFormat(
            "%s:deal:%I64u:%s",
            m_cycle_id,deal_ticket,kind
         );
      return StringFormat("%s:event:%I64u",m_cycle_id,sequence);
     }

   double NormalizePrice(const double value) const
     {
      return m_gateway.NormalizePrice(value);
     }

   ulong TrendRescueBit(const int index) const
     {
      return((ulong)1<<index);
     }

   bool TrendRescuePositionRearmPending(const bool is_buy,
                                        const int index) const
     {
      ulong bit=TrendRescueBit(index);
      return(
         is_buy
         ? (m_buy_trend_rescue_rearm_mask & bit)!=0
         : (m_sell_trend_rescue_rearm_mask & bit)!=0
      );
     }

   void MarkTrendRescuePositionRearms(const bool is_buy)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         if(is_buy && m_buy_levels[index].has_position)
            m_buy_trend_rescue_rearm_mask|=TrendRescueBit(index);
         else if(!is_buy && m_sell_levels[index].has_position)
            m_sell_trend_rescue_rearm_mask|=TrendRescueBit(index);
        }
     }

   void ClearTrendRescuePositionRearm(const bool is_buy,
                                      const int index)
     {
      if(is_buy)
         m_buy_trend_rescue_rearm_mask&=~TrendRescueBit(index);
      else
         m_sell_trend_rescue_rearm_mask&=~TrendRescueBit(index);
     }

   double CalculateStep(const double anchor)
     {
      if(m_profile.step_mode==STR_STEP_ANCHOR_DIVISOR)
         return NormalizePrice(anchor/m_profile.anchor_divisor);
      if(m_profile.step_mode==STR_STEP_ATR)
        {
         if(m_atr_handle==INVALID_HANDLE || BarsCalculated(m_atr_handle)<m_profile.atr_period)
            return 0.0;
         double atr_value[1];
         if(CopyBuffer(m_atr_handle,0,0,1,atr_value)!=1 || atr_value[0]<=0.0)
            return 0.0;
         return NormalizePrice(atr_value[0]*m_profile.atr_multiplier);
        }
      return NormalizePrice(m_profile.fixed_step);
     }

   void ResetLevelState(void)
     {
      m_trend_rescue_side=0;
      m_trend_rescue_replacing=false;
      m_trend_rescue_mask=0;
      m_buy_trend_rescue_latched_mask=0;
      m_sell_trend_rescue_latched_mask=0;
      m_buy_trend_rescue_rearm_mask=0;
      m_sell_trend_rescue_rearm_mask=0;
      m_trend_rescue_consumed_side=0;
      for(int index=0;index<STR_MAX_LEVELS;index++)
        {
         m_buy_levels[index].is_buy=true;
         m_buy_levels[index].level=index+1;
         m_buy_levels[index].target_price=0.0;
         m_buy_levels[index].volume=0.0;
         m_buy_levels[index].has_pending=false;
         m_buy_levels[index].has_position=false;
         m_buy_levels[index].active_order_count=0;
         m_buy_levels[index].active_position_count=0;
         m_buy_levels[index].duplicate_identity=false;
         m_buy_levels[index].recovery_done=false;
         m_buy_levels[index].deploy_deferred=false;
          m_buy_levels[index].order_ticket=0;
          m_buy_levels[index].position_ticket=0;
            m_buy_levels[index].rearm_requested=false;
            m_buy_levels[index].rearm_after_msc=0;
            m_buy_levels[index].trend_rescue_replacement=false;
            m_buy_levels[index].trend_rescue_latched=false;

         m_sell_levels[index].is_buy=false;
         m_sell_levels[index].level=index+1;
         m_sell_levels[index].target_price=0.0;
         m_sell_levels[index].volume=0.0;
         m_sell_levels[index].has_pending=false;
         m_sell_levels[index].has_position=false;
         m_sell_levels[index].active_order_count=0;
         m_sell_levels[index].active_position_count=0;
         m_sell_levels[index].duplicate_identity=false;
         m_sell_levels[index].recovery_done=false;
         m_sell_levels[index].deploy_deferred=false;
          m_sell_levels[index].order_ticket=0;
          m_sell_levels[index].position_ticket=0;
            m_sell_levels[index].rearm_requested=false;
            m_sell_levels[index].rearm_after_msc=0;
            m_sell_levels[index].trend_rescue_replacement=false;
            m_sell_levels[index].trend_rescue_latched=false;
        }
     }

   void InitializeLevelTargets(void)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         int level=index+1;
         m_buy_levels[index].target_price=NormalizePrice(m_anchor+level*m_step);
         m_buy_levels[index].volume=m_profile.lots[index];
         m_sell_levels[index].target_price=NormalizePrice(m_anchor-level*m_step);
         m_sell_levels[index].volume=m_profile.lots[index];
        }
     }

   bool ParseLevelComment(const string comment,bool &is_buy,int &index) const
     {
      if(StringFind(comment,"STR B")==0)
         is_buy=true;
      else if(StringFind(comment,"STR S")==0)
         is_buy=false;
      else
         return false;
      int level=(int)StringToInteger(StringSubstr(comment,5));
      if(level<1 || level>m_profile.levels_per_side)
         return false;
      index=level-1;
      return true;
     }

   string PositionCommentFromDeal(const ulong deal_ticket) const
     {
      ulong position_id=(ulong)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID);
      if(position_id==0 || !HistoryOrderSelect(position_id))
         return "";
      return HistoryOrderGetString(position_id,ORDER_COMMENT);
     }

   bool IsOwnedOrderSelected(void) const
     {
      return((ulong)OrderGetInteger(ORDER_MAGIC)==m_runtime.magic &&
             OrderGetString(ORDER_SYMBOL)==m_runtime.symbol);
     }

   bool IsOwnedPositionSelected(void) const
     {
      return((ulong)PositionGetInteger(POSITION_MAGIC)==m_runtime.magic &&
             PositionGetString(POSITION_SYMBOL)==m_runtime.symbol);
     }

   bool OrphanLeakActive(void) const
     {
      return(m_profile.replica_orphan_leak);
     }

   string LevelCommentOf(const SLevelState &level_state) const
     {
      return StringFormat(
         "STR %s%d",
         (level_state.is_buy ? "B" : "S"),
         level_state.level
      );
     }

   void ResetOrphanTickets(void)
     {
      m_orphan_count=0;
      ArrayResize(m_orphan_tickets,0);
     }

   bool IsOrphanTicket(const ulong ticket) const
     {
      for(int index=0;index<m_orphan_count;index++)
        {
         if(m_orphan_tickets[index]==ticket)
            return true;
        }
      return false;
     }

   void RememberOrphanTicket(const ulong ticket,const string level_comment,
                             const string reason="displaced_by_refill")
     {
      if(ticket==0 || IsOrphanTicket(ticket))
         return;
      ArrayResize(m_orphan_tickets,m_orphan_count+1);
      m_orphan_tickets[m_orphan_count]=ticket;
      m_orphan_count++;
      LogLifecycleEvent("position_orphaned",level_comment,reason);
     }

   // Drops tickets that are no longer live.  MT5 never recycles a ticket, so a
   // pruned entry can never be re-adopted by mistake.  Must not be called from
   // inside a PositionGetTicket() walk: it moves the selected position.
   void PruneClosedOrphanTickets(void)
     {
      int kept=0;
      for(int index=0;index<m_orphan_count;index++)
        {
         if(!PositionSelectByTicket(m_orphan_tickets[index]))
            continue;
         m_orphan_tickets[kept]=m_orphan_tickets[index];
         kept++;
        }
      if(kept==m_orphan_count)
         return;
      m_orphan_count=kept;
      ArrayResize(m_orphan_tickets,m_orphan_count);
     }

   // The set of positions the LEVEL TABLE still points at, ascending by ticket.
   // This is the Target EA's entire notion of "my open positions": one ticket
   // per (side,level), anything displaced is gone.  Sorted ascending so callers
   // can walk it forwards (oldest first) or reversed (newest first) and get an
   // exact ticket-ordered LIFO sweep.
   int CollectTrackedPositionTickets(ulong &tickets[]) const
     {
      ArrayResize(tickets,0);
      int count=0;
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         for(int side=0;side<2;side++)
           {
            bool has_position=(side==0
                               ? m_buy_levels[index].has_position
                               : m_sell_levels[index].has_position);
            ulong ticket=(side==0
                          ? m_buy_levels[index].position_ticket
                          : m_sell_levels[index].position_ticket);
            if(!has_position || ticket==0)
               continue;
            if(!PositionSelectByTicket(ticket) || !IsOwnedPositionSelected())
               continue;
            ArrayResize(tickets,count+1);
            tickets[count]=ticket;
            count++;
           }
        }
      if(count>1)
         ArraySort(tickets);
      return count;
     }

   int TrackedPositionCount(void) const
     {
      ulong tickets[];
      return CollectTrackedPositionTickets(tickets);
     }

   double TrackedFloatingProfit(void) const
     {
      ulong tickets[];
      int count=CollectTrackedPositionTickets(tickets);
      double total=0.0;
      for(int index=0;index<count;index++)
        {
         if(!PositionSelectByTicket(tickets[index]))
            continue;
         total+=(
            PositionGetDouble(POSITION_PROFIT)+
            PositionGetDouble(POSITION_SWAP)
         );
        }
      return total;
     }

   // Cycle-scoped accounting.  Identical to the Owned* pair when the leak is
   // off; restricted to the tracked set when it is on, which is what makes the
   // basket, the sweep and the restart drain all measure exactly what the
   // Target's level table measures.
   int CyclePositionCount(void) const
     {
      if(!OrphanLeakActive())
         return OwnedPositionCount();
      return TrackedPositionCount();
     }

   double CycleFloatingProfit(void) const
     {
      if(!OrphanLeakActive())
         return OwnedFloatingProfit();
      return TrackedFloatingProfit();
     }

   // Called immediately before the level table is wiped for a new cycle.  Any
   // ticket the table still points at would otherwise be silently released and
   // re-adopted by the next reconcile, which the tape rules out: all 153 of the
   // Target's orphans stayed untracked to the end of the window, none of them
   // ever received an [sl] order and none were swept by any of the 146 later
   // baskets.  In the normal path StartCycle()'s guard has already established
   // that nothing is tracked, so this is a no-op; it exists to make the
   // invariant hold on the edge paths too.
   void OrphanRemainingTrackedPositions(void)
     {
      if(!OrphanLeakActive())
         return;
      ulong tickets[];
      int count=CollectTrackedPositionTickets(tickets);
      for(int index=0;index<count;index++)
        {
         string level_comment="";
         if(PositionSelectByTicket(tickets[index]))
            level_comment=PositionGetString(POSITION_COMMENT);
         RememberOrphanTicket(tickets[index],level_comment,"cycle_reset");
        }
     }

   void ClearLiveFlags(void)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         m_buy_levels[index].has_pending=false;
         m_buy_levels[index].has_position=false;
         m_buy_levels[index].active_order_count=0;
         m_buy_levels[index].active_position_count=0;
         m_buy_levels[index].order_ticket=0;
         m_buy_levels[index].position_ticket=0;
         m_sell_levels[index].has_pending=false;
         m_sell_levels[index].has_position=false;
         m_sell_levels[index].active_order_count=0;
         m_sell_levels[index].active_position_count=0;
         m_sell_levels[index].order_ticket=0;
         m_sell_levels[index].position_ticket=0;
        }
     }

   void DetectDuplicateLevelIdentity(SLevelState &level_state)
     {
      int entity_count=
         level_state.active_order_count+
         level_state.active_position_count;
      // Target EA parity: with the orphan leak on, one pending plus one open
      // position on the SAME level is the normal steady state -- the level
      // re-arms at its original price while the displaced position is still
      // open.  Summing the two would flag that as a duplicate identity and
      // PlaceLevel() would then refuse the level for the rest of the cycle, so
      // score the two entity kinds independently instead.
      if(OrphanLeakActive())
         entity_count=MathMax(
            level_state.active_order_count,
            level_state.active_position_count
         );
      if(level_state.active_order_count==1 &&
         level_state.active_position_count==1 &&
         level_state.order_ticket>0 &&
         level_state.order_ticket==level_state.position_ticket)
         entity_count=1;
      bool duplicate=(entity_count>1);
      if(duplicate && !level_state.duplicate_identity)
         LogLifecycleEvent(
            "duplicate_level_identity",
            LevelCommentOf(level_state),
            "multiple_active_entities"
         );
      level_state.duplicate_identity=duplicate;
     }

   // Adopts the currently selected position into its level.  With the leak on the
   // level keeps exactly ONE ticket -- whichever opened LATER, i.e. the higher
   // ticket -- and the loser is orphaned for good, which is precisely what the
   // Target's single-pointer level table does when a level re-fills while its
   // previous position is still open.  active_position_count is therefore never
   // incremented past 1 in leak mode.
   void AdoptPositionIntoLevel(SLevelState &level_state,const ulong ticket)
     {
      // Read every property of the SELECTED position before anything that can
      // move the selection.  RememberOrphanTicket() writes telemetry, and
      // WriteTelemetry() calls CycleFloatingProfit(), which walks the book -- so
      // reading volume after it would report some other position's volume.
      double volume=PositionGetDouble(POSITION_VOLUME);
      if(OrphanLeakActive() &&
         level_state.has_position &&
         level_state.position_ticket!=ticket)
        {
         bool incoming_is_newer=(ticket>level_state.position_ticket);
         ulong displaced=(incoming_is_newer
                          ? level_state.position_ticket
                          : ticket);
         RememberOrphanTicket(displaced,LevelCommentOf(level_state));
         if(incoming_is_newer)
           {
            level_state.position_ticket=ticket;
            level_state.volume=volume;
           }
         return;
        }
      level_state.active_position_count++;
      level_state.has_position=true;
      level_state.position_ticket=ticket;
      level_state.volume=volume;
     }

   void ReconcileLevels(const bool report_duplicates=true)
     {
      if(OrphanLeakActive())
         PruneClosedOrphanTickets();
      ClearLiveFlags();
      for(int order_index=0;order_index<OrdersTotal();order_index++)
        {
         ulong ticket=OrderGetTicket(order_index);
         if(ticket==0 || !IsOwnedOrderSelected())
            continue;
          bool is_buy=false;
          int index=-1;
          if(!ParseLevelComment(OrderGetString(ORDER_COMMENT),is_buy,index))
             continue;
          double order_price=OrderGetDouble(ORDER_PRICE_OPEN);
          if(m_step>0.0)
            {
             double target_p=(is_buy ? m_buy_levels[index].target_price : m_sell_levels[index].target_price);
             if(target_p>0.0 && MathAbs(order_price-target_p)>0.50*m_step)
               {
                string comment=OrderGetString(ORDER_COMMENT);
                double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
                m_gateway.DeleteOrder(ticket);
                LogEvent("cancel",comment,ticket,volume,order_price,"zombie_purge");
                continue;
               }
            }
          if(is_buy)
            {
             m_buy_levels[index].active_order_count++;
             m_buy_levels[index].has_pending=true;
             m_buy_levels[index].order_ticket=ticket;
             m_buy_levels[index].volume=
                OrderGetDouble(ORDER_VOLUME_CURRENT);
            }
          else
            {
             m_sell_levels[index].active_order_count++;
             m_sell_levels[index].has_pending=true;
             m_sell_levels[index].order_ticket=ticket;
             m_sell_levels[index].volume=
                OrderGetDouble(ORDER_VOLUME_CURRENT);
            }
        }

      for(int position_index=0;position_index<PositionsTotal();position_index++)
        {
         ulong ticket=PositionGetTicket(position_index);
         if(ticket==0 || !IsOwnedPositionSelected())
            continue;
         if(OrphanLeakActive() && IsOrphanTicket(ticket))
            continue;
         bool is_buy=false;
         int index=-1;
         if(!ParseLevelComment(PositionGetString(POSITION_COMMENT),is_buy,index))
            continue;
          if(is_buy)
             AdoptPositionIntoLevel(m_buy_levels[index],ticket);
          else
             AdoptPositionIntoLevel(m_sell_levels[index],ticket);
        }
      if(report_duplicates)
        {
         for(int index=0;index<m_profile.levels_per_side;index++)
           {
            DetectDuplicateLevelIdentity(m_buy_levels[index]);
            DetectDuplicateLevelIdentity(m_sell_levels[index]);
           }
        }
     }

   void ArmMissingLevelsAfterRestore(void)
     {
      long rearm_after_msc=(
         CurrentServerMs()+
         (long)m_profile.rearm_delay_seconds*1000
      );
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
          if(!m_buy_levels[index].has_pending &&
             !m_buy_levels[index].has_position &&
             !m_buy_levels[index].trend_rescue_replacement)
           {
            m_buy_levels[index].rearm_requested=true;
            m_buy_levels[index].rearm_after_msc=rearm_after_msc;
           }
          if(!m_sell_levels[index].has_pending &&
             !m_sell_levels[index].has_position &&
             !m_sell_levels[index].trend_rescue_replacement)
           {
            m_sell_levels[index].rearm_requested=true;
            m_sell_levels[index].rearm_after_msc=rearm_after_msc;
           }
        }
     }

   void ResetProcessedDeals(void)
     {
      m_processed_deal_count=0;
      ArrayResize(m_processed_deal_tickets,0);
      m_last_processed_deal_ticket=0;
     }

   bool DealAlreadyProcessed(const ulong deal_ticket) const
     {
      if(deal_ticket==0)
         return true;
      for(int index=0;index<m_processed_deal_count;index++)
         if(m_processed_deal_tickets[index]==deal_ticket)
            return true;
      return false;
     }

   void RememberProcessedDeal(const ulong deal_ticket,
                              const bool persist=true)
     {
      if(deal_ticket==0 || DealAlreadyProcessed(deal_ticket))
         return;
      if(m_processed_deal_count>=ArraySize(m_processed_deal_tickets))
        {
         int resized=ArrayResize(
            m_processed_deal_tickets,
            m_processed_deal_count+128
         );
         if(resized<=m_processed_deal_count)
           {
            PrintFormat(
               "[STR] Processed-deal ledger resize failed; ticket=%I64u.",
               deal_ticket
            );
            return;
           }
        }
      m_processed_deal_tickets[m_processed_deal_count]=deal_ticket;
      m_processed_deal_count++;
      m_last_processed_deal_ticket=deal_ticket;
      if(persist)
        {
         GlobalVariableSet(
            GlobalKey("last_deal"),
            (double)m_last_processed_deal_ticket
         );
         GlobalVariablesFlush();
        }
     }

   void LoadProcessedDealsFromTelemetry(void)
     {
      ulong persisted_last=m_last_processed_deal_ticket;
      m_processed_deal_count=0;
      ArrayResize(m_processed_deal_tickets,0);
      if(m_cycle_id=="" || m_telemetry_file=="")
        {
         RememberProcessedDeal(persisted_last,false);
         return;
        }
      int handle=FileOpen(
         m_telemetry_file,
         FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|
         FILE_COMMON,
         ','
      );
      if(handle==INVALID_HANDLE)
        {
         RememberProcessedDeal(persisted_last,false);
         return;
        }
      while(!FileIsEnding(handle))
        {
         string fields[64];
         int field_count=0;
         while(field_count<64 && !FileIsEnding(handle))
           {
            fields[field_count]=FileReadString(handle);
            field_count++;
            if(FileIsLineEnding(handle))
               break;
           }
         while(!FileIsEnding(handle) && !FileIsLineEnding(handle))
            FileReadString(handle);
         if(field_count<=22)
            continue;
         if(fields[2]!=m_cycle_id)
            continue;
         ulong deal_ticket=(ulong)StringToInteger(fields[22]);
         RememberProcessedDeal(deal_ticket,false);
        }
      FileClose(handle);
      if(m_processed_deal_count==0)
         RememberProcessedDeal(persisted_last,false);
     }

   datetime RestartStartedAtFromTelemetry(void) const
     {
      if(m_cycle_id=="" || m_telemetry_file=="")
         return 0;
      int handle=FileOpen(
         m_telemetry_file,
         FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|
         FILE_COMMON,
         ','
      );
      if(handle==INVALID_HANDLE)
         return 0;
      datetime latest_restart_started_at=0;
      while(!FileIsEnding(handle))
        {
         string fields[64];
         int field_count=0;
         while(field_count<64 && !FileIsEnding(handle))
           {
            fields[field_count]=FileReadString(handle);
            field_count++;
            if(FileIsLineEnding(handle))
               break;
           }
         while(!FileIsEnding(handle) && !FileIsLineEnding(handle))
            FileReadString(handle);
         if(field_count<=4)
            continue;
         if(fields[2]!=m_cycle_id)
            continue;
         if(fields[4]!="cycle_complete")
            continue;
         datetime completed_at=StringToTime(fields[1]);
         if(completed_at>latest_restart_started_at)
            latest_restart_started_at=completed_at;
        }
      FileClose(handle);
      return latest_restart_started_at;
     }

   int OwnedOrderCount(void) const
     {
      int count=0;
      for(int index=0;index<OrdersTotal();index++)
        {
         if(OrderGetTicket(index)>0 && IsOwnedOrderSelected())
            count++;
        }
      return count;
     }

   int OwnedPositionCount(void) const
     {
      int count=0;
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)>0 && IsOwnedPositionSelected())
            count++;
        }
      return count;
     }

   bool FindReference(bool &is_buy,int &level,double &price) const
     {
      for(int index=0;index<OrdersTotal();index++)
        {
         if(OrderGetTicket(index)==0 || !IsOwnedOrderSelected())
            continue;
         int level_index=-1;
         if(ParseLevelComment(OrderGetString(ORDER_COMMENT),is_buy,level_index))
           {
            level=level_index+1;
            price=OrderGetDouble(ORDER_PRICE_OPEN);
            return true;
           }
        }
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)==0 || !IsOwnedPositionSelected())
            continue;
         int level_index=-1;
         if(ParseLevelComment(PositionGetString(POSITION_COMMENT),is_buy,level_index))
           {
            level=level_index+1;
            price=PositionGetDouble(POSITION_PRICE_OPEN);
            return true;
           }
        }
      return false;
     }

   bool RestoreCycle(void)
     {
      ENUM_CYCLE_STATE saved_state=CYCLE_RUNNING;
      if(GlobalVariableCheck(GlobalKey("state")))
         saved_state=(ENUM_CYCLE_STATE)(int)GlobalVariableGet(GlobalKey("state"));
      datetime persisted_restart_started_at=0;
      if(GlobalVariableCheck(GlobalKey("restart_started_at")))
         persisted_restart_started_at=(datetime)(long)GlobalVariableGet(
            GlobalKey("restart_started_at")
         );
      bool flat_restart=(
         OwnedOrderCount()==0 &&
         OwnedPositionCount()==0 &&
         saved_state==CYCLE_RESTARTING
      );
      if(OwnedOrderCount()==0 &&
         OwnedPositionCount()==0 &&
         !flat_restart)
         return false;

      bool restored=false;
      string anchor_key=GlobalKey("anchor");
      string step_key=GlobalKey("step");
      if(GlobalVariableCheck(anchor_key) && GlobalVariableCheck(step_key))
        {
         m_anchor=GlobalVariableGet(anchor_key);
         m_step=GlobalVariableGet(step_key);
         restored=(m_anchor>0.0 && m_step>0.0);
        }

      if(!restored)
        {
         bool is_buy=false;
         int level=0;
         double price=0.0;
         if(!FindReference(is_buy,level,price))
            return false;
         if(m_profile.step_mode==STR_STEP_ANCHOR_DIVISOR)
           {
            double factor=(is_buy ? 1.0+level/m_profile.anchor_divisor
                                  : 1.0-level/m_profile.anchor_divisor);
            m_anchor=NormalizePrice(price/factor);
           }
         else if(m_profile.step_mode==STR_STEP_ATR)
           {
            m_step=CalculateStep(price);
            if(m_step<=0.0)
               return false;
            m_anchor=NormalizePrice(is_buy ? price-level*m_step
                                          : price+level*m_step);
           }
         else
            m_anchor=NormalizePrice(is_buy ? price-level*m_profile.fixed_step
                                          : price+level*m_profile.fixed_step);
         if(m_profile.step_mode!=STR_STEP_ATR)
            m_step=CalculateStep(m_anchor);
        }

      m_cycle_start_balance=(GlobalVariableCheck(GlobalKey("balance"))
                             ? GlobalVariableGet(GlobalKey("balance"))
                             : AccountInfoDouble(ACCOUNT_BALANCE));
      m_cycle_started_msc=(
         GlobalVariableCheck(GlobalKey("start_msc"))
         ? (long)GlobalVariableGet(GlobalKey("start_msc"))
         : (long)TimeCurrent()*1000
      );
      m_cycle_started_at=(datetime)(m_cycle_started_msc/1000);
      m_cycle_started_utc=(
         GlobalVariableCheck(GlobalKey("start_utc"))
         ? (datetime)(long)GlobalVariableGet(GlobalKey("start_utc"))
         : 0
      );
      if(m_cycle_started_utc<=0)
        {
         long server_offset=(
            (long)TimeCurrent()-(long)TimeGMT()
         );
         m_cycle_started_utc=(
            datetime
         )((long)m_cycle_started_at-server_offset);
        }
      if(m_runtime.runtime_mode==STR_RUNTIME_NORMAL &&
         m_cycle_id=="")
         m_cycle_id=CycleIdFromUtc("local",m_cycle_started_utc);
      if(flat_restart && persisted_restart_started_at<=0)
         persisted_restart_started_at=RestartStartedAtFromTelemetry();
      m_cycle_started_ms=GetTickCount64();
      m_event_sequence=(
         GlobalVariableCheck(GlobalKey("event_seq"))
         ? (ulong)GlobalVariableGet(GlobalKey("event_seq"))
         : 0
      );
      m_last_processed_deal_ticket=(
         GlobalVariableCheck(GlobalKey("last_deal"))
         ? (ulong)GlobalVariableGet(GlobalKey("last_deal"))
         : 0
      );
      LoadProcessedDealsFromTelemetry();
      double persisted_realized=(
         GlobalVariableCheck(GlobalKey("realized"))
         ? GlobalVariableGet(GlobalKey("realized"))
         : 0.0
      );
      int persisted_realized_count=(
         GlobalVariableCheck(GlobalKey("realized_count"))
         ? (int)GlobalVariableGet(GlobalKey("realized_count"))
         : 0
      );
      double recalculated_realized=0.0;
      int recalculated_count=0;
      if(m_deal_ledger.TryRecalculate(
            m_cycle_started_msc,
            recalculated_realized,
            recalculated_count
         ) &&
         recalculated_count>=persisted_realized_count)
        {
         m_cycle_realized=recalculated_realized;
         m_cycle_exit_deal_count=recalculated_count;
        }
      else
        {
         m_cycle_realized=persisted_realized;
         m_cycle_exit_deal_count=persisted_realized_count;
        }
      m_last_stop_update_at=0;
      m_last_entry_fill_at=(
         GlobalVariableCheck(GlobalKey("last_entry_fill_at"))
         ? (datetime)(long)GlobalVariableGet(
            GlobalKey("last_entry_fill_at")
         )
         : 0
      );
      m_trend_rescue_side=(
         GlobalVariableCheck(GlobalKey("trend_rescue_side"))
         ? (int)GlobalVariableGet(GlobalKey("trend_rescue_side"))
         : 0
      );
      m_trend_rescue_replacing=(
         GlobalVariableCheck(GlobalKey("trend_rescue_replacing"))
         ? GlobalVariableGet(GlobalKey("trend_rescue_replacing"))>0.5
         : false
      );
      m_trend_rescue_mask=(
         GlobalVariableCheck(GlobalKey("trend_rescue_mask"))
         ? (ulong)GlobalVariableGet(GlobalKey("trend_rescue_mask"))
         : 0
      );
      m_buy_trend_rescue_latched_mask=(
         GlobalVariableCheck(GlobalKey("buy_trend_rescue_latched_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("buy_trend_rescue_latched_mask")
         )
         : 0
      );
      m_sell_trend_rescue_latched_mask=(
         GlobalVariableCheck(GlobalKey("sell_trend_rescue_latched_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("sell_trend_rescue_latched_mask")
         )
         : 0
      );
      m_buy_trend_rescue_rearm_mask=(
         GlobalVariableCheck(GlobalKey("buy_trend_rescue_rearm_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("buy_trend_rescue_rearm_mask")
         )
         : 0
      );
      m_sell_trend_rescue_rearm_mask=(
         GlobalVariableCheck(GlobalKey("sell_trend_rescue_rearm_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("sell_trend_rescue_rearm_mask")
         )
         : 0
      );
      m_trend_rescue_consumed_side=(
         GlobalVariableCheck(GlobalKey("trend_rescue_consumed_side"))
         ? (int)GlobalVariableGet(
            GlobalKey("trend_rescue_consumed_side")
         )
         : 0
      );
      m_has_traded=(
         OwnedPositionCount()>0 ||
         m_cycle_exit_deal_count>0
      );
      if(flat_restart)
        {
         m_state=CYCLE_RESTARTING;
         if(persisted_restart_started_at>0 &&
            persisted_restart_started_at<=TimeCurrent())
            m_restart_started_at=persisted_restart_started_at;
         else
            m_restart_started_at=TimeCurrent();
         PersistCycle();
         LogEvent("restore","",0,0.0,0.0,"flat_restart");
         return true;
        }
      InitializeLevelTargets();
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         m_buy_levels[index].trend_rescue_latched=(
            (m_buy_trend_rescue_latched_mask &
             TrendRescueBit(index))!=0
         );
         m_sell_levels[index].trend_rescue_latched=(
            (m_sell_trend_rescue_latched_mask &
             TrendRescueBit(index))!=0
         );
         bool replacement=(
            (m_trend_rescue_mask & TrendRescueBit(index))!=0
         );
         if(m_trend_rescue_side>0)
           {
            m_buy_levels[index].trend_rescue_replacement=replacement;
            if(replacement)
               m_buy_levels[index].volume=(
                  m_profile.lots[index]*
                  m_profile.trend_rescue_volume_multiplier
               );
           }
         else if(m_trend_rescue_side<0)
           {
            m_sell_levels[index].trend_rescue_replacement=replacement;
            if(replacement)
               m_sell_levels[index].volume=(
                  m_profile.lots[index]*
                  m_profile.trend_rescue_volume_multiplier
               );
           }
        }
      ReconcileLevels(false);
      ArmMissingLevelsAfterRestore();
      if(saved_state==CYCLE_CLOSING && CyclePositionCount()>0)
         m_state=CYCLE_CLOSING;
      else if((saved_state==CYCLE_CLOSING || saved_state==CYCLE_CANCELING) &&
              CyclePositionCount()==0 && OwnedOrderCount()>0)
         m_state=CYCLE_CANCELING;
      else
         m_state=CYCLE_RUNNING;
      ReconcileLevels();
      PersistCycle();
      LogEvent("restore","",0,0.0,0.0,"");
      return true;
     }

   void PersistCycle(void) const
     {
      GlobalVariableSet(GlobalKey("anchor"),m_anchor);
      GlobalVariableSet(GlobalKey("step"),m_step);
      GlobalVariableSet(GlobalKey("state"),(double)m_state);
      GlobalVariableSet(GlobalKey("balance"),m_cycle_start_balance);
      GlobalVariableSet(GlobalKey("realized"),m_cycle_realized);
      GlobalVariableSet(
         GlobalKey("realized_count"),
         (double)m_cycle_exit_deal_count
      );
      GlobalVariableSet(GlobalKey("start_msc"),(double)m_cycle_started_msc);
      GlobalVariableSet(
         GlobalKey("start_utc"),
         (double)m_cycle_started_utc
      );
      GlobalVariableSet(
         GlobalKey("restart_started_at"),
         (double)m_restart_started_at
      );
       GlobalVariableSet(
          GlobalKey("event_seq"),
          (double)m_event_sequence
       );
       GlobalVariableSet(
          GlobalKey("last_deal"),
          (double)m_last_processed_deal_ticket
       );
       GlobalVariableSet(
          GlobalKey("last_entry_fill_at"),
          (double)m_last_entry_fill_at
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_side"),
          (double)m_trend_rescue_side
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_replacing"),
          (double)(m_trend_rescue_replacing ? 1 : 0)
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_mask"),
          (double)m_trend_rescue_mask
       );
       GlobalVariableSet(
          GlobalKey("buy_trend_rescue_latched_mask"),
          (double)m_buy_trend_rescue_latched_mask
       );
       GlobalVariableSet(
          GlobalKey("sell_trend_rescue_latched_mask"),
          (double)m_sell_trend_rescue_latched_mask
       );
       GlobalVariableSet(
          GlobalKey("buy_trend_rescue_rearm_mask"),
          (double)m_buy_trend_rescue_rearm_mask
       );
       GlobalVariableSet(
          GlobalKey("sell_trend_rescue_rearm_mask"),
          (double)m_sell_trend_rescue_rearm_mask
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_consumed_side"),
          (double)m_trend_rescue_consumed_side
       );
       GlobalVariablesFlush();
      }

   void ClearPersistence(void) const
     {
      GlobalVariableDel(GlobalKey("anchor"));
      GlobalVariableDel(GlobalKey("step"));
      GlobalVariableDel(GlobalKey("state"));
      GlobalVariableDel(GlobalKey("balance"));
      GlobalVariableDel(GlobalKey("realized"));
      GlobalVariableDel(GlobalKey("realized_count"));
      GlobalVariableDel(GlobalKey("start_msc"));
       GlobalVariableDel(GlobalKey("start_utc"));
       GlobalVariableDel(GlobalKey("restart_started_at"));
       GlobalVariableDel(GlobalKey("event_seq"));
       GlobalVariableDel(GlobalKey("last_deal"));
       GlobalVariableDel(GlobalKey("last_entry_fill_at"));
       GlobalVariableDel(GlobalKey("trend_rescue_side"));
       GlobalVariableDel(GlobalKey("trend_rescue_replacing"));
       GlobalVariableDel(GlobalKey("trend_rescue_mask"));
       GlobalVariableDel(GlobalKey("buy_trend_rescue_latched_mask"));
       GlobalVariableDel(GlobalKey("sell_trend_rescue_latched_mask"));
       GlobalVariableDel(GlobalKey("buy_trend_rescue_rearm_mask"));
       GlobalVariableDel(GlobalKey("sell_trend_rescue_rearm_mask"));
       GlobalVariableDel(GlobalKey("trend_rescue_consumed_side"));
      }

   void PersistShadowSequence(void) const
     {
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
         GlobalVariableSet(
            GlobalKey("shadow_seq"),
            (double)m_shadow_last_command_seq
         );
     }

   void RestoreShadowSequence(void)
     {
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         GlobalVariableCheck(GlobalKey("shadow_seq")))
         m_shadow_last_command_seq=(ulong)GlobalVariableGet(
            GlobalKey("shadow_seq")
         );
     }

   string IsoUtcNow(void) const
     {
      MqlDateTime utc_time={};
      TimeToStruct(TimeGMT(),utc_time);
      return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                          utc_time.year,utc_time.mon,utc_time.day,
                          utc_time.hour,utc_time.min,utc_time.sec);
     }

   string ServerTimeNow(void) const
     {
      MqlDateTime server_time={};
      TimeToStruct(TimeTradeServer(),server_time);
      return StringFormat("%04d.%02d.%02d %02d:%02d:%02d",
                          server_time.year,server_time.mon,server_time.day,
                          server_time.hour,server_time.min,server_time.sec);
     }

   string EventSide(const string level_key,const string comment) const
     {
      string side_key=(level_key!="" ? level_key : comment);
      if(StringFind(side_key,"STR B")==0 ||
         side_key=="STR ORB" ||
         side_key=="STR AVB")
         return "buy";
      if(StringFind(side_key,"STR S")==0 ||
         side_key=="STR ORS" ||
         side_key=="STR AVS")
         return "sell";
      return "";
     }

   void WriteTelemetry(const string kind,
                       const string level_key,
                       const ulong ticket,
                       const double volume,
                       const double price,
                       const double stop_loss,
                       const double take_profit,
                       const string comment,
                       const ulong request_id,
                       const uint retcode,
                       const double commission,
                       const double swap,
                       const double profit,
                       const ulong deal_ticket,
                       const ulong order_ticket,
                       const ulong position_ticket)
     {
      if(!m_runtime.telemetry_enabled)
         return;
      int handle=FileOpen(m_telemetry_file,
                          FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return;
      if(FileSize(handle)==0)
         FileWrite(handle,
                   "utc_time","server_time","cycle_id","command_seq",
                   "kind","comment","side","volume","price","sl","tp",
                   "state","level","ticket","request_id","retcode",
                   "commission","swap","profit",
                   "schema_version","event_sequence","event_id",
                   "deal_ticket","order_ticket","position_ticket",
                   "cycle_realized","floating_profit","cycle_net",
                   "basket_target","evidence_grade");
      FileSeek(handle,0,SEEK_END);
      string event_comment=(comment!="" ? comment : level_key);
      ulong event_sequence=NextEventSequence();
      string event_id=EventId(kind,event_sequence,deal_ticket);
      double floating=CycleFloatingProfit();
      double scale=ContractScale();
      double basket_target=(
         m_profile.cycle_target_money>0.0
         ? m_profile.cycle_target_money*scale
         : m_cycle_start_balance*
           m_profile.cycle_target_balance_pct/100.0
      );
      double cycle_net=m_cycle_realized+floating;
      FileWrite(handle,
                 IsoUtcNow(),
                ServerTimeNow(),
                m_cycle_id,
                m_shadow_last_command_seq,
                kind,
                event_comment,
                EventSide(level_key,event_comment),
                DoubleToString(volume,8),
                DoubleToString(price,(int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS)),
                DoubleToString(stop_loss,(int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS)),
                DoubleToString(take_profit,(int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS)),
                EnumToString(m_state),
                level_key,
                ticket,
                request_id,
                 retcode,
                 DoubleToString(commission,8),
                 DoubleToString(swap,8),
                 DoubleToString(profit,8),
                 4,event_sequence,event_id,
                 deal_ticket,order_ticket,position_ticket,
                 DoubleToString(m_cycle_realized,8),
                 DoubleToString(floating,8),
                 DoubleToString(cycle_net,8),
                 DoubleToString(basket_target,8),
                 "FORMAL_CANDIDATE");
      FileClose(handle);
     }

   void LogEvent(const string kind,
                 const string level_key,
                 const ulong ticket,
                 const double volume,
                 const double price,
                 const string comment)
     {
      ulong deal_ticket=0;
      ulong order_ticket=0;
      ulong position_ticket=0;
      if(kind=="recovery")
         deal_ticket=ticket;
      else if(kind=="pending" || kind=="cancel")
         order_ticket=ticket;
      else if(kind=="stop" || kind=="close")
         position_ticket=ticket;
      WriteTelemetry(kind,level_key,ticket,volume,price,0.0,0.0,
                     comment,0,0,0.0,0.0,0.0,
                     deal_ticket,order_ticket,position_ticket);
     }

   void LogLifecycleEvent(const string kind,
                          const string level_key,
                          const string reason)
     {
      WriteTelemetry(
         kind,level_key,0,0.0,0.0,0.0,0.0,
         reason,0,0,0.0,0.0,0.0,
         0,0,0
       );
     }

   void UpdateAlignmentHoldTelemetry(const bool active)
     {
      if(active)
        {
         if(m_alignment_hold_logged)
            return;
         m_alignment_hold_logged=true;
         LogLifecycleEvent("alignment_hold","","file_present");
         return;
        }
      if(!m_alignment_hold_logged)
         return;
      m_alignment_hold_logged=false;
      LogLifecycleEvent("alignment_release","","file_removed");
     }

   string RequestComment(const MqlTradeRequest &request) const
     {
      if(request.position>0)
        {
         if(PositionSelectByTicket(request.position))
            return PositionGetString(POSITION_COMMENT);
         if(HistoryOrderSelect(request.position))
            return HistoryOrderGetString(request.position,ORDER_COMMENT);
        }
      if(request.order>0)
        {
         if(OrderSelect(request.order))
            return OrderGetString(ORDER_COMMENT);
         if(HistoryOrderSelect(request.order))
            return HistoryOrderGetString(request.order,ORDER_COMMENT);
        }
      if(request.comment!="")
         return request.comment;
      return "";
     }

   void LogTradeRequest(const MqlTradeRequest &request,
                         const MqlTradeResult &result)
     {
      string kind="trade_request";
      if(request.action==TRADE_ACTION_PENDING)
         kind="pending_request";
      else if(request.action==TRADE_ACTION_SLTP)
         kind="stop_request";
      else if(request.action==TRADE_ACTION_REMOVE)
         kind="cancel_request";
      else if(request.action==TRADE_ACTION_DEAL && request.position>0)
         kind="close_request";
      string comment=RequestComment(request);
      double event_price=(request.action==TRADE_ACTION_SLTP
                          ? request.sl
                          : request.price);
      ulong order_ticket=(
         request.order>0 ? request.order : result.order
      );
      WriteTelemetry(kind,comment,request.order,request.volume,event_price,
                     request.sl,request.tp,comment,
                     (ulong)result.request_id,result.retcode,
                     0.0,0.0,0.0,
                     0,order_ticket,request.position);
     }

   void WriteRuntimeManifest(void) const
     {
      string path=StringFormat("StraddleReplicaV2_%I64u_%s_manifest.csv",
                               m_runtime.magic,m_runtime.symbol);
      int handle=FileOpen(path,
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return;
      FileWrite(handle,"key","value");
      FileWrite(handle,"schema_version","3");
      FileWrite(handle,"runtime_mode",(int)m_runtime.runtime_mode);
      FileWrite(handle,"runtime_magic",m_runtime.magic);
      FileWrite(handle,"runtime_replica_mode",(int)m_runtime.replica_mode);
      FileWrite(handle,"runtime_inter_order_delay_ms",
                m_runtime.inter_order_delay_ms);
      FileWrite(handle,"runtime_deviation_points",
                m_runtime.deviation_points);
      FileWrite(handle,"runtime_require_demo_account",
                (int)m_runtime.require_demo_account);
      FileWrite(handle,"runtime_expected_account_login",
                m_runtime.expected_account_login);
      FileWrite(handle,"runtime_safety_enabled",
                (int)m_runtime.safety_enabled);
      FileWrite(handle,"runtime_max_equity_loss_pct",
                DoubleToString(m_runtime.max_equity_loss_pct,10));
      FileWrite(handle,"runtime_max_gross_lots",
                DoubleToString(m_runtime.max_gross_lots,10));
      FileWrite(handle,"runtime_max_spread_points",
                DoubleToString(m_runtime.max_spread_points,10));
      FileWrite(handle,"runtime_daily_loss_limit",
                DoubleToString(m_runtime.daily_loss_limit,10));
      FileWrite(handle,"runtime_shadow_command_max_age_ms",
                m_runtime.shadow_command_max_age_ms);
      FileWrite(handle,"runtime_shadow_adopt_existing_cycle",
                (int)m_runtime.allow_shadow_adopt_existing_cycle);
      FileWrite(handle,"profile",(int)m_profile.profile);
      FileWrite(handle,"profile_levels_per_side",
                m_profile.levels_per_side);
      FileWrite(handle,"profile_step_mode",(int)m_profile.step_mode);
      FileWrite(handle,"profile_fixed_step",
                DoubleToString(m_profile.fixed_step,10));
      FileWrite(handle,"profile_anchor_divisor",
                DoubleToString(m_profile.anchor_divisor,10));
      FileWrite(handle,"profile_atr_timeframe",
                (int)m_profile.atr_timeframe);
      FileWrite(handle,"profile_atr_period",m_profile.atr_period);
      FileWrite(handle,"profile_atr_multiplier",
                DoubleToString(m_profile.atr_multiplier,10));
      FileWrite(handle,"profile_lock_trigger_steps",
                DoubleToString(m_profile.lock_trigger_steps,10));
      FileWrite(handle,"profile_lock_offset_price",
                DoubleToString(m_profile.lock_offset_price,10));
      FileWrite(handle,"profile_activation_uses_trailing_distance",
                (int)m_profile.activation_uses_trailing_distance);
      FileWrite(handle,"profile_pre_tighten_trail_distance_steps",
                DoubleToString(m_profile.pre_tighten_trail_distance_steps,10));
      FileWrite(handle,"profile_tighten_trigger_steps",
                DoubleToString(m_profile.tighten_trigger_steps,10));
      FileWrite(handle,"profile_trail_distance_steps",
                DoubleToString(m_profile.trail_distance_steps,10));
      FileWrite(handle,"profile_cycle_target_balance_pct",
                DoubleToString(m_profile.cycle_target_balance_pct,10));
      FileWrite(handle,"profile_cycle_target_money",
                DoubleToString(m_profile.cycle_target_money,10));
      FileWrite(handle,"profile_cancel_before_close",
                (int)m_profile.cancel_before_close);
      FileWrite(handle,"profile_deployment_fill_cooldown_seconds",
                m_profile.deployment_fill_cooldown_seconds);
      FileWrite(handle,"profile_close_interval_seconds",
                m_profile.close_interval_seconds);
      FileWrite(handle,"profile_restart_delay_ms",
                m_profile.restart_delay_ms);
      FileWrite(handle,"profile_rearm_delay_seconds",
                m_profile.rearm_delay_seconds);
      FileWrite(handle,"profile_stop_update_interval_seconds",
                m_profile.stop_update_interval_seconds);
      FileWrite(handle,"profile_max_stop_updates_per_pass",
                m_profile.max_stop_updates_per_pass);
      FileWrite(handle,"profile_stop_scan_newest_first",
                (int)m_profile.stop_scan_newest_first);
      FileWrite(handle,"profile_stop_updates_on_timer",
                (int)m_profile.stop_updates_on_timer);
      FileWrite(handle,"profile_trend_rescue_enabled",
                (int)m_profile.trend_rescue_enabled);
      FileWrite(handle,"profile_trend_rescue_timeframe",
                (int)m_profile.trend_rescue_timeframe);
      FileWrite(handle,"profile_trend_rescue_bars",
                m_profile.trend_rescue_bars);
      FileWrite(handle,"profile_trend_rescue_minimum_pending_levels",
                m_profile.trend_rescue_minimum_pending_levels);
      FileWrite(handle,"profile_trend_rescue_move_price",
                DoubleToString(m_profile.trend_rescue_move_price,10));
      FileWrite(handle,"profile_trend_rescue_drawdown_money",
                DoubleToString(m_profile.trend_rescue_drawdown_money,10));
      FileWrite(handle,"profile_trend_rescue_volume_multiplier",
                DoubleToString(
                   m_profile.trend_rescue_volume_multiplier,
                   10
                ));
      for(int index=0;index<m_profile.levels_per_side;index++)
         FileWrite(handle,
                   StringFormat("profile_lot_%02d",index+1),
                   DoubleToString(m_profile.lots[index],10));
      FileWrite(handle,"account_server",AccountInfoString(ACCOUNT_SERVER));
      FileWrite(handle,"account_leverage",AccountInfoInteger(ACCOUNT_LEVERAGE));
      FileWrite(handle,"account_currency",AccountInfoString(ACCOUNT_CURRENCY));
      FileWrite(handle,"account_margin_mode",AccountInfoInteger(ACCOUNT_MARGIN_MODE));
      FileWrite(handle,"account_limit_orders",AccountInfoInteger(ACCOUNT_LIMIT_ORDERS));
      FileWrite(handle,"symbol",m_runtime.symbol);
      FileWrite(handle,"symbol_digits",SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS));
      FileWrite(handle,"symbol_tick_size",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_SIZE),10));
      FileWrite(handle,"symbol_tick_value",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_VALUE),10));
      FileWrite(handle,"symbol_tick_value_profit",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_VALUE_PROFIT),10));
      FileWrite(handle,"symbol_tick_value_loss",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_VALUE_LOSS),10));
      FileWrite(handle,"symbol_contract_size",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_CONTRACT_SIZE),10));
      FileWrite(handle,"symbol_volume_min",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_VOLUME_MIN),10));
      FileWrite(handle,"symbol_volume_max",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_VOLUME_MAX),10));
      FileWrite(handle,"symbol_volume_step",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_VOLUME_STEP),10));
      FileWrite(handle,"symbol_stops_level",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_STOPS_LEVEL));
      FileWrite(handle,"symbol_freeze_level",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_FREEZE_LEVEL));
      FileWrite(handle,"symbol_filling_mode",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_FILLING_MODE));
      FileWrite(handle,"symbol_swap_mode",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_SWAP_MODE));
      FileWrite(handle,"symbol_swap_long",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_SWAP_LONG),10));
      FileWrite(handle,"symbol_swap_short",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_SWAP_SHORT),10));
      FileWrite(handle,"symbol_swap_rollover3days",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_SWAP_ROLLOVER3DAYS));
      FileClose(handle);
     }

   double ContractScale(void) const
     {
      double contract_size=SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_CONTRACT_SIZE);
      if(contract_size<=0.0)
         return 1.0;
      return contract_size/100.0;
     }

   bool PendingPriceIsValid(const bool is_buy,const double price) const
     {
      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick))
         return false;
      double stops_distance=(double)SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_STOPS_LEVEL)*m_point;
      double freeze_distance=(double)SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_FREEZE_LEVEL)*m_point;
      double minimum_distance=MathMax(stops_distance,freeze_distance);
      if(is_buy)
         return price>tick.ask+minimum_distance;
      return price<tick.bid-minimum_distance;
     }

   bool IsHistoricalProfile(void) const
     {
      return(m_profile.profile==HISTORICAL_50 ||
             m_profile.profile==HISTORICAL_60);
     }

   bool PlaceLevel(SLevelState &level_state)
     {
      if(level_state.duplicate_identity)
         return false;
      // Target EA parity: an OPEN POSITION on this level does not block a fresh
      // pending at the same price.  That is the mechanism by which the Target
      // re-fills a level and orphans the position it was previously pointing at
      // (see replica_orphan_leak).  A live PENDING still blocks, on both paths.
      if(level_state.has_pending ||
         (!OrphanLeakActive() && level_state.has_position))
         return true;
      if(!PendingPriceIsValid(level_state.is_buy,level_state.target_price))
        {
         string level_comment=StringFormat("STR %s%d",
                                           (level_state.is_buy ? "B" : "S"),
                                           level_state.level);
          if(IsHistoricalProfile() && !level_state.recovery_done)
            {
             if(!ExposureAllowsRearm(level_state.volume))
               {
                LogLifecycleEvent(
                   "safety_rearm_blocked",
                   level_comment,
                   "max_gross_lots"
                );
                return false;
               }
             string recovery_comment=(level_state.is_buy ? "STR ORB" : "STR ORS");
             if(!m_gateway.OpenMarket(level_state.is_buy,
                                      level_state.volume,
                                      recovery_comment))
                return false;
             level_state.rearm_requested=false;
             level_state.rearm_after_msc=0;
             LogEvent("recovery",level_comment,m_gateway.LastDeal(),
                      level_state.volume,level_state.target_price,recovery_comment);
           }
         else if(!level_state.recovery_done)
            LogEvent("deferred",level_comment,0,level_state.volume,
                     level_state.target_price,"crossed");
         level_state.recovery_done=true;
         return true;
        }
      string comment=StringFormat("STR %s%d",(level_state.is_buy ? "B" : "S"),level_state.level);
      if(!m_gateway.PlaceStop(level_state.is_buy,
                              level_state.volume,
                              level_state.target_price,
                              comment))
         return false;
       level_state.has_pending=true;
       level_state.order_ticket=m_gateway.LastOrder();
       level_state.rearm_requested=false;
       level_state.rearm_after_msc=0;
      LogEvent("pending",comment,level_state.order_ticket,level_state.volume,level_state.target_price,comment);
      return true;
     }

   long CurrentServerMs(void) const
     {
      MqlTick tick={};
      if(SymbolInfoTick(m_runtime.symbol,tick) && tick.time_msc>0)
         return tick.time_msc;
      return (long)TimeCurrent()*1000;
     }

   bool RearmDelayElapsed(const SLevelState &level_state) const
     {
      return(level_state.rearm_after_msc<=0 ||
             !(CurrentServerMs()<level_state.rearm_after_msc));
     }

   void ScheduleLevelRearm(const string level_comment,
                           const long exit_time_msc=0)
     {
      bool is_buy=false;
      int index=-1;
      if(!ParseLevelComment(level_comment,is_buy,index))
         return;
       long rearm_base_msc=(
          exit_time_msc>0 ? exit_time_msc : CurrentServerMs()
       );
       long rearm_after_msc=(
          rearm_base_msc+
          (long)m_profile.rearm_delay_seconds*1000
       );
        if(is_buy)
          {
           m_buy_levels[index].volume=m_profile.lots[index];
           m_buy_levels[index].rearm_requested=true;
           m_buy_levels[index].rearm_after_msc=rearm_after_msc;
          }
        else
          {
           m_sell_levels[index].volume=m_profile.lots[index];
           m_sell_levels[index].rearm_requested=true;
           m_sell_levels[index].rearm_after_msc=rearm_after_msc;
          }
     }

   bool DealMetadataReady(const ulong deal_ticket) const
     {
      long deal_time_msc=0;
      long deal_magic=0;
      long entry_value=0;
      long position_id=0;
      long order_ticket=0;
      double deal_volume=0.0;
      double deal_price=0.0;
      string deal_symbol="";
      if(!HistoryDealGetInteger(
            deal_ticket,
            DEAL_TIME_MSC,
            deal_time_msc
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_MAGIC,
            deal_magic
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_ENTRY,
            entry_value
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_POSITION_ID,
            position_id
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_ORDER,
            order_ticket
         ) ||
         !HistoryDealGetDouble(
            deal_ticket,
            DEAL_VOLUME,
            deal_volume
         ) ||
         !HistoryDealGetDouble(
            deal_ticket,
            DEAL_PRICE,
            deal_price
         ) ||
         !HistoryDealGetString(
            deal_ticket,
            DEAL_SYMBOL,
            deal_symbol
         ))
         return false;
      if(deal_time_msc<=0 ||
         position_id<=0 ||
         order_ticket<=0 ||
         deal_volume<=0.0 ||
         deal_price<=0.0 ||
         deal_symbol=="")
         return false;
      long metadata_age_msc=CurrentServerMs()-deal_time_msc;
      if(deal_symbol==m_runtime.symbol &&
         deal_magic==0 &&
         metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
         return false;
      if((ulong)deal_magic!=m_runtime.magic ||
         deal_symbol!=m_runtime.symbol)
         return true;
      string deal_comment="";
      if(!HistoryDealGetString(
            deal_ticket,
            DEAL_COMMENT,
            deal_comment
         ))
         return false;
      string level_comment=PositionCommentFromDeal(deal_ticket);
      if(level_comment=="" &&
         deal_comment=="" &&
         metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
         return false;
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)entry_value;
      if(entry==DEAL_ENTRY_OUT ||
         entry==DEAL_ENTRY_OUT_BY ||
         entry==DEAL_ENTRY_INOUT)
        {
         long reason_value=0;
         if(!HistoryDealGetInteger(
               deal_ticket,
               DEAL_REASON,
               reason_value
            ))
            return false;
         if(reason_value==DEAL_REASON_CLIENT &&
            metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
            return false;
         if(deal_comment=="" &&
            metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
            return false;
         bool stop_exit=(
            reason_value==DEAL_REASON_SL ||
            StringFind(deal_comment,"[sl")==0 ||
            StringFind(deal_comment,"sl ")==0
         );
         bool level_is_buy=false;
         int level_index=-1;
         if(stop_exit &&
            !ParseLevelComment(
               level_comment,
               level_is_buy,
               level_index
            ))
            return false;
        }
      return true;
     }

   long CurrentUtcMs(void) const
     {
      return (long)TimeGMT()*1000;
     }

   bool ReadShadowCommand(SShadowCommand &command) const
     {
      int handle=FileOpen(m_runtime.shadow_command_file,
                          FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return false;
      for(int index=0;index<9;index++)
        {
         if(FileIsEnding(handle))
           {
            FileClose(handle);
            return false;
           }
         FileReadString(handle);
        }
      if(FileIsEnding(handle))
        {
         FileClose(handle);
         return false;
        }
      command.schema_version=(int)StringToInteger(FileReadString(handle));
      command.command_seq=(ulong)StringToInteger(FileReadString(handle));
      command.command=FileReadString(handle);
      command.cycle_id=FileReadString(handle);
      command.profile=FileReadString(handle);
      command.anchor=StringToDouble(FileReadString(handle));
      command.step=StringToDouble(FileReadString(handle));
      command.target_start_utc_ms=(long)StringToInteger(FileReadString(handle));
      command.expires_utc_ms=(long)StringToInteger(FileReadString(handle));
      FileClose(handle);
      return true;
     }

   bool ReadShadowAckState(ulong &command_seq,
                           string &status,
                           string &cycle_id) const
     {
      command_seq=0;
      status="";
      cycle_id="";
      int handle=FileOpen(m_runtime.shadow_ack_file,
                          FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return false;
      for(int index=0;index<6;index++)
        {
         if(FileIsEnding(handle))
           {
            FileClose(handle);
            return false;
           }
         FileReadString(handle);
        }
      if(FileIsEnding(handle))
        {
         FileClose(handle);
         return false;
        }
      int schema_version=(int)StringToInteger(FileReadString(handle));
      command_seq=(ulong)StringToInteger(FileReadString(handle));
      status=FileReadString(handle);
      cycle_id=FileReadString(handle);
      FileClose(handle);
      return(schema_version==1);
     }

   void WriteShadowAck(const string status,
                       const ulong command_seq,
                       const string reason) const
     {
      int handle=FileOpen(m_runtime.shadow_ack_file,
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return;
      FileWrite(handle,
                "schema_version","command_seq","status","cycle_id",
                "utc_time","reason");
      FileWrite(handle,
                1,command_seq,status,m_cycle_id,IsoUtcNow(),reason);
      FileClose(handle);
     }

   bool StartShadowCycle(const double anchor,const double step)
     {
      if(m_halted || anchor<=0.0 || step<=0.0)
         return false;
      if(OwnedOrderCount()>0 || CyclePositionCount()>0 || m_state!=CYCLE_IDLE)
         return false;
      OrphanRemainingTrackedPositions();
      ResetLevelState();
      m_anchor=NormalizePrice(anchor);
      m_step=NormalizePrice(step);
      if(m_anchor<=0.0 || m_step<=0.0)
         return false;
      InitializeLevelTargets();
      m_cycle_start_balance=AccountInfoDouble(ACCOUNT_BALANCE);
      m_cycle_realized=0.0;
      m_cycle_exit_deal_count=0;
      m_cycle_started_at=TimeCurrent();
      m_cycle_started_utc=TimeGMT();
       m_cycle_started_msc=(long)m_cycle_started_at*1000;
       m_cycle_started_ms=GetTickCount64();
       m_event_sequence=0;
       ResetProcessedDeals();
       m_last_history_reconcile_ms=0;
       m_history_reconcile_seeded=false;
       GlobalVariableSet(GlobalKey("event_seq"),0.0);
      m_last_stop_update_at=0;
      m_last_entry_fill_at=0;
      m_deploy_index=0;
      m_has_traded=false;
      m_shadow_reset_active=false;
      m_state=CYCLE_DEPLOYING;
      PersistCycle();
      LogEvent("cycle_start","",0,0.0,m_anchor,"");
      return true;
     }

   bool AdoptExistingShadowCycle(void)
     {
      if(m_runtime.runtime_mode!=STR_RUNTIME_SHADOW ||
         !m_runtime.allow_shadow_adopt_existing_cycle ||
         (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=
            ACCOUNT_TRADE_MODE_DEMO ||
         m_runtime.expected_account_login==0 ||
         OwnedOrderCount()+OwnedPositionCount()==0)
         return false;
      m_cycle_id=StringFormat(
         "local-adopt-%I64u-%I64d",
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
         (long)TimeGMT()
      );
      if(!RestoreCycle())
        {
         m_cycle_id="";
         return false;
        }
      PersistShadowSequence();
      LogEvent("shadow_adopt","",0,0.0,0.0,"existing_cycle");
      WriteShadowAck("ADOPTED",
                     m_shadow_last_command_seq,
                     "existing_cycle");
      return true;
     }

   void CompleteShadowReset(void)
     {
      m_shadow_reset_active=false;
      m_halted=false;
      m_state=CYCLE_IDLE;
      LogLifecycleEvent("cycle_complete","","flat");
      LogEvent("shadow_reset_complete","",0,0.0,0.0,"");
      WriteShadowAck("FLAT",m_shadow_last_command_seq,"");
      ClearPersistence();
      m_cycle_id="";
     }

   void BeginShadowReset(void)
     {
      m_shadow_reset_active=true;
      m_halted=false;
      if(OwnedOrderCount()>0)
         m_state=CYCLE_CANCELING;
      else if(CyclePositionCount()>0)
         m_state=CYCLE_CLOSING;
      else
        {
         CompleteShadowReset();
         return;
        }
      PersistCycle();
      LogEvent("shadow_reset_begin","",0,0.0,0.0,"");
     }

   void PollShadowCommand(void)
     {
      if(m_runtime.runtime_mode!=STR_RUNTIME_SHADOW)
         return;
      SShadowCommand command={};
      if(!ReadShadowCommand(command))
         return;
      if(command.command_seq<=m_shadow_last_command_seq)
         return;
      long now_ms=CurrentUtcMs();
      if(command.schema_version!=1 ||
         command.expires_utc_ms<now_ms ||
         now_ms-command.target_start_utc_ms>
            m_runtime.shadow_command_max_age_ms)
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"stale");
         WriteShadowAck("REJECTED",command.command_seq,"stale_or_schema");
         return;
        }
      if(command.command=="RESET")
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         WriteShadowAck("RESETTING",command.command_seq,"");
         BeginShadowReset();
         return;
        }
      if(command.command!="START" ||
         command.profile!="LATEST_30" ||
         m_profile.profile!=LATEST_30)
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"command");
         WriteShadowAck("REJECTED",command.command_seq,"invalid_command");
         return;
        }
      if(OwnedOrderCount()>0 || CyclePositionCount()>0 || m_state!=CYCLE_IDLE)
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"not_flat");
         WriteShadowAck("REJECTED",command.command_seq,"not_flat");
         return;
        }
      m_shadow_last_command_seq=command.command_seq;
      m_cycle_id=command.cycle_id;
      if(!StartShadowCycle(command.anchor,command.step))
        {
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"start_failed");
         WriteShadowAck("REJECTED",command.command_seq,"start_failed");
         return;
        }
      PersistShadowSequence();
      WriteShadowAck("STARTED",command.command_seq,"");
     }

   bool StartCycle(void)
     {
      if(m_halted)
         return false;
      // Target EA parity: the "am I flat?" test is over the LEVEL TABLE, not the
      // account book.  The Target opened 149+ cycles while its orphan residue
      // ratcheted 6 -> 148, which a book-wide test could not have done: the
      // first orphan would have blocked every later cycle forever.  Pendings are
      // never orphaned, so the order half of the test stays book-wide.
      if(OwnedOrderCount()>0 || CyclePositionCount()>0)
         return false;
      if(m_runtime.start_time>0 && TimeCurrent()<m_runtime.start_time)
         return false;
      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick) || tick.bid<=0.0 || tick.ask<=0.0)
         return false;
      OrphanRemainingTrackedPositions();
      ResetLevelState();
      m_anchor=NormalizePrice((tick.bid+tick.ask)/2.0);
      m_step=CalculateStep(m_anchor);
      if(m_step<=0.0)
         return false;
      InitializeLevelTargets();
      m_cycle_start_balance=AccountInfoDouble(ACCOUNT_BALANCE);
      m_cycle_realized=0.0;
      m_cycle_exit_deal_count=0;
      m_cycle_started_at=TimeCurrent();
      m_cycle_started_utc=TimeGMT();
      m_cycle_started_msc=(long)m_cycle_started_at*1000;
      m_cycle_started_ms=GetTickCount64();
       m_cycle_id=CycleIdFromUtc("local",m_cycle_started_utc);
       m_event_sequence=0;
       ResetProcessedDeals();
       m_last_history_reconcile_ms=0;
       m_history_reconcile_seeded=false;
       GlobalVariableSet(GlobalKey("event_seq"),0.0);
       GlobalVariableSet(GlobalKey("last_deal"),0.0);
      m_last_stop_update_at=0;
      m_last_entry_fill_at=0;
      m_deploy_index=0;
      m_has_traded=false;
      m_state=CYCLE_DEPLOYING;
      PersistCycle();
      LogEvent("cycle_start","",0,0.0,m_anchor,"");
      return true;
     }

   bool DeployDeferred(const int slot) const
     {
      int level_index=slot/2;
      if(level_index<0 || level_index>=m_profile.levels_per_side)
         return false;
      return(slot%2==0 ? m_buy_levels[level_index].deploy_deferred
                       : m_sell_levels[level_index].deploy_deferred);
     }

   void DeployOne(void)
     {
      int sweep_slots=m_profile.levels_per_side*2;
      int retry_slots=sweep_slots*2;
      // Slots [0,sweep_slots) are the interleaved first pass; slots
      // [sweep_slots,retry_slots) are the SINGLE retry pass appended at the tail
      // of the same burst.  Fast-forward over every retry slot whose level was
      // armed on the first pass INSIDE THIS SAME TICK, so that only a genuinely
      // deferred level costs a timer tick: on the 901018 tape the retry leg goes
      // out one inter_order_delay_ms after the last first-pass leg (110/113/111/
      // 111/117/116 ms on the first six HISTORICAL_60 bursts), not one tick per
      // skipped slot, which would put it ~12 s after S60.  A clean burst
      // therefore completes on exactly the tick it always did.
      while(m_deploy_index>=sweep_slots &&
            m_deploy_index<retry_slots &&
            !DeployDeferred(m_deploy_index-sweep_slots))
         m_deploy_index++;
      if(m_deploy_index>=retry_slots)
        {
         if(OwnedOrderCount()==0 && CyclePositionCount()==0)
           {
            // Degenerate case OUTSIDE the target's measured envelope: all 2N
            // first-pass attempts AND all 2N tail retries were rejected, so the
            // sweep armed nothing.  Staying in CYCLE_RUNNING would idle forever
            // on the flag-gated profiles -- CheckCycleTargets() returns early
            // while !m_has_traded with nothing open, and with
            // replica_orphan_leak=false RearmEligible() additionally needs
            // rearm_requested, which only a stop-loss exit or a post-restart
            // restore ever sets, so no level would ever come back.  Re-anchor
            // after the flat delay instead.  The worst real deployment on either
            // tape still armed 39 of 50 levels (Starwave 2026-08-21) and the
            // worst on the 901018 tape lost only level 1 (HISTORICAL_60, 118 of
            // 120 legs), so this branch cannot fire on any measured cycle.
            m_state=CYCLE_RESTARTING;
            m_restart_started_at=TimeCurrent();
            PersistCycle();
            LogLifecycleEvent("deployment_empty","","all_levels_rejected");
            LogEvent("deployment_empty","",0,0.0,0.0,"all_levels_rejected");
            return;
           }
         m_state=CYCLE_RUNNING;
         ReconcileLevels();
         PersistCycle();
         LogEvent("deployment_complete","",0,0.0,0.0,"");
         return;
        }
      if(m_profile.deployment_fill_cooldown_seconds>0 &&
         m_last_entry_fill_at>0 &&
         TimeCurrent()-m_last_entry_fill_at<m_profile.deployment_fill_cooldown_seconds)
         return;
      bool retry_pass=(m_deploy_index>=sweep_slots);
      int slot=(retry_pass ? m_deploy_index-sweep_slots : m_deploy_index);
      int level_index=slot/2;
      bool is_buy=(slot%2==0);
      // Clear the mark BEFORE the retry attempt, so a second failure abandons the
      // level for the rest of the cycle instead of queueing a third attempt.
      if(retry_pass)
        {
         if(is_buy)
            m_buy_levels[level_index].deploy_deferred=false;
         else
            m_sell_levels[level_index].deploy_deferred=false;
        }
      bool placed=(is_buy ? PlaceLevel(m_buy_levels[level_index])
                          : PlaceLevel(m_sell_levels[level_index]));
      string level_comment=StringFormat(
         "STR %s%d",
         (is_buy ? "B" : "S"),
         level_index+1
      );
      if(placed)
        {
         if(retry_pass)
            LogLifecycleEvent("deployment_level_retried",level_comment,"tail_retry");
         m_deploy_index++;
         return;
        }
      if(!retry_pass)
        {
         if(is_buy)
            m_buy_levels[level_index].deploy_deferred=true;
         else
            m_sell_levels[level_index].deploy_deferred=true;
        }
      string reject_reason=StringFormat(
         "retcode_%u%s",
         m_gateway.LastRetcode(),
         (retry_pass ? "_retry_abandoned" : "_deferred")
      );
      // TARGET EA PARITY -- A REJECTED LEVEL IS DEFERRED TO ONE RETRY PASS AT
      // THE TAIL OF THE SAME BURST, THEN ABANDONED.  IT NEVER ABORTS THE SWEEP
      // AND IT NEVER RETRIES MORE THAN ONCE.
      //
      // This branch previously dropped the whole cycle into CYCLE_CANCELING on
      // TRADE_RETCODE_INVALID_PRICE (cancel everything, re-anchor) and, on any
      // other retcode, fell through WITHOUT advancing m_deploy_index -- retrying
      // the same level on every subsequent tick, forever.  The target does
      // neither.  It attempts the level, fails, advances immediately, and comes
      // back for it exactly once after the last first-pass leg has gone out.
      //
      // The retry is invisible in the order table and can only be read off
      // DISPATCH ORDER: the 901018 tape carries 54,742 orders whose state is only
      // ever filled (35,430) or canceled (19,312) -- ZERO rejected -- so a level
      // the broker refuses leaves no row at all.  It shows up as a gap in the
      // lattice plus a late re-dispatch of that same (side,level).
      //
      // Measured over the 285 deployment bursts recovered from that tape,
      // 70 dispatch a level-1 leg AFTER the highest level of the burst:
      // HISTORICAL_60 68 of 78, HISTORICAL_50 2 of 101, and 0 of 103 on
      // STARWAVE_30.  The adjacent-rank inversion census is S60 -> S1 x37,
      // S60 -> B1 x31, S1 -> B1 x3 (71 inversions over 68 bursts; three carry
      // two).  Three facts pin it to the EA's own dispatch rather than to the
      // reader or to a folded-in re-arm:
      //   * timestamps and tickets are strictly monotone across every swap --
      //     0 swaps share a millisecond, 0 have non-monotone tickets, and the
      //     tickets run consecutively (20216347/48/49/50);
      //   * the gap from the last first-pass leg to the retry leg is ONE
      //     inter_order_delay_ms tick (110/113/111/111/117/116 ms), not the ~12 s
      //     a fresh burst or a re-arm sweep would cost;
      //   * the retry lands on the EXACT original lattice price, not a re-anchored
      //     one.  Burst 2026-07-02 21:52:35 has B60=4148.27 and S60=4093.07, so
      //     anchor=4120.67 and step=55.20/120=0.46; its tail leg is B1 at
      //     4121.13 = anchor + 1*step to the cent.
      //
      // The first-pass rejection is the broker minimum stop distance that
      // PendingPriceIsValid() already models.  Score all 285 bursts on step
      // alone: 0 of 66 bursts below step 0.60 are clean, versus 202 of 208
      // (97.12%) at or above 0.70.  Within HISTORICAL_60 the 10 clean bursts run
      // step 0.70..0.78 and the deferred ones 0.37..0.64 with ZERO overlap, and
      // AGGRESSIVE_30 is clean at 0.68 -- so the threshold is step in
      // (0.64, 0.68], i.e. stops_level ~ 0.50..0.55 plus half the spread.  Level
      // 1 sits one step from the anchor and fails; level 2 at twice the step
      // clears.  That is exactly the missing-legs census: ['B1'] x34, ['S1'] x27,
      // [] x5, ['S1','S2'] x1, ['S1','S15'..'S18'] x1 -- level 2 or higher is
      // missing in only 2 of 68.
      //
      // The retry is ONE pass, and a level whose retry also fails is abandoned
      // for the rest of the cycle.  7 of the 78 HISTORICAL_60 bursts and 2 of the
      // 103 STARWAVE_30 bursts carry NO level-1 leg at all, and the three
      // incomplete Starwave lattices below are the same outcome at scale -- so
      // there is no second retry, no loop, and no re-anchor.  Why the retry
      // usually succeeds on 901018 and did not on Starwave: a 60-level burst takes
      // ~12 s, price drifts, and the minimum-distance test that failed at t=0
      // passes by the time the tail is reached; on Starwave 2026-08-21 the
      // rejection was still live one tick later.
      //
      // HISTORICAL_50's 2 deferrals are the same architecture with a different
      // trigger: steps 0.94 and 0.99, far above the distance threshold, B1
      // dispatched in slot #0 and FILLED, S1 deferred to the last slot, and
      // nothing missing from the lattice -- a transient REQUOTE/PRICE_CHANGED that
      // the tail retry then placed successfully.
      //
      // Measured on all three of the 119 Starwave deployments that came out
      // incomplete (2.5%); there is not one abort-and-re-anchor event in the
      // whole history:
      //
      //   2026-08-21 18:03  anchor 4617.58  step 1.54  (round(4617.58/3000,2),
      //       B1-S1 = 3.08 = 2*step).  Placed B1 S1 B2 S2 ... B14 S14 then
      //       B15..B25 with S15..S25 all rejected.  Per-successful-op cadence
      //       DOUBLES across the tail -- B15 at +3.1 s to B25 at +5.4 s is
      //       ~209 ms/op against ~105 ms in the interleaved head -- which is the
      //       wasted tick of each failed SELL.  The skipped prices were valid:
      //       S15 would have sat at 4594.48 while S1 filled at 4616.04 two
      //       minutes later, i.e. ~23 dollars BELOW market.  The rejections were
      //       transient and broker-side, not price-side.  That partial lattice
      //       is what traded for the next 2.5 days, banking $479.75 over 64
      //       closes with S15..S25 permanently absent.
      //   2026-08-24 06:12  anchor 4636.08  step 1.55.  Scattered rejections on
      //       BOTH sides (S6, S8..S14, B16, S16, B17, S17, B18, S19, B22) in
      //       early Asia; same cadence doubling at each skip; sweep still ran
      //       out to level 30.
      //   2026-08-27 08:23  only S1 rejected -- the nearest level, i.e. a
      //       stops_level/freeze-level rejection -- and the other 59 were placed.
      //
      // And once the single retry has been spent the gaps are never back-filled:
      // in all three cycles the abandoned slots stayed empty while OTHER levels
      // re-armed normally (08-21 saw 11 distinct levels re-arm, e.g. B2 six times,
      // B1 five times).  The ordinary re-arm path cannot reach them either --
      // RearmOneMissingLevel() runs only in CYCLE_RUNNING, and on a profile with
      // replica_orphan_leak=false RearmEligible() additionally requires
      // rearm_requested, which ScheduleLevelRearm() sets only when a level's
      // position closes on stop-loss.  So the burst-local retry above is the only
      // second chance a deployment-rejected level ever gets, which is why it lives
      // in DeployOne() and not in the re-arm scheduler.
      LogLifecycleEvent("deployment_level_rejected",level_comment,reject_reason);
      LogEvent(
         "deployment_skip",
         level_comment,
         0,
         0.0,
         0.0,
         reject_reason
      );
      m_deploy_index++;
     }

   // Target EA parity: the Target has neither a "re-arm requested" flag nor a
   // "position still open" gate.  Its rule is simply "a level with no live
   // pending gets one", throttled only by PendingPriceIsValid() and the re-arm
   // delay.  That single rule accounts for all four re-arm buckets measured on
   // the Starwave tape -- 969 after a stop-out, 87 while the level's previous
   // position was STILL OPEN, 3 after some other exit, 59 with no in-cycle fill
   // at all -- and for the p50 81 s latency, because a level that has just
   // filled cannot re-arm until price retreats back through it.  The
   // flag-driven path structurally cannot produce the 87 or the 59, because
   // ScheduleLevelRearm() is only ever reached from the stop-exit branch of
   // ProcessSelectedDeal().  Re-filling a level while its previous position is
   // open is exactly what orphans that position (see replica_orphan_leak).
   bool RearmEligible(const SLevelState &level_state) const
     {
      if(level_state.has_pending ||
         level_state.trend_rescue_replacement ||
         level_state.duplicate_identity)
         return false;
      if(OrphanLeakActive())
         return true;
      return(level_state.rearm_requested && !level_state.has_position);
     }

   void RearmOneMissingLevel(void)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
          if(RearmEligible(m_buy_levels[index]))
            {
              if(!RearmDelayElapsed(m_buy_levels[index]))
                 continue;
              bool trend_rescue_rearm=(
                 TrendRescuePositionRearmPending(true,index)
              );
              m_buy_levels[index].volume=(
                 m_buy_levels[index].trend_rescue_latched ||
                 trend_rescue_rearm
                 ? m_profile.lots[index]*
                   m_profile.trend_rescue_volume_multiplier
                 : m_profile.lots[index]
             );
              // Target EA parity: re-arms ALWAYS return to the original anchor
              // lattice price. Measured on ReportHistory-901018: of 12,443 grid
              // pendings that are not deployment-burst orders, 1,091 belong to
              // 10 deployment bursts the cycle segmenter merged into an open
              // cycle, and ALL 11,352 true re-arms land on the exact price of
              // the same (side,level) slot -- 11,058 on the cycle's burst slot
              // and 294 on the same lattice past a truncated slot table.
              // Residual zero: not one relocation in the tape. Repeated re-arms
              // of one slot agree to the cent (2,490 slots, up to 19 repeats,
              // max intra-slot spread 0.0000), and only 0.93% sit at
              // market +/- level*step, so re-anchoring is refuted outright; sell
              // stops were observed re-armed up to 35 steps away from market on
              // the original lattice. The Target EA never re-anchors pendings to
              // market. If the lattice price is currently invalid (market has
              // crossed it), wait for price to return instead of moving the level.
              if(!PendingPriceIsValid(true,m_buy_levels[index].target_price))
                 continue;
             if(!ExposureAllowsRearm(m_buy_levels[index].volume))
               {
                LogLifecycleEvent(
                   "safety_rearm_blocked",
                   StringFormat("STR B%d",m_buy_levels[index].level),
                   "max_gross_lots"
                );
                 return;
                }
              if(PlaceLevel(m_buy_levels[index]))
                {
                 if(trend_rescue_rearm)
                   {
                    ClearTrendRescuePositionRearm(true,index);
                    PersistCycle();
                   }
                }
              return;
            }
          if(RearmEligible(m_sell_levels[index]))
            {
              if(!RearmDelayElapsed(m_sell_levels[index]))
                 continue;
              bool trend_rescue_rearm=(
                 TrendRescuePositionRearmPending(false,index)
              );
              m_sell_levels[index].volume=(
                 m_sell_levels[index].trend_rescue_latched ||
                 trend_rescue_rearm
                 ? m_profile.lots[index]*
                   m_profile.trend_rescue_volume_multiplier
                 : m_profile.lots[index]
             );
              // Target EA parity: sell-side re-arms also return to the original
              // anchor lattice price (see buy-side note above). Never re-anchor
              // to market; wait for price to return if currently invalid.
              if(!PendingPriceIsValid(false,m_sell_levels[index].target_price))
                 continue;
             if(!ExposureAllowsRearm(m_sell_levels[index].volume))
               {
                LogLifecycleEvent(
                   "safety_rearm_blocked",
                   StringFormat("STR S%d",m_sell_levels[index].level),
                   "max_gross_lots"
                );
                 return;
                }
              if(PlaceLevel(m_sell_levels[index]))
                {
                 if(trend_rescue_rearm)
                   {
                    ClearTrendRescuePositionRearm(false,index);
                    PersistCycle();
                   }
                }
             return;
            }
        }
     }

   double OwnedFloatingProfit(void) const
     {
      double total=0.0;
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)>0 && IsOwnedPositionSelected())
            total+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
        }
      return total;
     }

   int TrendRescueSide(void) const
     {
      if(!m_profile.trend_rescue_enabled ||
         m_profile.trend_rescue_bars<1 ||
         m_profile.trend_rescue_move_price<=0.0 ||
         m_profile.trend_rescue_drawdown_money<=0.0 ||
         m_profile.trend_rescue_volume_multiplier<=1.0 ||
         CycleFloatingProfit()>-m_profile.trend_rescue_drawdown_money)
         return 0;
      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick))
         return 0;
      double prior_close=iClose(m_runtime.symbol,m_profile.trend_rescue_timeframe,m_profile.trend_rescue_bars);
      if(prior_close<=0.0)
         return 0;
      if(tick.ask-prior_close>=m_profile.trend_rescue_move_price)
         return 1;
      if(prior_close-tick.bid>=m_profile.trend_rescue_move_price)
         return -1;
      return 0;
     }

   bool IsBaseLevelVolume(const int index,const double volume) const
     {
      return MathAbs(volume-m_profile.lots[index])<=1e-8;
     }

   bool HasTrendRescueBasePending(const bool is_buy) const
     {
      int matching_levels=0;
      for(int order_index=0;order_index<OrdersTotal();order_index++)
        {
         ulong ticket=OrderGetTicket(order_index);
         if(ticket==0 || !IsOwnedOrderSelected())
            continue;
         bool order_is_buy=false;
         int index=-1;
         if(!ParseLevelComment(
               OrderGetString(ORDER_COMMENT),
               order_is_buy,
               index
            ) ||
            order_is_buy!=is_buy)
            continue;
         if(IsBaseLevelVolume(
               index,
               OrderGetDouble(ORDER_VOLUME_CURRENT)
            ))
           {
            matching_levels++;
            if(matching_levels>=
               m_profile.trend_rescue_minimum_pending_levels)
               return true;
           }
        }
      return false;
     }

   bool TryCancelTrendRescueLevel(SLevelState &level_state,
                                  const int index)
     {
      if(level_state.trend_rescue_replacement ||
         !level_state.has_pending ||
         level_state.order_ticket==0 ||
         !OrderSelect(level_state.order_ticket) ||
         !IsOwnedOrderSelected() ||
         !IsBaseLevelVolume(
            index,
            OrderGetDouble(ORDER_VOLUME_CURRENT)
         ))
         return false;
      ulong ticket=level_state.order_ticket;
      double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
      double price=OrderGetDouble(ORDER_PRICE_OPEN);
      string comment=OrderGetString(ORDER_COMMENT);
      if(!m_gateway.DeleteOrder(ticket))
         return true;
      level_state.trend_rescue_replacement=true;
      level_state.trend_rescue_latched=true;
      level_state.volume=(
         m_profile.lots[index]*
         m_profile.trend_rescue_volume_multiplier
      );
      level_state.rearm_requested=false;
      level_state.rearm_after_msc=0;
      m_trend_rescue_mask|=TrendRescueBit(index);
      if(level_state.is_buy)
         m_buy_trend_rescue_latched_mask|=TrendRescueBit(index);
      else
         m_sell_trend_rescue_latched_mask|=TrendRescueBit(index);
      PersistCycle();
      LogEvent("cancel",comment,ticket,volume,price,comment);
      return true;
     }

   bool TryCancelOneTrendRescueOrder(const bool is_buy)
     {
      for(int index=m_profile.levels_per_side-1;index>=0;index--)
        {
         if(is_buy)
           {
            if(TryCancelTrendRescueLevel(m_buy_levels[index],index))
               return true;
           }
         else if(TryCancelTrendRescueLevel(
                    m_sell_levels[index],
                    index
                 ))
            return true;
        }
      return false;
     }

   void ClearTrendRescueReplacement(SLevelState &level_state,
                                    const int index)
     {
      level_state.trend_rescue_replacement=false;
      m_trend_rescue_mask&=~TrendRescueBit(index);
     }

   void PlaceOneTrendRescueReplacement(const bool is_buy)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         bool marked=(
            is_buy
            ? m_buy_levels[index].trend_rescue_replacement
            : m_sell_levels[index].trend_rescue_replacement
         );
         if(!marked)
            continue;
         if(is_buy)
           {
            if(m_buy_levels[index].has_position)
              {
               ClearTrendRescueReplacement(m_buy_levels[index],index);
               PersistCycle();
               return;
              }
            if(m_buy_levels[index].has_pending)
              {
               if(OrderSelect(m_buy_levels[index].order_ticket) &&
                  !IsBaseLevelVolume(
                     index,
                     OrderGetDouble(ORDER_VOLUME_CURRENT)
                  ))
                 {
                  ClearTrendRescueReplacement(m_buy_levels[index],index);
                  PersistCycle();
                 }
               return;
              }
            if(!PendingPriceIsValid(
                  true,
                  m_buy_levels[index].target_price
               ))
               return;
            m_buy_levels[index].volume=(
               m_profile.lots[index]*
               m_profile.trend_rescue_volume_multiplier
            );
            // The rescue path doubles volume (trend_rescue_volume_multiplier),
            // so it is the FIRST thing to hit max_gross_lots -- and it used to
            // be the only ExposureAllowsRearm site that returned without a log.
            // A rescue that silently no-ops leaves the trend side starved (see
            // PendingPriceIsValid, ~1312) with nothing in telemetry to explain
            // it.  guard_envelope.py measured why this matters: the Target's
            // heaviest final-regime cycle peaked at 2.10 gross lots against the
            // 2.20 cap in latest_30_real_safe.set, a 4.5% margin.
            if(!ExposureAllowsRearm(m_buy_levels[index].volume))
              {
               LogLifecycleEvent(
                  "safety_rearm_blocked",
                  StringFormat("STR B%d",m_buy_levels[index].level),
                  "max_gross_lots_rescue"
               );
               return;
              }
            if(PlaceLevel(m_buy_levels[index]))
              {
               ClearTrendRescueReplacement(m_buy_levels[index],index);
               PersistCycle();
              }
            return;
           }
         if(m_sell_levels[index].has_position)
           {
            ClearTrendRescueReplacement(m_sell_levels[index],index);
            PersistCycle();
            return;
           }
         if(m_sell_levels[index].has_pending)
           {
            if(OrderSelect(m_sell_levels[index].order_ticket) &&
               !IsBaseLevelVolume(
                  index,
                  OrderGetDouble(ORDER_VOLUME_CURRENT)
               ))
              {
               ClearTrendRescueReplacement(m_sell_levels[index],index);
               PersistCycle();
              }
            return;
           }
         if(!PendingPriceIsValid(
               false,
               m_sell_levels[index].target_price
            ))
            return;
         m_sell_levels[index].volume=(
            m_profile.lots[index]*
            m_profile.trend_rescue_volume_multiplier
         );
         // Sell-side twin of the buy-side rescue block above: log the block so a
         // starved trend side is diagnosable instead of mysterious.
         if(!ExposureAllowsRearm(m_sell_levels[index].volume))
           {
            LogLifecycleEvent(
               "safety_rearm_blocked",
               StringFormat("STR S%d",m_sell_levels[index].level),
               "max_gross_lots_rescue"
            );
            return;
           }
         if(PlaceLevel(m_sell_levels[index]))
           {
            ClearTrendRescueReplacement(m_sell_levels[index],index);
            PersistCycle();
           }
         return;
        }
      int completed_side=m_trend_rescue_side;
      m_trend_rescue_side=0;
      m_trend_rescue_replacing=false;
      m_trend_rescue_mask=0;
      PersistCycle();
      LogEvent(
         "trend_rescue_complete",
         "",
         0,
         0.0,
         0.0,
         completed_side>0 ? "buy" : "sell"
      );
     }

   void ProcessTrendRescue(void)
     {
      if(!m_profile.trend_rescue_enabled)
         return;
      int trigger_side=TrendRescueSide();
      if(trigger_side==0 && m_trend_rescue_consumed_side!=0)
        {
         m_trend_rescue_consumed_side=0;
         PersistCycle();
        }
      if(m_trend_rescue_side==0)
        {
         if(trigger_side==0 ||
            trigger_side==m_trend_rescue_consumed_side ||
            !HasTrendRescueBasePending(trigger_side>0))
            return;
         m_trend_rescue_consumed_side=trigger_side;
         MarkTrendRescuePositionRearms(trigger_side>0);
         m_trend_rescue_side=trigger_side;
         m_trend_rescue_replacing=false;
         m_trend_rescue_mask=0;
         PersistCycle();
         LogEvent(
            "trend_rescue_start",
            "",
            0,
            0.0,
            0.0,
            trigger_side>0 ? "buy" : "sell"
         );
        }
      if(m_profile.deployment_fill_cooldown_seconds>0 &&
         m_last_entry_fill_at>0 &&
         TimeCurrent()-m_last_entry_fill_at<
            m_profile.deployment_fill_cooldown_seconds)
         return;
      bool is_buy=(m_trend_rescue_side>0);
      if(!m_trend_rescue_replacing)
        {
         if(TryCancelOneTrendRescueOrder(is_buy))
            return;
         m_trend_rescue_replacing=true;
         PersistCycle();
        }
      PlaceOneTrendRescueReplacement(is_buy);
     }

   double OwnedGrossLots(void) const
     {
      double total=0.0;
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)>0 && IsOwnedPositionSelected())
            total+=PositionGetDouble(POSITION_VOLUME);
        }
      return total;
     }

   bool ExposureAllowsRearm(const double volume) const
     {
      if(!m_runtime.safety_enabled ||
         m_runtime.max_gross_lots<=0.0)
         return true;
      return(
         OwnedGrossLots()+volume<=
         m_runtime.max_gross_lots+0.0000001
      );
     }

   double TodayOwnedProfit(void) const
     {
      MqlDateTime now={};
      TimeToStruct(TimeCurrent(),now);
      now.hour=0;
      now.min=0;
      now.sec=0;
      datetime day_start=StructToTime(now);
      if(!HistorySelect(day_start,TimeCurrent()))
         return 0.0;
      double total=0.0;
      for(int index=0;index<HistoryDealsTotal();index++)
        {
         ulong ticket=HistoryDealGetTicket(index);
         if(ticket==0)
            continue;
         if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=m_runtime.magic ||
            HistoryDealGetString(ticket,DEAL_SYMBOL)!=m_runtime.symbol)
            continue;
         total+=HistoryDealGetDouble(ticket,DEAL_PROFIT)
               +HistoryDealGetDouble(ticket,DEAL_SWAP)
               +HistoryDealGetDouble(ticket,DEAL_COMMISSION)
               +HistoryDealGetDouble(ticket,DEAL_FEE);
        }
      return total;
     }

   bool SafetyTriggered(string &reason) const
     {
      if(!m_runtime.safety_enabled)
         return false;
      double equity=AccountInfoDouble(ACCOUNT_EQUITY);
      if(m_runtime.max_equity_loss_pct>0.0 && m_cycle_start_balance>0.0)
        {
         double loss_pct=100.0*(m_cycle_start_balance-equity)/m_cycle_start_balance;
         if(loss_pct>=m_runtime.max_equity_loss_pct)
           {
            reason="equity_loss";
            return true;
           }
        }
      if(m_runtime.max_gross_lots>0.0 && OwnedGrossLots()>m_runtime.max_gross_lots)
        {
         reason="gross_lots";
         return true;
        }
      MqlTick tick={};
      if(m_runtime.max_spread_points>0.0 &&
         SymbolInfoTick(m_runtime.symbol,tick) &&
         (tick.ask-tick.bid)/m_point>m_runtime.max_spread_points)
        {
         reason="spread";
         return true;
        }
      if(m_runtime.daily_loss_limit>0.0 && TodayOwnedProfit()<=-m_runtime.daily_loss_limit)
        {
         reason="daily_loss";
         return true;
        }
      return false;
     }

   void BeginClose(const string reason,const bool halt_after)
     {
      if(m_state==CYCLE_CLOSING || m_state==CYCLE_CANCELING || m_state==CYCLE_HALTED)
         return;
      m_halted=halt_after;
      // Kept in lockstep with m_halted so the terminal "halted" event can name the
      // guard.  Only ever READ while m_halted is true, so the m_halted=false reset
      // sites do not need to clear it.
      m_halt_reason=(halt_after ? reason : "");
      ENUM_CYCLE_STATE replica_close_state=
         (m_profile.cancel_before_close ? CYCLE_CANCELING : CYCLE_CLOSING);
      m_state=(halt_after ? CYCLE_CLOSING : replica_close_state);
      m_last_close_at=0;
      m_close_skip=0;
      PersistCycle();
      LogEvent("close_begin","",0,0.0,0.0,reason);
     }

   // True when the close pacer permits another close request.  Factored out of
   // CloseOnePosition because the CYCLE_RESTARTING handler drains leftover
   // positions by calling TryCloseOneOwnedPosition directly, and without this it
   // drained them at the OnTimer period (100 ms) instead of at
   // close_interval_seconds.  On 111638511 that produced runs of 2-4 market
   // closes 39-127 ms apart on consecutive order tickets -- a cadence the Target
   // never shows (0.2% of its stream in sub-100 ms clusters, versus 11.0% of
   // ours).  Every close request must pass through here.
   bool CloseIntervalElapsed(void) const
     {
      if(m_shadow_reset_active || m_halted)
         return true;
      if(m_profile.close_interval_seconds<=0 || m_last_close_at<=0)
         return true;
      return TimeCurrent()-m_last_close_at>=m_profile.close_interval_seconds;
     }

   // Issues AT MOST ONE close request per invocation.  An older version kept
   // walking the position list after a failed ClosePosition and closed the next
   // one in the same tick, which is how several synchronous OrderSend round-trips
   // ended up inside one 100 ms tick.
   //
   // The anti-stall property that motivated that loop is preserved by
   // m_close_skip: a ticket whose close failed is stepped over on the NEXT
   // invocation rather than in the same one, so a single quote-delayed ticket
   // still cannot block the basket -- it just costs one pacing interval instead
   // of firing a burst.
   //
   // THE WALK DIRECTION IS DESCENDING, AND THAT IS DELIBERATE.  MT5 appends new
   // positions to the end of the list, so a descending walk closes the most
   // recently opened leg first -- LIFO.  The Target's flatten sweep is LIFO:
   // tools/forensics/sweep_lifo.py measures a pair-inversion rate of 0.983 over
   // its 29 post-break sweeps, with 14 of those 29 in EXACTLY reverse-of-open
   // order and 0 of 29 in open order (pre-break: 0.853, 60 exactly reverse, 1
   // exactly forward out of 219).
   //
   // Commit 9a0cf62 briefly changed this to an ascending walk on the stated
   // grounds that the Target "closes positions in ascending level order", citing
   // an audit_sweep_order.py that is not in this repository.  That claim does not
   // reproduce.  tools/forensics/sweep_level_order.py reads the level straight off
   // the Target's OWN position comments -- "STR B7" / "STR S12" matches 17,515 of
   // its 17,632 positions (99.3%) and 1,097 of 1,097 post-break (100.0%) -- and
   // finds NO level ordering at all:
   //
   //   stream               sweeps  legs  median rho(order, level)  inner  outer
   //   Target pre-break        219  2250          -0.086              54     63
   //   Target post-break        29   255          -0.400               2     13
   //
   // Post-break the sign is NEGATIVE and outer-first sweeps outnumber inner-first
   // 13 to 2.  Ascending is the one direction the evidence excludes.  (A geometric
   // reconstruction from the fitted lattice is kept in that script as a
   // cross-check; it agrees with our own comments 47/47 and 31/31 but carries a
   // systematic off-by-one on Target cycles -- 86.1% agreement pre-break, 54.5%
   // post-break, always geo = comment + 1 -- so do not use it for an absolute
   // level.  Being off by one is monotone, which is why it reaches the same
   // verdict.)
   //
   // Level and open time are decoupled here because level is a PER-SIDE
   // coordinate: each wing numbers outward from the anchor independently, so
   // "newest" only means "outermost" inside a one-sided trend.  An earlier note in
   // this repository inferred "newest-first therefore outer-levels-first" from
   // rho(order, open time) = -0.994.  The measurement was right; the inference was
   // not.
   //
   // Do not re-flip this loop to ascending without first re-running sweep_lifo.py
   // and showing the Target's inversion rate below 0.5.  Closing inner legs first
   // to reduce drift exposure during the paced sweep would be a deliberate
   // DIVERGENCE from the Target, and pacing has already been measured as a
   // variance term rather than a bias term: rho(sweep span, cycle exit) = +0.015
   // across 91 Target sweeps (flatten_order.py Panel C).
   // Leak-mode sweep.  Walks ONLY the tickets the level table still points at,
   // strictly descending by ticket -- the exact reverse-of-ticket LIFO measured
   // on all 3,718 Target sweep closes -- so orphans are never swept.  On the
   // Starwave tape not one of the 146 baskets left the book flat and 148 of the
   // 153 orphans survived at least one complete sweep, 66 of them 61 or more.
   bool TryCloseOneTrackedPosition(void)
     {
      ulong tickets[];
      int count=CollectTrackedPositionTickets(tickets);
      int owned=0;
      for(int index=count-1;index>=0;index--)
        {
         owned++;
         if(owned<=m_close_skip)
            continue;
         ulong ticket=tickets[index];
         if(!PositionSelectByTicket(ticket) || !IsOwnedPositionSelected())
            continue;
         double volume=PositionGetDouble(POSITION_VOLUME);
         double price=PositionGetDouble(POSITION_PRICE_CURRENT);
         string comment=PositionGetString(POSITION_COMMENT);
         if(m_gateway.ClosePosition(ticket,CloseComment()))
           {
            m_last_close_at=TimeCurrent();
            m_close_skip=0;
            LogEvent("close",comment,ticket,volume,price,CloseComment());
            return true;
           }
         m_last_close_at=TimeCurrent();
         m_close_skip++;
         return false;
        }
      m_close_skip=0;
      return false;
     }

   // Basket-close comment.  The Target ran two builds over the 901018 window and
   // they stamp the sweep differently: inside HISTORICAL_50 and HISTORICAL_60 all
   // 2,724 basket closes carry an EMPTY comment and not one carries "STR CLOSE",
   // while every one of the 1,010 "STR CLOSE" closes falls inside the
   // anchor-divisor eras (AGGRESSIVE_30 9, LOW_RISK_30 11, STARWAVE_30 990).  The
   // two families are the same mechanism, not different actions: all 3,742 orders
   // resolve to DEAL_ENTRY_OUT deals (2732/2732 and 1010/1010), both run the same
   // ~105 ms machine cadence, and their windows partition the tape cleanly at the
   // 2026.07.13 12:28 changeover.  See parity audit DIV-3.
   string CloseComment(void) const
     {
      return(m_profile.stamp_close_comment ? "STR CLOSE" : "");
     }

   bool TryCloseOneOwnedPosition(void)
     {
      if(OrphanLeakActive())
         return TryCloseOneTrackedPosition();
      int owned=0;
      for(int index=PositionsTotal()-1;index>=0;index--)
        {
         ulong ticket=PositionGetTicket(index);
         if(ticket==0 || !IsOwnedPositionSelected())
            continue;
         owned++;
         if(owned<=m_close_skip)
            continue;
         double volume=PositionGetDouble(POSITION_VOLUME);
         double price=PositionGetDouble(POSITION_PRICE_CURRENT);
         string comment=PositionGetString(POSITION_COMMENT);
         if(m_gateway.ClosePosition(ticket,CloseComment()))
           {
            m_last_close_at=TimeCurrent();
            m_close_skip=0;
            LogEvent("close",comment,ticket,volume,price,CloseComment());
            return true;
           }
         m_last_close_at=TimeCurrent();
         m_close_skip++;
         return false;
        }
      // Either there are no owned positions, or the cursor has walked past the
      // last one.  Rewind so the next pass starts from the top again.
      m_close_skip=0;
      return false;
     }

   void CloseOnePosition(void)
     {
      if(CyclePositionCount()>0 && !CloseIntervalElapsed())
         return;
      if(TryCloseOneOwnedPosition())
         return;
      // A close that FAILED must not be read as "the basket is flat".  Without
      // this the engine declared cycle_complete/flat on a transient rejection and
      // dropped into CYCLE_RESTARTING with positions still open, which is the
      // state that used to hammer them at the timer period.
      if(CyclePositionCount()>0)
         return;
      if(m_shadow_reset_active)
        {
         if(OwnedOrderCount()>0)
            m_state=CYCLE_CANCELING;
         else
            CompleteShadowReset();
         return;
        }
      if(!m_halted && m_profile.cancel_before_close)
        {
         m_state=CYCLE_RESTARTING;
         m_restart_started_at=TimeCurrent();
         LogLifecycleEvent("cycle_complete","","flat");
         LogEvent("restart_wait","",0,0.0,0.0,"");
        }
      else
         m_state=CYCLE_CANCELING;
      PersistCycle();
     }

   bool TryCancelOneOwnedOrder(void)
     {
      for(int index=OrdersTotal()-1;index>=0;index--)
        {
         ulong ticket=OrderGetTicket(index);
         if(ticket==0 || !IsOwnedOrderSelected())
            continue;
         string comment=OrderGetString(ORDER_COMMENT);
         double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
         double price=OrderGetDouble(ORDER_PRICE_OPEN);
         if(m_gateway.DeleteOrder(ticket))
            LogEvent("cancel",comment,ticket,volume,price,comment);
         return true;
        }
      return false;
     }

   void CancelOneOrder(void)
     {
      if(TryCancelOneOwnedOrder())
         return;
      if(m_shadow_reset_active)
        {
         if(CyclePositionCount()>0)
           {
            m_state=CYCLE_CLOSING;
            m_last_close_at=0;
            m_close_skip=0;
           }
         else
            CompleteShadowReset();
         return;
        }
      if(!m_halted &&
         m_profile.cancel_before_close &&
         CyclePositionCount()>0)
        {
         m_state=CYCLE_CLOSING;
         m_last_close_at=0;
         m_close_skip=0;
         PersistCycle();
         return;
        }
      if(m_halted)
        {
         m_state=CYCLE_HALTED;
         LogLifecycleEvent("cycle_complete","","flat");
         // Name the guard on the terminal event.  CYCLE_HALTED has no automatic
         // exit, so this is the last thing the EA ever says: it must be
         // self-diagnosing.  Empty here previously.
         LogEvent("halted","",0,0.0,0.0,m_halt_reason);
         ClearPersistence();
        }
      else
        {
         m_state=CYCLE_RESTARTING;
         m_restart_started_at=TimeCurrent();
         LogLifecycleEvent("cycle_complete","","flat");
         PersistCycle();
         LogEvent("restart_wait","",0,0.0,0.0,"");
        }
     }

   // Trails the CURRENTLY SELECTED position one step.  Returns true only when a
   // stop modification was actually issued, so callers can honour
   // max_stop_updates_per_pass.
   bool TrailSelectedPosition(const MqlTick &tick,const ulong ticket)
     {
      ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double current_sl=PositionGetDouble(POSITION_SL);
      double desired=0.0;
      if(!m_stop_scheduler.Calculate(
            type,
            entry,
            current_sl,
            tick.bid,
            tick.ask,
            m_step,
            m_tick_size,
            (int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS),
            m_point,
            SymbolInfoInteger(
               m_runtime.symbol,
               SYMBOL_TRADE_STOPS_LEVEL
            ),
            m_profile,
            desired))
         return false;
      if(!m_gateway.ModifyPosition(ticket,desired))
         return false;
      LogEvent("stop",PositionGetString(POSITION_COMMENT),ticket,
               PositionGetDouble(POSITION_VOLUME),desired,"");
      return true;
     }

   // Leak-mode trail.  Orphans are NEVER trailed: not one of the Target's 153
   // orphans ever received an [sl] order, across 1-9 days of XAUUSD movement,
   // while 1,311 tracked positions did.  Walking the tracked array (ascending by
   // ticket, reversed when stop_scan_newest_first) preserves LATEST_30's
   // newest-first single-update-per-pass cadence exactly.
   void UpdateTrackedPositionStops(const MqlTick &tick)
     {
      ulong tickets[];
      int count=CollectTrackedPositionTickets(tickets);
      if(m_profile.stop_scan_newest_first && count>1)
         ArrayReverse(tickets);
      int update_count=0;
      for(int index=0;index<count;index++)
        {
         if(!PositionSelectByTicket(tickets[index]) || !IsOwnedPositionSelected())
            continue;
         if(!TrailSelectedPosition(tick,tickets[index]))
            continue;
         update_count++;
         if(m_profile.max_stop_updates_per_pass>0 &&
            update_count>=m_profile.max_stop_updates_per_pass)
            return;
        }
     }

   void UpdatePositionStops(void)
     {
      datetime now=TimeCurrent();
      if(m_profile.stop_update_interval_seconds>0 &&
         m_last_stop_update_at>0 &&
         now-m_last_stop_update_at<m_profile.stop_update_interval_seconds)
         return;
      m_last_stop_update_at=now;

      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick))
         return;
      if(OrphanLeakActive())
        {
         UpdateTrackedPositionStops(tick);
         return;
        }
      int position_total=PositionsTotal();
      int update_count=0;
      for(int offset=0;offset<position_total;offset++)
        {
         int index=(m_profile.stop_scan_newest_first
                    ? position_total-1-offset
                    : offset);
         ulong ticket=PositionGetTicket(index);
         if(ticket==0 || !IsOwnedPositionSelected())
            continue;
         if(!TrailSelectedPosition(tick,ticket))
            continue;
         update_count++;
         if(m_profile.max_stop_updates_per_pass>0 &&
            update_count>=m_profile.max_stop_updates_per_pass)
            return;
        }
     }

public:
                     CStraddleEngine(void)
     {
      m_state=CYCLE_IDLE;
      m_anchor=0.0;
      m_step=0.0;
      m_tick_size=0.0;
      m_point=0.0;
      m_cycle_start_balance=0.0;
      m_cycle_realized=0.0;
      m_cycle_exit_deal_count=0;
      m_cycle_started_at=0;
      m_cycle_started_utc=0;
      m_cycle_started_msc=0;
      m_cycle_started_ms=0;
      m_restart_started_at=0;
      m_last_close_at=0;
      m_close_skip=0;
      m_last_entry_fill_at=0;
      m_last_stop_update_at=0;
      m_deploy_index=0;
      m_has_traded=false;
      m_halted=false;
      m_atr_handle=INVALID_HANDLE;
      m_cycle_id="";
        m_shadow_last_command_seq=0;
        m_event_sequence=0;
        m_last_processed_deal_ticket=0;
        m_processed_deal_count=0;
        ArrayResize(m_processed_deal_tickets,0);
        m_pending_deal_count=0;
        ArrayInitialize(m_pending_deal_tickets,0);
         m_last_history_reconcile_ms=0;
         m_history_reconcile_seeded=false;
         m_shadow_reset_active=false;
         m_alignment_hold_logged=false;
       // NOT reset by ResetLevelState(): the orphan set must outlive every cycle
       // boundary, because a displaced position stays untracked for good.
       ResetOrphanTickets();
       ResetLevelState();
      }

   bool Initialize(const SRuntimeConfig &runtime,
                   const ENUM_STR_PROFILE selected_profile,
                   const SCustomProfileConfig &custom)
     {
      m_runtime=runtime;
      if(m_runtime.symbol=="")
         m_runtime.symbol=_Symbol;
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         ((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=
          ACCOUNT_TRADE_MODE_DEMO ||
          m_runtime.expected_account_login==0 ||
          m_runtime.shadow_command_file=="" ||
          m_runtime.shadow_ack_file=="" ||
          m_runtime.shadow_command_max_age_ms<1))
        {
         Print("[STR] Shadow mode requires a demo account and valid command settings.");
         return false;
        }
      if(m_runtime.require_demo_account &&
         (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=
         ACCOUNT_TRADE_MODE_DEMO)
        {
         Print("[STR] Initialization refused: a demo account is required.");
         return false;
        }
      if(m_runtime.require_bound_account &&
         m_runtime.expected_account_login==0)
        {
         Print("[STR] Initialization refused: bound account login is required.");
         return false;
        }
      if(m_runtime.expected_account_login>0 &&
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN)!=
         m_runtime.expected_account_login)
        {
         PrintFormat(
            "[STR] Initialization refused: login=%I64u expected=%I64u.",
            (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
            m_runtime.expected_account_login
         );
         return false;
        }
      if((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
        {
         Print("[STR] A hedging account is required.");
         return false;
        }
      if(!SymbolSelect(m_runtime.symbol,true))
        {
         PrintFormat("[STR] Unable to select symbol %s",m_runtime.symbol);
         return false;
        }
      m_deal_ledger.Configure(m_runtime.magic,m_runtime.symbol);
      bool profile_loaded=(selected_profile==CUSTOM_PROFILE
                           ? LoadCustomProfile(custom,m_profile)
                           : LoadProfileConfig(selected_profile,m_profile));
      if(!profile_loaded)
        {
         Print("[STR] Invalid strategy profile.");
         return false;
        }
      long order_limit=AccountInfoInteger(ACCOUNT_LIMIT_ORDERS);
      if(order_limit>0 &&
         order_limit<m_profile.levels_per_side*2 &&
         m_runtime.runtime_mode!=STR_RUNTIME_SHADOW)
        {
         PrintFormat("[STR] Account order limit %d is below required %d.",
                     order_limit,m_profile.levels_per_side*2);
         return false;
        }

      m_tick_size=SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_SIZE);
      m_point=SymbolInfoDouble(m_runtime.symbol,SYMBOL_POINT);
      if(m_tick_size<=0.0 || m_point<=0.0)
        {
         Print("[STR] Invalid symbol tick configuration.");
         return false;
        }
      m_gateway.Initialize(m_runtime.symbol,m_runtime.magic,m_runtime.deviation_points);
      if(m_profile.step_mode==STR_STEP_ATR)
        {
         m_atr_handle=iATR(m_runtime.symbol,m_profile.atr_timeframe,m_profile.atr_period);
         if(m_atr_handle==INVALID_HANDLE)
           {
            PrintFormat("[STR] Unable to create ATR handle error=%d",GetLastError());
            return false;
           }
        }
      m_telemetry_file=StringFormat("StraddleReplicaV2_%I64u_%s.csv",
                                    m_runtime.magic,m_runtime.symbol);
      WriteRuntimeManifest();
       // A fresh Initialize() is a fresh binary lifetime: the Target holds its
       // orphan set in RAM only, so a terminal restart or an input change makes
       // it re-derive newest-per-level from an empty set.  That is exactly what
       // the Target did at 2026-08-27 08:23 (59 cancels in 33 ms, then re-place
       // at the identical anchor with a new ladder) and it is safety-positive:
       // the worst case is that a previously hidden position becomes tracked
       // again and therefore gets trailed and swept.
       ResetOrphanTickets();
       ResetLevelState();
       m_state=CYCLE_IDLE;
       m_halted=false;
       m_alignment_hold_logged=false;
       string restored_shadow_cycle="";
      string restored_shadow_status="";
      SShadowCommand restored_shadow_command={};
      bool has_restored_shadow_command=false;
      bool shadow_command_available=false;
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
        {
         FolderCreate("StraddleShadow",FILE_COMMON);
         RestoreShadowSequence();
         ulong acknowledged_sequence=0;
         string acknowledged_status="";
         string acknowledged_cycle="";
         if(ReadShadowAckState(acknowledged_sequence,
                               acknowledged_status,
                               acknowledged_cycle))
           {
            if(acknowledged_sequence>m_shadow_last_command_seq)
               m_shadow_last_command_seq=acknowledged_sequence;
            restored_shadow_cycle=acknowledged_cycle;
            restored_shadow_status=acknowledged_status;
           }
         if(ReadShadowCommand(restored_shadow_command))
           {
            shadow_command_available=true;
            if(restored_shadow_command.command_seq==
               m_shadow_last_command_seq)
              {
               has_restored_shadow_command=true;
               if(restored_shadow_cycle=="" &&
                  restored_shadow_command.command=="START")
                  restored_shadow_cycle=restored_shadow_command.cycle_id;
              }
           }
         PersistShadowSequence();
        }
      bool has_owned_cycle=(OwnedOrderCount()>0 || OwnedPositionCount()>0);
      bool has_persisted_restart=(
         !has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_NORMAL &&
         GlobalVariableCheck(GlobalKey("state")) &&
         (ENUM_CYCLE_STATE)(int)GlobalVariableGet(GlobalKey("state"))==
         CYCLE_RESTARTING
      );
      bool adopted_existing_shadow_cycle=false;
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         shadow_command_available &&
         restored_shadow_command.command=="START" &&
         restored_shadow_command.command_seq>=m_shadow_last_command_seq)
        {
         restored_shadow_cycle=restored_shadow_command.cycle_id;
         m_shadow_last_command_seq=restored_shadow_command.command_seq;
         has_restored_shadow_command=true;
         PersistShadowSequence();
        }
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         restored_shadow_cycle=="")
        {
         if(!m_runtime.allow_shadow_adopt_existing_cycle)
           {
            Print("[STR] existing_cycle_adoption_disabled: shadow cycle identity could not be restored safely.");
            return false;
           }
         if(!AdoptExistingShadowCycle())
           {
            Print("[STR] Existing shadow cycle adoption failed safely.");
            return false;
           }
         adopted_existing_shadow_cycle=true;
         restored_shadow_cycle=m_cycle_id;
         restored_shadow_status="ADOPTED";
        }
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         !adopted_existing_shadow_cycle)
         m_cycle_id=restored_shadow_cycle;
      if((has_owned_cycle || has_persisted_restart) &&
         !adopted_existing_shadow_cycle &&
         !RestoreCycle())
        {
         Print("[STR] Existing cycle could not be restored safely.");
         return false;
        }
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         (restored_shadow_status=="RESETTING" ||
          (has_restored_shadow_command &&
           restored_shadow_command.command=="RESET")))
        {
         m_shadow_reset_active=true;
         BeginShadowReset();
         WriteShadowAck("RESETTING",
                        m_shadow_last_command_seq,
                        "restored");
        }
      else if(has_owned_cycle &&
              m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
              has_restored_shadow_command &&
              restored_shadow_command.command=="START" &&
              restored_shadow_status!="STARTED")
         WriteShadowAck("STARTED",
                        m_shadow_last_command_seq,
                        "restored");
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
        {
         if(!has_owned_cycle)
           {
            m_cycle_id="";
            WriteShadowAck("FLAT",m_shadow_last_command_seq,"initialized");
           }
        }
      int timer_ms=MathMax(20,m_runtime.inter_order_delay_ms);
      if(!EventSetMillisecondTimer(timer_ms))
        {
         PrintFormat("[STR] Unable to start millisecond timer error=%d",GetLastError());
         return false;
        }
      PrintFormat("[STR] Initialized profile=%s symbol=%s levels=%d replica=%s mode=%s",
                  EnumToString(selected_profile),
                  m_runtime.symbol,
                  m_profile.levels_per_side,
                  (m_runtime.replica_mode ? "true" : "false"),
                  EnumToString(m_runtime.runtime_mode));
      return true;
     }

   void Shutdown(void)
     {
      EventKillTimer();
      PersistCycle();
      if(m_atr_handle!=INVALID_HANDLE)
        {
         IndicatorRelease(m_atr_handle);
         m_atr_handle=INVALID_HANDLE;
        }
     }

   void OnTick(void)
     {
       if(m_state==CYCLE_IDLE)
         {
          if(AlignmentHoldActive())
            {
             UpdateAlignmentHoldTelemetry(true);
             return;
            }
          UpdateAlignmentHoldTelemetry(false);
          if(m_pending_deal_count>0)
             return;
         if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
            return;
         if(StartCycle())
            DeployOne();
         return;
        }
       if(m_state!=CYCLE_RUNNING)
          return;
       ReconcileLevels();
       if(!m_profile.stop_updates_on_timer)
          UpdatePositionStops();

       CheckCycleTargets();
      }

    void CheckCycleTargets(void)
      {
       if(m_state!=CYCLE_RUNNING && m_state!=CYCLE_DEPLOYING)
          return;
       if(CyclePositionCount()>0)
          m_has_traded=true;
       if(!m_has_traded && CyclePositionCount()==0)
          return;

       string safety_reason="";
       if(SafetyTriggered(safety_reason))
         {
          BeginClose(safety_reason,true);
          return;
         }

       double scale=ContractScale();
       double target=(m_profile.cycle_target_money>0.0
                      ? m_profile.cycle_target_money*scale
                      : m_cycle_start_balance*m_profile.cycle_target_balance_pct/100.0);
       // Target EA parity: the basket sums ONLY the positions the level table
       // still points at.  Orphans contribute neither profit nor a position to
       // the trigger, which is why several Target sweeps fired on a tracked net
       // near the target while the raw book net was far away from it.
       double floating=CycleFloatingProfit();
       int open_pos_count=CyclePositionCount();
       SBasketSnapshot basket=m_basket_evaluator.Evaluate(
          m_cycle_realized,
          floating,
          target,
          m_has_traded,
          open_pos_count
       );
       if(basket.triggered)
         {
          LogLifecycleEvent("basket_trigger","","threshold_reached");
          BeginClose("basket_target",false);
          return;
         }

       // ------------------------------------------------------------------
       // The $30 basket target above is the Target EA's ONLY money exit.
       //
       // Two further exit rules previously lived here -- a 20-point
       // "grid_recenter" and a "rescue_breakeven" liquidation.  Both were
       // written from the mission brief's hypotheses and never measured.
       // Both are now refuted against the 901018 dataset (100 final-regime
       // cycles delimited by their own flatten sweeps).  See
       // tools/forensics/q3p_replicarules.py for the scoring harness; it
       // reports, for every candidate rule, the first tick at which the rule
       // would have fired versus the tick at which the Target EA actually
       // closed:
       //
       //   grid_recenter   (dist>=20 || (realized>=50 && net>=-20 && dist>=15))
       //       would fire on 49/100 cycles, 27 of them >5 min early, at a
       //       median net of -$19.36 where the Target EA went on to bank
       //       +$36.00.  Aggregate profit destroyed: $5,738.88.  Both clauses
       //       are equally culpable (27 and 26 of 100).  The distance gate
       //       does not even separate the exit groups: cycles that exited on
       //       the money target were >=20 pts from the anchor 18/72 of the
       //       time, versus 1/6 for the below-zero exits.
       //
       //   rescue_breakeven (realized>=200 && net>=-10)
       //       would fire on 14/100 cycles, 9 of them >5 min early, at a
       //       median net of +$10.16 where the Target EA banked +$42.62.
       //       Aggregate profit destroyed: $623.52.  Decisively, the marked
       //       total at exit has ZERO cycles in [-25,0) under two independent
       //       segmentations -- a "close at breakeven" rule would pile up
       //       exactly there.
       //
       // A flat threshold on realized_since_cycle_start + floating is the
       // whole rule.  FOUR independent estimators agree on its value:
       // exact burst-flatten total 29.31, whole-sweep total 29.36,
       // decision-instant marked total 30.46, and -- the only one that needs
       // no price mark at all -- the median money actually BANKED at the exit
       // across 99 cycles, 29.32.  That last one is the load-bearing figure:
       // a flatten closes the whole basket, so realised-at-exit IS the total
       // the EA saw, with no bid/ask model and no stale-mark exposure.
       // A size-scaled threshold (net >= k * $/pt, or k * open_positions) is
       // refuted outright: 0/100 cycles fire at the decision and 97/100 fire
       // prematurely.
       //
       // The exit VALUES scatter widely (only 29/99 inside [25,35], tails to
       // +632 and -108) and that scatter is NOT a missing rule.  The basket
       // carries 20-170 $/pt of gross exposure, so the decision variable
       // moves in jumps of $3-30 per tick and cannot land on 30.  Dividing
       // each overshoot by its own gross sensitivity gives the price move
       // needed to explain it: median 0.83 pt, and 46 of 47 inside the
       // 6.79 pt dispersion measured inside the flatten sweeps themselves.
       // Undershoots need 0.91 pt.  Same magnitude, opposite sign, one
       // mechanism -- price moving faster than a basket can be valued.  A
       // hold rule would give a one-sided right tail; a second exit rule a
       // one-sided left tail.  The symmetry is what rules both out.
       //
       // An earlier note here claimed 5-13 cycles held above $30 without
       // closing.  RETRACTED.  That came from a mark-walk whose error, at the
       // Target's own flatten instant where the true value is known to be 30,
       // is median 25.23 with p10 -35.59 / p90 +47.70 -- a p90 of $102.30 per
       // reading, i.e. 3.4x the threshold it was being used to test.  Every
       // "gated" cycle resolves as ordinary tick noise (194 -> 1.20 pt,
       // 187 -> 1.62, 250 -> 2.41, 253 -> 4.44, 252 -> 6.41).
       //
       // Do not reintroduce a distance, drawdown or breakeven exit without
       // first re-running q3o/q3p and showing a median lead near zero.  And
       // do not re-open the threshold question with a mark-based script: use
       // tools/forensics/basket_resolution.py, which is mark-free, and check
       // any new estimator against value@t0 before believing it.
       // ------------------------------------------------------------------
      }

   int PendingDealIndex(const ulong deal_ticket) const
     {
      for(int index=0;index<m_pending_deal_count;index++)
         if(m_pending_deal_tickets[index]==deal_ticket)
            return index;
      return -1;
     }

   void RemovePendingDealAt(const int remove_index)
     {
      if(remove_index<0 || remove_index>=m_pending_deal_count)
         return;
      for(int index=remove_index;index<m_pending_deal_count-1;index++)
         m_pending_deal_tickets[index]=m_pending_deal_tickets[index+1];
      m_pending_deal_count--;
      m_pending_deal_tickets[m_pending_deal_count]=0;
     }

   void QueuePendingDeal(const ulong deal_ticket)
     {
      if(deal_ticket==0 ||
         DealAlreadyProcessed(deal_ticket) ||
         PendingDealIndex(deal_ticket)>=0)
         return;
      if(m_pending_deal_count>=STR_PENDING_DEAL_CAPACITY)
        {
         PrintFormat(
            "[STR] Deal-history retry queue is full; ticket=%I64u.",
            deal_ticket
         );
         return;
        }
      m_pending_deal_tickets[m_pending_deal_count]=deal_ticket;
      m_pending_deal_count++;
      PrintFormat(
         "[STR] Deferred deal-history processing ticket=%I64u.",
         deal_ticket
      );
     }

   void QueueMissingHistoryDeals(void)
     {
      if(m_cycle_started_msc<=0 || m_cycle_id=="")
         return;
      ulong now_ms=GetTickCount64();
      if(m_last_history_reconcile_ms>0 &&
         now_ms-m_last_history_reconcile_ms<
            STR_HISTORY_RECONCILE_INTERVAL_MS)
         return;
      m_last_history_reconcile_ms=now_ms;
      long history_from_msc=m_cycle_started_msc;
      if(m_history_reconcile_seeded)
        {
         long lookback_from_msc=(
            CurrentServerMs()-STR_HISTORY_RECONCILE_LOOKBACK_MS
         );
         if(lookback_from_msc>history_from_msc)
            history_from_msc=lookback_from_msc;
        }
      if(!HistorySelect(
            (datetime)(history_from_msc/1000),
            TimeCurrent()
         ))
         return;
      m_history_reconcile_seeded=true;
      int deal_total=HistoryDealsTotal();
      for(int index=0;index<deal_total;index++)
        {
         ulong deal_ticket=HistoryDealGetTicket(index);
         if(deal_ticket==0 ||
            DealAlreadyProcessed(deal_ticket) ||
            PendingDealIndex(deal_ticket)>=0 ||
            (long)HistoryDealGetInteger(
               deal_ticket,
               DEAL_TIME_MSC
            )<m_cycle_started_msc ||
            (ulong)HistoryDealGetInteger(
               deal_ticket,
               DEAL_MAGIC
            )!=m_runtime.magic ||
            HistoryDealGetString(
               deal_ticket,
               DEAL_SYMBOL
            )!=m_runtime.symbol)
            continue;
         QueuePendingDeal(deal_ticket);
        }
     }

   bool ProcessSelectedDeal(const ulong deal_ticket)
     {
      if(DealAlreadyProcessed(deal_ticket))
         return true;
      if(!DealMetadataReady(deal_ticket))
         return false;
      if((ulong)HistoryDealGetInteger(deal_ticket,DEAL_MAGIC)!=m_runtime.magic ||
         HistoryDealGetString(deal_ticket,DEAL_SYMBOL)!=m_runtime.symbol)
         return true;
      ENUM_DEAL_ENTRY entry=
         (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal_ticket,DEAL_ENTRY);
      ulong position_id=
         (ulong)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID);
      ulong order_ticket=
         (ulong)HistoryDealGetInteger(deal_ticket,DEAL_ORDER);
      long deal_time_msc=
         (long)HistoryDealGetInteger(deal_ticket,DEAL_TIME_MSC);
      double deal_volume=HistoryDealGetDouble(deal_ticket,DEAL_VOLUME);
      double deal_price=HistoryDealGetDouble(deal_ticket,DEAL_PRICE);
      double deal_commission=
         HistoryDealGetDouble(deal_ticket,DEAL_COMMISSION);
      double deal_swap=HistoryDealGetDouble(deal_ticket,DEAL_SWAP);
      double deal_fee=HistoryDealGetDouble(deal_ticket,DEAL_FEE);
      double deal_profit=HistoryDealGetDouble(deal_ticket,DEAL_PROFIT);
      string level_comment=PositionCommentFromDeal(deal_ticket);
      if(level_comment=="")
         level_comment=HistoryDealGetString(deal_ticket,DEAL_COMMENT);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
        {
         m_has_traded=true;
         m_last_entry_fill_at=(datetime)(deal_time_msc/1000);
         WriteTelemetry("fill",level_comment,position_id,
                        deal_volume,deal_price,0.0,0.0,
                        level_comment,0,0,
                        deal_commission,deal_swap,deal_profit,
                        deal_ticket,
                        order_ticket,
                        position_id);
        }
      if(entry==DEAL_ENTRY_OUT ||
         entry==DEAL_ENTRY_OUT_BY ||
         entry==DEAL_ENTRY_INOUT)
        {
         double recalculated_realized=0.0;
         int recalculated_count=0;
         if(m_deal_ledger.TryRecalculate(
               m_cycle_started_msc,
               recalculated_realized,
               recalculated_count
            ) &&
            recalculated_count>m_cycle_exit_deal_count)
           {
            m_cycle_realized=recalculated_realized;
            m_cycle_exit_deal_count=recalculated_count;
           }
         else
           {
            m_cycle_realized=(
               m_cycle_realized+
               deal_profit+
               deal_swap+
               deal_commission+
               deal_fee
            );
            m_cycle_exit_deal_count++;
           }
         string exit_comment=HistoryDealGetString(deal_ticket,DEAL_COMMENT);
         ENUM_DEAL_REASON exit_reason=
            (ENUM_DEAL_REASON)HistoryDealGetInteger(
               deal_ticket,
               DEAL_REASON
            );
         bool is_stop=(exit_reason==DEAL_REASON_SL ||
                       StringFind(exit_comment,"[sl")==0 ||
                       StringFind(exit_comment,"sl ")==0);
         if(is_stop)
           {
            ScheduleLevelRearm(level_comment,deal_time_msc);
            LogLifecycleEvent("rearm_eligible",
                              level_comment,
                              "stop_exit");
            WriteTelemetry("stop_exit",level_comment,position_id,
                           deal_volume,deal_price,0.0,0.0,
                           level_comment,0,0,
                           deal_commission,deal_swap,deal_profit,
                           deal_ticket,
                           order_ticket,
                           position_id);
           }
         else
            WriteTelemetry("close_fill",level_comment,position_id,
                           deal_volume,deal_price,0.0,0.0,
                           level_comment,0,0,
                           deal_commission,deal_swap,deal_profit,
                           deal_ticket,
                           order_ticket,
                           position_id);
          PersistCycle();
         }
      RememberProcessedDeal(deal_ticket);
      return true;
     }

   void ProcessPendingDeals(void)
     {
      int index=0;
      while(index<m_pending_deal_count)
        {
         ulong deal_ticket=m_pending_deal_tickets[index];
         if(!HistoryDealSelect(deal_ticket) ||
            !DealMetadataReady(deal_ticket))
           {
            index++;
            continue;
           }
         if(ProcessSelectedDeal(deal_ticket))
            RemovePendingDealAt(index);
         else
            index++;
        }
     }

   void OnTimer(void)
     {
      QueueMissingHistoryDeals();
      ProcessPendingDeals();
      PollShadowCommand();
      switch(m_state)
        {
          case CYCLE_IDLE:
             if(AlignmentHoldActive())
               {
                UpdateAlignmentHoldTelemetry(true);
                break;
               }
             UpdateAlignmentHoldTelemetry(false);
             if(m_pending_deal_count>0)
                break;
            if(m_runtime.runtime_mode==STR_RUNTIME_NORMAL && StartCycle())
               DeployOne();
            break;
         case CYCLE_DEPLOYING:
            DeployOne();
            CheckCycleTargets();
            break;
          case CYCLE_RUNNING:
             ReconcileLevels();
             if(m_profile.stop_updates_on_timer)
                UpdatePositionStops();
             ProcessTrendRescue();
             if(m_trend_rescue_side==0)
                RearmOneMissingLevel();
             CheckCycleTargets();
             break;
         case CYCLE_CLOSING:
            CloseOnePosition();
            break;
         case CYCLE_CANCELING:
            CancelOneOrder();
             break;
          case CYCLE_RESTARTING:
             if(OwnedOrderCount()>0)
               {
                TryCancelOneOwnedOrder();
                break;
               }
              if(CyclePositionCount()>0)
                {
                 // Paced, exactly like CYCLE_CLOSING.  Reaching CYCLE_RESTARTING
                 // with positions still open means a close request was rejected;
                 // draining them at the OnTimer period turned that rejection into
                 // a burst of market closes milliseconds apart.  Cycle-scoped, so
                 // orphans cannot pin the engine in CYCLE_RESTARTING forever.
                 if(CloseIntervalElapsed())
                    TryCloseOneOwnedPosition();
                 break;
                }
              if(AlignmentHoldActive())
                {
                 UpdateAlignmentHoldTelemetry(true);
                 break;
                }
              UpdateAlignmentHoldTelemetry(false);
              if(TimeCurrent()-m_restart_started_at>=
                 (m_profile.restart_delay_ms+999)/1000)
               {
               m_state=CYCLE_IDLE;
               LogLifecycleEvent("cycle_restart","","new_cycle");
               if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
                  WriteShadowAck("READY",m_shadow_last_command_seq,"");
               ClearPersistence();
              }
            break;
         case CYCLE_HALTED:
            break;
        }
     }

   void OnTradeTransaction(const MqlTradeTransaction &transaction,
                           const MqlTradeRequest &request,
                           const MqlTradeResult &result)
     {
      if(transaction.type==TRADE_TRANSACTION_REQUEST &&
         request.magic==m_runtime.magic &&
         (request.symbol=="" || request.symbol==m_runtime.symbol))
         LogTradeRequest(request,result);
      if(transaction.type==TRADE_TRANSACTION_DEAL_ADD && transaction.deal>0)
        {
         if(!HistoryDealSelect(transaction.deal) ||
            !DealMetadataReady(transaction.deal))
            QueuePendingDeal(transaction.deal);
         else
           {
            int pending_index=PendingDealIndex(transaction.deal);
            if(pending_index>=0)
               RemovePendingDealAt(pending_index);
            ProcessSelectedDeal(transaction.deal);
           }
        }
      if(m_state==CYCLE_RUNNING || m_state==CYCLE_DEPLOYING)
         ReconcileLevels(false);
     }

   ENUM_CYCLE_STATE State(void) const { return m_state; }
   double Anchor(void) const { return m_anchor; }
   double Step(void) const { return m_step; }
  };

#endif


// ====================================================================
// SECTION: StraddleReplicaApp.mqh (Event Handlers & Inputs)
// ====================================================================

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
// This modular build's un-overridden defaults reproduce the Starwave / Target
// account (a standalone that pins the macros above ships different ones):
//   Profile     = STARWAVE_30  (N=30/side, step=round(anchor/3000,2),
//                               lots 0.01@1-10 / 0.06@11-20 / 0.15@21-30,
//                               ratchet L=2 Dpre=2 Tt=3 D=1, cancel-then-close,
//                               cycle_target_money=26.5, restart_delay_ms=2000)
//                              The money target is authoritative in
//                              ProfileCatalog.mqh (case STARWAVE_30); this
//                              summary previously said 25, which no profile uses.
//   MagicNumber = 26011001     measured on all 10,844 EA-authored rows of
//                              Starwave_60542_orders_history.csv; the other 19
//                              rows are magic 0 manual operator closes.
#ifndef STR_DEFAULT_MAGIC
   #define STR_DEFAULT_MAGIC 26011001
#endif

// included inline
// included inline

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
// 26.5, not the 25.0 this default carried until the basket target was solved:
// ProfileCatalog.mqh (case STARWAVE_30) brackets the measured value to
// (26.41, 26.51] from the 3-cycle censored run over 2026-08-24 19:22..19:49,
// which EXCLUDES 25.0.  Since cycle_target_money is the EA's only exit, a 25.0
// default made CUSTOM_PROFILE bank 5.66% early on every basket -- the one value
// in this block that was a placeholder rather than a measurement.
input double CustomCycleTargetMoney = 26.5;
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
