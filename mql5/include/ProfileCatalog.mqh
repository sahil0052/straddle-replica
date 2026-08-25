#ifndef STRADDLE_REPLICA_PROFILE_CATALOG_MQH
#define STRADDLE_REPLICA_PROFILE_CATALOG_MQH

#include "StraddleTypes.mqh"

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
   config.activation_uses_trailing_distance=false;
   config.pre_tighten_trail_distance_steps=2.0;
   config.tighten_trigger_steps=3.0;
   config.trail_distance_steps=2.0;
   config.cycle_target_balance_pct=0.18;
   config.cycle_target_money=0.0;
   config.cancel_before_close=false;
   config.deployment_fill_cooldown_seconds=0;
   config.close_interval_seconds=0;
   config.restart_delay_ms=3000;
   config.rearm_delay_seconds=0;
   config.stop_update_interval_seconds=0;
   config.max_stop_updates_per_pass=0;
   config.stop_scan_newest_first=false;
   config.stop_updates_on_timer=false;
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
         SetLotTier(config,1,15,0.01);
         SetLotTier(config,16,45,0.02);
         SetLotTier(config,46,60,0.05);
         return true;

      case AGGRESSIVE_30:
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor = 6000.0;
         config.trail_distance_steps=1.0;
         SetLotTier(config,1,10,0.08);
         SetLotTier(config,11,20,0.41);
         SetLotTier(config,21,30,0.82);
         return true;

      case LOW_RISK_30:
         config.levels_per_side=30;
         config.step_mode=STR_STEP_ANCHOR_DIVISOR;
         config.anchor_divisor = 3000.0;
         config.trail_distance_steps=1.0;
         SetLotTier(config,1,10,0.01);
         SetLotTier(config,11,20,0.02);
         SetLotTier(config,21,30,0.05);
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
         config.deployment_fill_cooldown_seconds=20;
         config.close_interval_seconds=20;
         config.restart_delay_ms=20000;
          // Target EA parity: level re-arms are modally 0-5s after a stop-out
          // (490 of 2,370 measured re-arms landed inside the first 5s bucket).
          config.rearm_delay_seconds=5;
          config.stop_scan_newest_first=true;
          config.max_stop_updates_per_pass=1;
          config.stop_updates_on_timer=true;
          config.trend_rescue_enabled=true;
          config.trend_rescue_timeframe=PERIOD_M15;
          config.trend_rescue_bars=6;
          config.trend_rescue_minimum_pending_levels=3;
          config.trend_rescue_move_price=20.0;
          // Target EA parity: reconstructed floating drawdown at the moment the
          // first 2x rescue order of each cycle was opened clusters at -$350 to
          // -$450 (Jul 17: -$444, Jul 28: -$354/-$357; the lone Jul 23 -$813
          // reading is a late re-trigger inside an already-rescued cycle).
          config.trend_rescue_drawdown_money=400.0;
          // Target EA parity: rescue replacements trade at exactly 2x the tier
          // volume in the dataset (0.12 = 2x0.06 at L11-20, 0.30 = 2x0.15 at L21-30).
          config.trend_rescue_volume_multiplier=2.0;
          // Target EA parity: final-regime (Jul 14-30) lot schedule measured
          // from every order the Target EA placed in that window:
          //   L1-10 -> 0.01 (10,940 orders), L11-20 -> 0.06 (2,624 orders),
          //   L21-30 -> 0.15 (378 orders). Zero exceptions at base volume.
          SetLotTier(config,1,10,0.01);
          SetLotTier(config,11,20,0.06);
          SetLotTier(config,21,30,0.15);
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
   SetLotTier(config,1,custom.tier1_end,custom.lot1);
   SetLotTier(config,custom.tier1_end+1,custom.tier2_end,custom.lot2);
   SetLotTier(config,custom.tier2_end+1,custom.levels_per_side,custom.lot3);
   return true;
  }

#endif
