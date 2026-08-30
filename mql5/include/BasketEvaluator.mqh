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
         has_traded &&
         open_positions > 0 &&
         target>0.0 &&
         snapshot.net>=target
      );
      return snapshot;
     }
  };

#endif
