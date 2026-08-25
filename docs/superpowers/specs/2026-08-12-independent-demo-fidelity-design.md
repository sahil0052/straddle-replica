# Independent Demo Fidelity Validation Design

## Objective

Create one new demo trading account, deploy the StraddleReplica EA to a new
isolated VPS container in independent mode, and compare its deterministic
behavior against target account `901018`.

The primary account provider is AchieverGlobalMarkets. If its MT5 demo
registration is unavailable, use MetaQuotes-Demo as the fallback.

## Safety and Scope

- Demo account only. No real-money account is authorized by this design.
- Do not modify, stop, restart, or reuse any existing VPS container.
- Create a separate container named `straddle-fidelity-independent-demo`.
- Bind any VNC port to VPS loopback only.
- Bind the EA to the newly created account login and XAUUSD.
- Never print, log, or return the master trading password.
- Return only the investor/read-only login, server, and password to the user.
- Run independent EA logic. Shadow mode, trade copying, and signal mirroring
  are excluded.

## Approaches Considered

### 1. AchieverGlobalMarkets demo — selected primary

This provides the closest available symbol specification, quote feed, spread,
and execution environment to the target account. It gives the best chance of
matching both deterministic logic and broker-dependent execution.

### 2. MetaQuotes-Demo — selected fallback

This is acceptable for validating the EA state machine, level identities, lot
ladder, stop logic, exits, and cycle restarts. Exact entry prices and profit
cannot be expected because its XAUUSD quote was materially different from the
target feed during the August 12, 2026 comparison.

### 3. Shadow or copied execution — rejected

The previous candidate was configured in shadow mode and remained `FLAT`
because `command.csv` was missing. This approach does not validate independent
EA logic and will not be reused.

## Account Creation

1. Attempt demo registration for AchieverGlobalMarkets through a native
   Windows MT5 terminal.
2. Use the user-provided registration identity only where the broker requires
   it.
3. Capture the generated master and investor credentials during registration.
4. If AchieverGlobalMarkets does not permit an MT5 demo registration, create a
   MetaQuotes-Demo account instead.
5. Store the master password only in a temporary restricted credential file
   used for VPS commissioning.
6. Remove temporary credential artifacts after the VPS terminal has saved the
   login and the investor account has been verified.

## VPS Deployment

The new container will:

- use the existing validated MT5/Wine image;
- use a new host directory under `/opt`;
- use an independent terminal and Wine prefix;
- use a unique loopback-only VNC port;
- have no restart dependency on the existing candidate or replica containers;
- load the compiled StraddleReplica EA and a dedicated independent-mode set
  file;
- require a demo account and the exact new login;
- trade only XAUUSD with magic `901018`;
- enable telemetry before Algo Trading is enabled.

Deployment is rejected if the set file contains shadow runtime mode, shadow
command paths, or an expected account login different from the new account.

## Fidelity Configuration

The initial independent profile retains the observed target structure:

- 30 levels per side;
- comments `STR B1` through `STR B30` and `STR S1` through `STR S30`;
- levels 1–10 at 0.01 lots;
- levels 11–20 at 0.06 lots;
- levels 21–30 at 0.15 lots;
- dynamic step derived from the cycle anchor;
- target-compatible trailing activation, tightening, stop-update ordering,
  rearming, basket close, and cycle restart behavior.

No safety control may silently change level identity, lot size, or stop logic.
Account binding, demo-only enforcement, and gross-exposure validation remain
deployment safeguards.

## Comparison Method

The target side is collected through the investor-only target terminal. The
new demo side is collected through EA telemetry and a read-only investor view.

Events are paired by:

- cycle identity;
- comment and grid level;
- side;
- lot size;
- relative entry position versus cycle anchor and step;
- fill sequence;
- stop creation and each stop modification;
- exit reason;
- rearm event;
- basket cancellation and close;
- next-cycle restart.

Broker spread, quote basis, slippage, commissions, swap, fill price, and server
timing are recorded separately from deterministic EA logic.

## Success Criteria

“100% deterministic parity” requires at least one complete synchronized cycle
with all of the following:

- no missing or duplicate level identities;
- identical side, level, comment, and lot for every paired order;
- identical deterministic trigger sequence;
- identical stop-state transitions;
- identical rearm decisions;
- identical basket-close decision;
- identical cycle-restart decision.

Exact monetary profit is claimed only if broker, quote feed, entry, exit, lot,
commission, swap, and timing are also paired. A MetaQuotes-Demo fallback cannot
be described as 100% execution or profit parity with the Achiever target.

## Failure Handling

- If account creation fails, stop without modifying existing VPS deployments.
- If credentials cannot be captured, do not deploy.
- If telemetry is absent or stale, do not claim the EA is running correctly.
- If the first independent cycle diverges, preserve both evidence streams,
  identify one deterministic mismatch at a time, and fix only the proven root
  cause.
- Do not move the EA to a real account until deterministic parity is verified
  over completed demo cycles.

## Deliverables

- New demo login and server.
- Investor/read-only password.
- New isolated VPS container.
- Independent-mode EA preset.
- Candidate telemetry and target comparison evidence.
- A concise parity report listing deterministic matches, broker differences,
  and any remaining mismatch.
