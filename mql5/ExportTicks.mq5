//+------------------------------------------------------------------+
//| ExportTicks.mq5                                                  |
//| Phase 0 of the parity plan: export broker tick history for the  |
//| final-regime window (Jul 14-30) so the Python replay simulator   |
//| (tools/parity_sim) can replay the exact price path the Target EA |
//| traded on.                                                       |
//|                                                                  |
//| Usage: attach as a script to an XAUUSD chart on                  |
//| D:\MT5ReplicaObserverTerminal (AchieverGlobalMarkets feed).      |
//| Output: MQL5\Files\ticks-xauusd-jul14-30.csv (chunked writes).   |
//| Then gzip and copy into the repo as                              |
//| data/ticks-xauusd-jul14-30.csv.gz                                |
//+------------------------------------------------------------------+
#property copyright "StraddleReplica parity toolkit"
#property version   "1.00"
#property script_show_inputs

input string   InpSymbol       = "XAUUSD";
input datetime InpFrom         = D'2026.07.14 00:00:00';
input datetime InpTo           = D'2026.07.30 23:59:59';
input string   InpFileName     = "ticks-xauusd-jul14-30.csv";
input int      InpChunkSeconds = 3600; // request window per CopyTicksRange call

//+------------------------------------------------------------------+
void OnStart()
  {
   int handle=FileOpen(InpFileName,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(handle==INVALID_HANDLE)
     {
      PrintFormat("[ExportTicks] FileOpen failed: %d",GetLastError());
      return;
     }
   FileWrite(handle,"time_msc","bid","ask","last","flags");

   long total=0;
   datetime chunk_start=InpFrom;
   while(chunk_start<InpTo && !IsStopped())
     {
      datetime chunk_end=(datetime)MathMin((double)(chunk_start+InpChunkSeconds),(double)InpTo);
      MqlTick ticks[];
      // COPY_TICKS_ALL preserves both quote and trade ticks; times in ms.
      int copied=CopyTicksRange(InpSymbol,ticks,COPY_TICKS_ALL,
                                (long)chunk_start*1000,(long)chunk_end*1000);
      if(copied<0)
        {
         PrintFormat("[ExportTicks] CopyTicksRange failed at %s err=%d (history may be truncated here)",
                     TimeToString(chunk_start),GetLastError());
         // Mark the gap so the fidelity checker can flag affected cycles.
         FileWrite(handle,(long)chunk_start*1000,"GAP","GAP","GAP",0);
        }
      else
        {
         for(int i=0;i<copied;i++)
           {
            FileWrite(handle,ticks[i].time_msc,
                      DoubleToString(ticks[i].bid,_Digits),
                      DoubleToString(ticks[i].ask,_Digits),
                      DoubleToString(ticks[i].last,_Digits),
                      (long)ticks[i].flags);
           }
         total+=copied;
        }
      chunk_start=chunk_end;
      if(total>0 && (total%1000000)<10000)
         PrintFormat("[ExportTicks] progress: %s exported=%I64d",TimeToString(chunk_start),total);
     }
   FileClose(handle);
   PrintFormat("[ExportTicks] DONE. Exported %I64d ticks to MQL5\\Files\\%s",total,InpFileName);
   PrintFormat("[ExportTicks] Next: gzip the file and commit as data/ticks-xauusd-jul14-30.csv.gz");
  }
//+------------------------------------------------------------------+
