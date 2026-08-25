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
      // so a locked value between 1.0 and 2.0 is UNREACHABLE: it would need a
      // peak in (3.0,4.0) with the 2.0 distance still applied, but at peak >=
      // 3.0 the ternary below has already switched to 1.0.  That makes the
      // configuration falsifiable by a single histogram.
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
      // DO NOT collapse these two branches into a single trailing distance.
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
