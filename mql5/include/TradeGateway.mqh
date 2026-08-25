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
      request.type_filling=ORDER_FILLING_RETURN;
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
