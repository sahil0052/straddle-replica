#property copyright "StraddleReplica forensic observer"
#property version   "1.00"
#property strict
#property description "Read-only account transaction, tick, and state observer."

input ulong ExpectedLogin = 901018;
input string ExpectedServer = "AchieverGlobalMarkets-Server";
input string MonitoredSymbol = "XAUUSD";
input int TimerIntervalMs = 50;
input int SnapshotIntervalMs = 50;
input int FullCheckpointIntervalMs = 30000;
input int HeartbeatIntervalMs = 1000;
input string OutputPrefix = "StraddleObserver";

#define TRANSACTION_QUEUE_CAPACITY 4096
#define TRANSACTION_FLUSH_LIMIT 2048

string g_transaction_queue[];
int g_queue_head = 0;
int g_queue_tail = 0;
int g_queue_count = 0;
ulong g_dropped_transactions = 0;

string g_session_dir = "";
string g_hour_key = "";
int g_transaction_handle = INVALID_HANDLE;
int g_tick_handle = INVALID_HANDLE;
int g_snapshot_handle = INVALID_HANDLE;
int g_heartbeat_handle = INVALID_HANDLE;

ulong g_transaction_sequence = 0;
ulong g_tick_sequence = 0;
ulong g_snapshot_sequence = 0;
ulong g_heartbeat_sequence = 0;
long g_last_tick_msc = 0;
string g_last_millisecond_tick_ids[];
string g_last_state_fingerprint = "";
ulong g_last_snapshot_ms = 0;
ulong g_last_checkpoint_ms = 0;
ulong g_last_heartbeat_ms = 0;
bool g_force_snapshot = false;

string CsvText(string value)
{
   StringReplace(value, "\"", "\"\"");
   return "\"" + value + "\"";
}

string ULongText(const ulong value)
{
   return StringFormat("%I64u", value);
}

string LongText(const long value)
{
   return StringFormat("%I64d", value);
}

string IntText(const int value)
{
   return IntegerToString(value);
}

string BoolText(const bool value)
{
   return value ? "1" : "0";
}

string NumberText(const double value)
{
   return DoubleToString(value, 10);
}

string TimeText(const datetime value)
{
   if(value <= 0)
      return "";
   return TimeToString(value, TIME_DATE | TIME_MINUTES | TIME_SECONDS);
}

string CurrentHourKey()
{
   MqlDateTime value;
   TimeToStruct(TimeGMT(), value);
   return StringFormat(
      "%04d%02d%02d-%02d",
      value.year,
      value.mon,
      value.day,
      value.hour
   );
}

string NewSessionName()
{
   MqlDateTime value;
   TimeToStruct(TimeGMT(), value);
   return StringFormat(
      "%04d%02d%02dT%02d%02d%02dZ_%I64u_%s",
      value.year,
      value.mon,
      value.day,
      value.hour,
      value.min,
      value.sec,
      ExpectedLogin,
      MonitoredSymbol
   );
}

int OpenAppendText(const string relative_path, const string header)
{
   int handle = FileOpen(
      relative_path,
      FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_SHARE_READ | FILE_COMMON,
      0,
      CP_UTF8
   );
   if(handle == INVALID_HANDLE)
   {
      PrintFormat(
         "StraddleObserver: FileOpen failed for %s, error=%d",
         relative_path,
         GetLastError()
      );
      return INVALID_HANDLE;
   }

   ulong size = (ulong)FileSize(handle);
   FileSeek(handle, 0, SEEK_END);
   if(size == 0 && header != "")
   {
      FileWriteString(handle, header + "\r\n");
      FileFlush(handle);
   }
   return handle;
}

void CloseHourlyFiles()
{
   if(g_transaction_handle != INVALID_HANDLE)
   {
      FileClose(g_transaction_handle);
      g_transaction_handle = INVALID_HANDLE;
   }
   if(g_tick_handle != INVALID_HANDLE)
   {
      FileClose(g_tick_handle);
      g_tick_handle = INVALID_HANDLE;
   }
   if(g_snapshot_handle != INVALID_HANDLE)
   {
      FileClose(g_snapshot_handle);
      g_snapshot_handle = INVALID_HANDLE;
   }
   if(g_heartbeat_handle != INVALID_HANDLE)
   {
      FileClose(g_heartbeat_handle);
      g_heartbeat_handle = INVALID_HANDLE;
   }
}

bool EnsureHourlyFiles()
{
   string hour_key = CurrentHourKey();
   if(hour_key == g_hour_key &&
      g_transaction_handle != INVALID_HANDLE &&
      g_tick_handle != INVALID_HANDLE &&
      g_snapshot_handle != INVALID_HANDLE &&
      g_heartbeat_handle != INVALID_HANDLE)
   {
      return true;
   }

   CloseHourlyFiles();
   g_hour_key = hour_key;

   string transaction_header =
      "server_time,local_time,capture_micros,sequence,"
      "trans_type,trans_deal,trans_order,trans_symbol,trans_order_type,"
      "trans_order_state,trans_deal_type,trans_time_type,"
      "trans_time_expiration,trans_price,trans_price_trigger,trans_price_sl,"
      "trans_price_tp,trans_volume,trans_position,trans_position_by,"
      "request_action,request_magic,request_order,request_symbol,"
      "request_volume,request_price,request_stoplimit,request_sl,request_tp,"
      "request_deviation,request_type,request_type_filling,request_type_time,"
      "request_expiration,request_comment,request_position,request_position_by,"
      "result_retcode,result_deal,result_order,result_volume,result_price,"
      "result_bid,result_ask,result_comment,result_request_id,"
      "result_retcode_external";
   string tick_header =
      "server_time,local_time,capture_micros,sequence,time,time_msc,bid,ask,"
      "last,volume,volume_real,flags";
   string snapshot_header =
      "server_time,local_time,capture_micros,snapshot_sequence,reason,"
      "record_type,ticket,time_msc,time_update_msc,type,state,magic,"
      "identifier,position_id,position_by_id,reason_code,volume_initial,"
      "volume_current,price_open,sl,tp,price_current,price_stoplimit,swap,"
      "profit,symbol,comment";
   string heartbeat_header =
      "server_time,local_time,capture_micros,sequence,connected,trade_allowed,"
      "positions_total,orders_total,queue_depth,dropped_transactions,"
      "last_tick_msc,transaction_sequence,tick_sequence,snapshot_sequence";

   g_transaction_handle = OpenAppendText(
      g_session_dir + "\\transactions-" + hour_key + ".csv",
      transaction_header
   );
   g_tick_handle = OpenAppendText(
      g_session_dir + "\\ticks-" + hour_key + ".csv",
      tick_header
   );
   g_snapshot_handle = OpenAppendText(
      g_session_dir + "\\snapshots-" + hour_key + ".csv",
      snapshot_header
   );
   g_heartbeat_handle = OpenAppendText(
      g_session_dir + "\\heartbeat-" + hour_key + ".csv",
      heartbeat_header
   );

   return (
      g_transaction_handle != INVALID_HANDLE &&
      g_tick_handle != INVALID_HANDLE &&
      g_snapshot_handle != INVALID_HANDLE &&
      g_heartbeat_handle != INVALID_HANDLE
   );
}

void WriteManifest()
{
   string path = g_session_dir + "\\manifest.csv";
   int handle = FileOpen(
      path,
      FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON,
      0,
      CP_UTF8
   );
   if(handle == INVALID_HANDLE)
   {
      PrintFormat(
         "StraddleObserver: manifest open failed, error=%d",
         GetLastError()
      );
      return;
   }

   FileWriteString(
      handle,
      "key,value\r\n"
      "schema_version,1\r\n"
      "mode,read_only_observer\r\n"
      "account_login," + ULongText((ulong)AccountInfoInteger(ACCOUNT_LOGIN)) + "\r\n"
      "account_server," + CsvText(AccountInfoString(ACCOUNT_SERVER)) + "\r\n"
      "account_trade_allowed," + BoolText(
         (bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)
      ) + "\r\n"
      "account_trade_expert," + BoolText(
         (bool)AccountInfoInteger(ACCOUNT_TRADE_EXPERT)
      ) + "\r\n"
      "account_margin_mode," + LongText(
         AccountInfoInteger(ACCOUNT_MARGIN_MODE)
      ) + "\r\n"
      "terminal_build," + LongText(
         TerminalInfoInteger(TERMINAL_BUILD)
      ) + "\r\n"
      "terminal_connected," + BoolText(
         (bool)TerminalInfoInteger(TERMINAL_CONNECTED)
      ) + "\r\n"
      "terminal_company," + CsvText(TerminalInfoString(TERMINAL_COMPANY)) + "\r\n"
      "terminal_name," + CsvText(TerminalInfoString(TERMINAL_NAME)) + "\r\n"
      "symbol," + CsvText(MonitoredSymbol) + "\r\n"
      "symbol_digits," + LongText(
         SymbolInfoInteger(MonitoredSymbol, SYMBOL_DIGITS)
      ) + "\r\n"
      "symbol_tick_size," + NumberText(
         SymbolInfoDouble(MonitoredSymbol, SYMBOL_TRADE_TICK_SIZE)
      ) + "\r\n"
      "symbol_volume_min," + NumberText(
         SymbolInfoDouble(MonitoredSymbol, SYMBOL_VOLUME_MIN)
      ) + "\r\n"
      "symbol_volume_step," + NumberText(
         SymbolInfoDouble(MonitoredSymbol, SYMBOL_VOLUME_STEP)
      ) + "\r\n"
      "timer_interval_ms," + IntText(TimerIntervalMs) + "\r\n"
      "snapshot_interval_ms," + IntText(SnapshotIntervalMs) + "\r\n"
      "full_checkpoint_interval_ms," + IntText(FullCheckpointIntervalMs) + "\r\n"
      "heartbeat_interval_ms," + IntText(HeartbeatIntervalMs) + "\r\n"
   );
   FileFlush(handle);
   FileClose(handle);
}

string SerializeTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
{
   g_transaction_sequence++;
   return
      CsvText(TimeText(TimeTradeServer())) + "," +
      CsvText(TimeText(TimeLocal())) + "," +
      ULongText(GetMicrosecondCount()) + "," +
      ULongText(g_transaction_sequence) + "," +
      IntText((int)trans.type) + "," +
      ULongText(trans.deal) + "," +
      ULongText(trans.order) + "," +
      CsvText(trans.symbol) + "," +
      IntText((int)trans.order_type) + "," +
      IntText((int)trans.order_state) + "," +
      IntText((int)trans.deal_type) + "," +
      IntText((int)trans.time_type) + "," +
      CsvText(TimeText(trans.time_expiration)) + "," +
      NumberText(trans.price) + "," +
      NumberText(trans.price_trigger) + "," +
      NumberText(trans.price_sl) + "," +
      NumberText(trans.price_tp) + "," +
      NumberText(trans.volume) + "," +
      ULongText(trans.position) + "," +
      ULongText(trans.position_by) + "," +
      IntText((int)request.action) + "," +
      ULongText(request.magic) + "," +
      ULongText(request.order) + "," +
      CsvText(request.symbol) + "," +
      NumberText(request.volume) + "," +
      NumberText(request.price) + "," +
      NumberText(request.stoplimit) + "," +
      NumberText(request.sl) + "," +
      NumberText(request.tp) + "," +
      ULongText(request.deviation) + "," +
      IntText((int)request.type) + "," +
      IntText((int)request.type_filling) + "," +
      IntText((int)request.type_time) + "," +
      CsvText(TimeText(request.expiration)) + "," +
      CsvText(request.comment) + "," +
      ULongText(request.position) + "," +
      ULongText(request.position_by) + "," +
      ULongText((ulong)result.retcode) + "," +
      ULongText(result.deal) + "," +
      ULongText(result.order) + "," +
      NumberText(result.volume) + "," +
      NumberText(result.price) + "," +
      NumberText(result.bid) + "," +
      NumberText(result.ask) + "," +
      CsvText(result.comment) + "," +
      ULongText((ulong)result.request_id) + "," +
      IntText(result.retcode_external);
}

void EnqueueTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
{
   if(g_queue_count >= TRANSACTION_QUEUE_CAPACITY)
   {
      g_dropped_transactions++;
      return;
   }
   g_transaction_queue[g_queue_tail] = SerializeTransaction(
      trans,
      request,
      result
   );
   g_queue_tail = (g_queue_tail + 1) % TRANSACTION_QUEUE_CAPACITY;
   g_queue_count++;
}

void FlushTransactions()
{
   if(g_transaction_handle == INVALID_HANDLE)
      return;

   int written = 0;
   while(g_queue_count > 0 && written < TRANSACTION_FLUSH_LIMIT)
   {
      FileWriteString(
         g_transaction_handle,
         g_transaction_queue[g_queue_head] + "\r\n"
      );
      g_transaction_queue[g_queue_head] = "";
      g_queue_head = (g_queue_head + 1) % TRANSACTION_QUEUE_CAPACITY;
      g_queue_count--;
      written++;
   }
   if(written > 0)
      FileFlush(g_transaction_handle);
}

string TickIdentity(const MqlTick &tick)
{
   return
      ULongText(tick.time_msc) + "|" +
      NumberText(tick.bid) + "|" +
      NumberText(tick.ask) + "|" +
      NumberText(tick.last) + "|" +
      ULongText(tick.volume) + "|" +
      NumberText(tick.volume_real) + "|" +
      ULongText((ulong)tick.flags);
}

bool SeenLastMillisecondTick(const string identity)
{
   int total = ArraySize(g_last_millisecond_tick_ids);
   for(int i = 0; i < total; i++)
   {
      if(g_last_millisecond_tick_ids[i] == identity)
         return true;
   }
   return false;
}

void CaptureTicks()
{
   if(g_tick_handle == INVALID_HANDLE)
      return;

   ulong from_msc = (ulong)MathMax(0, g_last_tick_msc);
   if(from_msc == 0)
      from_msc = (ulong)MathMax(1, TimeTradeServer() - 10) * 1000;

   MqlTick ticks[];
   int copied = CopyTicks(
      MonitoredSymbol,
      ticks,
      COPY_TICKS_ALL,
      from_msc,
      2000
   );
   if(copied <= 0)
      return;

   int written = 0;
   for(int i = 0; i < copied; i++)
   {
      MqlTick tick = ticks[i];
      if(tick.time_msc < g_last_tick_msc)
         continue;
      if(tick.time_msc > g_last_tick_msc)
      {
         g_last_tick_msc = tick.time_msc;
         ArrayResize(g_last_millisecond_tick_ids, 0);
      }

      string identity = TickIdentity(tick);
      if(SeenLastMillisecondTick(identity))
         continue;
      int identity_count = ArraySize(g_last_millisecond_tick_ids);
      ArrayResize(g_last_millisecond_tick_ids, identity_count + 1);
      g_last_millisecond_tick_ids[identity_count] = identity;

      g_tick_sequence++;
      string row =
         CsvText(TimeText(TimeTradeServer())) + "," +
         CsvText(TimeText(TimeLocal())) + "," +
         ULongText(GetMicrosecondCount()) + "," +
         ULongText(g_tick_sequence) + "," +
         CsvText(TimeText(tick.time)) + "," +
         ULongText(tick.time_msc) + "," +
         NumberText(tick.bid) + "," +
         NumberText(tick.ask) + "," +
         NumberText(tick.last) + "," +
         ULongText(tick.volume) + "," +
         NumberText(tick.volume_real) + "," +
         ULongText((ulong)tick.flags);
      FileWriteString(g_tick_handle, row + "\r\n");
      written++;
   }
   if(written > 0)
      FileFlush(g_tick_handle);
}

void SortTickets(ulong &tickets[])
{
   int total = ArraySize(tickets);
   for(int i = 0; i < total - 1; i++)
   {
      for(int j = i + 1; j < total; j++)
      {
         if(tickets[j] < tickets[i])
         {
            ulong temporary = tickets[i];
            tickets[i] = tickets[j];
            tickets[j] = temporary;
         }
      }
   }
}

void CollectPositionTickets(ulong &tickets[])
{
   int total = PositionsTotal();
   ArrayResize(tickets, total);
   int count = 0;
   for(int i = 0; i < total; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         tickets[count] = ticket;
         count++;
      }
   }
   ArrayResize(tickets, count);
   SortTickets(tickets);
}

void CollectOrderTickets(ulong &tickets[])
{
   int total = OrdersTotal();
   ArrayResize(tickets, total);
   int count = 0;
   for(int i = 0; i < total; i++)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0)
      {
         tickets[count] = ticket;
         count++;
      }
   }
   ArrayResize(tickets, count);
   SortTickets(tickets);
}

string BuildStateFingerprint()
{
   string value = "";
   ulong position_tickets[];
   CollectPositionTickets(position_tickets);
   for(int i = 0; i < ArraySize(position_tickets); i++)
   {
      ulong ticket = position_tickets[i];
      if(!PositionSelectByTicket(ticket))
         continue;
      value +=
         "P|" + ULongText(ticket) + "|" +
         LongText(PositionGetInteger(POSITION_TIME_MSC)) + "|" +
         LongText(PositionGetInteger(POSITION_TIME_UPDATE_MSC)) + "|" +
         LongText(PositionGetInteger(POSITION_TYPE)) + "|" +
         LongText(PositionGetInteger(POSITION_MAGIC)) + "|" +
         NumberText(PositionGetDouble(POSITION_VOLUME)) + "|" +
         NumberText(PositionGetDouble(POSITION_PRICE_OPEN)) + "|" +
         NumberText(PositionGetDouble(POSITION_SL)) + "|" +
         NumberText(PositionGetDouble(POSITION_TP)) + "|" +
         PositionGetString(POSITION_SYMBOL) + "|" +
         PositionGetString(POSITION_COMMENT) + ";";
   }

   ulong order_tickets[];
   CollectOrderTickets(order_tickets);
   for(int i = 0; i < ArraySize(order_tickets); i++)
   {
      ulong ticket = order_tickets[i];
      if(!OrderSelect(ticket))
         continue;
      value +=
         "O|" + ULongText(ticket) + "|" +
         LongText(OrderGetInteger(ORDER_TIME_SETUP_MSC)) + "|" +
         LongText(OrderGetInteger(ORDER_TIME_DONE_MSC)) + "|" +
         LongText(OrderGetInteger(ORDER_TYPE)) + "|" +
         LongText(OrderGetInteger(ORDER_STATE)) + "|" +
         LongText(OrderGetInteger(ORDER_MAGIC)) + "|" +
         NumberText(OrderGetDouble(ORDER_VOLUME_INITIAL)) + "|" +
         NumberText(OrderGetDouble(ORDER_VOLUME_CURRENT)) + "|" +
         NumberText(OrderGetDouble(ORDER_PRICE_OPEN)) + "|" +
         NumberText(OrderGetDouble(ORDER_SL)) + "|" +
         NumberText(OrderGetDouble(ORDER_TP)) + "|" +
         OrderGetString(ORDER_SYMBOL) + "|" +
         OrderGetString(ORDER_COMMENT) + ";";
   }
   return value;
}

string SnapshotPrefix(const string reason, const string record_type)
{
   return
      CsvText(TimeText(TimeTradeServer())) + "," +
      CsvText(TimeText(TimeLocal())) + "," +
      ULongText(GetMicrosecondCount()) + "," +
      ULongText(g_snapshot_sequence) + "," +
      CsvText(reason) + "," +
      CsvText(record_type) + ",";
}

void WritePositionSnapshot(
   const ulong ticket,
   const string reason
)
{
   if(!PositionSelectByTicket(ticket))
      return;
   string row =
      SnapshotPrefix(reason, "position") +
      ULongText(ticket) + "," +
      LongText(PositionGetInteger(POSITION_TIME_MSC)) + "," +
      LongText(PositionGetInteger(POSITION_TIME_UPDATE_MSC)) + "," +
      LongText(PositionGetInteger(POSITION_TYPE)) + "," +
      "-1," +
      LongText(PositionGetInteger(POSITION_MAGIC)) + "," +
      LongText(PositionGetInteger(POSITION_IDENTIFIER)) + "," +
      "0,0," +
      LongText(PositionGetInteger(POSITION_REASON)) + "," +
      NumberText(PositionGetDouble(POSITION_VOLUME)) + "," +
      NumberText(PositionGetDouble(POSITION_VOLUME)) + "," +
      NumberText(PositionGetDouble(POSITION_PRICE_OPEN)) + "," +
      NumberText(PositionGetDouble(POSITION_SL)) + "," +
      NumberText(PositionGetDouble(POSITION_TP)) + "," +
      NumberText(PositionGetDouble(POSITION_PRICE_CURRENT)) + "," +
      "0," +
      NumberText(PositionGetDouble(POSITION_SWAP)) + "," +
      NumberText(PositionGetDouble(POSITION_PROFIT)) + "," +
      CsvText(PositionGetString(POSITION_SYMBOL)) + "," +
      CsvText(PositionGetString(POSITION_COMMENT));
   FileWriteString(g_snapshot_handle, row + "\r\n");
}

void WriteOrderSnapshot(
   const ulong ticket,
   const string reason
)
{
   if(!OrderSelect(ticket))
      return;
   string row =
      SnapshotPrefix(reason, "order") +
      ULongText(ticket) + "," +
      LongText(OrderGetInteger(ORDER_TIME_SETUP_MSC)) + "," +
      LongText(OrderGetInteger(ORDER_TIME_DONE_MSC)) + "," +
      LongText(OrderGetInteger(ORDER_TYPE)) + "," +
      LongText(OrderGetInteger(ORDER_STATE)) + "," +
      LongText(OrderGetInteger(ORDER_MAGIC)) + "," +
      "0," +
      LongText(OrderGetInteger(ORDER_POSITION_ID)) + "," +
      LongText(OrderGetInteger(ORDER_POSITION_BY_ID)) + "," +
      LongText(OrderGetInteger(ORDER_REASON)) + "," +
      NumberText(OrderGetDouble(ORDER_VOLUME_INITIAL)) + "," +
      NumberText(OrderGetDouble(ORDER_VOLUME_CURRENT)) + "," +
      NumberText(OrderGetDouble(ORDER_PRICE_OPEN)) + "," +
      NumberText(OrderGetDouble(ORDER_SL)) + "," +
      NumberText(OrderGetDouble(ORDER_TP)) + "," +
      NumberText(OrderGetDouble(ORDER_PRICE_CURRENT)) + "," +
      NumberText(OrderGetDouble(ORDER_PRICE_STOPLIMIT)) + "," +
      "0,0," +
      CsvText(OrderGetString(ORDER_SYMBOL)) + "," +
      CsvText(OrderGetString(ORDER_COMMENT));
   FileWriteString(g_snapshot_handle, row + "\r\n");
}

void CaptureSnapshot(const string reason, const bool force)
{
   if(g_snapshot_handle == INVALID_HANDLE)
      return;

   string fingerprint = BuildStateFingerprint();
   if(!force && fingerprint == g_last_state_fingerprint)
      return;

   g_snapshot_sequence++;
   ulong position_tickets[];
   CollectPositionTickets(position_tickets);
   for(int i = 0; i < ArraySize(position_tickets); i++)
      WritePositionSnapshot(position_tickets[i], reason);

   ulong order_tickets[];
   CollectOrderTickets(order_tickets);
   for(int i = 0; i < ArraySize(order_tickets); i++)
      WriteOrderSnapshot(order_tickets[i], reason);

   if(ArraySize(position_tickets) == 0 && ArraySize(order_tickets) == 0)
   {
      FileWriteString(
         g_snapshot_handle,
         SnapshotPrefix(reason, "empty") +
         "0,0,0,-1,-1,0,0,0,0,0,0,0,0,0,0,0,0,0,0," +
         CsvText(MonitoredSymbol) + "," + CsvText("") + "\r\n"
      );
   }
   FileFlush(g_snapshot_handle);
   g_last_state_fingerprint = fingerprint;
}

void WriteHeartbeat()
{
   if(g_heartbeat_handle == INVALID_HANDLE)
      return;
   g_heartbeat_sequence++;
   string row =
      CsvText(TimeText(TimeTradeServer())) + "," +
      CsvText(TimeText(TimeLocal())) + "," +
      ULongText(GetMicrosecondCount()) + "," +
      ULongText(g_heartbeat_sequence) + "," +
      BoolText((bool)TerminalInfoInteger(TERMINAL_CONNECTED)) + "," +
      BoolText((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED)) + "," +
      IntText(PositionsTotal()) + "," +
      IntText(OrdersTotal()) + "," +
      IntText(g_queue_count) + "," +
      ULongText(g_dropped_transactions) + "," +
      LongText(g_last_tick_msc) + "," +
      ULongText(g_transaction_sequence) + "," +
      ULongText(g_tick_sequence) + "," +
      ULongText(g_snapshot_sequence);
   FileWriteString(g_heartbeat_handle, row + "\r\n");
   FileFlush(g_heartbeat_handle);
}

bool ValidateEnvironment()
{
   if((ulong)AccountInfoInteger(ACCOUNT_LOGIN) != ExpectedLogin)
   {
      PrintFormat(
         "StraddleObserver refused: login=%I64u expected=%I64u",
         (ulong)AccountInfoInteger(ACCOUNT_LOGIN),
         ExpectedLogin
      );
      return false;
   }
   if(AccountInfoString(ACCOUNT_SERVER) != ExpectedServer)
   {
      PrintFormat(
         "StraddleObserver refused: server=%s expected=%s",
         AccountInfoString(ACCOUNT_SERVER),
         ExpectedServer
      );
      return false;
   }
   if((bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      Print("StraddleObserver refused: ACCOUNT_TRADE_ALLOWED is true");
      return false;
   }
   if(!(bool)TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      Print("StraddleObserver refused: terminal is not connected");
      return false;
   }
   if(_Symbol != MonitoredSymbol)
   {
      PrintFormat(
         "StraddleObserver refused: attach to %s, current chart=%s",
         MonitoredSymbol,
         _Symbol
      );
      return false;
   }
   if(TimerIntervalMs < 20 ||
      SnapshotIntervalMs < TimerIntervalMs ||
      FullCheckpointIntervalMs < SnapshotIntervalMs ||
      HeartbeatIntervalMs < TimerIntervalMs)
   {
      Print("StraddleObserver refused: invalid timer intervals");
      return false;
   }
   return true;
}

int OnInit()
{
   if(!ValidateEnvironment())
      return INIT_FAILED;

   ArrayResize(g_transaction_queue, TRANSACTION_QUEUE_CAPACITY);
   g_session_dir = OutputPrefix + "\\" + NewSessionName();
   FolderCreate(OutputPrefix, FILE_COMMON);
   FolderCreate(g_session_dir, FILE_COMMON);
   WriteManifest();

   if(!EnsureHourlyFiles())
      return INIT_FAILED;

   CaptureTicks();
   CaptureSnapshot("initial", true);
   WriteHeartbeat();
   ulong now_ms = GetTickCount64();
   g_last_snapshot_ms = now_ms;
   g_last_checkpoint_ms = now_ms;
   g_last_heartbeat_ms = now_ms;

   if(!EventSetMillisecondTimer(TimerIntervalMs))
   {
      PrintFormat(
         "StraddleObserver: EventSetMillisecondTimer failed, error=%d",
         GetLastError()
      );
      CloseHourlyFiles();
      return INIT_FAILED;
   }

   PrintFormat(
      "StraddleObserver started in read-only mode: Common\\Files\\%s",
      g_session_dir
   );
   return INIT_SUCCEEDED;
}

void OnTradeTransaction(
   const MqlTradeTransaction &trans,
   const MqlTradeRequest &request,
   const MqlTradeResult &result
)
{
   EnqueueTransaction(trans, request, result);
   g_force_snapshot = true;
}

void OnTimer()
{
   if((ulong)AccountInfoInteger(ACCOUNT_LOGIN) != ExpectedLogin ||
      AccountInfoString(ACCOUNT_SERVER) != ExpectedServer ||
      (bool)AccountInfoInteger(ACCOUNT_TRADE_ALLOWED))
   {
      Print("StraddleObserver stopped: account safety boundary changed");
      ExpertRemove();
      return;
   }

   if(!EnsureHourlyFiles())
      return;

   FlushTransactions();
   CaptureTicks();

   ulong now_ms = GetTickCount64();
   bool snapshot_due = (
      now_ms - g_last_snapshot_ms >= (ulong)SnapshotIntervalMs
   );
   bool checkpoint_due = (
      now_ms - g_last_checkpoint_ms >= (ulong)FullCheckpointIntervalMs
   );
   if(g_force_snapshot || snapshot_due || checkpoint_due)
   {
      CaptureSnapshot(
         checkpoint_due ? "checkpoint" : (g_force_snapshot ? "transaction" : "change"),
         g_force_snapshot || checkpoint_due
      );
      g_force_snapshot = false;
      g_last_snapshot_ms = now_ms;
      if(checkpoint_due)
         g_last_checkpoint_ms = now_ms;
   }

   if(now_ms - g_last_heartbeat_ms >= (ulong)HeartbeatIntervalMs)
   {
      WriteHeartbeat();
      g_last_heartbeat_ms = now_ms;
   }
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   if(EnsureHourlyFiles())
   {
      FlushTransactions();
      CaptureTicks();
      CaptureSnapshot("deinit_" + IntText(reason), true);
      WriteHeartbeat();
   }
   CloseHourlyFiles();
   PrintFormat(
      "StraddleObserver stopped: reason=%d dropped_transactions=%I64u",
      reason,
      g_dropped_transactions
   );
}
