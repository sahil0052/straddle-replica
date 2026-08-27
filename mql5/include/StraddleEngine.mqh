#ifndef STRADDLE_REPLICA_ENGINE_MQH
#define STRADDLE_REPLICA_ENGINE_MQH

#include "StraddleTypes.mqh"
#include "ProfileCatalog.mqh"
#include "TradeGateway.mqh"
#include "CycleDealLedger.mqh"
#include "BasketEvaluator.mqh"
#include "StopScheduler.mqh"

#define STR_PENDING_DEAL_CAPACITY 256
#define STR_DEAL_METADATA_SETTLE_MS 5000
#define STR_HISTORY_RECONCILE_INTERVAL_MS 1000
#define STR_HISTORY_RECONCILE_LOOKBACK_MS 900000

class CStraddleEngine
  {
private:
   SRuntimeConfig    m_runtime;
   SProfileConfig    m_profile;
   CTradeGateway     m_gateway;
   CCycleDealLedger  m_deal_ledger;
   CBasketEvaluator m_basket_evaluator;
   CStopScheduler m_stop_scheduler;
   ENUM_CYCLE_STATE m_state;
   SLevelState       m_buy_levels[STR_MAX_LEVELS];
   SLevelState       m_sell_levels[STR_MAX_LEVELS];
   double            m_anchor;
   double            m_step;
   double            m_tick_size;
   double            m_point;
   double            m_cycle_start_balance;
   double            m_cycle_realized;
   int               m_cycle_exit_deal_count;
   datetime          m_cycle_started_at;
   datetime          m_cycle_started_utc;
   long              m_cycle_started_msc;
   ulong             m_cycle_started_ms;
   datetime          m_restart_started_at;
   datetime          m_last_close_at;
   // How many owned positions TryCloseOneOwnedPosition() steps over before it
   // makes its single close attempt.  This exists so that ONE close request per
   // tick and "a stalled ticket must not block the basket" can both hold at
   // once; see the comment on TryCloseOneOwnedPosition for why that mattered.
   int               m_close_skip;
   datetime          m_last_entry_fill_at;
   datetime          m_last_stop_update_at;
   int               m_deploy_index;
   bool              m_has_traded;
   bool              m_halted;
   // Which guard set m_halted, carried forward so the TERMINAL "halted" event can
   // name it.  BeginClose() logs the reason on "close_begin", but it is also called
   // for every ordinary $30 basket exit, so the log holds hundreds of close_begin
   // lines and only one of them is fatal -- and the flatten sweep in between takes
   // one position per timer tick, so the two lines can be far apart.  Without this,
   // an operator finding the EA parked in CYCLE_HALTED cannot tell WHICH limit
   // killed it.  Kept in lockstep with m_halted at the single assignment site.
   string            m_halt_reason;
   string            m_telemetry_file;
   int               m_atr_handle;
   string            m_cycle_id;
   ulong             m_shadow_last_command_seq;
   ulong             m_event_sequence;
   ulong             m_last_processed_deal_ticket;
   ulong             m_processed_deal_tickets[];
   int               m_processed_deal_count;
   ulong             m_pending_deal_tickets[STR_PENDING_DEAL_CAPACITY];
   int               m_pending_deal_count;
   ulong             m_last_history_reconcile_ms;
   bool              m_history_reconcile_seeded;
   bool              m_shadow_reset_active;
   int               m_trend_rescue_side;
   bool              m_trend_rescue_replacing;
   ulong             m_trend_rescue_mask;
   ulong             m_buy_trend_rescue_latched_mask;
   ulong             m_sell_trend_rescue_latched_mask;
   ulong             m_buy_trend_rescue_rearm_mask;
   ulong             m_sell_trend_rescue_rearm_mask;
   int               m_trend_rescue_consumed_side;
   bool              m_alignment_hold_logged;

   string GlobalKey(const string suffix) const
     {
      return StringFormat("STR_%I64u_%s_%s",m_runtime.magic,m_runtime.symbol,suffix);
     }

   string AlignmentHoldFileName(void) const
     {
      return StringFormat(
         "StraddleAlignmentHold_%I64u_%I64u_%s.json",
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
         m_runtime.magic,
         m_runtime.symbol
      );
     }

   bool AlignmentHoldActive(void) const
     {
      return FileIsExist(AlignmentHoldFileName(),FILE_COMMON);
     }

   string CycleIdFromUtc(const string prefix,
                         const datetime cycle_started_utc) const
      {
       MqlDateTime utc={};
       TimeToStruct(cycle_started_utc,utc);
       return StringFormat(
          "%s-%I64u-%04d%02d%02dT%02d%02d%02dZ",
         prefix,
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
         utc.year,utc.mon,utc.day,utc.hour,utc.min,utc.sec
       );
      }

   string NewCycleId(const string prefix) const
      {
       return CycleIdFromUtc(prefix,TimeGMT());
      }

   ulong NextEventSequence(void)
      {
       m_event_sequence++;
       GlobalVariableSet(GlobalKey("event_seq"),(double)m_event_sequence);
       GlobalVariablesFlush();
       return m_event_sequence;
      }

   string EventId(const string kind,
                  const ulong sequence,
                  const ulong deal_ticket) const
     {
      if(deal_ticket>0)
         return StringFormat(
            "%s:deal:%I64u:%s",
            m_cycle_id,deal_ticket,kind
         );
      return StringFormat("%s:event:%I64u",m_cycle_id,sequence);
     }

   double NormalizePrice(const double value) const
     {
      return m_gateway.NormalizePrice(value);
     }

   ulong TrendRescueBit(const int index) const
     {
      return((ulong)1<<index);
     }

   bool TrendRescuePositionRearmPending(const bool is_buy,
                                        const int index) const
     {
      ulong bit=TrendRescueBit(index);
      return(
         is_buy
         ? (m_buy_trend_rescue_rearm_mask & bit)!=0
         : (m_sell_trend_rescue_rearm_mask & bit)!=0
      );
     }

   void MarkTrendRescuePositionRearms(const bool is_buy)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         if(is_buy && m_buy_levels[index].has_position)
            m_buy_trend_rescue_rearm_mask|=TrendRescueBit(index);
         else if(!is_buy && m_sell_levels[index].has_position)
            m_sell_trend_rescue_rearm_mask|=TrendRescueBit(index);
        }
     }

   void ClearTrendRescuePositionRearm(const bool is_buy,
                                      const int index)
     {
      if(is_buy)
         m_buy_trend_rescue_rearm_mask&=~TrendRescueBit(index);
      else
         m_sell_trend_rescue_rearm_mask&=~TrendRescueBit(index);
     }

   double CalculateStep(const double anchor)
     {
      if(m_profile.step_mode==STR_STEP_ANCHOR_DIVISOR)
         return NormalizePrice(anchor/m_profile.anchor_divisor);
      if(m_profile.step_mode==STR_STEP_ATR)
        {
         if(m_atr_handle==INVALID_HANDLE || BarsCalculated(m_atr_handle)<m_profile.atr_period)
            return 0.0;
         double atr_value[1];
         if(CopyBuffer(m_atr_handle,0,0,1,atr_value)!=1 || atr_value[0]<=0.0)
            return 0.0;
         return NormalizePrice(atr_value[0]*m_profile.atr_multiplier);
        }
      return NormalizePrice(m_profile.fixed_step);
     }

   void ResetLevelState(void)
     {
      m_trend_rescue_side=0;
      m_trend_rescue_replacing=false;
      m_trend_rescue_mask=0;
      m_buy_trend_rescue_latched_mask=0;
      m_sell_trend_rescue_latched_mask=0;
      m_buy_trend_rescue_rearm_mask=0;
      m_sell_trend_rescue_rearm_mask=0;
      m_trend_rescue_consumed_side=0;
      for(int index=0;index<STR_MAX_LEVELS;index++)
        {
         m_buy_levels[index].is_buy=true;
         m_buy_levels[index].level=index+1;
         m_buy_levels[index].target_price=0.0;
         m_buy_levels[index].volume=0.0;
         m_buy_levels[index].has_pending=false;
         m_buy_levels[index].has_position=false;
         m_buy_levels[index].active_order_count=0;
         m_buy_levels[index].active_position_count=0;
         m_buy_levels[index].duplicate_identity=false;
         m_buy_levels[index].recovery_done=false;
          m_buy_levels[index].order_ticket=0;
          m_buy_levels[index].position_ticket=0;
            m_buy_levels[index].rearm_requested=false;
            m_buy_levels[index].rearm_after_msc=0;
            m_buy_levels[index].trend_rescue_replacement=false;
            m_buy_levels[index].trend_rescue_latched=false;

         m_sell_levels[index].is_buy=false;
         m_sell_levels[index].level=index+1;
         m_sell_levels[index].target_price=0.0;
         m_sell_levels[index].volume=0.0;
         m_sell_levels[index].has_pending=false;
         m_sell_levels[index].has_position=false;
         m_sell_levels[index].active_order_count=0;
         m_sell_levels[index].active_position_count=0;
         m_sell_levels[index].duplicate_identity=false;
         m_sell_levels[index].recovery_done=false;
          m_sell_levels[index].order_ticket=0;
          m_sell_levels[index].position_ticket=0;
            m_sell_levels[index].rearm_requested=false;
            m_sell_levels[index].rearm_after_msc=0;
            m_sell_levels[index].trend_rescue_replacement=false;
            m_sell_levels[index].trend_rescue_latched=false;
        }
     }

   void InitializeLevelTargets(void)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         int level=index+1;
         m_buy_levels[index].target_price=NormalizePrice(m_anchor+level*m_step);
         m_buy_levels[index].volume=m_profile.lots[index];
         m_sell_levels[index].target_price=NormalizePrice(m_anchor-level*m_step);
         m_sell_levels[index].volume=m_profile.lots[index];
        }
     }

   bool ParseLevelComment(const string comment,bool &is_buy,int &index) const
     {
      if(StringFind(comment,"STR B")==0)
         is_buy=true;
      else if(StringFind(comment,"STR S")==0)
         is_buy=false;
      else
         return false;
      int level=(int)StringToInteger(StringSubstr(comment,5));
      if(level<1 || level>m_profile.levels_per_side)
         return false;
      index=level-1;
      return true;
     }

   string PositionCommentFromDeal(const ulong deal_ticket) const
     {
      ulong position_id=(ulong)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID);
      if(position_id==0 || !HistoryOrderSelect(position_id))
         return "";
      return HistoryOrderGetString(position_id,ORDER_COMMENT);
     }

   bool IsOwnedOrderSelected(void) const
     {
      return((ulong)OrderGetInteger(ORDER_MAGIC)==m_runtime.magic &&
             OrderGetString(ORDER_SYMBOL)==m_runtime.symbol);
     }

   bool IsOwnedPositionSelected(void) const
     {
      return((ulong)PositionGetInteger(POSITION_MAGIC)==m_runtime.magic &&
             PositionGetString(POSITION_SYMBOL)==m_runtime.symbol);
     }

   void ClearLiveFlags(void)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         m_buy_levels[index].has_pending=false;
         m_buy_levels[index].has_position=false;
         m_buy_levels[index].active_order_count=0;
         m_buy_levels[index].active_position_count=0;
         m_buy_levels[index].order_ticket=0;
         m_buy_levels[index].position_ticket=0;
         m_sell_levels[index].has_pending=false;
         m_sell_levels[index].has_position=false;
         m_sell_levels[index].active_order_count=0;
         m_sell_levels[index].active_position_count=0;
         m_sell_levels[index].order_ticket=0;
         m_sell_levels[index].position_ticket=0;
        }
     }

   void DetectDuplicateLevelIdentity(SLevelState &level_state)
     {
      int entity_count=
         level_state.active_order_count+
         level_state.active_position_count;
      if(level_state.active_order_count==1 &&
         level_state.active_position_count==1 &&
         level_state.order_ticket>0 &&
         level_state.order_ticket==level_state.position_ticket)
         entity_count=1;
      bool duplicate=(entity_count>1);
      if(duplicate && !level_state.duplicate_identity)
         LogLifecycleEvent(
            "duplicate_level_identity",
            StringFormat(
               "STR %s%d",
               level_state.is_buy ? "B" : "S",
               level_state.level
            ),
            "multiple_active_entities"
         );
      level_state.duplicate_identity=duplicate;
     }

   void ReconcileLevels(const bool report_duplicates=true)
     {
      ClearLiveFlags();
      for(int order_index=0;order_index<OrdersTotal();order_index++)
        {
         ulong ticket=OrderGetTicket(order_index);
         if(ticket==0 || !IsOwnedOrderSelected())
            continue;
         bool is_buy=false;
         int index=-1;
         if(!ParseLevelComment(OrderGetString(ORDER_COMMENT),is_buy,index))
            continue;
          if(is_buy)
            {
             m_buy_levels[index].active_order_count++;
             m_buy_levels[index].has_pending=true;
             m_buy_levels[index].order_ticket=ticket;
             m_buy_levels[index].volume=
                OrderGetDouble(ORDER_VOLUME_CURRENT);
            }
          else
            {
             m_sell_levels[index].active_order_count++;
             m_sell_levels[index].has_pending=true;
             m_sell_levels[index].order_ticket=ticket;
             m_sell_levels[index].volume=
                OrderGetDouble(ORDER_VOLUME_CURRENT);
            }
        }

      for(int position_index=0;position_index<PositionsTotal();position_index++)
        {
         ulong ticket=PositionGetTicket(position_index);
         if(ticket==0 || !IsOwnedPositionSelected())
            continue;
         bool is_buy=false;
         int index=-1;
         if(!ParseLevelComment(PositionGetString(POSITION_COMMENT),is_buy,index))
            continue;
          if(is_buy)
            {
             m_buy_levels[index].active_position_count++;
             m_buy_levels[index].has_position=true;
             m_buy_levels[index].position_ticket=ticket;
             m_buy_levels[index].volume=
                PositionGetDouble(POSITION_VOLUME);
            }
          else
            {
             m_sell_levels[index].active_position_count++;
             m_sell_levels[index].has_position=true;
             m_sell_levels[index].position_ticket=ticket;
             m_sell_levels[index].volume=
                PositionGetDouble(POSITION_VOLUME);
            }
        }
      if(report_duplicates)
        {
         for(int index=0;index<m_profile.levels_per_side;index++)
           {
            DetectDuplicateLevelIdentity(m_buy_levels[index]);
            DetectDuplicateLevelIdentity(m_sell_levels[index]);
           }
        }
     }

   void ArmMissingLevelsAfterRestore(void)
     {
      long rearm_after_msc=(
         CurrentServerMs()+
         (long)m_profile.rearm_delay_seconds*1000
      );
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
          if(!m_buy_levels[index].has_pending &&
             !m_buy_levels[index].has_position &&
             !m_buy_levels[index].trend_rescue_replacement)
           {
            m_buy_levels[index].rearm_requested=true;
            m_buy_levels[index].rearm_after_msc=rearm_after_msc;
           }
          if(!m_sell_levels[index].has_pending &&
             !m_sell_levels[index].has_position &&
             !m_sell_levels[index].trend_rescue_replacement)
           {
            m_sell_levels[index].rearm_requested=true;
            m_sell_levels[index].rearm_after_msc=rearm_after_msc;
           }
        }
     }

   void ResetProcessedDeals(void)
     {
      m_processed_deal_count=0;
      ArrayResize(m_processed_deal_tickets,0);
      m_last_processed_deal_ticket=0;
     }

   bool DealAlreadyProcessed(const ulong deal_ticket) const
     {
      if(deal_ticket==0)
         return true;
      for(int index=0;index<m_processed_deal_count;index++)
         if(m_processed_deal_tickets[index]==deal_ticket)
            return true;
      return false;
     }

   void RememberProcessedDeal(const ulong deal_ticket,
                              const bool persist=true)
     {
      if(deal_ticket==0 || DealAlreadyProcessed(deal_ticket))
         return;
      if(m_processed_deal_count>=ArraySize(m_processed_deal_tickets))
        {
         int resized=ArrayResize(
            m_processed_deal_tickets,
            m_processed_deal_count+128
         );
         if(resized<=m_processed_deal_count)
           {
            PrintFormat(
               "[STR] Processed-deal ledger resize failed; ticket=%I64u.",
               deal_ticket
            );
            return;
           }
        }
      m_processed_deal_tickets[m_processed_deal_count]=deal_ticket;
      m_processed_deal_count++;
      m_last_processed_deal_ticket=deal_ticket;
      if(persist)
        {
         GlobalVariableSet(
            GlobalKey("last_deal"),
            (double)m_last_processed_deal_ticket
         );
         GlobalVariablesFlush();
        }
     }

   void LoadProcessedDealsFromTelemetry(void)
     {
      ulong persisted_last=m_last_processed_deal_ticket;
      m_processed_deal_count=0;
      ArrayResize(m_processed_deal_tickets,0);
      if(m_cycle_id=="" || m_telemetry_file=="")
        {
         RememberProcessedDeal(persisted_last,false);
         return;
        }
      int handle=FileOpen(
         m_telemetry_file,
         FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|
         FILE_COMMON,
         ','
      );
      if(handle==INVALID_HANDLE)
        {
         RememberProcessedDeal(persisted_last,false);
         return;
        }
      while(!FileIsEnding(handle))
        {
         string fields[64];
         int field_count=0;
         while(field_count<64 && !FileIsEnding(handle))
           {
            fields[field_count]=FileReadString(handle);
            field_count++;
            if(FileIsLineEnding(handle))
               break;
           }
         while(!FileIsEnding(handle) && !FileIsLineEnding(handle))
            FileReadString(handle);
         if(field_count<=22)
            continue;
         if(fields[2]!=m_cycle_id)
            continue;
         ulong deal_ticket=(ulong)StringToInteger(fields[22]);
         RememberProcessedDeal(deal_ticket,false);
        }
      FileClose(handle);
      if(m_processed_deal_count==0)
         RememberProcessedDeal(persisted_last,false);
     }

   datetime RestartStartedAtFromTelemetry(void) const
     {
      if(m_cycle_id=="" || m_telemetry_file=="")
         return 0;
      int handle=FileOpen(
         m_telemetry_file,
         FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|
         FILE_COMMON,
         ','
      );
      if(handle==INVALID_HANDLE)
         return 0;
      datetime latest_restart_started_at=0;
      while(!FileIsEnding(handle))
        {
         string fields[64];
         int field_count=0;
         while(field_count<64 && !FileIsEnding(handle))
           {
            fields[field_count]=FileReadString(handle);
            field_count++;
            if(FileIsLineEnding(handle))
               break;
           }
         while(!FileIsEnding(handle) && !FileIsLineEnding(handle))
            FileReadString(handle);
         if(field_count<=4)
            continue;
         if(fields[2]!=m_cycle_id)
            continue;
         if(fields[4]!="cycle_complete")
            continue;
         datetime completed_at=StringToTime(fields[1]);
         if(completed_at>latest_restart_started_at)
            latest_restart_started_at=completed_at;
        }
      FileClose(handle);
      return latest_restart_started_at;
     }

   int OwnedOrderCount(void) const
     {
      int count=0;
      for(int index=0;index<OrdersTotal();index++)
        {
         if(OrderGetTicket(index)>0 && IsOwnedOrderSelected())
            count++;
        }
      return count;
     }

   int OwnedPositionCount(void) const
     {
      int count=0;
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)>0 && IsOwnedPositionSelected())
            count++;
        }
      return count;
     }

   bool FindReference(bool &is_buy,int &level,double &price) const
     {
      for(int index=0;index<OrdersTotal();index++)
        {
         if(OrderGetTicket(index)==0 || !IsOwnedOrderSelected())
            continue;
         int level_index=-1;
         if(ParseLevelComment(OrderGetString(ORDER_COMMENT),is_buy,level_index))
           {
            level=level_index+1;
            price=OrderGetDouble(ORDER_PRICE_OPEN);
            return true;
           }
        }
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)==0 || !IsOwnedPositionSelected())
            continue;
         int level_index=-1;
         if(ParseLevelComment(PositionGetString(POSITION_COMMENT),is_buy,level_index))
           {
            level=level_index+1;
            price=PositionGetDouble(POSITION_PRICE_OPEN);
            return true;
           }
        }
      return false;
     }

   bool RestoreCycle(void)
     {
      ENUM_CYCLE_STATE saved_state=CYCLE_RUNNING;
      if(GlobalVariableCheck(GlobalKey("state")))
         saved_state=(ENUM_CYCLE_STATE)(int)GlobalVariableGet(GlobalKey("state"));
      datetime persisted_restart_started_at=0;
      if(GlobalVariableCheck(GlobalKey("restart_started_at")))
         persisted_restart_started_at=(datetime)(long)GlobalVariableGet(
            GlobalKey("restart_started_at")
         );
      bool flat_restart=(
         OwnedOrderCount()==0 &&
         OwnedPositionCount()==0 &&
         saved_state==CYCLE_RESTARTING
      );
      if(OwnedOrderCount()==0 &&
         OwnedPositionCount()==0 &&
         !flat_restart)
         return false;

      bool restored=false;
      string anchor_key=GlobalKey("anchor");
      string step_key=GlobalKey("step");
      if(GlobalVariableCheck(anchor_key) && GlobalVariableCheck(step_key))
        {
         m_anchor=GlobalVariableGet(anchor_key);
         m_step=GlobalVariableGet(step_key);
         restored=(m_anchor>0.0 && m_step>0.0);
        }

      if(!restored)
        {
         bool is_buy=false;
         int level=0;
         double price=0.0;
         if(!FindReference(is_buy,level,price))
            return false;
         if(m_profile.step_mode==STR_STEP_ANCHOR_DIVISOR)
           {
            double factor=(is_buy ? 1.0+level/m_profile.anchor_divisor
                                  : 1.0-level/m_profile.anchor_divisor);
            m_anchor=NormalizePrice(price/factor);
           }
         else if(m_profile.step_mode==STR_STEP_ATR)
           {
            m_step=CalculateStep(price);
            if(m_step<=0.0)
               return false;
            m_anchor=NormalizePrice(is_buy ? price-level*m_step
                                          : price+level*m_step);
           }
         else
            m_anchor=NormalizePrice(is_buy ? price-level*m_profile.fixed_step
                                          : price+level*m_profile.fixed_step);
         if(m_profile.step_mode!=STR_STEP_ATR)
            m_step=CalculateStep(m_anchor);
        }

      m_cycle_start_balance=(GlobalVariableCheck(GlobalKey("balance"))
                             ? GlobalVariableGet(GlobalKey("balance"))
                             : AccountInfoDouble(ACCOUNT_BALANCE));
      m_cycle_started_msc=(
         GlobalVariableCheck(GlobalKey("start_msc"))
         ? (long)GlobalVariableGet(GlobalKey("start_msc"))
         : (long)TimeCurrent()*1000
      );
      m_cycle_started_at=(datetime)(m_cycle_started_msc/1000);
      m_cycle_started_utc=(
         GlobalVariableCheck(GlobalKey("start_utc"))
         ? (datetime)(long)GlobalVariableGet(GlobalKey("start_utc"))
         : 0
      );
      if(m_cycle_started_utc<=0)
        {
         long server_offset=(
            (long)TimeCurrent()-(long)TimeGMT()
         );
         m_cycle_started_utc=(
            datetime
         )((long)m_cycle_started_at-server_offset);
        }
      if(m_runtime.runtime_mode==STR_RUNTIME_NORMAL &&
         m_cycle_id=="")
         m_cycle_id=CycleIdFromUtc("local",m_cycle_started_utc);
      if(flat_restart && persisted_restart_started_at<=0)
         persisted_restart_started_at=RestartStartedAtFromTelemetry();
      m_cycle_started_ms=GetTickCount64();
      m_event_sequence=(
         GlobalVariableCheck(GlobalKey("event_seq"))
         ? (ulong)GlobalVariableGet(GlobalKey("event_seq"))
         : 0
      );
      m_last_processed_deal_ticket=(
         GlobalVariableCheck(GlobalKey("last_deal"))
         ? (ulong)GlobalVariableGet(GlobalKey("last_deal"))
         : 0
      );
      LoadProcessedDealsFromTelemetry();
      double persisted_realized=(
         GlobalVariableCheck(GlobalKey("realized"))
         ? GlobalVariableGet(GlobalKey("realized"))
         : 0.0
      );
      int persisted_realized_count=(
         GlobalVariableCheck(GlobalKey("realized_count"))
         ? (int)GlobalVariableGet(GlobalKey("realized_count"))
         : 0
      );
      double recalculated_realized=0.0;
      int recalculated_count=0;
      if(m_deal_ledger.TryRecalculate(
            m_cycle_started_msc,
            recalculated_realized,
            recalculated_count
         ) &&
         recalculated_count>=persisted_realized_count)
        {
         m_cycle_realized=recalculated_realized;
         m_cycle_exit_deal_count=recalculated_count;
        }
      else
        {
         m_cycle_realized=persisted_realized;
         m_cycle_exit_deal_count=persisted_realized_count;
        }
      m_last_stop_update_at=0;
      m_last_entry_fill_at=(
         GlobalVariableCheck(GlobalKey("last_entry_fill_at"))
         ? (datetime)(long)GlobalVariableGet(
            GlobalKey("last_entry_fill_at")
         )
         : 0
      );
      m_trend_rescue_side=(
         GlobalVariableCheck(GlobalKey("trend_rescue_side"))
         ? (int)GlobalVariableGet(GlobalKey("trend_rescue_side"))
         : 0
      );
      m_trend_rescue_replacing=(
         GlobalVariableCheck(GlobalKey("trend_rescue_replacing"))
         ? GlobalVariableGet(GlobalKey("trend_rescue_replacing"))>0.5
         : false
      );
      m_trend_rescue_mask=(
         GlobalVariableCheck(GlobalKey("trend_rescue_mask"))
         ? (ulong)GlobalVariableGet(GlobalKey("trend_rescue_mask"))
         : 0
      );
      m_buy_trend_rescue_latched_mask=(
         GlobalVariableCheck(GlobalKey("buy_trend_rescue_latched_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("buy_trend_rescue_latched_mask")
         )
         : 0
      );
      m_sell_trend_rescue_latched_mask=(
         GlobalVariableCheck(GlobalKey("sell_trend_rescue_latched_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("sell_trend_rescue_latched_mask")
         )
         : 0
      );
      m_buy_trend_rescue_rearm_mask=(
         GlobalVariableCheck(GlobalKey("buy_trend_rescue_rearm_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("buy_trend_rescue_rearm_mask")
         )
         : 0
      );
      m_sell_trend_rescue_rearm_mask=(
         GlobalVariableCheck(GlobalKey("sell_trend_rescue_rearm_mask"))
         ? (ulong)GlobalVariableGet(
            GlobalKey("sell_trend_rescue_rearm_mask")
         )
         : 0
      );
      m_trend_rescue_consumed_side=(
         GlobalVariableCheck(GlobalKey("trend_rescue_consumed_side"))
         ? (int)GlobalVariableGet(
            GlobalKey("trend_rescue_consumed_side")
         )
         : 0
      );
      m_has_traded=(
         OwnedPositionCount()>0 ||
         m_cycle_exit_deal_count>0
      );
      if(flat_restart)
        {
         m_state=CYCLE_RESTARTING;
         if(persisted_restart_started_at>0 &&
            persisted_restart_started_at<=TimeCurrent())
            m_restart_started_at=persisted_restart_started_at;
         else
            m_restart_started_at=TimeCurrent();
         PersistCycle();
         LogEvent("restore","",0,0.0,0.0,"flat_restart");
         return true;
        }
      InitializeLevelTargets();
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         m_buy_levels[index].trend_rescue_latched=(
            (m_buy_trend_rescue_latched_mask &
             TrendRescueBit(index))!=0
         );
         m_sell_levels[index].trend_rescue_latched=(
            (m_sell_trend_rescue_latched_mask &
             TrendRescueBit(index))!=0
         );
         bool replacement=(
            (m_trend_rescue_mask & TrendRescueBit(index))!=0
         );
         if(m_trend_rescue_side>0)
           {
            m_buy_levels[index].trend_rescue_replacement=replacement;
            if(replacement)
               m_buy_levels[index].volume=(
                  m_profile.lots[index]*
                  m_profile.trend_rescue_volume_multiplier
               );
           }
         else if(m_trend_rescue_side<0)
           {
            m_sell_levels[index].trend_rescue_replacement=replacement;
            if(replacement)
               m_sell_levels[index].volume=(
                  m_profile.lots[index]*
                  m_profile.trend_rescue_volume_multiplier
               );
           }
        }
      ReconcileLevels(false);
      ArmMissingLevelsAfterRestore();
      if(saved_state==CYCLE_CLOSING && OwnedPositionCount()>0)
         m_state=CYCLE_CLOSING;
      else if((saved_state==CYCLE_CLOSING || saved_state==CYCLE_CANCELING) &&
              OwnedPositionCount()==0 && OwnedOrderCount()>0)
         m_state=CYCLE_CANCELING;
      else
         m_state=CYCLE_RUNNING;
      ReconcileLevels();
      PersistCycle();
      LogEvent("restore","",0,0.0,0.0,"");
      return true;
     }

   void PersistCycle(void) const
     {
      GlobalVariableSet(GlobalKey("anchor"),m_anchor);
      GlobalVariableSet(GlobalKey("step"),m_step);
      GlobalVariableSet(GlobalKey("state"),(double)m_state);
      GlobalVariableSet(GlobalKey("balance"),m_cycle_start_balance);
      GlobalVariableSet(GlobalKey("realized"),m_cycle_realized);
      GlobalVariableSet(
         GlobalKey("realized_count"),
         (double)m_cycle_exit_deal_count
      );
      GlobalVariableSet(GlobalKey("start_msc"),(double)m_cycle_started_msc);
      GlobalVariableSet(
         GlobalKey("start_utc"),
         (double)m_cycle_started_utc
      );
      GlobalVariableSet(
         GlobalKey("restart_started_at"),
         (double)m_restart_started_at
      );
       GlobalVariableSet(
          GlobalKey("event_seq"),
          (double)m_event_sequence
       );
       GlobalVariableSet(
          GlobalKey("last_deal"),
          (double)m_last_processed_deal_ticket
       );
       GlobalVariableSet(
          GlobalKey("last_entry_fill_at"),
          (double)m_last_entry_fill_at
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_side"),
          (double)m_trend_rescue_side
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_replacing"),
          (double)(m_trend_rescue_replacing ? 1 : 0)
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_mask"),
          (double)m_trend_rescue_mask
       );
       GlobalVariableSet(
          GlobalKey("buy_trend_rescue_latched_mask"),
          (double)m_buy_trend_rescue_latched_mask
       );
       GlobalVariableSet(
          GlobalKey("sell_trend_rescue_latched_mask"),
          (double)m_sell_trend_rescue_latched_mask
       );
       GlobalVariableSet(
          GlobalKey("buy_trend_rescue_rearm_mask"),
          (double)m_buy_trend_rescue_rearm_mask
       );
       GlobalVariableSet(
          GlobalKey("sell_trend_rescue_rearm_mask"),
          (double)m_sell_trend_rescue_rearm_mask
       );
       GlobalVariableSet(
          GlobalKey("trend_rescue_consumed_side"),
          (double)m_trend_rescue_consumed_side
       );
       GlobalVariablesFlush();
      }

   void ClearPersistence(void) const
     {
      GlobalVariableDel(GlobalKey("anchor"));
      GlobalVariableDel(GlobalKey("step"));
      GlobalVariableDel(GlobalKey("state"));
      GlobalVariableDel(GlobalKey("balance"));
      GlobalVariableDel(GlobalKey("realized"));
      GlobalVariableDel(GlobalKey("realized_count"));
      GlobalVariableDel(GlobalKey("start_msc"));
       GlobalVariableDel(GlobalKey("start_utc"));
       GlobalVariableDel(GlobalKey("restart_started_at"));
       GlobalVariableDel(GlobalKey("event_seq"));
       GlobalVariableDel(GlobalKey("last_deal"));
       GlobalVariableDel(GlobalKey("last_entry_fill_at"));
       GlobalVariableDel(GlobalKey("trend_rescue_side"));
       GlobalVariableDel(GlobalKey("trend_rescue_replacing"));
       GlobalVariableDel(GlobalKey("trend_rescue_mask"));
       GlobalVariableDel(GlobalKey("buy_trend_rescue_latched_mask"));
       GlobalVariableDel(GlobalKey("sell_trend_rescue_latched_mask"));
       GlobalVariableDel(GlobalKey("buy_trend_rescue_rearm_mask"));
       GlobalVariableDel(GlobalKey("sell_trend_rescue_rearm_mask"));
       GlobalVariableDel(GlobalKey("trend_rescue_consumed_side"));
      }

   void PersistShadowSequence(void) const
     {
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
         GlobalVariableSet(
            GlobalKey("shadow_seq"),
            (double)m_shadow_last_command_seq
         );
     }

   void RestoreShadowSequence(void)
     {
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         GlobalVariableCheck(GlobalKey("shadow_seq")))
         m_shadow_last_command_seq=(ulong)GlobalVariableGet(
            GlobalKey("shadow_seq")
         );
     }

   string IsoUtcNow(void) const
     {
      MqlDateTime utc_time={};
      TimeToStruct(TimeGMT(),utc_time);
      return StringFormat("%04d-%02d-%02dT%02d:%02d:%02dZ",
                          utc_time.year,utc_time.mon,utc_time.day,
                          utc_time.hour,utc_time.min,utc_time.sec);
     }

   string ServerTimeNow(void) const
     {
      MqlDateTime server_time={};
      TimeToStruct(TimeTradeServer(),server_time);
      return StringFormat("%04d.%02d.%02d %02d:%02d:%02d",
                          server_time.year,server_time.mon,server_time.day,
                          server_time.hour,server_time.min,server_time.sec);
     }

   string EventSide(const string level_key,const string comment) const
     {
      string side_key=(level_key!="" ? level_key : comment);
      if(StringFind(side_key,"STR B")==0 ||
         side_key=="STR ORB" ||
         side_key=="STR AVB")
         return "buy";
      if(StringFind(side_key,"STR S")==0 ||
         side_key=="STR ORS" ||
         side_key=="STR AVS")
         return "sell";
      return "";
     }

   void WriteTelemetry(const string kind,
                       const string level_key,
                       const ulong ticket,
                       const double volume,
                       const double price,
                       const double stop_loss,
                       const double take_profit,
                       const string comment,
                       const ulong request_id,
                       const uint retcode,
                       const double commission,
                       const double swap,
                       const double profit,
                       const ulong deal_ticket,
                       const ulong order_ticket,
                       const ulong position_ticket)
     {
      if(!m_runtime.telemetry_enabled)
         return;
      int handle=FileOpen(m_telemetry_file,
                          FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return;
      if(FileSize(handle)==0)
         FileWrite(handle,
                   "utc_time","server_time","cycle_id","command_seq",
                   "kind","comment","side","volume","price","sl","tp",
                   "state","level","ticket","request_id","retcode",
                   "commission","swap","profit",
                   "schema_version","event_sequence","event_id",
                   "deal_ticket","order_ticket","position_ticket",
                   "cycle_realized","floating_profit","cycle_net",
                   "basket_target","evidence_grade");
      FileSeek(handle,0,SEEK_END);
      string event_comment=(comment!="" ? comment : level_key);
      ulong event_sequence=NextEventSequence();
      string event_id=EventId(kind,event_sequence,deal_ticket);
      double floating=OwnedFloatingProfit();
      double scale=ContractScale();
      double basket_target=(
         m_profile.cycle_target_money>0.0
         ? m_profile.cycle_target_money*scale
         : m_cycle_start_balance*
           m_profile.cycle_target_balance_pct/100.0
      );
      double cycle_net=m_cycle_realized+floating;
      FileWrite(handle,
                 IsoUtcNow(),
                ServerTimeNow(),
                m_cycle_id,
                m_shadow_last_command_seq,
                kind,
                event_comment,
                EventSide(level_key,event_comment),
                DoubleToString(volume,8),
                DoubleToString(price,(int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS)),
                DoubleToString(stop_loss,(int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS)),
                DoubleToString(take_profit,(int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS)),
                EnumToString(m_state),
                level_key,
                ticket,
                request_id,
                 retcode,
                 DoubleToString(commission,8),
                 DoubleToString(swap,8),
                 DoubleToString(profit,8),
                 4,event_sequence,event_id,
                 deal_ticket,order_ticket,position_ticket,
                 DoubleToString(m_cycle_realized,8),
                 DoubleToString(floating,8),
                 DoubleToString(cycle_net,8),
                 DoubleToString(basket_target,8),
                 "FORMAL_CANDIDATE");
      FileClose(handle);
     }

   void LogEvent(const string kind,
                 const string level_key,
                 const ulong ticket,
                 const double volume,
                 const double price,
                 const string comment)
     {
      ulong deal_ticket=0;
      ulong order_ticket=0;
      ulong position_ticket=0;
      if(kind=="recovery")
         deal_ticket=ticket;
      else if(kind=="pending" || kind=="cancel")
         order_ticket=ticket;
      else if(kind=="stop" || kind=="close")
         position_ticket=ticket;
      WriteTelemetry(kind,level_key,ticket,volume,price,0.0,0.0,
                     comment,0,0,0.0,0.0,0.0,
                     deal_ticket,order_ticket,position_ticket);
     }

   void LogLifecycleEvent(const string kind,
                          const string level_key,
                          const string reason)
     {
      WriteTelemetry(
         kind,level_key,0,0.0,0.0,0.0,0.0,
         reason,0,0,0.0,0.0,0.0,
         0,0,0
       );
     }

   void UpdateAlignmentHoldTelemetry(const bool active)
     {
      if(active)
        {
         if(m_alignment_hold_logged)
            return;
         m_alignment_hold_logged=true;
         LogLifecycleEvent("alignment_hold","","file_present");
         return;
        }
      if(!m_alignment_hold_logged)
         return;
      m_alignment_hold_logged=false;
      LogLifecycleEvent("alignment_release","","file_removed");
     }

   string RequestComment(const MqlTradeRequest &request) const
     {
      if(request.position>0)
        {
         if(PositionSelectByTicket(request.position))
            return PositionGetString(POSITION_COMMENT);
         if(HistoryOrderSelect(request.position))
            return HistoryOrderGetString(request.position,ORDER_COMMENT);
        }
      if(request.order>0)
        {
         if(OrderSelect(request.order))
            return OrderGetString(ORDER_COMMENT);
         if(HistoryOrderSelect(request.order))
            return HistoryOrderGetString(request.order,ORDER_COMMENT);
        }
      if(request.comment!="")
         return request.comment;
      return "";
     }

   void LogTradeRequest(const MqlTradeRequest &request,
                         const MqlTradeResult &result)
     {
      string kind="trade_request";
      if(request.action==TRADE_ACTION_PENDING)
         kind="pending_request";
      else if(request.action==TRADE_ACTION_SLTP)
         kind="stop_request";
      else if(request.action==TRADE_ACTION_REMOVE)
         kind="cancel_request";
      else if(request.action==TRADE_ACTION_DEAL && request.position>0)
         kind="close_request";
      string comment=RequestComment(request);
      double event_price=(request.action==TRADE_ACTION_SLTP
                          ? request.sl
                          : request.price);
      ulong order_ticket=(
         request.order>0 ? request.order : result.order
      );
      WriteTelemetry(kind,comment,request.order,request.volume,event_price,
                     request.sl,request.tp,comment,
                     (ulong)result.request_id,result.retcode,
                     0.0,0.0,0.0,
                     0,order_ticket,request.position);
     }

   void WriteRuntimeManifest(void) const
     {
      string path=StringFormat("StraddleReplicaV2_%I64u_%s_manifest.csv",
                               m_runtime.magic,m_runtime.symbol);
      int handle=FileOpen(path,
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return;
      FileWrite(handle,"key","value");
      FileWrite(handle,"schema_version","3");
      FileWrite(handle,"runtime_mode",(int)m_runtime.runtime_mode);
      FileWrite(handle,"runtime_magic",m_runtime.magic);
      FileWrite(handle,"runtime_replica_mode",(int)m_runtime.replica_mode);
      FileWrite(handle,"runtime_inter_order_delay_ms",
                m_runtime.inter_order_delay_ms);
      FileWrite(handle,"runtime_deviation_points",
                m_runtime.deviation_points);
      FileWrite(handle,"runtime_require_demo_account",
                (int)m_runtime.require_demo_account);
      FileWrite(handle,"runtime_expected_account_login",
                m_runtime.expected_account_login);
      FileWrite(handle,"runtime_safety_enabled",
                (int)m_runtime.safety_enabled);
      FileWrite(handle,"runtime_max_equity_loss_pct",
                DoubleToString(m_runtime.max_equity_loss_pct,10));
      FileWrite(handle,"runtime_max_gross_lots",
                DoubleToString(m_runtime.max_gross_lots,10));
      FileWrite(handle,"runtime_max_spread_points",
                DoubleToString(m_runtime.max_spread_points,10));
      FileWrite(handle,"runtime_daily_loss_limit",
                DoubleToString(m_runtime.daily_loss_limit,10));
      FileWrite(handle,"runtime_shadow_command_max_age_ms",
                m_runtime.shadow_command_max_age_ms);
      FileWrite(handle,"runtime_shadow_adopt_existing_cycle",
                (int)m_runtime.allow_shadow_adopt_existing_cycle);
      FileWrite(handle,"profile",(int)m_profile.profile);
      FileWrite(handle,"profile_levels_per_side",
                m_profile.levels_per_side);
      FileWrite(handle,"profile_step_mode",(int)m_profile.step_mode);
      FileWrite(handle,"profile_fixed_step",
                DoubleToString(m_profile.fixed_step,10));
      FileWrite(handle,"profile_anchor_divisor",
                DoubleToString(m_profile.anchor_divisor,10));
      FileWrite(handle,"profile_atr_timeframe",
                (int)m_profile.atr_timeframe);
      FileWrite(handle,"profile_atr_period",m_profile.atr_period);
      FileWrite(handle,"profile_atr_multiplier",
                DoubleToString(m_profile.atr_multiplier,10));
      FileWrite(handle,"profile_lock_trigger_steps",
                DoubleToString(m_profile.lock_trigger_steps,10));
      FileWrite(handle,"profile_lock_offset_price",
                DoubleToString(m_profile.lock_offset_price,10));
      FileWrite(handle,"profile_activation_uses_trailing_distance",
                (int)m_profile.activation_uses_trailing_distance);
      FileWrite(handle,"profile_pre_tighten_trail_distance_steps",
                DoubleToString(m_profile.pre_tighten_trail_distance_steps,10));
      FileWrite(handle,"profile_tighten_trigger_steps",
                DoubleToString(m_profile.tighten_trigger_steps,10));
      FileWrite(handle,"profile_trail_distance_steps",
                DoubleToString(m_profile.trail_distance_steps,10));
      FileWrite(handle,"profile_cycle_target_balance_pct",
                DoubleToString(m_profile.cycle_target_balance_pct,10));
      FileWrite(handle,"profile_cycle_target_money",
                DoubleToString(m_profile.cycle_target_money,10));
      FileWrite(handle,"profile_cancel_before_close",
                (int)m_profile.cancel_before_close);
      FileWrite(handle,"profile_deployment_fill_cooldown_seconds",
                m_profile.deployment_fill_cooldown_seconds);
      FileWrite(handle,"profile_close_interval_seconds",
                m_profile.close_interval_seconds);
      FileWrite(handle,"profile_restart_delay_ms",
                m_profile.restart_delay_ms);
      FileWrite(handle,"profile_rearm_delay_seconds",
                m_profile.rearm_delay_seconds);
      FileWrite(handle,"profile_stop_update_interval_seconds",
                m_profile.stop_update_interval_seconds);
      FileWrite(handle,"profile_max_stop_updates_per_pass",
                m_profile.max_stop_updates_per_pass);
      FileWrite(handle,"profile_stop_scan_newest_first",
                (int)m_profile.stop_scan_newest_first);
      FileWrite(handle,"profile_stop_updates_on_timer",
                (int)m_profile.stop_updates_on_timer);
      FileWrite(handle,"profile_trend_rescue_enabled",
                (int)m_profile.trend_rescue_enabled);
      FileWrite(handle,"profile_trend_rescue_timeframe",
                (int)m_profile.trend_rescue_timeframe);
      FileWrite(handle,"profile_trend_rescue_bars",
                m_profile.trend_rescue_bars);
      FileWrite(handle,"profile_trend_rescue_minimum_pending_levels",
                m_profile.trend_rescue_minimum_pending_levels);
      FileWrite(handle,"profile_trend_rescue_move_price",
                DoubleToString(m_profile.trend_rescue_move_price,10));
      FileWrite(handle,"profile_trend_rescue_drawdown_money",
                DoubleToString(m_profile.trend_rescue_drawdown_money,10));
      FileWrite(handle,"profile_trend_rescue_volume_multiplier",
                DoubleToString(
                   m_profile.trend_rescue_volume_multiplier,
                   10
                ));
      for(int index=0;index<m_profile.levels_per_side;index++)
         FileWrite(handle,
                   StringFormat("profile_lot_%02d",index+1),
                   DoubleToString(m_profile.lots[index],10));
      FileWrite(handle,"account_server",AccountInfoString(ACCOUNT_SERVER));
      FileWrite(handle,"account_leverage",AccountInfoInteger(ACCOUNT_LEVERAGE));
      FileWrite(handle,"account_currency",AccountInfoString(ACCOUNT_CURRENCY));
      FileWrite(handle,"account_margin_mode",AccountInfoInteger(ACCOUNT_MARGIN_MODE));
      FileWrite(handle,"account_limit_orders",AccountInfoInteger(ACCOUNT_LIMIT_ORDERS));
      FileWrite(handle,"symbol",m_runtime.symbol);
      FileWrite(handle,"symbol_digits",SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS));
      FileWrite(handle,"symbol_tick_size",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_SIZE),10));
      FileWrite(handle,"symbol_tick_value",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_VALUE),10));
      FileWrite(handle,"symbol_tick_value_profit",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_VALUE_PROFIT),10));
      FileWrite(handle,"symbol_tick_value_loss",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_VALUE_LOSS),10));
      FileWrite(handle,"symbol_contract_size",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_CONTRACT_SIZE),10));
      FileWrite(handle,"symbol_volume_min",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_VOLUME_MIN),10));
      FileWrite(handle,"symbol_volume_max",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_VOLUME_MAX),10));
      FileWrite(handle,"symbol_volume_step",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_VOLUME_STEP),10));
      FileWrite(handle,"symbol_stops_level",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_STOPS_LEVEL));
      FileWrite(handle,"symbol_freeze_level",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_FREEZE_LEVEL));
      FileWrite(handle,"symbol_filling_mode",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_FILLING_MODE));
      FileWrite(handle,"symbol_swap_mode",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_SWAP_MODE));
      FileWrite(handle,"symbol_swap_long",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_SWAP_LONG),10));
      FileWrite(handle,"symbol_swap_short",
                DoubleToString(SymbolInfoDouble(m_runtime.symbol,SYMBOL_SWAP_SHORT),10));
      FileWrite(handle,"symbol_swap_rollover3days",
                SymbolInfoInteger(m_runtime.symbol,SYMBOL_SWAP_ROLLOVER3DAYS));
      FileClose(handle);
     }

   double ContractScale(void) const
     {
      double contract_size=SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_CONTRACT_SIZE);
      if(contract_size<=0.0)
         return 1.0;
      return contract_size/100.0;
     }

   bool PendingPriceIsValid(const bool is_buy,const double price) const
     {
      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick))
         return false;
      double stops_distance=(double)SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_STOPS_LEVEL)*m_point;
      double freeze_distance=(double)SymbolInfoInteger(m_runtime.symbol,SYMBOL_TRADE_FREEZE_LEVEL)*m_point;
      double minimum_distance=MathMax(stops_distance,freeze_distance);
      if(is_buy)
         return price>tick.ask+minimum_distance;
      return price<tick.bid-minimum_distance;
     }

   bool IsHistoricalProfile(void) const
     {
      return(m_profile.profile==HISTORICAL_50 ||
             m_profile.profile==HISTORICAL_60);
     }

   bool PlaceLevel(SLevelState &level_state)
     {
      if(level_state.duplicate_identity)
         return false;
      if(level_state.has_pending || level_state.has_position)
         return true;
      if(!PendingPriceIsValid(level_state.is_buy,level_state.target_price))
        {
         string level_comment=StringFormat("STR %s%d",
                                           (level_state.is_buy ? "B" : "S"),
                                           level_state.level);
          if(IsHistoricalProfile() && !level_state.recovery_done)
            {
             if(!ExposureAllowsRearm(level_state.volume))
               {
                LogLifecycleEvent(
                   "safety_rearm_blocked",
                   level_comment,
                   "max_gross_lots"
                );
                return false;
               }
             string recovery_comment=(level_state.is_buy ? "STR ORB" : "STR ORS");
             if(!m_gateway.OpenMarket(level_state.is_buy,
                                      level_state.volume,
                                      recovery_comment))
                return false;
             level_state.rearm_requested=false;
             level_state.rearm_after_msc=0;
             LogEvent("recovery",level_comment,m_gateway.LastDeal(),
                      level_state.volume,level_state.target_price,recovery_comment);
           }
         else if(!level_state.recovery_done)
            LogEvent("deferred",level_comment,0,level_state.volume,
                     level_state.target_price,"crossed");
         level_state.recovery_done=true;
         return true;
        }
      string comment=StringFormat("STR %s%d",(level_state.is_buy ? "B" : "S"),level_state.level);
      if(!m_gateway.PlaceStop(level_state.is_buy,
                              level_state.volume,
                              level_state.target_price,
                              comment))
         return false;
       level_state.has_pending=true;
       level_state.order_ticket=m_gateway.LastOrder();
       level_state.rearm_requested=false;
       level_state.rearm_after_msc=0;
      LogEvent("pending",comment,level_state.order_ticket,level_state.volume,level_state.target_price,comment);
      return true;
     }

   long CurrentServerMs(void) const
     {
      MqlTick tick={};
      if(SymbolInfoTick(m_runtime.symbol,tick) && tick.time_msc>0)
         return tick.time_msc;
      return (long)TimeCurrent()*1000;
     }

   bool RearmDelayElapsed(const SLevelState &level_state) const
     {
      return(level_state.rearm_after_msc<=0 ||
             !(CurrentServerMs()<level_state.rearm_after_msc));
     }

   void ScheduleLevelRearm(const string level_comment,
                           const long exit_time_msc=0)
     {
      bool is_buy=false;
      int index=-1;
      if(!ParseLevelComment(level_comment,is_buy,index))
         return;
       long rearm_base_msc=(
          exit_time_msc>0 ? exit_time_msc : CurrentServerMs()
       );
       long rearm_after_msc=(
          rearm_base_msc+
          (long)m_profile.rearm_delay_seconds*1000
       );
        if(is_buy)
          {
           m_buy_levels[index].volume=m_profile.lots[index];
           m_buy_levels[index].rearm_requested=true;
           m_buy_levels[index].rearm_after_msc=rearm_after_msc;
          }
        else
          {
           m_sell_levels[index].volume=m_profile.lots[index];
           m_sell_levels[index].rearm_requested=true;
           m_sell_levels[index].rearm_after_msc=rearm_after_msc;
          }
     }

   bool DealMetadataReady(const ulong deal_ticket) const
     {
      long deal_time_msc=0;
      long deal_magic=0;
      long entry_value=0;
      long position_id=0;
      long order_ticket=0;
      double deal_volume=0.0;
      double deal_price=0.0;
      string deal_symbol="";
      if(!HistoryDealGetInteger(
            deal_ticket,
            DEAL_TIME_MSC,
            deal_time_msc
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_MAGIC,
            deal_magic
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_ENTRY,
            entry_value
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_POSITION_ID,
            position_id
         ) ||
         !HistoryDealGetInteger(
            deal_ticket,
            DEAL_ORDER,
            order_ticket
         ) ||
         !HistoryDealGetDouble(
            deal_ticket,
            DEAL_VOLUME,
            deal_volume
         ) ||
         !HistoryDealGetDouble(
            deal_ticket,
            DEAL_PRICE,
            deal_price
         ) ||
         !HistoryDealGetString(
            deal_ticket,
            DEAL_SYMBOL,
            deal_symbol
         ))
         return false;
      if(deal_time_msc<=0 ||
         position_id<=0 ||
         order_ticket<=0 ||
         deal_volume<=0.0 ||
         deal_price<=0.0 ||
         deal_symbol=="")
         return false;
      long metadata_age_msc=CurrentServerMs()-deal_time_msc;
      if(deal_symbol==m_runtime.symbol &&
         deal_magic==0 &&
         metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
         return false;
      if((ulong)deal_magic!=m_runtime.magic ||
         deal_symbol!=m_runtime.symbol)
         return true;
      string deal_comment="";
      if(!HistoryDealGetString(
            deal_ticket,
            DEAL_COMMENT,
            deal_comment
         ))
         return false;
      string level_comment=PositionCommentFromDeal(deal_ticket);
      if(level_comment=="" &&
         deal_comment=="" &&
         metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
         return false;
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)entry_value;
      if(entry==DEAL_ENTRY_OUT ||
         entry==DEAL_ENTRY_OUT_BY ||
         entry==DEAL_ENTRY_INOUT)
        {
         long reason_value=0;
         if(!HistoryDealGetInteger(
               deal_ticket,
               DEAL_REASON,
               reason_value
            ))
            return false;
         if(reason_value==DEAL_REASON_CLIENT &&
            metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
            return false;
         if(deal_comment=="" &&
            metadata_age_msc<STR_DEAL_METADATA_SETTLE_MS)
            return false;
         bool stop_exit=(
            reason_value==DEAL_REASON_SL ||
            StringFind(deal_comment,"[sl")==0 ||
            StringFind(deal_comment,"sl ")==0
         );
         bool level_is_buy=false;
         int level_index=-1;
         if(stop_exit &&
            !ParseLevelComment(
               level_comment,
               level_is_buy,
               level_index
            ))
            return false;
        }
      return true;
     }

   long CurrentUtcMs(void) const
     {
      return (long)TimeGMT()*1000;
     }

   bool ReadShadowCommand(SShadowCommand &command) const
     {
      int handle=FileOpen(m_runtime.shadow_command_file,
                          FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return false;
      for(int index=0;index<9;index++)
        {
         if(FileIsEnding(handle))
           {
            FileClose(handle);
            return false;
           }
         FileReadString(handle);
        }
      if(FileIsEnding(handle))
        {
         FileClose(handle);
         return false;
        }
      command.schema_version=(int)StringToInteger(FileReadString(handle));
      command.command_seq=(ulong)StringToInteger(FileReadString(handle));
      command.command=FileReadString(handle);
      command.cycle_id=FileReadString(handle);
      command.profile=FileReadString(handle);
      command.anchor=StringToDouble(FileReadString(handle));
      command.step=StringToDouble(FileReadString(handle));
      command.target_start_utc_ms=(long)StringToInteger(FileReadString(handle));
      command.expires_utc_ms=(long)StringToInteger(FileReadString(handle));
      FileClose(handle);
      return true;
     }

   bool ReadShadowAckState(ulong &command_seq,
                           string &status,
                           string &cycle_id) const
     {
      command_seq=0;
      status="";
      cycle_id="";
      int handle=FileOpen(m_runtime.shadow_ack_file,
                          FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return false;
      for(int index=0;index<6;index++)
        {
         if(FileIsEnding(handle))
           {
            FileClose(handle);
            return false;
           }
         FileReadString(handle);
        }
      if(FileIsEnding(handle))
        {
         FileClose(handle);
         return false;
        }
      int schema_version=(int)StringToInteger(FileReadString(handle));
      command_seq=(ulong)StringToInteger(FileReadString(handle));
      status=FileReadString(handle);
      cycle_id=FileReadString(handle);
      FileClose(handle);
      return(schema_version==1);
     }

   void WriteShadowAck(const string status,
                       const ulong command_seq,
                       const string reason) const
     {
      int handle=FileOpen(m_runtime.shadow_ack_file,
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,
                          ',');
      if(handle==INVALID_HANDLE)
         return;
      FileWrite(handle,
                "schema_version","command_seq","status","cycle_id",
                "utc_time","reason");
      FileWrite(handle,
                1,command_seq,status,m_cycle_id,IsoUtcNow(),reason);
      FileClose(handle);
     }

   bool StartShadowCycle(const double anchor,const double step)
     {
      if(m_halted || anchor<=0.0 || step<=0.0)
         return false;
      if(OwnedOrderCount()>0 || OwnedPositionCount()>0 || m_state!=CYCLE_IDLE)
         return false;
      ResetLevelState();
      m_anchor=NormalizePrice(anchor);
      m_step=NormalizePrice(step);
      if(m_anchor<=0.0 || m_step<=0.0)
         return false;
      InitializeLevelTargets();
      m_cycle_start_balance=AccountInfoDouble(ACCOUNT_BALANCE);
      m_cycle_realized=0.0;
      m_cycle_exit_deal_count=0;
      m_cycle_started_at=TimeCurrent();
      m_cycle_started_utc=TimeGMT();
       m_cycle_started_msc=(long)m_cycle_started_at*1000;
       m_cycle_started_ms=GetTickCount64();
       m_event_sequence=0;
       ResetProcessedDeals();
       m_last_history_reconcile_ms=0;
       m_history_reconcile_seeded=false;
       GlobalVariableSet(GlobalKey("event_seq"),0.0);
      m_last_stop_update_at=0;
      m_last_entry_fill_at=0;
      m_deploy_index=0;
      m_has_traded=false;
      m_shadow_reset_active=false;
      m_state=CYCLE_DEPLOYING;
      PersistCycle();
      LogEvent("cycle_start","",0,0.0,m_anchor,"");
      return true;
     }

   bool AdoptExistingShadowCycle(void)
     {
      if(m_runtime.runtime_mode!=STR_RUNTIME_SHADOW ||
         !m_runtime.allow_shadow_adopt_existing_cycle ||
         (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=
            ACCOUNT_TRADE_MODE_DEMO ||
         m_runtime.expected_account_login==0 ||
         OwnedOrderCount()+OwnedPositionCount()==0)
         return false;
      m_cycle_id=StringFormat(
         "local-adopt-%I64u-%I64d",
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
         (long)TimeGMT()
      );
      if(!RestoreCycle())
        {
         m_cycle_id="";
         return false;
        }
      PersistShadowSequence();
      LogEvent("shadow_adopt","",0,0.0,0.0,"existing_cycle");
      WriteShadowAck("ADOPTED",
                     m_shadow_last_command_seq,
                     "existing_cycle");
      return true;
     }

   void CompleteShadowReset(void)
     {
      m_shadow_reset_active=false;
      m_halted=false;
      m_state=CYCLE_IDLE;
      LogLifecycleEvent("cycle_complete","","flat");
      LogEvent("shadow_reset_complete","",0,0.0,0.0,"");
      WriteShadowAck("FLAT",m_shadow_last_command_seq,"");
      ClearPersistence();
      m_cycle_id="";
     }

   void BeginShadowReset(void)
     {
      m_shadow_reset_active=true;
      m_halted=false;
      if(OwnedOrderCount()>0)
         m_state=CYCLE_CANCELING;
      else if(OwnedPositionCount()>0)
         m_state=CYCLE_CLOSING;
      else
        {
         CompleteShadowReset();
         return;
        }
      PersistCycle();
      LogEvent("shadow_reset_begin","",0,0.0,0.0,"");
     }

   void PollShadowCommand(void)
     {
      if(m_runtime.runtime_mode!=STR_RUNTIME_SHADOW)
         return;
      SShadowCommand command={};
      if(!ReadShadowCommand(command))
         return;
      if(command.command_seq<=m_shadow_last_command_seq)
         return;
      long now_ms=CurrentUtcMs();
      if(command.schema_version!=1 ||
         command.expires_utc_ms<now_ms ||
         now_ms-command.target_start_utc_ms>
            m_runtime.shadow_command_max_age_ms)
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"stale");
         WriteShadowAck("REJECTED",command.command_seq,"stale_or_schema");
         return;
        }
      if(command.command=="RESET")
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         WriteShadowAck("RESETTING",command.command_seq,"");
         BeginShadowReset();
         return;
        }
      if(command.command!="START" ||
         command.profile!="LATEST_30" ||
         m_profile.profile!=LATEST_30)
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"command");
         WriteShadowAck("REJECTED",command.command_seq,"invalid_command");
         return;
        }
      if(OwnedOrderCount()>0 || OwnedPositionCount()>0 || m_state!=CYCLE_IDLE)
        {
         m_shadow_last_command_seq=command.command_seq;
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"not_flat");
         WriteShadowAck("REJECTED",command.command_seq,"not_flat");
         return;
        }
      m_shadow_last_command_seq=command.command_seq;
      m_cycle_id=command.cycle_id;
      if(!StartShadowCycle(command.anchor,command.step))
        {
         PersistShadowSequence();
         LogEvent("shadow_start_rejected","",0,0.0,0.0,"start_failed");
         WriteShadowAck("REJECTED",command.command_seq,"start_failed");
         return;
        }
      PersistShadowSequence();
      WriteShadowAck("STARTED",command.command_seq,"");
     }

   bool StartCycle(void)
     {
      if(m_halted)
         return false;
      if(OwnedOrderCount()>0 || OwnedPositionCount()>0)
         return false;
      if(m_runtime.start_time>0 && TimeCurrent()<m_runtime.start_time)
         return false;
      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick) || tick.bid<=0.0 || tick.ask<=0.0)
         return false;
      ResetLevelState();
      m_anchor=NormalizePrice((tick.bid+tick.ask)/2.0);
      m_step=CalculateStep(m_anchor);
      if(m_step<=0.0)
         return false;
      InitializeLevelTargets();
      m_cycle_start_balance=AccountInfoDouble(ACCOUNT_BALANCE);
      m_cycle_realized=0.0;
      m_cycle_exit_deal_count=0;
      m_cycle_started_at=TimeCurrent();
      m_cycle_started_utc=TimeGMT();
      m_cycle_started_msc=(long)m_cycle_started_at*1000;
      m_cycle_started_ms=GetTickCount64();
       m_cycle_id=CycleIdFromUtc("local",m_cycle_started_utc);
       m_event_sequence=0;
       ResetProcessedDeals();
       m_last_history_reconcile_ms=0;
       m_history_reconcile_seeded=false;
       GlobalVariableSet(GlobalKey("event_seq"),0.0);
       GlobalVariableSet(GlobalKey("last_deal"),0.0);
      m_last_stop_update_at=0;
      m_last_entry_fill_at=0;
      m_deploy_index=0;
      m_has_traded=false;
      m_state=CYCLE_DEPLOYING;
      PersistCycle();
      LogEvent("cycle_start","",0,0.0,m_anchor,"");
      return true;
     }

   void DeployOne(void)
     {
      if(m_deploy_index>=m_profile.levels_per_side*2)
        {
         m_state=CYCLE_RUNNING;
         ReconcileLevels();
         PersistCycle();
         LogEvent("deployment_complete","",0,0.0,0.0,"");
         return;
        }
      if(m_profile.deployment_fill_cooldown_seconds>0 &&
         m_last_entry_fill_at>0 &&
         TimeCurrent()-m_last_entry_fill_at<m_profile.deployment_fill_cooldown_seconds)
         return;
      int level_index=m_deploy_index/2;
      bool is_buy=(m_deploy_index%2==0);
      bool placed=(is_buy ? PlaceLevel(m_buy_levels[level_index])
                          : PlaceLevel(m_sell_levels[level_index]));
      if(placed)
         m_deploy_index++;
      else if(m_gateway.LastRetcode()==TRADE_RETCODE_INVALID_PRICE)
        {
         string level_comment=StringFormat(
            "STR %s%d",
            (is_buy ? "B" : "S"),
            level_index+1
         );
         // A broker-side quote can advance between the local tick validation
         // and OrderCheck.  Continuing would leave a partial grid and retry
         // this level indefinitely.  Cancel only our pending orders, then
         // restart from a fresh anchor after the configured flat delay.
         m_state=CYCLE_CANCELING;
         PersistCycle();
         LogLifecycleEvent(
            "deployment_price_rejected",
            level_comment,
            "invalid_price"
         );
         LogEvent(
            "deployment_abort",
            level_comment,
            0,
            0.0,
            0.0,
            "invalid_price"
         );
        }
     }

   void RearmOneMissingLevel(void)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
          if(m_buy_levels[index].rearm_requested &&
             !m_buy_levels[index].has_pending &&
             !m_buy_levels[index].has_position &&
             !m_buy_levels[index].trend_rescue_replacement)
            {
              if(!RearmDelayElapsed(m_buy_levels[index]))
                 continue;
              bool trend_rescue_rearm=(
                 TrendRescuePositionRearmPending(true,index)
              );
              m_buy_levels[index].volume=(
                 m_buy_levels[index].trend_rescue_latched ||
                 trend_rescue_rearm
                 ? m_profile.lots[index]*
                   m_profile.trend_rescue_volume_multiplier
                 : m_profile.lots[index]
             );
              // Target EA parity: re-arms ALWAYS return to the original anchor
              // lattice price. Measured against 1,797 mid-cycle re-arms in the
              // final regime, 99.4% land exactly (<0.1 step) on the price of the
              // same (side,level) slot from the cycle's deployment burst; sell
              // stops were observed re-armed up to 35 steps away from market on
              // the original lattice. The Target EA never re-anchors pendings to
              // market. If the lattice price is currently invalid (market has
              // crossed it), wait for price to return instead of moving the level.
              if(!PendingPriceIsValid(true,m_buy_levels[index].target_price))
                 continue;
             if(!ExposureAllowsRearm(m_buy_levels[index].volume))
               {
                LogLifecycleEvent(
                   "safety_rearm_blocked",
                   StringFormat("STR B%d",m_buy_levels[index].level),
                   "max_gross_lots"
                );
                 return;
                }
              if(PlaceLevel(m_buy_levels[index]))
                {
                 if(trend_rescue_rearm)
                   {
                    ClearTrendRescuePositionRearm(true,index);
                    PersistCycle();
                   }
                }
              return;
            }
          if(m_sell_levels[index].rearm_requested &&
             !m_sell_levels[index].has_pending &&
             !m_sell_levels[index].has_position &&
             !m_sell_levels[index].trend_rescue_replacement)
            {
              if(!RearmDelayElapsed(m_sell_levels[index]))
                 continue;
              bool trend_rescue_rearm=(
                 TrendRescuePositionRearmPending(false,index)
              );
              m_sell_levels[index].volume=(
                 m_sell_levels[index].trend_rescue_latched ||
                 trend_rescue_rearm
                 ? m_profile.lots[index]*
                   m_profile.trend_rescue_volume_multiplier
                 : m_profile.lots[index]
             );
              // Target EA parity: sell-side re-arms also return to the original
              // anchor lattice price (see buy-side note above). Never re-anchor
              // to market; wait for price to return if currently invalid.
              if(!PendingPriceIsValid(false,m_sell_levels[index].target_price))
                 continue;
             if(!ExposureAllowsRearm(m_sell_levels[index].volume))
               {
                LogLifecycleEvent(
                   "safety_rearm_blocked",
                   StringFormat("STR S%d",m_sell_levels[index].level),
                   "max_gross_lots"
                );
                 return;
                }
              if(PlaceLevel(m_sell_levels[index]))
                {
                 if(trend_rescue_rearm)
                   {
                    ClearTrendRescuePositionRearm(false,index);
                    PersistCycle();
                   }
                }
             return;
            }
        }
     }

   double OwnedFloatingProfit(void) const
     {
      double total=0.0;
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)>0 && IsOwnedPositionSelected())
            total+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
        }
      return total;
     }

   int TrendRescueSide(void) const
     {
      if(!m_profile.trend_rescue_enabled ||
         m_profile.trend_rescue_bars<1 ||
         m_profile.trend_rescue_move_price<=0.0 ||
         m_profile.trend_rescue_drawdown_money<=0.0 ||
         m_profile.trend_rescue_volume_multiplier<=1.0 ||
         OwnedFloatingProfit()>-m_profile.trend_rescue_drawdown_money)
         return 0;
      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick))
         return 0;
      double prior_close=iClose(m_runtime.symbol,m_profile.trend_rescue_timeframe,m_profile.trend_rescue_bars);
      if(prior_close<=0.0)
         return 0;
      if(tick.ask-prior_close>=m_profile.trend_rescue_move_price)
         return 1;
      if(prior_close-tick.bid>=m_profile.trend_rescue_move_price)
         return -1;
      return 0;
     }

   bool IsBaseLevelVolume(const int index,const double volume) const
     {
      return MathAbs(volume-m_profile.lots[index])<=1e-8;
     }

   bool HasTrendRescueBasePending(const bool is_buy) const
     {
      int matching_levels=0;
      for(int order_index=0;order_index<OrdersTotal();order_index++)
        {
         ulong ticket=OrderGetTicket(order_index);
         if(ticket==0 || !IsOwnedOrderSelected())
            continue;
         bool order_is_buy=false;
         int index=-1;
         if(!ParseLevelComment(
               OrderGetString(ORDER_COMMENT),
               order_is_buy,
               index
            ) ||
            order_is_buy!=is_buy)
            continue;
         if(IsBaseLevelVolume(
               index,
               OrderGetDouble(ORDER_VOLUME_CURRENT)
            ))
           {
            matching_levels++;
            if(matching_levels>=
               m_profile.trend_rescue_minimum_pending_levels)
               return true;
           }
        }
      return false;
     }

   bool TryCancelTrendRescueLevel(SLevelState &level_state,
                                  const int index)
     {
      if(level_state.trend_rescue_replacement ||
         !level_state.has_pending ||
         level_state.order_ticket==0 ||
         !OrderSelect(level_state.order_ticket) ||
         !IsOwnedOrderSelected() ||
         !IsBaseLevelVolume(
            index,
            OrderGetDouble(ORDER_VOLUME_CURRENT)
         ))
         return false;
      ulong ticket=level_state.order_ticket;
      double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
      double price=OrderGetDouble(ORDER_PRICE_OPEN);
      string comment=OrderGetString(ORDER_COMMENT);
      if(!m_gateway.DeleteOrder(ticket))
         return true;
      level_state.trend_rescue_replacement=true;
      level_state.trend_rescue_latched=true;
      level_state.volume=(
         m_profile.lots[index]*
         m_profile.trend_rescue_volume_multiplier
      );
      level_state.rearm_requested=false;
      level_state.rearm_after_msc=0;
      m_trend_rescue_mask|=TrendRescueBit(index);
      if(level_state.is_buy)
         m_buy_trend_rescue_latched_mask|=TrendRescueBit(index);
      else
         m_sell_trend_rescue_latched_mask|=TrendRescueBit(index);
      PersistCycle();
      LogEvent("cancel",comment,ticket,volume,price,comment);
      return true;
     }

   bool TryCancelOneTrendRescueOrder(const bool is_buy)
     {
      for(int index=m_profile.levels_per_side-1;index>=0;index--)
        {
         if(is_buy)
           {
            if(TryCancelTrendRescueLevel(m_buy_levels[index],index))
               return true;
           }
         else if(TryCancelTrendRescueLevel(
                    m_sell_levels[index],
                    index
                 ))
            return true;
        }
      return false;
     }

   void ClearTrendRescueReplacement(SLevelState &level_state,
                                    const int index)
     {
      level_state.trend_rescue_replacement=false;
      m_trend_rescue_mask&=~TrendRescueBit(index);
     }

   void PlaceOneTrendRescueReplacement(const bool is_buy)
     {
      for(int index=0;index<m_profile.levels_per_side;index++)
        {
         bool marked=(
            is_buy
            ? m_buy_levels[index].trend_rescue_replacement
            : m_sell_levels[index].trend_rescue_replacement
         );
         if(!marked)
            continue;
         if(is_buy)
           {
            if(m_buy_levels[index].has_position)
              {
               ClearTrendRescueReplacement(m_buy_levels[index],index);
               PersistCycle();
               return;
              }
            if(m_buy_levels[index].has_pending)
              {
               if(OrderSelect(m_buy_levels[index].order_ticket) &&
                  !IsBaseLevelVolume(
                     index,
                     OrderGetDouble(ORDER_VOLUME_CURRENT)
                  ))
                 {
                  ClearTrendRescueReplacement(m_buy_levels[index],index);
                  PersistCycle();
                 }
               return;
              }
            if(!PendingPriceIsValid(
                  true,
                  m_buy_levels[index].target_price
               ))
               return;
            m_buy_levels[index].volume=(
               m_profile.lots[index]*
               m_profile.trend_rescue_volume_multiplier
            );
            // The rescue path doubles volume (trend_rescue_volume_multiplier),
            // so it is the FIRST thing to hit max_gross_lots -- and it used to
            // be the only ExposureAllowsRearm site that returned without a log.
            // A rescue that silently no-ops leaves the trend side starved (see
            // PendingPriceIsValid, ~1312) with nothing in telemetry to explain
            // it.  guard_envelope.py measured why this matters: the Target's
            // heaviest final-regime cycle peaked at 2.10 gross lots against the
            // 2.20 cap in latest_30_real_safe.set, a 4.5% margin.
            if(!ExposureAllowsRearm(m_buy_levels[index].volume))
              {
               LogLifecycleEvent(
                  "safety_rearm_blocked",
                  StringFormat("STR B%d",m_buy_levels[index].level),
                  "max_gross_lots_rescue"
               );
               return;
              }
            if(PlaceLevel(m_buy_levels[index]))
              {
               ClearTrendRescueReplacement(m_buy_levels[index],index);
               PersistCycle();
              }
            return;
           }
         if(m_sell_levels[index].has_position)
           {
            ClearTrendRescueReplacement(m_sell_levels[index],index);
            PersistCycle();
            return;
           }
         if(m_sell_levels[index].has_pending)
           {
            if(OrderSelect(m_sell_levels[index].order_ticket) &&
               !IsBaseLevelVolume(
                  index,
                  OrderGetDouble(ORDER_VOLUME_CURRENT)
               ))
              {
               ClearTrendRescueReplacement(m_sell_levels[index],index);
               PersistCycle();
              }
            return;
           }
         if(!PendingPriceIsValid(
               false,
               m_sell_levels[index].target_price
            ))
            return;
         m_sell_levels[index].volume=(
            m_profile.lots[index]*
            m_profile.trend_rescue_volume_multiplier
         );
         // Sell-side twin of the buy-side rescue block above: log the block so a
         // starved trend side is diagnosable instead of mysterious.
         if(!ExposureAllowsRearm(m_sell_levels[index].volume))
           {
            LogLifecycleEvent(
               "safety_rearm_blocked",
               StringFormat("STR S%d",m_sell_levels[index].level),
               "max_gross_lots_rescue"
            );
            return;
           }
         if(PlaceLevel(m_sell_levels[index]))
           {
            ClearTrendRescueReplacement(m_sell_levels[index],index);
            PersistCycle();
           }
         return;
        }
      int completed_side=m_trend_rescue_side;
      m_trend_rescue_side=0;
      m_trend_rescue_replacing=false;
      m_trend_rescue_mask=0;
      PersistCycle();
      LogEvent(
         "trend_rescue_complete",
         "",
         0,
         0.0,
         0.0,
         completed_side>0 ? "buy" : "sell"
      );
     }

   void ProcessTrendRescue(void)
     {
      if(!m_profile.trend_rescue_enabled)
         return;
      int trigger_side=TrendRescueSide();
      if(trigger_side==0 && m_trend_rescue_consumed_side!=0)
        {
         m_trend_rescue_consumed_side=0;
         PersistCycle();
        }
      if(m_trend_rescue_side==0)
        {
         if(trigger_side==0 ||
            trigger_side==m_trend_rescue_consumed_side ||
            !HasTrendRescueBasePending(trigger_side>0))
            return;
         m_trend_rescue_consumed_side=trigger_side;
         MarkTrendRescuePositionRearms(trigger_side>0);
         m_trend_rescue_side=trigger_side;
         m_trend_rescue_replacing=false;
         m_trend_rescue_mask=0;
         PersistCycle();
         LogEvent(
            "trend_rescue_start",
            "",
            0,
            0.0,
            0.0,
            trigger_side>0 ? "buy" : "sell"
         );
        }
      if(m_profile.deployment_fill_cooldown_seconds>0 &&
         m_last_entry_fill_at>0 &&
         TimeCurrent()-m_last_entry_fill_at<
            m_profile.deployment_fill_cooldown_seconds)
         return;
      bool is_buy=(m_trend_rescue_side>0);
      if(!m_trend_rescue_replacing)
        {
         if(TryCancelOneTrendRescueOrder(is_buy))
            return;
         m_trend_rescue_replacing=true;
         PersistCycle();
        }
      PlaceOneTrendRescueReplacement(is_buy);
     }

   double OwnedGrossLots(void) const
     {
      double total=0.0;
      for(int index=0;index<PositionsTotal();index++)
        {
         if(PositionGetTicket(index)>0 && IsOwnedPositionSelected())
            total+=PositionGetDouble(POSITION_VOLUME);
        }
      return total;
     }

   bool ExposureAllowsRearm(const double volume) const
     {
      if(!m_runtime.safety_enabled ||
         m_runtime.max_gross_lots<=0.0)
         return true;
      return(
         OwnedGrossLots()+volume<=
         m_runtime.max_gross_lots+0.0000001
      );
     }

   double TodayOwnedProfit(void) const
     {
      MqlDateTime now={};
      TimeToStruct(TimeCurrent(),now);
      now.hour=0;
      now.min=0;
      now.sec=0;
      datetime day_start=StructToTime(now);
      if(!HistorySelect(day_start,TimeCurrent()))
         return 0.0;
      double total=0.0;
      for(int index=0;index<HistoryDealsTotal();index++)
        {
         ulong ticket=HistoryDealGetTicket(index);
         if(ticket==0)
            continue;
         if((ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)!=m_runtime.magic ||
            HistoryDealGetString(ticket,DEAL_SYMBOL)!=m_runtime.symbol)
            continue;
         total+=HistoryDealGetDouble(ticket,DEAL_PROFIT)
               +HistoryDealGetDouble(ticket,DEAL_SWAP)
               +HistoryDealGetDouble(ticket,DEAL_COMMISSION)
               +HistoryDealGetDouble(ticket,DEAL_FEE);
        }
      return total;
     }

   bool SafetyTriggered(string &reason) const
     {
      if(!m_runtime.safety_enabled)
         return false;
      double equity=AccountInfoDouble(ACCOUNT_EQUITY);
      if(m_runtime.max_equity_loss_pct>0.0 && m_cycle_start_balance>0.0)
        {
         double loss_pct=100.0*(m_cycle_start_balance-equity)/m_cycle_start_balance;
         if(loss_pct>=m_runtime.max_equity_loss_pct)
           {
            reason="equity_loss";
            return true;
           }
        }
      if(m_runtime.max_gross_lots>0.0 && OwnedGrossLots()>m_runtime.max_gross_lots)
        {
         reason="gross_lots";
         return true;
        }
      MqlTick tick={};
      if(m_runtime.max_spread_points>0.0 &&
         SymbolInfoTick(m_runtime.symbol,tick) &&
         (tick.ask-tick.bid)/m_point>m_runtime.max_spread_points)
        {
         reason="spread";
         return true;
        }
      if(m_runtime.daily_loss_limit>0.0 && TodayOwnedProfit()<=-m_runtime.daily_loss_limit)
        {
         reason="daily_loss";
         return true;
        }
      return false;
     }

   void BeginClose(const string reason,const bool halt_after)
     {
      if(m_state==CYCLE_CLOSING || m_state==CYCLE_CANCELING || m_state==CYCLE_HALTED)
         return;
      m_halted=halt_after;
      // Kept in lockstep with m_halted so the terminal "halted" event can name the
      // guard.  Only ever READ while m_halted is true, so the m_halted=false reset
      // sites do not need to clear it.
      m_halt_reason=(halt_after ? reason : "");
      ENUM_CYCLE_STATE replica_close_state=
         (m_profile.cancel_before_close ? CYCLE_CANCELING : CYCLE_CLOSING);
      m_state=(halt_after ? CYCLE_CLOSING : replica_close_state);
      m_last_close_at=0;
      m_close_skip=0;
      PersistCycle();
      LogEvent("close_begin","",0,0.0,0.0,reason);
     }

   // True when the close pacer permits another close request.  Factored out of
   // CloseOnePosition because the CYCLE_RESTARTING handler drains leftover
   // positions by calling TryCloseOneOwnedPosition directly, and without this it
   // drained them at the OnTimer period (100 ms) instead of at
   // close_interval_seconds.  On 111638511 that produced runs of 2-4 market
   // closes 39-127 ms apart on consecutive order tickets -- a cadence the Target
   // never shows (0.2% of its stream in sub-100 ms clusters, versus 11.0% of
   // ours).  Every close request must pass through here.
   bool CloseIntervalElapsed(void) const
     {
      if(m_shadow_reset_active || m_halted)
         return true;
      if(m_profile.close_interval_seconds<=0 || m_last_close_at<=0)
         return true;
      return TimeCurrent()-m_last_close_at>=m_profile.close_interval_seconds;
     }

   // Issues AT MOST ONE close request per invocation.  An older version kept
   // walking the position list after a failed ClosePosition and closed the next
   // one in the same tick, which is how several synchronous OrderSend round-trips
   // ended up inside one 100 ms tick.
   //
   // The anti-stall property that motivated that loop is preserved by
   // m_close_skip: a ticket whose close failed is stepped over on the NEXT
   // invocation rather than in the same one, so a single quote-delayed ticket
   // still cannot block the basket -- it just costs one pacing interval instead
   // of firing a burst.
   //
   // THE WALK DIRECTION IS DESCENDING, AND THAT IS DELIBERATE.  MT5 appends new
   // positions to the end of the list, so a descending walk closes the most
   // recently opened leg first -- LIFO.  The Target's flatten sweep is LIFO:
   // tools/forensics/sweep_lifo.py measures a pair-inversion rate of 0.983 over
   // its 29 post-break sweeps, with 14 of those 29 in EXACTLY reverse-of-open
   // order and 0 of 29 in open order (pre-break: 0.853, 60 exactly reverse, 1
   // exactly forward out of 219).
   //
   // Commit 9a0cf62 briefly changed this to an ascending walk on the stated
   // grounds that the Target "closes positions in ascending level order", citing
   // an audit_sweep_order.py that is not in this repository.  That claim does not
   // reproduce.  tools/forensics/sweep_level_order.py reads the level straight off
   // the Target's OWN position comments -- "STR B7" / "STR S12" matches 17,515 of
   // its 17,632 positions (99.3%) and 1,097 of 1,097 post-break (100.0%) -- and
   // finds NO level ordering at all:
   //
   //   stream               sweeps  legs  median rho(order, level)  inner  outer
   //   Target pre-break        219  2250          -0.086              54     63
   //   Target post-break        29   255          -0.400               2     13
   //
   // Post-break the sign is NEGATIVE and outer-first sweeps outnumber inner-first
   // 13 to 2.  Ascending is the one direction the evidence excludes.  (A geometric
   // reconstruction from the fitted lattice is kept in that script as a
   // cross-check; it agrees with our own comments 47/47 and 31/31 but carries a
   // systematic off-by-one on Target cycles -- 86.1% agreement pre-break, 54.5%
   // post-break, always geo = comment + 1 -- so do not use it for an absolute
   // level.  Being off by one is monotone, which is why it reaches the same
   // verdict.)
   //
   // Level and open time are decoupled here because level is a PER-SIDE
   // coordinate: each wing numbers outward from the anchor independently, so
   // "newest" only means "outermost" inside a one-sided trend.  An earlier note in
   // this repository inferred "newest-first therefore outer-levels-first" from
   // rho(order, open time) = -0.994.  The measurement was right; the inference was
   // not.
   //
   // Do not re-flip this loop to ascending without first re-running sweep_lifo.py
   // and showing the Target's inversion rate below 0.5.  Closing inner legs first
   // to reduce drift exposure during the paced sweep would be a deliberate
   // DIVERGENCE from the Target, and pacing has already been measured as a
   // variance term rather than a bias term: rho(sweep span, cycle exit) = +0.015
   // across 91 Target sweeps (flatten_order.py Panel C).
   bool TryCloseOneOwnedPosition(void)
     {
      int owned=0;
      for(int index=PositionsTotal()-1;index>=0;index--)
        {
         ulong ticket=PositionGetTicket(index);
         if(ticket==0 || !IsOwnedPositionSelected())
            continue;
         owned++;
         if(owned<=m_close_skip)
            continue;
         double volume=PositionGetDouble(POSITION_VOLUME);
         double price=PositionGetDouble(POSITION_PRICE_CURRENT);
         string comment=PositionGetString(POSITION_COMMENT);
         if(m_gateway.ClosePosition(ticket,"STR CLOSE"))
           {
            m_last_close_at=TimeCurrent();
            m_close_skip=0;
            LogEvent("close",comment,ticket,volume,price,"STR CLOSE");
            return true;
           }
         m_last_close_at=TimeCurrent();
         m_close_skip++;
         return false;
        }
      // Either there are no owned positions, or the cursor has walked past the
      // last one.  Rewind so the next pass starts from the top again.
      m_close_skip=0;
      return false;
     }

   void CloseOnePosition(void)
     {
      if(OwnedPositionCount()>0 && !CloseIntervalElapsed())
         return;
      if(TryCloseOneOwnedPosition())
         return;
      // A close that FAILED must not be read as "the basket is flat".  Without
      // this the engine declared cycle_complete/flat on a transient rejection and
      // dropped into CYCLE_RESTARTING with positions still open, which is the
      // state that used to hammer them at the timer period.
      if(OwnedPositionCount()>0)
         return;
      if(m_shadow_reset_active)
        {
         if(OwnedOrderCount()>0)
            m_state=CYCLE_CANCELING;
         else
            CompleteShadowReset();
         return;
        }
      if(!m_halted && m_profile.cancel_before_close)
        {
         m_state=CYCLE_RESTARTING;
         m_restart_started_at=TimeCurrent();
         LogLifecycleEvent("cycle_complete","","flat");
         LogEvent("restart_wait","",0,0.0,0.0,"");
        }
      else
         m_state=CYCLE_CANCELING;
      PersistCycle();
     }

   bool TryCancelOneOwnedOrder(void)
     {
      for(int index=OrdersTotal()-1;index>=0;index--)
        {
         ulong ticket=OrderGetTicket(index);
         if(ticket==0 || !IsOwnedOrderSelected())
            continue;
         string comment=OrderGetString(ORDER_COMMENT);
         double volume=OrderGetDouble(ORDER_VOLUME_CURRENT);
         double price=OrderGetDouble(ORDER_PRICE_OPEN);
         if(m_gateway.DeleteOrder(ticket))
            LogEvent("cancel",comment,ticket,volume,price,comment);
         return true;
        }
      return false;
     }

   void CancelOneOrder(void)
     {
      if(TryCancelOneOwnedOrder())
         return;
      if(m_shadow_reset_active)
        {
         if(OwnedPositionCount()>0)
           {
            m_state=CYCLE_CLOSING;
            m_last_close_at=0;
            m_close_skip=0;
           }
         else
            CompleteShadowReset();
         return;
        }
      if(!m_halted &&
         m_profile.cancel_before_close &&
         OwnedPositionCount()>0)
        {
         m_state=CYCLE_CLOSING;
         m_last_close_at=0;
         m_close_skip=0;
         PersistCycle();
         return;
        }
      if(m_halted)
        {
         m_state=CYCLE_HALTED;
         LogLifecycleEvent("cycle_complete","","flat");
         // Name the guard on the terminal event.  CYCLE_HALTED has no automatic
         // exit, so this is the last thing the EA ever says: it must be
         // self-diagnosing.  Empty here previously.
         LogEvent("halted","",0,0.0,0.0,m_halt_reason);
         ClearPersistence();
        }
      else
        {
         m_state=CYCLE_RESTARTING;
         m_restart_started_at=TimeCurrent();
         LogLifecycleEvent("cycle_complete","","flat");
         PersistCycle();
         LogEvent("restart_wait","",0,0.0,0.0,"");
        }
     }

   void UpdatePositionStops(void)
     {
      datetime now=TimeCurrent();
      if(m_profile.stop_update_interval_seconds>0 &&
         m_last_stop_update_at>0 &&
         now-m_last_stop_update_at<m_profile.stop_update_interval_seconds)
         return;
      m_last_stop_update_at=now;

      MqlTick tick={};
      if(!SymbolInfoTick(m_runtime.symbol,tick))
         return;
      int position_total=PositionsTotal();
      int update_count=0;
      for(int offset=0;offset<position_total;offset++)
        {
         int index=(m_profile.stop_scan_newest_first
                    ? position_total-1-offset
                    : offset);
         ulong ticket=PositionGetTicket(index);
         if(ticket==0 || !IsOwnedPositionSelected())
            continue;
         ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         double entry=PositionGetDouble(POSITION_PRICE_OPEN);
         double current_sl=PositionGetDouble(POSITION_SL);
         double desired=0.0;
         if(!m_stop_scheduler.Calculate(
               type,
               entry,
               current_sl,
               tick.bid,
               tick.ask,
               m_step,
               m_tick_size,
               (int)SymbolInfoInteger(m_runtime.symbol,SYMBOL_DIGITS),
               m_point,
               SymbolInfoInteger(
                  m_runtime.symbol,
                  SYMBOL_TRADE_STOPS_LEVEL
               ),
               m_profile,
               desired))
            continue;
         if(m_gateway.ModifyPosition(ticket,desired))
           {
            LogEvent("stop",PositionGetString(POSITION_COMMENT),ticket,
                     PositionGetDouble(POSITION_VOLUME),desired,"");
            update_count++;
            if(m_profile.max_stop_updates_per_pass>0 &&
               update_count>=m_profile.max_stop_updates_per_pass)
               return;
           }
        }
     }

public:
                     CStraddleEngine(void)
     {
      m_state=CYCLE_IDLE;
      m_anchor=0.0;
      m_step=0.0;
      m_tick_size=0.0;
      m_point=0.0;
      m_cycle_start_balance=0.0;
      m_cycle_realized=0.0;
      m_cycle_exit_deal_count=0;
      m_cycle_started_at=0;
      m_cycle_started_utc=0;
      m_cycle_started_msc=0;
      m_cycle_started_ms=0;
      m_restart_started_at=0;
      m_last_close_at=0;
      m_close_skip=0;
      m_last_entry_fill_at=0;
      m_last_stop_update_at=0;
      m_deploy_index=0;
      m_has_traded=false;
      m_halted=false;
      m_atr_handle=INVALID_HANDLE;
      m_cycle_id="";
        m_shadow_last_command_seq=0;
        m_event_sequence=0;
        m_last_processed_deal_ticket=0;
        m_processed_deal_count=0;
        ArrayResize(m_processed_deal_tickets,0);
        m_pending_deal_count=0;
        ArrayInitialize(m_pending_deal_tickets,0);
         m_last_history_reconcile_ms=0;
         m_history_reconcile_seeded=false;
         m_shadow_reset_active=false;
         m_alignment_hold_logged=false;
       ResetLevelState();
      }

   bool Initialize(const SRuntimeConfig &runtime,
                   const ENUM_STR_PROFILE selected_profile,
                   const SCustomProfileConfig &custom)
     {
      m_runtime=runtime;
      if(m_runtime.symbol=="")
         m_runtime.symbol=_Symbol;
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         ((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=
          ACCOUNT_TRADE_MODE_DEMO ||
          m_runtime.expected_account_login==0 ||
          m_runtime.shadow_command_file=="" ||
          m_runtime.shadow_ack_file=="" ||
          m_runtime.shadow_command_max_age_ms<1))
        {
         Print("[STR] Shadow mode requires a demo account and valid command settings.");
         return false;
        }
      if(m_runtime.require_demo_account &&
         (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)!=
         ACCOUNT_TRADE_MODE_DEMO)
        {
         Print("[STR] Initialization refused: a demo account is required.");
         return false;
        }
      if(m_runtime.require_bound_account &&
         m_runtime.expected_account_login==0)
        {
         Print("[STR] Initialization refused: bound account login is required.");
         return false;
        }
      if(m_runtime.expected_account_login>0 &&
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN)!=
         m_runtime.expected_account_login)
        {
         PrintFormat(
            "[STR] Initialization refused: login=%I64u expected=%I64u.",
            (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
            m_runtime.expected_account_login
         );
         return false;
        }
      if((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING)
        {
         Print("[STR] A hedging account is required.");
         return false;
        }
      if(!SymbolSelect(m_runtime.symbol,true))
        {
         PrintFormat("[STR] Unable to select symbol %s",m_runtime.symbol);
         return false;
        }
      m_deal_ledger.Configure(m_runtime.magic,m_runtime.symbol);
      bool profile_loaded=(selected_profile==CUSTOM_PROFILE
                           ? LoadCustomProfile(custom,m_profile)
                           : LoadProfileConfig(selected_profile,m_profile));
      if(!profile_loaded)
        {
         Print("[STR] Invalid strategy profile.");
         return false;
        }
      long order_limit=AccountInfoInteger(ACCOUNT_LIMIT_ORDERS);
      if(order_limit>0 &&
         order_limit<m_profile.levels_per_side*2 &&
         m_runtime.runtime_mode!=STR_RUNTIME_SHADOW)
        {
         PrintFormat("[STR] Account order limit %d is below required %d.",
                     order_limit,m_profile.levels_per_side*2);
         return false;
        }

      m_tick_size=SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_TICK_SIZE);
      m_point=SymbolInfoDouble(m_runtime.symbol,SYMBOL_POINT);
      if(m_tick_size<=0.0 || m_point<=0.0)
        {
         Print("[STR] Invalid symbol tick configuration.");
         return false;
        }
      m_gateway.Initialize(m_runtime.symbol,m_runtime.magic,m_runtime.deviation_points);
      if(m_profile.step_mode==STR_STEP_ATR)
        {
         m_atr_handle=iATR(m_runtime.symbol,m_profile.atr_timeframe,m_profile.atr_period);
         if(m_atr_handle==INVALID_HANDLE)
           {
            PrintFormat("[STR] Unable to create ATR handle error=%d",GetLastError());
            return false;
           }
        }
      m_telemetry_file=StringFormat("StraddleReplicaV2_%I64u_%s.csv",
                                    m_runtime.magic,m_runtime.symbol);
      WriteRuntimeManifest();
       ResetLevelState();
       m_state=CYCLE_IDLE;
       m_halted=false;
       m_alignment_hold_logged=false;
       string restored_shadow_cycle="";
      string restored_shadow_status="";
      SShadowCommand restored_shadow_command={};
      bool has_restored_shadow_command=false;
      bool shadow_command_available=false;
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
        {
         FolderCreate("StraddleShadow",FILE_COMMON);
         RestoreShadowSequence();
         ulong acknowledged_sequence=0;
         string acknowledged_status="";
         string acknowledged_cycle="";
         if(ReadShadowAckState(acknowledged_sequence,
                               acknowledged_status,
                               acknowledged_cycle))
           {
            if(acknowledged_sequence>m_shadow_last_command_seq)
               m_shadow_last_command_seq=acknowledged_sequence;
            restored_shadow_cycle=acknowledged_cycle;
            restored_shadow_status=acknowledged_status;
           }
         if(ReadShadowCommand(restored_shadow_command))
           {
            shadow_command_available=true;
            if(restored_shadow_command.command_seq==
               m_shadow_last_command_seq)
              {
               has_restored_shadow_command=true;
               if(restored_shadow_cycle=="" &&
                  restored_shadow_command.command=="START")
                  restored_shadow_cycle=restored_shadow_command.cycle_id;
              }
           }
         PersistShadowSequence();
        }
      bool has_owned_cycle=(OwnedOrderCount()>0 || OwnedPositionCount()>0);
      bool has_persisted_restart=(
         !has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_NORMAL &&
         GlobalVariableCheck(GlobalKey("state")) &&
         (ENUM_CYCLE_STATE)(int)GlobalVariableGet(GlobalKey("state"))==
         CYCLE_RESTARTING
      );
      bool adopted_existing_shadow_cycle=false;
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         shadow_command_available &&
         restored_shadow_command.command=="START" &&
         restored_shadow_command.command_seq>=m_shadow_last_command_seq)
        {
         restored_shadow_cycle=restored_shadow_command.cycle_id;
         m_shadow_last_command_seq=restored_shadow_command.command_seq;
         has_restored_shadow_command=true;
         PersistShadowSequence();
        }
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         restored_shadow_cycle=="")
        {
         if(!m_runtime.allow_shadow_adopt_existing_cycle)
           {
            Print("[STR] existing_cycle_adoption_disabled: shadow cycle identity could not be restored safely.");
            return false;
           }
         if(!AdoptExistingShadowCycle())
           {
            Print("[STR] Existing shadow cycle adoption failed safely.");
            return false;
           }
         adopted_existing_shadow_cycle=true;
         restored_shadow_cycle=m_cycle_id;
         restored_shadow_status="ADOPTED";
        }
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         !adopted_existing_shadow_cycle)
         m_cycle_id=restored_shadow_cycle;
      if((has_owned_cycle || has_persisted_restart) &&
         !adopted_existing_shadow_cycle &&
         !RestoreCycle())
        {
         Print("[STR] Existing cycle could not be restored safely.");
         return false;
        }
      if(has_owned_cycle &&
         m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
         (restored_shadow_status=="RESETTING" ||
          (has_restored_shadow_command &&
           restored_shadow_command.command=="RESET")))
        {
         m_shadow_reset_active=true;
         BeginShadowReset();
         WriteShadowAck("RESETTING",
                        m_shadow_last_command_seq,
                        "restored");
        }
      else if(has_owned_cycle &&
              m_runtime.runtime_mode==STR_RUNTIME_SHADOW &&
              has_restored_shadow_command &&
              restored_shadow_command.command=="START" &&
              restored_shadow_status!="STARTED")
         WriteShadowAck("STARTED",
                        m_shadow_last_command_seq,
                        "restored");
      if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
        {
         if(!has_owned_cycle)
           {
            m_cycle_id="";
            WriteShadowAck("FLAT",m_shadow_last_command_seq,"initialized");
           }
        }
      int timer_ms=MathMax(20,m_runtime.inter_order_delay_ms);
      if(!EventSetMillisecondTimer(timer_ms))
        {
         PrintFormat("[STR] Unable to start millisecond timer error=%d",GetLastError());
         return false;
        }
      PrintFormat("[STR] Initialized profile=%s symbol=%s levels=%d replica=%s mode=%s",
                  EnumToString(selected_profile),
                  m_runtime.symbol,
                  m_profile.levels_per_side,
                  (m_runtime.replica_mode ? "true" : "false"),
                  EnumToString(m_runtime.runtime_mode));
      return true;
     }

   void Shutdown(void)
     {
      EventKillTimer();
      PersistCycle();
      if(m_atr_handle!=INVALID_HANDLE)
        {
         IndicatorRelease(m_atr_handle);
         m_atr_handle=INVALID_HANDLE;
        }
     }

   void OnTick(void)
     {
       if(m_state==CYCLE_IDLE)
         {
          if(AlignmentHoldActive())
            {
             UpdateAlignmentHoldTelemetry(true);
             return;
            }
          UpdateAlignmentHoldTelemetry(false);
          if(m_pending_deal_count>0)
             return;
         if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
            return;
         if(StartCycle())
            DeployOne();
         return;
        }
       if(m_state!=CYCLE_RUNNING)
          return;
       ReconcileLevels();
       if(!m_profile.stop_updates_on_timer)
          UpdatePositionStops();

       CheckCycleTargets();
      }

    void CheckCycleTargets(void)
      {
       if(m_state!=CYCLE_RUNNING && m_state!=CYCLE_DEPLOYING)
          return;
       if(!m_has_traded && OwnedPositionCount()==0)
          return;

       string safety_reason="";
       if(SafetyTriggered(safety_reason))
         {
          BeginClose(safety_reason,true);
          return;
         }

       double scale=ContractScale();
       double target=(m_profile.cycle_target_money>0.0
                      ? m_profile.cycle_target_money*scale
                      : m_cycle_start_balance*m_profile.cycle_target_balance_pct/100.0);
       double floating=OwnedFloatingProfit();
       SBasketSnapshot basket=m_basket_evaluator.Evaluate(
          m_cycle_realized,
          floating,
          target,
          (m_has_traded || OwnedPositionCount()>0)
       );
       if(basket.triggered)
         {
          LogLifecycleEvent("basket_trigger","","threshold_reached");
          BeginClose("basket_target",false);
          return;
         }

       // ------------------------------------------------------------------
       // The $30 basket target above is the Target EA's ONLY money exit.
       //
       // Two further exit rules previously lived here -- a 20-point
       // "grid_recenter" and a "rescue_breakeven" liquidation.  Both were
       // written from the mission brief's hypotheses and never measured.
       // Both are now refuted against the 901018 dataset (100 final-regime
       // cycles delimited by their own flatten sweeps).  See
       // tools/forensics/q3p_replicarules.py for the scoring harness; it
       // reports, for every candidate rule, the first tick at which the rule
       // would have fired versus the tick at which the Target EA actually
       // closed:
       //
       //   grid_recenter   (dist>=20 || (realized>=50 && net>=-20 && dist>=15))
       //       would fire on 49/100 cycles, 27 of them >5 min early, at a
       //       median net of -$19.36 where the Target EA went on to bank
       //       +$36.00.  Aggregate profit destroyed: $5,738.88.  Both clauses
       //       are equally culpable (27 and 26 of 100).  The distance gate
       //       does not even separate the exit groups: cycles that exited on
       //       the money target were >=20 pts from the anchor 18/72 of the
       //       time, versus 1/6 for the below-zero exits.
       //
       //   rescue_breakeven (realized>=200 && net>=-10)
       //       would fire on 14/100 cycles, 9 of them >5 min early, at a
       //       median net of +$10.16 where the Target EA banked +$42.62.
       //       Aggregate profit destroyed: $623.52.  Decisively, the marked
       //       total at exit has ZERO cycles in [-25,0) under two independent
       //       segmentations -- a "close at breakeven" rule would pile up
       //       exactly there.
       //
       // A flat threshold on realized_since_cycle_start + floating is the
       // whole rule.  FOUR independent estimators agree on its value:
       // exact burst-flatten total 29.31, whole-sweep total 29.36,
       // decision-instant marked total 30.46, and -- the only one that needs
       // no price mark at all -- the median money actually BANKED at the exit
       // across 99 cycles, 29.32.  That last one is the load-bearing figure:
       // a flatten closes the whole basket, so realised-at-exit IS the total
       // the EA saw, with no bid/ask model and no stale-mark exposure.
       // A size-scaled threshold (net >= k * $/pt, or k * open_positions) is
       // refuted outright: 0/100 cycles fire at the decision and 97/100 fire
       // prematurely.
       //
       // The exit VALUES scatter widely (only 29/99 inside [25,35], tails to
       // +632 and -108) and that scatter is NOT a missing rule.  The basket
       // carries 20-170 $/pt of gross exposure, so the decision variable
       // moves in jumps of $3-30 per tick and cannot land on 30.  Dividing
       // each overshoot by its own gross sensitivity gives the price move
       // needed to explain it: median 0.83 pt, and 46 of 47 inside the
       // 6.79 pt dispersion measured inside the flatten sweeps themselves.
       // Undershoots need 0.91 pt.  Same magnitude, opposite sign, one
       // mechanism -- price moving faster than a basket can be valued.  A
       // hold rule would give a one-sided right tail; a second exit rule a
       // one-sided left tail.  The symmetry is what rules both out.
       //
       // An earlier note here claimed 5-13 cycles held above $30 without
       // closing.  RETRACTED.  That came from a mark-walk whose error, at the
       // Target's own flatten instant where the true value is known to be 30,
       // is median 25.23 with p10 -35.59 / p90 +47.70 -- a p90 of $102.30 per
       // reading, i.e. 3.4x the threshold it was being used to test.  Every
       // "gated" cycle resolves as ordinary tick noise (194 -> 1.20 pt,
       // 187 -> 1.62, 250 -> 2.41, 253 -> 4.44, 252 -> 6.41).
       //
       // Do not reintroduce a distance, drawdown or breakeven exit without
       // first re-running q3o/q3p and showing a median lead near zero.  And
       // do not re-open the threshold question with a mark-based script: use
       // tools/forensics/basket_resolution.py, which is mark-free, and check
       // any new estimator against value@t0 before believing it.
       // ------------------------------------------------------------------
      }

   int PendingDealIndex(const ulong deal_ticket) const
     {
      for(int index=0;index<m_pending_deal_count;index++)
         if(m_pending_deal_tickets[index]==deal_ticket)
            return index;
      return -1;
     }

   void RemovePendingDealAt(const int remove_index)
     {
      if(remove_index<0 || remove_index>=m_pending_deal_count)
         return;
      for(int index=remove_index;index<m_pending_deal_count-1;index++)
         m_pending_deal_tickets[index]=m_pending_deal_tickets[index+1];
      m_pending_deal_count--;
      m_pending_deal_tickets[m_pending_deal_count]=0;
     }

   void QueuePendingDeal(const ulong deal_ticket)
     {
      if(deal_ticket==0 ||
         DealAlreadyProcessed(deal_ticket) ||
         PendingDealIndex(deal_ticket)>=0)
         return;
      if(m_pending_deal_count>=STR_PENDING_DEAL_CAPACITY)
        {
         PrintFormat(
            "[STR] Deal-history retry queue is full; ticket=%I64u.",
            deal_ticket
         );
         return;
        }
      m_pending_deal_tickets[m_pending_deal_count]=deal_ticket;
      m_pending_deal_count++;
      PrintFormat(
         "[STR] Deferred deal-history processing ticket=%I64u.",
         deal_ticket
      );
     }

   void QueueMissingHistoryDeals(void)
     {
      if(m_cycle_started_msc<=0 || m_cycle_id=="")
         return;
      ulong now_ms=GetTickCount64();
      if(m_last_history_reconcile_ms>0 &&
         now_ms-m_last_history_reconcile_ms<
            STR_HISTORY_RECONCILE_INTERVAL_MS)
         return;
      m_last_history_reconcile_ms=now_ms;
      long history_from_msc=m_cycle_started_msc;
      if(m_history_reconcile_seeded)
        {
         long lookback_from_msc=(
            CurrentServerMs()-STR_HISTORY_RECONCILE_LOOKBACK_MS
         );
         if(lookback_from_msc>history_from_msc)
            history_from_msc=lookback_from_msc;
        }
      if(!HistorySelect(
            (datetime)(history_from_msc/1000),
            TimeCurrent()
         ))
         return;
      m_history_reconcile_seeded=true;
      int deal_total=HistoryDealsTotal();
      for(int index=0;index<deal_total;index++)
        {
         ulong deal_ticket=HistoryDealGetTicket(index);
         if(deal_ticket==0 ||
            DealAlreadyProcessed(deal_ticket) ||
            PendingDealIndex(deal_ticket)>=0 ||
            (long)HistoryDealGetInteger(
               deal_ticket,
               DEAL_TIME_MSC
            )<m_cycle_started_msc ||
            (ulong)HistoryDealGetInteger(
               deal_ticket,
               DEAL_MAGIC
            )!=m_runtime.magic ||
            HistoryDealGetString(
               deal_ticket,
               DEAL_SYMBOL
            )!=m_runtime.symbol)
            continue;
         QueuePendingDeal(deal_ticket);
        }
     }

   bool ProcessSelectedDeal(const ulong deal_ticket)
     {
      if(DealAlreadyProcessed(deal_ticket))
         return true;
      if(!DealMetadataReady(deal_ticket))
         return false;
      if((ulong)HistoryDealGetInteger(deal_ticket,DEAL_MAGIC)!=m_runtime.magic ||
         HistoryDealGetString(deal_ticket,DEAL_SYMBOL)!=m_runtime.symbol)
         return true;
      ENUM_DEAL_ENTRY entry=
         (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal_ticket,DEAL_ENTRY);
      ulong position_id=
         (ulong)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID);
      ulong order_ticket=
         (ulong)HistoryDealGetInteger(deal_ticket,DEAL_ORDER);
      long deal_time_msc=
         (long)HistoryDealGetInteger(deal_ticket,DEAL_TIME_MSC);
      double deal_volume=HistoryDealGetDouble(deal_ticket,DEAL_VOLUME);
      double deal_price=HistoryDealGetDouble(deal_ticket,DEAL_PRICE);
      double deal_commission=
         HistoryDealGetDouble(deal_ticket,DEAL_COMMISSION);
      double deal_swap=HistoryDealGetDouble(deal_ticket,DEAL_SWAP);
      double deal_fee=HistoryDealGetDouble(deal_ticket,DEAL_FEE);
      double deal_profit=HistoryDealGetDouble(deal_ticket,DEAL_PROFIT);
      string level_comment=PositionCommentFromDeal(deal_ticket);
      if(level_comment=="")
         level_comment=HistoryDealGetString(deal_ticket,DEAL_COMMENT);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
        {
         m_has_traded=true;
         m_last_entry_fill_at=(datetime)(deal_time_msc/1000);
         WriteTelemetry("fill",level_comment,position_id,
                        deal_volume,deal_price,0.0,0.0,
                        level_comment,0,0,
                        deal_commission,deal_swap,deal_profit,
                        deal_ticket,
                        order_ticket,
                        position_id);
        }
      if(entry==DEAL_ENTRY_OUT ||
         entry==DEAL_ENTRY_OUT_BY ||
         entry==DEAL_ENTRY_INOUT)
        {
         double recalculated_realized=0.0;
         int recalculated_count=0;
         if(m_deal_ledger.TryRecalculate(
               m_cycle_started_msc,
               recalculated_realized,
               recalculated_count
            ) &&
            recalculated_count>m_cycle_exit_deal_count)
           {
            m_cycle_realized=recalculated_realized;
            m_cycle_exit_deal_count=recalculated_count;
           }
         else
           {
            m_cycle_realized=(
               m_cycle_realized+
               deal_profit+
               deal_swap+
               deal_commission+
               deal_fee
            );
            m_cycle_exit_deal_count++;
           }
         string exit_comment=HistoryDealGetString(deal_ticket,DEAL_COMMENT);
         ENUM_DEAL_REASON exit_reason=
            (ENUM_DEAL_REASON)HistoryDealGetInteger(
               deal_ticket,
               DEAL_REASON
            );
         bool is_stop=(exit_reason==DEAL_REASON_SL ||
                       StringFind(exit_comment,"[sl")==0 ||
                       StringFind(exit_comment,"sl ")==0);
         if(is_stop)
           {
            ScheduleLevelRearm(level_comment,deal_time_msc);
            LogLifecycleEvent("rearm_eligible",
                              level_comment,
                              "stop_exit");
            WriteTelemetry("stop_exit",level_comment,position_id,
                           deal_volume,deal_price,0.0,0.0,
                           level_comment,0,0,
                           deal_commission,deal_swap,deal_profit,
                           deal_ticket,
                           order_ticket,
                           position_id);
           }
         else
            WriteTelemetry("close_fill",level_comment,position_id,
                           deal_volume,deal_price,0.0,0.0,
                           level_comment,0,0,
                           deal_commission,deal_swap,deal_profit,
                           deal_ticket,
                           order_ticket,
                           position_id);
          PersistCycle();
         }
      RememberProcessedDeal(deal_ticket);
      return true;
     }

   void ProcessPendingDeals(void)
     {
      int index=0;
      while(index<m_pending_deal_count)
        {
         ulong deal_ticket=m_pending_deal_tickets[index];
         if(!HistoryDealSelect(deal_ticket) ||
            !DealMetadataReady(deal_ticket))
           {
            index++;
            continue;
           }
         if(ProcessSelectedDeal(deal_ticket))
            RemovePendingDealAt(index);
         else
            index++;
        }
     }

   void OnTimer(void)
     {
      QueueMissingHistoryDeals();
      ProcessPendingDeals();
      PollShadowCommand();
      switch(m_state)
        {
          case CYCLE_IDLE:
             if(AlignmentHoldActive())
               {
                UpdateAlignmentHoldTelemetry(true);
                break;
               }
             UpdateAlignmentHoldTelemetry(false);
             if(m_pending_deal_count>0)
                break;
            if(m_runtime.runtime_mode==STR_RUNTIME_NORMAL && StartCycle())
               DeployOne();
            break;
         case CYCLE_DEPLOYING:
            DeployOne();
            CheckCycleTargets();
            break;
          case CYCLE_RUNNING:
             ReconcileLevels();
             if(m_profile.stop_updates_on_timer)
                UpdatePositionStops();
             ProcessTrendRescue();
             if(m_trend_rescue_side==0)
                RearmOneMissingLevel();
             CheckCycleTargets();
             break;
         case CYCLE_CLOSING:
            CloseOnePosition();
            break;
         case CYCLE_CANCELING:
            CancelOneOrder();
             break;
          case CYCLE_RESTARTING:
             if(OwnedOrderCount()>0)
               {
                TryCancelOneOwnedOrder();
                break;
               }
              if(OwnedPositionCount()>0)
                {
                 // Paced, exactly like CYCLE_CLOSING.  Reaching CYCLE_RESTARTING
                 // with positions still open means a close request was rejected;
                 // draining them at the OnTimer period turned that rejection into
                 // a burst of market closes milliseconds apart.
                 if(CloseIntervalElapsed())
                    TryCloseOneOwnedPosition();
                 break;
                }
              if(AlignmentHoldActive())
                {
                 UpdateAlignmentHoldTelemetry(true);
                 break;
                }
              UpdateAlignmentHoldTelemetry(false);
              if(TimeCurrent()-m_restart_started_at>=
                 (m_profile.restart_delay_ms+999)/1000)
               {
               m_state=CYCLE_IDLE;
               LogLifecycleEvent("cycle_restart","","new_cycle");
               if(m_runtime.runtime_mode==STR_RUNTIME_SHADOW)
                  WriteShadowAck("READY",m_shadow_last_command_seq,"");
               ClearPersistence();
              }
            break;
         case CYCLE_HALTED:
            break;
        }
     }

   void OnTradeTransaction(const MqlTradeTransaction &transaction,
                           const MqlTradeRequest &request,
                           const MqlTradeResult &result)
     {
      if(transaction.type==TRADE_TRANSACTION_REQUEST &&
         request.magic==m_runtime.magic &&
         (request.symbol=="" || request.symbol==m_runtime.symbol))
         LogTradeRequest(request,result);
      if(transaction.type==TRADE_TRANSACTION_DEAL_ADD && transaction.deal>0)
        {
         if(!HistoryDealSelect(transaction.deal) ||
            !DealMetadataReady(transaction.deal))
            QueuePendingDeal(transaction.deal);
         else
           {
            int pending_index=PendingDealIndex(transaction.deal);
            if(pending_index>=0)
               RemovePendingDealAt(pending_index);
            ProcessSelectedDeal(transaction.deal);
           }
        }
      if(m_state==CYCLE_RUNNING || m_state==CYCLE_DEPLOYING)
         ReconcileLevels(false);
     }

   ENUM_CYCLE_STATE State(void) const { return m_state; }
   double Anchor(void) const { return m_anchor; }
   double Step(void) const { return m_step; }
  };

#endif
