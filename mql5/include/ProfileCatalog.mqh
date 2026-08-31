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
         config.replica_orphan_leak=true;
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
         config.replica_orphan_leak=true;
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
