# StraddleReplica real-account candidate

This package contains the real-account build of the independent `LATEST_30`
EA. It is not a trade copier: after deployment it makes grid, stop, rearm,
basket-close, and restart decisions from its own account state and broker
prices.

## Validation status

The deterministic grid geometry, order comments, sequence, spacing, lot tiers,
and current lifecycle model are evidence-based. The demo validation gate still
requires ten complete paired cycles and 48 market-open hours before the build
can be represented as validated.

The original private source is unavailable. Different brokers can also produce
different fills, slippage, spread, commission, swap, execution timing, and
profit even when the EA sends the same deterministic requests.

## VPS files

- `StraddleReplica_REAL_EXACT.ex5`: compiled real-capable EA.
- `LATEST_30_REAL_EXACT.set`: target-pattern settings.
- `real-vps-startup.ini`: optional command-line startup configuration.
- `SHA256SUMS.txt`: hashes for every packaged file.
- `Source`: reviewable source used to compile the binary.

## VPS installation

1. Use an isolated MT5 installation and a hedging account that permits at
   least 60 pending XAUUSD orders.
2. Copy `StraddleReplica_REAL_EXACT.ex5` to `MQL5\Experts`.
3. Copy `LATEST_30_REAL_EXACT.set` to `MQL5\Profiles\Tester`.
4. Edit `ExpectedAccountLogin` in the set file to the intended real login.
5. If the broker uses `XAUUSDm` or another suffix, change `TradeSymbol` and the
   startup `Symbol` to that exact symbol.
6. Copy `real-vps-startup.ini` to a permanent VPS directory.
7. Start MT5 with `/portable /config:"C:\path\real-vps-startup.ini"`, or attach
   the EA manually and load the set file.
8. Confirm `RuntimeMode=0`, `RequireDemoAccount=false`,
   `TelemetryEnabled=true`, and `SafetyEnabled=false`.

The package does not contain credentials and does not activate a terminal
automatically.

## Strategy configuration

- 30 buy stops and 30 sell stops.
- Alternating `STR B1`, `STR S1` through level 30.
- Lots per side: `0.01` for levels 1-10, `0.06` for levels 11-20, and `0.15`
  for levels 21-30.
- Anchor-derived, tick-normalized spacing.
- Approximately 100 ms request cadence.
- Two-stage stop management with newest-first serialized updates.
- Twenty-second rearm eligibility for the current `Straddle v1.1.36` target.
- Fixed `$30` basket baseline.
- Pending-order cancellation before residual position closes.

## Real-money warning

This pattern can hold a losing residual basket while banking many small stop
profits. Optional equity-loss, daily-loss, spread, and gross-lot protections
remain disabled because they would change the target behavior.

Use one EA instance per symbol and magic number. Preserve Experts, Journal, and
EA telemetry logs. A real account can lose money, and exact target profit is
not guaranteed.
