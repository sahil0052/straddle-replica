---
name: target-ea-parity
description: >-
  Core operating directive for the StraddleReplica project. Enforces 100% mathematical,
  architectural, and operational lockstep parity between our replica EA (111387094) and the
  Target EA (901018 on AchieverGlobalMarkets). Grants full autonomous execution authority to
  detect, implement, compile, and deploy any parity fixes immediately without asking.
---

# Target EA Parity & Autonomous Execution Directive

## 1. Prime Mission Directive
The **sole and overriding goal** of this project is to make our EA (`111387094`) behave with **100% identical logic, risk profile, execution speed, lot sizing, and lifecycle reset behavior** as the Target EA (`901018`).

### Autonomous Action Authority
Whenever you detect a logic difference, parameter mismatch, boundary drift, or synchronization delay between our EA and the Target EA:
* **DO NOT WAIT OR ASK FOR PERMISSION.**
* **Proactively research, modify code, compile (`metaeditor64.exe`), deploy to VPS, and verify execution immediately.**

---

## 2. Core Architectural Invariants (Target EA Exact Standards)

> **THE "FINAL REGIME" CONTAINS A SETTINGS CHANGE.** On **2026-07-24 midday** the Target EA's operator
> raised all four pacing knobs from 0 to 20 s in one change. The flatten close mode proves the date and
> proves it is a settings change rather than a runtime condition: **69 consecutive** burst-close sweeps
> (Jul 14 → Jul 24 09:10:18), then **32 consecutive** paced sweeps (Jul 24 15:48:43 → Jul 30 17:10:07).
> That is **2 runs** where a state-dependent rule on a 69/32 split would give ~45.
>
> **Parity tracks the LATER configuration.** Every invariant in this section was re-measured
> independently on both sides of the break (`q4c_regimebreak.py`). What did **not** move: the trail
> ratchet (empty band `0.9927` early vs `0.9926` late — §D is now confirmed twice over, independently),
> the lot tiers, `levels_per_side = 30`, the step and its 3000 divisor, the 100 ms action cadence, and
> the total absence of take-profits. What moved: only the four pacing knobs below. When you measure a
> new constant over Jul 14–30, split it at the break before believing the pooled number.

### A. Lot Sizing Schedule (Strict Parity — Final Regime)
The Target EA changed regimes several times inside `ReportHistory-901018.xlsx`. Parity MUST track the
**final regime (Jul 14–30)**, measured from every order placed in that window:
* **Levels 1 to 10**: `0.01` lots (10,940 orders, zero exceptions at base volume).
* **Levels 11 to 20**: `0.06` lots (2,624 orders).
* **Levels 21 to 30**: `0.15` lots (378 orders).
* Trend-rescue replacement orders trade at exactly `2x` the tier volume (0.12 at L11–20, 0.30 at L21–30).

> NOTE: The older 0.01/0.03/0.06 schedule at 15/25/30 boundaries matches only the June regime and the
> whole-history aggregate. Do NOT regress to it.

### B. Compact Cycle Boundary (Basket Target Is The Only Money Exit)
* **Cycle Basket Target**: `cycle_target_money = 30.0`, evaluated as
  `realized_since_cycle_start + floating >= 30.0`. **CONFIRMED** by four independent estimators over
  100 final-regime cycles delimited by their own flatten sweeps: exact burst-flatten total `29.31`,
  whole-sweep total `29.36`, decision-instant marked total `30.46`, and a first-fire lead time that
  bottoms out at T=30 (median lead `5.6 s`, i.e. one 20 s timer tick).
  * The ledger scope is `realized + floating`, **not** `equity - balance`. Binning cycles by
    realized-before-exit, the median `realized + floating` at exit stays pinned across the whole range
    (`28.19 → 31.19 → 29.96 → 27.12 → 28.10`) while floating alone walks to `-422.38`.
  * `cycle_target_balance_pct` is **rejected**: balance grew 10,132 → 17,900 (+77%) while the trigger
    total moved only 32.53 → 35.22 (0.18% of balance predicts 57.6).
  * A **size-scaled** target is rejected outright: `net >= min(30, k*$/pt)` and `net >= k*open_positions`
    fire at the decision on 0/100 cycles and prematurely on 97/100.
* **REFUTED — 20-Point Auto-Recenter.** `dist>=20 || (realized>=50 && net>=-20 && dist>=15)` would fire
  on 49/100 cycles, 27 of them >5 min early (max lead 12.4 h), at a median net of **-$19.36** where the
  Target EA went on to bank **+$36.00**. Aggregate profit destroyed: **$5,738.88**. Both clauses are
  equally culpable. The distance gate does not even separate the exit groups (money-target exits were
  >=20 pts from the anchor 18/72 of the time vs 1/6 for below-zero exits). **Removed from the engine.**
* **REFUTED — Trend Rescue Breakeven Liquidation.** `realized>=200 && net>=-10` would fire on 14/100
  cycles, 9 of them >5 min early (max lead 9.2 h), at a median net of +$10.16 vs +$42.62 banked.
  Aggregate profit destroyed: **$623.52**. Decisively, the marked total at exit has **zero** cycles in
  `[-25, 0)` under two independent segmentations — a breakeven-liquidation rule would pile up exactly
  there. **Removed from the engine.**
* **REFUTED — any floor on net or floating.** The shallowest below-zero exit bottomed at `-$25.68`
  while *surviving* cycles rode net down to `-924, -537, -501, -412, -403, -384` (floating to
  `-1043.86`) and went on to close in profit. The ranges overlap by two orders of magnitude.
* **Flatten behaviour**: `cancel_before_close = true` — 24–54 pendings (median 44) are cancelled first,
  the first position closing a median 4.82 s later. The basket goes fully flat every cycle (0/100
  boundaries had anything still open), so there is no re-centre-without-flatten. Closing is bimodal, but
  **the mode is a date regime, not a basket property** — see the pacing table below. The paced mode is
  direct confirmation of `close_interval_seconds = 20`; the burst mode is the same EA with the knob at 0.
* **Measurement caveat**: the paced flatten takes up to ~8 minutes (23 positions × 20 s), which degrades
  every basket-target estimator that reads `realized_before + flatten_net`, because mid-sweep SL closures
  fall into neither term and the last position closes far from the decision instant. Post-break totals
  land in [20,40] on only 6/32 sweeps against 39/68 pre-break. Re-marking the un-closed remainder at the
  first close's own price recovers 13/32. **This is instrument degradation, not a moved target** — the
  pre-break burst population is the precise instrument (it liquidates in ~1 s) and it is what the four
  §B estimators were dominated by. `$30` stands.
* **OPEN RESIDUALS** (characterised, deliberately not modelled):
  * 6/100 exits land below `-$25` (worst `-170.20`) with no discoverable rule — no floor, no distance
    signature, no pinned quantity, and young cycle ages (four under 20 min). Most consistent with
    discretionary/manual flattens. Do not invent a rule for these; that is exactly what cost $6,362.
  * 5/100 cycles sustained a total above $30 for 6–257 min without closing (all heavily loaded,
    32–94 $/pt, 4–57 h old). Leading hypothesis: the basket check is skipped while the EA is
    deploying/re-arming. Untested.

### B2. The 20-Second Pacing Family (all four flipped 0 → 20 on 2026-07-24)

| knob | before Jul 24 | after Jul 24 | replica |
|---|---|---|---|
| `close_interval_seconds` | burst, `0.106 s`/close (69 sweeps) | paced, `20.19 s`/close (32 sweeps) | `20` |
| `rearm_delay_seconds` | no floor; 42/1196 delays under 4.5 s | floor `19.80 s`; 2/581 under 19 s | `20` |
| `restart_delay_ms` | floor `1.17 s`; 64/68 under 4.5 s | floor `20.91 s`; 32/32 over 20.9 s | `20000` |
| `deployment_fill_cooldown_seconds` | gap after an in-burst fill `0.13 s` | gap after an in-burst fill `20.17 s` | `20` |

* **A delay parameter is a FLOOR, not a spike.** With a 100 ms evaluation timer, no observation can land
  below the delay. The observations that expose it are the ones where price was already back at the level
  so that only the timer was holding them. `rearm_delay_seconds = 5` was set from a modal bucket ("490 of
  2,370 re-arms in the first 5 s") which pooled the two regimes; it is **refuted on both sides** — the
  early side has 42 delays under 4.5 s (no gate at all), the late side's floor is 19.80 s. **Corrected to
  20.** A 5 s delay sampled by a 20 s evaluation clock is refuted too: that scatters across 20/40/60 s,
  but the post-break counts are **48 near 20 s against 5 near 40 s and 5 near 60 s**.
* **`deployment_fill_cooldown_seconds` is the strongest of the four**, and it is confirmed *causally*, not
  by correlation: across 32 post-break deployments, **25 of 25** placement gaps that follow an in-burst
  fill are ≥ 15 s (median `20.118 s`) while **0 of 1,863** gaps that do not are (median `0.101 s`, max
  `0.144 s`). Independently, burst span fits `6.12 s + 19.898 s × (in-burst fills)` with a max residual of
  `0.66 s` over fill counts {0,1,2,3,7,10} — and the `6.12 s` intercept over 59 placement gaps
  re-derives `InterOrderDelayMs = 100` from a completely different direction.
* **Why none of them is exactly 20.00**: the engine compares a whole-second `TimeCurrent()` against the
  threshold and samples it on a 100 ms timer, so the release lands inside a ±1 s window whose sign
  depends on which timestamp the report exposes. Re-arms read 19.8 because they are measured from the
  position's `close_time`, which precedes the fill by the 0.1–0.2 s SL-trigger-to-fill latency seen
  everywhere else in this dataset. Nobody configures 19.8.
* All four knobs being 0 before and 20 after is **one operator action, not four coincidences** — which is
  itself the strongest corroboration of the `rearm_delay_seconds` correction, since the other three are
  each independently measured at 20.

### B3. Execution Sequence & Timer Architecture (CONFIRMED)

**One broker call per timer tick, at 100 ms.** `OnTimer` dispatches on `m_state` and performs exactly ONE
action per tick — `DeployOne()` places one stop, `CancelOneOrder()` deletes one order, `CloseOnePosition()`
closes one position, `UpdatePositionStops()` modifies one SL (`max_stop_updates_per_pass = 1`),
`RearmOneMissingLevel()` arms one level and then `return`s. This makes **cadence a fingerprint**: an
observable inter-action gap in the report *is* the timer period. Two independent estimators agree:

* deployment placements: median gap **101 ms** (pre-break) / **100 ms** (post-break)
* cancellation sweeps: median gap **103 ms** / **102 ms**, at a median 44 pendings per sweep
* a third, from the cooldown fit above: `6.12 s` intercept ÷ 59 gaps = **104 ms**

⇒ `EventSetMillisecondTimer(MathMax(20, InterOrderDelayMs))` with `InterOrderDelayMs = 100`. **No change.**
`cancel_before_close` ordering is confirmed too: cancels complete, then the first close follows a median
`4.82 s` later.

**Retry queues are sound.** `STR_PENDING_DEAL_CAPACITY 256` with `DealMetadataReady` gating, plus history
reconciliation every `STR_HISTORY_RECONCILE_INTERVAL_MS 1000` over a `STR_HISTORY_RECONCILE_LOOKBACK_MS
900000` (15 min) window, covers the deal-arrival races. No parity gap found.

**Three defects found in `TradeGateway.mqh` / the close path** (independent of parity — these are
robustness bugs that would make the replica *diverge* from the Target under broker stress):

1. `PlaceStop` hardcodes `request.type_filling = ORDER_FILLING_RETURN` instead of calling
   `MarketFillingMode()`. On a broker that rejects RETURN for stops, every placement fails.
2. `Send()` treats a non-`DONE` retcode (`REQUOTE`, `PRICE_CHANGED`, `PRICE_OFF`, `TOO_MANY_REQUESTS`) as a
   **silent single-shot failure** — no retry, no requeue. A level that fails to arm stays unarmed, leaving
   the replica's lattice permanently thinner than the Target's. Since §G shows the lattice re-arms are half
   the profit engine, a missing level is a direct revenue loss, not a cosmetic difference.
3. `TryCloseOneOwnedPosition` has `return true` **outside** the success branch, so a position that keeps
   failing to close head-of-line-blocks the entire flatten sweep — the state machine retries the same
   position forever and never advances to the rest of the basket.

### C. Step Spacing
* Step mode: `STR_STEP_ANCHOR_DIVISOR` with `divisor = 3000.0`.
* Measured final-regime step is **1.32–1.39 points (median 1.3500)** on XAUUSD, *not* 1.50–1.51 — that
  older figure came from a pre-final-regime window. The divisor itself is corroborated independently:
  fitted `anchor / step` has median `3000.35` (range 2988.98–3010.59) across final-regime lattices.
* Total levels: 30 Buy levels above Anchor + 30 Sell levels below Anchor.

### D. Trailing Stops (SL Ratchet Equation — CONFIRMED)
The 2-stage ratchet in `StopScheduler.mqh` is **confirmed exactly**, by market-price inversion rather
than by profit histogram. For a position closed at its own SL, invert the trail to recover the market
price the EA was trailing from: `locked = dir*(sl - entry)/step = favorable - D`, so a trail distance of
`D` steps forces `locked` into a known band. Over **n = 2,695** final-regime positions carrying an SL:
* `locked < 1` (mode A, `D = 2`): 1,103 positions, spanning +0.0073 … +0.9927 steps.
* `locked >= 1` (mode B, `D = 1`): 1,592 positions, spanning +1.9853 … +17.5221 steps.
* **The band (0.9927, 1.9853) is EMPTY** — width 0.9926 ≈ exactly one step. That gap is the signature of
  a two-stage trail with `D_pre - D_post = 1.0`, and it cannot be produced by any single-stage trail.
* Zero negative `locked` values: **the SL is never placed below entry.**
* Reconstructing `M̂ = sl + dir*D*step` collapses the 2,695 positions onto 1,601 market marks; 408 of
  those marks contain positions from *both* stages, with a within-mark spread of median 0.0100 (one tick,
  max 0.1000) — the two stages agree on the same underlying price to tick precision.

Therefore:
* **Activation**: 2.0 favorable steps (`lock_trigger_steps = 2.0`); first SL = `market - 2.0*step`.
* **Pre-tighten phase**: trail at `2.0` steps while favorable < 3.0 steps → locked lands in [0,1).
* **Tighten**: at 3.0 favorable steps (`tighten_trigger_steps = 3.0`) distance tightens to `1.0` step
  → locked lands in [2,∞).
* **Runners**: the 1.0-step trail is FIXED, never tightens further (max observed locked 17.52 steps).
* **No take-profit is ever set** — 0 of 3,455 final-regime positions had a TP. **CONFIRMED.**
* **Timer cadence**: 20 s. SL-closure gaps spike at 20.1 s / 19.8 s (267 gaps in [19.5, 20.7], 23 near
  40 s, 16 near 60 s), with 467 sub-second cascades when several SLs are breached inside one tick.

> CORRECTION: the earlier "287 winners closed exactly at SL" figure was a sampling artifact — there are
> **2,490** SL closures in the final regime; only 287 filled at *exactly* the recorded SL price. And
> "ZERO losers ever closed at SL" is **false**: 94 of the 2,490 were net-negative (worst `-$16.67` on
> `STR B2`, 14.03 points of slippage), 4 were exactly zero, 2,392 positive. The ratchet equation above
> is unaffected — it was derived from the full 2,695-position SL population, not the 287.

### E. Pending-Order Re-Arms (Static Lattice — NO dynamic repositioning)
* Re-arms ALWAYS return to the **original anchor lattice price**: 99.4% of 1,797 measured mid-cycle re-arms landed exactly (<0.1 step) on the same (side,level) price from the cycle's deployment burst.
* Sell stops were observed re-armed up to 35 steps below market ON THE LATTICE. The Target EA NEVER moves opposite-side pendings toward market during trends.
* If a lattice price is currently invalid (market has crossed it), WAIT for price to return — do not re-anchor.

### F. Trend Rescue (2x Volume) — TRIGGER CONFIRMED
* Replacement volume: exactly `2x` tier (0.12 at L11–20, 0.30 at L21–30). Final-regime volume histogram
  is `{0.01: 3581, 0.02: 5, 0.06: 2260, 0.12: 55, 0.15: 2091, 0.30: 65}` — the 0.12/0.30 counts are the
  rescue population. **CONFIRMED.**
* **Population.** 125 rescue orders in **6 of 100** final-regime cycles (187, 197, 234, 244, 250, 252),
  fills in 5. Clean **3 EARLY / 3 LATE** split across the Jul-24 break, so none of these knobs moved
  with the pacing family. Cancel-replace dominates re-arm 89 to 36.
* **The decision instant.** Every earlier measurement was taken at the first 2x placement and was
  therefore wrong. `ProcessTrendRescue` does ONE action per tick and `TryCancelOneTrendRescueOrder`
  returns early until the trend side is fully pulled, so by the first 2x placement every base pending
  being replaced is already gone — the trend-side pending count reads 0 *by construction*. The correct
  instant is the **first cancel of a trend-side base pending later re-placed at 2x**. Re-measured:

  | cyc | reg | trend | floating | move(M15,6) | pend[trend] | mark age |
  |---|---|---|---|---|---|---|
  | 187 | EARLY | B | −147.25 | +40.97 | 3 | 0 s |
  | 197 | EARLY | S | −398.82 | −21.08 | 16 | 2 s |
  | 234 | EARLY | S | −759.25 | −29.74 | 10 | 47 s |
  | 244 | LATE | B | −77.92 | +36.37 | 6 | 227 s |
  | 250 | LATE | B | −375.51 | +21.87 | 19 | 196 s |
  | 252 | LATE | S | −382.85 | −19.85 | 11 | 28 s |

* `trend_rescue_bars = 6` **CONFIRMED** — unique argmax over `{2,4,6,8,10,12,16,24}`. Only at 6 do all
  six events clear 20 (min 19.85). Every other lookback lets a real event fire below the threshold.
* `trend_rescue_minimum_pending_levels = 3` **CONFIRMED** — the minimum of `3 16 10 6 19 11` sits
  exactly ON the threshold with zero margin.
* `trend_rescue_volume_multiplier = 2.0` **CONFIRMED** — and the cancel COUNT equals the trend-side
  pending count in every measurable event (3/3, 11/11, 20/20, 12/12): the rescue pulls *every* surviving
  base pending on the trend side and re-places it at 2x. The 0.10–0.12 s cancel gaps re-derive
  `InterOrderDelayMs = 100` a **fourth** independent way.
* `trend_rescue_drawdown_money = 400.0` **CONFIRMED** — the value was right; two earlier readings of it
  were not. `m_trend_rescue_side` is a **latch**, so the right question is not "what was floating at the
  first action" but "did floating reach −X at or before it", evaluated only at trade prints where the
  mark is exact. On that test: **miss = 0**, and the falsifier count falls monotonically 12 → 4 across
  −300 → −400, sits **flat at 4 through −440**, and only improves at −460 by buying two *impossible*
  negative leads. 400 is the corner of the plateau. Of the 4 falsifiers, 3 are blocked by `move_price`
  (moves of −17.70, +16.71, +15.60) and the survivor (cyc 253) goes true with 14.6 min of cycle left.
  Floating is exactly linear in the mark, so the mark each event needed for −400 is closed-form, and
  4 of 6 sit within **0.17 / 1.01 / 4.08 / 6.44 points** of it — cycle 197 was $1.18 short with a 2 s
  mark and crossed −400 **5.4 seconds** after the sweep began.
* **BOUNDED, NOT POINT-IDENTIFIED.** The report carries no tick feed: the reconstructed mark is the set
  of trade prints, fresh for only **0.3%** of the timeline (median gap 32 s, p90 388 s, max 49 h). Any
  drawdown threshold evaluated off-print carries unbounded error. This single fact explains every
  symptom that previously looked like a rule error — 212–698-minute leads that *grew* under a freshness
  gate, negative leads, and an M15 proxy that pointed at the wrong side in 3 of 6 events.
* **Why the rescue exists.** `PendingPriceIsValid` requires a buy stop above the ask, so once price
  marches past a buy level's lattice price that level can never be re-armed — the trend-side lattice is
  destroyed level by level. Three independent corroborations: rescue cycles are duration ranks
  `[1,3,9,11,13,22]` of 99; the more-exhausted side (`gone[trend] > gone[opp]`) identifies the rescued
  side **5/6** where the price proxy managed 3/6; and in 4 of 6 events the first 2x order sits at the
  very next level beyond the deepest occupied trend-side level. Duration alone is a confound but not the
  rule — top-22 by duration leaves 16 falsifiers, and cycle 204 ran 55.52 h without ever rescuing.
* **Best exact predictor found (not a replica parameter).** `maxfill[trend] >= 16` alone: miss 1,
  falsifiers 21, side **5/6**, lead median **10.3 min**. At `>= 19`: lead median **4.3 min**, zero
  negative leads. Compare the best price-based row anywhere: lead median 212 min, side 3/6. `maxfill ≡
  maxopen` identically, proving nothing closes on the losing side. Recorded as corroboration of the
  exhaustion mechanism, **not** proposed as a new gate — the six values span 12–25 with no clean cut.
* The breakeven-liquidation clause formerly listed here is **refuted** — see §B.

### F2. `.ex5` hashes are meaningless — the MQL5 compiler is non-deterministic
Two consecutive compiles of byte-identical source produced **112,986** and **114,142** bytes with
different MD5s. Never use `.ex5` size or hash as a source-integrity check, and do not read a perpetually
`M mql5/*.ex5` git status as evidence of a source change. Compare `.mq5`/`.mqh` sources instead.
Compile via `Start-Process -Wait` (as `scripts/build.ps1` does) — MetaEditor detaches if invoked
directly, returning exit 0 without producing a log or a binary.


### G. Large-Trend Survival Mechanism
There is NO special trend-survival module. Survival in 40–50+ point runs emerges from the invariants
above: trailing SLs continuously bank realized cash while the static lattice re-arms harvest pullbacks,
and the cycle exits when `realized + floating >= $30`. Floating drawdown at exit is offset by banked
realized cash — that offset is the entire mechanism, and it only works if the EA is allowed to *hold*
the drawdown. This is why the recenter and breakeven exits were so damaging: they liquidated the
drawdown before the realized cash had finished accumulating against it.

The economics confirm where the money comes from. In the final regime, SL closures sum to
**+$10,683.93** while basket flattens sum to **-$2,760.06** (448 wins / 511 losses). The trailing
ratchet is the profit engine; the basket exit is a *reset*, and it is expected to be net-negative.
Any change that makes the basket exit fire more often is therefore a direct transfer out of the
profit engine.

---

## 3. Evidence Standard For Any Claimed Invariant

Every constant above that is marked CONFIRMED was established by **first-fire lead-time scoring**, and
nothing else counts. Coverage alone ("the rule is true at the moment the EA closed") is the weak half of
the test and it passed every wrong rule in this project's history. The strong half is **prematurity**.

For a candidate rule, reconstruct the full per-tick ledger over each cycle, find the *first* tick at
which the rule becomes true, and report:

```
lead = decision_time - first_true_time

lead ~ 0     the rule fires when the EA fired          -> admissible
lead >> 0    the rule would have fired early           -> REFUTED
never true   the rule misses this exit                 -> incomplete
```

A correct rule shows a median lead near zero (one 20 s timer tick) on nearly every cycle. `net >= 30`
scores a median lead of **5.6 s**. Both deleted rules scored median leads in the *hours*. Harness:

* `tools/forensics/q3o_ruleseparation.py` — scores arbitrary candidate rules; scan constants with it
  instead of guessing them.
* `tools/forensics/q3p_replicarules.py` — scores the rules **currently coded in the engine**, and prices
  the disagreement in dollars. Run this after any exit-logic change.
* `tools/forensics/q3m_flattenseg.py` — cycle segmentation from flatten sweeps (the EA's own boundary,
  since `StartCycle()` is reachable only from `CYCLE_IDLE`, which requires a fully closed basket).
* `tools/forensics/q1c_market_identity.py` — the market-price inversion that confirmed the ratchet.

Regime and pacing harness (the 2026-07-24 break):

* `tools/forensics/q4a_execpacing.py` — deployment / cancel / close cadences; found the close bimodality.
* `tools/forensics/q4b_closemode.py` — the **run-length test** that identified the break. Order the sweeps
  in time, map each to a mode letter, count runs: a state-dependent rule on a 69/32 split gives ~45 runs, a
  configuration change gives 2. Use this before attributing any bimodality to a runtime condition.
* `tools/forensics/q4c_regimebreak.py` — re-measures 7 invariant families on both sides of the break. Run
  this after adding any new constant measured over Jul 14–30.
* `tools/forensics/q4d_rearmfloor.py` — the **floor-vs-spike discriminator** for delay parameters, with a
  background-corrected cadence test.
* `tools/forensics/q4e_pacingknobs.py` — `restart_delay_ms` floors and in-burst fill detection.
* `tools/forensics/q4f_cooldownfit.py` — the causal (ordering) test and linear fit for the fill cooldown.

Scripts run under `.venv/Scripts/python.exe` (bare `python` is a Microsoft Store stub and fails).
Parsing is stdlib-only — the venv has neither pandas nor openpyxl.

> **A modal bucket is not a parameter.** A delay `D` evaluated by a 100 ms timer admits **zero**
> observations below `D` — it is a floor. `rearm_delay_seconds = 5` was set from a spike and was wrong in
> both regimes. Before believing a timing constant, check for a floor and check that the pile above it
> stands above the local background.

> **Do not add a money-exit rule to `CheckCycleTargets()` without a q3o/q3p run showing a near-zero
> median lead.** Two plausible-sounding rules written from hypothesis in this file cost a measured
> **$6,362** across 100 cycles, against a final-regime trailing-stop profit of $10,684.

---

## 4. Standard Deployment & Verification Workflow

1. **Edit Source**: Update `mql5/include/StraddleEngine.mqh`, `ProfileCatalog.mqh`, etc.
2. **Compile**: Run MetaEditor on Windows (`0 errors, 0 warnings` required):
   `D:\MT5ReplicaObserverTerminal\metaeditor64.exe /portable /compile:D:\MT5ReplicaObserverTerminal\MQL5\Experts\StraddleReplicaVPS\StraddleReplicaReal.mq5`
3. **Deploy Artifacts**:
   * Copy `.ex5` to `C:\Users\HPUSER\Desktop\StraddleReplicaReal.ex5`.
   * Upload `.ex5` to AWS VPS `/home/ubuntu/mt5-straddle-shadow/MQL5/Experts/StraddleReplica/StraddleReplicaReal.ex5`.
   * Overwrite default `StraddleReplica.ex5` on VPS.
4. **Service Restart**:
   `sudo systemctl restart straddle-shadow-mt5.service`
5. **Verify Logs**: Confirm `[STR] Initialized profile=LATEST_30 levels=30 replica=true` in MQL5 logs.
