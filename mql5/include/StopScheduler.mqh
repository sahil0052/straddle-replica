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

      // Target EA standard: Only trail when price moves favorable by at least lock_trigger_steps (1.0 step):
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
