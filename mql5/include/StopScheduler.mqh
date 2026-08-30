#ifndef STRADDLE_STOP_SCHEDULER_MQH
#define STRADDLE_STOP_SCHEDULER_MQH

#include "StraddleTypes.mqh"

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
      // TRUE for the target, and lock_offset_price is dead code on every modern
      // profile (JUNE_2K, LATEST_30, STARWAVE_30, STARWAVE_20 all set the flag).
      // Starwave activation overshoot, offsets under 0.5 step, n=289:
      // p10 +0.058 / p50 +0.226 / p90 +0.455 steps, and 0 at exact breakeven --
      // same strictly-positive polling signature as the Target, just slower.
      //

      // That would fill the (1.0,2.0) band and is directly falsified by the
      // measurement above.
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
