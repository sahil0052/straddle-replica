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
         // Unpaced high-frequency micro-scalping (burst execution)
         config.close_interval_seconds=0;
         config.stop_update_interval_seconds=0;
         config.stop_updates_on_timer=false;
         config.max_stop_updates_per_pass=0;
         config.rearm_delay_seconds=0;
         config.restart_delay_ms=1000;
         config.deployment_fill_cooldown_seconds=0;
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
         config.cycle_target_money=25.0;
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
         config.cycle_target_money=15.0;
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
