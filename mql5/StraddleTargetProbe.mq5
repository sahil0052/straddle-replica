//+------------------------------------------------------------------+
//|                                      StraddleTargetProbe.mq5      |
//| Passive same-terminal request/result and execution probe          |
//+------------------------------------------------------------------+
#property copyright "StraddleReplica target probe"
#property version   "1.00"
#property strict
#property description "Passive same-terminal target transaction and tick probe."

input ulong ExpectedLogin = 901018;
input string ExpectedServer = "AchieverGlobalMarkets-Server";
input string MonitoredSymbol = "XAUUSD";
input int TimerIntervalMs = 50;
input int HeartbeatIntervalMs = 1000;
input string OutputPrefix = "StraddleTargetProbe";

#define TRANSACTION_QUEUE_CAPACITY 8192
#define TRANSACTION_FLUSH_LIMIT 2048
#define PROBE_BUILD_ID "latest30-live-twin-v1"

string g_transaction_queue[];
int g_queue_head = 0;
int g_queue_tail = 0;
int g_queue_count = 0;
ulong g_dropped_transactions = 0;
ulong g_transaction_sequence = 0;
ulong g_tick_sequence = 0;
ulong g_heartbeat_sequence = 0;
ulong g_last_heartbeat_ms = 0;
string g_session_dir = "";
string g_hour_key = "";
int g_transaction_handle = INVALID_HANDLE;
int g_tick_handle = INVALID_HANDLE;
int g_heartbeat_handle = INVALID_HANDLE;

string CsvText(string value)
  {
   StringReplace(value,"\"","\"\"");
   return "\""+value+"\"";
  }

string ULongText(const ulong value)
  {
   return StringFormat("%I64u",value);
  }

string LongText(const long value)
  {
   return StringFormat("%I64d",value);
  }

string IntText(const int value)
  {
   return IntegerToString(value);
  }

string NumberText(const double value)
  {
   return DoubleToString(value,10);
  }

string TimeText(const datetime value)
  {
   if(value<=0)
      return "";
   return TimeToString(value,TIME_DATE|TIME_MINUTES|TIME_SECONDS);
  }

string IsoUtcNow()
  {
   MqlDateTime value={};
   TimeToStruct(TimeGMT(),value);
   return StringFormat(
      "%04d-%02d-%02dT%02d:%02d:%02dZ",
      value.year,value.mon,value.day,value.hour,value.min,value.sec
   );
  }

string CurrentHourKey()
  {
   MqlDateTime value={};
   TimeToStruct(TimeGMT(),value);
   return StringFormat(
      "%04d%02d%02d-%02d",
      value.year,value.mon,value.day,value.hour
   );
  }

string NewSessionName()
  {
   MqlDateTime value={};
   TimeToStruct(TimeGMT(),value);
   return StringFormat(
      "%04d%02d%02dT%02d%02d%02dZ_%I64u_%I64u_%s",
      value.year,value.mon,value.day,value.hour,value.min,value.sec,
      GetTickCount64(),ExpectedLogin,MonitoredSymbol
   );
  }

int OpenAppendText(const string path,const string header)
  {
   int handle=FileOpen(
      path,
      FILE_READ|FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ|FILE_COMMON,
      0,
      CP_UTF8
   );
   if(handle==INVALID_HANDLE)
     {
      PrintFormat("TargetProbe: FileOpen failed path=%s error=%d",path,GetLastError());
      return INVALID_HANDLE;
     }
   ulong size=(ulong)FileSize(handle);
   FileSeek(handle,0,SEEK_END);
   if(size==0 && header!="")
      FileWriteString(handle,header+"\r\n");
   return handle;
  }

void CloseFiles()
  {
   if(g_transaction_handle!=INVALID_HANDLE)
      FileClose(g_transaction_handle);
   if(g_tick_handle!=INVALID_HANDLE)
      FileClose(g_tick_handle);
   if(g_heartbeat_handle!=INVALID_HANDLE)
      FileClose(g_heartbeat_handle);
   g_transaction_handle=INVALID_HANDLE;
   g_tick_handle=INVALID_HANDLE;
   g_heartbeat_handle=INVALID_HANDLE;
  }

bool EnsureFiles()
  {
   string hour_key=CurrentHourKey();
   if(hour_key==g_hour_key &&
      g_transaction_handle!=INVALID_HANDLE &&
      g_tick_handle!=INVALID_HANDLE &&
      g_heartbeat_handle!=INVALID_HANDLE)
      return true;

   CloseFiles();
   g_hour_key=hour_key;
   string transaction_header=
      "utc_time,server_time,local_time,capture_micros,sequence,event_kind,"
      "entity_comment,entity_magic,trans_type,trans_deal,trans_order,"
      "trans_symbol,trans_order_type,trans_order_state,trans_deal_type,"
      "trans_price,trans_price_sl,trans_price_tp,trans_volume,trans_position,"
      "request_action,request_magic,request_order,request_symbol,"
      "request_volume,request_price,request_stoplimit,request_sl,request_tp,"
      "request_deviation,request_type,request_type_filling,request_type_time,"
      "request_expiration,request_comment,request_position,request_position_by,"
      "result_retcode,result_deal,result_order,result_volume,result_price,"
      "result_bid,result_ask,result_comment,result_request_id,"
      "result_retcode_external,deal_entry,deal_reason,deal_commission,"
      "deal_swap,deal_profit";
   string tick_header=
      "utc_time,server_time,local_time,capture_micros,sequence,time_msc,"
      "bid,ask,last,volume,volume_real,flags";
   string heartbeat_header=
      "utc_time,server_time,local_time,capture_micros,sequence,connected,"
      "trade_allowed,queue_depth,dropped_transactions,transaction_sequence,"
      "tick_sequence,positions_total,orders_total";

   g_transaction_handle=OpenAppendText(
      g_session_dir+"\\transactions-"+hour_key+".csv",
      transaction_header
   );
   g_tick_handle=OpenAppendText(
      g_session_dir+"\\ticks-"+hour_key+".csv",
      tick_header
   );
   g_heartbeat_handle=OpenAppendText(
      g_session_dir+"\\heartbeat-"+hour_key+".csv",
      heartbeat_header
   );
   return(
      g_transaction_handle!=INVALID_HANDLE &&
      g_tick_handle!=INVALID_HANDLE &&
      g_heartbeat_handle!=INVALID_HANDLE
   );
  }

void WriteManifest()
  {
   int handle=FileOpen(
      g_session_dir+"\\manifest.csv",
      FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON,
      0,
      CP_UTF8
   );
   if(handle==INVALID_HANDLE)
      return;
   string payload=
      "key,value\r\n"
      "schema_version,2\r\n"
      "mode,same_terminal_passive_probe\r\n"
      "probe_build_id,"+CsvText(PROBE_BUILD_ID)+"\r\n"
      "account_login,"+ULongText((ulong)AccountInfoInteger(ACCOUNT_LOGIN))+"\r\n"
      "account_server,"+CsvText(AccountInfoString(ACCOUNT_SERVER))+"\r\n"
      "account_trade_allowed,"+IntText((int)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+"\r\n"
      "account_trade_mode,"+IntText((int)AccountInfoInteger(ACCOUNT_TRADE_MODE))+"\r\n"
      "account_margin_mode,"+IntText((int)AccountInfoInteger(ACCOUNT_MARGIN_MODE))+"\r\n"
      "account_limit_orders,"+LongText(AccountInfoInteger(ACCOUNT_LIMIT_ORDERS))+"\r\n"
      "account_leverage,"+LongText(AccountInfoInteger(ACCOUNT_LEVERAGE))+"\r\n"
      "account_currency,"+CsvText(AccountInfoString(ACCOUNT_CURRENCY))+"\r\n"
      "symbol,"+CsvText(MonitoredSymbol)+"\r\n"
      "symbol_digits,"+LongText(SymbolInfoInteger(MonitoredSymbol,SYMBOL_DIGITS))+"\r\n"
      "symbol_tick_size,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_TRADE_TICK_SIZE))+"\r\n"
      "symbol_tick_value,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_TRADE_TICK_VALUE))+"\r\n"
      "symbol_tick_value_profit,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_TRADE_TICK_VALUE_PROFIT))+"\r\n"
      "symbol_tick_value_loss,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_TRADE_TICK_VALUE_LOSS))+"\r\n"
      "symbol_contract_size,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_TRADE_CONTRACT_SIZE))+"\r\n"
      "symbol_volume_min,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_VOLUME_MIN))+"\r\n"
      "symbol_volume_max,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_VOLUME_MAX))+"\r\n"
      "symbol_volume_step,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_VOLUME_STEP))+"\r\n"
      "symbol_stops_level,"+LongText(SymbolInfoInteger(MonitoredSymbol,SYMBOL_TRADE_STOPS_LEVEL))+"\r\n"
      "symbol_freeze_level,"+LongText(SymbolInfoInteger(MonitoredSymbol,SYMBOL_TRADE_FREEZE_LEVEL))+"\r\n"
      "symbol_filling_mode,"+LongText(SymbolInfoInteger(MonitoredSymbol,SYMBOL_FILLING_MODE))+"\r\n"
      "symbol_swap_mode,"+LongText(SymbolInfoInteger(MonitoredSymbol,SYMBOL_SWAP_MODE))+"\r\n"
      "symbol_swap_long,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_SWAP_LONG))+"\r\n"
      "symbol_swap_short,"+NumberText(SymbolInfoDouble(MonitoredSymbol,SYMBOL_SWAP_SHORT))+"\r\n"
      "symbol_swap_rollover3days,"+LongText(SymbolInfoInteger(MonitoredSymbol,SYMBOL_SWAP_ROLLOVER3DAYS))+"\r\n"
      "timer_interval_ms,"+IntText(TimerIntervalMs)+"\r\n"
      "heartbeat_interval_ms,"+IntText(HeartbeatIntervalMs)+"\r\n";
   FileWriteString(handle,payload);
   FileClose(handle);
  }

string PositionCommentFromDeal(const ulong deal_ticket)
  {
   if(deal_ticket==0 || !HistoryDealSelect(deal_ticket))
      return "";
   ulong position_id=(ulong)HistoryDealGetInteger(deal_ticket,DEAL_POSITION_ID);
   if(position_id>0 && HistoryOrderSelect(position_id))
     {
      string value=HistoryOrderGetString(position_id,ORDER_COMMENT);
      if(value!="")
         return value;
     }
   return HistoryDealGetString(deal_ticket,DEAL_COMMENT);
  }

string EntityComment(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request
)
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
   if(trans.order>0)
     {
      if(OrderSelect(trans.order))
         return OrderGetString(ORDER_COMMENT);
      if(HistoryOrderSelect(trans.order))
         return HistoryOrderGetString(trans.order,ORDER_COMMENT);
     }
   if(trans.deal>0)
      return PositionCommentFromDeal(trans.deal);
   if(request.comment!="")
      return request.comment;
   return "";
  }

ulong EntityMagic(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request
)
  {
   if(request.magic>0)
      return request.magic;
   if(trans.order>0)
     {
      if(OrderSelect(trans.order))
         return (ulong)OrderGetInteger(ORDER_MAGIC);
      if(HistoryOrderSelect(trans.order))
         return (ulong)HistoryOrderGetInteger(trans.order,ORDER_MAGIC);
     }
   if(trans.deal>0 && HistoryDealSelect(trans.deal))
      return (ulong)HistoryDealGetInteger(trans.deal,DEAL_MAGIC);
   return 0;
  }

string CanonicalKind(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request
)
  {
   if(trans.type==TRADE_TRANSACTION_REQUEST)
     {
      if(request.action==TRADE_ACTION_PENDING)
         return "pending_request";
      if(request.action==TRADE_ACTION_SLTP)
         return "stop_request";
      if(request.action==TRADE_ACTION_REMOVE)
         return "cancel_request";
      if(request.action==TRADE_ACTION_DEAL)
         return (request.position>0 ? "close_request" : "deal_request");
      return "trade_request";
     }
   if(trans.type==TRADE_TRANSACTION_ORDER_ADD)
      return "order_add";
   if(trans.type==TRADE_TRANSACTION_ORDER_DELETE)
      return "order_delete";
   if(trans.type==TRADE_TRANSACTION_POSITION)
      return "position_change";
   if(trans.type==TRADE_TRANSACTION_DEAL_ADD && trans.deal>0 &&
      HistoryDealSelect(trans.deal))
     {
      ENUM_DEAL_ENTRY entry=(ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
      ENUM_DEAL_REASON reason=(ENUM_DEAL_REASON)HistoryDealGetInteger(trans.deal,DEAL_REASON);
      if(entry==DEAL_ENTRY_IN || entry==DEAL_ENTRY_INOUT)
         return "fill";
      if(reason==DEAL_REASON_SL)
         return "stop_exit";
      if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY)
         return "close_fill";
     }
   return "transaction";
  }

string SerializeTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
  {
   g_transaction_sequence++;
   string comment=EntityComment(trans,request);
   ulong magic=EntityMagic(trans,request);
   long deal_entry=-1;
   long deal_reason=-1;
   double commission=0.0;
   double swap=0.0;
   double profit=0.0;
   if(trans.deal>0 && HistoryDealSelect(trans.deal))
     {
      deal_entry=HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
      deal_reason=HistoryDealGetInteger(trans.deal,DEAL_REASON);
      commission=HistoryDealGetDouble(trans.deal,DEAL_COMMISSION);
      swap=HistoryDealGetDouble(trans.deal,DEAL_SWAP);
      profit=HistoryDealGetDouble(trans.deal,DEAL_PROFIT);
     }
   return
      CsvText(IsoUtcNow())+","+
      CsvText(TimeText(TimeTradeServer()))+","+
      CsvText(TimeText(TimeLocal()))+","+
      ULongText(GetMicrosecondCount())+","+
      ULongText(g_transaction_sequence)+","+
      CsvText(CanonicalKind(trans,request))+","+
      CsvText(comment)+","+
      ULongText(magic)+","+
      IntText((int)trans.type)+","+
      ULongText(trans.deal)+","+
      ULongText(trans.order)+","+
      CsvText(trans.symbol)+","+
      IntText((int)trans.order_type)+","+
      IntText((int)trans.order_state)+","+
      IntText((int)trans.deal_type)+","+
      NumberText(trans.price)+","+
      NumberText(trans.price_sl)+","+
      NumberText(trans.price_tp)+","+
      NumberText(trans.volume)+","+
      ULongText(trans.position)+","+
      IntText((int)request.action)+","+
      ULongText(request.magic)+","+
      ULongText(request.order)+","+
      CsvText(request.symbol)+","+
      NumberText(request.volume)+","+
      NumberText(request.price)+","+
      NumberText(request.stoplimit)+","+
      NumberText(request.sl)+","+
      NumberText(request.tp)+","+
      ULongText(request.deviation)+","+
      IntText((int)request.type)+","+
      IntText((int)request.type_filling)+","+
      IntText((int)request.type_time)+","+
      CsvText(TimeText(request.expiration))+","+
      CsvText(request.comment)+","+
      ULongText(request.position)+","+
      ULongText(request.position_by)+","+
      ULongText((ulong)result.retcode)+","+
      ULongText(result.deal)+","+
      ULongText(result.order)+","+
      NumberText(result.volume)+","+
      NumberText(result.price)+","+
      NumberText(result.bid)+","+
      NumberText(result.ask)+","+
      CsvText(result.comment)+","+
      ULongText((ulong)result.request_id)+","+
      IntText(result.retcode_external)+","+
      LongText(deal_entry)+","+
      LongText(deal_reason)+","+
      NumberText(commission)+","+
      NumberText(swap)+","+
      NumberText(profit);
  }

void EnqueueTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
  {
   if(g_queue_count>=TRANSACTION_QUEUE_CAPACITY)
     {
      g_dropped_transactions++;
      return;
     }
   g_transaction_queue[g_queue_tail]=SerializeTransaction(trans,request,result);
   g_queue_tail=(g_queue_tail+1)%TRANSACTION_QUEUE_CAPACITY;
   g_queue_count++;
  }

void FlushTransactions()
  {
   if(g_transaction_handle==INVALID_HANDLE)
      return;
   int written=0;
   while(g_queue_count>0 && written<TRANSACTION_FLUSH_LIMIT)
     {
      FileWriteString(g_transaction_handle,g_transaction_queue[g_queue_head]+"\r\n");
      g_transaction_queue[g_queue_head]="";
      g_queue_head=(g_queue_head+1)%TRANSACTION_QUEUE_CAPACITY;
      g_queue_count--;
      written++;
     }
   if(written>0)
      FileFlush(g_transaction_handle);
  }

void CaptureTick()
  {
   if(g_tick_handle==INVALID_HANDLE)
      return;
   MqlTick tick={};
   if(!SymbolInfoTick(MonitoredSymbol,tick))
      return;
   g_tick_sequence++;
   string row=
      CsvText(IsoUtcNow())+","+
      CsvText(TimeText(TimeTradeServer()))+","+
      CsvText(TimeText(TimeLocal()))+","+
      ULongText(GetMicrosecondCount())+","+
      ULongText(g_tick_sequence)+","+
      LongText(tick.time_msc)+","+
      NumberText(tick.bid)+","+
      NumberText(tick.ask)+","+
      NumberText(tick.last)+","+
      ULongText(tick.volume)+","+
      NumberText(tick.volume_real)+","+
      ULongText((ulong)tick.flags);
   FileWriteString(g_tick_handle,row+"\r\n");
  }

void WriteHeartbeat()
  {
   if(g_heartbeat_handle==INVALID_HANDLE)
      return;
   g_heartbeat_sequence++;
   string row=
      CsvText(IsoUtcNow())+","+
      CsvText(TimeText(TimeTradeServer()))+","+
      CsvText(TimeText(TimeLocal()))+","+
      ULongText(GetMicrosecondCount())+","+
      ULongText(g_heartbeat_sequence)+","+
      IntText((int)TerminalInfoInteger(TERMINAL_CONNECTED))+","+
      IntText((int)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))+","+
      IntText(g_queue_count)+","+
      ULongText(g_dropped_transactions)+","+
      ULongText(g_transaction_sequence)+","+
      ULongText(g_tick_sequence)+","+
      IntText(PositionsTotal())+","+
      IntText(OrdersTotal());
   FileWriteString(g_heartbeat_handle,row+"\r\n");
   FileFlush(g_heartbeat_handle);
  }

bool ValidateEnvironment()
  {
   if((ulong)AccountInfoInteger(ACCOUNT_LOGIN)!=ExpectedLogin)
     {
      PrintFormat(
         "TargetProbe refused: login=%I64u expected=%I64u",
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),ExpectedLogin
      );
      return false;
     }
   if(AccountInfoString(ACCOUNT_SERVER)!=ExpectedServer)
     {
      PrintFormat(
         "TargetProbe refused: server=%s expected=%s",
         AccountInfoString(ACCOUNT_SERVER),ExpectedServer
      );
      return false;
     }
   if(_Symbol!=MonitoredSymbol)
     {
      PrintFormat("TargetProbe refused: attach to %s",MonitoredSymbol);
      return false;
     }
   if(TimerIntervalMs<20 || HeartbeatIntervalMs<TimerIntervalMs)
     {
      Print("TargetProbe refused: invalid timer intervals");
      return false;
     }
   return true;
  }

int OnInit()
  {
   if(!ValidateEnvironment())
      return INIT_FAILED;
   ArrayResize(g_transaction_queue,TRANSACTION_QUEUE_CAPACITY);
   g_session_dir=OutputPrefix+"\\"+NewSessionName();
   FolderCreate(OutputPrefix,FILE_COMMON);
   FolderCreate(g_session_dir,FILE_COMMON);
   WriteManifest();
   if(!EnsureFiles())
      return INIT_FAILED;
   WriteHeartbeat();
   g_last_heartbeat_ms=GetTickCount64();
   if(!EventSetMillisecondTimer(TimerIntervalMs))
      return INIT_FAILED;
   PrintFormat("TargetProbe started: Common\\Files\\%s",g_session_dir);
   return INIT_SUCCEEDED;
  }

void OnTick()
  {
   if(EnsureFiles())
      CaptureTick();
  }

void OnTradeTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
  {
   EnqueueTransaction(trans,request,result);
  }

void OnTimer()
  {
   if((ulong)AccountInfoInteger(ACCOUNT_LOGIN)!=ExpectedLogin ||
      AccountInfoString(ACCOUNT_SERVER)!=ExpectedServer)
     {
      Print("TargetProbe stopped: account boundary changed");
      ExpertRemove();
      return;
     }
   if(!EnsureFiles())
      return;
   FlushTransactions();
   ulong now_ms=GetTickCount64();
   if(now_ms-g_last_heartbeat_ms>=(ulong)HeartbeatIntervalMs)
     {
      WriteHeartbeat();
      g_last_heartbeat_ms=now_ms;
     }
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(EnsureFiles())
     {
      FlushTransactions();
      WriteHeartbeat();
     }
   CloseFiles();
   PrintFormat(
      "TargetProbe stopped reason=%d dropped_transactions=%I64u",
      reason,g_dropped_transactions
   );
  }
