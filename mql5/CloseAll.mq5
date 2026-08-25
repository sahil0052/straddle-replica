//+------------------------------------------------------------------+
//| CloseAll.mq5 - Instantly close all positions and delete orders   |
//+------------------------------------------------------------------+
#property script_show_inputs
#include <Trade\Trade.mqh>

void OnStart()
{
   CTrade trade;
   trade.SetDeviationInPoints(200);
   
   for(int i=OrdersTotal()-1; i>=0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0)
         trade.OrderDelete(ticket);
   }
   
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
         trade.PositionClose(ticket);
   }
   
   PrintFormat("[CLOSE_ALL] Done. Remaining positions: %d, orders: %d", PositionsTotal(), OrdersTotal());
}
