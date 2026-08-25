# Live Straddle Observer Design

## Objective

Capture the broker-visible behavior of account `901018` continuously without
placing, changing, or closing any trade. The resulting event stream must expose
the hidden stop-selection, basket-close, cancellation, re-arm, and restart
rules needed to improve `StraddleReplica`.

## Confirmed Environment

- The local portable terminal is `C:\Program Files\MetaTrader 5`.
- It is connected to `AchieverGlobalMarkets-Server` in investor/read-only mode.
- MT5 reports `trade_allowed=false`, four positions, and 54 working orders.
- The original trading EA is running elsewhere. Monitoring must not alter its
  terminal, charts, files, or account state.
- The workspace is not a Git repository, so design and implementation records
  can be saved locally but cannot be committed.

## Safety Boundary

Monitoring uses two independent read-only layers:

1. `StraddleObserver.mq5` receives account transaction events, records ticks,
   and snapshots orders and positions. It contains no trading includes or
   trading API calls and refuses to initialize unless the account is the
   expected investor/read-only account.
2. A Python collector uses only read APIs from the installed MetaTrader5
   package. It also refuses to run if MT5 reports that trading is allowed.

Automated tests scan both implementations for forbidden trading operations.
Installation scripts copy files and start collectors only; they do not enable
Algo Trading, submit requests, modify charts belonging to the original EA, or
store account/VPS passwords.

## Data Capture

Each session writes append-only, hourly-rotated data:

- `manifest.json`: terminal build, server, masked account, symbol properties,
  collector versions, start times, and safety checks.
- `ticks-*.csv`: MT5 millisecond time, local UTC capture time, Bid, Ask, Last,
  volume, real volume, and tick flags.
- `transactions-*.csv`: every `OnTradeTransaction` structure plus all request
  and result fields exposed to the observer.
- `snapshots-*.jsonl`: complete order and position state after transactions,
  whenever state changes, and periodic checkpoints.
- `history-orders-*.jsonl` and `history-deals-*.jsonl`: newly visible completed
  orders and deals.
- `heartbeat.json`: atomic status, latest tick/event, queue depth, dropped-event
  count, reconnect count, and file sizes.

The MQL5 transaction handler only enqueues data. A millisecond timer performs
file writes so the 1,024-item MT5 transaction queue is not blocked. Tick
collection uses overlapping `CopyTicks` reads and deterministic deduplication,
because `OnTick` is a notification and is not guaranteed to represent every
individual tick.

## Runtime and Recovery

- The collector runs until explicitly stopped; this avoids losing most of the
  requested 48-hour window to the weekend beginning August 1, 2026.
- Useful completion is at least 48 market-open hours and ten complete grid
  deploy/close/restart cycles.
- A Windows scheduled task starts the collector at boot and logon, restarts it
  after failure, and writes a PID/status record.
- The collector reconnects to MT5 after network or terminal interruptions and
  resumes from the last stored tick/history identifiers.
- Files remain valid after abrupt shutdown because records are append-only and
  flushed regularly.

## VPS Deployment

The VPS receives a separate portable MT5 monitoring terminal logged in with
investor credentials. This avoids touching the terminal that runs the original
EA. The observer and Python collector run in that isolated terminal, and a
scheduled task keeps the collector alive when the laptop is closed.

No password is written into the project, deployment package, logs, command
files, or scheduled-task arguments. Interactive login is the only credential
entry point. If unattended MT5 relaunch is needed, MT5's own encrypted account
store is used after the initial interactive login.

## Success Criteria

- Observer and collector compile/start with safety checks passing.
- Static audit finds no order-send, order-modify, order-delete, position-close,
  or trade-library usage.
- The first live capture contains ticks, a four-position/54-order snapshot, and
  a healthy heartbeat.
- A synthetic transaction burst proves that queueing and rotation lose no
  records.
- Local and VPS monitoring can be stopped without affecting orders or
  positions.
- After sufficient market activity, the captured stream can identify every SL
  transition and reconstruct complete cycle ordering.

