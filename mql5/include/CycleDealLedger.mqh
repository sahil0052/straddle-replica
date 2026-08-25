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
