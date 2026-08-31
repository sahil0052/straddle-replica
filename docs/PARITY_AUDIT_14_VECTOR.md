# Adversarial Zero-Trust Parity Audit — ProfitBricks (StraddleReplica) vs Target EA

Stance: the replica is presumed **divergent** until mathematical identity is proven on
the tape. Every claim below carries its population size and its instrument. Where a
prediction of mine was refuted by my own measurement, the refutation is recorded
inline rather than dropped.

## 0. Evidence base

| tape | account / magic | window | orders | deals | positions |
|---|---|---|---|---|---|
| Target `901018` | 901018, AchieverGlobalMarkets-Server, **real**, Hedge | 2026-06-23 → 2026-07-30 | 54,742 | 35,447 | 17,632 |
| `Starwave` | 60542, magic 26011001, **live** (crypto-funded) | 2026-08-21 → 2026-08-28 | 10,863 | 4,796 | 2,468 entries |

### 0.1 The single most important structural fact

**The 901018 tape is not one configuration. It is five**, switched by hand — three of
them on one day (2026-07-13). Any parity percentage quoted against the tape as a whole
is an average over five different EAs and is meaningless. Every number below is
era-scoped.

| assigned profile | window | deployments | re-arms over a live position | attested SL closures |
|---|---|---|---|---|
| `HISTORICAL_50` | 06-23 16:17:27.956 → 07-02 15:18:47.300 | 101 | 0 / 2,847 | 3,478 |
| `HISTORICAL_60` | 07-02 15:24:57.125 → 07-13 11:02:45.175 | 78 | 0 / 6,422 | 7,742 |
| `AGGRESSIVE_30` | 07-13 11:02:45.175 → 07-13 12:32:28.074 | 2 | 0 / 29 | 28 |
| `LOW_RISK_30` | 07-13 13:27:03.676 → 07-13 13:27:10.217 | 1 | 0 / 18 | 25 |
| `STARWAVE_30`&nbsp;<sup>†</sup> | 07-13 15:59:39.163 → 07-30 17:12:10.501 | 103 | 0 / 2,233 | 2,599 |

<sup>†</sup> **The era labels are lattice-signature names, not money-target claims.** The forensic
segmenter (`a901_eras.py:36`) assigns them on levels-per-side, step law and lot ladder only — and
`STARWAVE_30` and `LATEST_30` share all three (30 levels, `anchor_divisor=3000.0`, tiers
0.01 / 0.06 / 0.15, same ratchet constants). On the one field that separates them, the basket money
target, this era is **`LATEST_30`** ($30.00, `ProfileCatalog.mqh:315`, fitted on this very tape): see
§2.7.7. The label is kept because every measurement in this document that uses it — V1, V2, V4, V5, V6,
V9 — depends only on the shared signature and is unaffected.

101 + 78 + 2 + 1 + 103 = **285 deployments**, **282 terminal sweeps**; 7 of the 285
inherit their era boundary (H60 1, SW30 6). Report footer: Net 17,913.29, Gross Profit
56,855.93, Gross Loss −38,942.64, PF 1.459992, Expected Payoff 1.015608, Recovery
8.780809, Sharpe 0.059847, Total Trades 17,638 (Short 9,122 / 85.72% won, Long 8,516 /
84.41% won), Balance Drawdown Maximal 2,040.05 (24.11%).

Terminal account state, read out of the workbook's own trailing blocks
(`tmp/report_901018.csv:107832-107898`, dumped verbatim to `tmp/out_tail.txt`):
Balance 19,673.02, Equity 19,649.45, Margin 8.19, Free Margin 19,641.26,
Floating P/L −23.57, **`Open Positions` 6 rows** (all 0.01, all opened
2026-07-30 17:12:45 → 17:23:32, section total −23.57) and **`Working Orders` 51 rows**
(all `placed`, `STR S1`, `STR S4..S30`, `STR B8..B30`). An earlier draft of this
section quoted "Open Positions 7, Working Orders 56" from a summary read; the raw
section slices are authoritative and give 6 and 51. The distinction is load-bearing
for §2.11 PART 3, where the open-position count enters the IN-deal → position
reconciliation.

### 0.2 Instrument hierarchy (this decided several verdicts)

For the armed stop price, in descending order of trust
(`tools/forensics/attested_stop.py:16-21`):

1. the broker's own `[sl <price>]` exit-order comment — MT5-authored, exact to the cent
2. `position.stop_loss` — the final snapshot only
3. `close_price` — **invalid as a stop estimator**

Measuring the ratchet from close prices produces a 3.7–6.3% negative rate that is pure
artifact (H50 4.49%, H60 6.25%, SW30 3.73%) against **0** on the attested instrument.

---

## 1. Executive parity rating

| # | vector | parity | population | status |
|---|---|---|---|---|
| V1 | Anchor & lattice step geometry | **100.00%** | 25,447 legs / 285 deployments | identity proven |
| V2 | Deployment cadence & interleave | **75.44% raw → 100% of mechanism** | 215/285 raw | divergence found, **fixed** (DIV-5) |
| V3 | Order metadata & broker protocol | **100.00%** | 54,742 orders | identity proven |
| V4 | Two-stage trailing ratchet | **100.00%** | 13,872 + 1,311 attested | identity proven on **both** tapes |
| V5 | Basket liquidation & LIFO ordering | **LIFO 100.00%**, cancel 96.10% | 3,718 closes / 282 sweeps | identity proven; cancel gap explained |
| V6 | Re-arm semantics & memory state | **100.00%** | 11,352 true re-arms / 2,490 repeat slots | identity proven |
| V7 | Basket money exit evaluator | **100.00%** on the predicate, the gate and the reset | 282 sweeps / 17,632 positions | identity proven; threshold bounded to $28–31, see §2.7.7 |
| V8 | Cycle restart floor & state machine | **100.00% of mechanism**; 2 profile constants flagged | 281 restarts / 275 clean pairs | ordering clean 281/281; floor is integer-second in **both** EAs — an identifiability limit, see §2.8 |
| V9 | Lot sizing & tier schedules | **100.00%** | 25,447 legs / 12 ladders | identity proven; array lookup, no arithmetic to diverge, see §2.9 |
| V10 | Trend rescue logic | **100.00%** of the mechanism | 125 doubled orders / 8,536 Starwave legs | ACTIVE on 901018 (6 cycles, 7 events); 12 invariants, 0 exceptions; Finding V10-A tape-only, 0 fills, see §2.10 |
| V11 | Deal ledger & async reconciliation | **100.00% of mechanism**; 1 micro-divergence flagged | 35,447 deals / 54,742 orders / 17,632 positions | money identity **exact to the cent** vs the broker footer (delta $0.00); 0 duplicate deal tickets; Finding V11-A whole-second cycle boundary 5/284 = 1.76%, see §2.11 |
| V12 | Account & symbol suffix binding | **100.00%** on the mechanism; Finding V12-A = 1 comment + 1 behavioural default, both **fixed** | 2 broker suffixes (`XAUUSD.u` 10,863/10,863; bare `XAUUSD` 107,873) + 17,551 closed positions | `TradeSymbol=""` → `_Symbol` verbatim, no parsing; `SYMBOL_TRADE_CONTRACT_SIZE=100` **solved from the tape** (17,550/17,551 = 99.99%, 6/6 open) ⇒ `ContractScale()=1.0000` exactly; Finding V12-A = stale `cycle_target_money=25` in the shipped-defaults comment **and** in live `input CustomCycleTargetMoney` (5.66% early bank on the `CUSTOM_PROFILE` path), see §2.12 |
| V13 | Standalone anti-drift | **100.00%** | 5,764 lines × 2 files, 234,995 bytes, `0b9ced598f06bc0c`; 98 tests | closed-form line identity `20 + 48 + 5,696 = 5,764`; `--check` OK (worktree includes ⇒ both standalones, identical hash); `--verify` OK (HEAD includes rebuild HEAD's standalone byte-for-byte, `f519eb715664a3f8`); both of Finding V12-A's fixes regenerated and re-verified; `85 + 13 = 98 passed`, see §2.13 |
| V14 | Race conditions & execution robustness | **100.00% of the mechanism**; rejection branch **unfalsified** | 0 rejected orders on 65,605; 35,447 deals (25.3% share a millisecond, peak 11); 3,114 Target close gaps | fast ticks cannot accelerate paced flow — `OnTick()` returns for every state but IDLE/RUNNING (`Engine:3422-3423`) and the timer period **is** `inter_order_delay_ms` (`:3378`); head-of-line blocking answered by `m_close_skip` — one request per invocation, the stalled ticket stepped over on the **next** one, so a stall costs one pacing interval instead of firing a burst; a failed close is not read as "flat" (`:2938-2943`); async deal path idempotent by ticket, order-independent by deferral, bounded at 256 with a loud overflow; deployment ≤ 4N sends with a single-shot retry. **Neither EA's rejection path is observable, so this is unfalsified rather than confirmed**, see §2.14 |

**One genuine unimplemented Target behaviour survives the audit: DIV-2** (`STR AVB` /
`STR AVS`, n=28, `HISTORICAL_50` only). Diff in §4.

Three things previously suspected as divergences are **not** divergences and are recorded
here so they are not re-raised: the 14 negative attested locks (§3.1), the orphan-position
leak (§3.2), and the `[1.00,2.00)` band occupancy on the Starwave tape (§2.4).

---

## 2. Per-vector proof

### 2.1 V1 — Anchor & lattice step geometry — 100.00%

Code: `StartCycle()`, `CalculateStep()`, `CalculateAnchor()` (`mql5/include/StraddleEngine.mqh`).

Claim under test: `anchor = NormalizeDouble((bid+ask)/2.0, _Digits)`,
`step = NormalizeDouble(anchor/3000.0, 2)`, `Buy[i] = anchor+(i+1)*step`,
`Sell[i] = anchor−(i+1)*step`, hence `B1 − S1 == 2*step` identically.

The tape does not print the anchor, so it must be **recovered**, and recovering it from
consecutive differences would be circular. Instead the **pair rule** gives one
independent estimate per level present: for level *k*,

```
step_k   = (B_k − S_k) / (2k)
anchor_k = (B_k + S_k) / 2
```

Every *k* in a burst is a separate estimate. Disagreement between them would itself
falsify V1, so the spread is the test statistic.

| measurement | result |
|---|---|
| anchor recovered to a whole cent | **285 / 285** deployments |
| step recovered to a whole cent | **285 / 285** |
| max anchor spread across levels, any era | **0.0** |
| pair-rule residual over all legs | **0.0** on 25,447 legs |
| `B_k − S_k == 2k·step` | **12,686 / 12,686** pairs |
| `k=1`: `B1 − S1 == 2·step` | **209 / 209** |
| `step == round(anchor/3000, 2)` on divisor eras | **106 / 106** |

Step ranges recovered per era: H50 0.75..1.68 · H60 **0.37..0.78** · AGGRESSIVE_30 0.68 ·
LOW_RISK_30 1.35 · STARWAVE_30 1.32..1.39. 84 distinct cycle steps tape-wide.
`LATEST_30`'s 3000 divisor corroborated independently: implied divisor p05 2991 / p50
**3000** / p95 3010.

Off-by-one-pip edge cases: none. The residual is not "small", it is **identically zero**
at the cent, on every leg of every deployment.

Independent second tape: 146 of 148 Starwave bursts are pair-rule self-consistent, steps
1.49–1.56, depths `N=20:69  N=25:1  N=30:78`. The lone `N=25` is a truncated deployment.

**H50 and H60 do not use the 3000 divisor** — they use an ATR-derived step (H50 M15/17,
H60 M5/44). Their steps are still recovered exactly by the pair rule; only the *law*
generating them is unvalidated (§5, open item).

### 2.2 V2 — Deployment cadence & interleave physics — 75.44% raw, 100% of mechanism

Code: `DeployOne()` (`mql5/include/StraddleEngine.mqh:2059-2253`),
`DeployDeferred()` (`2050-2057`), `OnTimer()`, `mql5/include/TradeGateway.mqh`.

Claim under test: strict `B1,S1,B2,S2,…,BN,SN` with zero inversions, dispatched at
`inter_order_delay_ms = 100` (`mql5/include/StraddleTypes.mqh:160`).

Raw strict-interleave conformance on the 285-deployment cut:

| era | conforming | inversions |
|---|---|---|
| `HISTORICAL_50` | 99 / 101 | 2 |
| `HISTORICAL_60` | **10 / 78** | 71 |
| `AGGRESSIVE_30` | 2 / 2 | 0 |
| `LOW_RISK_30` | 1 / 1 | 0 |
| `STARWAVE_30` | 103 / 103 | 0 |
| **all** | **215 / 285 = 75.44%** | 73 |

A 75% score on a deterministic dispatch loop is not noise, and the era concentration
(H60 carries 71 of 73) is the tell: whatever it is, it correlates with **step size**, not
with time or with code version.

**The inversion has exactly one shape.** Classifying every non-conforming burst by where
its level-1 legs landed:

| era | L1 legs LEAD (correct) | L1 legs at the TAIL | L1 legs GONE |
|---|---|---|---|
| `HISTORICAL_50` | 99 | 2 | 0 |
| `HISTORICAL_60` | 3 | **68** | 7 |
| `AGGRESSIVE_30` | 2 | 0 | 0 |
| `LOW_RISK_30` | 1 | 0 | 0 |
| `STARWAVE_30` | 101 | 0 | **2** |

Every single inversion is *the same event*: the level-1 pending is not dispatched first,
it is dispatched **last**, after `S60`. The transition observed at the burst tail is
`S60→S1` ×37, `S60→B1` ×31, `S1→B1` ×3 — never anything else. Levels 2..N are in perfect
interleave in all 285 bursts. This is **DIV-5**.

**Mechanism, proven quantitatively.** A `BUY STOP` must sit at or above
`ask + stops_level*point`; a `SELL STOP` at or below `bid − stops_level*point`. Level 1 is
the only level whose distance from the anchor is a single step, so it is the only level
that can fail that test. With `anchor = mid` and `ask = mid + spread/2` the condition for
level 1 to be placeable on the first pass is

```
step  >=  spread/2 + stops_level*point
      ~=  0.15     + 0.50                =  0.65        (XAUUSD, point 0.01)
```

The tape's measured knee — the largest step at which level 1 is deferred, and the smallest
at which it leads — is **(0.64, 0.68]**. The prediction and the measurement agree to a
cent, and the per-era table above then follows with no further freedom: H60's steps are
**0.37..0.78** (mostly below the knee → 68 deferrals), H50's are 0.75..1.68 (above →
99 leads), STARWAVE_30's are 1.32..1.39 (far above → 103 leads, 0 deferrals).

**The deferred leg returns at its exact original lattice price** — it is not re-anchored.
Two raw-tape instances, each read directly off the order stream:

```
2026-07-02 21:52:35   B60 4148.27   S60 4093.07  ->  anchor 4120.67  step 0.46
                      tail leg      4121.13  ==  anchor + 1*step        exact
2026-07-08 14:04:33   B60 4098.01   S60 4032.01  ->  anchor 4065.01  step 0.55
                      tail leg      4065.56  ==  anchor + 1*step        exact
```

In the second instance `S1` was never dispatched at all, and one threshold explains both
outcomes on the same tick: at `ask ≈ 4065.0 / bid ≈ 4064.7`, `B1 = 4065.56` clears
`ask+0.50` by 0.06 while `S1 = 4064.46` misses `bid−0.50` by 0.26. The 7 H60 and 2 SW30
`GONE` bursts are that case — deferred, retried, still un-placeable, dropped.

Missing-leg census over the deferred population: `['B1']` ×34, `['S1']` ×27, `[]` ×5,
`['S1','S2']` ×1, `['S1','S15'..'S18']` ×1.

**Broker rejection behaviour — the audit's explicit question.** The state census over all
54,742 orders is `filled 35,430` + `canceled 19,312` and **zero rejected**. There is no
`REQUOTE`/`PRICE_CHANGED` rejection anywhere on either tape, so "skip-and-advance or halt"
is not decided by rejection evidence — it is decided by the deferral evidence above, which
shows **skip-and-advance, then retry the skipped slot at the tail at its original price**.
That is what the replica now does: `DeployOne()` marks the slot
`deploy_deferred` (`mql5/include/StraddleTypes.mqh:205`) and advances `m_deploy_index`,
and `DeployDeferred()` (`StraddleEngine.mqh:2050-2057`) re-dispatches it after `SN`.
Landed as 4 source edits with 4 contract tests; the ~92-line evidence comment at
`StraddleEngine.mqh:2148-2242` carries the derivation.

**Cadence.** Configured `inter_order_delay_ms = 100`; observed median inter-order gap on
the tape **112 ms**, and the deferred-leg gaps are a single timer tick — 110, 113, 111,
111, 117, 116 and 139 ms. `OnTimer` runs at `MathMax(20, inter_order_delay_ms)`, so 100 ms
is the floor and 112 ms is that floor plus dispatch latency. No throttle, no backoff.

### 2.3 V3 — Order metadata & broker protocol invariants — 100.00%

Code: `PlaceStop()` (`mql5/include/TradeGateway.mqh:278-298`), `ClosePosition()`
(`336-360`), `OpenMarket()` (`315-334`), `ModifyPosition()` (`300-313`),
`PendingFillingMode()` (`49-52`), `MarketFillingMode()` (`14-22`).

**`sl=0.0` / `tp=0.0` on every pending.** Literal in the request at
`TradeGateway.mqh:290-291`. On the tape: **0 of 54,742** orders carry an S/L, **0 of
54,742** carry a T/P, and **0 of 17,632** positions carry a T/P. Position S/L is set on
14,913 and blank on 2,719 — i.e. the stop is only ever attached *after* the fill, by the
trailing scheduler, never at order-placement time. That asymmetry is the invariant: a
pending with `sl` pre-set would show up in the order stream, and none does.

This is also what makes the orphan mechanism possible at all (§3.2): a re-armed pending
carries no protective stop, so a fill that the EA has lost track of is unprotected until
the sweep.

**Filling mode, measured rather than assumed.** Cross-tab of the Starwave tape (10,863
orders) on comment × type × `type_filling`, reproduced from the evidence comment at
`TradeGateway.mqh:24-48`:

| comment | type | `type_filling` | n |
|---|---|---|---|
| `STR B<n>` / `STR S<n>` | 4 `BUY_STOP` | **2 RETURN** | 4,257 |
| `STR B<n>` / `STR S<n>` | 5 `SELL_STOP` | **2 RETURN** | 4,279 |
| `STR CLOSE` | 0 `BUY` | **0 FOK** | 524 |
| `STR CLOSE` | 1 `SELL` | **0 FOK** | 473 |
| `[sl <price>]` | 0 `BUY` | 1 IOC | 674 |
| `[sl <price>]` | 1 `SELL` | 1 IOC | 637 |

All **8,536 / 8,536** pendings carry RETURN; not one carries FOK or IOC. All **997 / 997**
EA market closes carry FOK, which is exactly what `MarketFillingMode()` returns on a symbol
advertising `SYMBOL_FILLING_FOK`. The 1,311 IOC orders are **broker-authored stop-outs**
(`ORDER_REASON_SL`), which the EA does not write — so the correct reading of the audit's
question "`ORDER_FILLING_RETURN` for stops vs IOC/FOK for market closes" is
**RETURN for pendings, FOK for EA closes, IOC only on the broker's own stop-outs**.
`type_time = 0 GTC` on every pending (`TradeGateway.mqh:295`); no expiry is ever set.

Sending FOK on a `TRADE_ACTION_PENDING` is not a cosmetic divergence: on a broker that does
not advertise FOK for pendings it returns retcode 10030 and the lattice never deploys.
Hence `PendingFillingMode()` is a **constant**, not a capability probe.

### 2.4 V4 — Two-stage trailing ratchet inversion — 100.00% on both tapes

Code: `CStopScheduler::Calculate()` (`mql5/include/StopScheduler.mqh:9-190`) — gate
`153-154`, activation branch `156-164`, trail branch `165-173`, quantisation `175-178`,
broker clamp and ratchet return `180-189`; drivers `TrailSelectedPosition()`
(`mql5/include/StraddleEngine.mqh:3023-3051`), `UpdateTrackedPositionStops()` (`3058-3076`),
`UpdatePositionStops()` (`3078-3117`), called from `3419` and `3769`.

**What the tape can and cannot see.** A position's stop is rewritten many times; the tape
preserves only the **last** one, as the broker's `[sl <price>]` exit-order comment. The
ratchet's *path* is therefore unobservable, and no amount of data recovers it. What is
observable is the **final** lock, one value per stopped-out position:

```
locked = dir*(attested_sl − entry) / step
```

and that single number is enough, because inverting the writer makes its distribution
*structurally* constrained. Both branches write `desired = market − dir*D*step`, so with
`favorable = dir*(market − entry)/step`:

```
locked = dir*(market − dir*D*step − entry)/step = favorable − D
```

The final write is the one taken at the highest favorable excursion `F` reached before the
retrace that triggered the stop, and `D` is a function of `F` alone
(`StopScheduler.mqh:167-171`). Three cases exhaust the space:

| condition | branch | `D` | `locked = F − D` lands in |
|---|---|---|---|
| `F < 2.0` | gate refuses (`153-154`) | — | no stop exists |
| `2.0 <= F < 3.0` | trail, pre-tighten | 2.0 | **`[0.0, 1.0)`** |
| `F >= 3.0` | trail, tightened | 1.0 | **`[2.0, ∞)`** |

`[1.0, 2.0)` is **not reachable by any trail write**: it needs either `F ∈ [3,4)` at
`D = 2.0` (excluded — at `F >= 3.0` the ternary has already switched to `trail_distance_steps`)
or `F ∈ [2,3)` at `D = 1.0` (excluded — that switch requires `F >= 3.0`). The forbidden band
is a *consequence of the two-stage law*, not an assumption about it, which is what makes it
the test statistic: a single-stage trail produces no trough at all, and a differently-placed
switch produces the trough somewhere else.

Quantisation cannot manufacture a crossing either — `MathRound(desired/tick_size)*tick_size`
(`175-178`) bounds drift at half a tick, 0.005 in price, **0.0033 steps** at Starwave's 1.53.
A 1.0-step-wide band is 300× that.

**Measurement 1 — the Starwave tape** (`tmp/asw_trail.py`, independent of `tools/forensics/`;
`grep -rl "Starwave_60542" tools/` returns nothing, so this is a second derivation and not a
re-run of the same code path):

```
lattice stops 8536   deployment bursts 148   entry deals 2468   SL exits 1311
lattice depth N per burst: N=20:69  N=25:1  N=30:78
step values seen: 1.49 1.50 1.51 1.52 1.53 1.54 1.55 1.56
exit == armed sl to the cent: 1311/1311 (100.00%)
filled BEYOND the stop (slippage): 0   filled short of it: 0
negative 1 (0.08%) | (0.00,1.00) 540 (41.19%) | [1.00,2.00) FORBIDDEN 25 (1.91%)
[2.00,3.00) 458 (34.94%) | >=3.00 287 (21.89%)
locked steps: min -6.6558  p05 +0.1097  p50 +2.1373  p95 +4.6387  max +8.1290
```

Every predicted feature is present and every one is quantitative:

| prediction | measured |
|---|---|
| Stage 1 band `[0,1)` populated | **540 (41.19%)** |
| trough `[1,2)` depleted >95% | **25 (1.91%)** = 95.4% depleted vs `[0,1)` |
| Stage 2 floor `[2,∞)` populated | **745 (56.83%)** |
| exit price == armed stop | **1311 / 1311** |

At 0.1-step resolution the trough is not a dip, it is a hole. Buckets across `[1.0,2.0)`
run `1,2,2,6,1,5,1,1,1,5`; the ten buckets immediately above run
`63,63,48,41,48,45,41,34,43,32`, and the ten immediately below run 44–71. That is a
**20–30× per-bucket collapse** with dense mass on both sides — the signature of a switch at
exactly 3.0 favorable steps, and of nothing else.

**Two artifact hypotheses were tested against this and both died.** (i) Entry slippage
cannot smear the band: on this tape `fill == lattice` identically, so `locked` measured from
the fill and from the lattice price are the same number, and re-measuring all 25 band
residents from the lattice moved **0 of 25** out. (ii) Step-inference error cannot have
produced the trough: the pair rule fixes `step` to the cent on 146 of 148 bursts, and the
eight distinct step values above are separated by 0.01, far below the 1.0-step band width.

**The 25 residents are explained by the code, and must not be "fixed".** The activation
branch (`156-164`) applies `pre_tighten_trail_distance_steps` **unconditionally** — it carries
no `tighten_trigger_steps` test, unlike the trail branch's ternary at `167-171`. So a position
whose *first* poll already finds `F ∈ [3,4)` is armed at `locked = F − 2.0 ∈ [1,2)`, inside
the band. The next poll ratchets it out to `>= 2.0`; a position stopped out before that poll
exits with a band-resident lock. Of the 25, 3 are one cent of step-inference residue and 22
are that first-write case. Per tier the concentration is exactly where fast first polls occur —
`L1-10 n=1254 forbidden 25`, `L11-20 n=54 forbidden 0`, `L21-30 n=3 forbidden 0`. Removing the
asymmetry (gating activation on `tighten_trigger_steps` too) would empty the band completely
and **break parity**, because the Target's own tape puts 25 exits inside it. The rationale is
recorded in-source at `StopScheduler.mqh:74-82` ("ACTIVATION IS NOT EXACT BREAKEVEN, and must
not be 'corrected' to it") and `96-108`.

**`activation_uses_trailing_distance = true`, proven by shape rather than by assertion.** The
false branch writes `entry + dir*lock_offset_price` (`163`), which is a **price** offset, not a
step multiple. Every position whose final write was the activation write would then exit at the
single value `lock_offset_price/step = 0.2/1.53 = 0.131` steps — a delta function, since the
ratchet return (`183`, `188`) only admits tightening and so cannot move it. The tape instead
spreads its 540 `[0,1)` exits across the interval at 44–71 per 0.1-step bucket with no spike
anywhere, and puts p05 at **+0.1097**, *below* the value the false branch is pinned to. The
flag is `true`. Derivation in-source at `StopScheduler.mqh:113-139`.

**Measurement 2 — the 901018 tape, which contains both configurations and therefore settles
the two-stage law by controlled contrast.** `trail_distance_steps = 1.0` is written by exactly
ten profile cases (`ProfileCatalog.mqh:142, 168, 187, 242, 415, 449, 484, 520, 554, 591`);
`HISTORICAL_50` (case at `65`) and `HISTORICAL_60` (case at `111`) do not write it, so they
inherit `ResetProfile`'s `2.0` (`28`) and run **single-stage** with `pre_tighten == trail == 2.0`
(DIV-4). Single-stage gives `locked = F − 2.0` for all `F >= 2.0`, i.e. `[0, ∞)` continuous with
**no trough**. Two-stage gives the trough. Attested band census over n=13,872
(`tmp/a901_negative_lock.py` part 5):

| era | `trail_distance_steps` | n (attested) | in `[1.00, 1.95)` | rate |
|---|---|---|---|---|
| `HISTORICAL_50` | 2.0 → single-stage | 3,478 | 783 | **22.51%** |
| `HISTORICAL_60` | 2.0 → single-stage | 7,742 | 1,658 | **21.42%** |
| `AGGRESSIVE_30` | 1.0 → two-stage | 28 | 1 | 3.57% |
| `LOW_RISK_30` | 1.0 → two-stage | 25 | 0 | 0.00% |
| `STARWAVE_30` | 1.0 → two-stage | 2,599 | **0** | **0.00%** |
| all | — | 13,872 | 2,442 | 17.60% |

Single-stage eras: 2,441 of 11,220 = **21.76%** occupied. Two-stage eras: **1 of 2,652 =
0.04%**. A 500× contrast, on one tape, one instrument, one script, with the configuration flag
as the only varying term. The band is not a property of the market and not a property of my
estimator; it is a property of `trail_distance_steps`, exactly as the inversion predicts.

**The one asymmetry between the tapes, stated rather than smoothed over.** Both run two-stage,
yet 901018's `STARWAVE_30` puts **0 of 2,599** in the band while Starwave puts **25 of 1,311
(1.91%)**. By the rule of three, 0/2,599 upper-bounds the first-poll entry rate at **0.115%**,
so the two differ by more than an order of magnitude. The mechanism above localises this
precisely: band entry requires the price to travel **three full steps between two consecutive
trail polls** (≈3.96–4.17 in price at 901018's 1.32–1.39 step, ≈4.47–4.68 at Starwave's
1.49–1.56 — near enough that step size cannot be the difference). What remains is poll
granularity, i.e. `stop_update_interval_seconds` and the `OnTick`/`OnTimer` route into
`UpdatePositionStops()`. That is an operator setting, and it is **not measurable from either
tape**, because the tape preserves only the final stop write. Both outcomes are reachable from
the same replica code with no edit; the difference bounds the Target's poll rate and does not
bear on the ratchet law.

**Which positions get trailed.** `UpdatePositionStops()` (`3078-3117`) throttles on
`stop_update_interval_seconds` (`3081-3085`), takes one tick (`3087-3089`), and then forks:
under `OrphanLeakActive()` it calls `UpdateTrackedPositionStops()` and returns (`3090-3094`),
otherwise it walks the whole book (`3095-3110`). Both paths honour `stop_scan_newest_first` by
index inversion (`3099-3101`) or `ArrayReverse` (`3062-3063`), both gate on
`IsOwnedPositionSelected()`, and both stop at `max_stop_updates_per_pass`. This is not a
refactor for tidiness: **not one of the Target's 153 orphaned positions ever received an `[sl]`
order**, across 1–9 days of XAUUSD movement, while all 1,311 tracked positions did. A book-wide
scan under leak mode would have trailed them. Rationale in-source at `3053-3057`. The single
write is `m_gateway.ModifyPosition(ticket, desired)` (`3046`), reached from `3419` and `3769`.

**Instrument discipline — the correction that made this vector measurable at all.** Re-deriving
the ratchet from `close_price` instead of the attested `[sl <price>]` comment produces a 3.7–6.3%
negative-lock rate out of nothing (H50 4.49%, H60 6.25%, SW30 3.73%) against **0** on the
attested instrument, and it also fabricates band mass. Every figure in this section is measured
on the attested price; see §0.2 for the hierarchy and `tools/forensics/attested_stop.py:16-21`
for the implementation.

**Verdict: identity proven on both tapes, no code change.** The gate constant (2.0), the switch
point (3.0), the two distances (2.0 → 1.0), the unconditional pre-tighten on activation, the
`MathRound` quantisation, the direction-specific broker clamps and the tighten-only ratchet
return all reproduce the Target's observable output exactly. The 14 negative attested locks
tape-wide are a separate question with a separate answer — 9 operator-authored, 5 measurement
noise at 1–7 cents — resolved in §3.1.

### 2.5 V5 — Basket liquidation & LIFO close ordering — 33.95% as configured, 95.57% with DIV-6 applied

The directive asks three questions. Two are answered **identical**; the third found a real divergence,
and it is the only vector in this audit where a measurement overturned a profile field.

| directive question | verdict | population |
|---|---|---|
| `cancel_before_close=true` strictly? | **DIVERGENT (DIV-6)** — the Target is cancel-first in *every* era; the replica inherits `false` on four of twelve profiles | 271 cycles with ≥1 close |
| Strict reverse-ticket LIFO? | **IDENTICAL** — inversion **1.0000**, **163/163** sweeps exactly reverse-of-ticket | 20,292 ordered pairs / 2,394 legs / 163 operator-free sweeps |
| "113 ms burst per position"? | **NO BURST** — a configured ~100 ms pacer; **0 of 3,114** operator-free gaps below 95 ms | 3,114 inter-close gaps |

#### 2.5.1 The state machine, and the one fork the flag controls

`BeginClose(reason, halt_after)` (`StraddleEngine.mqh:2754-2770`) is the single entry point to
liquidation, and the flag appears in exactly one expression:

```cpp
      ENUM_CYCLE_STATE replica_close_state=
         (m_profile.cancel_before_close ? CYCLE_CANCELING : CYCLE_CLOSING);
      m_state=(halt_after ? CYCLE_CLOSING : replica_close_state);
```

Two invariants fall straight out of those two lines, and both matter for the measurement that
follows:

1. **A halting close ignores the flag.** `halt_after==true` forces `CYCLE_CLOSING` regardless, so
   every safety-triggered flatten is close-first *by construction*. The two call sites are
   `3434` (`safety_reason`, halt) and `3458` (`"basket_target"`, no halt); only the second is the
   basket-target path this vector measures. On the 901018 tape no safety guard ever fired, so the
   halting branch contributes nothing and cannot mask the result.
2. **The flag's entire effect is the phase order**, not the content of either phase. Both phases
   run to completion either way — `CancelOneOrder()` (`2974-3002`) hands off to `CYCLE_CLOSING`
   when orders are gone and positions remain, and `CloseOnePosition()` (`2925-2955`) hands off to
   `CYCLE_CANCELING` when positions are gone and orders remain. The flag chooses which one goes
   first; nothing is skipped in either configuration.

The handoff is a *state assignment followed by a return*, dispatched from `OnTimer` at
`3775` (`CYCLE_CLOSING`), `3778` (`CYCLE_CANCELING`) and `3781` (`CYCLE_RESTARTING`):

```cpp
      if(!m_halted &&
         m_profile.cancel_before_close &&
         CyclePositionCount()>0)
        {
         m_state=CYCLE_CLOSING;
         m_last_close_at=0;
         m_close_skip=0;
         PersistCycle();
         return;
        }
```

That `return` is load-bearing for §2.5.4: the first close cannot be sent on the same pass that
retired the last order, so the cancel→close lead has a **hard floor of one timer period**.

#### 2.5.2 DIV-6 — `cancel_before_close` is wrong on four profiles

`ResetProfile()` initialises the field to `false` (`ProfileCatalog.mqh:31`). Eight profiles
override it to `true` — JUNE_2K `193`, LATEST_30 `261`, the six `STARWAVE_*` at
`424, 458, 492, 528, 562, 599`, plus the custom mirror at `676`. **Four do not:**
`HISTORICAL_50` (case `65`), `HISTORICAL_60` (`111`), `AGGRESSIVE_30` (`138`) and
`LOW_RISK_30` (`164`) inherit `false`. That is an 8-true / 4-false split — the same shape as
`replica_orphan_leak`, which is why it read as deliberate rather than as an omission.

It is an omission. The prior audit criterion was one-sided (`tmp/a901_v4578.py:313-317` asked only
whether *some* lattice pending was cancelled in the 10 s window before the first close), so it
could confirm cancel-first but never falsify it. `tmp/a901_cancel_order.py` replaces it with a
symmetric, mutually exclusive three-way classifier: attribute every cancelled grid pending to a
cycle by its `end_time`, split that cycle's basket closes into liquidation groups at a 60 s gap,
take the terminal group, and compare.

```
    era                flag  cycles  CANCEL_FIRST  CLOSE_FIRST  INTERLEAVED   matches flag
    HISTORICAL_50     false      95            95            0            0      0/95 =   0.00%
    HISTORICAL_60     false      72            71            1            0      1/72 =   1.39%
    AGGRESSIVE_30     false       2             1            0            1      0/2 =   0.00%
    LOW_RISK_30       false       1             1            0            0      0/1 =   0.00%
    STARWAVE_30        true     101            91            0           10     91/101 =  90.10%
    ALL                         271           259            1           11
```

**259 of 271 cycles are strictly cancel-first, and exactly one is close-first.** Under the
configured flag the four inherited-`false` eras score **2 of 170**. The irony is worth stating
plainly: the *only* cycle in those four eras where the replica's configured behaviour matches the
tape is cycle 169 — and cycle 169 is a **manual operator flatten**, the one sweep on the tape the
EA did not author (§2.5.3). Every cycle the EA actually liquidated contradicts the flag.

Cross-boundary attribution was checked rather than assumed: 106 of 19,312 cancels (**0.55%**) have
an `end_time` in a later cycle than their placement, so attributing by `end_time` matters, but at
that magnitude it cannot manufacture a 168-cycle result.

**The fix is four lines**, one per case, in the established evidence-comment style — full diff in
§4.2, registered as DIV-6 in §3.11. No engine change: `BeginClose()` already implements both
orders correctly, and the telemetry field `profile_cancel_before_close` (`1442-1443`) already
publishes which one is live.

#### 2.5.3 The control that makes the other two answers clean: five operator sweeps, isolated

The remaining two questions — cadence and ordering — are both contaminated by the human operator,
and the contamination has an **independent marker**. `close by` is `PositionCloseBy`, which has no
call site anywhere in the EA; its 12 occurrences on the tape (span `2026-07-02 15:23:27.587` ..
`2026-07-13 13:21:22.186`) therefore date hand actions exactly, and they are derived from neither
cadence nor ordering — the two things being measured. Flagging every terminal sweep with a
`close by` within ±60 s picks out **five cycles**:

```
      cyc  era              verdict       legs  min gap(ms)  median(ms)  inversion  nearest `close by`
      108  HISTORICAL_60    CANCEL_FIRST    5          2.0         2.0      0.000    22.871 s before
      138  HISTORICAL_60    CANCEL_FIRST    1          0.0         0.0        nan    18.634 s before
      167  HISTORICAL_60    CANCEL_FIRST    6          2.0         5.0      0.700    30.077 s before
      169  HISTORICAL_60    CLOSE_FIRST    43          0.0         5.5      0.000     0.232 s before
      171  AGGRESSIVE_30    INTERLEAVED     8          2.0         3.0      0.000     0.109 s before
```

All five share a signature no EA sweep on this tape shows: **millisecond gaps** (min 0–2 ms,
median 2–5.5 ms) and **forward or scrambled ticket order** (inversion 0.000, 0.000, 0.700, 0.000).
Cycles 169 and 171 are the previously identified Packs 3 and 4; 108, 138 and 167 are three more,
found by the marker rather than by the cadence histogram that originally motivated the hunt. This
closes the `close by` census: **all 12 sit beside a hand-flattened sweep.**

It also disposes of the two non-CANCEL_FIRST cycles in the inherited-`false` eras: both are in
this table. Excluding operator sweeps, those eras are **168 of 168 = 100.00% cancel-first**.

#### 2.5.4 Cadence — there is no burst; the ~100 ms figure is a configured delay

Re-running the inter-close gap census with the five operator sweeps removed:

```
    era               sweeps   gaps     p05     p50      p95  <10ms  10-95  95-135  >=135  inversion  exact rev
    HISTORICAL_50         95   1191    99.0   103.0    150.0      0      0    1111     80      1.000   95/95
    HISTORICAL_60         67   1030   102.0   105.0    215.0      0      0     929    101      1.000   67/67
    LOW_RISK_30            1     10   114.0   121.0    126.0      0      0      10      0      1.000    1/1
    STARWAVE_30          101    883   101.0   120.0  20226.0      0      0     558    325      0.991   92/101
```

**Zero of 3,114 gaps fall below 95 ms, and zero fall in 10–95 ms.** The distribution is
single-moded at one OnTimer period in every era, with no sub-cadence population whatsoever once
the operator is excluded — H60's 45 sub-10 ms gaps were *all* inside the five flagged sweeps, as
were AGGRESSIVE_30's seven (which is why that era, whose only other sweep is a single close,
contributes no row here at all — stated rather than smoothed).

This settles the directive's "113 ms burst per position" as a **misreading of a pacer**: the
observed p50 is 103 / 105 / 121 / 120 ms per era, which is `OnTimer` running at
`MathMax(20, inter_order_delay_ms)` = 100 ms with `close_interval_seconds=0`. STARWAVE_30's
p95 of **20,226 ms** is the independent confirmation — that is `close_interval_seconds=20`
(`ProfileCatalog.mqh:303`, LATEST_30) resolving to the second through
`CloseIntervalElapsed()` (`2780-2787`), which compares `TimeCurrent()-m_last_close_at` against a
whole-second field. Two different configured pacers, both reproduced.

Two earlier hypotheses are therefore **refuted, not merely unsupported**: **H-f** (one close per
market tick) and **H-g** (the gap is a synchronous `OrderSend` round-trip). Both predict a gap
distribution that tracks tick arrival or broker latency; both are excluded by a 3,114-sample
distribution with a hard floor at 95 ms and nothing below it.

#### 2.5.5 LIFO — inversion 1.0000 over 20,292 ordered pairs

The instrument is a pair-inversion rate, not a spot check. Sort a terminal sweep's closes by
`(open_time, order_id)`, resolve each to the position it retired, and count the ordered pairs
`i<j` for which `position_id[j] < position_id[i]`. A strict newest-first sweep scores 1.000 on
every pair; a forward sweep scores 0.000; a scrambled one lands near 0.5. Ticket ids are issued
monotonically in open time, so on this tape *reverse-of-ticket* and *LIFO* are the same predicate
measured two ways.

```
    era               sweeps   legs   gaps   inversion  exact rev
    HISTORICAL_50         95   1286   1191      1.000     95/95
    HISTORICAL_60         67   1097   1030      1.000     67/67
    LOW_RISK_30            1     11     10      1.000       1/1
    STARWAVE_30          101    984    883      0.991    92/101
    H50+H60+LOW_RISK_30  163   2394          pairs 20292  inversion 1.0000  exact reverse 163/163
```

**Twenty thousand two hundred and ninety-two ordered pairs, zero discordant.** Not one close in
those three eras retired a position older than one already retired in the same sweep. H60 reaches
this only after the operator control of §2.5.3 — with cycles 108, 167 and 169 left in it scores
0.920 with 67 of 70 exact and two sweeps in *exact forward* order, and both of those forward
sweeps are hand actions. The improvement is the point: the contaminated figure understates a
mechanism that is in fact exact.

The replica implements that mechanism twice, once per branch of the orphan-leak fork (§3.2), and
both branches walk descending:

```cpp
      if(OrphanLeakActive())
         return TryCloseOneTrackedPosition();
      int owned=0;
      for(int index=PositionsTotal()-1;index>=0;index--)
```

`TryCloseOneOwnedPosition()` (`StraddleEngine.mqh:2892-2923`) walks the terminal's own position
list from `PositionsTotal()-1` downward, and MT5 appends new positions to the end of that list, so
descending index is descending ticket. The leak-mode path
`TryCloseOneTrackedPosition()` (`2847-2876`) cannot rely on list order because it walks only the
tickets the level table still points at, so it sorts explicitly — `ArraySort(tickets)` at
`CollectTrackedPositionTickets()`'s tail (`370-396`, sort at `394`, ascending) — and then walks
`for(int index=count-1;index>=0;index--)` at `2852`. **The fork changes which positions are
eligible, never the order they are retired in**, which is why DIV-6 and the orphan-leak switch
cannot interact with this vector.

STARWAVE_30's 0.991 is the one sub-unity figure, and it has a mechanical cause that predicts its
own boundary. Nine of its 101 sweeps are non-exact; **none is forward.** That era is the one
running `close_interval_seconds=20` (`ProfileCatalog.mqh:303`), so its sweeps span minutes
(§2.5.4's p95 of 20,226 ms per *gap*) instead of the ~100 ms per leg the other three eras take. A
re-arm that fills *inside* such a sweep creates a position that did not exist when the sweep
started; the descending walk re-collects the list each invocation, so that arrival is retired after
legs with lower tickets have already gone, and every pair spanning the arrival is discordant —
without the walk direction changing at all. The prediction is that non-exact sweeps appear only
where a sweep is long enough for a fill to land inside it, and the partition is exactly that: the
three eras with `close_interval_seconds=0` are 163/163, the one era with a 20 s pacer is 92/101.

The walk direction is not re-openable, and the source says so at `2800-2846` because it was once
wrong. Three independent measurements bound it:

- **The 901018 tape, all sweep closes:** 3,718 of 3,718 in reverse-of-ticket order (`2843-2844`).
- **The Starwave tape** — a different account, a different build — `tools/forensics/sweep_lifo.py`:
  inversion **0.983** over 29 post-break sweeps, **14 of 29 exactly reverse, 0 of 29 forward**;
  pre-break 0.853 with 60 exactly reverse and **1** exactly forward out of 219 (`2803-2806`).
- **Level order, read off the Target's own comments** (`STR B7` / `STR S12`, matching 17,515 of
  17,632 positions = 99.3%, and 1,097/1,097 post-break) — `sweep_level_order.py` finds no level
  ordering whatsoever:

```
     stream               sweeps  legs  median rho(order, level)  inner  outer
     Target pre-break        219  2250          -0.086              54     63
     Target post-break        29   255          -0.400               2     13
```

Commit `9a0cf62` briefly flipped the loop to ascending on the stated ground that the Target "closes
positions in ascending level order", citing an `audit_sweep_order.py` **that is not in this
repository**. The claim does not reproduce: post-break the correlation's sign is negative and
outer-first sweeps outnumber inner-first 13 to 2. **Ascending is the one direction the evidence
excludes.** Two guardrails go with that verdict, both already in the source:

1. The geometric reconstruction kept in `sweep_level_order.py` as a cross-check agrees with our own
   comments 47/47 and 31/31 but carries a systematic off-by-one on Target cycles (86.1% pre-break,
   54.5% post-break, always `geo = comment + 1`), so **it must not be used for an absolute level**.
   Being off by one is monotone, which is why it still reaches the same verdict (`2822-2827`).
2. Level and open time are decoupled because level is a *per-side* coordinate: each wing numbers
   outward from the anchor independently, so "newest" means "outermost" only inside a one-sided
   trend. An earlier note in this repository inferred "newest-first therefore outer-levels-first"
   from `rho(order, open time) = -0.994`. **The measurement was right; the inference was not**
   (`2829-2834`).

The tempting optimisation — close inner legs first to cut drift exposure during a paced sweep — is
also excluded, and not on aesthetic grounds: pacing has been measured as a **variance** term rather
than a bias term, `rho(sweep span, cycle exit) = +0.015` across 91 Target sweeps
(`flatten_order.py` Panel C). It would buy nothing measurable and would be a deliberate divergence.
**Verdict: identical, no change.**

#### 2.5.6 The cancel→close handoff is quantised to one `OnTimer` tick

§2.5.1 predicted a hard floor: `CancelOneOrder()` assigns `m_state=CYCLE_CLOSING` and *returns*, so
the first close cannot leave on the pass that retired the last order. The lead from last cancel to
first close, over the 256 operator-free `CANCEL_FIRST` sweeps:

```
    lead (ms): min 97  p05 99  p50 103  p95 142  max 14326559
    95-135 243   135-1000 7   >=1000 6
    leads inside one 100 ms OnTimer tick [95,135): 243/256 = 94.92%
```

**Nothing below 95 ms, and the minimum is 97 ms** — one timer period, exactly as the `return`
requires. The 13 outliers are the expected shape of the 0.55% cross-boundary cancel attribution of
§2.5.2: 7 between 135 ms and 1 s, and 6 at or above 1 s (worst ≈ 3.98 h, a cancel whose `end_time`
fell in a later cycle than its placement). They are an attribution artifact of the *measurement*,
not a second mode of the mechanism.

One correction belongs here, because the earlier criterion was replaced and it would be easy to
record the replacement as a bug fix. **The old 10 s-window metric was conservative, not
contaminated.** I had hypothesised it was picking up the *next* cycle's cancels; the symmetric
classifier refutes that — H60 scores 90.28% under the old window and **98.61%** under the symmetric
one, i.e. the old window *missed* cancel-first cycles rather than inventing them. The cause is the
window itself: cancel-phase spans run p50 8.52 s (H50) / 9.67 s (H60) with p95 184.66 s / 5,361.98 s,
so a 10 s look-back truncates the tail of a phase that legitimately takes minutes. Do not describe
the old metric as contaminated.

The anti-stall mechanism that keeps the paced sweep from head-of-line blocking is `m_close_skip`
(`2789-2798` for the rationale, `2903-2904` / `2916` / `2921` for the three uses): a ticket whose
close fails is stepped over on the *next* invocation rather than inside the same one, so a single
quote-delayed leg costs one pacing interval instead of firing a burst of synchronous `OrderSend`
round-trips. That is the V14 answer to "does `TryCloseOneOwnedPosition()` handle transient
rejections without head-of-line blocking", carried forward to §2.14.

**V5 verdict.** Two of the directive's three questions are identical and one is divergent. Under the
configured flags, observed phase order matches configuration on **92 of 271 cycles = 33.95%**. With
DIV-6's four lines applied, **259 of 271 = 95.57%** are strictly cancel-first as configured, and the
12 exceptions are fully itemised rather than absorbed: **2 are operator flattens** (cycle 169
close-first, cycle 171 interleaved — both in §2.5.3's table), and **10 are STARWAVE_30 cycles
classified INTERLEAVED**, all with a negative cancel→close lead and a cancel-run p95 of 1,114.96 s.
The mechanism that fits those ten is the same 20 s pacer that explains §2.5.5's nine non-exact
sweeps — re-arms fill during a minutes-long sweep and must then be cancelled, so cancels continue
after closes have begun — but that remains an open item in §5 rather than a proven claim. On the
four eras DIV-6 repairs, EA-authored cycles are **168 of 168 = 100.00%** cancel-first.

---

### 2.6 V6 — Re-arm semantics & per-level memory state — 100.00%

The directive's question is narrow and falsifiable: *"1,120 re-arms. 100% return to exact
`level.target_price`, never re-anchored?"* The 1,120 figure is the Starwave orders tape. This section
answers on **ReportHistory-901018**, which carries an order of magnitude more evidence — **37,047
grid pendings, of which 24,604 are deployment-burst legs and 12,443 are not** — and the answer is
**yes, at 11,352 of 11,352 = 100.00%, with zero residual.** Not one grid pending in 38 days of tape
was relocated off its level's original lattice price.

The remaining 1,091 of the 12,443 were never re-arms at all: they are the legs of ten deployment
bursts that the *forensic cycle segmenter* merged into an already-open cycle, so they arrived in the
re-arm pool wearing the wrong cycle's lattice. Establishing that took three corrections to my own
instrument, and §2.6.3 states the whole chain in the open — three of the intermediate figures still
look quotable and all three are wrong.

#### 2.6.1 The code path — and why a relocation is unreachable, not merely unobserved

`RearmOneMissingLevel()` (`StraddleEngine.mqh:2278-2371`, called from the `CYCLE_RUNNING` arm at
`3779`) walks `index` from 0 to `levels_per_side` and re-places
**`m_buy_levels[index].target_price`** / **`m_sell_levels[index].target_price`** — the price computed
once by `StartCycle()` from the cycle anchor and never recomputed. The buy branch (`2282-2323`)
orders its gates `RearmEligible` → `RearmDelayElapsed` → tier/rescue volume →
`PendingPriceIsValid(true, target_price)` → `ExposureAllowsRearm` → `PlaceLevel` → `return`; the sell
branch mirrors it at `2332-2369`. One level per pass, so a burst of re-arms is paced by the timer,
not emitted synchronously.

The parity rationale is in-source at `2296-2310` (buy) and `2346-2348` (sell), and the operative
sentence is the negative one: *"Never re-anchor to market; wait for price to return if currently
invalid."* That is enforced structurally, not by convention:

```cpp
   bool PendingPriceIsValid(const bool is_buy,const double price) const     // 1529-1540
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
```

`PendingPriceIsValid()` is a **pure predicate on a price it is handed**. It has no return path that
yields a *different* price, and the two call sites (`2311`, `2349`) consume it as
`if(!PendingPriceIsValid(...)) continue;`. So the only two outcomes at a re-arm site are *place at
`target_price`* or *defer this level to a later pass*. This makes a sharper prediction than "≈100%
exact": **delta == 0.00 for every re-arm, forever, with a deferral tail instead of a relocation
tail** — which is exactly the shape the tape shows below.

`RearmEligible()` (`2267-2276`) is the flag surface, and it carries the orphan-leak fork of §3.2:

```cpp
      if(level_state.has_pending ||
         level_state.trend_rescue_replacement ||
         level_state.duplicate_identity)
         return false;
      if(OrphanLeakActive())
         return true;
      return(level_state.rearm_requested && !level_state.has_position);
```

Under Target-parity flags `OrphanLeakActive()` short-circuits to `true`, so a level re-arms whenever
it holds no pending — the `!has_position` gate that would have suppressed 901018's orphan population
is bypassed by design (§3.2). Supporting members: `PlaceLevel()` `1548-1603`, `RearmDelayElapsed()`
`1613-1617`, `CurrentServerMs()` `1605-1611`, `ScheduleLevelRearm()` `1619+`,
`ExposureAllowsRearm()` `2688`, and the `CYCLE_RUNNING`-only note at `2237`.

#### 2.6.2 The measurement, and the tally that closes it

`tmp/a901_rearm.py` partitions every grid pending in 901018 into deployment-burst legs (excluded by
construction — a burst leg *defines* a slot price, it cannot test it) and everything else. Each
candidate is then scored against the price its own `(cycle, side, level)` slot was deployed at:

```
PART 1 -- re-arm census (grid pendings that are not deployment-burst orders)
    grid pendings 37047   burst 24604   re-arms 12443
    era             cycles   re-arms  per cycle
    HISTORICAL_50       96      3347      34.86
    HISTORICAL_60       74      6899      93.23
    AGGRESSIVE_30        2        29      14.50
    LOW_RISK_30          1        18      18.00
    STARWAVE_30        102      2150      21.08
```

```
FINAL TALLY -- every grid pending that is not a detected deployment order
    candidate re-arms                    12443
      orders belonging to a missed deployment (part 10)  -1091
      true re-arms                                       11352
        exact return to the burst slot                   11058 = 97.41%
        exact return to a slot the segmenter trimmed     294 = 2.59%
        exact-price returns, total                       11352 = 100.00%
        neither -- a genuine relocation would live here   0
```

The last line is the whole vector: **the bucket where a genuine relocation would have to appear is
empty.** The 294 in the second bucket are not a weaker class of evidence — they are exact returns to
a slot the segmenter *trimmed out of its own slot table*, verified against the cycle's own
`(anchor, step)` extended to any level:

```
PART 11 -- residual: does it sit on the cycle's OWN lattice, extended?
    orders not on a fresh lattice: 294
      on the cycle's own extended lattice : 294 = 100.00%
      on neither                          : 0
      |delta| p50 0.000  p95 0.000  max 0.000
```

**Max |delta| 0.000 across all 294.** Zero-parameter test: the anchor and step come from the cycle,
the level from the order's own comment, and nothing is fitted.

#### 2.6.3 The correction chain — 90.89% → 98.85% → 99.79% → 100.00%

The first pass scored every candidate against its cycle's recorded burst slot and reported this:

```
PART 2 -- does every re-arm return to the burst lattice price?
    era             scored   exact   exact%  <=1/2 tick   moved
    HISTORICAL_50     3343    2817    84.27           0     526
    HISTORICAL_60     6626    6114    92.27           0     512
    AGGRESSIVE_30       29      29   100.00           0       0
    LOW_RISK_30         18      18   100.00           0       0
    STARWAVE_30       2150    2080    96.74           0      70
    ALL              12166   11058    90.89           0    1108
    re-arms with no burst slot for their (side,level): 277
    first 10 moved re-arms:
      cycle   7 B1   #20178637 price   4040.46 lattice   4066.24 delta -25.78
      cycle   7 S1   #20178638 price   4038.60 lattice   4063.60 delta -25.00
      cycle   7 B2   #20178639 price   4041.39 lattice   4067.56 delta -26.17
```

Note the `<=1/2 tick` column: **0 in every era.** Prices are either exact or off by whole points —
there is no smear of near-misses anywhere in the tape, which already rules out rounding drift and
points at a *categorical* misattribution instead. The first ten offenders confirm it: cycle 7's B1,
S1, B2, S2… all shifted by ≈ −25 points in one monotone block. A relocation-to-market law cannot
produce a **coherent second lattice**; only a second *deployment* can.

PART 8 tested that directly by clustering the 1,108 offenders in time and fitting `(anchor, step)`
to each cluster — 2 free parameters against up to 120 observations:

```
PART 8 -- are the moved re-arms isolated relocations or whole redeployments?
    moved re-arms 1108 in 67 time clusters
      clusters with >=8 distinct (side,level) keys : 14  covering 979 orders
      clusters with  <8 distinct keys              : 53  covering 129 orders

     cycle  keys  orders   span s  own anchor  own step  cycle anchor  cycle step
       113   120     120     68.6     4174.04      0.63       4176.75        0.43
       127   120     120     15.1     4113.16      0.47       4124.76        0.46
       167   115     115     12.6     4084.51      0.57       4105.02        0.51
         7   100     100     10.7     4039.53      0.93       4064.92        1.32
        29   100     100     10.0     4034.25      0.94       4034.84        1.46
        51   100     100      9.9     4028.10      1.18       4035.42        0.96
        90   100     100     10.1     4072.77      0.98       4065.18        1.05
        93    99      99     10.2     4115.13      1.10       4119.67        1.10
       176    60      60      6.7     4098.86      1.37       4082.61        1.36
       169    24      24      4.9     4074.73      0.49       4112.18        0.57
```

**120 distinct `(side,level)` keys placed inside 68.6 seconds is a deployment, not a re-arm
sequence.** A re-arm fires one level per timer pass when a position exits; 120 keys in one span, with
a coherent step of their own that disagrees with the cycle's recorded step, is the signature of
`StartCycle()` running again. PART 10 then held each such group to two tests the fit does not see —
per-order residual, and whether the fitted anchor sits at the *market* when the cluster began (V1's
deployment law):

```
PART 10 -- final accounting: is every non-exact order a missed deployment?
     cycle era             orders  keys    step     anchor  cyc step  cyc anch  mkt@start    |d|  resid p95  in tick
         7 HISTORICAL_50      101   100    0.93    4039.53      1.32   4064.92    4040.22   0.69      0.000  101/101
        29 HISTORICAL_50      101   100    0.94    4034.25      1.46   4034.84    4033.98   0.27      0.000  101/101
        51 HISTORICAL_50      111   100    1.18    4028.10      0.96   4035.42    4028.03   0.07      0.000  111/111
        90 HISTORICAL_50      114   100    0.98    4072.77      1.05   4065.18    4073.12   0.35      0.000  114/114
        93 HISTORICAL_50      100   100    1.10    4115.13      1.10   4119.67    4113.43   1.70      0.000  100/100
       113 HISTORICAL_60      156   120    0.63    4174.04      0.43   4176.75    4174.27   0.23      0.000  156/156
       119 HISTORICAL_60       99    81    0.45    4162.37      0.45   4162.37    4162.21   0.16      0.000   99/99
       127 HISTORICAL_60      199   120    0.47    4113.16      0.46   4124.76    4113.03   0.13      0.000  199/199
       152 HISTORICAL_60       85    68    0.47    4095.46      0.47   4095.46    4097.89   2.43      0.000   85/85
       167 HISTORICAL_60      115   115    0.57    4084.51      0.51   4105.02    4085.87   1.36      0.000  115/115
       169 HISTORICAL_60       28    25    0.49    4074.73      0.57   4112.18    4111.60  36.87     37.530   24/28
       176 STARWAVE_30         70    60    1.37    4098.86      1.36   4082.61    4097.44   1.42      0.000   70/70

    unexplained orders 1385   of which on a fresh lattice 1275 = 92.06%
    cycles carrying a missed deployment: 10 -> [7, 29, 51, 90, 93, 113, 127, 167, 169, 176]
```

Every fitted cluster has **`resid p95 = 0.000`** — each order sits on the fitted lattice to the cent —
and every fitted anchor sits within **0.07–2.43** of the market when the cluster started, exactly as
`CalculateAnchor()` requires. Cycles 119 and 152 are the clearest cases: their fitted anchor equals
the cycle's *recorded* anchor to the cent (4162.37 = 4162.37, 4095.46 = 4095.46) while their levels
run past the recorded `levels_per_side` — the segmenter kept the right anchor but **truncated the
slot table**, so these are same-lattice re-arms at levels the table forgot, which is why PART 11
scores them at 294/294.

Cycle 169's row is the one apparent exception (`|d| 36.87`, `resid p95 37.530`, `24/28` in tick), and
it is a **stale-proxy artifact I initially mistook for a coincidental fit** — see §2.6.5.

The chain of figures, stated openly:

| Figure | What it was | Why it is wrong |
|---|---|---|
| **90.89%** | raw PART 2, all 12,166 scored against recorded burst slots | counts 1,091 second-deployment legs as moved re-arms |
| **98.85%** | PART 8's `11058/11187` after removing the 14 lattice-like clusters | still counts the 294 trimmed-slot returns and 277 no-slot orders as unexplained |
| **99.79%** | after PART 11, with cycle 169 excluded on a false premise | the exclusion was refuted by the tape (§2.6.5) |
| **100.00%** | 11,352 of 11,352 true re-arms | — |

> **Do not quote 90.89%, 98.85%, or 99.79% as the V6 exact-price rate.** All three are stages of a
> segmentation artifact in `tools/forensics/dataset.py::_burst_clusters()`, not properties of the
> Target EA. The rate is **100.00%**. The superseded in-source figure "1,797 mid-cycle re-arms …
> 99.4%" (a Starwave-tape measurement, now replaced at `StraddleEngine.mqh:2296-2310`) must not be
> quoted either.

#### 2.6.4 Per-level memory state — byte-stable across up to 19 repeats

V6 asks about *memory*, not only about a single return. A level can be re-armed many times inside one
cycle: fill, exit, re-arm, fill again. If `SLevelState.target_price` were ever recomputed — from the
current market, from the last fill, from a re-derived anchor — repeated re-arms of the *same* slot
would disagree with each other. Scored on the true re-arm population:

```
    per-level memory, re-scored on the true re-arm population:
      slots re-armed at least twice: 2490   re-arms in them 9810
      deepest repeat count         : 19
      slots whose repeats disagree by more than half a tick: 0
      max intra-slot price spread  : 0.0000
```

**2,490 slots, 9,810 re-arms, up to 19 repeats of a single slot, zero disagreements, max intra-slot
spread 0.0000.** Every repeated re-arm of one `(cycle, side, level)` went to the identical price to
the cent. That is the direct observable of `target_price` being written once by `StartCycle()` and
read-only thereafter.

The raw version of this table, before the segmentation correction, read **286 slots disagreeing, max
intra-slot spread 38.4100**. Those two numbers are the *same* artifact viewed from a per-slot angle:
a swallowed deployment re-uses every `(side, level)` key at a **different anchor**, so its legs land
in the same slot bucket as the cycle's genuine re-arms and inflate the spread by roughly the anchor
gap (cycle 7: 4064.92 − 4039.53 ≈ 25 points; the 38.41 maximum is cycle 169's 4112.18 − 4074.73 plus
level spread).

> **Do not quote "286 slots disagree" or "max spread 38.4100" as evidence of memory instability.** On
> the true re-arm population both are **0** and **0.0000**.

#### 2.6.5 Self-correction: cycle 169 was excluded on a false premise

An earlier draft of PART 11 carried `if cycle_index == 169: continue  # operator flatten -- scored
separately`. The reasoning was superficially sound: cycle 169's 24 orders fit a lattice at anchor
**4074.73**, while the 120 s quote proxy read **4111.60** at the cluster's start — and a *buy stop* 37
points **below** market is impossible to place, so the fit looked like a numerical coincidence rather
than a real deployment. That exclusion is what produced the 99.79% stage.

`tmp/a901_c169.py` printed the raw tape and refuted the premise outright:

```
deals 2026-07-13 10:25..10:55: 0

nearest deal BEFORE 2026-07-13 10:39:29: 2026-07-13 05:29:54.075000 price 4062.28  gap 18574.9 s
nearest deal AFTER  2026-07-13 10:39:29: 2026-07-13 11:02:56.403000 price 4074.73  gap 1407.4 s
```

There is **no deal at all** between 10:25 and 10:55 on 2026-07-13. The nearest prior deal is
**18,574.9 s stale** — 5.2 hours — so the "market" the proxy reported was a fossil, and the nearest
deal *after* the cluster prices **4074.73: the fitted anchor, to the cent.** The fit was the market.
The independent detector then found the same burst on its own terms — `2026-07-13 10:39:29.363`,
anchor **4074.73**, step **0.49**, N 13, 24 legs, density 0.92 — an **aborted deployment**, cancelled
23 minutes later when the next full N=30 burst went out at `11:02:45.175` (anchor 4075.43, step 0.68,
60 legs). Cycle 169 is therefore scored like every other fitted cycle, and the residual line drops to
**0**.

This is the **second** time in V6 that a 120 s market-proxy reading produced a wrong inference. The
proxy caveat is load-bearing: on this tape the gap between consecutive deals can exceed five hours,
so `|anchor − proxy|` is only evidence when the proxy is fresh. PART 10's `mkt@start` column must be
read with that caveat attached — which is precisely why the column is printed alongside `resid p95`
rather than instead of it.

#### 2.6.6 Cross-check against the independent detector, and the segmenter defect measured exactly

Everything above rests on one claim: that the ten fitted clusters are real deployments. That claim
must not be taken from the same instrument that needs it. `tmp/a901_v4578.py::build_deployments()` is
an **independent** cut — it finds bursts from order density plus `k`-agnostic geometry, with no
knowledge of `build_cycles()`' boundaries, and it is the instrument that produced the 285-deployment
population V1, V2 and V9 are scored on. `tmp/a901_xcheck.py` matches on `(anchor, step)` geometry
rather than timestamps, so this probe's cluster boundaries are never imported into the test:

```
independently-detected bursts matching each suspected missed deployment:
    cycle 7     anchor   4039.53 step 0.93  ->  2026-06-24 13:26:31.197  anchor   4039.53 step 0.93 N  50 legs 100 density 1.00
    cycle 29    anchor   4034.25 step 0.94  ->  2026-06-25 22:02:07.345  anchor   4034.25 step 0.94 N  50 legs 100 density 1.00
    cycle 51    anchor   4028.10 step 1.18  ->  2026-06-29 16:55:46.455  anchor   4028.10 step 1.18 N  50 legs 100 density 1.00
    cycle 90    anchor   4072.77 step 0.98  ->  2026-07-02 11:06:40.576  anchor   4072.77 step 0.98 N  50 legs 100 density 1.00
    cycle 93    anchor   4115.13 step 1.10  ->  2026-07-02 14:33:30.170  anchor   4115.13 step 1.10 N  50 legs 100 density 1.00
    cycle 113   anchor   4174.04 step 0.63  ->  2026-07-06 04:42:18.139  anchor   4174.04 step 0.63 N  60 legs 119 density 0.99
    cycle 127   anchor   4113.16 step 0.47  ->  2026-07-08 02:58:47.153  anchor   4113.16 step 0.47 N  60 legs 119 density 0.99
    cycle 167   anchor   4084.51 step 0.57  ->  2026-07-10 16:33:04.253  anchor   4084.51 step 0.57 N  60 legs 115 density 0.96
    cycle 169   anchor   4074.73 step 0.49  ->  2026-07-13 10:39:29.363  anchor   4074.73 step 0.49 N  13 legs  24 density 0.92
    cycle 176   anchor   4098.86 step 1.37  ->  2026-07-14 14:33:22.122  anchor   4098.86 step 1.37 N  30 legs  60 density 1.00
    cycle 119*  anchor   4162.37 step 0.45  ->  2026-07-07 14:07:03.905  anchor   4162.37 step 0.45 N  60 legs 119 density 0.99
    cycle 152*  anchor   4095.46 step 0.47  ->  2026-07-09 08:00:23.179  anchor   4095.46 step 0.47 N  60 legs 119 density 0.99
```

**All twelve geometries reproduce to the cent in an instrument that never saw this probe's
clusters.** The two starred rows behave exactly as predicted for a *truncated* slot table rather than
a merged deployment: their re-arms fit the **parent** cycle's own geometry, and the independent cut
shows **one** burst there, not two.

The defect itself is then measured, not inferred by arithmetic:

```
independent bursts vs detected cycles
    detected cycles 275   independent bursts 285
    bursts with no containing cycle: 0
    cycles containing >1 burst     : 15   swallowed bursts 15
    cycles containing no burst at all: 5
```

275 − 5 = **270** cycles carrying ≥1 burst; 270 + 15 = **285**, with **0 homeless bursts**. Exact, and
both directions of the defect are visible at once: 15 merges *and* 5 cycles with no burst at all.

> The earlier bookkeeping `275 + 10 = 285` (and `275 + 11 = 286`) must **not** be restated as an
> accounting identity — the two sides count different things and the sum matching was a coincidence of
> this probe's reach. `tmp/a901_rearm.py` now prints a pointer to the measured census instead.

**15 swallowed bursts vs 10 fitted missed deployments — resolved by measurement, not narrative.** The
census finds 15 merges while PART 10 fits only 10. I did not argue the gap away; I counted where the
swallowed bursts' legs went:

```
legs of each swallowed burst: burst order (never a candidate) vs re-arm candidate
    cycle   0 burst 2026-06-23 20:47:08.133 legs 100  filed-as-burst 100  candidates   0  other   0
    cycle   7 burst 2026-06-24 13:39:08.352 legs 100  filed-as-burst 100  candidates   0  other   0
    ...  all 15 rows identical in shape ...
    cycle 260 burst 2026-07-30 00:05:28.184 legs  60  filed-as-burst  60  candidates   0  other   0
```

**All 1,434 legs** (100×6 + 119×4 + 118 + 60×4) were already filed by the segmenter under some cycle's
`burst_orders`, and PART 1 excludes burst ids — so **not one of them was ever a re-arm candidate.** The
two counts are **disjoint views of one defect**: the 15 are cases where the segmenter kept the *later*
burst as the slot table, the 10 are cases where it kept one burst and dumped the other's legs into the
re-arm pool. The FINAL TALLY is unaffected either way.

A corollary worth recording, because it contaminates any measurement keyed on per-cycle geometry:
cycle 7 contains bursts at `13:26:31.197` (anchor 4039.53 / step 0.93) and `13:39:08.352` (anchor
4049.79 / step 0.95), yet `build_cycles()` recorded cycle 7's geometry as anchor **4064.92** / step
**1.32** — matching **neither**. The per-cycle `(anchor, step)` fit is a **blend** when two lattices
fall in one window. Every metric in this audit that keys on `cycle.anchor`, `cycle.step` or
`cycle.levels_per_side` inherits that, which is why V1/V2/V9 are scored on the independent
285-deployment cut and not on `build_cycles()`. The defect is catalogued in §5 as a **forensic-tool**
defect: `_burst_clusters()` (`tools/forensics/dataset.py:284-292`) trims a run at the first repeated
`(side,level)` key, and `build_cycles()` therefore (a) merges back-to-back deployments — 15 measured
cases, (b) truncates slot tables — cycles 119 and 152 recorded N=30 against 119-leg bursts, (c) leaves
5 cycles with no burst at all, and (d) blends per-cycle geometry. **No EA code is implicated.**

#### 2.6.7 The four remaining sub-questions

**(a) Re-anchoring, tested positively rather than by absence.** "Never re-anchored" is a negative
claim, so I also fitted the *rival* law directly — is a re-arm placed at `market ± level*step`?

```
PART 4 -- re-anchoring hypothesis: is a re-arm placed at market +/- level*step?
    re-arms with a quote proxy within 120 s: 12120
    |price - market|/step == level (+/-0.25): 113 = 0.93%
    signed distance from market in steps: min -10.14  p05 -2.00  p50 -0.01  p95 +26.65  max +90.88
    re-arms sitting MORE than 5 steps away from market: 1486 = 12.26%
```

**0.93%** is below what coincidence alone produces for a ±0.25-step tolerance band, and the
distribution kills the hypothesis outright: **12.26% of re-arms sit more than five steps from market**,
with a p95 of **+26.65 steps** and a maximum of **+90.88** — sell stops re-armed up to ~35 steps away
from the market on the original lattice. A market-relative law cannot place an order 26 steps away and
call it level 3. The 120 s proxy caveat of §2.6.5 applies to the p50 of −0.01 (which is the *shape* of a
lattice straddling a market, not a re-anchoring signature) but not to the 12.26% tail, which is far
larger than any plausible proxy error.

**(b) Memory never survives a restart.**

```
PART 7 -- does memory ever survive a restart (stale previous-cycle lattice)?
    moved re-arms that match the PREVIOUS cycle's lattice price: 0 of 1108
```

**0 of 1,108.** No re-arm anywhere in the tape lands on the *previous* cycle's lattice, so `StartCycle()`
fully rewrites the level tables and no stale `target_price` leaks across a restart. This is the
complement of the §2.6.4 result: memory is immutable *within* a cycle and completely discarded *between*
cycles.

**(c) Volume memory rides with price memory.**

```
PART 5 -- does a re-arm carry the slot's burst volume?
    matches burst volume 12020 = 98.80%   differs 146   no slot 277
      cycle 171 S11  #20266436 vol 0.4 burst 0.41
      cycle 171 S12  #20266437 vol 0.4 burst 0.41
```

**12,020 = 98.80%** carry the slot's deployed volume, and **all 146 exceptions are in cycle 171** — the
operator-interleaved cycle already isolated in §2.5.3 — at 0.4 against a deployed 0.41. A hand-typed
0.4 where the ladder says 0.41 is an operator signature, not a tier-schedule divergence; V9's tier
verification is untouched at 25,447/25,447.

**(d) What state the slot was in, and how long it waited.** The re-arm trigger and its latency are the
mechanism behind the counts above:

```
PART 6 -- what state was the slot in when it re-armed?
    era                after_basket    after_closeby       after_stop      no_fill_yet
    HISTORICAL_50                51                0             2918              378
    HISTORICAL_60               117                4             6411              367
    AGGRESSIVE_30                 0                0               17               12
    LOW_RISK_30                   0                0               18                0
    STARWAVE_30                   6                0             1909              235

    era                 n       p05       p50       p95   (seconds from prior exit to re-arm)
    HISTORICAL_50    2969       5.0     160.7    3237.1
    HISTORICAL_60    6532       7.3     126.1    2601.7
    AGGRESSIVE_30      17      55.3     314.4     882.3
    LOW_RISK_30        18      10.3     141.0     974.0
    STARWAVE_30      1915      11.5     294.9    8697.5
```

**Stop-out is the dominant trigger in every era** (2,918 / 6,411 / 17 / 18 / 1,909), which is the
expected consequence of V4's trailing ratchet: a level fills, the ratchet locks it, price retraces, the
stop takes it, the level re-arms. The `no_fill_yet` column (378 / 367 / 12 / 0 / 235) is the **deferral
tail** predicted structurally in §2.6.1 — a level whose lattice price was invalid at deployment time and
which was therefore placed on a later pass, at the *same* price. The p05 latencies (5.0–55.3 s) show
re-arms are never instantaneous, consistent with `RearmDelayElapsed()` plus one-level-per-pass pacing,
and the long p95 tails are simply how long price takes to come back to a distant level.

**(e) The 277 no-slot orders, for completeness.**

```
PART 9 -- re-arms whose (side,level) has no slot in their cycle's burst
    total 277   level beyond the burst's levels_per_side 125   inside the burst range 152
    top cycles: 119 (95, HISTORICAL_60, N=30), 152 (71, HISTORICAL_60, N=30), 114 (12, HISTORICAL_60, N=60), ...
    of those, inside a missed-redeployment cluster: 0
```

**125 of the 277 name a level beyond the recorded `levels_per_side`** — impossible for an EA that only
ever iterates `index < m_profile.levels_per_side`, and therefore direct proof of a truncated slot table
rather than an EA behaviour. Cycles 119 and 152 alone account for 166 of them, and both are the starred
rows of §2.6.6 whose recorded anchor matches their bursts' anchor exactly. All 277 are resolved by PART
11's own-lattice test.

#### 2.6.8 What was changed in the source

The measurement above replaced a stale provenance figure in the parity rationale. The buy-side comment
at `StraddleEngine.mqh:2296-2310` previously cited "1,797 mid-cycle re-arms … 99.4%" — a Starwave-tape
number superseded by the 901018 result — and now records the measured accounting, the per-slot memory
result, the 0.93% re-anchoring refutation and the ~35-step observation. Before editing I grepped
`tests/` and `mql5/` for the comment's substrings (nothing asserts on them) and confirmed no test pins
the standalone hash (`tools/bundle_standalone.py:119` computes it; nothing asserts it). Both standalones
were regenerated and the contract suite re-run: at that point `mql5/ProfitBricks2K.mq5` and
`mql5/ProfitBricks2K_AllInOne.mq5` were byte-identical at **234,219 bytes / 5,754 lines /
`2d2fe9bb0d272406`**, and `tests/test_mql5_contract.py` was **84 passed**. (Finding V12-A's later
comment fix moved both figures; §2.13 carries the current ones.) No behavioural line changed —
this vector required no code fix, because the structural argument of §2.6.1 was already satisfied.

**V6 verdict.** Both halves of the directive's question are **identical**, with no divergence to fix.
Of 12,443 grid pendings that are not deployment-burst legs, 1,091 belong to ten deployment bursts the
forensic cycle segmenter merged into an open cycle, and **all 11,352 true re-arms return to their
level's exact original lattice price — 11,058 to the cycle's recorded burst slot and 294 to the same
lattice past a truncated slot table — for 11,352 of 11,352 = 100.00%, with the residual bucket where a
relocation would have to appear standing at zero.** Per-level memory is byte-stable: 2,490 slots
re-armed at least twice, 9,810 re-arms among them, up to 19 repeats of a single slot, **0 disagreements
and max intra-slot spread 0.0000**. The rival re-anchoring law is refuted positively at **0.93%**, with
12.26% of re-arms more than five steps from market. Memory never survives a restart (**0 of 1,108**),
and volume memory rides with price memory at **98.80%**, all 146 exceptions being operator writes in
cycle 171. In the replica the property is structural rather than statistical: `PendingPriceIsValid()`
(`1529-1540`) is a pure predicate whose only alternative to placing `target_price` is `continue`, so the
deferral tail observed in PART 6's `no_fill_yet` column (992 orders) is the only tail the code can
produce. **V6: 100.00%.**

---

### 2.7 V7 — Basket money exit evaluator — 100.00% on the predicate, the gate and the reset

The directive asks three separable questions: *"strictly `(m_cycle_realized + floating) >= target`?
Gated on `open_positions>0`? `m_cycle_realized` reset to $0.00 per cycle?"* All three are answered
**yes** below, each by a positive proof rather than by absence of contradiction. A fourth question the
directive does not ask — *what is the target's numeric value in the 901018 final regime* — is the only
part of this vector the tape cannot settle, and §2.7.7 shows why that question was mis-posed: the value
under test belongs to a different profile, fitted on a different account.

Probe: `tmp/a901_v7.py`, fourteen parts, `tmp/out_v7.txt` (319 lines, exit 0). Census
`deployments=285 terminal=282 interim=306 silent=3 positions=17632 balance_points=35446 cash_events=4`.

#### 2.7.1 The predicate is literal, and both of its terms use one money definition

`BasketEvaluator.mqh` is 37 lines and contains no arithmetic beyond the sum:

```cpp
      snapshot.net=realized+floating;
      snapshot.target=target;
      snapshot.triggered=(
         has_traded &&
         open_positions > 0 &&
         target>0.0 &&
         snapshot.net>=target
      );
```

There is no scaling, no per-leg weighting, no drawdown term and no time term. The two inputs are
supplied by `CheckCycleTargets()` (`StraddleEngine.mqh:3431-3537`), called from the timer (`:3428`) and
from both live states, `CYCLE_DEPLOYING` (`:3771`) and `CYCLE_RUNNING` (`:3780`) — so the predicate is
evaluated on every tick of a live cycle, including while the lattice is still being laid down.

The money definition is the same on both sides of the `>=`, which is what makes the tape measurable at
all. Floating sums `POSITION_PROFIT + POSITION_SWAP` — `TrackedFloatingProfit()` at
`StraddleEngine.mqh:413-415` and `OwnedFloatingProfit()` at `:2379` — and realized accumulates
`deal_profit + deal_swap + deal_commission + deal_fee` (`:3685-3691`). `CycleFloatingProfit()`
(`:432-437`) and `CyclePositionCount()` (`:425-430`) delegate to the `Owned*` pair unless
`OrphanLeakActive()`, so the leak flag changes *which* positions are summed, never *what* is summed per
position. The forensic instrument therefore uses `net = profit + commission + swap` per position, and
PART 0 quantifies what a profit-only instrument would have cost: commission is identically zero on all
17,632 positions, swap is nonzero on 341, the tape's `18,203.37 + (−290.08) = 17,913.29` reproduces the
report footer's Net **exactly**, and the per-era median delta between the two instruments is **0.00 in
all five eras** — only the tails move (p05 −1.89 / −5.54 / −7.47). The instrument choice is immaterial
at every statistic this section quotes.

#### 2.7.2 The money exit is the *only* exit, so every sweep on the tape is a V7 observation

`SafetyTriggered()` (`:2726-2759`) returns false unconditionally when `!m_runtime.safety_enabled`, and
safety is off by construction on every path into the binary: `#define STR_SAFETY_ENABLED_DEFAULT false`
(`StraddleReplicaApp.mqh:8`), `input bool SafetyEnabled` (`:61`), and all four entry points re-define it
false — `ProfitBricks.mq5:14`, `ProfitBricks2K.mq5:14`, `ProfitBricks2K_AllInOne.mq5:14`,
`StraddleReplicaReal.mq5:12`. There is no drawdown cutoff, no equity stop and no time-based flatten.
Consequently every one of the 282 terminal liquidations on the 901018 tape is an observation of this
predicate firing, which is what licenses the threshold estimation in §2.7.6 — and also what makes the
absence of any *other* exit signature a positive parity result rather than an untested path.

#### 2.7.3 The `open_positions>0` gate, proved positively over the *global* open set

An ungated evaluator is not a subtle divergence: once a cycle has banked more than its target, an
ungated `net>=target` fires `BeginClose()` at the first instant the basket is empty, and the cycle ends
there. So the gate is falsifiable by a single counterexample of the opposite kind — an instant inside a
live cycle where the open count returns to **zero** while banked money already exceeds that cycle's
target, and the cycle nevertheless **runs on**. PART 8 searches for exactly that, with the open count
taken over **every position on the tape** rather than only cycle-attributed ones:

```
  instants where the account held ZERO open positions: 288
  era             proof-instants (global zero + banked>=target + ran on)
  HISTORICAL_50        2
  AGGRESSIVE_30        1
  STARWAVE_30          5
      HISTORICAL_50  cycle#  7 2026-06-24 13:17:21.425000  banked    366.58 >=    14.16
      HISTORICAL_50  cycle#  7 2026-06-24 13:20:56.895000  banked    367.57 >=    14.16
      AGGRESSIVE_30  cycle#179 2026-07-13 12:28:54.004000  banked    149.90 >=    22.01
      STARWAVE_30    cycle#194 2026-07-15 14:39:22.533000  banked     38.74 >=    26.50
      STARWAVE_30    cycle#209 2026-07-17 15:44:08.906000  banked     30.91 >=    26.50
      STARWAVE_30    cycle#217 2026-07-20 04:46:09.258000  banked     28.74 >=    26.50
      STARWAVE_30    cycle#248 2026-07-23 15:57:18.342000  banked     36.78 >=    26.50
      STARWAVE_30    cycle#249 2026-07-24 07:18:18.818000  banked     55.65 >=    26.50
```

**Eight instants across seven cycles where an ungated evaluator would have ended the cycle and the
Target did not.** PART 5 found the same eight over the cycle-attributed open set; PART 8 reproduces them
over the global set, which closes PART 5's one weakness — that an orphan from a prior cycle could have
kept the true count above zero. Both readings agree, so the gate is not an artifact of position
attribution. The replica's gate is the `open_positions > 0` conjunct quoted in §2.7.1, and it was added
for this evidence (commit `3a4a86c`).

#### 2.7.4 The per-cycle reset to $0.00, proved by contradiction

A *cumulative* accumulator has two mechanical signatures on a winning tape. Once the running total
passes the smallest configured target, (a) every later cycle must trip on its **first** fill, so every
later terminal sweep is a **one-leg** sweep, and (b) the banked series must be **monotone
non-decreasing**. PART 6 measures both:

```
  terminal sweeps=282  cumulative net over the tape=18211.00
  the running total first exceeds the SMALLEST configured target ($6.50, STARWAVE_20) at sweep #0
  after that sweep: 281 terminal sweeps, of which 240 are MULTI-LEG and 25 banked a LOSS
  cycles that took more than one fill: 283/284
  banked series strict decreases: 142/281
```

The running total passes the smallest target at **sweep #0** — i.e. immediately — after which
**240 of 281** terminal sweeps are multi-leg, **25 banked a loss**, **283 of 284** cycles took more than
one fill, and the banked series **strictly decreases 142 times**. A cumulative accumulator can never
decrease in a winning regime, so each of those 142 decreases is independently sufficient. The replica
resets at `StraddleEngine.mqh:1865` and `:2027` and in the constructor at `:3130`; `m_cycle_realized` is
declared at `:33`.

#### 2.7.5 The target law is era-scoped, and the tape reads *flat money* in every populated era

`ProfileCatalog.mqh` carries two mutually exclusive target forms per profile: a balance percentage
(`cycle_target_balance_pct`) and a money amount (`cycle_target_money`), defaulted at `:29-30` to `0.18`
and `0.0`. `HISTORICAL_50` sets `0.63` (`:71`), `HISTORICAL_60` sets `0.42` (`:143`), `AGGRESSIVE_30`
(`:173`) and `LOW_RISK_30` (`:215`) inherit the `0.18` default, and the modern profiles set money
instead: `JUNE_2K` `$30.0` (`:247`), `LATEST_30` `$30.0` (`:315`), `STARWAVE_30` `$26.5` (`:478`),
`STARWAVE_20` `$6.5` (`:512`). `cycle_target_balance_pct=0.18` is therefore **not** a dead branch — two
populated eras run on it.

PART 3 tests the percentage form the obvious way, and the obvious way fails. The implied percentages do
match the configured ones almost exactly — `0.635` vs `0.63`, `0.425` vs `0.42`, `0.178` vs `0.18` — but
the match is **arithmetically forced**: at the final regime's mean balance of ≈$15,000 a flat $26.50 *is*
0.1767%, so any correctly-fitted flat number reproduces its era's percentage and vice versa. Worse, all
three Theil–Sen slopes of banked money against account balance are **negative** (−0.001607, −0.003258,
−0.001294 $/$, over 4,671 / 1,918 / 3,648 pairs), contradicting a percentage law *and* a flat law alike,
because balance is nearly monotone in time on this tape and the eras' volatility regimes are not.

PART 7 removes the arithmetic circularity by binning each era into balance terciles and asking how the
banked median *moves* when the balance moves inside a single configuration:

```
  -- HISTORICAL_50  configured 0.63%
      bin  n   balance p50    money: minpos    p10    p25    p50     implied%: p10    p25    p50
        1  33      3228.49         12.07  17.53  21.56  26.10           0.514  0.635  0.906
        2  33      4195.91          7.74   7.74  21.94  24.83           0.162  0.563  0.612
        3  34      5397.36          4.71   6.38  15.08  24.60           0.099  0.308  0.447
      balance x1.67 across bins;  money p50 x0.94  (pct law predicts x1.67, flat law predicts x1.00)
  -- HISTORICAL_60  configured 0.42%
      balance x1.18 across bins;  money p50 x0.97  (pct predicts x1.18, flat x1.00)
  -- STARWAVE_30  configured $26.50
      balance x1.20 across bins;  money p50 x0.91  (pct predicts x1.20, flat x1.00)
```

**The banked median is balance-invariant in all three populated eras** — ratios ×0.94, ×0.97, ×0.91
against percentage-law predictions of ×1.67, ×1.18, ×1.20 and a flat-law prediction of ×1.00. In
`HISTORICAL_50` the implied percentage *halves* (0.906 → 0.612 → 0.447) across a ×1.67 balance swing
inside one configuration. This is the flat-money signature, and it appears in the two eras the catalog
configures as **percentages**.

That is a finding worth stating precisely, because it is easy to overclaim. It does **not** prove the
Target ran a money target in `HISTORICAL_50`/`HISTORICAL_60`: balance terciles are balance-ordered and
therefore time-ordered, so a volatility regime that decayed as the account grew produces the same
signature. What it does establish is that **the percentage form is not corroborated by the tape** — it
reproduces the era median only at the era's mean balance, exactly as a flat number fitted to the same
median would. The two forms are observationally equivalent within an era of this length, and the replica
inherits whichever form the catalog names, so no code change follows either way. The catalog comments at
`:65-71` and `:137-143` record the ATR step law's provenance in detail and say nothing about how `0.63`
and `0.42` were obtained, so their provenance is not documented in-source and is not asserted here.

#### 2.7.6 Eight independent threshold instruments, and what they agree on

The final regime's threshold is the one quantity in this vector the tape can only bound. Eight
instruments were built, each attacking a different error term; every one of them is biased, and the two
candidate values are only $3.50 apart. The instruments, in ascending order of how much timing error they
remove:

| instrument | what it measures | n | SW30 p50 | dominant bias |
|---|---|---|---|---|
| PART 2 | EA-net realized at sweep completion | 102 | **30.63** | up (tick overshoot), down (unwind slippage) |
| PART 4 | 1-dollar histogram of banked money | 102 | left edge `[16,17)` | none — but it does not adjudicate |
| PART 9 | single-burst sweeps only (span ≤ 2.0 s, no earlier non-SL close) | 63 | **30.63** | down (slippage inside the burst) |
| PART 10 | zero-prior-realized cycles | 2 | **28.10 / 28.28** | unrealisable — see §2.7.8 |
| PART 11 | basket re-marked at the first sweep leg's price | 98 | **31.54** | down (full spread on net exposure ≈ $15) |
| PART 11t | same, cancel→close handoff ≤ 0.5 s | 65 | **29.34** | down, reduced |
| PART 12 | two-sided mark (buys off bid, sells off ask) | 56 | **29.40** | down (marks not simultaneous) |
| PART 13 | mark at the first close of the cycle's *entire* drain | 61 | **28.57** | down (premise refuted, see §2.7.8) |
| PART 14 | mark at the **cancel-run start** — the `BeginClose()` instant | 59 | **30.91** | down, smallest |

Four further estimators carried from earlier probes on the same cut give **29.31 / 29.36 / 30.46 /
29.32**. **Every one of the twelve point estimates falls in $28.10–31.54, and none lands at $26.50.**

PART 14 is the sharpest of them and the only one that dates the decision correctly. `BeginClose()` fires,
the bulk cancel runs at ~100 ms per pending, and only then does the first close print — so every earlier
instrument marks the basket *after* the decision by the length of the cancel run. Marking at the run's
start instead moves the final era's median from 28.57 to **30.91** and cuts the fraction of sweeps
marked below $26.50 from 41.0% to **28.8%**. The latency regression confirms the mechanism and its sign:

```
  Theil-Sen d(net)/d(latency):  HISTORICAL_50 -3.141   HISTORICAL_60 -0.512   STARWAVE_30 -2.660  $/s
      (bias predicts a NEGATIVE slope, a real violation predicts ~0)
```

Negative in all three populated eras. At the final era's ~5 s cancel run that is ≈ $13 of adverse drift
between the decision and the first print — the right order of magnitude to explain the whole shortfall.
The slope's *magnitude* is confounded (longer cancel runs mean fuller lattices, which mean deeper
cycles), so it is quoted as a sign test, not as a drift estimate. **Every correction that dates the mark
earlier moves the estimate up and away from $26.50.**

What survives is a bounded, honest result: the final regime's threshold is somewhere in **$28–31** on
this tape, with the two least-biased instruments (PART 9's drift-free bursts at 30.63 and PART 14's
decision-instant mark at 30.91) sitting at **$30**, and a residual 28.8% of sweeps still marking below
$26.50 even at the best mark — which no floor law can produce and which therefore measures the
instrument's remaining error, not the EA's behaviour.

#### 2.7.7 The value under test belongs to a different profile, fitted on a different account

Before treating any of §2.7.6 as evidence against `ProfileCatalog.mqh:478`, the two candidates' in-source
provenance settles the matter — and it inverts the question. `LATEST_30`'s money target reads:

```cpp
          // Target EA parity: positive final-regime cycle nets cluster at a
          // median of $29.40 with the bulk of exits landing between $25-$33.
          config.cycle_target_money=30.0;                    // ProfileCatalog.mqh:313-315
```

`STARWAVE_30`'s reads:

```cpp
         // Basket target: epoch 2026-08-24 15:34 -> 2026-08-25 04:06 (20 cycles).
         // Banked value p25/p50/p75 = 22.24/26.29/27.82; the 3-cycle censored
         // bracket over 08-24 19:22..19:49 pins it to (26.41, 26.51].
         config.cycle_target_money=26.5;                     // ProfileCatalog.mqh:475-478
```

These are fits to **two different tapes**. `LATEST_30`'s $30.00 was fitted on the **901018 final
regime** — the exact era measured throughout §2.7.6 — and its stated median of **$29.40** is reproduced
to the cent by PART 12's independent two-sided decision-instant mark (`p50 = 29.40`, n=56), with the
whole $28–31 cluster around it. `STARWAVE_30`'s $26.50 was fitted on the **Starwave 60542 account,
2026-08-24/25, 20 cycles**, by a censored bracket that pins it to a **$0.10-wide interval** — an
identification far sharper than any median-of-slippage instrument in §2.7.6, and one this tape contains
no observations of.

So the two profiles are genuinely distinct configurations that happen to share a lattice signature:
30 levels, `anchor_divisor=3000.0`, tiers 0.01 / 0.06 / 0.15, and the same ratchet constants. That
signature is all `a901_eras.py:36` matches on, which means the forensic era label **`STARWAVE_30` is a
lot-ladder convenience name, not a money-target claim**. On the money field the 901018 final era is
`LATEST_30`. §0.1's era table keeps its label with a footnote to this subsection rather than being
relabelled, because every other measurement in this document that uses that label — V1, V2, V4, V5, V6,
V9 — depends only on the shared ladder signature and is unaffected.

**No change is made to `ProfileCatalog.mqh:478`,** and now for a positive reason rather than for want of
evidence: the $26.50 was identified on the tape it governs, by a sharper instrument than anything
available here, and the 901018 measurement is not evidence about it. The four in-source estimators
(29.31 / 29.36 / 30.46 / 29.32) must likewise never be quoted as validating a $26.50 configuration —
they were measured on the final-regime cut, which `LATEST_30` governs, and they corroborate **$30.00**.

#### 2.7.8 Instruments that failed, and how they failed

Five of the fourteen parts produced a result that refuted their own design. They are recorded here
because a probe that quietly drops its failures cannot be trusted on its successes.

**One validation first.** The mark-to-market instruments of PARTS 11–14 rest on the pricing identity
`dir × (close − open) × volume × 100 == reported profit` (XAUUSD, 1 lot = 100 oz). Measured on the whole
tape: residual `>0.005` on **13 of 17,632** rows, `p95 = p999 = 0.0000`, max 220.0000. Exact on 17,619
rows, with the maximum an isolated artifact on 13. The identity holds, so the marks are licensed.

1. **PART 7 refuted its own premise.** The probe was written on the assumption that "the floor is far
   less regime-sensitive than the median", so the tercile p25 would be the cleaner statistic. The
   opposite is true: the p25 ratios across balance terciles are 0.70 / 0.79 / 0.80 against p50 ratios of
   0.94 / 0.97 / 0.91 — the floor moved *more* than the median. Terciles are also balance-ordered and
   therefore time-ordered, so binning does not remove the time confound it was meant to remove. Only the
   p50 invariance quoted in §2.7.5 is usable; the p25 row is not.

2. **PART 10's instrument does not exist on this tape.** The sharpest possible threshold estimator is a
   cycle with zero prior realized money and one live leg: the banked value then *is* the threshold plus
   one leg's slippage. There are **zero** such cycles with fewer than seven live legs, in any era. The
   mechanism is structural: a cycle deploys 60 pendings, the ratchet trails and stops them out, so
   realized accumulates long before the sweep — the final era's pre-sweep realized median is **$46.03**,
   and all 37 of its singleton terminal sweeps had prior closes. The two clean cases that do exist
   (28.10, 28.28) sit between the candidates and are far too few to weigh.

3. **PART 11's one-sided mark carried a systematic ≈ $15 error.** Marking every live position at a single
   price loads a full spread onto the basket's net directional exposure (≈ 0.5 lots at the 0.15 tier ×
   $0.30 × 100). Its "35.7% of sweeps marked below their own target" was therefore instrument error, not
   EA misbehaviour. PART 12's two-sided construction was written to remove it and demonstrably works —
   the recovered ask−bid is `p05 −0.160 / p50 0.300 / p95 0.760`, a plausible XAUUSD spread, and
   `HISTORICAL_60`'s left tail improved from −119.56 to −15.13 — yet the below-target fraction **rose** to
   41.1%, which proved a second, larger timing error remained. That was the observation PARTS 13–14 were
   built to chase, and PART 14 found it.

4. **PART 13's premise was refuted by its own first output line.** The hypothesis was that the 2-second
   burst grouper was cutting one paced liquidation into several "bursts" — the final era has 284 interim
   bursts over 103 cycles, 279 of them singletons, which looks exactly like a paced drain being
   fragmented. Measured: **bursts per cycle p50 = 1 in every era**, drain span p50 1.23–1.76 s. The
   terminal burst *is* the whole drain for the median cycle, the interim singletons are something else,
   and the re-marked median moved only 29.40 → 28.57 with the below-target fraction unchanged at 41.0%.
   The long tail is real but rare (final era p95 240.83 s, max 481.33 s; `HISTORICAL_60` max 19,771 s —
   the known cancel-run pathology plus operator closes, §2.5).

5. **PART 3's percentage match is arithmetically forced and its slope is time-confounded** — recorded in
   §2.7.5 rather than repeated here.

**V7 verdict.** All three of the directive's questions are **identical**. The predicate is the literal
sum `realized + floating >= target` with no additional term (`BasketEvaluator.mqh`, evaluated every tick
of a live cycle from `CheckCycleTargets()`, `StraddleEngine.mqh:3431-3537`), and both of its terms use one
money definition — `POSITION_PROFIT + POSITION_SWAP` for floating (`:413-415`, `:2379`) against
`deal_profit + deal_swap + deal_commission + deal_fee` for realized (`:3685-3691`) — a choice the tape
shows is immaterial at every quoted statistic (commission identically 0 on 17,632 positions, per-era
median instrument delta 0.00 in all five eras). The `open_positions>0` gate is proved **positively** by
**8 instants across 7 cycles** where the account held zero open positions with banked money already above
the cycle target and the cycle ran on, measured over the global open set so position attribution cannot
explain it away. The per-cycle reset is proved by contradiction on **142 strict decreases** in the banked
series, **240 of 281** multi-leg terminal sweeps after the cumulative total passed the smallest target,
and **25** sweeps that banked a loss. The threshold's numeric value is the only quantity this tape cannot
pin, and §2.7.7 shows the question was mis-posed: the $26.50 under test belongs to `STARWAVE_30`, fitted
on the Starwave 60542 tape by a censored bracket $0.10 wide, while the 901018 final regime is governed by
`LATEST_30`'s $30.00 — whose in-source fitted median of $29.40 is reproduced to the cent by this audit's
independent PART 12 mark, inside a twelve-estimate cluster of $28.10–31.54. **No code change is licensed
by this vector. V7: 100.00% on the predicate, the gate and the reset.**

### 2.8 V8 — Cycle restart floor & state machine

The directive asks two questions: *"does `restart_delay_ms=2000` enforce an exact 2.0 s delay? Clean
`CYCLE_IDLE → DEPLOYING → RUNNING → CANCELING → CLOSING → RESTARTING → IDLE`?"*

The first question contains a false premise, and finding it is most of the vector. The delay is **not**
2.0 s and cannot be: the comparison is between two whole-second datetimes, so the engine can only ever
enforce an integer number of seconds. The measurement below therefore recovers that integer directly from
the tape — from the engine's own comparison operand, with no latency model — and it recovers the *configured*
value in the two eras where that value is known, which is what licenses the same instrument everywhere else.

Instrument: `tmp/a901_v8.py`, seven parts, exit 0, over `ReportHistory-901018` (54,742 orders). Population:
**281 restarts** — every terminal sweep that has a following deployment — against **285 deployments**, 306
interim bursts and 19,312 lattice cancels.

#### 2.8.1 The floor expression, and what it actually compares

`StraddleEngine.mqh:3811-3812`, verbatim:

```cpp
              if(TimeCurrent()-m_restart_started_at>=
                 (m_profile.restart_delay_ms+999)/1000)
```

`restart_delay_ms` is `int`, so `(ms+999)/1000` is integer division — **exactly `ceil(ms/1000)`**. Write
that quantum `T`: 1000 → 1, 1500 → 2, 2000 → 2, 2001 → 3, 3000 → 3, 20000 → 20. Both operands are
whole-second `datetime` values, so the predicate is a pure integer-second test. Two consequences follow
immediately, and both matter:

1. **Any two `restart_delay_ms` values sharing a `ceil(ms/1000)` are behaviourally identical.** The tape can
   therefore pin `restart_delay_ms` only to a 1000 ms bucket. That is an *identifiability* limit of the
   evidence, not a divergence of the replica: the replica's quantisation **is** the Target's quantisation,
   because it is the same expression on the same integer-second operands.
2. **`m_restart_started_at` is the flat instant truncated down.** It is assigned `TimeCurrent()` at each of
   the three sites that enter the wait — `:2954-2955` (close-path), `:3019-3020` (cancel-path) and the
   degenerate `deployment_empty` third at `:2092-2093` — and `TimeCurrent()` carries no sub-second part.

#### 2.8.2 The two-instrument derivation, and the off-by-one it exposes

Write the flat instant as `flat = S + f` with `S = floor(flat)` and `f ∈ [0,1)`. Then
`m_restart_started_at = S`, the earliest second satisfying the predicate is `S + T`, and the engine samples
that predicate on the 100 ms `OnTimer()`, so the next deployment lands at `deploy = S + T + δ` with `δ` small
and positive (timer phase + placement round-trip). That yields two different instruments on the same rows:

| | definition | distribution | what it reads |
|---|---|---|---|
| **model-free** | `q = floor(deploy) − floor(flat)` | `= T` exactly, whenever `δ < 1` | `T` **directly**; this *is* the engine's operand |
| **modelled** | `real = deploy − flat` | `T − f + δ`, i.e. `U(T−1, T) + δ` | a *floor* at `T − 1 + δ_min` |

The consequence is the pivot of this vector: **a measured real-valued floor of `F` implies `T ≈ F + 1`, not
`T ≈ F`.** The in-source inference at `ProfileCatalog.mqh:259-263` — "1000 yields a 1 s floor (observed
1.17 s once tick lag is added)" — reads the floor as `T` and is therefore one bucket low. Note that the
model-free instrument does not depend on this reasoning at all, which is precisely why it can adjudicate it.

One minority bucket is predicted. If `TimeCurrent()` is still reporting second `S−1` when the flat is
detected — a stale quote, one tick behind — then `m_restart_started_at = S−1`, so `q = T−1` and
`real ∈ (T−2, T−1+δ)`. The bucket duly appears wherever there are enough rows to see it: `HISTORICAL_50` 6,
`HISTORICAL_60` 3, `STARWAVE_30/post-break` 4. It is a property of the clock, not of a profile.

#### 2.8.3 The model-free quantum, per era (PART 1 / PART 5)

`q` is tabulated per era, splitting `STARWAVE_30` at the 2026-07-24 pacing break already established in
§2.6.7 (burst sweeps run to Jul 24 09:10, paced sweeps resume Jul 24 15:48, so any split inside that window
separates the sub-regimes cleanly). PART 5 then drops the two contaminants — pairs whose next deployment
belongs to a *different* era (an input change happened during the wait) and pairs with `real > 600 s`
(operator gaps and market closures) — and reads `T` off the mode of what remains:

| era | n | `q` histogram (clean) | mode `T` | at mode | implied `restart_delay_ms` | configured | verdict |
|---|---:|---|---:|---:|---|---:|---|
| `HISTORICAL_50` | 99 | `{0:1, 2:6, 3:90, 63:1, 93:1}` | **3** | 90/99 = 90.91% | `(2000, 3000]` | 3000 | **CONSISTENT** |
| `HISTORICAL_60` | 76 | `{0:4, 2:3, 3:66, 13:1, 14:1, 28:1}` | **3** | 66/76 = 86.84% | `(2000, 3000]` | 3000 | **CONSISTENT** |
| `AGGRESSIVE_30` | 1 | `{85:1}` | — | — | unusable (single operator gap) | 3000 | n/a |
| `STARWAVE_30/pre-break` | 69 | `{2:65, 3:1, 32:3}` | **2** | 65/69 = 94.20% | `(1000, 2000]` | 20000 | **DIVERGENT** |
| `STARWAVE_30/post-break` | 31 | `{21:4, 22:26, 82:1}` | **22** | 26/31 = 83.87% | `(21000, 22000]` | 20000 | **DIVERGENT** |

Adding the `q = T−1` quote-lag bucket to the mode covers 96.97% / 90.79% / 94.20% / 96.77% of the four
usable eras. Two readings deserve emphasis:

- **The instrument validates itself where the answer is known.** `HISTORICAL_50` and `HISTORICAL_60` both
  inherit the `ResetProfile` default `restart_delay_ms = 3000` (`ProfileCatalog.mqh:35`), and the model-free
  quantum returns `T = 3` on 156 of 175 clean rows. Had the instrument been off by a bucket, it would have
  said 2 or 4 here.
- **`STARWAVE_30/pre-break`'s `q = 1` bucket is empty (0 rows).** So `T = 2` is not the top of a smear
  reaching down from a larger value; it is the floor of the distribution, exactly as the derivation predicts.
  This independently reproduces the in-source Starwave note's own model-free reading —
  "floor(next_deploy)−floor(flat) = 2 s on 96 cycles and 3 s on 6" — on a completely different account.

#### 2.8.4 The modelled interval, and the uniformity test (PART 2)

The derivation predicts `real ~ U(T−1, T) + δ`. Measured, with `real ≤ 600 s`:

| era | n | `T` | min | p05 | p50 | p95 | max | inside `(T−1, T+0.4)` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `HISTORICAL_50` | 99 | 3 | 0.207 | 2.154 | 2.716 | 3.191 | 92.902 | 96/99 = **96.97%** |
| `HISTORICAL_60` | 76 | 3 | 0.210 | 2.110 | 2.764 | 3.291 | 27.544 | 69/76 = **90.79%** |
| `STARWAVE_30/pre-break` | 69 | 2 | **1.170** | 1.275 | 1.754 | 2.675 | 31.984 | band `(1, 2+δ)` |
| `STARWAVE_30/post-break` | 31 | 22 | **20.905** | 21.152 | 21.699 | 22.190 | 81.913 | band `(21, 22+δ)` |

The residual `r = real − (T−1)` should be `~U(0,1) + δ`; measured p25/p50/p75 are 0.492/0.716/1.020 for
`HISTORICAL_50` and 0.401/0.764/1.054 for `HISTORICAL_60` against the predicted 0.25/0.50/0.75. The upward
shift is `δ` — the timer phase and placement round-trip — and it is the same order as the ~112 ms dispatch
cadence measured in §2.2. The distribution is one second wide, spans the predicted interval, and has no mass
below it beyond the four rows dissected in §2.8.7. This is the positive confirmation that `f` is uniform,
which is what makes the model-free reading of §2.8.3 the *right* instrument rather than merely a different one.

Two per-era readings land exactly on in-source claims. `STARWAVE_30/pre-break`'s `min = 1.170` reproduces the
1.17 s pre-break floor recorded in the `LATEST_30` four-knob table (`ProfileCatalog.mqh:317-346`) **to the
centisecond**; and `STARWAVE_30/post-break`'s `p95 = 22.190` with `min = 20.905` is the same family as that
table's "floor 20.91 s, 32/32 over 20.9 s". The measurements are not in dispute. Only their translation into
`T` is, and §2.8.8 resolves that.

#### 2.8.5 The state machine, proved as an ordering (PART 3)

The enum is seven states — `CYCLE_IDLE=0, CYCLE_DEPLOYING=1, CYCLE_RUNNING=2, CYCLE_CLOSING=3,
CYCLE_CANCELING=4, CYCLE_RESTARTING=5, CYCLE_HALTED=6` (`StraddleTypes.mqh:38-44`) — and there are 24
`m_state=` assignment sites in `StraddleEngine.mqh` (`1006`, `1052/1055/1057`, `1881`, `1918`, `1931/1933`,
`2044`, `2092`, `2099`, `2763`, `2772`, `2947/2954/2960`, `2989/3001/3009/3019`, `3124/3263`, `3406`, `3814`,
`3847`). The tape cannot observe a state variable, but it can observe the *ordering* the state machine
implies: within a cycle, the last lattice cancel must not follow the first close, the closes must be
non-decreasing in time, and the next deployment must strictly follow the last close. Over all **281**
restarts:

```
  era                                   n  cancel_then  cancel_over  cancel_afte  no_cancel_r  deploy_befo  close_order  cancel_afte
  HISTORICAL_50                       100          100            0            0            0            0            0            0
  HISTORICAL_60                        77           76            0            1            0            0            0            0
  AGGRESSIVE_30                         2            1            0            1            0            0            0            0
  LOW_RISK_30                           1            1            0            0            0            0            0            0
  STARWAVE_30/pre-break                70           61            0            9            0            0            0            0
  STARWAVE_30/post-break               31           30            0            1            0            0            0            0
```

**Zero violations of every kind, in every era: 0 `deploy_before_flat`, 0 `close_order_inverted`, 0
`cancel_after_deploy`, 0 `no_cancel_run`, 0 `cancel_overlaps_close`.** 269 of 281 = **95.73%** are strict
cancel-then-close — the `cancel_before_close = true` signature of §2.5 — and the 12 remaining rows are not
inversions but overlaps in which the cancel run outlives the flat instant (1 `HISTORICAL_60`, 1
`AGGRESSIVE_30`, 9 `STARWAVE_30/pre-break`, 1 `STARWAVE_30/post-break`). Those 12 are the population §2.8.6
uses as an instrument, and they are almost certainly the same 10 INTERLEAVED / negative-lead
`STARWAVE_30` cycles carried as an open item in §5.

#### 2.8.6 Where the restart clock is anchored (PART 7)

The 12 overlap rows answer a question the aggregate statistics cannot: when the cancel run outlives the
flat instant, does the wait run **in parallel** with the drain (anchored at the flat, merely deferred), or
does it **restart** when the drain ends? The replica's `CYCLE_RESTARTING` body defers without re-anchoring —
`StraddleEngine.mqh:3788-3820`, verbatim:

```cpp
          case CYCLE_RESTARTING:
             if(OwnedOrderCount()>0)
               {
                TryCancelOneOwnedOrder();
                break;
               }
              if(CyclePositionCount()>0)
                {
                 if(CloseIntervalElapsed())
                    TryCloseOneOwnedPosition();
                 break;
                }
              ...
              if(TimeCurrent()-m_restart_started_at>=
                 (m_profile.restart_delay_ms+999)/1000)
```

Both drain branches `break` — they do **not** touch `m_restart_started_at`. So if the engine is already in
`CYCLE_RESTARTING` when a residual cancel run is still draining, the wait has been running throughout, and
the deployment should follow the drain's end by **one timer tick (~0.1 s)**, not by `T`. The competing
hypothesis — anchoring when the drain ends — predicts `T` seconds after the last cancel. The two predictions
are separated by `T` seconds, so any row whose cancel run outlives `T` discriminates them cleanly. There are
four such rows, three at `T = 2` and one at `T = 22`:

```
  -- STARWAVE_30/pre-break    pairs with a post-flat cancel: 9
       still deploying inside the T band: 6/9   cancel run extending BEYOND T after the flat: 3
          2026-07-21 03:19:51.706  cancel_run=+ 29.556s  deploy-last_cancel=  2.025s  q=32  => drain-end anchored
          2026-07-22 05:08:09.803  cancel_run=+ 29.342s  deploy-last_cancel=  2.212s  q=32  => drain-end anchored
          2026-07-22 15:46:33.234  cancel_run=+ 30.005s  deploy-last_cancel=  1.979s  q=32  => drain-end anchored
  -- STARWAVE_30/post-break   pairs with a post-flat cancel: 1
       still deploying inside the T band: 1/1   cancel run extending BEYOND T after the flat: 0
       2026-07-30 06:46:16.653  last_cancel=+ 19.911s  deploy=+ 21.906s  q=22
```

The three pre-break rows deploy **2.025 / 2.212 / 1.979 s after the last cancel** — `T = 2`, measured from the
drain end, not 0.1 s after it. The post-break row's cancel run ends at +19.911 s, *inside* its `T = 22` wait,
and it deploys at **+21.906 s from the flat** — `T = 22` measured from the flat, not 19.911 + 22 = 41.9 s.
**4 of 4 rows are decisive, and they split.**

That split is not a contradiction, and it is not a divergence: **the replica has exactly two anchor sites,
and they implement exactly these two semantics on the two paths DIV-6 distinguishes.** `CloseOnePosition()`
anchors when the *positions* hit zero (`:2952-2958`), which is the cancel-first path — the flat-anchored
case — and it does so without testing `OwnedOrderCount()`, so a residual order run is left to
`CYCLE_RESTARTING` to drain under an already-running clock:

```cpp
      if(!m_halted && m_profile.cancel_before_close)
        {
         m_state=CYCLE_RESTARTING;
         m_restart_started_at=TimeCurrent();
```

`CancelOneOrder()` anchors when the *cancel run* is the thing that empties the basket (`:3017-3024`), which is
the close-first path — the drain-end-anchored case:

```cpp
      if(m_halted) { ... }
      else
        {
         m_state=CYCLE_RESTARTING;
         m_restart_started_at=TimeCurrent();
         LogLifecycleEvent("cycle_complete","","flat");
```

So the tape's four discriminating rows land on the two semantics the replica already has, in the direction the
code selects them: closes finishing last ⇒ flat-anchored; cancels finishing last ⇒ drain-end-anchored. A
count-level corroboration sits alongside this — the clean subset holds exactly **10** post-flat-cancel
`STARWAVE_30` rows (9 pre-break + 1 post-break), and DIV-6's census (`ProfileCatalog.mqh:88-101`) puts exactly
**10** `STARWAVE_30` cycles in the non-cancel-first bucket (101/91/0/**10**).

**Stated at the strength the evidence supports:** the two anchor semantics are *both* present in the Target
tape, the replica implements *both*, and the observed selection is consistent with the code's selection on
4/4 discriminating rows. What is **not** yet proven is the per-row mapping — the 10-versus-10 agreement cannot
be a bijection, because under the mapping the flat-anchored post-break row must be a *cancel-first* cycle, so
at least one DIV-6 non-cancel-first cycle has no post-flat cancel at all. Cross-tabulating those four `flat`
timestamps against the per-cycle DIV-6 classification would upgrade this from best-fitting mechanism to proof;
it is carried in §5. Until then the four rows are recorded as a **confirmation with an open cross-tabulation**,
not as a closed identity.

#### 2.8.7 Every interval shorter than the model allows (PART 6)

A row is "under-floor" when `real < T_measured − 1`, i.e. shorter than any draw of `T − f + δ` can be. Over
the 275 measurable clean pairs there are **7**, and 6 are explained:

```
  -- HISTORICAL_50  T_meas=3  under-floor 1/99
     2026-06-29 00:14:49.519  legs=11 real= 0.207  burst span= 2.040  deploy-last_cancel=   2.347  => in-burst flat at leg 0
  -- HISTORICAL_60  T_meas=3  under-floor 4/76
     2026-07-09 00:45:29.478  legs= 5 real= 0.210  burst span= 0.862  deploy-last_cancel=14327.631  => UNEXPLAINED
     2026-07-07 14:07:03.694  legs=26 real= 0.211  burst span= 5.695  deploy-last_cancel=   6.011  => in-burst flat at leg 12
     2026-07-06 20:37:03.326  legs=31 real= 0.212  burst span= 7.063  deploy-last_cancel=   7.387  => in-burst flat at leg 17
     2026-07-10 10:37:16.313  legs=19 real= 0.216  burst span= 4.031  deploy-last_cancel=   4.354  => in-burst flat at leg 4
  -- STARWAVE_30/pre-break  T_meas=2  under-floor 0/69
  -- STARWAVE_30/post-break T_meas=22  under-floor 2/31
     2026-07-29 21:42:59.264  legs= 1 real=20.905  burst span= 0.000  deploy-last_cancel= 141.368  => quote-lag branch q=T-1
     2026-07-30 15:46:12.209  legs= 1 real=20.909  burst span= 0.000  deploy-last_cancel= 201.735  => quote-lag branch q=T-1
```

Four rows are **in-burst flats**: the burst's tail legs are late or asynchronous fills, so the engine saw
`CyclePositionCount() == 0` at an *earlier* leg and started the wait there — and in each case some earlier leg
sits exactly `T − f + δ` before the deployment (leg 0 of 11, leg 12 of 26, leg 17 of 31, leg 4 of 19). This is
the same async-fill effect §2.11 documents for the deal ledger, not a timing divergence; the replica's own
anchor is `CyclePositionCount()`, and it would have behaved identically. Two rows are the predicted `q = T−1`
**quote-lag branch**, with `real` landing correctly in `(T−2, T−0.6)`. Both are single-leg bursts, so no
in-burst explanation is even available, and both are post-break where that bucket is populated (4 rows).

**One row of 275 is unexplained:** `HISTORICAL_60` 2026-07-09 00:45:29.478 — 5 legs, burst span 0.862 s,
`real = 0.210`, `q = 0`, with the nearest prior lattice cancel 14,327.631 s (≈4 h) away, so neither the
in-burst nor the cancel-run explanation can apply. It is carried in §5 as the single residual anomaly of this
vector: **274/275 = 99.64%** of clean restarts are accounted for at the sub-second level.

Two instrument artifacts are retracted here, both of them mine. First, an earlier build of PART 6 tested the
residual against the *configured* `T = 20` rather than the measured `T = 2`, and duly flagged all 66 perfectly
normal `STARWAVE_30/pre-break` restarts as "under-floor / UNEXPLAINED". Against the measured `T` the count is
**0/69**. The rule this cost is worth keeping: never test a residual against a parameter the same script has
just refuted. Second, the earlier partial reading of the post-break floor as "20.91 s with ~0.8 s residual
unexplained" is **superseded**: the band `(21, 22+δ)` implied by `T = 22` fits p05 21.152 / p50 21.699 /
p95 22.190 with nothing left over. Neither figure should be quoted again. Separately, `LOW_RISK_30`'s single
row reads `q = 2` against a configured `T = 3` and PART 1 prints it as a mismatch; it is a cross-era pair —
flat 2026-07-13 15:59:37.495, deploy 15:59:39.163, which is the *first* `STARWAVE_30` deployment — so `q = 2`
agrees with the pre-break `T = 2` of the era that received it. PART 5's cross-era filter drops it.

#### 2.8.8 Two parameter values the tape contradicts — flagged, not applied

Neither of the following is a defect in engine logic. Both are profile constants whose measured value differs
from the configured one, and both are recorded as proposed diffs only.

**Finding V8-A — `LATEST_30.restart_delay_ms = 20000` matches neither sub-regime.** `ProfileCatalog.mqh:359`
carries a single value across the 2026-07-24 pacing break, but the two sides of that break demand different
buckets: pre-break `(1000, 2000]` (18 s too high) and post-break `(21000, 22000]` (2 s too low). The
in-source four-knob table (`:317-346`) records the post-break floor correctly as "20.91 s, 32/32 over 20.9 s"
and then concludes "Parity must track the LATER configuration, so all four are 20" — the measurement is right
and the floor→`T` step is the error. Mode `q = 22` on 26/31 with the `q = 21` bucket at 4 implies `T = 22`:

```diff
--- a/mql5/include/ProfileCatalog.mqh
+++ b/mql5/include/ProfileCatalog.mqh
@@ -359 +359 @@
-         p.restart_delay_ms=20000;
+         p.restart_delay_ms=22000;   // measured: mode q=22 on 26/31 post-break clean restarts
```

Scope: this is a **forensic-fidelity** divergence for the 901018 replay profile, not a live divergence for the
Starwave parity artifact. The six `STARWAVE_*` profiles at 2000 are independently confirmed — the pre-break
tape reads `T = 2` with an empty `q = 1` bucket, and the Starwave 60542 note's own model-free reading was 2 s
on 96 cycles. A cleaner fix than the diff above is the `LATEST_30_FAST` split carried in §5, since one profile
cannot express both sides of the break on *any* of the four pacing knobs.

**Finding V8-B — `JUNE_2K.restart_delay_ms = 1000` is wrong on both epochs it invokes.** The case declares its
own regime at `:237-238`: `// Target EA parity: initial $2,000 growth regime (June 23 - July 02, 2026).` That
window **is** the `HISTORICAL_50` era, whose measured quantum is `T = 3` on 90/99 with real p05 = 2.154 — i.e.
`(2000, 3000]`, the inherited default. But the justifying comment at `:251-263` imports a *different* epoch's
floor — "pre-2026-07-24 (this regime) restart floor 1.17 s, 64/68 under 4.5 s" — which is
`STARWAVE_30/pre-break`'s floor (measured `min = 1.170`, and 66/70 under 4.5 s reproduces the cited 64/68),
three weeks after June 23 – July 02. And even for that borrowed epoch the inference is one bucket low: a
1.17 s floor implies `T = 2`, never `T = 1`. So the override is unfounded twice over, and its closing
instruction — "Raising this to 2000 would contradict the pre-break floor, so do not 'align' it with the
Starwave profiles" — is unfounded with it:

```diff
--- a/mql5/include/ProfileCatalog.mqh
+++ b/mql5/include/ProfileCatalog.mqh
@@ -269 +269 @@
-         p.restart_delay_ms=1000;
+         // (delete the override: inherit the ResetProfile default 3000, :35)
+         // measured on the June 23 - July 02 era this profile models: mode q=3
+         // on 90/99 clean restarts, real p05=2.154 => restart_delay_ms in (2000,3000]
```

**This is explicitly not a re-application of a previously reversed change.** An earlier session changed this
field 1000 → 2000 and that change was wrong and was reverted. The proposal here is a *different value* —
**3000**, from a *different epoch* (the era `JUNE_2K` itself declares, not the one its comment quotes) — and it
arrives via the model-free quantum rather than the floor-reading that produced the earlier error. It remains
**flagged and unapplied** pending the user's decision, together with the comment block at `:251-263`, which
would need rewriting whichever way the value goes.

#### 2.8.9 Verdict

The directive's first question is answered in the negative, for a reason that turns out to be identity rather
than divergence: `restart_delay_ms = 2000` does **not** enforce a 2.0 s delay in either EA. It enforces
`ceil(2000/1000) = 2` whole seconds measured between two integer-second clocks, which the tape sees as
`q = 2` exactly and as a real interval uniform on `(1, 2) + δ`. The replica's inability to express a
sub-second delay is the *Target's* inability, expressed by the same integer division, so what remains is an
**identifiability** limit on the evidence and not a behavioural gap: every value in a 1000 ms bucket is
bit-identical, so 3000 is exactly as correct as 2500, and no tape of any length can separate them.

The second question is answered in the affirmative and positively: over **281** restarts the implied ordering
of `CANCELING → CLOSING → RESTARTING → IDLE → DEPLOYING` holds with **zero** violations of any of the five
tested kinds, 95.73% of them in the strict cancel-then-close form, and the 12 overlap rows resolve to the
replica's two documented anchor sites 4/4. The floor itself is confirmed where it is knowable: `HISTORICAL_50`
and `HISTORICAL_60` both read `T = 3` against an inherited configured 3000, on 156 of 175 clean rows.

**V8: 100.00% on the mechanism** — the floor expression, the state-machine ordering, the anchor-site
selection, the deferral semantics and the persistence of `m_restart_started_at` across a restart (declared
`:39`, persisted `:1081-1082`, restored `:822-834` / `:901-902` / `:1004-1013` with the
`RestartStartedAtFromTelemetry()` fallback at `:738-763`, cleared `:1141`, zeroed `:3136`, telemetry
`:1448-1449`). **Two profile constants are flagged** (`LATEST_30` 20000; `JUNE_2K` 1000), neither applied,
both affecting only 901018 replay fidelity and not the Starwave parity artifact. **One row of 275 is
unexplained.** The executive table records V8 as 100.00% of mechanism with two flagged constants; the earlier
provisional entry ("micro-divergence — quantisation, documented") was written before the model-free quantum
existed and understated the result, since the quantisation it referred to is shared by both EAs by
construction.

### 2.9 V9 — Lot sizing & tier schedules

The directive names three ladders: `STARWAVE_30` 0.01/0.06/0.15 at L1–10/11–20/21–30, `STARWAVE_20`
0.01/0.04/0.15 at L1–6/7–13/14–20, `JUNE_2K` 0.01/0.03/0.06 at L1–15/16–25/26–30.

#### 2.9.1 The mechanism is a lookup, not a formula

`SetLotTier()` (`ProfileCatalog.mqh:52-56`) writes a constant into a closed level range:

```cpp
void SetLotTier(SProfileConfig &config,const int first_level,const int last_level,const double volume)
  {
   for(int level=first_level;level<=last_level && level<=STR_MAX_LEVELS;level++)
      config.lots[level-1]=volume;
  }
```

So volume is a **pure function of the level index** — an array lookup into `lots[STR_MAX_LEVELS]`
(`StraddleTypes.mqh:57`), never a running function of fill count, drawdown, equity or elapsed time. Three
invariants follow, and all three are testable on the tape:

1. **Buy/sell symmetry at every level.** `InitializeLevelTargets()` (`StraddleEngine.mqh:258-267`) assigns
   both sides from the same slot — `m_buy_levels[index].volume=m_profile.lots[index]` and
   `m_sell_levels[index].volume=m_profile.lots[index]` — so `B<n>` and `S<n>` must always carry an identical
   volume.
2. **Re-arms carry the tier lot, not a recomputed one.** The re-arm path (`:1635-1641`) reads the same array,
   which is the volume half of V6's "return to the exact original slot" result (§2.6).
3. **Volume participates in level identity.** `:2408` — `MathAbs(volume-m_profile.lots[index])<=1e-8` — so a
   leg whose volume did not match its slot would not be recognised as that slot at all.

The only multiplier anywhere on this path is `ContractScale()` (`:1035/:1044`, `:2292-2294`, `:2342-2344`,
`:2464`, `:2542`, `:2594`), which is **1.0** on this symbol (§2.12), so the configured ladder reaches the
broker unmodified.

#### 2.9.2 The catalogue, verbatim

| profile | N | tier 1 | tier 2 | tier 3 | source |
|---|---:|---|---|---|---|
| `HISTORICAL_50` | 50 | 1–15 @ 0.01 | 16–25 @ 0.03 | 26–50 @ 0.06 | `:132-134` |
| `HISTORICAL_60` | 60 | 1–15 @ 0.01 | 16–45 @ 0.02 | 46–60 @ 0.05 | `:168-170` |
| `AGGRESSIVE_30` | 30 | 1–10 @ 0.08 | 11–20 @ 0.41 | 21–30 @ 0.82 | `:210-212` |
| `LOW_RISK_30` | 30 | 1–10 @ 0.01 | 11–20 @ 0.02 | 21–30 @ 0.05 | `:231-233` |
| `JUNE_2K` | 30 | 1–15 @ 0.01 | 16–25 @ 0.03 | 26–30 @ 0.06 | `:277-279` |
| `LATEST_30` | 30 | 1–10 @ 0.01 | 11–20 @ 0.06 | 21–30 @ 0.15 | `:459-461` |
| `STARWAVE_30` | 30 | 1–10 @ 0.01 | 11–20 @ 0.06 | 21–30 @ 0.15 | `:491-493` |
| `STARWAVE_20` | 20 | 1–6 @ 0.01 | 7–13 @ 0.04 | 14–20 @ 0.15 | `:525-527` |
| `STARWAVE_30_HIGH` | 30 | 1–10 @ 0.01 | 11–20 @ 0.05 | 21–30 @ 0.20 | `:560-562` |
| `STARWAVE_30_MID` | 30 | 1–10 @ 0.01 | 11–20 @ 0.04 | 21–30 @ 0.15 | `:595-597` |
| `STARWAVE_20_WIDE` | 20 | 1–6 @ 0.01 | 7–13 @ 0.06 | 14–20 @ 0.15 | `:629-631` |
| `STARWAVE_20_LIGHT` | 20 | 1–6 @ 0.01 | 7–13 @ 0.03 | 14–20 @ 0.15 | `:670-672` |

All three ladders the directive names are present at exactly the specified boundaries and volumes.
`CUSTOM_PROFILE` reproduces the same shape from three inputs (`:745-747`), validated at `:687-689` so that
`1 ≤ tier1_end ≤ tier2_end ≤ levels_per_side`.

#### 2.9.3 Measured on the tape

Every lattice leg the Target placed on 901018 was scored against the tier lot its own level index demands,
under the era assignment established in §0.1 (101 / 78 / 2 / 1 / 103 deployments):

| population | matched | rate |
|---|---:|---:|
| lattice legs across 285 deployments | 25,447 / 25,447 | **100.00%** |

Zero exceptions — no partial lot, no rounding drift, no level whose volume fell between two tiers, and no
`B<n>`/`S<n>` pair whose volumes differed. The three structural invariants of §2.9.1 are therefore satisfied
by measurement as well as by construction: because the same array slot feeds both sides, symmetry could only
fail through a broker-side volume rewrite, and none occurred in 25,447 placements.

Two consequences worth stating plainly, because they close doors rather than open them:

- **The tier boundaries are recoverable from the tape.** Each era's ladder appears as a step function whose
  risers sit at exactly the configured level indices, so a deployment that reaches level 30 exposes its
  profile's full signature `(N, tier volumes, boundaries)` and pins the era independently of anchor/step
  geometry (§2.1). `AGGRESSIVE_30`'s 0.08/0.41/0.82 is the one ladder an order of magnitude above the rest,
  and it ran for exactly 2 deployments (§0.1) — its footprint in the money series (§2.7) is correspondingly
  extreme and is not evidence of a sizing rule, only of that ladder.
- **The two "unrecognised signatures" carried from the era census are prefixes, not unknown ladders.** A burst
  truncated at level 10 exposes only `(0.01,)` and at level 11 only `(0.01, 0.06)`. The latter is
  *uniquely* `LATEST_30`/`STARWAVE_30` among the 30-level ladders, since the boundary-at-10 alternatives carry
  0.05 (`_HIGH`), 0.04 (`_MID`) or 0.08 (`AGGRESSIVE_30`) at level 11, and the boundary-at-15 ladders
  (`JUNE_2K`) carry 0.01 there. The former is under-determined on volume alone — every 0.01-opening ladder
  agrees over levels 1–10 — so it is placed by step/anchor era, not by lot signature. Neither row is a ladder
  the catalogue lacks.

#### 2.9.4 Verdict

Lot sizing is the one vector where the replica cannot diverge by arithmetic, because there is no arithmetic:
`SetLotTier()` materialises constants into `lots[]` at profile load, `InitializeLevelTargets()` copies slot
`index` into both sides of level `index+1`, the re-arm path re-reads the same slot, and `:2408` refuses to
recognise a leg whose volume disagrees with its slot by more than 1e-8. The directive's three named ladders
match source exactly (`STARWAVE_30` `:491-493`, `STARWAVE_20` `:525-527`, `JUNE_2K` `:277-279`), and
`LATEST_30` `:459-461` is byte-identical to `STARWAVE_30` as spec §6 requires.

**V9: 100.00%** — 25,447 of 25,447 legs, twelve ladders confirmed against source with line citations, buy/sell
symmetry structural, and the two open signature rows resolved as truncation prefixes.

### 2.10 V10 — Trend rescue logic

The directive asks two questions: verify the sign and thresholds of the four rescue constants, and confirm
that rescue is disabled for the Starwave profiles "matching the total absence of doubled orders in the
Starwave dataset". Both are answered here, the second **positively rather than by assumption** — and the
executive row that previously read *"100.00% (inactive on both tapes) — identity by absence"* is retracted.
The mechanism is **measured active on the 901018 tape**: six cycles, seven side-events, 125 doubled orders.
Identity-by-absence was never available; the vector had to be proven on live evidence, and it now is, with
one tape-only divergence registered as Finding V10-A.

#### 2.10.1 The four thresholds, and the sign of the drawdown gate

| directive constant | source | value | second attestation |
|---|---|---|---|
| `trend_rescue_bars = 6` | `ProfileCatalog.mqh:416` | 6 | `:283` (`JUNE_2K`) |
| `trend_rescue_move_price = 20.0` | `:421` | 20.0 | `:285` |
| `trend_rescue_drawdown_money = 400.0` | `:444` | 400.0 | `:286` |
| `trend_rescue_volume_multiplier = 2.0` | `:452` | 2.0 | `:287` |

The sign question is the one that matters, because `400.0` is stored unsigned and a drawdown is negative.
`TrendRescueSide()` (`StraddleEngine.mqh:2384-2404`) resolves it with a **negating comparison** at `:2391`:

```cpp
      if(CycleFloatingProfit()>-m_profile.trend_rescue_drawdown_money)
         return 0;
```

so the stored constant is a **positive magnitude** and the gate opens only when cycle floating P&L has fallen
to **≤ −400.00** account currency. `CycleFloatingProfit()` (`:432-437`) sums `POSITION_PROFIT+POSITION_SWAP`
over cycle-owned positions only, so the threshold is cycle-scoped, not account-scoped. Direction then comes
from a bar-close reference rather than from the drawdown: `prior_close = iClose(symbol,
trend_rescue_timeframe, trend_rescue_bars)`, with `tick.ask - prior_close >= move_price → +1` (buy side) and
`prior_close - tick.bid >= move_price → −1` (sell side). The two conditions are conjunctive: a −400 drawdown
with a <20.0 price move does not fire, and a 20.0 move with floating above −400 does not fire.

`minimum_pending_levels` is the fifth constant the directive does not name but which gates the trigger via
`HasTrendRescueBasePending()` (`:2428-2440`): **0** for `JUNE_2K` (`:284`), **3** for `LATEST_30` (`:420`).
The in-source claim at `ProfileCatalog.mqh:420` that the six measured events had 3/16/10/6/19/11 base
pendings available is **not reproduced** by this audit and remains the one unverified numeric assertion in
the rescue block; the constant itself is safe because 3 is a floor below every measured event's count.

`trend_rescue_drawdown_money = 400.0` remains **bounded, not point-identified**: the tape proves the gate
opened at some floating level ≤ −400 on six occasions and never opened above it, which brackets the constant
without pinning it. That was stated in §2.7 and is unchanged.

#### 2.10.2 Question 2 — Starwave rescue disabled, proven positively

All six Starwave profiles set `trend_rescue_enabled=false`: `ProfileCatalog.mqh:495` (`STARWAVE_30`), `:529`
(`STARWAVE_20`), `:564` (`STARWAVE_30_HIGH`), `:599` (`STARWAVE_30_MID`), `:633` (`STARWAVE_20_WIDE`), `:674`
(`STARWAVE_20_LIGHT`). `ResetProfile()` `:42-48` already defaults `enabled=false` with
`volume_multiplier=1.0`, so the six settings are re-assertions rather than overrides.

The empirical half needed a repair before it could be trusted. Scoring the 8,536 Starwave lattice orders
against a **single pooled ladder** manufactures 668 "non-tier" rows and 24 apparent same-level doubling
collisions — the exact artifact that would have produced a false positive for rescue activity. Rescoring each
order against **its own cycle's recovered ladder** removes them completely:

```
scored against own-cycle ladder: base=8536  x2=0  other=0  no-tier=0
orders at exactly 2x their OWN CYCLE's tier at that level: 0
```

**8,536 of 8,536** Starwave lattice orders sit at their own cycle's base tier and **not one** sits at twice
it. The directive's premise — "the total absence of doubled orders in the Starwave dataset" — is confirmed,
and `trend_rescue_enabled=false` on the six profiles is therefore **empirically required**, not merely
assumed. The pooled figures (668 / 24) are retracted as multi-epoch artifacts; the volumes 0.10 and 0.12 that
generated them are the tier lots of *other* epochs, sitting at n≈62 per level contiguously across L21–L30,
which is the signature of a whole configuration era rather than of scattered rescue replacements.

#### 2.10.3 The mechanism, measured active on 901018

Rescue is enabled on `LATEST_30` (`:402-452`) and `JUNE_2K` (`:281-287`), and the 901018 tape exercised it.
Six distinct cycles fired, **three before the 24 July configuration break and three after** — cycles 197,
207, 244, then 254, 260, 262 — producing **seven `(cycle, side)` events** (cycle 262 fired on both sides,
separated by 9,683.058 s) and **125 orders at exactly twice the tier volume**. Both figures reproduce the
in-source parity claim at `ProfileCatalog.mqh:403-405` exactly.

The seven events decompose as **89 immediate replacements** (a base cancel followed at the same level by a
2× order) plus **36 latched re-arms** (a 2× order placed after a 2× position exited, the latch surviving the
exit). 89 + 36 = 125. The 89 is reproduced independently by two instruments built on different groupings,
which is the cross-check that the event segmentation is not an artifact of either.

Scalar-state invariant: `m_trend_rescue_side` is a single `int` (`:2648`), so two events in one cycle on
opposite sides must be **time-disjoint**. Measured same-cycle opposite-side span overlaps: **0**. The one
same-cycle pair (262 sell then 262 buy) is separated by 9,683.058 s of dead time.

Side-exclusivity within an event: `other_side = 0` on every one of the nine 600 s replacement groups — a
rescue never places on the side opposite its trigger. This is enforced by `ProcessTrendRescue()` passing a
single `is_buy` derived from `m_trend_rescue_side` into both phases (`:2666-2674`), and by the consumed-side
refusal at `:2643` which blocks a repeat of the same side until the trigger lapses (`:2635-2639`).

#### 2.10.4 The two walk directions, proven per pass

The replica's rescue is a two-phase sweep with **opposite walk directions**, and both are testable on the tape:

```cpp
   bool TryCancelOneTrendRescueOrder(const bool is_buy)          // :2479
     {
      for(int index=m_profile.levels_per_side-1;index>=0;index--)  // :2481  DESCENDING
   void PlaceOneTrendRescueReplacement(const bool is_buy)        // :2504
     {
      for(int index=0;index<m_profile.levels_per_side;index++)     // :2506  ASCENDING
```

Both invariants initially appeared to fail — the cancel walk read `2/7` and the placement walk `5/7`. Both
readings were **concatenation artifacts**: an event contains several passes, and gluing them end to end
destroys monotonicity that holds inside every pass. Segmenting on a **time gap** (non-circular: the split is
independent of the level ordering being tested) and testing each pass separately:

| phase | source | passes | strictly monotone | previous artifact |
|---|---|---|---|---|
| A — cancel, descending | `:2481` | 40 | **40 / 40** | `cnl_desc 2/7` |
| B — place, ascending | `:2506` | 47 | **47 / 47** | `imm_asc 5/7` |

Zero exceptions on either walk across all seven events. Both artifact readings are retracted. The load-bearing
multi-level placement runs are `28-30`, `16-30`, `20-30`, `27-30`, `26-30`, `10-30`, `19-30` — each strictly
ascending from the lowest cancelled level to the top of the ladder, which is exactly what an ascending sweep
over a `trend_rescue_replacement` mask produces.

Cycle 262 buy is the cleanest single event: **20 base cancels over 20 distinct levels, no level cancelled more
than once, 30 orders at 2×**, and its seven passes are 7/7 descending.

#### 2.10.5 Cadence, pricing, and the volume ratio

The rescue reuses the EA's ordinary 100 ms dispatch pacer rather than a dedicated one — one cancel per tick in
phase A (`:2669-2670` returns immediately after a successful delete), one placement per tick in phase B
(`:2613` returns after each `PlaceLevel`). Measured, as two independent re-derivations of the same constant:

| interval | n | min | p05 | p50 | p95 |
|---|---|---|---|---|---|
| cancel → cancel | 156 | 0.098 s | 0.099 s | **0.105 s** | 2.661 s |
| place → place | 82 | 0.098 s | 0.098 s | **0.102 s** | 0.140 s |

Both p50s sit on the same 0.10–0.12 s band that §2.2 derived from deployment and §2.5 from liquidation, a
fourth and fifth independent attestation of `InterOrderDelayMs=100`. The `min=0.098` on both series is the
floor; nothing dispatches faster.

Pricing: **`price_dev = 0.0000` on all nine replacement groups.** The rescue re-places at the *exact* original
lattice price `anchor ± level*step`, never at a re-anchored price — which is what `PlaceOneTrendRescueReplacement`
does by reading `level.target_price` rather than recomputing from the current mid, gated by
`PendingPriceIsValid()`.

Volume: **every one of the 125 ratios is exactly 2.0000**, in four groups — L6 `0.01→0.02` (n=1), L10
`0.01→0.02` (n=4), L11–20 `0.06→0.12` (n=55), L21–30 `0.15→0.30` (n=65). The in-source comment at
`ProfileCatalog.mqh:445-446` reads:

```cpp
// Target EA parity: rescue replacements trade at exactly 2x the tier
// volume in the dataset (0.12 = 2x0.06 at L11-20, 0.30 = 2x0.15 at L21-30)
```

Confirmed, and **extended**: the comment omits the five `0.02 = 2×0.01` rows at L6 and L10, which are the
tier-1 instances of the same law. `deployment_fill_cooldown_seconds = 20` is confirmed as a live gate on the
rescue path at `:2661-2665` — a pause, not an abort.

#### 2.10.6 Finding V10-A — the 85 base re-placements (tape-only, zero economic content)

This is the one divergence the vector produced, and it was found by refusing to accept that a cancel is always
followed by a 2×. Reconstructing the full per-level order chain at every rescued level and classifying each
transition by `(predecessor tag, predecessor state) → successor tag`:

```
        base canceled  -> x2      n=89          <== the replica's predicted behaviour
        base canceled  -> base    n=85          <== the replica predicts 0
          x2 filled    -> x2      n=22
        base filled    -> base    n=19
        base filled    -> x2      n=14
          x2 filled    -> base    n=7
```

The replica cannot emit `base canceled → base`. `TryCancelTrendRescueLevel()` rewrites the level's volume to
`lots[index]*multiplier` **at cancel time** (`:2463-2466`), sets `rearm_requested=false` (`:2467`), and sets a
`trend_rescue_replacement` mark that only `ClearTrendRescueReplacement()` (`:2497-2502`) clears — and that
runs only after a successful placement (`:2610`) or when the level holds a position (`:2519`). So the replica's
first replacement at a cancelled level is **always** the 2×. The Target instead re-placed at **base** 85 times.

The economic question — can such an order fill, giving the Target a position the replica never opens? — needed
a correctly scoped population. Defining a *base re-placement* as a base order whose immediate predecessor at
the same level is a **canceled base order** (which excludes the deployment leg and ordinary re-arms, the
contamination that a first attempt at this measurement suffered from):

```
  base re-placements: 85
      final state canceled   n=85
      re-placed at the IDENTICAL price: 85/85
      cancel->replace gap  n=85  min=0.102s  p50=1.481s  max=22.410s
      replacement lifetime n=85  min=0.679s  p50=3.466s  max=1544.941s
  filled re-placements: 0
```

**All 85 ended canceled. Not one filled.** The divergence is confined to the order tape: it produced no
position, no exposure, no swap, no commission and no realised or floating P&L on either side. Every affected
level reached the **identical terminal state** in both EAs — a single 2× pending at the exact lattice price —
and the 2× order count matches exactly (125 measured, 125 predicted). The `min=0.102 s` cancel→replace gap is
the ordinary 100 ms pacer, confirming these are EA-issued orders on the normal placement path, not broker
artifacts.

The divergence is also **not universal**. Counting base orders preceding the first 2× at each rescued level:

```
  cyc  side  levels  depth histogram
   197 buy      10   1B x10
   207 sell     20   1B x20
   244 sell     11   3B x11
   254 buy       8   1B x4  2B x3  3B x1
   260 buy      20   2B x5  3B x13  4B x1  5B x1
   262 buy      21   1B x13  2B x3  3B x4  4B x1
   262 sell     13   1B x1  3B x12
```

Depth 1 means "deployment leg, then the 2×" — the replica's exact shape. **48 of the 103 level-events are
depth 1, and three of the seven events (197 buy, 207 sell, 262 buy at 13 of 21 levels) match the replica
without exception.** The 85 extra orders are concentrated in four events: 244 sell (22), 254 buy (4), 260 buy
(35), 262 sell (24). Where they occur they are strikingly uniform — cycle 244 sell runs `Bc Bc Bc Xf` at
**all eleven** rescued levels, and 262 sell at twelve of thirteen — the signature of a whole-side sweep
repeated, not of a per-level race.

The mechanism behind the extra passes, read off the replica's own control flow, is that the Target evidently
separates the cancel gate from the placement gate. The replica does not: once `m_trend_rescue_side` latches at
`:2648`, `ProcessTrendRescue()` never re-reads `trigger_side` again (`:2661-2674` uses only the latched side),
so phase A always runs to exhaustion and phase B always follows. The transition from A to B is a one-way latch
(`m_trend_rescue_replacing=true`, `:2671`) that cannot be un-set within an event. **The replica therefore has
no cancel-without-place state, and the Target demonstrably does.**

Two consequences worth stating explicitly, because both are candidates for a code change and both are rejected
on evidence:

1. **The replica has no latent "vacated level" hazard.** The first reading of `:2463-2467` suggested that an
   interrupted rescue could leave a level with `has_pending=false`, `rearm_requested=false` and a live
   `trend_rescue_replacement` mark — permanently empty, which *would* be economically material. Reading
   `ProcessTrendRescue()` in full refutes this: the mark persists and phase B is re-entered on every subsequent
   tick, so a failed `PlaceLevel` or an `ExposureAllowsRearm` block (`:2599-2607`) retries rather than
   abandons. No hole exists, and no fix is needed.
2. **Emulating the Target's abort-and-retry is rejected.** It would require inventing an abort predicate the
   tape cannot identify — four events aborted one to four times and three aborted zero times, and nothing in
   the order history distinguishes them. Any such predicate would be unfalsifiable, would add order traffic
   with no economic content, and would introduce a real new risk: 85 additional live pendings ahead of a
   trending price, which on this tape happened never to fill but are not structurally prevented from filling.
   The replica's behaviour is a strict subset of the Target's with an identical terminal state.

**Finding V10-A is therefore registered as a tape-only divergence with zero economic content, and no code
change is licensed.** Consistent with Findings V8-A and V8-B, it is flagged rather than legislated.

#### 2.10.7 Finding V10-B — 34 Starwave cycles run ladders the catalogue does not model

Recovering each Starwave cycle's ladder independently (§2.10.2's per-cycle rescoring) produced a by-product
that belongs to V9 as much as to V10: the tape runs **eight distinct per-cycle ladders**, and the catalogue
models four of them.

```
distinct per-cycle ladders recovered (>=10 levels): 8
      53 cycles   L1+@0.01  L7+@0.04  L14+@0.15     STARWAVE_20        :525-527
      39 cycles   L1+@0.01  L11+@0.06 L21+@0.15     STARWAVE_30        :491-493
      31 cycles   L1+@0.01  L11+@0.04 L21+@0.12     ** UNMODELLED **
      14 cycles   L1+@0.01  L7+@0.06  L14+@0.15     STARWAVE_20_WIDE   :629-631
       6 cycles   L1+@0.01  L11+@0.05 L21+@0.20     STARWAVE_30_HIGH   :560-562
       1 cycles   L1+@0.01  L11+@0.03 L21+@0.10     ** UNMODELLED **
       1 cycles   L1+@0.01  L7+@0.03  L14+@0.10     ** UNMODELLED **
       1 cycles   L1+@0.01  L7+@0.04  L14+@0.12     ** UNMODELLED **
```

A tier-2 start at `L7` implies tier 1 = L1–6, i.e. a 20-level profile; `L11` implies L1–10, a 30-level profile.
**112 of 146 cycles are attested to a catalogue profile.** The remaining 34 run four unmodelled ladders, of
which one — `.01/.04/.12 @ 10/20/30`, **31 cycles, ~21% of the tape** — is the second most common 30-level
ladder the operator used. Symmetrically, **`STARWAVE_30_MID` (`:595-597`) and `STARWAVE_20_LIGHT` (`:670-672`)
are unattested**: zero cycles on this tape run either ladder.

This is a **coverage gap, not a parity defect**. The replica reproduces whichever ladder it is configured with,
exactly (V9: 25,447/25,447), and the ladder is operator-selected input rather than EA behaviour. It is recorded
in §5 as an open item, with the natural remedy being a `STARWAVE_30_MID2` profile carrying `.01/.04/.12` at
10/20/30 to cover the 31 cycles, and no change to the two unattested profiles — absence of attestation is not
evidence of error, only of non-use during this window.

#### 2.10.8 Verdict

Both directive questions are answered. The four thresholds are verified at source with a second attestation
each, and the sign question — the only one with a wrong answer available — is settled by the negating
comparison at `StraddleEngine.mqh:2391`, which makes `400.0` a positive magnitude gating at floating ≤ −400.00.
Rescue is disabled on all six Starwave profiles, and that setting is now **empirically required** by
8,536/8,536 Starwave lattice orders sitting at their own cycle's base tier with zero at 2×, rather than assumed
from a pooled scoring that would have produced a false positive.

The vector's substance, though, is that **the premise of the old executive row was wrong**. Rescue is not
inactive on both tapes; it is inactive on Starwave and **active on 901018**, where it fired on six cycles in
seven side-events and issued 125 doubled orders. That could not be certified by absence, and every invariant
had to be proven on live evidence:

| invariant | source | measured |
|---|---|---|
| event count and split | `ProfileCatalog.mqh:403-405` | 6 cycles, 3 before / 3 after the 24 Jul break ✓ |
| doubled order count | `:403-405` | 125 ✓ |
| volume ratio exactly 2× | `:452`, `:2463-2466` | 125 / 125 at 2.0000 ✓ |
| re-place at original lattice price | `:2504-2614` via `target_price` | `price_dev = 0.0000` on 9/9 groups ✓ |
| phase A descending | `:2481` | **40 / 40** passes ✓ |
| phase B ascending | `:2506` | **47 / 47** passes ✓ |
| single-side per event | `:2643`, `:2666` | `other_side = 0` on 9/9 groups ✓ |
| scalar side state, disjoint | `m_trend_rescue_side`, `:2648` | 0 same-cycle overlaps ✓ |
| every cancelled level gets a 2× | `:2497-2502` mark lifecycle | `clv ⊆ ilv`, 7 / 7 events ✓ |
| 100 ms pacer on both phases | `:2669`, `:2613` | p50 0.105 s / 0.102 s, min 0.098 s ✓ |
| fill cooldown gates the rescue | `:2661-2665` | 20 s confirmed ✓ |
| latch survives a 2× position exit | `:2462`, `:1635`/`:1641` | 22 `x2→x2`, 7 `x2→base` ✓ |
| Starwave rescue disabled | `:495 :529 :564 :599 :633 :674` | 8,536 / 8,536 base, 0 at 2× ✓ |

Twelve invariants proven, zero exceptions. One divergence found — **85 base re-placements the replica does not
emit** — measured to be tape-only: 85/85 canceled, **0 filled**, 85/85 at the identical price, identical
terminal state at every affected level, and three of the seven events matching the replica exactly. Two
candidate code changes were considered and both rejected on evidence: the "vacated level" hazard does not exist
(`ProcessTrendRescue()` retries the mark every tick), and emulating the abort-and-retry would require an
unfalsifiable predicate while adding fill risk the Target never realised.

**V10: 100.00% of the economic mechanism** — 125/125 doubled orders reproduced in volume, price, side, walk
direction, cadence and count; 8,536/8,536 Starwave orders confirming the disable; one tape-only order-traffic
divergence (Finding V10-A) with zero P&L content, flagged not legislated; one catalogue coverage gap (Finding
V10-B) recorded in §5.

Retracted by this section: *"inactive on both tapes"*, *"identity by absence"*, the pooled Starwave scoring's
668 non-tier rows and 24 doubling collisions, the concatenated-run readings `cnl_desc 2/7` and `imm_asc 5/7`,
the mislabelled one-sidedness test that read "cycles carrying 2x on BOTH sides: 1" as a violation when the
source refuses only a repeat of the *consumed* side, and a first attempt at the economic test whose
"intermediate pending" population was cycle-wide rather than rescue-scoped (reporting 32 fills and a p50
lifetime of 10,228 s, both artifacts of counting deployment legs).

### 2.11 V11 — Deal ledger and async trade reconciliation

**Rating: 100.00% of the mechanism, with one flagged micro-divergence (V11-A).** The money
identity is proven against the broker's own report footer to the cent.

Instrument: `tmp/a901_v912.py` (nine parts, output `tmp/out_v912.txt`) and
`tmp/a901_v913.py` (PART 3d, output `tmp/out_v913.txt`), both over the full 901018
workbook — 35,447 deal rows, 54,742 order rows, 17,632 closed-position rows.

#### 2.11.0 The directive names a function that does not exist

The directive asks about `ReconcileHistoryDeals()`. **There is no such symbol in the tree.**
The name is a paraphrase; V11's real surface is four components:

| Directive's name | Actual implementation | Responsibility |
| --- | --- | --- |
| `ReconcileHistoryDeals()` | `QueueMissingHistoryDeals()` `StraddleEngine.mqh:3579-3626` | owns the lookback; periodic re-scan |
| — | `ProcessPendingDeals()` `:3731-3748` | drains the retry queue |
| — | `ProcessSelectedDeal()` `:3628-3729` | the per-deal accumulator |
| — | `CCycleDealLedger::TryRecalculate()` `CycleDealLedger.mqh:17-51` | absolute set recompute |

with `OnTradeTransaction()` `:3826-3849` as the live entry point (forwarded from
`StraddleReplicaApp.mqh:197-202`; standalone `ProfitBricks2K.mq5:5526` and `:5759-5764`).

#### 2.11.1 The four constants and the scan budget

`StraddleEngine.mqh:12-15`:

| Constant | Value | Role |
| --- | --- | --- |
| `STR_PENDING_DEAL_CAPACITY` | 256 | retry-queue depth for **unsettled** deals only |
| `STR_DEAL_METADATA_SETTLE_MS` | 5000 | grace before a deal's metadata is trusted |
| `STR_HISTORY_RECONCILE_INTERVAL_MS` | 1000 | re-scan cadence |
| `STR_HISTORY_RECONCILE_LOOKBACK_MS` | 900000 | re-scan window (15 min) |

The directive's phrasing — "lookback with `DEAL_TIME_MSC >= m_cycle_started_msc`" — conflates
two different bounds that the implementation keeps separate. The 900 s lookback bounds only
the *periodic re-scan* in `QueueMissingHistoryDeals()`; the `DEAL_TIME_MSC >= cycle_started_msc`
predicate is the *ledger's* cycle filter inside `TryRecalculate()` (`CycleDealLedger.mqh:17-51`).
A deal older than 900 s is therefore not lost: it is still inside the recompute set, and the
live path reaches it through `DEAL_ADD` regardless of age. Interval ÷ lookback gives **900
re-scans covering any single in-window second**, which is the redundancy that makes a single
missed `OnTradeTransaction()` callback economically harmless.

#### 2.11.2 The money formula, proven against the broker's own footer to the cent

`ProcessSelectedDeal()` accumulates four terms (`StraddleEngine.mqh:3685-3691`) and
`TryRecalculate()` sums the identical four over the absolute set (`CycleDealLedger.mqh:45-48`):

```
deal_profit + deal_swap + deal_commission + deal_fee
```

Summing exactly that expression over every magic-901018 XAUUSD deal in the workbook, and
comparing against the report's own `Total Net Profit` (`tmp/out_v912.txt`, PART 2):

```
four-term sum over XAUUSD deals : 17,913.29
report footer Net               : 17,913.29
delta                           : 0.00
IDENTITY: MATCH
```

Term census: `Profit nonzero=17554 sum=18,203.37`; `Swap nonzero=341 sum=−290.08`;
`Commission nonzero=0`; `Fee nonzero=0`; `inout deals (DEAL_ENTRY_INOUT) : 0`.

**Swap is load-bearing.** Profit alone gives 18,203.37 — omitting `deal_swap` would misprice
the cycle accumulator by **+290.08** against this broker. PART 2b confirms the same identity
independently at the *position* level: `position count 17632 sum(profit+swap+comm)=17,913.29`
vs `footer Net=17,913.29`.

The magic-and-symbol filter (`:3634-3636`) is also attested: the workbook carries 5
non-XAUUSD rows — `Initial balance from CRM` 0.00, `Deposit from #USDT TRC20` +2,000.00,
`Withdraw to CRM #4417856484` −60.27, `Withdraw to CRM #4417856489` −180.00, and a
duplicated footer artifact row 19,963.10 — totalling **21,722.83**, all excluded exactly.
(This resolves the earlier "39,926.20 matches nothing" puzzle: 18,203.37 + 21,722.83 =
39,926.20.)

One residual is recorded and deliberately not chased: deal-level gross splits are
57,010.93 / −38,807.56 against the footer's 56,855.93 / −38,942.64 — a **symmetric ±28.22**
per-side discrepancy that nets to zero. That is an MT5 report-aggregation convention for how
a multi-tranche close is attributed to the profit or loss column, not an EA quantity.

#### 2.11.3 Scope of the formula claim — what is attested and what merely stands unfalsified

Honest scoping, because the tape cannot prove what it never exercised:

| Term | Status on 901018 | Claim |
| --- | --- | --- |
| `deal_profit` | 17,554 nonzero rows | **attested** |
| `deal_swap` | 341 nonzero rows, Σ −290.08 | **attested** (load-bearing) |
| `deal_commission` | 0 nonzero rows | unexercised → unverified, unfalsified |
| `deal_fee` | 0 nonzero rows | unexercised → unverified, unfalsified |
| `DEAL_ENTRY_INOUT` | 0 rows | unexercised → unverified, unfalsified |

This audit therefore states neither "the four-term formula is proven" nor "the formula is
untested". Two terms are proven against the broker's footer; three are structurally present
and correct by construction on a broker that never charged them.

#### 2.11.4 Duplicate and out-of-order callbacks — the idempotence triple

The directive's core question is "duplicate/out-of-order callbacks without double-counting?"
The answer is three independent mechanisms, any one of which is sufficient:

**(1) The processed-ticket set** (`StraddleEngine.mqh:630-678`). `RememberProcessedDeal()` is
itself idempotent — it returns early if the ticket is already present (`:650`) — and grows in
blocks of 128. `ProcessSelectedDeal()` opens with `DealAlreadyProcessed()` (`:3630-3631`) and
closes with `RememberProcessedDeal()` (`:3727`). Crucially the set is keyed on the **deal**
ticket (`:667`), not the order or position ticket, which is what makes a multi-tranche close
count each tranche exactly once.

**(2) The retry queue's admission test** (`:3539-3577`). `QueuePendingDeal()` refuses a ticket
that is *either* already processed *or* already queued (`:3557-3577`), so double-queueing is
structurally impossible rather than merely improbable. `OnTradeTransaction()` (`:3826-3849`)
de-queues before processing, so the live path and the drain path can never both accumulate the
same ticket.

**(3) The absolute set recompute** (`CycleDealLedger.mqh:17-51`). `TryRecalculate()` does not
add to a running figure — it recomputes `m_cycle_realized` from scratch over every history
deal matching `(magic, symbol, DEAL_TIME_MSC >= cycle_started_msc, entry ∈ {OUT, OUT_BY,
INOUT})`. An absolute recompute is order-independent by construction: no permutation of
arrivals, however pathological, can change its result.

Measured: **0 duplicated deal tickets in 35,447 rows** (`tmp/out_v912.txt`, PART 1). The tape
never exercised mechanism (1) or (2) in anger, so their correctness rests on the code reading
above; mechanism (3) is exercised on every deal.

The only early return that precedes accumulation is `DealMetadataReady()` (`:3632-3633`) — a
deal whose metadata has not settled for `STR_DEAL_METADATA_SETTLE_MS` is re-queued, not
dropped and not partially counted. The magic/symbol filter (`:3634-3636`) follows. The
stop-detection tail (`:3700-3702`) then calls `ScheduleLevelRearm()` (`:3705`), which is where
V6's re-arm chain begins — so the ledger and the re-arm scheduler share one arrival path and
cannot disagree about whether a level was vacated.

#### 2.11.5 Recompute-preferred, increment-fallback — and the `>` vs `>=` asymmetry

`StraddleEngine.mqh:3671-3693`:

```cpp
if(m_deal_ledger.TryRecalculate(m_cycle_started_msc, recalculated_realized, recalculated_count)
   && recalculated_count>m_cycle_exit_deal_count)
  { m_cycle_realized=recalculated_realized; m_cycle_exit_deal_count=recalculated_count; }
else
  { m_cycle_realized=(m_cycle_realized+deal_profit+deal_swap+deal_commission+deal_fee);
    m_cycle_exit_deal_count++; }
```

The accumulator prefers the absolute recompute and falls back to incrementing only when the
recompute is unavailable or has not yet observed the just-arrived deal. **The strict `>` at
`:3678` is deliberate, not an off-by-one.** A history snapshot that lags the callback by one
deal would return `recalculated_count == m_cycle_exit_deal_count`; accepting it would silently
discard the deal now in hand. Strict `>` forces the increment path in exactly that case. The
sibling comparison at `:932` is `>=` because at cycle *adoption* there is no in-hand deal to
protect and an equal-count recompute is the authoritative repair for accumulated drift.

#### 2.11.6 Out-of-order arrival, measured on 35,442 deals

PART 5 tests whether the broker ever issued deal tickets out of time order, and how densely
deals land inside a single millisecond:

```
time-ascending ticket inversions : 0  (0.00%)
deals-per-millisecond histogram  : [(1,26471),(2,1773),(3,806),(4,375),(5,165),(6,50),
                                    (7,30),(8,11),(9,7),(10,1),(11,1)]
milliseconds carrying >1 deal    : 3219   deals involved = 8971
```

Two conclusions. First, **ticket order never contradicts time order** on this tape, so the
"out-of-order" hazard the directive asks about was not exercised by the broker's numbering.
Second, and more important, **25.3% of all deals (8,971 of 35,442) share a millisecond with at
least one other deal, and the exit histogram tops out at 11 exit deals in one millisecond.**
That is the measured justification for both design choices in §2.11.5: at 11 deals per
millisecond a history snapshot taken mid-burst is *routinely* one or more deals stale, which is
precisely the case the strict `>` guard protects, and the recompute's order-independence is
what makes the resulting interleaving irrelevant to the money.

#### 2.11.7 Capacity and lookback load — figures stated with their reasoning

PART 6 measures the two constants against per-cycle reality across 285 cycles:

```
cycles                          : 285
deals per cycle                 : max=1714  p50=76    over capacity(256) = 30
exits per cycle                 : max=852   p50=38
cycle deal-span (s)             : max=235,911.9  p50=3,097.5  over lookback(900s) = 222
scans per second in-window      : 900x
```

Read naively these look like two overflow defects — 30 of 285 cycles exceed
`STR_PENDING_DEAL_CAPACITY`, and 222 of 285 exceed `STR_HISTORY_RECONCILE_LOOKBACK_MS`.
**Neither is a defect, for structural reasons:**

- The 256-slot queue holds only **unsettled** deals awaiting metadata, not the cycle's deals.
  It is drained every `OnTimer()` tick (100 ms) by `ProcessPendingDeals()` (`:3731-3748`), so
  the standing occupancy is the arrival rate over one 100 ms window, not the cycle total. For
  the worst cycle (1,714 deals over a span of hours) the queue would need ~256 deals to arrive
  inside a single 100 ms window and all fail the 5 s settle test simultaneously. The measured
  peak arrival density is 11 deals per millisecond in a burst, so a 256-deep queue has margin;
  the comparison of a cycle total against a per-tick queue depth is a category error.
- The 900 s lookback bounds only the periodic re-scan. The **seed pass is unclamped** and the
  live `DEAL_ADD` path has no age bound at all, so a cycle spanning 65 hours does not lose its
  early deals — they are already processed, already in the processed set, and still inside
  `TryRecalculate()`'s absolute set (which is bounded by `m_cycle_started_msc`, not by 900 s).

Both figures are recorded here because an adversarial audit must state them; neither licenses
a code change. What *would* be a defect is a cycle whose realized money disagreed with the
broker — and §2.11.2 shows the aggregate disagreement is $0.00.

#### 2.11.8 Reconciling the three tapes — orders ↔ deals ↔ positions

The ledger's correctness depends on assumptions about MT5's own bookkeeping. Each was tested
rather than assumed.

**Order → deal fan-out (PART 3).** `deals-per-order histogram [(1,35418),(2,12)]`;
`extra IN deals (partial fills): 0`; `extra OUT: 12`; `mixed-direction orders: 0`. So no order
ever produced a partial-fill chain, and exactly 12 orders produced two deals each.

**The 24 `out by` deals are exactly those 12 orders** — `'out by' deals=24 distinct orders=12
== the multi-deal orders? True`. A close-by operation emits one deal per position it closes.
Consequently `exits (17,638) − closed positions (17,632) = 6`: **six positions were each closed
by two separate `out` deals.** Because the processed set keys on the deal ticket (`:667`), each
tranche is counted once and the total is right — a ledger keyed on the *position* ticket would
have lost six tranches.

**Order ↔ deal bijection (PART 4).** `deal.Order not in order section: 0`;
`filled orders 35430`; `filled orders with zero deals: 0`;
`volume(order.filled)==sum(deal.volume) 35418/35430`. The 12 "mismatches" (`filled=0.01
deals=0.02`) are that same close-by signature — **not a bijection defect.** No filled order is
missing its deal and no deal references a phantom order.

**Position identity (PART 3b).** `position tickets never seen as an IN order: 0` on
**17,632/17,632** — MT5 hedging's `POSITION_IDENTIFIER == opening order ticket` invariant, on
which the engine's position↔level mapping depends, holds without exception.

**The 166 ghost IN deals (PARTS 3c and 3d).** 17,804 IN deals − 17,632 closed positions − 6
rows in the workbook's `Open Positions` block = **166 IN deals with neither a closed-position
row nor an open-position row**, carrying 14.13 lots. Two hypotheses were tested and both are
refuted:

- *"They are still open."* Refuted by the terminal account block
  (`tmp/report_901018.csv:107895-107898`): `Margin: 8.190000` and `Floating P/L: -23.570000`
  are consistent only with the 6 listed positions totalling 0.06 lots, not with 14.13.
- *"The Positions table is merely missing 166 rows whose exits are among the 17,638."* Refuted
  by volume conservation (`tmp/out_v913.txt`): `closed positions volume 283.57`,
  `exit deals volume 283.57`, **`exit − closed volume delta : 0.0000`** ⇒ every exit deal is
  already fully consumed by a listed closed position, so no exit deal exists for any ghost.

What settles the audit question is that **they are economically inert**:

```
ghost IN deals (no closed row, not open): 166   volume: 14.13
   Profit      nonzero=   0  sum=      0.00
   Swap        nonzero=   0  sum=      0.00
   Commission  nonzero=   0  sum=      0.00
   Fee         nonzero=   0  sum=      0.00
   ghost rows that moved Balance    : 0 of 166
```

All four money terms are nonzero on **0 of 166** and sum to exactly **0.00**, and **0 of 166**
rows move the running `Balance` column. They therefore cannot perturb `m_cycle_realized`, and
the §2.11.2 identity (delta 0.00) is untouched by them. Further, **51 of the 166 carry volumes
outside the lattice tier set {0.01, 0.03, 0.06, 0.15}** — 0.02(20), 0.05(14), 0.08(1), 0.12(5),
0.30(3), 0.41(1), 0.82(7) — so they are not all EA lattice legs; and they are spread over 17
distinct days (max 33 on 2026-06-24), not clustered at the tape's end. The doubled-tier subset
0.02+0.12+0.30 = 28 rows coincides numerically with DIV-2's `STR AVB`/`STR AVS` count (n=28)
and with `trend_rescue_volume_multiplier=2.0`; **recorded as a coincidence, not a causal
claim.** Classification: a dataset/report-structure anomaly with zero economic content and zero
contact with the code path under test — the same class as the ±28.22 gross-split convention
residual. **It licenses no code change.**

#### 2.11.9 Cycle scoping and reset discipline

`m_cycle_realized` (`:33`) is cycle-scoped, and its scope boundary is `m_cycle_started_msc`.
`ResetProcessedDeals()` fires at exactly two sites — `:1872` and `:2035` (plus the
`:3131`/`:3149-3154` region) — and at each one it is in lockstep with `m_cycle_realized=0.0`
and the forward move of `m_cycle_started_msc`. **It never fires mid-cycle**, so a cycle can
never lose its idempotence memory while its deals are still arriving. This is the source-side
half of V7's "reset to $0.00 per cycle" requirement; V7 verifies the money side.

Two supporting barriers:

- `OnTimer()` runs reconciliation **before** the state machine, and `CYCLE_IDLE` refuses to
  start a new cycle while `m_pending_deal_count>0` (`:3764-3765`). A new cycle therefore cannot
  begin while an unsettled deal from the previous cycle is still in the queue.
- `LoadProcessedDealsFromTelemetry()` (`:680-724`) rebuilds the processed set after a restart,
  filtering on `fields[2]==m_cycle_id` and reading the deal ticket from `fields[22]`. **Honest
  limitation:** with telemetry absent the reconstructed set is one ticket wide, so a restart
  mid-cycle could in principle re-present an already-counted deal to the increment path. The
  absolute recompute (`CycleDealLedger.mqh:17-51`) repairs the money on the next tick regardless,
  which is why this is a latency exposure and not a money exposure.

#### 2.11.10 Finding V11-A (flagged, not applied) — the cycle-boundary second floor

`m_cycle_started_msc` is derived as `(long)m_cycle_started_at*1000` (`:1869` and `:2031`).
`m_cycle_started_at` is a `datetime`, so **the millisecond boundary is floored to the whole
second.** Any prior-cycle exit deal that lands in the same whole second as the new cycle's start
satisfies `DEAL_TIME_MSC >= m_cycle_started_msc` and is admitted into the *new* cycle's realized
total.

The earlier prediction that a ≥2 s `restart_delay_ms` guarantees ≥1 s of clearance is
**refuted by measurement** (PART 7):

```
cycle starts with a prior exit  : 284
gap last-exit -> next start (s) : min=0.207  p50=2.661  max=26,597.1
under 1.000 s                   : 5
SAME WHOLE SECOND (leak window) : 5  (1.76%)
```

So the exposure is real and its measured frequency on this tape is **5 of 284 boundaries
(1.76%)**. The money consequence per event is bounded by one exit deal's four-term value.

**Why no diff is proposed.** The candidate fix is to carry a true millisecond start stamp
(`GetTickCount64()`-anchored or `TimeCurrent()`+`msc` from the triggering deal) instead of
flooring. But V8 established that the Target EA's own restart floor behaves as though it is
driven by the same whole-second `TimeCurrent()` granularity, and the aggregate money identity
in §2.11.2 is exact **including** whatever the Target did at those five boundaries. Changing the
replica's flooring would therefore change replica behaviour away from a Target behaviour that
the tape is consistent with. Per the audit's own standing rule — do not "fix" the replica toward
a specification the Target does not satisfy — **V11-A is registered in §3.6 as flagged, not
legislated**, pending an instrument that can discriminate the Target's own boundary handling.

#### 2.11.11 V11 verdict

| Directive question | Verdict | Evidence |
| --- | --- | --- |
| `ReconcileHistoryDeals()` lookback correct? | **Paraphrase** — four real components; lookback bounds only the periodic re-scan | `:3579-3626`, `:3731-3748`, `:3628-3729`, `CycleDealLedger.mqh:17-51` |
| `DEAL_TIME_MSC >= m_cycle_started_msc` applied? | **Yes**, inside `TryRecalculate()`; boundary floored to the second → **V11-A** | `CycleDealLedger.mqh:17-51`; `:1869`, `:2031` |
| Duplicate callbacks double-counted? | **No** — three independent mechanisms; 0 duplicate deal tickets in 35,447 | `:630-678`, `:3539-3577`, `CycleDealLedger.mqh:17-51` |
| Out-of-order callbacks mishandled? | **No** — 0 ticket/time inversions; recompute is order-independent by construction | PART 5 |
| Money formula exact? | **Yes, delta $0.00** at deal level and at position level | PART 2, PART 2b |
| Multi-tranche closes counted correctly? | **Yes** — keyed on the deal ticket; 24 `out by` = 12 close-by ops, 6 double-closed positions | `:667`, PARTS 3/4 |
| Capacity / lookback overflow? | **No** — per-tick queue vs cycle total is a category error; seed pass unclamped | PART 6 + §2.11.7 |

**Rating: 100.00% of the mechanism.** Every invariant the ledger depends on was tested against
the broker's own three tapes rather than assumed, and the money identity closes to the cent.
Two items are registered rather than fixed: **Finding V11-A** (whole-second cycle boundary,
5/284 = 1.76% exposure, flagged pending a discriminating instrument) and the **166 economically
inert ghost IN deals** (a dataset anomaly with $0.00 in all four money terms and 0/166 Balance
movements, licensing no diff). Three formula terms — `commission`, `fee`, `DEAL_ENTRY_INOUT` —
remain unexercised on this broker and are therefore recorded as unverified but unfalsified.

### 2.12 V12 — Account and symbol suffix auto-binding

#### 2.12.0 The two questions, restated

The directive asks exactly two things of this vector:

> `TradeSymbol=""` → `_Symbol` for any suffix? `ContractScale()=1.0` consistent?

Both are answerable without assumption. The first is a source question with a one-line answer and
a nine-step consequence chain. The second has been carried through this audit as an *assertion*
— "`ContractScale()=1.0`" — and that is not good enough, because `ContractScale()` multiplies
`cycle_target_money` on the **only exit the EA has** (§2.7). A broker quoting XAUUSD with a
contract size other than 100 would silently rescale the basket target and every cycle would end
at the wrong money. So §2.12.3 stops asserting and *identifies* the Target broker's contract size
from the tape, on 17,551 closed positions and the terminal's own open block.

#### 2.12.1 The binding chain, end to end

The symbol enters as an empty input and is resolved once, at initialisation:

```cpp
input string TradeSymbol = "";            // StraddleReplicaApp.mqh:40
   runtime.symbol=TradeSymbol;            // StraddleReplicaApp.mqh:126
```

```cpp
      m_runtime=runtime;                  // StraddleEngine.mqh:3167
      if(m_runtime.symbol=="")            // :3168
         m_runtime.symbol=_Symbol;        // :3169   <-- the auto-binding
```

`_Symbol` is the chart's symbol string **verbatim**, suffix included, so the resolution is
suffix-agnostic by construction: it never parses, strips, normalises or pattern-matches the
broker's decoration. `StraddleTypes.mqh:156` declares the field as a plain `string symbol;` — no
canonical form is stored anywhere, which is why there is nothing to get wrong.

Everything downstream then binds to the *resolved* string, not to the input:

| Consumer | Line | What breaks if the binding were wrong |
| --- | --- | --- |
| `SymbolSelect(m_runtime.symbol,true)` | `:3210-3214` | refuses init if the symbol is not selectable |
| `m_deal_ledger.Configure(magic,symbol)` | `:3215` | V11's ledger filter — a wrong string silently zeroes realized money |
| `ACCOUNT_LIMIT_ORDERS` vs `levels_per_side*2` | `:3224-3232` | refuses init if the account cannot hold 60 pendings |
| `m_tick_size` / `m_point` | `:3234-3235` | lattice rounding and stop distances |
| `if(m_tick_size<=0.0 \|\| m_point<=0.0) return false;` | `:3236-3240` | hard refusal, not a silent default |
| `m_gateway.Initialize(symbol,magic,deviation)` | `:3241` | every order request |
| `iATR(m_runtime.symbol,tf,period)` | `:3244` | ATR step mode (unused by Starwave profiles) |
| `StringFormat("StraddleReplicaV2_%I64u_%s.csv",magic,symbol)` | `:3251-3252` | telemetry filename carries the suffix |

Two of these are worth naming explicitly. `:3215` is the join between this vector and V11: the
deal ledger filters on `(magic, symbol)`, so the auto-binding is load-bearing for the money
identity proven in §2.11 — bind the wrong string and `m_cycle_realized` stays at $0.00 forever
while floating profit alone chases a target it can never reach. And `:3236-3240` is the pattern
the rest of the chain follows: on a symbol whose metadata is unavailable the engine **refuses to
initialise** rather than substituting a default, so there is no silent-fallback path to audit.

#### 2.12.2 The suffix question, measured on both tapes

The directive's "for any suffix" is not hypothetical on this dataset — the two Target tapes carry
**two different broker suffixes**, and a census sizes the exposure exactly (`tmp/a901_v12.py`
PART 1 → `tmp/out_v12.txt`):

```
  Starwave_60542_orders_history.csv          n= 10863  {'XAUUSD.u': 10863}
  Starwave_60542_full_history.csv            n=  4796  {'': 1, 'XAUUSD.u': 4795}
  tmp/report_901018.csv                      n=107932  {'XAUUSD': 107873}
```

| Tape | Symbol string | Rows | Share |
| --- | --- | --- | --- |
| Starwave 60542 orders | `XAUUSD.u` | 10,863 / 10,863 | 100.00% |
| Starwave 60542 deals | `XAUUSD.u` | 4,795 / 4,796 | 99.98% (1 blank header artifact) |
| 901018 workbook (all blocks) | `XAUUSD` (bare) | 107,873 | 100.00% of XAU-bearing cells |

So the Starwave account traded a `.u`-suffixed instrument and the 901018 account traded the bare
symbol, and **one code path served both** — because neither account's suffix ever reached the
code. `TradeSymbol=""` defers to `_Symbol` at `:3169`, and `_Symbol` is whatever the chart says.
The audit therefore answers the directive's first question affirmatively and, unusually, with a
*cross-broker* rather than a single-broker attestation: the same source, unmodified, is what
produced both tapes' symbol strings.

The corollary is a live-deployment note rather than a parity finding: because resolution is
delegated to the chart, attaching the EA to the wrong chart is the one way to mis-bind it, and the
engine cannot detect that — `XAUUSD.u` and `XAUUSD` are both perfectly valid symbols. The guard
that does exist is the order-limit and metadata refusal chain above, not a symbol whitelist.

#### 2.12.3 `ContractScale()` is identified from the tape, not assumed

The multiplier itself (`StraddleEngine.mqh:1521-1527`):

```cpp
   double ContractScale(void) const
     {
      double contract_size=SymbolInfoDouble(m_runtime.symbol,SYMBOL_TRADE_CONTRACT_SIZE);
      if(contract_size<=0.0)
         return 1.0;
      return contract_size/100.0;
     }
```

Two consumers, both scaling money: telemetry `:1244-1250` and the live evaluator `:3445-3448`:

```cpp
       double scale=ContractScale();
       double target=(m_profile.cycle_target_money>0.0
                      ? m_profile.cycle_target_money*scale
                      : m_cycle_start_balance*m_profile.cycle_target_balance_pct/100.0);
```

`SYMBOL_TRADE_CONTRACT_SIZE` is a runtime broker property and cannot be read from a CSV — but it
can be **solved for**. Every closed position on the workbook satisfies

```
    profit = dir * (close_price - open_price) * volume * contract_size
```

which inverts to `contract_size = profit / (dir * (close - open) * volume)` on every row where the
price moved and the profit is nonzero. `tmp/a901_v12.py` PART 2 runs that inversion on the whole
`Positions` block (`tmp/out_v12.txt`):

```
  rows solved      : 17,551
  rows skipped     : 81  (zero move or zero profit)
  contract_size census (top 8): [('100', 17548), ('99.97', 1), ('99.55', 1), ('18.15', 1)]
  contract_size == 100 +/- 0.5 : 17,550/17,551  (99.99%)
  => ContractScale() = contract_size/100.0 = 1.0000 on this broker
```

PART 3 then re-solves the same equation **independently**, on the terminal's own `Open Positions`
block, using the report's `Market Price` column instead of a close price — a different six rows,
a different price source, and no overlap with the 17,551:

```
  STR S2   sell 0.01 @   4085.57 ->   4094.43  profit=  -8.86  contract_size= 100.0000  OK
  STR S3   sell 0.01 @   4083.55 ->   4094.43  profit= -10.88  contract_size= 100.0000  OK
  STR B5   buy  0.01 @   4094.39 ->   4094.15  profit=  -0.24  contract_size= 100.0000  OK
  STR B6   buy  0.01 @   4095.71 ->   4094.15  profit=  -1.56  contract_size= 100.0000  OK
  STR B7   buy  0.01 @   4097.08 ->   4094.15  profit=  -2.93  contract_size= 100.0000  OK
  STR B4   buy  0.01 @   4093.25 ->   4094.15  profit=   0.90  contract_size= 100.0000  OK
  contract_size == 100: 6/6
```

**Verdict: `SYMBOL_TRADE_CONTRACT_SIZE = 100` on the Target's broker, so `ContractScale()` returns
exactly `100/100.0 = 1.0000`.** The carried assertion is now a measurement on 17,550 closed
positions plus 6 open rows from a second, independent price column.

A third, weaker corroboration comes from the report's own `Margin` figure. Gross 0.06 lots at
4094.15 with contract size 100 is 24,564.90 notional; the reported margin is **8.19**, and
24,564.90/3000 = **8.1883 → 8.19**. The identity closes — but it closes twice, at 1:3000 on gross
volume and at 1:1000 on hedged-net 0.02 lots, because the hedged account's net exposure is exactly
one third of its gross here. So the margin figure **corroborates contract size 100 without
discriminating the leverage convention**, and this audit states it as corroboration only.

#### 2.12.4 The 0.01% accounted for — all four non-exact rows, and all 81 skips

A 99.99% result is only usable if the residue is explained rather than tolerated, so
`tmp/a901_v12.py` was re-run to print the outliers verbatim (`tmp/out_v12c.txt`):

```
non-exact contract_size rows: 4
   ('100.035436', '20221196', 'buy',  '0.02', '4182.01', '4167.90', '0.00', '-28.23', ...)
   ('99.973573',  '20261614', 'sell', '0.02', '4073.58', '4092.50', '0.00', '-37.83', ...)
   ('99.545455',  '20262142', 'sell', '0.02', '4090.49', '4091.59', '-2.74', '-2.19', ...)
   ('18.154762',  '20266436', 'sell', '0.4',  '4058.22', '4064.94', '0.00', '-48.80', ...)
skipped reasons: Counter({'zero_move': 72, 'zero_profit': 9})
skipped with nonzero swap: 1
```

| Row | Solved | Cause | Contract size 100? |
| --- | --- | --- | --- |
| `20221196` | 100.0354 | reports −28.23 where 100 gives −28.22 — **one-cent rounding** | yes |
| `20261614` | 99.9736 | reports −37.83 where 100 gives −37.84 — **one-cent rounding** | yes |
| `20262142` | 99.5455 | reports −2.19 where 100 gives −2.20 — **one-cent rounding** | yes |
| `20266436` | 18.1548 | sell **0.4** lots, −48.80 where a single-price close gives −268.80 | yes (see below) |

The first three are the same ±$0.01 rounding the audit already characterised in §2.11.2 as the
broker's gross-split convention residue, and they leave the contract size unambiguous — at 0.02
lots one cent of profit is 0.5 units of contract size, which is precisely the width of the three
deviations.

The fourth is not a rounding at all, and it is not new. `20266436` is a **multi-tranche close**:
the `Positions` row carries the *aggregate* profit of several closing deals while the
`close_price` column carries only the *last* tranche's price. That is exactly the close-by
signature §2.11.8 isolated on the deal tape — the 12 close-by orders producing 24 `out by` deals
and 6 double-closed positions. Solving a single-price identity against an aggregated profit
necessarily under-reports, and 18.15 ≈ 100 × (48.80/268.80) confirms the arithmetic: the row is
consistent with contract size 100 once the aggregation is accounted for. So all four non-exact
rows are attributable, and **none of them is evidence of a contract size other than 100**.

The 81 skips are equally accounted for: **72 zero-move** (a position closed at its open price to
the cent — the equation is `0/0` and carries no information) and **9 zero-profit**. Exactly one
skipped row carries a nonzero swap, i.e. one row where money moved with no price move, which is
the expected shape of an overnight-swap-only position and again inverts to nothing.

#### 2.12.5 Why the multiplier is load-bearing, and what it is actually for

`ContractScale()` scales the **target**, never the **measurement**. Floating and realized money
both arrive already denominated in account currency (`POSITION_PROFIT + POSITION_SWAP` at
`:413-415` / `:2379`; the deal accumulator at `:3685-3691`), so the multiplier's only job is to
keep the *price-space* geometry of a cycle invariant across brokers. A broker quoting a 10×
larger contract makes every 0.01-lot leg move 10× the money per price unit, so an unscaled money
target would be hit after one tenth of the price excursion and the whole lattice would behave
differently. Multiplying the target by `contract_size/100` cancels that exactly.

On the Target's broker it is a no-op, which is the entire parity claim for this vector:

| Hypothetical `SYMBOL_TRADE_CONTRACT_SIZE` | `ContractScale()` | `STARWAVE_30` effective target | Measured? |
| --- | --- | --- | --- |
| 1 | 0.01 | $0.265 | no |
| 10 | 0.10 | $2.65 | no |
| **100** | **1.0000** | **$26.50** | **yes — 17,550/17,551 + 6/6** |
| 1000 | 10.0 | $265.00 | no |
| 0 or unavailable | 1.0 (guard `:1523-1524`) | $26.50 | n/a |

Two observations follow. First, the guard at `:1523-1524` returns `1.0` when the broker property
is unavailable, so the failure mode **coincides with the correct answer on this broker** — the
replica cannot be pushed off the Target's target by a metadata read failing. That is a fortunate
alignment rather than a proof of correctness elsewhere, and the audit records it as such. Second,
because the multiplier is exactly 1.0 here, every money figure this audit has proven — the
delta-$0.00 identity of §2.11.2, the $26.50 bracket of §2.7, the 285-cycle exit census — is
unaffected by it. `ContractScale()` is load-bearing code that is provably inert on this dataset.

#### 2.12.6 Account binding, and the five refusals

Symbol binding is one half of the vector; the account is the other. `Initialize()` runs five
refusals before it will touch a symbol, in this order:

| Check | Line | Shipped default | Fires on the Target's account? |
| --- | --- | --- | --- |
| shadow-mode file/mode validation | `:3170-3180` | `STR_RUNTIME_NORMAL` | no — normal mode skips it |
| `require_demo_account` | `:3181-3187` | `true` (`STR_REQUIRE_DEMO_DEFAULT`) | **would refuse a live account** |
| `require_bound_account` | `:3188-3193` | `false` (`STR_REQUIRE_BOUND_DEFAULT`) | no — disabled |
| `expected_account_login` mismatch | `:3194-3204` | `0` (unset) | no — unset means no binding |
| `ACCOUNT_MARGIN_MODE_RETAIL_HEDGING` | `:3205-3209` | required | no — the Target account is hedged |

The hedging requirement is not optional decoration: the strategy holds simultaneous long and short
positions on one symbol by construction, so a netting account would collapse the straddle into a
single net position and no amount of downstream code could recover the behaviour. §2.12.3's own
margin arithmetic is the independent confirmation that the Target account was hedged — gross 0.06
lots and hedged-net 0.02 lots both reconcile to the reported 8.19, which is only a meaningful
statement on an account that can hold 0.04 long and 0.02 short at once.

The shipped posture, read from the app's macro block and input list (`StraddleReplicaApp.mqh:1-12`,
`:31-33`, `:38-118`):

```cpp
   #define STR_REQUIRE_DEMO_DEFAULT true          // :2
   #define STR_REQUIRE_BOUND_DEFAULT false        // :5
   #define STR_SAFETY_ENABLED_DEFAULT false       // :8
   #define STR_DEFAULT_PROFILE STARWAVE_30        // :11
   #define STR_DEFAULT_MAGIC 26011001             // :32
```

```cpp
input ENUM_STR_PROFILE Profile = STR_DEFAULT_PROFILE;          // :39
input string TradeSymbol = "";                                 // :40
input ulong MagicNumber = STR_DEFAULT_MAGIC;                   // :41
input bool ReplicaMode = true;                                 // :42
input int InterOrderDelayMs = 100;                             // :44
input bool RequireDemoAccount = STR_REQUIRE_DEMO_DEFAULT;      // :56
input bool RequireBoundAccount = STR_REQUIRE_BOUND_DEFAULT;    // :57
input ulong ExpectedAccountLogin = 0;                          // :58
input bool SafetyEnabled = STR_SAFETY_ENABLED_DEFAULT;         // :61
```

Three of these deserve comment against the standing specification's "do NOT implement artificial
safety throttles" clause. `SafetyEnabled=false` is what makes the money target the **only** exit,
as §2.7 requires — the equity-loss, gross-lot, spread and daily-loss ceilings at `:62-65`
(`MaxEquityLossPercent=20.0`, `MaxGrossLots=2.20`, `MaxSpreadPoints=1000.0`, `DailyLossLimit=0.0`)
are all read into `SRuntimeConfig` at `OnInit()` but never consulted while `SafetyEnabled` is false.
`RequireBoundAccount=false` with `ExpectedAccountLogin=0` means no account pinning, matching a
Target that ran on two different accounts (60542 and 901018) from one code base.
`RequireDemoAccount=true` is the one guard the shipped build *does* keep armed, and it is a
deployment guard rather than a behavioural one: it gates whether the EA runs at all, and cannot
alter a single order once it does. Turning it off is a deliberate operator act, not a parity
change.

The magic number is measured, not chosen. `26011001` is the value carried by **all 10,844
EA-authored rows** of `Starwave_60542_orders_history.csv`; the remaining 19 rows carry magic 0 and
are the manual operator closes identified in §0. The in-source comment at `:13-30` also records a
real defect this indirection fixed — before the macros existed, the input initialisers hard-coded
`LATEST_30` / `901018` and `STR_DEFAULT_PROFILE` was **inert**, so every binary silently defaulted
to `LATEST_30` regardless of what it defined. That is a genuine historical divergence, already
resolved, and it is the reason this vector reads the macro block rather than trusting the enum.

One further symbol-dependent refusal sits outside the five: `ACCOUNT_LIMIT_ORDERS` against
`m_profile.levels_per_side*2` at `:3224-3232`. For a 30-per-side profile that is 60 pending orders,
and a broker or account capping pendings below 60 would truncate the lattice silently at deployment
time. The engine refuses to initialise instead. The Target's own tapes carry full 60-order
deployments (§2.2), so the limit was never binding there.

#### 2.12.7 Finding V12-A — the stale money target, in a comment *and* in a live default

Auditing the macro block against the catalogue it claims to describe turned up one stale number,
and then following that number through the source turned up a second, worse instance of it. Finding
V12-A is therefore two findings sharing one cause: the shipped-defaults summary **and** the
`CUSTOM_PROFILE` basket-target input both still carried the pre-Starwave `25`.

**V12-A(i) — the comment.** The header comment at `StraddleReplicaApp.mqh:13-30` enumerates eight
properties of the shipped `STARWAVE_30` default. Seven were exact; the eighth was stale:

| Comment claim (`:21-24`) | Catalogue truth | Line | Match |
| --- | --- | --- | --- |
| `N=30/side` | `config.levels_per_side=30` | `:467` | yes |
| `step=round(anchor/3000,2)` | `STR_STEP_ANCHOR_DIVISOR`, `anchor_divisor=3000.0` | `:468-469` | yes |
| `lots 0.01@1-10 / 0.06@11-20 / 0.15@21-30` | `SetLotTier(1,10,0.01)`, `(11,20,0.06)`, `(21,30,0.15)` | `:491-493` | yes |
| `ratchet L=2` | `lock_trigger_steps=2.0` | `:471` | yes |
| `Dpre=2` | `pre_tighten_trail_distance_steps=2.0` | `:472` | yes |
| `Tt=3` | `tighten_trigger_steps=3.0` | `:473` | yes |
| `D=1` | `trail_distance_steps=1.0` | `:470` | yes |
| `cancel-then-close` | `cancel_before_close=true` | `:479` | yes |
| **`cycle_target_money=25`** | **`config.cycle_target_money=26.5;`** | **`:478`** | **NO** |
| `restart_delay_ms=2000` | `config.restart_delay_ms=2000` | `:486` | yes |

The comment said **25**; the profile the binary actually loads uses **26.5**, the value §2.7
bracketed to `(26.41, 26.51]` from the 3-cycle censored interval over 2026-08-24 19:22–19:49. The
stale text sat at three sites — `StraddleReplicaApp.mqh:23` plus the bundler's two copies of it at
`ProfitBricks2K.mq5:5585` and `ProfitBricks2K_AllInOne.mq5:5585`.

**Part (i)'s own behavioural impact: none.** It is a comment; `Profile = STR_DEFAULT_PROFILE`
resolves to `STARWAVE_30` and `LoadProfileConfig()` reads `:478`, not the prose. Nothing in the
285-cycle exit census, the $26.50 bracket or §2.11's money identity depends on it. It is still a
finding because this is the one comment block in the codebase that presents itself as the
authoritative summary of the shipped defaults, sitting immediately above the inputs an operator
edits, and it is the same block that already documents a *previous* defect of exactly this kind (the
inert `STR_DEFAULT_PROFILE` macro). Fixed: the corrected text now occupies `App:21-27` and cites
`ProfileCatalog.mqh` as the authority rather than restating a number; both standalones carry the
correction at `:5586`.

**V12-A(ii) — the default, and this one moves money.** The sentence that closed this section in its
first draft was a hypothetical: *an operator reproducing the Target by hand through the `Custom*`
inputs would set 25.0 and diverge on every basket exit.* It was not hypothetical. The shipped source
set 25.0 for the operator:

```cpp
input double CustomCycleTargetPercent = 0.18;
input double CustomCycleTargetMoney   = 25.0;      // StraddleReplicaApp.mqh, pre-fix
```

and it did so directly beneath a block comment that promises the opposite (`App:68-77`): "Defaults
below are the measured Starwave/Target values, so CUSTOM_PROFILE is a Starwave clone out of the box
and only the tier lots and N need touching to reproduce any of the seven observed lot ladders."

The plumbing from that input to the live exit test is complete — five hops, all present, none gated
behind a flag the operator has to find:

| Hop | Site | Text |
| --- | --- | --- |
| operator input | `App:100` | `input double CustomCycleTargetMoney = 26.5;` |
| → custom struct | `App:165` | `custom.cycle_target_money=CustomCycleTargetMoney;` |
| → profile struct | `ProfileCatalog.mqh:730` | `config.cycle_target_money=custom.cycle_target_money;` |
| → live evaluator | `Engine:3446-3447` | `m_profile.cycle_target_money>0.0 ? m_profile.cycle_target_money*scale` |
| → the only exit | `Engine:3431-3537` | `CheckCycleTargets()`, §2.7's sole liquidation trigger |

`scale` is `ContractScale()`, identified in §2.12.3 as exactly `1.0000` on this broker, so the input
value *is* the dollar target with no intervening arithmetic. A 25.0 default against a measured 26.5
therefore banked every `CUSTOM_PROFILE` basket **5.66% early** — `(26.5 − 25.0) / 26.5 = 0.05660`.
That is a behavioural divergence on the EA's only exit path, not a documentation defect, and the
"6%" this section previously quoted was a rounding of it rather than a measurement.

**The 27-field sweep that isolated it.** Every `Custom*` default in the `Custom Profile` input group
(`App:67-118`) was compared against the `STARWAVE_30` case body: **26 of 27 matched exactly**, and
this one contradicted. The two fields that look like further gaps are non-divergences twice over —
they equal `ResetProfile()`'s own defaults (`ProfileCatalog.mqh:17`, `:30`) *and* they are provably
unreachable on every profile in the catalogue:

| Field | Consumer | Why inert |
| --- | --- | --- |
| `lock_offset_price = 0.2` | `StopScheduler.mqh:162` `: entry+direction*profile.lock_offset_price` | the **false** arm of the `activation_uses_trailing_distance` ternary, which every catalogue profile sets `true`; the in-source comment at `:126` records it as "dead code on EVERY" profile |
| `cycle_target_balance_pct = 0.18` | `StraddleEngine.mqh:3448` `: m_cycle_start_balance*…/100.0` | the **false** arm of `m_profile.cycle_target_money>0.0`, so a set money target always dominates |

The money target was therefore the one behaviour-carrying placeholder left in the block, and it was
the last one: the other five (`false / false / 0.0 / false / 3000`) had already been converted to
measured Starwave values in earlier rounds of this audit.

**Provenance correction.** This audit previously recorded that 25.0 "appears nowhere in the
catalogue, so the stale comment had no provenance". The first clause is true and re-verified — the
money-target census over `ProfileCatalog.mqh` returns `0.0` `:30`, `30.0` `:247`, `30.0` `:315`,
`26.5` `:478`, `6.5` `:512`, `26.5` `:546`, `12.0` `:582`, `28.5` `:616`, `17.8` `:653`, plus the
`custom` hop at `:730`, and no 25.0 anywhere — but the conclusion drawn from it was wrong. The
provenance did exist: it was the `CUSTOM_PROFILE` input default. The accurate statement is *no
catalogue profile uses 25.0; the Custom input default did, and the stale comment was describing it.*

**Both parts applied, and pinned so they cannot drift apart again.** Comment and default are
corrected in `mql5/include/StraddleReplicaApp.mqh`, both standalones are regenerated
(`0b9ced598f06bc0c`, §2.13), and a new contract test —
`test_custom_basket_target_default_matches_the_starwave_catalogue` in `tests/test_mql5_contract.py` —
parses the input default and `STARWAVE_30`'s catalogue value as floats and asserts they are equal,
instead of asserting one spelling of one number in two places and hoping both get edited together.
It also re-asserts the `(26.41, 26.51]` bracket, all three plumbing hops, and the corrected default
in both generated standalones. The suite is green at **98 tests**. Diffs in §4.5.


#### 2.12.8 Standalone parity on this vector

Both single-file builds carry the whole binding chain at identical offsets, which is a V13
anti-drift datum obtained for free while auditing V12:

| Construct | Modular | `ProfitBricks2K.mq5` | `ProfitBricks2K_AllInOne.mq5` |
| --- | --- | --- | --- |
| `input string TradeSymbol = "";` | `App:40` | `:5602` | `:5602` |
| `runtime.symbol=TradeSymbol;` | `App:126` | `:5688` | `:5688` |
| `m_runtime.symbol=_Symbol;` | `Engine:3169` | `:4869` | `:4869` |
| `ContractScale()` definition | `Engine:1521-1527` | `:3221` | `:3221` |
| telemetry consumer | `Engine:1244` | `:2944` | `:2944` |
| live-evaluator consumer | `Engine:3445` | `:5145` | `:5145` |

The `ContractScale()` bodies were compared directly (`tmp/out_v12b.txt`) and are byte-identical to
the modular one, including the `contract_size<=0.0 → 1.0` guard. Every offset above is the same in
both standalones, i.e. the two files agree with each other line-for-line on this vector as well as
with the modular source. Finding V12-A's two corrections propagate identically, which is a more
informative test of the bundler than the defect was: the rewritten shipped-defaults comment lands at
`:5586` and the corrected `input double CustomCycleTargetMoney = 26.5;` at `:5662`, in both files, at
the same offsets. Pre-fix, the stale comment had sat in both at `:5585` and the stale default in both
at `:5656`. A faithful bundler propagates whatever the includes say, defect or fix, and both
directions have now been observed on the same construct.

#### 2.12.9 V12 verdict

| Directive question | Verdict | Evidence |
| --- | --- | --- |
| `TradeSymbol=""` → `_Symbol`? | **Yes**, unconditionally, at init | `App:40` → `App:126` → `Engine:3168-3169` |
| Works for any suffix? | **Yes** — `_Symbol` is taken verbatim; no parsing or normalisation anywhere | `StraddleTypes.mqh:156`; census `XAUUSD.u` 10,863/10,863 vs bare `XAUUSD` 107,873 |
| Does the resolved string reach every consumer? | **Yes**, 8 consumers audited, incl. V11's ledger filter | `:3210-3252` |
| Silent fallback on bad metadata? | **No** — hard refusal | `:3236-3240`; `:3210-3214`; `:3224-3232` |
| `ContractScale() = 1.0` consistent? | **Yes, and now identified rather than assumed** | 17,550/17,551 closed (99.99%) + 6/6 open ⇒ contract size 100 ⇒ scale exactly 1.0000 |
| Residue explained? | **Yes** — 3 one-cent roundings + 1 multi-tranche close; 81 skips = 72 zero-move + 9 zero-profit | `tmp/out_v12c.txt` |
| Account binding refusals correct? | **Yes**, 5 checks; hedging requirement corroborated by the margin arithmetic | `:3170-3209`; §2.12.3 |
| Standalones in step? | **Yes**, byte-identical bodies, identical offsets in both | `tmp/out_v12b.txt`, §2.12.8 |
| Shipped defaults describe the shipped profile? | **No — one comment and one live default were stale**; both now fixed and pinned | Finding V12-A, §2.12.7 |

**Rating: 100.00% on the auto-binding mechanism, with Finding V12-A — one stale comment *and* one
behaviour-carrying stale default — surfaced on this vector and both now applied.** The auto-binding
is correct for any suffix because it never inspects the suffix, and this is attested across *two*
different broker decorations from one unmodified source. The `ContractScale()=1.0` claim that this
audit had been carrying as an assertion is now a measurement: `SYMBOL_TRADE_CONTRACT_SIZE = 100` is
solved from the tape on 17,550 of 17,551 closed positions and independently on all 6 rows of the
terminal's open block, with every one of the four non-exact rows and all 81 skips attributed. The
multiplier is therefore provably inert on this dataset, so no money figure elsewhere in this audit
depends on it.

Finding V12-A is **not** documentation-only, which is how this section first classified it. Part (i),
the shipped-defaults comment saying `cycle_target_money=25` where the catalogue uses `26.5`, is inert
prose. Part (ii) is the same stale number as a live `input double CustomCycleTargetMoney = 25.0`,
wired through five hops to the EA's only exit, banking every `CUSTOM_PROFILE` basket 5.66% early.
Neither part touches the `STARWAVE_30` path the Target actually ran — `LoadProfileConfig()` reads
`:478`, not an input and not the prose — so no measurement, census or bracket elsewhere in this audit
moves and the mechanism rating stands. But the divergence was real, shipped, and on the money path,
so it is registered in §3 as behavioural rather than cosmetic, and §4.5 carries three diffs: the
comment, the default, and the test that ties them to each other.

### 2.13 Vector 13 — Standalone anti-drift verification

> *"V13 Standalone Anti-Drift Verification (standalones byte-identical to bundler output? all
> contract tests passing?)"*

V13 is the only vector in this directive whose subject is the **build** rather than the strategy.
Both of its questions can be answered with one hash and one test count, and both answers are yes —
but that would only describe the current state. What follows also establishes why the state cannot
drift silently again, because it already did once.

#### 2.13.1 The generator, and the defect that motivated it

`tools/bundle_standalone.py` is the single source of truth for both single-file builds. Its own
docstring records the incident it exists to prevent: the standalones "were 33 lines behind
`mql5/include` … **They compiled cleanly and were silently a different EA.**"

That is the precise failure mode this vector must exclude, and it is invisible to every other check
in the project. A stale standalone satisfies the standing specification's own acceptance test (§7:
"compiles with 0 errors and 0 warnings on MetaEditor MT5 build 4000+"), passes any MQL5 syntax
check, and runs — while trading an older strategy. No compiler can detect it, because both files are
internally valid. Only a byte comparison against the includes can.

The API surface, for citation: `INCLUDE_DIR :39`, `TARGETS :40`, `SECTIONS :46`,
`RULE = "// " + "=" * 68` `:57`, `INCLUDE_RE :58`, `PLACEHOLDER = "// included inline"` `:60`,
`body_lines :63`, `header_of :71`, `bundle :84`, `worktree_includes :97`, `build_from_worktree :103`,
`first_divergence :108`, `digest :118`, `verify :122`, `check :144`, `write :163`, `MODES :175`.

#### 2.13.2 Three modes, three different invariants

| Mode | Rebuilds from | Compares against | What it catches |
| --- | --- | --- | --- |
| `--write` | worktree `mql5/include` | — (overwrites both targets) | the only sanctioned way to change a standalone |
| `--check` | worktree `mql5/include` | the on-disk target files | an include was edited and the standalone not regenerated |
| `--verify` | **git HEAD**'s includes | **git HEAD**'s standalone | the generator's own behaviour changed |

The current run of both read-only modes:

```
OK      mql5\ProfitBricks2K.mq5  234995 chars  0b9ced598f06bc0c
OK      mql5\ProfitBricks2K_AllInOne.mq5  234995 chars  0b9ced598f06bc0c
CHECK OK - both standalones match mql5/include

HEAD standalone :  213227 chars  f519eb715664a3f8
rebuilt         :  213227 chars  f519eb715664a3f8
VERIFY OK - bundler reproduces HEAD byte-for-byte
```

The two modes report **different** sizes and hashes, on purpose, and the difference is not a defect:
`--check` reads the worktree (234,995 chars) while `--verify` reads git HEAD (213,227 chars), so the
21,768-char gap is exactly the uncommitted parity work of this audit. A reader who expects one number
from both modes is reading the wrong invariant. On failure, `first_divergence()` `:108` reports the
first differing offset rather than a bare "differs", so a regression localises immediately instead of
starting a search.

#### 2.13.3 The closed-form line identity

A hash proves equality but explains nothing. The line identity does both: every line of the
standalone is accounted for by a rule, so an unexplained line becomes a defect by construction.

| Component | Lines | Content |
| --- | --- | --- |
| header | 20 | `:1-5` banner, `:6-10` five `#property` lines, `:11` blank, `:12-19` the five build defines plus their 3-line comment, `:20` blank |
| framing | 48 | 8 sections × 6 lines: two blanks, `RULE`, `// SECTION: <file>`, `RULE`, blank |
| bodies | 5,696 | the eight includes in `SECTIONS` order — i.e. `wc -l mql5/include/*.mqh`, not a hand-maintained constant |
| **total** | **5,764** | `wc -l mql5/ProfitBricks2K.mq5` |

`20 + 48 + 5,696 = 5,764`, exact — computed rather than asserted in `tmp/a901_v13b.py` PART 1, which
derives the framing width from the label positions in the file and confirms all eight sections use
the same 6-line block with the label as its 4th line.

#### 2.13.4 Verbatim body comparison — 5,686 identical, 10 substituted, 0 unaccounted

The identity above constrains line *counts*. PART 1 of the same probe goes further: it slices each
section's body out of the standalone and compares it to the include line for line, printing in full
any line that differs. Across all 5,696 body lines there are exactly **10** differences, and every
one of them is the same transformation — `INCLUDE_RE` matched, `PLACEHOLDER` written:

| Section | Standalone lines | Standalone text | Include text it replaced |
| --- | --- | --- | --- |
| `ProfileCatalog.mqh` | `:250` | `// included inline` | `#include "StraddleTypes.mqh"` |
| `StopScheduler.mqh` | `:1007` | `// included inline` | `#include "StraddleTypes.mqh"` |
| `StraddleEngine.mqh` | `:1704-1709` | `// included inline` ×6 | `StraddleTypes`, `ProfileCatalog`, `TradeGateway`, `CycleDealLedger`, `BasketEvaluator`, `StopScheduler` |
| `StraddleReplicaApp.mqh` | `:5597-5598` | `// included inline` ×2 | `StraddleTypes`, `StraddleEngine` |

So **5,686 of 5,696 body lines are byte-identical to the includes**, 10 are the substitution that
inlining necessarily performs, and **0 are unaccounted for**. Two independent greps close on the same
10 from opposite directions: `grep -c "// included inline"` over the standalone returns **10**, and
`grep -c '#include'` returns **0**. No local include survived the bundle, and none was introduced.
That zero is also what makes the file satisfy the specification's §7 "single standalone `.mq5` file" —
it can be dropped into `MQL5/Experts/` with no `include/` tree beside it.

This is a materially stronger claim than the hash in §2.13.2. A hash says the committed file equals
whatever the generator currently emits; both could be wrong together. The line-for-line comparison
says the generator emits the includes **verbatim** — there is no reformatting, reordering, macro
expansion or comment-stripping step anywhere in the path, so no transformation exists that could
alter semantics while keeping generator and artifact mutually consistent.

#### 2.13.5 The offset law, derived from the file and validated on 17 citations

Every citation in this audit names an include and a line — `StraddleEngine.mqh:3446`, not
`ProfitBricks2K.mq5:5146`. That is the right convention, because the includes are the editable
source. But it leaves the standalone unverifiable by a reader who only has the shipped `.mq5`. The
offset law closes that gap: one addition per section maps any include citation into either standalone.

| Section | Include lines | `// SECTION:` label | Body span | Law |
| --- | --- | --- | --- | --- |
| `StraddleTypes.mqh` | 214 | `:24` | `:27-240` | **+26** |
| `ProfileCatalog.mqh` | 751 | `:244` | `:247-997` | **+246** |
| `StopScheduler.mqh` | 193 | `:1001` | `:1004-1196` | **+1003** |
| `BasketEvaluator.mqh` | 37 | `:1200` | `:1203-1239` | **+1202** |
| `CycleDealLedger.mqh` | 63 | `:1243` | `:1246-1308` | **+1245** |
| `TradeGateway.mqh` | 380 | `:1312` | `:1315-1694` | **+1314** |
| `StraddleEngine.mqh` | 3,856 | `:1698` | `:1701-5556` | **+1700** |
| `StraddleReplicaApp.mqh` | 202 | `:5560` | `:5563-5764` | **+5562** |

The law was **derived from the file, then validated**, in that order — the probe reads the label
positions out of the standalone rather than computing them from the framing arithmetic, and only then
tests them. PART 2 pushes all 17 constructs this audit cites through the derived offsets and prints
the standalone line beside the include line at each site. **17 of 17 match; `mismatched citations:
0`:**

| Include citation | Standalone | Text at both sites |
| --- | --- | --- |
| `StraddleTypes.mqh:156` | `:182` | `string            symbol;` |
| `ProfileCatalog.mqh:17` | `:263` | `// DIV-4: measured law, not a neutral default. …` |
| `ProfileCatalog.mqh:30` | `:276` | `config.cycle_target_money=0.0;` |
| `ProfileCatalog.mqh:478` | `:724` | `config.cycle_target_money=26.5;` |
| `ProfileCatalog.mqh:730` | `:976` | `config.cycle_target_money=custom.cycle_target_money;` |
| `StopScheduler.mqh:126` | `:1129` | `// TRUE for the target, and lock_offset_price is now dead code on EVERY` |
| `StopScheduler.mqh:162` | `:1165` | `: entry+direction*profile.lock_offset_price` |
| `CycleDealLedger.mqh:17` | `:1262` | `bool TryRecalculate(const long cycle_started_msc,` |
| `StraddleEngine.mqh:1244` | `:2944` | `double scale=ContractScale();` |
| `StraddleEngine.mqh:3169` | `:4869` | `m_runtime.symbol=_Symbol;` |
| `StraddleEngine.mqh:3446` | `:5146` | `double target=(m_profile.cycle_target_money>0.0` |
| `StraddleEngine.mqh:3448` | `:5148` | `: m_cycle_start_balance*m_profile.cycle_target_balance_pct/100.0);` |
| `StraddleEngine.mqh:3826` | `:5526` | `void OnTradeTransaction(const MqlTradeTransaction &transaction,` |
| `StraddleReplicaApp.mqh:24` | `:5586` | `//   cycle_target_money=26.5, restart_delay_ms=2000)` |
| `StraddleReplicaApp.mqh:100` | `:5662` | `input double CustomCycleTargetMoney = 26.5;` |
| `StraddleReplicaApp.mqh:126` | `:5688` | `runtime.symbol=TradeSymbol;` |
| `StraddleReplicaApp.mqh:165` | `:5727` | `custom.cycle_target_money=CustomCycleTargetMoney;` |

Those 17 are not an arbitrary sample: they are the constructs §2.1 through §2.12 rest on — the money
target in its catalogue site, its `CUSTOM_PROFILE` site and its evaluator site; the DIV-4 activation
comment; the inert `lock_offset_price` arm; the symbol auto-bind; the deal-ledger recalculation
entry; and the transaction callback. The whole audit is therefore checkable against the shipped
binary, not just against the tree.

Two structural corollaries, both used by the sections above:

- **`StraddleReplicaApp.mqh` is last** (`:5563-5764`, ending exactly at the file's final line — the
  probe reports `last body ends :5764  file ends :5764`, so nothing is appended after it). An edit
  inside App therefore cannot move a `StraddleTypes`, `ProfileCatalog`, `StopScheduler`,
  `BasketEvaluator`, `CycleDealLedger`, `TradeGateway` or `StraddleEngine` citation. This is why
  §2.12.7's V12-A(ii) fix — six added lines in App — left every other standalone citation in this
  document intact while shifting only App's own.
- **The converse holds too**, and is the sharper warning: an edit in `ProfileCatalog.mqh` moves the
  offsets of the six sections after it. Any standalone line number quoted in this audit is valid only
  for the hash it was measured against, which is why §2.13.7 records the lineage rather than a single
  number.

#### 2.13.6 One binary, two filenames, one deliberate header divergence

`mql5/ProfitBricks2K.mq5` and `mql5/ProfitBricks2K_AllInOne.mq5` are the same file twice:

```
$ cmp mql5/ProfitBricks2K.mq5 mql5/ProfitBricks2K_AllInOne.mq5
IDENTICAL
$ md5sum ...
00f0b3b8951b771dc9ba12678cb37efb  mql5/ProfitBricks2K.mq5
00f0b3b8951b771dc9ba12678cb37efb  mql5/ProfitBricks2K_AllInOne.mq5
```

234,995 bytes, 5,764 lines, bundler digest `0b9ced598f06bc0c` — and the probe's own line-list
comparison agrees independently (`identical to ProfitBricks2K_AllInOne.mq5: True`). The duplication
is not a copy that can rot: both names are listed in `TARGETS` (`tools/bundle_standalone.py:40`), so
`--write` writes both from the same in-memory bundle and `--check` verifies both. There is no path by
which one filename can be stale while the other is current — which is exactly the failure the tool
was built to end (§2.13.1).

The header is the one place where the standalone is deliberately **not** the modular build:

| Define | Standalone (`:12-19`) | Modular default |
| --- | --- | --- |
| `STR_REQUIRE_DEMO_DEFAULT` | `false` | (input-driven) |
| `STR_REQUIRE_BOUND_DEFAULT` | `false` | (input-driven) |
| `STR_SAFETY_ENABLED_DEFAULT` | `false` | (input-driven) |
| `STR_DEFAULT_PROFILE` | `JUNE_2K` (`:15`) | `STARWAVE_30` |
| `STR_DEFAULT_MAGIC` | `901018` (`:19`) | `26011001` |

This is stated in the source itself rather than left to be inferred, at `:16-18`:

```cpp
// This standalone is the June-2026 $2k artifact, so it pins both the profile
// and the magic of that regime (account 901018).  The shared modular build
// defaults to STARWAVE_30 / 26011001 instead -- see StraddleReplicaApp.mqh.
```

Three checks confirm the pin is coherent rather than a leftover:

1. **The description matches the ladder it claims.** `#property description` at `:11` reads
   "0.01 (L1-15), 0.03 (L16-25), 0.06 (L26-30)", which is the `JUNE_2K` tier schedule verified in
   §2.9 at `ProfileCatalog.mqh:277-279` — the same file the header points at, in agreement with it.
2. **The magic matches the dataset.** `901018` is the magic of `ReportHistory-901018.xlsx`, the tape
   this audit's V3–V12 measurements were taken from; a standalone shipped for that regime that
   defaulted to `26011001` would not reproduce it.
3. **The three `false`s are the specification, not a relaxation.** The spec's framing clause requires
   "Do NOT implement artificial safety throttles, hard drawdown cutoffs, or conservative filters", and
   §2.7 established that the money target is the *only* exit. Pinning demo-only, bound-account and
   safety gating off at compile time makes that unconditional in the shipped artifact instead of
   dependent on an operator leaving three inputs alone.

The consequence to be explicit about: an operator who wants **Starwave** behaviour out of this
standalone must select a Starwave profile in the inputs rather than accept the pinned default, and
must expect magic `901018` unless they change it. §5 carries the related operational warning that
leftover magic-`901018` orders from a previous run are invisible to a differently-magicked instance.
Neither is a parity divergence — the strategy code is byte-identical per §2.13.4; only the two
defaults and the three compile-time gates differ, by design and with the reason recorded in source.

#### 2.13.7 Hash lineage, and the tests that pin it

The digest is not a constant to be defended — it is a fingerprint that *should* move whenever the
includes move, and the audit trail is the sequence of moves. Three digests were observed over the
V12-A repair alone:

| Digest | Step | Line delta | Source of the delta |
| --- | --- | --- | --- |
| `2d2fe9bb0d272406` | pre-V12-A | — | the state §2.12.7 opened against |
| `c12978335e4803ad` | V12-A(i) applied | **+4** | the rewritten shipped-defaults comment, `StraddleReplicaApp.mqh:13-26` → `:13-30` |
| **`0b9ced598f06bc0c`** | V12-A(ii) applied | **+6** | the justification comment now at `StraddleReplicaApp.mqh:94-99`, above the corrected `input double CustomCycleTargetMoney = 26.5;` |

The current endpoint is measured, not inferred: 5,764 lines, 234,995 chars, both filenames
(§2.13.6). The `+6` is verifiable in the source — six comment lines, `:94-99`, ending with "the one
value in this block that was a placeholder rather than a measurement." The behavioural change in that
step was one literal, `25.0` → `26.5`; the six lines are the reason it changed, written where the next
reader will trip over it.

Note what the lineage demonstrates beyond bookkeeping: **the bundler propagated a defect and a fix
through the same construct**. Pre-V12-A, both standalones carried the stale comment at `:5585` and the
stale `25.0` default at `:5656`. Post-fix, both carry the corrected comment at `:5586` and
`= 26.5;` at `:5662`. A faithful generator transmits whatever the includes say in either direction —
which is the honest statement of what §2.13 can and cannot certify. It certifies that the standalone
*is* the include tree. It does not certify that the include tree is correct; that is what §2.1–§2.12
are for. V12-A is the proof that the second question is independent of the first, because the build
was byte-perfect the whole time the default was wrong.

**The four tests that make drift a test failure rather than a discovery:**

| Test | Site | What it fails on |
| --- | --- | --- |
| `test_standalone_builds_are_current_generated_copies_of_the_includes` | `tests/test_mql5_contract.py:2025` | either standalone differing from a fresh bundle of the worktree — the `--check` invariant, as a test |
| `test_standalone_generator_round_trips_the_committed_tree` | `:2062` | the generator not reproducing the committed standalone from the committed includes — the `--verify` invariant |
| `test_standalone_sources_mirror_the_starwave_profile_catalog` | `:1652` | the Starwave catalogue values not appearing in the standalone text, independently of the hash |
| `test_custom_basket_target_default_matches_the_starwave_catalogue` | added for V12-A(ii) | `CustomCycleTargetMoney`'s default drifting away from `STARWAVE_30`'s `cycle_target_money` — the specific defect V12-A(ii) was |

The first two are structural and would have caught the 33-line drift of §2.13.1. Neither would have
caught V12-A(ii), because a stale default is perfectly bundled; that is why the third and fourth
assert on *values* rather than on equality of files. The suite is green at **98 passed in 0.48s**
(85 contract + 13 profile), with `--check` and `--verify` both exiting 0 against the same tree.

#### 2.13.8 V13 verdict

| Question | Answer | Evidence |
| --- | --- | --- |
| Standalones byte-identical to bundler output? | **Yes** — `CHECK OK`, 234,995 chars, `0b9ced598f06bc0c`, both filenames, exit 0 | §2.13.2 |
| All contract tests passing? | **Yes** — `98 passed in 0.48s` (85 contract + 13 profile) | §2.13.7 |
| Does the generator reproduce the committed artifact? | **Yes** — `VERIFY OK`, 213,227 chars, `f519eb715664a3f8`, exit 0 | §2.13.2 |
| Is every line of the standalone accounted for by a rule? | **Yes** — `20 + 48 + 5,696 = 5,764`, exact | §2.13.3 |
| Does the standalone *contain* the includes verbatim? | **Yes** — 5,686 of 5,696 body lines byte-identical; 10 differ; **0 unaccounted** | §2.13.4 |
| Are those 10 explained? | **Yes** — every one is `#include "…"` → `// included inline`; `grep -c "// included inline"` = 10 | §2.13.4 |
| Any include directive left in the shipped file? | **No** — `grep -c '#include'` = **0**; fully self-contained per spec §7 | §2.13.4 |
| Can an include citation be checked against the standalone? | **Yes** — 8-section offset law, derived from the file, **17/17 validated, 0 mismatches** | §2.13.5 |
| Are the two filenames the same file? | **Yes** — `cmp` IDENTICAL, md5 `00f0b3b8951b771dc9ba12678cb37efb`, both in `TARGETS` | §2.13.6 |
| Is the header identical to the modular build? | **No — by design**: 5 defines pinned to the June-2026 $2k regime, with the reason in source at `:16-18` | §2.13.6 |
| Can the build drift silently again? | **No** — 2 structural tests for file drift, 2 value tests for the V12-A class of defect | §2.13.7 |

**Rating: 100.00%.** Both of the directive's questions answer yes, and the vector was closed on the
stronger reading — not "the file hashes to what the generator emits", but "the file *is* the include
tree, line for line, with every difference enumerated and every remaining line mapped by a validated
offset law." No findings. No diffs licensed by V13.

One boundary, stated plainly because §2.13.7 makes it unavoidable: V13 certifies the **build**, not the
**strategy**. The artifact was byte-perfect for the entire period during which `CustomCycleTargetMoney`
defaulted to `25.0` and banked 5.66% early. A green V13 is necessary for the other thirteen vectors to
mean anything about the shipped file — it is what lets §2.1–§2.12's include citations be read as claims
about the EA an operator actually runs — but it is not evidence for any of them.

### 2.14 Vector 14 — Race conditions & execution robustness

> *"V14 Race Conditions & Execution Robustness (behaviour under fast ticks? does
> `TryCloseOneOwnedPosition()` handle transient rejections without head-of-line blocking?)"*

V14 is the one vector where the adversarial stance cannot be discharged by the tape. Across both
datasets — 65,605 orders — there are **zero rejected orders**. The rejection path is therefore
unexercised in the evidence, and no amount of forensic work on 17,632 positions will falsify or
confirm it. That is a fact about the data, not an excuse: it means V14 must be argued structurally,
from the code, and it means the honest verdict is *unfalsified* rather than *observed*.

What can be proved is stronger than it first sounds. Both of the directive's questions have
mechanical answers, and the second one has an answer that was arrived at by getting it **wrong first**
— the naive anti-stall fix is exactly the change that destroys cadence parity, and the resolution is
visible in source with the measurement that forced it.

#### 2.14.1 Fast ticks cannot accelerate order flow — the timer is the clock

`OnTick()` (`StraddleEngine.mqh:3404-3429`) is deliberately almost empty. It handles exactly two
states and returns for every other one:

```cpp
if(m_state==CYCLE_IDLE) { … if(StartCycle()) DeployOne(); return; }   // :3406-3421
if(m_state!=CYCLE_RUNNING)                                            // :3422
   return;                                                            // :3423
ReconcileLevels();                                                    // :3424
if(!m_profile.stop_updates_on_timer) UpdatePositionStops();           // :3425-3426
CheckCycleTargets();                                                  // :3428
```

`CYCLE_DEPLOYING`, `CYCLE_CANCELING`, `CYCLE_CLOSING`, `CYCLE_RESTARTING` and `CYCLE_HALTED` all fall
through `:3422` and do nothing. So during the two events V2 and V5 measure — the deployment burst and
the flatten sweep — **`OnTick()` is a no-op**, and the cadence is a pure function of the timer period:

```cpp
int timer_ms=MathMax(20,m_runtime.inter_order_delay_ms);   // :3378
if(!EventSetMillisecondTimer(timer_ms))                   // :3379
```

With `inter_order_delay_ms = 100` that is a 100 ms timer, and every paced action — deploy legs 2…2N
(`:3770`), closes (`:3783`), cancels (`:3786`), the restart drain (`:3801-3802`), re-arms (`:3779`) —
is reached only from `OnTimer()` (`:3750-3824`). A tick storm cannot compress a burst, because ticks
are not in the burst's control path at all. This is what makes V2's 112 ms and V5's 113 ms measurable
quantities rather than artifacts of quote density, and it is corroborated on the Target side by V5's
own result: **0 of 3,114 Target gaps fall below 95 ms**. A tick-driven close path could not produce
that distribution.

Two things a fast tick *can* do, both correct:

1. **Start a cycle up to one timer period earlier.** The `CYCLE_IDLE` branch is duplicated on tick
   (`:3406-3421`) and timer (`:3757-3768`) with the same three guards — alignment hold, the
   `m_pending_deal_count>0` race guard, and shadow-mode — so whichever clock arrives first opens the
   cycle. Only the *first* leg goes out there; legs 2…2N are timer-paced regardless.
2. **Trail a stop.** For the audited profiles this is the intended path: `stop_updates_on_timer` is
   **`false`** for `STARWAVE_30` (`ProfileCatalog.mqh:483`) and `JUNE_2K` (`:266`) — only `LATEST_30`
   sets it `true` (`:401`), and `ResetProfile()` defaults it `false` (`:40`). So the V4 ratchet runs
   on ticks and the order machinery runs on the timer.

That split is the architectural answer to "behaviour under fast ticks": **price-reactive work is
tick-driven, paced work is timer-driven.** A faster tick stream makes the ratchet more responsive —
which is what a stop is for — and leaves deployment, cancellation and liquidation cadence untouched.

#### 2.14.2 The head-of-line question, answered by `m_close_skip`

The directive's second question names a genuine tension. Two properties must hold simultaneously:

- **One close request per invocation**, or the sweep fires a burst and breaks V5's 113 ms cadence.
- **A stalled ticket must not block the basket**, or one quote-rejected position pins 29 others open.

Satisfying either alone is trivial. The member that satisfies both is declared with its rationale
(`StraddleEngine.mqh:41-45`):

```cpp
// How many owned positions TryCloseOneOwnedPosition() steps over before it
// makes its single close attempt.  This exists so that ONE close request per
// tick and "a stalled ticket must not block the basket" can both hold at
// once
int               m_close_skip;
```

`TryCloseOneOwnedPosition()` (`:2899-2930`) is the whole mechanism:

| Line | Construct | Role |
|---|---|---|
| `:2901-2902` | `if(OrphanLeakActive()) return TryCloseOneTrackedPosition();` | leak-mode dispatch (DIV-6) |
| `:2904` | `for(int index=PositionsTotal()-1;index>=0;index--)` | descending walk — V5's LIFO |
| `:2907` | ownership filter (magic + symbol) | never touches foreign positions |
| `:2909` | `owned++` | counts owned positions seen |
| **`:2910`** | **`if(owned<=m_close_skip) continue;`** | **steps over the stalled prefix** |
| `:2917-2918` | `m_last_close_at=TimeCurrent(); m_close_skip=0;` | success → rewind cursor |
| `:2919-2920` | `LogEvent("close",…); return true;` | one request, then return |
| **`:2922-2924`** | **`m_last_close_at=TimeCurrent(); m_close_skip++; return false;`** | **failure → advance cursor, still return** |
| `:2928-2929` | `m_close_skip=0; return false;` | walk-past → rewind |

Both exits from the loop body `return`. There is no path that attempts a second close in the same
invocation. The anti-stall property is carried entirely by the *cursor*: a ticket whose close failed is
stepped over on the **next** invocation, one pacing interval later, not in the same one.

The cost of that is bounded and small. If the newest *k* positions are all stalling, the sweep spends
*k* intervals walking to a closable one, and every success resets the cursor to zero (`:2918`) so the
next pass starts from the top again. If the cursor walks off the end of the list — because the stalled
tickets closed by other means, or the list shrank — it rewinds (`:2926-2929`):

```cpp
// Either there are no owned positions, or the cursor has walked past the
// last one.  Rewind so the next pass starts from the top again.
m_close_skip=0;
return false;
```

So the cursor is monotone-increasing only within a stalling episode and is bounded above by
`PositionsTotal()`. It cannot run away, and it cannot leak across a boundary: it is reset in
`BeginClose()` (`:2774`), on both `CYCLE_CANCELING → CYCLE_CLOSING` transitions in `CancelOneOrder()`
(`:2991`, `:3003`), and on cycle reset (`:3138`).

**This design is a correction, and the source says so** (`:2796-2805`):

> *"Issues AT MOST ONE close request per invocation. An older version kept walking the position list
> after a failed `ClosePosition` and closed the next one in the same tick, which is how several
> synchronous `OrderSend` round-trips ended up inside one 100 ms tick. … The anti-stall property that
> motivated that loop is preserved by `m_close_skip`: a ticket whose close failed is stepped over on
> the NEXT invocation rather than in the same one, so a single quote-delayed ticket still cannot block
> the basket — it just costs one pacing interval instead of firing a burst."*

That is the naive fix and its refutation in one place. Walking on after a failure *does* solve
head-of-line blocking; it also puts multiple synchronous broker round-trips inside one pacing interval,
which is precisely the cadence signature V5 proves the Target does not have.

The same logic exists twice, because DIV-6 gave the engine two sweeps. `TryCloseOneTrackedPosition()`
(`:2854-2883`) is the `replica_orphan_leak=true` twin: it walks `CollectTrackedPositionTickets()`
instead of `PositionsTotal()`, but carries the identical cursor at `:2862`, `:2873`, `:2878`, `:2881`.
So the answer to the directive's question holds under **both** settings of the leak flag — including
`STARWAVE_30`, where the flag is `true`.

**Answer: yes.** Transient rejections are handled, without head-of-line blocking, and without the burst
the obvious fix produces.

#### 2.14.3 A rejected close must not be read as "flat"

`m_close_skip` keeps a stalled ticket from blocking the sweep. It does not, by itself, stop the
*caller* from misreading a failed close. `CloseOnePosition()` (`:2932-2962`) closes that gap:

```cpp
if(CyclePositionCount()>0 && !CloseIntervalElapsed())   // :2934  pacer gate
   return;
if(TryCloseOneOwnedPosition())                          // :2936  one request
   return;
// A close that FAILED must not be read as "the basket is flat".  Without      :2938
// this the engine declared cycle_complete/flat on a transient rejection and   :2939
// dropped into CYCLE_RESTARTING with positions still open, which is the       :2940
// state that used to hammer them at the timer period.                         :2941
if(CyclePositionCount()>0)                              // :2942
   return;                                              // :2943
```

Only after both a failed attempt **and** a confirmed-empty cycle book does the function fall through to
the terminal branch — shadow reset (`:2944-2951`), then `CYCLE_RESTARTING` with `cycle_complete` /
`restart_wait` when `cancel_before_close` is set (`:2952-2958`), else `CYCLE_CANCELING` (`:2959-2960`).

The comment names a **two-bug chain**, and the second bug is the interesting one: the state it fell
into, `CYCLE_RESTARTING`, used to drain positions on its own at the timer period instead of at the
close pacer. The fix hoisted the gate into a single predicate every close must pass through
(`:2779-2794`):

```cpp
// … drained them at the OnTimer period (100 ms) instead of at              :2779-2782
// close_interval_seconds.  On 111638511 that produced runs of 2-4 market   :2783
// closes 39-127 ms apart on consecutive order tickets -- a cadence the     :2784
// Target never shows (0.2% of its stream in sub-100 ms clusters, versus    :2785
// 11.0% of ours).  Every close request must pass through here.             :2786
bool CloseIntervalElapsed(void) const                                       // :2787
  {
   if(m_shadow_reset_active || m_halted)                                    // :2789
      return true;                                                          // :2790
   …
```

That measurement — **0.2% of the Target's close stream in sub-100 ms clusters versus 11.0% of ours** —
is why this belongs in V14 and not in a robustness appendix. The defect was a *race* (a rejected close
racing the flat check), but its observable signature was a **cadence divergence**, i.e. a V5 failure.
Fixing the race fixed the cadence.

The `CYCLE_RESTARTING` handler (`:3788-3820`) now routes through the same predicate. Its ordering is
itself race-relevant — orders first, then positions, then the clock:

```cpp
if(OwnedOrderCount()>0)            { TryCancelOneOwnedOrder(); break; }   // :3789-3793
if(CyclePositionCount()>0)                                                // :3795
  {
   // Paced, exactly like CYCLE_CLOSING … Cycle-scoped, so orphans cannot      :3796-3800
   // pin the engine in CYCLE_RESTARTING forever
   if(CloseIntervalElapsed())                                             // :3801
      TryCloseOneOwnedPosition();                                         // :3802
   break;
  }
if(AlignmentHoldActive()) …                                               // :3805-3810
if(TimeCurrent()-m_restart_started_at>=(m_profile.restart_delay_ms+999)/1000)  // :3811-3812
   m_state=CYCLE_IDLE;                                                    // :3814
```

Three properties fall out. The drain is **paced** by the same predicate as `CYCLE_CLOSING`, so a
restart cannot produce a burst. It is **cycle-scoped** (`CyclePositionCount()`, not
`PositionsTotal()`), so the 153 orphans DIV-6 documents cannot pin the engine in `CYCLE_RESTARTING`
indefinitely. And the restart floor is only consulted *after* the book is clear, so a stalling close
extends the restart delay rather than racing it — which is the correct direction for V8, since the
Target's own restarts never began with positions open.

The one deliberate bypass is `:2789-2790`: `m_shadow_reset_active || m_halted → return true`. Both are
terminal, operator-initiated conditions where pacing parity is no longer the objective, and both are
outside the measured tape.

Four contract assertions pin this shape (`tests/test_mql5_contract.py`):

| Line | Assertion | What it prevents |
|---|---|---|
| `:325` | `"bool CloseIntervalElapsed(void) const" in engine` | the predicate being inlined away again |
| `:330` | `engine.count("CloseIntervalElapsed()") >= 2` | one caller regaining an unpaced path |
| `:334` | `"if(CyclePositionCount()>0 && !CloseIntervalElapsed())"` | the `CloseOnePosition` gate exactly |
| `:338-339` | `"if(CloseIntervalElapsed())"` + `"TryCloseOneOwnedPosition()"` in the restart drain | the 100 ms drain returning |

with `test_flat_detection_bypasses_position_close_interval` (`:469`) pinning the halt/shadow bypass and
`test_flatten_sweep_walks_the_position_list_newest_first` (`:409`) pinning both cursor constructs —
`assert "if(owned<=m_close_skip)" in body` (`:446`) and `assert "m_close_skip++" in body` (`:447`) —
under the comment (`:444-445`): *"The anti-stall cursor must survive the direction, otherwise a
quote-rejected ticket blocks the basket instead of costing one pacing interval."* The direction and the
cursor are pinned together because DIV-6 changed the direction and could have dropped the cursor.

#### 2.14.4 The async deal path: idempotent, order-independent, bounded

V11 proved the ledger's *arithmetic* (delta **$0.00** over 35,447 deals, **0** duplicate tickets). V14
asks the adversarial question behind it: the arithmetic was exact on a tape where **25.3% of deals share
a millisecond with another deal (peak 11 in one millisecond)** — so what stops a burst of simultaneous
`DEAL_ADD` callbacks from double-counting, dropping, or mis-attributing a deal?

Three independent defences, each at a different layer.

**(1) Idempotence — a deal cannot be counted twice.** `QueuePendingDeal()` (`:3557-3576`) opens with a
triple guard:

```cpp
if(deal_ticket==0 || DealAlreadyProcessed(deal_ticket) || PendingDealIndex(deal_ticket)>=0)   // :3559-3561
   return;                                                                                    // :3562
```

`DealAlreadyProcessed()` (`:637`) rejects a ticket the ledger has consumed; `PendingDealIndex()`
(`:3539`) rejects one already queued. A duplicate callback, a callback that races
`QueueMissingHistoryDeals()`, and a re-delivery after a terminal restart are all absorbed here. The
synchronous path has the mirror of this: on a callback whose metadata *is* ready,
`OnTradeTransaction()` removes any queued copy before consuming it (`:3841-3844`), so the two paths
cannot both process the same deal.

**(2) Order-independence — a partial record is deferred, never consumed.** MT5 can deliver
`TRADE_TRANSACTION_DEAL_ADD` before the history record is fully materialised. The engine treats that as
the normal case (`:3836-3838`):

```cpp
if(!HistoryDealSelect(transaction.deal) || !DealMetadataReady(transaction.deal))   // :3836-3837
   QueuePendingDeal(transaction.deal);                                             // :3838
```

`DealMetadataReady()` (`:1647+`) requires **all eight** of `DEAL_TIME_MSC`, `DEAL_MAGIC`, entry,
position id, order ticket, volume, price and symbol to read successfully. A record missing any one of
them is queued, not partially consumed — which matters because V11's money identity is computed from
volume × price and its cycle attribution from `DEAL_TIME_MSC`; a half-read deal would corrupt both.
`ProcessPendingDeals()` (`:3731-3748`) then retries with **remove-on-success only**:

```cpp
while(index<m_pending_deal_count)
  {
   … if(!ready) { index++; continue; }                       // :3737-3742
   if(ProcessSelectedDeal(deal_ticket)) RemovePendingDealAt(index);   // :3743-3744
   else index++;                                             // :3745-3746
  }
```

A not-yet-ready deal keeps its slot and is retried on the next timer tick. Arrival order is therefore
irrelevant to the outcome: the queue converges on the same ledger regardless of the sequence in which a
same-millisecond burst is delivered.

**(3) Boundedness — the queue cannot grow without limit or fail silently.** The backlog is a fixed
array: `#define STR_PENDING_DEAL_CAPACITY 256` (`:11`), `m_pending_deal_tickets[…]` (`:67`),
`m_pending_deal_count` (`:68`). On overflow the engine does **not** silently drop:

```cpp
if(m_pending_deal_count>=STR_PENDING_DEAL_CAPACITY)   // :3563
   { PrintFormat(…); return; }                        // :3564-3570
```

256 is generous against the measured worst case — the peak same-millisecond cluster on the 901018 tape
is 11 deals, and a full 30-level basket liquidation is 30 deals spread over ~3 s of paced closes — but
the diagnostic print means an unmeasured burst that *did* exceed it would leave a trace in the log
rather than a quiet accounting hole. That is the correct trade for an audit artifact: bounded memory,
loud failure.

**The attribution guard.** The subtlest race in the engine is not double-counting but *mis-attribution*:
a deal from cycle *n* landing after cycle *n+1* has opened would be booked against the wrong cycle,
which would break V7's per-cycle `$0.00` reset and V11's cycle-scoped ledger simultaneously. The engine
refuses to open a cycle while any deal is unreconciled, on **both** clocks:

| Clock | Site | Code |
|---|---|---|
| tick | `:3414-3415` | `if(m_pending_deal_count>0) return;` |
| timer | `:3764-3765` | `if(m_pending_deal_count>0) break;` |

Duplicating the guard is necessary precisely because §2.14.1's `CYCLE_IDLE` branch is duplicated: a
fast tick is the one thing that can start a cycle off-timer, so the guard has to sit on the tick path
too. Without it, the fastest tick after a liquidation would be the one most likely to mis-attribute.

`QueueMissingHistoryDeals()` (`:3579-3626`) closes the last hole — a callback that never arrives at all.
It runs **first** on every timer tick (`:3752`), ahead of `ProcessPendingDeals()` (`:3753`), so the
history sweep and the callback path feed one queue with one idempotence check rather than two
independent ledgers. `test_timer_reconciles_deals_missing_from_trade_callbacks`
(`tests/test_mql5_contract.py:268`) pins that ordering.

Net: the async path is idempotent by ticket, order-independent by deferral, bounded by capacity with a
diagnostic, and cycle-safe by a guard on both clocks. That is the structural reason V11's `$0.00`
identity held on a tape where a quarter of the deals shared a millisecond — the exactness was not luck.

#### 2.14.5 The deployment-side race: one retry, then abandonment

The close path is not the only place a broker rejection can stall the machine. V2's open question — what
the Target did on its 5 skipped interior levels — was answered as skip-and-advance, and DIV-5 implemented
it. V14's question about that implementation is different: **can a rejection loop, burst, or run
unbounded?**

`DeployOne()` (`:2059-2120`) is bounded by construction. The slot space is two passes over the lattice:

```cpp
int sweep_slots=2*m_profile.levels_per_side;   // :2061   first pass: B1,S1,…,BN,SN
int retry_slots=4*m_profile.levels_per_side;   // :2062   tail pass: one retry per deferred level
```

so a deployment issues **at most 4N sends** — 120 for `STARWAVE_30`, 80 for `STARWAVE_20` — no matter how
many rejections occur. The retry pass is a *tail* pass, not an inline retry: a rejected level is marked
deferred and re-attempted only after every first-pass level has been tried.

The tail pass fast-forwards rather than ticking through empty slots (`:2072-2075`):

```cpp
while(m_deploy_index>=sweep_slots && m_deploy_index<retry_slots &&
      !DeployDeferred(m_deploy_index-sweep_slots))
   m_deploy_index++;
```

That loop is why the retry leg lands **one `inter_order_delay_ms` after the last first-pass leg** rather
than 2N intervals later. The source records the measurement it was fitted to (`:2063-2071`): the first
six `HISTORICAL_60` bursts put the retry at **110 / 113 / 111 / 111 / 117 / 116 ms** after the final
first-pass leg, whereas one timer tick per skipped slot would have placed it **~12 s after S60**. Note
what the fast-forward is *not*: it is not a burst. It consumes no sends and issues no orders — it only
advances an index inside one invocation, then falls through to the single send that invocation is
allowed.

The retry is strictly single-shot, and the ordering of the two statements is the whole point
(`:2113-2120`):

```cpp
// Clear the mark BEFORE the retry attempt, so a second failure abandons the
// level for the rest of the cycle instead of queueing a third attempt.
```

Clearing after a successful send would be equivalent; clearing after a *failed* send would re-mark the
level and admit an unbounded retry chain. Clearing first makes abandonment the default and success the
exception, which is the safe direction.

The degenerate case — all 4N slots rejected — is handled explicitly (`:2076-2098`): the engine logs
`deployment_empty` / `all_levels_rejected` and drops to `CYCLE_RESTARTING` rather than sitting in
`CYCLE_DEPLOYING` with an empty book. This branch is honestly labelled unreachable on the evidence: the
worst real deployment on either tape armed **39 of 50** levels (Starwave, 2026-08-21) and the worst on
the 901018 tape lost only level 1 (**118 of 120** legs, `HISTORICAL_60`). It exists so that a total
rejection storm degrades into a restart instead of a hang.

Three contract tests pin the retry semantics:
`test_rejected_deployment_level_is_deferred_to_one_tail_retry_then_abandoned` (`:752`),
`test_deployment_retry_pass_never_repends_a_level_that_already_placed` (`:828`, asserting the
`!DeployDeferred(m_deploy_index-sweep_slots)` guard at `:854` / `:882` and the helper body at `:861`), and
`test_deploy_deferred_mark_survives_reconcile_and_dies_at_cycle_boundaries` (`:899`) — the last of which
is a race test in its own right: the deferred mark must survive a `ReconcileLevels()` landing mid-burst,
and must not survive into the next cycle.

#### 2.14.6 What the tape can and cannot falsify

The adversarial stance requires stating the limit of this vector plainly.

**Both tapes contain 0 rejected orders in 65,605.** Every order in the evidence either filled, was
cancelled, or expired. There is therefore **no observation of the replica's rejection path, and no
observation of the Target's either.** The rejection branch is *unfalsified*, not confirmed, and V14's
rating is a rating of the mechanism, not of a measured agreement.

That cuts symmetrically, which is worth being explicit about: because the Target's rejection handling is
equally unobservable, **"100% same" cannot be established by measurement on this vector in either
direction.** No amount of further forensics on these two datasets will change that. Claiming a measured
parity here would be the kind of overreach this audit is supposed to catch.

What *can* be established is a shared upper bound. Any rejection-handling policy that retried inline
would leave a signature in the close and open cadence, and that signature is measurable:

| Observable | Target | Replica |
|---|---|---|
| gaps below 95 ms in the close stream | **0 of 3,114** | impossible by construction (§2.14.1, §2.14.2) |
| sub-100 ms clusters, share of stream | **0.2%** | pre-fix **11.0%**, post-fix gated by `CloseIntervalElapsed()` |
| sends per deployment | ≤ 4N implied (118 of 120 worst case) | ≤ 4N by construction (`:2061-2062`) |
| same-millisecond deal clusters absorbed | peak **11** | queue capacity **256**, loud on overflow |
| ledger identity across those clusters | — | delta **$0.00** over 35,447 deals, **0** duplicates |

So the Target, whatever its internal policy, demonstrably did **not** burst; and the replica
demonstrably **cannot**. That is a genuine parity statement about the observable consequence of
rejection handling, even though the branch itself is unobserved.

One near-miss deserves recording, because it is the only place the tape shows a sweep failing to leave
the book flat: DIV-6's orphan census — **153 orphans, 148 of which survived at least one complete sweep,
66 of them 61 or more**. A rejection-based explanation for that was considered and rejected: sustained
rejections on the same tickets would have produced retry clustering, and the close stream contains none
(0 of 3,114 gaps under 95 ms). The surviving explanation is *tracking scope* — the Target does not close
what it does not track — which is what `replica_orphan_leak` implements. The orphan evidence is
therefore consistent with the rejection path being genuinely unexercised on the Target too, rather than
exercised and hidden.

**Residue, named rather than papered over:** the replica's behaviour on `TRADE_RETCODE_REQUOTE`,
`PRICE_CHANGED`, `INVALID_STOPS`, `NO_MONEY` and a broker-side kill of an in-flight close is derived from
code reading and the pinning tests, not from data. Reproducing it would require a broker simulator or a
strategy-tester run with injected rejections; that is out of scope for a forensic parity audit against a
fixed tape, and it is listed as an open item rather than claimed as done.

#### 2.14.7 V14 verdict

| # | Invariant | Evidence | Status |
|---|---|---|---|
| 1 | A fast tick cannot accelerate paced order flow | `OnTick()` returns for every state but IDLE/RUNNING — `Engine:3422-3423`; period = `MathMax(20,inter_order_delay_ms)` — `:3378` | **VERIFIED** |
| 2 | Ratchet is tick-driven for every audited profile | `stop_updates_on_timer=false` — `ProfileCatalog.mqh:40`, `:266`, `:483`, `:517`; `true` only `:401` | **VERIFIED** |
| 3 | At most one close request per invocation | both loop exits `return` — `Engine:2917-2920`, `:2922-2924` | **VERIFIED** |
| 4 | A stalled ticket cannot block the basket | `if(owned<=m_close_skip) continue;` `:2910` + `m_close_skip++` `:2923` | **VERIFIED** |
| 5 | The cursor is bounded and cannot leak | reset on success `:2918`, on walk-past `:2928`; boundaries `:2774`, `:2991`, `:3003`, `:3138` | **VERIFIED** |
| 6 | Same guarantee under `replica_orphan_leak=true` | `TryCloseOneTrackedPosition()` `:2854-2883`, dispatch `:2901-2902` | **VERIFIED** |
| 7 | A failed close is not read as "flat" | `:2938-2943` | **VERIFIED** |
| 8 | The restart drain is paced and cycle-scoped | `if(CloseIntervalElapsed()) TryCloseOneOwnedPosition();` `:3801-3802` | **VERIFIED** |
| 9 | Duplicate / out-of-order deal callbacks are absorbed | triple guard `:3559-3562`; `DealMetadataReady()` `:1647+`; remove-on-success `:3743-3746` | **VERIFIED** |
| 10 | The deal backlog is bounded and fails loudly | `STR_PENDING_DEAL_CAPACITY 256` `:11`; overflow print `:3563-3570` | **VERIFIED** |
| 11 | No cycle opens with an unreconciled deal, on either clock | `:3414-3415` (tick), `:3764-3765` (timer) | **VERIFIED** |
| 12 | Deployment is bounded at ≤ 4N sends with a single-shot retry | `:2061-2062`, `:2072-2075`, `:2113-2120`, degenerate guard `:2076-2098` | **VERIFIED** |
| 13 | Contract tests pin all of the above | `tests/test_mql5_contract.py:98`, `:268`, `:325-339`, `:409`, `:446-447`, `:469`, `:752`, `:828`, `:899` | **VERIFIED** |
| 14 | The rejection branch is exercised by the evidence | **0 rejected orders in 65,605** — neither EA's rejection path is observable | **UNFALSIFIED** |
| 15 | Observable burst signature matches | Target **0 of 3,114** gaps < 95 ms, **0.2%** sub-100 ms clusters; replica cannot burst by construction | **CONSISTENT** |

**Rating: 100.00% of the mechanism; the rejection branch is unfalsified on the tape, not confirmed.**
No findings. No diffs.

The boundary, stated as precisely as V13's: **V14 certifies that no race can change *what* the EA does,
only *when* — and every "when" that matters is pinned by `CloseIntervalElapsed()` and the timer period.**
It does not certify behaviour on a broker rejection, because no rejection exists in 65,605 orders to
certify against. The two questions the directive asked are answered mechanically and affirmatively; the
question it did not ask — *is the rejection policy identical?* — is unanswerable from this evidence, and
saying so is part of the answer.

---

## 3. Findings register

Every finding raised anywhere in this audit is recorded here with its class and its disposition —
including the ones that did not survive. The purpose is symmetric: nothing raised is silently
dropped, and nothing settled is re-raised. Six classes are used.

| class | meaning |
|---|---|
| **DIVERGENCE — APPLIED** | a real difference from the Target, proven on the tape, already fixed in the shipped source with a pinning test |
| **DIVERGENCE — OPEN** | a real difference, proven, not yet implemented; exact diff supplied in §4 |
| **RETRACTED** | I raised it, my own data refuted it, and no diff is licensed |
| **NOT A DIVERGENCE** | looked like one and is not — a build switch, a broker convention, or an operator action |
| **FLAGGED** | a candidate difference the evidence *bounds* but does not point-identify; deliberately not legislated |
| **INSTRUMENT DEFECT** | a defect in my own measurement, found and fixed, with the superseded figure named |

The distinction between the last two matters and is the reason this section exists. A flagged
finding is a fact about the Target that the tape underdetermines; an instrument defect is a fact
about *me*. Both are failure modes of an audit that claims 100%, and both are enumerated rather
than smoothed over.

### 3.0 Master table

| ID | vector | subject | class | disposition | § |
|---|---|---|---|---|---|
| DIV-1 | V2 / V6 | `PlaceLevel()`'s crossed-price recovery gate `IsHistoricalProfile()` alleged "too narrow" | **RETRACTED** | no diff — **do not widen the gate** | §3.5 |
| DIV-2 | V3 | `STR AVB` / `STR AVS` — out-of-ladder 0.05-lot market legs, `HISTORICAL_50` only, n=28 | **DIVERGENCE — OPEN** | the audit's one unimplemented Target behaviour; diff §4.1 | §3.14 |
| DIV-3 | V3 / V5 | 2,724 of the Target's basket closes carry **no** comment | **NOT A DIVERGENCE** — build fingerprint | modelled as `stamp_close_comment`, applied | §3.12 |
| DIV-4 | V4 | activation writes the first stop at the **trailing distance**, not at `entry ± 0.20` | **DIVERGENCE — APPLIED** | 5 source edits, 3 contract tests, Python mirror fixed | §3.13 |
| DIV-5 | V2 | level 1 is dispatched **last**, not first — skip-and-advance, then retry at the tail | **DIVERGENCE — APPLIED** | 4 source edits, 4 contract tests | §3.4 |
| DIV-6 | V5 | `cancel_before_close` inherited `false` on four of twelve profiles | **DIVERGENCE — APPLIED** | 4 catalogue lines, no engine change | §3.11 |
| — | V4 | 14 negative attested locks tape-wide | **NOT A DIVERGENCE** | 9 operator-authored, 5 measurement noise at 1–7 cents | §3.1 |
| — | V5 / V6 | the Target orphans positions it has stopped tracking (153 of them) | **NOT A DIVERGENCE** | build switch `replica_orphan_leak`, applied | §3.2 |
| — | V4 | `[1.00, 2.00)` band occupancy on the Starwave tape | **NOT A DIVERGENCE** | poll granularity, not the ratchet law | §2.4 |
| H-f | V5 | "one close per market tick" | **RETRACTED** | refuted by the close-gap distribution | §3.3 |
| H-g | V5 | "the close gap is a synchronous `OrderSend` round-trip" | **RETRACTED** | refuted by the same distribution | §3.3 |
| V8-A | V8 | `LATEST_30` `restart_delay_ms = 20000` against a measured ≈22 s floor | **FLAGGED** | proposed diff §4.3, **not applied** | §3.6, §3.7 |
| V8-B | V8 | `JUNE_2K`'s `restart_delay_ms = 1000` override | **FLAGGED** | proposed diff §4.4, argued against **in-source** | §3.6, §3.7 |
| V10-A | V10 | a trend-rescue signature present on the tape with **0 fills** | **FLAGGED** | tape-only; licenses no diff | §3.6 |
| V10-B | V10 | 34 Starwave per-cycle ladders that no shipped profile models | **FLAGGED** | candidate `STARWAVE_30_MID2`, carried to §5 | §3.6 |
| V11-A | V11 | cycle boundary quantised to a whole second (5/284 = 1.76%) | **FLAGGED** | no diff — the Target shares the quantisation | §3.6 |
| V12-A(i) | V12 | shipped-defaults comment stale at `cycle_target_money = 25` | **APPLIED** | comment corrected on both carriers | §3.15 |
| V12-A(ii) | V12 | live `input CustomCycleTargetMoney = 25.0` against a measured 26.5 | **APPLIED** | default corrected (5.66% early bank removed), pinned by test | §3.15 |
| — | V4 | `close_price` used as a stop-loss estimator | **INSTRUMENT DEFECT** | superseded by the broker-attested `[sl <price>]` | §3.9 |
| — | V5 – V14 | further defects in my own instruments, each with its superseded figure | **INSTRUMENT DEFECT** | measurement corrected; no code change | §3.10 |

### 3.1 The 14 negative attested locks — NOT a divergence

**The observation.** Across the whole 901018 tape, 14 positions carry a broker-attested stop whose
signed distance from the entry is *negative*: `dir*(sl − open) < 0`, i.e. the stop was written on the
**losing** side of the fill. The replica cannot produce this. Nine of the fourteen sit in
`AGGRESSIVE_30`'s era, where the census is 9 of 28 attested S/L positions, worst
**−10.559 steps (−7.18 in price)**.

**Why this is not a near-miss.** Both candidate activation branches are *floored at the entry*:

```
fixed-offset branch : locked = entry + dir*0.20                 → dir*(locked − entry) = +0.20
trailing branch     : locked = favorable − dir*D*step, gated on
                      dir*(favorable − entry) >= D*step         → dir*(locked − entry) >= 0
```

Substituting a market-anchored write into its own gate gives `locked = favorable − D >= 0` **for
every market price**. A negative is therefore outside the *range of the function*, not an unlikely
draw from it. No parameterisation of either branch — no `D`, no `lock_offset_price`, no rounding
mode — reaches these fourteen rows. If they were EA-authored, the ratchet law derived in §2.4 would
be wrong, not merely imprecise. So this had to be settled, not bounded.

**Five independent tests, all pointing the same way** (census retained in-source at
[ProfileCatalog.mqh:196](mql5/include/ProfileCatalog.mqh#L196)–[:209](mql5/include/ProfileCatalog.mqh#L209)):

1. **Not stale data.** The broker-attested `[sl X]` price equals the position's own stop field to
   the cent in **all 28** rows of the era, so nothing was measured against a superseded snapshot.
2. **Not a lattice mis-measurement.** Re-deriving each row's step from its own deployment burst
   clears **0 of 9**. The sign does not depend on which step I use.
3. **Not a broadcast.** The nine share only three distinct prices. Solving each shared-price group
   for the market level it would imply, then asking whether that market passes the activation gate
   for the other members of its own group, succeeds for only **0/3, 0/2 and 5-of-9**. A genuine
   timer-driven broadcast passes for *all* members by construction.
4. **Price texture is human.** The violating prices are **16× more likely** to be whole-dollar and
   **6.6× more likely** to be round-10c than the era's own population of stop prices.
5. **Adjacency to a hand action.** Two of the nine sit **0.109 s** and **30 s** from a
   `PositionCloseBy` — an operation with **no call site anywhere in this EA** (§3.11).

**Disposition.** Nine are **operator-authored**: someone set stops by hand on a live account. The
remaining five, all in other eras, are **measurement noise at 1–7 cents** — one tick of rounding on
a one-cent grid, indistinguishable from `+0.00`. Neither group is evidence about the replica.
**No code change. Do not re-raise.** §1's forward promise at line 92 and the in-source pointer
"See parity audit DIV-6 / section 3.1" at
[ProfileCatalog.mqh:209](mql5/include/ProfileCatalog.mqh#L209) both resolve here.

### 3.2 The orphan-position leak — NOT a divergence, a build switch

**The observation.** The Target loses track of positions. 153 positions on the 901018 tape outlive
the cycle that opened them; **148** of them survive at least one *complete* basket sweep, and **66**
survive **61 or more** sweeps. A replica that closes every position it can see would have retired all
153 on the first sweep after each was orphaned, so this is a genuine behavioural difference and not a
bookkeeping artefact.

**The decisive test — the one that turns a leak into a build fact.** An orphan is not merely
un-closed; it is *un-managed*. **Not one of the 153 ever received an `[sl <price>]` order**, while
**all 1,311** tracked positions did. If the Target still held these in its level array they would
have been ratcheted; they were not. The positions are therefore invisible to *both* the stop walker
and the close walker — a single lost handle, not two independent policies.

**How it is modelled.** As a profile flag, `replica_orphan_leak`, not as engine policy — so the
behaviour is a property of the *build era* being replicated and can be turned off without editing
the engine. It gates two sites, and only these two:

- **Re-arm.** `PlaceLevel()`'s admission test at
  [StraddleEngine.mqh:1556](mql5/include/StraddleEngine.mqh#L1556)–[:1558](mql5/include/StraddleEngine.mqh#L1558)
  reads `if(level_state.has_pending || (!OrphanLeakActive() && level_state.has_position)) return true;`
  — with the leak active an *open position* on a level no longer blocks a fresh pending at the same
  price, matching the Target's re-arms onto occupied levels. A live **pending** still blocks, on both
  paths; the parity comment at
  [:1552](mql5/include/StraddleEngine.mqh#L1552)–[:1555](mql5/include/StraddleEngine.mqh#L1555)
  states exactly that asymmetry.
- **Close.** `TryCloseOneOwnedPosition()`'s leak twin at
  [StraddleEngine.mqh:2854](mql5/include/StraddleEngine.mqh#L2854)–[:2883](mql5/include/StraddleEngine.mqh#L2883)
  walks only *tracked* positions, so an untracked position is never swept.

`ResetProfile()` sets it `false`; `STARWAVE_30` sets it `true`. The switch, not a global policy
change, is what keeps the pre-Starwave eras replayable.

**Disposition.** **NOT a divergence** — implemented, tested, and era-scoped. Retracted along the way:
an earlier "59.81 % orphan rate" was an artefact of pooling eras; measured per-cycle it is **0.00 %**
in the eras that do not set the flag. **Do not quote 59.81 %.** Whether the EA *should* carry an
orphan **policy** (adopt / ignore / alert) is a product question, not a parity question, and is
carried to §5.

### 3.3 Close cadence — H-f and H-g refuted, not merely unsupported

Two hypotheses about the ~105 ms spacing between consecutive basket closes were raised and both are
**dead**, on the tape's own gap distribution:

- **H-f — one close per market tick.** Refuted: the gaps cluster far too tightly and too uniformly
  around a machine value to be sampling XAUUSD tick arrivals, whose inter-arrival distribution on
  this symbol is nothing like it.
- **H-g — the gap is a synchronous `OrderSend` round-trip.** Refuted: a round-trip would inherit the
  broker's latency spread, and the observed spread is far narrower than the pending-dispatch
  round-trips measured on the same account in the same minutes.

What survives is the timer: the close walk retires **one** position per timer callback, so the gap is
the *timer period*, and the p50 of **105 ms / 111 ms** (versus **103 ms** for the pending lattice on
the same builds) is one clock, not three. The full derivation is §2.5 and lines 591–592 record the
refutation. Both hypotheses are listed here so neither is re-proposed as an explanation for a close
gap in some future window.

### 3.4 DIV-5 — the level-1 deferral — DIVERGENCE, APPLIED

**The observation.** In 70 of 285 deployment bursts the interleave is not `B1,S1,B2,S2,…`. Every
single inversion is *the same event*: the level-1 pending is not dispatched **first**, it is
dispatched **last**, after `S60`. The burst-tail transition is `S60→S1` ×37, `S60→B1` ×31,
`S1→B1` ×3 — **never anything else** — and levels 2..N are in perfect interleave in **all 285**
bursts. The naive reading (a broken interleave) is wrong; there is one displaced leg, not a scrambled
ladder.

**Mechanism, proven quantitatively.** A `BUY STOP` must sit at or above `ask + stops_level*point`,
a `SELL STOP` at or below `bid − stops_level*point`. Level 1 is the only level one step from the
anchor, so it is the only level that can fail that test. With `anchor = mid`:

```
placeable on the first pass  ⟺  step >= spread/2 + stops_level*point  ≈  0.15 + 0.50  =  0.65
```

The tape's measured knee is **(0.64, 0.68]** — the prediction and the observation agree to one cent
of the grid. Per era, exactly as the inequality demands:

| era | step range | level-1 leads | level-1 deferred |
|---|---|---|---|
| `HISTORICAL_60` | 0.37 .. 0.78 | — | **68** |
| `HISTORICAL_50` | 0.75 .. 1.68 | **99** | 0 |
| `STARWAVE_30` | 1.32 .. 1.39 | **103** | 0 |

Steps straddling 0.65 defer; steps clear of it never do. Nothing else in the burst changes.

**The deferred leg returns at its exact original lattice price**, not at a re-anchored one — the two
raw instances: 2026-07-02 21:52:35, anchor 4120.67, step 0.46, tail leg **4121.13 = anchor + 1×step**;
2026-07-08 14:04:33, anchor 4065.01, step 0.55, tail leg **4065.56**. Nine bursts (7 `HISTORICAL_60`
+ 2 `STARWAVE_30`) end `GONE`: deferred, retried, still un-placeable, dropped — the retry is bounded,
not a spin. Missing-leg census: `['B1']` ×34, `['S1']` ×27, `[]` ×5, `['S1','S2']` ×1,
`['S1','S15'..'S18']` ×1.

**This is what answers V2's rejection question, and it is worth being explicit about why.** The
directive asks what the Target did "on broker rejection (REQUOTE / PRICE_CHANGED) — skip-and-advance
or halt". The order-state census is `filled 35,430 + canceled 19,312 + **rejected 0**`: there is no
rejection anywhere in 54,742 orders to answer from. The question is therefore **not decided by
rejection evidence — it is decided by the deferral evidence above**, which shows
**skip-and-advance, then retry the skipped slot at the tail at its original price**. That is a
stronger answer than the one asked for, because it is measured rather than inferred, but it is an
answer about *pre-flight un-placeability*, not about a broker `retcode`. See §2.14 for the residue.

**Applied.** `DeployOne()` marks the slot `deploy_deferred`
([StraddleTypes.mqh:205](mql5/include/StraddleTypes.mqh#L205)) and advances `m_deploy_index`;
`DeployDeferred()`
([StraddleEngine.mqh:2050](mql5/include/StraddleEngine.mqh#L2050)–[:2057](mql5/include/StraddleEngine.mqh#L2057))
re-dispatches after `SN`. Four source edits, four contract tests; the ~92-line derivation is retained
in-source at
[StraddleEngine.mqh:2148](mql5/include/StraddleEngine.mqh#L2148)–[:2242](mql5/include/StraddleEngine.mqh#L2242).
Cadence is preserved through the displacement: median **112 ms** overall, deferred-leg gaps
110 / 113 / 111 / 111 / 117 / 116 / 139 ms.

### 3.5 DIV-1 — RETRACTED

**What I claimed.** That the crossed-price recovery path in `PlaceLevel()` is gated too narrowly.
When a re-arm's target price has been crossed by the market, the replica converts the pending into an
immediate market entry stamped `STR ORB` / `STR ORS` — but only for two profiles:

```cpp
   bool IsHistoricalProfile(void) const                    // StraddleEngine.mqh:1542-1546
     {
      return(m_profile.profile==HISTORICAL_50 ||
             m_profile.profile==HISTORICAL_60);
     }
```

used at [StraddleEngine.mqh:1564](mql5/include/StraddleEngine.mqh#L1564) as
`if(IsHistoricalProfile() && !level_state.recovery_done)`, with the comment literal chosen at
[:1575](mql5/include/StraddleEngine.mqh#L1575). I proposed widening it to all profiles, on the theory
that a behaviour this fundamental could not be era-scoped.

**What the tape says.** Every crossed-price recovery the Target ever authored:

| literal | n | era split |
|---|---|---|
| `STR ORB` | 38 | `HISTORICAL_50` 4, `HISTORICAL_60` 34 |
| `STR ORS` | 54 | `HISTORICAL_50` 7, `HISTORICAL_60` 47 |

**All 92 fall inside exactly the two profiles `IsHistoricalProfile()` admits**, and zero fall
outside — including across 2,809 `STARWAVE_30` positions, where a wider gate would have had ample
opportunity to fire and did not. The gate is not a conservative approximation of the Target; it is a
measurement of it. Widening it would have manufactured market entries the Target never made, in the
one era we are trying hardest to match.

**Disposition. RETRACTED. Do not widen the gate; the DIV-1 diff must not be applied.** This is the
reason the shipped numbering has a deliberate gap at 1 — `DIV-1` appears nowhere in the source,
because nothing was changed. The identifier is retained here so that the absence reads as a decision
rather than an oversight.

### 3.6 Flagged, not legislated

Five findings are real observations that the tape **bounds but does not point-identify**. Each could
be "fixed" by picking the value that best fits 285 cycles — and each such fix would be an
extrapolation dressed as a measurement. They are recorded, not applied. The rule I held to: *a
constant may be written into the catalogue only when the evidence excludes every neighbouring value,
not merely when it prefers one.*

| ID | observation | why it is not legislated |
|---|---|---|
| **V8-A** | `LATEST_30` carries `restart_delay_ms = 20000`; the era's measured restart floor is ≈**22 s** | The estimator is a censored interval — `(restart_delay_ms + 999)/1000` compared against a whole-second `TimeCurrent()` (§3.7) admits a ±1 s band, so 20000 and 22000 are **both** inside the bracket that the observed floor implies. Diff proposed in §4.3, deliberately unapplied. |
| **V8-B** | `JUNE_2K` overrides `restart_delay_ms` to **1000** where its neighbours use 2000–3000 | The catalogue's own in-source comment argues *for* the override on that era's evidence. Reversing it would overturn a documented finding with a weaker one. Diff proposed in §4.4 and **argued against**; **do not reverse the in-source comment**. |
| **V10-A** | a trend-rescue signature is present on the 901018 tape with **0 fills** | Tape-only: a signature that never filled constrains the *trigger* but says nothing about the *action*, so there is no volume, side or price to match. Licenses no diff. |
| **V10-B** | **34** Starwave cycles deploy per-cycle lot ladders that no shipped profile models; the largest coherent cluster is `.01/.04/.12 @ 10/20/30` over **31 cycles** | Adding `STARWAVE_30_MID2` would be a *new profile*, i.e. new behaviour, on 31 cycles of evidence. That is a product decision, not a parity repair. Carried to §5. |
| **V11-A** | the cycle boundary is quantised to a whole second — `(long)m_cycle_started_at*1000` at [StraddleEngine.mqh:1869](mql5/include/StraddleEngine.mqh#L1869) and [:2031](mql5/include/StraddleEngine.mqh#L2031) — mis-binning **5 of 284** cycles (**1.76 %**) | The Target's own ledger shows the same quantisation, so "fixing" it would move the replica *away* from the Target. Flagged as a shared imprecision, not a divergence. |

One further bound belongs here rather than in V10's body: `trend_rescue_drawdown_money = 400.0` is
**bounded, not point-identified**. The tape excludes values far from it but does not distinguish 400
from its immediate neighbourhood, because the trigger fired too few times to separate them. The
constant stays as shipped and is labelled as a bound wherever it is cited.

### 3.7 V8's micro-divergence — "exact 2.0 s" is false for **both** EAs

V8 asks whether `restart_delay_ms = 2000` means an exact 2.0-second restart floor. It does not, and
the interesting part is that it does not for the Target either — so this is a shared imprecision, not
a gap.

The RESTARTING drain compares a **second-granularity** clock against a millisecond constant rounded
up to whole seconds:

```cpp
   // StraddleEngine.mqh:3811-3812
   ...(m_profile.restart_delay_ms+999)/1000   compared against whole-second TimeCurrent()
```

Two consequences, both measurable:

1. **The constant is quantised on the way in.** `2000 → 2 s`, but so does `1001 → 2 s` and
   `2000 → 2 s` alike; any value in `(1000, 2000]` produces the identical floor. The catalogue's
   millisecond precision is therefore *not* observable at this site.
2. **The comparison is quantised on the way out.** A whole-second `TimeCurrent()` means the realised
   wait is anywhere in `[delay − 1 s, delay]` depending on where inside the second the cycle ended.
   The realised floor is a **band**, never a point.

This is exactly why V8-A cannot be legislated (§3.6): the estimator that reports "≈22 s" for
`LATEST_30` is a censored interval, and any constant `T` is admissible when `lo < T <= hi` for every
clean cycle in the era. The Target's own restarts show the same one-second staircase, with restart
gaps landing on whole seconds far more often than a millisecond timer would produce — so the
replica's quantisation is a *match*, and removing it would be the divergence.

**Disposition.** No code change. V8 is scored **100 % of the mechanism** with two constants flagged;
their proposed diffs are §4.3 and §4.4, and neither is applied. The one figure to keep out of future
write-ups: **do not restate "restart_delay_ms = 2000 gives an exact 2.0 s floor"** — it is false on
both sides of the comparison.

### 3.8 V5 artifact retractions

Five V5 figures were produced by defective instruments and are retracted. They are listed with their
replacements because each one, taken at face value, would have licensed a wrong edit to the close
walk:

| retracted figure | replacement | the edit it would have licensed |
|---|---|---|
| LIFO conformance **62.73 %** | **96.04 %** after excluding operator sweeps → **1.0000** operator-free | re-flipping the close walk to ascending — i.e. breaking a perfect match |
| cancel-before-close **71.43 %** | **95.57 %** with DIV-6 applied; **168/168 = 100.00 %** EA-authored | inventing a mixed-order policy to explain operator flattens |
| `imm_asc 5/7`, `cnl_desc 2/7` | superseded by the full 271-liquidation census (§3.11) | a "sometimes ascending" branch on n=7 |
| PART 3b's "both sides" test | mislabelled — it tested one side | a symmetry claim the data never made |
| the "latent vacated-level hazard" | refuted; no vacated level is ever re-armed out of order | a defensive guard with no referent |

**Standing prohibitions from this section.** Do not quote 62.73 % or 71.43 %. Do not re-flip the
close walk to ascending without first showing the Target's inversion rate below 0.5 in
`sweep_lifo.py`. Do not quote `audC.js`'s 99.34 % / 90.83 % / 52.05 %.

### 3.9 The SL-slippage correction — an instrument defect, superseded, no code change

**The defect.** Early ratchet work on the 901018 tape estimated the stop level from the *close price*,
scoring `dir*(close − sl)/step`. On that account **98.62 %** of stop-loss closes land at or **worse**
than the recorded stop, and only **13.57 %** land exactly on it. The close price is therefore a
*downward-biased* estimator of the stop with a heavy tail — every band statistic derived from it is
shifted by an amount that varies with market conditions, not with the ratchet law. Any `[a,b)`
occupancy computed this way is meaningless, and the two-stage trough (§2.4) would be either invented
or erased depending on the era's slippage.

**Why the Starwave tape is a different instrument.** On Starwave, `close_price − sl_recorded_price` is
**0.00 on all 1,311** stop-loss closures — the broker filled every stop exactly at its price, so there
the close *is* an exact measurement. The two tapes are not comparable instruments, and pooling them
was the original error.

**The hierarchy this established** (§0.2, implemented in
[tools/forensics/attested_stop.py:16](tools/forensics/attested_stop.py#L16)–[:21](tools/forensics/attested_stop.py#L21)):

```
1. broker-attested  [sl <price>]  order comment   ← the only per-write, time-stamped record
2. position.stop_loss field                       ← final snapshot only; earlier writes are lost
3. close_price                                    ← INVALID as a stop estimator
```

All V4 conclusions in this audit are computed from tier 1, with tier 2 used only to prove tier 1 is
not stale (§3.1, test 1).

**Related, and kept distinct.** Basket-sweep value slippage `vSweep − vPre` is wide and two-sided —
p05 **−18.96**, p25 −0.90, p50 **+1.40**, p75 +10.12, p95 **+42.98**, min **−409.80**, max +95.72 —
which is why the money exit is scored against the *pre-sweep* basket value and never against realised
sweep proceeds. That is a property of market closes, not of stops: stop fills on Starwave have
**zero** slippage, so nothing was "given back" at the stop.

**Disposition.** A **data-quality supersession with no code change** — the EA never reads close prices
to drive the ratchet; only my instrument did. **Standing prohibition: never re-derive the ratchet from
close prices, and do not quote any fill-price-derived V4 band figure.**

### 3.10 Measurement-instrument defects found and fixed

An audit that claims 100 % has to account for its own instruments, so every defect I found in my own
measurement is listed with the figure it superseded. None of these changed the EA; all of them would
have changed a *conclusion about* the EA, and several would have licensed a wrong edit.

**(A) Data-side defects.**

| # | defect | superseded figure | corrected figure |
|---|---|---|---|
| 1 | close price used as a stop estimator (§3.9) | all fill-derived V4 band occupancies | attested `[sl <price>]`, tier 1 |
| 2 | `HISTORICAL_60` money-exit target measured across cycle boundaries | V7 p50 **255.71** (and **193.66**) | **31.37 / 31.28** |
| 3 | V8 restart-band census counted censored intervals as observations | `[2,3)` = **2/7** | **49/77** |
| 4 | LIFO conformance pooled operator sweeps with EA sweeps | **62.73 %** | **96.04 %** → **1.0000** operator-free |
| 5 | orphan rate pooled eras that do and do not set the leak flag | **59.81 %** | **0.00 %** per-cycle in non-leak eras |
| 6 | Starwave ratchet scored pooled instead of per-cycle | the pooled band shape | per-cycle: `[1,2)` = **0/2809** |
| 7 | V10 rescue census counted signature rows as fills | **32 fills**, p50 **10,228 s** | **0 fills** (V10-A, §3.6) |
| 8 | cycle-index off-by-one between two probe scripts — `a901_v911.py` numbers cycles `i+1`, `a901_v910.py` does not | any cross-quoted cycle number | **§2.10 uses v910 numbering** |
| 9 | `tmp/out_v912f.txt` renders Profit in the Volume column | every volume in that file | **do not quote any volume from it** |
| 10 | `a901_v13.py` dropped the final line when a file lacked a trailing newline | line counts off by one | fixed in `a901_v13b.py` via `lines_of()` |
| 11 | report-footer figures read from the wrong summary block | "Open Positions **7**", "Working Orders **56**", "**165** unmatched" | **6**, **51**, **166** |
| 12 | `audC.js`'s conformance rates computed on an unsegmented stream | **99.34 % / 90.83 % / 52.05 %** | superseded by the per-era censuses |
| 13 | the "12 volume mismatches" in PART 4 and the "40 volume-mismatch re-arms" | both read as defects | **neither is a defect** — `build_deployments()` returns dicts, so the comparison was type-mismatched, not value-mismatched |

Two data-side defects remain **open** and are carried to §5 rather than claimed as fixed:
`tools/forensics/dataset.py`'s `_burst_clusters()` segmenter (lines 247–284), which mis-splits bursts
whose tail is deferred (§3.4), and `tmp/a901_traildist.py`'s docstring, which claims its `D` estimator
needs "no model assumption at all" — it assumes the ratchet is monotone, which is exactly what it is
being used to test.

**(B) Citation and bookkeeping defects.** These are cheaper to make and more expensive to leave: a
wrong line number in a parity audit is indistinguishable, to the next reader, from a wrong claim about
the code.

| # | defect | as carried | as verified |
|---|---|---|---|
| 14 | DIV-1's gate citation | `PlaceLevel()` at `:1546`, gate at `:1572` | `IsHistoricalProfile()` **`:1542-1546`**, `PlaceLevel()` **`:1548`**, gate **`:1564`**, comment literal **`:1575`** |
| 15 | DIV-5's **subject** | "deployment skip-and-advance on broker rejection" | **the level-1 deferral** forced by `step >= spread/2 + stops_level*point`; skip-and-advance-then-retry is the *implementation*, and the finding is decided by deferral evidence, not rejection evidence (§3.4) |
| 16 | §1 executive rows for V11 / V12 / V14 | stale stubs written before the vectors closed | rewritten to the final scores and findings |
| 17 | two standalone hash pins | superseded digests quoted as current | lineage recorded: `2d2fe9bb0d272406` → `c12978335e4803ad` → **`0b9ced598f06bc0c`** |
| 18 | `StraddleReplicaApp.mqh` line citations | drifted by the edits that fixed V12-A | re-grepped after every edit |
| 19 | the contract assertion `"config.anchor_divisor = 3000.0"` | treated as pinning the value | **satisfiable by a comment** — and `LOW_RISK_30` writes it *with* spaces, so the assertion is weak; recorded, not strengthened, because tightening it would fail on a formatting change rather than a behavioural one |
| 20 | ownership of the `m_close_skip` assertions at `tests/test_mql5_contract.py:433-447` | attributed to the test at `:469` | they belong to `test_flatten_sweep_walks_the_position_list_newest_first` at **`:409`** |
| 21 | "`25.0` appears nowhere in the source" | stated flatly | true of `ProfileCatalog.mqh` **only**; the provenance was the `CUSTOM_PROFILE` **input default** (§3.15) |
| 22 | Finding V12-A's class | logged as documentation-only | **two parts, one of them a live behavioural default** — reclassified and applied (§3.15) |

Three further bookkeeping items settled rather than corrected: both ghost-position hypotheses are
**refuted**; the "39,926.20 matches nothing" puzzle is **resolved** (`18,203.37 + 21,722.83`); and the
prediction that a ≥2 s restart floor implies ≥1 s of order-book clearance is **refuted** — the observed
minimum is **0.207 s**.

**The two rules these produced, which the rest of this audit is written under.** First: *never derive a
citation from a `sed` offset or from memory — grep the construct*, because an edit above a cited line
silently invalidates every citation below it. Second: *recover a label's definition from a primary
source before asserting it* — defects 14 and 15 were both caught by refusing to write a register entry
whose subject I had not re-read.

### 3.11 DIV-6 — `cancel_before_close` — DIVERGENCE, APPLIED

**The observation.** When the money target is hit, the Target **cancels every working pending first**
and only then closes the basket. Four of the twelve shipped profiles inherited `cancel_before_close =
false` from `ResetProfile()` and would have closed into a live lattice — re-arming levels as the sweep
walked, on the very eras whose tapes prove the opposite.

**The census, retained in-source** at
[ProfileCatalog.mqh:88](mql5/include/ProfileCatalog.mqh#L88)–[:101](mql5/include/ProfileCatalog.mqh#L101),
over all 271 terminal liquidations on the 901018 tape:

| era | liquidations | cancel-first | close-first | interleaved |
|---|---|---|---|---|
| `HISTORICAL_50` | 95 | **95** | 0 | 0 |
| `HISTORICAL_60` | 72 | **71** | **1** | 0 |
| `AGGRESSIVE_30` | 2 | **1** | 0 | 1 |
| `LOW_RISK_30` | 1 | **1** | 0 | 0 |
| `STARWAVE_30` | 101 | **91** | 0 | 10 |
| **total** | **271** | **259** | **1** | **11** |

**259/271 = 95.57 %** strictly cancel-first, and **exactly one** close-first anywhere on the tape.

**The single exception is not the EA.** Cycle 169's sweep is preceded by a `PositionCloseBy`
**0.232 s** earlier — and `PositionCloseBy` has **no call site in this EA**, on either side. It is a
manual operator flatten. `AGGRESSIVE_30`'s one interleaved row (cycle 171) is the same story with a
`close by` **0.109 s** ahead of it, scrambled ticket order and 2 ms gaps, where the EA's own gaps are
~105 ms. Excluding those two operator sweeps, **the four eras DIV-6 changed are 168/168 = 100.00 %**
cancel-first. The 11 interleaved rows are cycles where the cancel burst and the close burst overlap in
time, so the ordering is not separable from the tape at all — they are neither evidence for nor against,
and are counted out rather than assumed favourable.

**Attribution risk, bounded.** A cancel landing near a cycle boundary could be credited to the wrong
cycle; measured, that is **106 of 19,312 cancels = 0.55 %**, which cannot move a 95.57 % result.

**Applied with no engine change.** `BeginClose()` already implemented both orderings; the divergence was
purely which profiles selected which. Four catalogue lines set `cancel_before_close = true`, each with
its own era's census in the comment above it, so the evidence travels with the constant. Pinned by the
tests at
[tests/test_mql5_contract.py:2373](tests/test_mql5_contract.py#L2373)–[:2487](tests/test_mql5_contract.py#L2487).
Full derivation at lines 497–534.

### 3.12 DIV-3 — the basket-close comment — NOT a divergence, a build fingerprint

**The observation.** The spec says basket closes carry `STR CLOSE`. On the 901018 tape **2,732**
closing orders carry **no comment at all** — and the replica stamped every one of them. That looked
like a protocol divergence in V3.

**It is one mechanism, not two.** Three measurements collapse the two populations into a single code
path with a different literal:

1. **Both resolve identically.** All **3,742** closing orders in the two families resolve to
   `DEAL_ENTRY_OUT` — **2,732/2,732** and **1,010/1,010**. Nothing about the *action* differs.
2. **Both run on the same clock.** p50 gap **105 ms** (empty) and **111 ms** (`STR CLOSE`) against
   **103 ms** for the pending lattice on the same builds — one timer, three populations.
3. **The windows partition cleanly, with no overlap**, at the **2026.07.13 12:28** changeover:

| comment | n | eras | window |
|---|---|---|---|
| *(empty)* | 2,732 | `HISTORICAL_50` **1,392**, `HISTORICAL_60` **1,332** | 2026.06.23 16:17 → the changeover |
| `STR CLOSE` | 1,010 | `AGGRESSIVE_30` **9**, `LOW_RISK_30` **11**, `STARWAVE_30` **990** | the changeover → end of tape |

(1,392 + 1,332 = 2,724 are attributable to a single identified cycle window; the remaining 8 straddle a
boundary and are counted out.) **Zero** empty-comment closes appear after the changeover and **zero**
`STR CLOSE` closes appear before it. A behavioural difference does not switch on a calendar date and
respect era boundaries to the minute; a **rebuild** does.

**How it is modelled.** As a profile flag, so the literal is a property of the build era:

```cpp
   // StraddleEngine.mqh:2894-2897
   string CloseComment(void) const
     {
      return(m_profile.stamp_close_comment ? "STR CLOSE" : "");
     }
```

declared at [StraddleTypes.mqh:75](mql5/include/StraddleTypes.mqh#L75) with its four-line evidence
comment at [:67](mql5/include/StraddleTypes.mqh#L67)–[:74](mql5/include/StraddleTypes.mqh#L74), sited
immediately above `TryCloseOneOwnedPosition()`. `ResetProfile()` sets it **`true`**; exactly
`{HISTORICAL_50, HISTORICAL_60}` set it **`false`**; `LoadCustomProfile()` exposes **no operator input**
and inherits `STR CLOSE` through `ResetProfile(config)`, so an operator cannot accidentally select the
retired literal. Both close sites route through the one accessor — pinned by
[tests/test_mql5_contract.py:2156](tests/test_mql5_contract.py#L2156) and
[:2195](tests/test_mql5_contract.py#L2195).

**Disposition.** **NOT a divergence** in behaviour; a divergence in *metadata* that is now era-exact.

### 3.13 DIV-4 — the activation law — DIVERGENCE, APPLIED

**The two candidate branches.** When a position first qualifies for a stop, the first write is either

```
fixed-offset :  locked = entry     + dir*lock_offset_price        (= entry ± 0.20)
trailing     :  locked = favorable − dir*trail_distance*step      (one distance behind the extreme)
```

and they are distinguishable, because the fixed-offset branch can **never** produce a signed lock
distance strictly inside `(0, 0.20)` — 0.20 *is* its minimum, exactly.

**The falsification, on both large eras.** Signed lock distance `dir*(sl − open)` over every attested
`[sl <price>]` write:

| era | attested writes | strictly inside `(0, 0.20)` | min | at 0.19 / 0.20 / 0.21 | negative |
|---|---|---|---|---|---|
| `HISTORICAL_50` | **4,094** | **351 = 8.57 %** | **+0.01** | 22 / 18 / 17 | 0 |
| `HISTORICAL_60` | **7,952** | **1,068** | **+0.01** | 47 / 57 / 55 | 0 |

The forbidden interval is not merely occupied, it is *densely and smoothly* occupied right down to one
cent of the grid, with no accumulation at 0.20 — the signature of a continuous market-anchored write,
not of a constant. **`activation_uses_trailing_distance = true`**, and the fixed-offset reading is dead
on 12,046 writes. (The zero-negative column is what makes §3.1's fourteen negatives so decisive: this
branch is floored at 0 by construction, so a negative is out of range, not out of luck.)

**The second stage is separable from the first, and must not be copied across eras.** Whether the
ratchet is one-stage or two shows up as occupancy of the `[1.00, 2.00)` band:

| era | `trail_distance_steps` | `[1,2)` occupancy |
|---|---|---|
| `HISTORICAL_50` | inherits **2.0** → single-stage | **951/4,094 = 23.23 %** |
| `HISTORICAL_60` | inherits **2.0** → single-stage | **23.04 %** |
| `STARWAVE_30` | **1.0** → two-stage | **0/2,809 = 0.00 %** |

A profile that trails at 2.0 steps *lives* in that band; a profile that tightens to 1.0 steps
**evacuates** it completely. The catalogue therefore records, in-source, that `HISTORICAL_50` and
`HISTORICAL_60` **deliberately do not set** `trail_distance_steps` — with the standing instruction
**"do not copy `trail_distance_steps = 1.0` here"**, because doing so would erase a 23 % band that the
tape says is occupied.

**Applied.** Five source edits, three contract tests, plus the Python mirror corrected so the two
implementations cannot drift. `ResetProfile()` carries the default and the derivation at
[ProfileCatalog.mqh:17](mql5/include/ProfileCatalog.mqh#L17)–[:25](mql5/include/ProfileCatalog.mqh#L25);
each era's own census sits above its own flag.

### 3.14 DIV-2 — `STR AVB` / `STR AVS` — the ONE open divergence

**The observation.** Two order-comment literals exist on the Target tape that the replica can recognise
but cannot author:

| literal | n | side | volume | era | first → last |
|---|---|---|---|---|---|
| `STR AVB` | **14** | all **buy** | uniform **0.05** | `HISTORICAL_50` only | 2026-06-24 01:39:41.884 → 2026-07-02 14:31:25.006 |
| `STR AVS` | **14** | all **sell** | uniform **0.05** | `HISTORICAL_50` only | 2026-06-24 01:46:39.428 → 2026-07-01 15:38:58.439 |

All 28 are `direction = in` — `{'in': 14}` and `{'in': 14}` — so they **open** positions.

**Four facts that constrain what they can be.**

1. **Not lattice legs.** `HISTORICAL_50`'s ladder is `0.01 @ 1-15 / 0.03 @ 16-25 / 0.06 @ 26-50`.
   **0.05 is not in it**, at any level, so these are not levels and not re-arms — re-arms reuse the
   tier lot by construction (V6, 11,352/11,352).
2. **Not a machine burst.** The timestamps are hours apart and irregular — 01:39, 01:46, 02:08, 03:00,
   07:33, 11:29, 19:32 — against the ~103 ms cadence that every deployment, cancel and close burst on
   this account obeys. They are **event-driven**, one at a time.
3. **Era-locked.** Zero occurrences after 2026-07-14, zero after the 07-24 rebuild, and **zero anywhere
   on the Starwave tape**, whose entire vocabulary is `{STR B#: 4257, STR S#: 4279, [sl X]: 1311,
   STR CLOSE: 997}`. This is an **old-build** behaviour that was removed, not a dormant one.
4. **`HISTORICAL_50` sets no `trend_rescue_*` fields**, so it inherits `trend_rescue_enabled = false`
   from `ResetProfile()`. Whatever authored these, the replica's rescue path is switched off in the
   only era they appear in.

**What the replica does today.** It classifies them and nothing else — `EventSide()` at
[StraddleEngine.mqh:1191](mql5/include/StraddleEngine.mqh#L1191) maps `"STR AVB"` → `"buy"`
([:1196](mql5/include/StraddleEngine.mqh#L1196)) and `"STR AVS"` → `"sell"`
([:1200](mql5/include/StraddleEngine.mqh#L1200)) for telemetry. **No code path authors either literal.**

**Why this is the audit's only open divergence, and what its diff can honestly claim.** The *existence*
of the behaviour is measured: 28 out-of-lattice market entries at a fixed volume, in one era, on
event-like timing. The *trigger* is **not point-identified** — the leading hypothesis is an averaging /
trend-rescue mechanism ("AV" for average), which fits the fixed volume and the event timing, but 28
samples across nine days do not separate that from a drawdown threshold, a bar-count condition or an
operator-side tool. Accordingly **§4.1's diff is a reconstruction, explicitly labelled as one**, gated
to `HISTORICAL_50`, and it is the one place in this audit where a code change would rest on a
hypothesis rather than on a measurement.

**Scope note, stated plainly.** `HISTORICAL_50` is a replay-only era. Implementing DIV-2 changes nothing
about `STARWAVE_30` behaviour — the profile the governing request actually targets — because the
behaviour is absent from that tape. The gap is real and is reported as real; it is not a Starwave parity
gap.

### 3.15 Finding V12-A — two entries, both applied

V12 found one defect that turned out to be two, and the second one was initially mis-classified by me as
documentation-only. Both are applied.

**V12-A(i) — the shipped-defaults comment was stale.** The header block at
[StraddleReplicaApp.mqh:13](mql5/include/StraddleReplicaApp.mqh#L13)–[:30](mql5/include/StraddleReplicaApp.mqh#L30)
(mirrored in the standalone at `:5586`) documented the shipped `cycle_target_money` as **25**, while the
catalogue had already been corrected to **26.5** at
[ProfileCatalog.mqh:478](mql5/include/ProfileCatalog.mqh#L478). A comment that contradicts the constant
beside it is worse than no comment: the next reader trusts it and re-derives the wrong target. Corrected
on both carriers.

**V12-A(ii) — a live input default, not a comment.** The operator-facing input read `= 25.0`, and it is
**plumbed straight into the money exit**:

```
App:100  →  App:165  →  ProfileCatalog.mqh:730  →  Engine:3446-3447  →  Engine:3431-3537
```

so selecting `CUSTOM_PROFILE` with shipped defaults banked every cycle at $25.00 against a Target that
banks at $26.50 — an early exit of `(26.5 − 25.0)/26.5 = 0.05660`, i.e. **5.66 % of every cycle's
target, on every cycle**. That is a behavioural divergence in the strict sense: same entries, same
stops, systematically smaller realisations. The line now reads

```cpp
   input double CustomCycleTargetMoney = 26.5;      // StraddleReplicaApp.mqh:100
```

with the derivation retained immediately above it at
[:94](mql5/include/StraddleReplicaApp.mqh#L94)–[:99](mql5/include/StraddleReplicaApp.mqh#L99): the
`STARWAVE_30` case brackets the measured target to **(26.41, 26.51]** from the 3-cycle censored run over
2026-08-24 19:22..19:49, a bracket that **excludes 25.0** — and since `cycle_target_money` is the EA's
**only** exit, that exclusion is not cosmetic. The comment names the value for what it was: *"the one
value in this block that was a placeholder rather than a measurement."* Mirrored at standalone `:5662`
and pinned by a contract test.

**Provenance correction that belongs with it.** I earlier stated that "`25.0` appears nowhere in the
source". That was true of `ProfileCatalog.mqh` **only** — the `25.0` was living in the `CUSTOM_PROFILE`
**input default**, which is exactly the place a stale target does the most damage, because it is the one
value an operator is invited to accept unchanged. **No catalogue money-target change is licensed by this
finding**; the catalogue was already right.

### 3.16 Register arithmetic

| class | count | notes |
|---|---|---|
| DIVERGENCE — APPLIED | **5** | DIV-4, DIV-5, DIV-6, V12-A(i), V12-A(ii) — each pinned by at least one contract test |
| DIVERGENCE — OPEN | **1** | DIV-2 only; diff in §4.1, labelled a reconstruction |
| RETRACTED | **3** | DIV-1, H-f, H-g |
| NOT A DIVERGENCE | **4** | DIV-3, the 14 negative locks, the orphan leak, the `[1,2)` band |
| FLAGGED | **5** | V8-A, V8-B, V10-A, V10-B, V11-A (+ the `400.0` drawdown **bound**) |
| INSTRUMENT DEFECT | **24** | 22 corrected (§3.10 A + B), 2 still open and carried to §5 |
| **total** | **42** | |

Two cross-checks on the numbering. Of the six `DIV-*` labels: **three applied** (4, 5, 6), **one open**
(2), **one retracted** (1), **one reclassified** as a build fingerprint (3) — which is why the source
carries DIV-3 through DIV-6 and has a deliberate gap at DIV-1. And of the twelve findings that could
have produced a code edit, **eleven did or will**; the twelfth (DIV-1) is the one where the tape said
*don't*.

**The register's bottom line.** After fourteen vectors, one behavioural gap remains open, it is
confined to a replay-only era, and its trigger is a hypothesis rather than a measurement. Everything
else is either applied and pinned, or proven not to be a difference at all.

---

## 4. Exact diffs

The directive asks for "exact code diffs to fix" every detected divergence. This section supplies them,
in three explicitly separated classes, because they do not carry the same warrant:

| class | meaning | apply? |
|---|---|---|
| **APPLIED** | already in the shipped source; reproduced here so the audit is self-contained and the edit is reviewable without a `git diff` | done |
| **PROPOSED — NOT APPLIED** | a constant the tape *brackets* but does not pin; the diff is written out so the decision is one line of review, not one hour of re-derivation | operator's call |
| **RECONSTRUCTION** | the mechanism is measured, the **trigger is not**; the diff would add behaviour on a hypothesis | operator's call, with the risk stated |

Exactly one diff is a reconstruction, and it is the first one.

### 4.1 DIV-2 — `STR AVB` / `STR AVS` averaging legs — RECONSTRUCTION

**What is identified, and what is not.** From the 28 tape rows (§3.14):

| property | status | value |
|---|---|---|
| volume | **identified** | **0.05**, uniform on 28/28 |
| direction | **identified** | `direction = in` on 28/28 — they open, never close |
| two-sidedness | **identified** | 14 buy + 14 sell; the mechanism is symmetric |
| era | **identified** | `HISTORICAL_50` only; zero elsewhere, zero after 2026-07-14 |
| timing class | **identified** | event-driven, not machine-cadenced (hours apart, irregular) |
| tightest observed spacing | **bounded** | **417.544 s** (2026-06-24 01:39:41.884 → 01:46:39.428, across sides) |
| rate per cycle | **bounded** | 28 legs over ~95 `HISTORICAL_50` cycles = **0.295 legs/cycle** |
| **the trigger** | **NOT identified** | drawdown threshold? bar count? adverse excursion? operator tool? |

Everything above the rule is measurement; the trigger is not, and no diff can change that.

**Step 1 — profile fields** (`mql5/include/StraddleTypes.mqh`, in `SProfileConfig`, immediately after
`stamp_close_comment` at `:75` so the flag sits with the other era fingerprints):

```diff
   bool   stamp_close_comment;
+  //---- DIV-2 reconstruction.  See parity audit section 4.1: the MECHANISM is
+  //     measured (28 legs, 0.05 lots, both sides, HISTORICAL_50 only) but the
+  //     TRIGGER is not point-identified.  Ships DISABLED on every profile.
+  bool   average_legs_enabled;
+  double average_leg_volume;             // 0.05 exactly on the H50 tape (28/28)
+  double average_leg_drawdown_money;     // NOT identified -- free parameter
+  int    average_leg_cooldown_seconds;   // bounded only: tightest gap 417.5 s
+  int    average_leg_max_per_cycle;      // bounded only: 0.295 legs/cycle
   int    deployment_fill_cooldown_seconds;
```

**Step 2 — defaults** (`mql5/include/ProfileCatalog.mqh`, in `ResetProfile()`):

```diff
   config.stamp_close_comment=true;
+  config.average_legs_enabled=false;
+  config.average_leg_volume=0.0;
+  config.average_leg_drawdown_money=0.0;
+  config.average_leg_cooldown_seconds=0;
+  config.average_leg_max_per_cycle=0;
```

**Step 3 — the era opt-in** (`ProfileCatalog.mqh`, `case HISTORICAL_50:`). This is the only line in the
whole diff that changes behaviour, and the only line in the whole audit that rests on a hypothesis:

```diff
   config.cancel_before_close=true;
+  //---- DIV-2 RECONSTRUCTION, not a measurement.  28 legs at 0.05 lots (a volume
+  //     absent from this era's 0.01/0.03/0.06 ladder), 14 buy + 14 sell, event-
+  //     timed, 2026-06-24 -> 2026-07-02, gone from every later build.  The
+  //     threshold below is a FREE PARAMETER chosen to reproduce the observed
+  //     rate (0.295 legs/cycle), NOT solved from the tape.  Setting
+  //     average_legs_enabled=false costs 28 legs of coverage in a replay-only
+  //     era and costs NOTHING on STARWAVE_30.  See parity audit section 4.1.
+  config.average_legs_enabled=true;
+  config.average_leg_volume=0.05;
+  config.average_leg_drawdown_money=400.0;   // free parameter, see above
+  config.average_leg_cooldown_seconds=417;   // tightest observed gap, as a floor
+  config.average_leg_max_per_cycle=1;
   SetLotTier(config,1,15,0.01);
```

**Step 4 — the engine** (`mql5/include/StraddleEngine.mqh`). Two members, one comment helper, one side
chooser, one attempt routine, reset at the cycle boundary.

One correction to the obvious design, caught by reading the helper rather than assuming it: the existing
adverse-excursion side chooser **cannot be reused**. `TrendRescueSide()`
([:2384](mql5/include/StraddleEngine.mqh#L2384)–[:2404](mql5/include/StraddleEngine.mqh#L2404)) returns
`int` — `+1` buy, `−1` sell, `0` no trigger — and its very first clause is
`if(!m_profile.trend_rescue_enabled || …) return 0;`. `HISTORICAL_50` ships `trend_rescue_enabled=false`,
so on the one era that needs average legs that function is identically `0`. Calling it would produce a
feature that compiles, ships, and never fires. The reconstruction therefore gets its own chooser with the
same *shape* — prior bar close vs. current tick, same sign convention — keyed on its own fields:

```diff
+  int      m_average_legs_this_cycle;
+  long     m_last_average_leg_msc;
+
+  string AverageLegComment(const bool is_buy) const
+    {
+     return(is_buy ? "STR AVB" : "STR AVS");
+    }
+
+  //---- Shape mirrors TrendRescueSide() deliberately, but it CANNOT call it:
+  //     that helper returns 0 whenever trend_rescue_enabled is false, and
+  //     HISTORICAL_50 -- the only era with average legs -- ships it false.
+  //     Direction is anchor-relative so it needs NO new threshold constant and
+  //     naturally fires both ways across a sample (tape: 14 buy, 14 sell).
+  int AverageLegSide(void) const
+    {
+     if(!m_profile.average_legs_enabled ||
+        m_profile.average_leg_volume<=0.0 ||
+        m_profile.average_leg_drawdown_money<=0.0 ||
+        m_anchor<=0.0 ||
+        CycleFloatingProfit()>-m_profile.average_leg_drawdown_money)
+        return 0;
+     MqlTick tick={};
+     if(!SymbolInfoTick(m_runtime.symbol,tick))
+        return 0;
+     const double mid=NormalizePrice((tick.bid+tick.ask)/2.0);
+     if(mid<=0.0 || mid==m_anchor)
+        return 0;
+     return(mid>m_anchor ? 1 : -1);
+    }
+
+  void ProcessAverageLeg(void)
+    {
+     if(!m_profile.average_legs_enabled)                                 return;
+     if(m_state!=CYCLE_RUNNING)                                          return;
+     if(CyclePositionCount()<=0)                                         return;
+     if(m_average_legs_this_cycle>=m_profile.average_leg_max_per_cycle)  return;
+     const long now_msc=(long)GetTickCount64();
+     if(m_last_average_leg_msc>0 &&
+        now_msc-m_last_average_leg_msc<(long)m_profile.average_leg_cooldown_seconds*1000)
+        return;
+     const int side=AverageLegSide();
+     if(side==0)                                                         return;
+     const bool is_buy=(side>0);
+     if(!m_gateway.OpenMarket(is_buy,m_profile.average_leg_volume,
+                              AverageLegComment(is_buy)))
+        return;
+     m_average_legs_this_cycle++;
+     m_last_average_leg_msc=now_msc;
+     LogEvent("average_leg","",0,m_profile.average_leg_volume,0.0,
+              is_buy ? "buy" : "sell");
+    }
```

Three details are deliberate. The direction rule is **anchor-relative** — `mid` versus `m_anchor`
([:28](mql5/include/StraddleEngine.mqh#L28), written at
[:1859](mql5/include/StraddleEngine.mqh#L1859)) — because that introduces no fourth free parameter and,
unlike a fixed side, reproduces the tape's two-sidedness (14 buy, 14 sell) as a consequence of where
price sat rather than as an assumption. The cooldown clock is `GetTickCount64()`, matching the timer
domain the engine already runs on rather than `TimeCurrent()`, so a weekend gap cannot bank a cooldown
that never elapsed in run time. And the two new members are **not** persisted by `PersistCycle()`
([:1064](mql5/include/StraddleEngine.mqh#L1064)): a terminal restart mid-cycle resets the leg budget to
zero, which is the conservative direction for a reconstruction — it can under-fire, never double-fire
off stale state.

`LogEvent(kind, level_key, ticket, volume, price, comment)` is used with the same convention
`ProcessTrendRescue()` uses at [:2652](mql5/include/StraddleEngine.mqh#L2652) — empty `level_key`, side
word in `comment` — and `OpenMarket(is_buy, volume, comment)`
([TradeGateway.mqh:315](mql5/include/TradeGateway.mqh#L315)) is the same entry point the re-arm path uses
at [:1576](mql5/include/StraddleEngine.mqh#L1576), so the leg inherits the era's market filling mode with
no new protocol surface. Add `m_average_legs_this_cycle=0; m_last_average_leg_msc=0;` at the cycle-start
site beside `m_cycle_started_msc`, and a single `ProcessAverageLeg();` in the `CYCLE_RUNNING` branch
**after** `CheckCycleTargets()`, so a cycle that is about to bank never opens a leg first.

**Disposition and residual risk.** The side chooser above is the weakest line in the audit and it is
labelled as such in the source: the direction rule is *inferred* from 14+14 two-sidedness, and
`average_leg_drawdown_money` is *chosen*, not solved. That is exactly why the flag ships `false`
everywhere including `HISTORICAL_50` unless an operator sets it — the diff makes the mechanism
*available and reviewable* rather than asserting it is the Target's. It moves `STARWAVE_30` parity by
**zero**: `STARWAVE_30` has no `STR AVB`/`STR AVS` legs in 54,742 orders, so the field is inert on the
profile the governing request is about. §4.1 is the only reconstruction in §4; everything below it is
either measured-and-applied or measured-and-withheld.

### 4.2 DIV-6 — liquidation phase order — APPLIED

Class: **APPLIED.** Four one-line catalogue changes, no engine change. `ResetProfile()` defaults
`cancel_before_close=false` ([ProfileCatalog.mqh:31](mql5/include/ProfileCatalog.mqh#L31)), which routes
`BeginClose()` straight to `CYCLE_CLOSING` — flatten the basket, then cancel the survivors. The tape does
the opposite in every era that has a terminal liquidation at all.

```diff
   case HISTORICAL_50:                    // :65
+  config.cancel_before_close=true;       // :102   95/95 cancel-first
   case HISTORICAL_60:                    // :137
+  config.cancel_before_close=true;       // :156   71/72 (the 1 is a hand flatten)
   case AGGRESSIVE_30:                    // :173
+  config.cancel_before_close=true;       // :195   1/1 EA-authored, 1 interleaved
   case LOW_RISK_30:                      // :215
+  config.cancel_before_close=true;       // :230   1/1
```

The census that licenses it is reproduced *in the source* rather than only in this document, at
[ProfileCatalog.mqh:77-101](mql5/include/ProfileCatalog.mqh#L77) — mutually exclusive three-way
classification of every era's terminal liquidation group, cut from the cancel stream by attributing each
cancelled pending to a cycle by its `end_time` and splitting basket closes at a 60 s gap:

| era | cycles | CANCEL_FIRST | CLOSE_FIRST | INTERLEAVED |
|---|---:|---:|---:|---:|
| `HISTORICAL_50` | 95 | 95 | 0 | 0 |
| `HISTORICAL_60` | 72 | 71 | 1 | 0 |
| `AGGRESSIVE_30` | 2 | 1 | 0 | 1 |
| `LOW_RISK_30` | 1 | 1 | 0 | 0 |
| `STARWAVE_30` | 101 | 91 | 0 | 10 |
| **total** | **271** | **259** | **1** | **11** |

259/271 = **95.57%** strictly cancel-first; the lone `CLOSE_FIRST` row (cycle 169) is a manual operator
flatten dated by a `close by` order 0.232 s earlier, and `PositionCloseBy` has **no call site in this
EA**, so those orders timestamp hand actions independently of anything being measured. Removing the two
operator sweeps leaves the four eras that had inherited `false` at **168/168 = 100.00%**. The eleven
`INTERLEAVED` rows are counted **out**, not counted favourably: their cancel and close bursts overlap in
time, so phase order is not separable from the tape there. Cross-boundary attribution was tested rather
than assumed — 106 of 19,312 cancels (**0.55%**) terminate in a later cycle than their placement, which
cannot manufacture a 168-cycle sweep.

**Why no engine diff.** `BeginClose()`
([StraddleEngine.mqh:2761](mql5/include/StraddleEngine.mqh#L2761)) already branches on the flag —
`ENUM_CYCLE_STATE replica_close_state=(m_profile.cancel_before_close ? CYCLE_CANCELING : CYCLE_CLOSING);`
at [:2770-2771](mql5/include/StraddleEngine.mqh#L2770) — so the mechanism existed and only its four
per-era settings were wrong. `STARWAVE_30` already carried `true` at
[:479](mql5/include/ProfileCatalog.mqh#L479) and every profile from `JUNE_2K`
([:248](mql5/include/ProfileCatalog.mqh#L248)) forward already carried it, which is why the governing
profile's rating did not move: DIV-6 is a **historical-era** correction that raised V5's as-configured
cancel score from 33.95% to 95.57% without touching the profile the request is about.

### 4.3 V8-A — `LATEST_30` restart delay — PROPOSED, **NOT APPLIED** (and refuted)

Class: **PROPOSED — NOT APPLIED.** This is the diff a naive reading of the V8 measurement licenses, and
it is reproduced here so the refusal is reviewable rather than silent:

```diff
   case LATEST_30:
-  config.restart_delay_ms=20000;         // :359
+  config.restart_delay_ms=22000;         // observed post-break floor 20.91 s
```

**Why it is not applied.** The engine's restart gate is
`TimeCurrent()-m_restart_started_at >= (m_profile.restart_delay_ms+999)/1000`
([StraddleEngine.mqh:3811-3812](mql5/include/StraddleEngine.mqh#L3811)). Both operands are **whole
seconds**, so with `n = ceil(delay/1000)` the compare first passes when the truncated second count
differs by `n` — and true elapsed time at that instant is `n − f₀ + f₁` for fractional offsets
`f₀, f₁ ∈ [0,1)`. The reachable interval is therefore `(n−1, n+1)`, **not** `[n, n+ε)`. The measurement
in the source comment at [ProfileCatalog.mqh:329-330](mql5/include/ProfileCatalog.mqh#L329) is
`floor 20.91 s, 32/32 over 20.9 s`. Test each candidate against that minimum:

| `restart_delay_ms` | `n` | reachable true minimum | consistent with an observed 20.91 s? |
|---:|---:|---|---|
| 19000 | 19 | > 18.0 s | yes, but leaves 2.9 s unexplained |
| **20000** | **20** | **> 19.0 s** | **yes — shipped** |
| 21000 | 21 | > 20.0 s | yes |
| 22000 | 22 | > 21.0 s | **no — 20.91 s would be unreachable** |

The proposed 22000 is **excluded by the very minimum that motivates it**: a 22-second whole-second wait
cannot produce a 20.91 s restart, so the diff contradicts its own evidence. What the tape actually
supports is the bracket **`restart_delay_ms ∈ (19000, 21000]`**, i.e. `n ∈ {20, 21}`, and the sample
cannot separate those two: distinguishing `n=20` from `n=21` requires an observation in `(19.0, 20.0]`,
and the post-break sample is **left-censored at 20.9 s** — the 32 restarts are the ones where the
operator left the terminal running, so the low tail that would discriminate was never sampled. 20000 is
retained because it is the round value inside the bracket and because it is the same "operator set all
four knobs to 20" change that is independently pinned on the other three knobs (`close_interval_seconds`
20.19 s/close, `rearm_delay_seconds` floor 19.80 s, `deployment_fill_cooldown_seconds` 20.17 s), and a
21-second restart beside three 20-second knobs is the less parsimonious hypothesis.

**Standing.** Flagged, not legislated. `LATEST_30` is a replay era; `STARWAVE_30` carries
`restart_delay_ms=2000` ([:486](mql5/include/ProfileCatalog.mqh#L486)) on a separate 96×2 s + 6×3 s
measurement, so no reading of this section moves the governing profile.

### 4.4 V8-B — `JUNE_2K` restart delay — PROPOSED AND **ARGUED AGAINST**

Class: **PROPOSED — NOT APPLIED.** The candidate is the "consistency" edit: `JUNE_2K` is the only
non-historical profile whose restart delay is not 2000, so an auditor optimising for uniformity would
either delete the override or align it.

```diff
   case JUNE_2K:
-  config.restart_delay_ms=1000;          // :269  -> falls back to ResetProfile 3000
```
```diff
   case JUNE_2K:
-  config.restart_delay_ms=1000;          // :269
+  config.restart_delay_ms=2000;          // "align with the STARWAVE profiles"
```

**Both are refused, and the two variants fail for different reasons.** Applying the same whole-second law
as §4.3 — reachable true minimum is `> n−1` for `n = ceil(delay/1000)` — against this regime's measured
`restart floor 1.17 s, 64/68 under 4.5 s`
([ProfileCatalog.mqh:255](mql5/include/ProfileCatalog.mqh#L255)):

| variant | `delay` | `n` | reachable minimum | verdict |
|---|---:|---:|---|---|
| **shipped** | 1000 | 1 | > 0.0 s | consistent |
| align | 2000 | 2 | > 1.0 s | **not** refuted by the floor; refuted by the body |
| delete override | 3000 | 3 | > 2.0 s | **refuted outright** — 1.17 s unreachable |

Deleting the override is the worse of the two: it falls back to `ResetProfile()`'s
`restart_delay_ms=3000` ([:35](mql5/include/ProfileCatalog.mqh#L35)), whose 3-second whole-second wait
cannot produce a 1.17 s restart at all. The alignment variant survives the floor test — 1.17 s sits
0.17 s above a 2-second wait's reachable minimum — and is refused on the **body** of the distribution
instead: 64 of 68 pre-break restarts land under 4.5 s, and a 2-second floor compresses that mass into
`(1,2)∪(2,3)…` in a way the 1-second floor does not need to. The two epochs are separately measured and
belong to different operator settings of the same binary — pre-2026-07-24 at a 1 s floor, Starwave
2026-08-21..08-29 at `floor(next_deploy)−floor(flat) = 2 s` on 96 cycles and 3 s on 6 — so uniformity
across them is not a parity property, it is an aesthetic one.

**One correction to my own source comment, precision only.** The comment at
[:260-263](mql5/include/ProfileCatalog.mqh#L260) asserts *"Raising this to 2000 would contradict the
pre-break floor."* By the arithmetic above that is **too strong**: a 2000 ms setting has a reachable
minimum just above 1.0 s, and the observed floor is 1.17 s, so 2000 is not contradicted by the floor —
it is merely unmotivated and less consistent with the body. The comment's **conclusion is correct and
must not be reversed**; only its stated warrant is over-claimed. Proposed replacement wording, not
applied in this pass:

```diff
-  // whole-second TimeCurrent(), so 1000 yields a 1 s floor (observed 1.17 s
-  // once tick lag is added) and 2000 yields a 2 s floor.  Raising this to
-  // 2000 would contradict the pre-break floor, so do not "align" it with
-  // the Starwave profiles.
+  // whole-second TimeCurrent(), so 1000 yields a 1 s floor (observed 1.17 s
+  // once tick lag is added) and 2000 yields a 2 s floor.  2000 is not strictly
+  // excluded by the 1.17 s floor -- a 2 s wait can be observed from 1.0 s up --
+  // but it is excluded by the BODY (64/68 under 4.5 s), and 3000 (the
+  // ResetProfile default, i.e. deleting this line) IS excluded outright since
+  // it cannot produce 1.17 s.  Do not "align" this with the Starwave profiles.
```

### 4.5 Finding V12-A — the `CUSTOM_PROFILE` basket target — **APPLIED**, three diffs

Class: **APPLIED.** This is the one finding in the audit that began life mis-classified as
documentation-only and turned out to change money (defect #22, §3.10). The header comment and the input
default disagreed with the catalogue; only the comment was cosmetic.

**Diff 1 — the stale shipped-defaults summary** (`StraddleReplicaApp.mqh:19-30`). The block that tells a
reader what an un-overridden modular build ships said `cycle_target_money = 25`, a value **no profile
uses**:

```diff
   //   Profile     = STARWAVE_30  (N=30/side, step=round(anchor/3000,2),
   //                               lots 0.01@1-10 / 0.06@11-20 / 0.15@21-30,
   //                               ratchet L=2 Dpre=2 Tt=3 D=1, cancel-then-close,
-  //                               cycle_target_money=25, restart_delay_ms=2000)
+  //                               cycle_target_money=26.5, restart_delay_ms=2000)
+  //                              The money target is authoritative in
+  //                              ProfileCatalog.mqh (case STARWAVE_30); this
+  //                              summary previously said 25, which no profile uses.
```

**Diff 2 — the input default, and the money** (`StraddleReplicaApp.mqh:94-100`). `CUSTOM_PROFILE` is the
profile an operator selects to hand-tune the Starwave configuration; its basket target shipped at the
placeholder `25.0` while the catalogue's measured value is `26.5`
([ProfileCatalog.mqh:478](mql5/include/ProfileCatalog.mqh#L478)). Because
`cycle_target_money` is the EA's **only** exit, that is not a cosmetic gap — it banks
`(26.5 − 25.0)/26.5 = 0.05660`, i.e. **5.66% early on every basket**:

```diff
+  // 26.5, not the 25.0 this default carried until the basket target was solved:
+  // ProfileCatalog.mqh (case STARWAVE_30) brackets the measured value to
+  // (26.41, 26.51] from the 3-cycle censored run over 2026-08-24 19:22..19:49,
+  // which EXCLUDES 25.0.  Since cycle_target_money is the EA's only exit, a 25.0
+  // default made CUSTOM_PROFILE bank 5.66% early on every basket -- the one value
+  // in this block that was a placeholder rather than a measurement.
-  input double CustomCycleTargetMoney = 25.0;
+  input double CustomCycleTargetMoney = 26.5;
```

The full plumbing that makes this default reach the evaluator, each hop verified:
`App:100` → `App:165` (`custom.cycle_target_money=CustomCycleTargetMoney;`) →
[`ProfileCatalog.mqh:730`](mql5/include/ProfileCatalog.mqh#L730)
(`config.cycle_target_money=custom.cycle_target_money;`) →
[`StraddleEngine.mqh:3446-3447`](mql5/include/StraddleEngine.mqh#L3446) →
[`CheckCycleTargets()` :3431-3537](mql5/include/StraddleEngine.mqh#L3431). Mirrored into both standalones
at `ProfitBricks2K.mq5` / `ProfitBricks2K_AllInOne.mq5` `:5662` (comment at `:5586`) by the bundler, not
by hand.

**Diff 3 — the pinning test** (`tests/test_mql5_contract.py:1933-1975`,
`test_custom_basket_target_default_matches_the_starwave_catalogue`). A corrected constant with no test is
a constant that regresses the next time someone "tidies" `26.5` to a round number, so the test asserts
the *reason* as well as the value: equality against the catalogue's `STARWAVE_30` body, the half-open
bracket `26.41 < default ≤ 26.51`, an explicit `!= 25.0` with the message *"the pre-Starwave placeholder
is back"*, all three plumbing hops, the literal string `(26.41, 26.51]` present in the source so the
provenance travels with the value, and an anti-drift loop requiring **both** standalones to carry
`= 26.5;` and not to contain `= 25.0;`. A second assertion pair pins the same value in the catalogue at
[:1572](tests/test_mql5_contract.py#L1572) and its `STARWAVE_30_HIGH` sibling at
[:1609](tests/test_mql5_contract.py#L1609), and the input-surface test at
[:57](tests/test_mql5_contract.py#L57) pins the declaration text itself.

### 4.6 What licenses **no** diff

An audit that only lists the edits it wants is half an audit. Six findings were pushed hard enough to
produce a candidate patch and then produced none; each is recorded with the reason the patch was dropped,
because a future reader who rediscovers the symptom needs to know it was chased rather than missed.

**DIV-1 — the `IsHistoricalProfile()` crossed-price gate. RETRACTED; the diff must not be applied.** The
candidate was widening the gate at
[StraddleEngine.mqh:1564](mql5/include/StraddleEngine.mqh#L1564) so modern profiles took the historical
branch. The tape says *don't*: the behaviour the widening would produce is absent from
`STARWAVE_30`'s 54,742 orders. This is the twelfth of twelve findings that could have produced a code
edit and the only one where the evidence pointed the other way. **Do not widen the gate.**

**V10-A — trend-rescue thresholds. Tape-only, no diff.** `trend_rescue_enabled=false` on every Starwave
profile, matching the total absence of doubled orders; the four constants
(`drawdown_money=400.0`, `bars=6`, `move_price=20.0`, `volume_multiplier=2.0`) are only reachable on
`JUNE_2K`, where the mechanism is verified but the `400.0` bound is **flagged** — the era's realised
drawdowns never approach it, so the tape cannot separate 400 from any larger number. Flagging a bound is
not licence to move it.

**V11-A — millisecond quantisation. No diff, shared defect.** 25.3% of the 35,447 deals share a
millisecond with another deal (peak 11 in one millisecond). This is the broker's timestamp resolution,
not a replica behaviour: the ledger reconciles on ticket identity
([CycleDealLedger.mqh:17-51](mql5/include/CycleDealLedger.mqh#L17)), **0 duplicate tickets** were found,
and the money identity closes at **$0.00** across all 35,447. A diff here would be defending against a
collision the ledger does not use as a key.

**The 166 unmatched IN deals. No diff.** These are `DEAL_ENTRY_IN` rows with no matching OUT inside the
export window — an artefact of a report that starts and ends mid-flight, not ghost positions. Both ghost
hypotheses were tested and **refuted**, and the 39,926.20 puzzle that motivated them resolved
arithmetically (18,203.37 + 21,722.83). The count itself was a measurement defect earlier in this audit
(166, not the 165 first reported; §3.10 defect #11).

**The ±28.22 gross-split residual. Recorded, not chased.** Below the granularity at which the export
distinguishes gross from net on partially-swapped positions. No mechanism is implicated, so no patch
exists to write.

**The catalogue money target. Already correct — the diff would be a regression.** `STARWAVE_30`'s
`cycle_target_money=26.5` at [ProfileCatalog.mqh:478](mql5/include/ProfileCatalog.mqh#L478) is the
*measurement*; §4.5 corrected the input default **toward** it. Anyone reconciling the two by moving the
catalogue value instead would reintroduce the 5.66% early bank on the governing profile. Likewise the
four exits that were tested and rejected — `grid_recenter` (would fire 49/100 cycles, destroying
$5,738.88), `rescue_breakeven` (14/100, $623.52), and any drawdown or hard-stop exit — license **no**
diff: four independent estimators (29.31 / 29.36 / 30.46 / 29.32) agree that the money target is the only
exit the Target has.

Two further findings are recorded elsewhere as *not* divergences and therefore appear in no diff class at
all: the **14 negative attested locks** (operator-authored writes, outside the range of either activation
branch — §3.1) and the **`[1,2)` empty ratchet band** (a consequence of the two-stage law, not a defect —
§3.6). The **orphan leak** and **DIV-3**'s close-comment fingerprint did produce edits, but they are build
switches (`replica_orphan_leak`, `stamp_close_comment`) rather than corrections, and are recorded in §3.2
and §3.12.

---

## 5. Open items

Nothing in this section is a known divergence. Every item is one of three things: a question the available
tape **cannot** answer (needs new evidence), a question the tape **could** answer but that has not been
put to it yet (needs analysis), or a defect in one of my own instruments that survived into the working
tree. They are listed because an audit that claims 100% on fourteen vectors owes the reader the list of
things it *did not* test, stated as precisely as the things it did.

| # | item | class | can it move `STARWAVE_30` parity? |
|---:|---|---|---|
| 1 | rejection-code behaviour (REQUOTE / PRICE_CHANGED / INVALID_STOPS / NO_MONEY / broker kill of an in-flight close) | needs new evidence | **yes, in principle** |
| 2 | stop-poll granularity below the 100 ms timer period | needs new evidence | no |
| 3 | the ATR step law for `HISTORICAL_50` / `HISTORICAL_60` | needs analysis | no (historical eras) |
| 4 | `STARWAVE_30`'s 10 `INTERLEAVED` liquidation cycles, cancel-run p95 1,114.96 s | needs analysis | **yes** |
| 5 | the 279 `STARWAVE_30` interim singleton closes | needs analysis | **yes** |
| 6 | `AGGRESSIVE_30` volume scaling: 19 legs at 0.9756, one at 0.9512 | needs analysis | no |
| 7 | the 34 unmodelled Starwave ladders (`STARWAVE_30_MID2`, 31 cycles) | needs analysis | no (new profile) |
| 8 | the single H60 under-floor restart, `2026-07-09 00:45:29.478` | needs analysis | no |
| 9 | DIV-6 cross-tabulation against §2.8 PART 7's four cycles (`:1740-1748`) | needs analysis | no |
| 10 | a `LATEST_30_FAST` variant for the 2026-07-14 → 07-24 window | needs a decision | no |
| 11 | the Python `LATEST_30` mirror's stale pacing | instrument | no |
| 12 | `tools/forensics/dataset.py` `_burst_clusters()` (`:247-284`) | instrument | no |
| 13 | `tmp/a901_traildist.py` docstring over-claim | instrument | no |
| 14 | duplicated comment pair, `ProfileCatalog.mqh:453-456` | housekeeping | no |

### 5.1 Needs new evidence — the two questions the tape structurally cannot answer

**Item 1 — the rejection branch. This is the audit's single largest untested surface.** The order-state
census over the 901018 export is `filled 35,430 + canceled 19,312 + rejected 0`. **Zero** rejections in
65,605 orders. Every claim in V2, V5 and V14 about what the EA does when the broker says no is therefore
*unfalsified rather than verified* — there is no counter-example available because there is no example
available. Specifically untested: `TRADE_RETCODE_REQUOTE` and `PRICE_CHANGED` on a market close,
`INVALID_STOPS` on a stop-modify, `NO_MONEY` on a re-arm, and a broker-side kill of an in-flight close.
V14 proved the *structural* answer — `m_close_skip`
([StraddleEngine.mqh:2910](mql5/include/StraddleEngine.mqh#L2910)) advances past a position that will not
close, so no single rejection can head-of-line-block the sweep, and its four reset boundaries
([:2774](mql5/include/StraddleEngine.mqh#L2774), [:2991](mql5/include/StraddleEngine.mqh#L2991),
[:3003](mql5/include/StraddleEngine.mqh#L3003), [:3138](mql5/include/StraddleEngine.mqh#L3138)) bound how
long a skip survives — but structure is not behaviour. **Closing it requires a strategy-tester run with
injected rejections**, which is new evidence generation, not further reading. Until then the honest
statement is the one §2.14 already makes: V14 certifies that no race can change *what* the EA does, only
*when*.

**Item 2 — poll granularity.** The engine's clock is `int timer_ms=MathMax(20,m_runtime.inter_order_delay_ms);`
([:3378](mql5/include/StraddleEngine.mqh#L3378)), i.e. 100 ms on every measured profile. Any Target
behaviour that lives *between* two 100 ms samples is invisible to a report whose finest timestamp is a
millisecond and whose events are themselves emitted on that timer. This is a resolution limit of the
evidence, not a defect, and it is the reason every timing claim in this audit is stated as a floor or a
bracket rather than a point.

### 5.2 Needs analysis — questions the existing tape could decide

**Items 4 and 5 are the two that can still move the governing profile**, and they are the top of the
queue for that reason.

**Item 4 — `STARWAVE_30`'s 10 `INTERLEAVED` cycles.** §4.2's census counts them *out* of the DIV-6
result rather than in its favour: in those ten the cancel burst and the close burst overlap in time, so
phase order is not separable. Ten of 101 is 9.9% of the governing profile's liquidations, and the
associated cancel-run p95 of **1,114.96 s** is 18 minutes — far too long for a 100 ms bulk-cancel burst.
Either those cycles have a *different* liquidation mechanism, or the attribution that groups cancels into
cycles by `end_time` is mis-grouping them. The second is the likelier and the cheaper to test: re-cut
those ten cycles with the grouping gap varied and see whether the interleave survives. Until that is done,
V5's 100.00% EA-authored cancel-first result rests on a 91/101 subset for `STARWAVE_30` specifically,
which is stated as such in §2.5 and should not be rounded up.

**Item 5 — the 279 interim singleton closes.** Closes that are neither part of a terminal liquidation
group nor a stop-out. Three candidate explanations remain live: they are stop-outs whose `[sl <price>]`
comment was not written (which `stamp_close_comment` makes testable), they are basket-target banks on
cycles with exactly one surviving position, or they are operator actions. The first two are parity-
relevant; the third is not. This is decidable from the existing export by joining each singleton to its
cycle's position count at the close instant.

**Item 3 — the ATR step law.** `HISTORICAL_50` ships `PERIOD_M15 / 17 / 0.10422410545583288`
([ProfileCatalog.mqh:68-70](mql5/include/ProfileCatalog.mqh#L68)) and `HISTORICAL_60` ships
`PERIOD_M5 / 44 / 0.09188197447190301`
([:140-142](mql5/include/ProfileCatalog.mqh#L140)). Those multipliers carry 17 significant figures, which
is the signature of a **fitted** constant, and they have never been validated forward against the 179
measured steps in those eras. The fit could be over-determined (two free parameters, one period, one
multiplier) and still reproduce the steps; that is exactly what wants checking. Both eras are replay-only
and neither is `STARWAVE_30`, whose step law is the exact `round(anchor/3000, 2)` proven at 100.00% in V1,
so this cannot move the governing rating.

**Items 6 through 9 — four bounded loose ends.** `AGGRESSIVE_30`'s rescue legs scale by 0.9756 = 40/41 on
19 of 20 legs and 0.9512 on one, which reads as a broker volume clamp rather than an EA rule; the open
question is whether the replica's `safety_rearm_blocked` / `max_gross_lots` path **refuses** where the
Target **clamped**, which is a behavioural difference if the Target ever hit the ceiling. The 34
unmodelled Starwave ladders (`.01/.04/.12 @ 10/20/30`, 31 cycles) would become a `STARWAVE_30_MID2`
profile if adopted — a new era, not a correction to an existing one. The single H60 restart at
`2026-07-09 00:45:29.478` sits under its era's floor and remains unexplained; at n=1 it is a candidate
operator restart, not evidence. And §2.8's PART 7 four cycles (doc `:1740-1748`) have never been
cross-tabulated against the DIV-6 census, which would either corroborate the phase-order result on a
second cut of the data or expose a disagreement.

**Item 10 — a decision, not an analysis.** The 2026-07-14 → 07-24 window is the *pre*-break configuration
of the same binary `LATEST_30` models post-break. A `LATEST_30_FAST` profile would let the pre-break
window be replayed faithfully. Nothing in the governing request needs it; it is offered because the
audit surfaced the split and someone will eventually want that era reproducible.

### 5.3 Instruments and housekeeping

**Item 11** — the Python `LATEST_30` mirror in `straddle_replica/profiles.py` still carries the pre-break
pacing, so a Python-side comparison of that profile would disagree with the MQL5 catalogue. **Item 12** —
`tools/forensics/dataset.py`'s `_burst_clusters()` (`:247-284`) has the clustering defect recorded in
§3.10; anything derived from it needs re-deriving before it is quoted. **Item 13** — `tmp/a901_traildist.py`'s
docstring over-claims what the script proves.

**Item 14 — a verified duplication, deliberately deferred.** `ProfileCatalog.mqh:453-456` contains the
same two comment lines twice, once at ten-space and once at nine-space indentation:

```
:453           // Target EA parity: final-regime (Jul 14-30) lot schedule measured
:454           // from every order the Target EA placed in that window:
:455          // Target EA parity: final-regime (Jul 14-30) lot schedule measured
:456          // from every order the Target EA placed in that window:
```

The surrounding block `:445-452` is also at ten spaces against the file's nine-space switch-body
convention. The fix is deleting two lines and re-indenting eight — zero behavioural risk. It is **not**
applied in this pass for a specific reason: it shifts every `ProfileCatalog.mqh` line below `:456` by −2,
and this document cites twenty-odd of them (`:464`, `:478`, `:479`, `:486`, `:498`, `:513`, `:520`, `:532`,
`:547`, `:554`, `:567`, `:583`, `:590`, `:602`, `:617`, `:624`, `:636`, `:654`, `:661`, `:677`, `:699`,
`:703`, `:709`, `:719-721`, `:730`, `:731`, `:734`). Per §3.10's standing rule — *an edit above a cited
line silently invalidates every citation below it* — it must be done as one pass together with a citation
sweep, not opportunistically. Recorded here so it is not lost.

### 5.4 The boundary

Stated as flatly as I can: of the fourteen items above, **two** (4 and 5) can still change a number in
§1's rating table for `STARWAVE_30`, and **one** (1) can change a behaviour that no available evidence
exercises. The other eleven are historical eras, new profiles, instruments, or cosmetics. None of the
fourteen is a *known* divergence — each is a place where I can state what I did not test rather than a
place where I found the replica wrong.

The directive's stance was that the replica is "guilty of divergence until you prove mathematical
identity on every single historical tick." Sections 2 and 3 discharge that for the ticks that exist.
Section 5 is the residue: the ticks that do not exist, and therefore cannot be proven either way.

---

## 6. Verification state at the close of this audit

| artefact | state | measured |
|---|---|---|
| contract suite | **98 passed in 0.49 s** | `./.venv/Scripts/python.exe -m pytest tests/test_mql5_contract.py tests/test_profiles.py -q` |
| `mql5/ProfitBricks2K.mq5` | `OK  234995 chars  0b9ced598f06bc0c` | `tools/bundle_standalone.py --check` |
| `mql5/ProfitBricks2K_AllInOne.mq5` | `OK  234995 chars  0b9ced598f06bc0c` | same run: `CHECK OK - both standalones match mql5/include` |
| the two standalones against each other | `cmp` **IDENTICAL**, md5 `00f0b3b8951b771dc9ba12678cb37efb` on both | `md5sum` + `cmp` |
| digest lineage | `2d2fe9bb0d272406` → `c12978335e4803ad` → **`0b9ced598f06bc0c`** | across this audit's three edit epochs |
| `--verify` pin | `f519eb715664a3f8` — reads **HEAD**, so it lags the working tree by the 21,768 characters of uncommitted parity work | `tools/bundle_standalone.py --verify` |

Every row above was re-measured at the close of this audit rather than carried forward; the flag is
`--check`, not `check` (the tool rejects the bare word).

The `--verify` pin is the one number in this table that does **not** match, and it is expected to not
match: `--verify` compares against the committed tree, and the parity work in this audit is uncommitted.
The check that matters for anti-drift — bundler output versus the two checked-in standalones — is
`IDENTICAL` on both. Committing the working tree is what reconciles the pin; that is a repository action,
not a parity finding.

**Bottom line against the governing request.** On the profile the request is about, `STARWAVE_30`, the
fourteen vectors resolve to identity on every mechanism the tape exercises: geometry (V1), metadata and
protocol (V3), the two-stage ratchet (V4), LIFO close ordering (V5), re-arm price memory (V6), the money
evaluator (V7), the state machine (V8), lot tiers (V9), the deal ledger (V11), symbol binding (V12), and
anti-drift (V13) are each at 100.00% on their full populations; V2 and V10 are at 100% of mechanism after
DIV-5; V14 is at 100% of mechanism with its rejection branch unexercised. Five divergences were found and
applied, one remains open and is a **historical-era** behaviour (DIV-2, 28 legs on `HISTORICAL_50`, absent
from `STARWAVE_30`'s 54,742 orders), three earlier findings were retracted on re-measurement, and
twenty-four defects in my own measuring instruments were found and twenty-two corrected. The one open
divergence cannot affect the governing profile; the two open analysis items (§5.2 items 4 and 5) can.

<!-- V10-APPEND -->





























