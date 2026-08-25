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
* **THE THRESHOLD, CONFIRMED MARK-FREE AT n=99.** A flatten closes the whole basket, so the money the
  cycle banks at its exit — `realised_before_sweep + realised_by_sweep` — **is** the total the EA saw at
  its decision, and it needs no mark, no spread assumption and no bid/ask model. Median = **`29.32`**.
  That is a fourth independent estimator agreeing with the three already in-code (`29.31` / `29.36` /
  `30.46`). `cycle_target_money = 30.0` is settled; stop re-testing it.
* **THE MARKED RECONSTRUCTION CANNOT ADJUDICATE THIS RULE, AND NEVER COULD.** Use the free calibration
  point before trusting any mark-walk: at `t0`, the instant the Target itself flattened, its own value
  *was* the threshold. Measured there, the reconstruction reads **median `25.23`, mean `12.25`,
  p10 `-35.59`, p90 `+47.70`, only 16/99 inside [28,34], and 66/99 BELOW 30**. The cause is measured too:
  price dispersion inside one flatten sweep is median `0.610` pt / p90 `6.790` pt, and multiplied by
  20–170 $/pt of gross exposure that is a **p90 error of `$102.30` per reading**. The $30 threshold is
  **0.29×** the instrument's own noise floor. A reconstruction with less resolution than the quantity it
  measures cannot produce a finding about that quantity in either direction.
* **RETRACTED — the "gated cycles" were gap-throughs, not a missing gate.** The claim that 5–13 cycles
  held a total above $30 without closing is **withdrawn**. The basket total is not continuous in time: it
  carries 20–170 $/pt, so an ordinary tick sequence moves it by hundreds of dollars between two 100 ms
  polls. Dividing each overshoot by its own gross sensitivity gives the price move needed to explain it —
  **median `0.83` pt, p75 `1.58` pt, and 46 of 47 within the `6.79` pt dispersion already observed inside
  the sweeps.** Every previously-gated cycle resolves as ordinary noise: 194 → `1.20p`, 187 → `1.62p`,
  250 → `2.41p`, 253 → `4.44p`, 252 → `6.41p`. Four hypotheses died getting here — starvation (0/10
  intervals busy, cycle 194 idle 85.9 min), EA downtime (the silences are the broker's break, below), a
  size-scaled target (0/100 at the decision), and cycle-boundary attribution (`R carry = 0.00` on all ten,
  and only 3/99 cycles have any money settling after their own sweep).
* **THE SYMMETRY IS THE PROOF, and it forbids adding a condition.** Exits overshoot by a move of `0.83` pt
  and undershoot by `0.91` pt — same magnitude, opposite sign, one mechanism. A hold rule produces a
  one-sided right tail; a second exit rule produces a one-sided left tail. Symmetric smearing around a
  median of `29.32` is the signature of a single threshold that is exactly right, with execution physics
  doing the rest. **The outcome distribution being wide (29/99 inside [25,35]) is therefore not evidence of
  a missing rule and must not be treated as such.**
* **`close_interval_seconds = 20` costs `$1.96` per flatten. Do not touch it.** Tested as the suspected
  mechanism behind the negative exits and **refuted on three counts**: the median slip delta across the
  regime break is `+0.06` pt = **`$62.74` total over 32 post-break flattens**; slip does not scale with
  sweep span (under-5 s `0.03p`, 1–3 min `0.41p`, over-3 min `-0.02p` — non-monotonic, longest bucket
  best); and three of the six worst exits happened **BEFORE** the break in **1–3 second** sweeps at
  `0.1 s`/close. A loss taken in one second is not caused by 20-second pacing.
* **THE BROKER SESSION BREAK, measured at minute resolution: `22:58 → 23:59` server time, 62 minutes with
  zero activity of any kind, account-wide, every one of the 13 trading days**, plus two Fri→Mon holes of
  `2964.1` and `2947.4` min. Any mark taken at the far side of one of these values the entire basket at a
  reopen extreme — cycle 244's "crossing" sits at a gap-before of **177,824 s**. Filter on gap-before, not
  on hour-of-day: it subsumes both the daily break and the weekend.
* **OPEN RESIDUALS** (characterised, deliberately not modelled):
  * 6/100 exits land below `-$25` (worst `-149.29`) with no discoverable rule — no floor, no distance
    signature, no pinned quantity, and young cycle ages (four under 20 min). Most consistent with
    discretionary/manual flattens. Do not invent a rule for these; that is exactly what cost $6,362.
    The sweep-slip explanation was tested and refuted (above), so this note stands as originally written.

### B1b. The accumulator is CYCLE-scoped — confirmed on both sides (`tools/forensics/accumulator_scope.py`)
§B settled the **threshold** (`$30.00`, four independent estimators, mark-free median `29.32` at n=99). It
did **not** settle the **scope** of the accumulator compared against it — and **scope is a bigger divergence
than value.** If the Target's accumulator were day- or run-scoped rather than per-cycle, every exit in the
run would fire at the wrong moment and no threshold tuning could fix it.

The three hypotheses make catastrophically different predictions, so the test is cheap and decisive:

* **DAY-scoped** — the day total already cleared 30, so cycles 2..n of each day exit at a per-cycle value
  near **zero**. Predicts a large *negative* ordinal-within-day gradient.
* **RUN-scoped** — after the first winning cycle the condition is permanently satisfied; per-cycle exit
  values **collapse toward zero** and stay there.
* **CYCLE-scoped** — every ordinal and every quartile centres on 30 alike.

Measured on the mark-free identity (a flatten closes the whole basket, so
`realised_before_sweep + realised_by_sweep` **is** the total the EA saw):

| ordinal in day | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| median exit $ | 30.94 | 33.80 | 32.29 | 37.97 | 26.27 | 24.49 |
| frac ≥ $20 | 69% | 77% | 69% | 75% | 75% | 100% |

first-of-day median `30.94` vs later-in-day `29.32` → difference **−1.63**, where day-scoping predicts a
large negative number. Run quartiles `33.59 / 28.77 / 26.84 / 41.42` show **no collapse**. **76% of cycles
exit on ≥$20 of their OWN money**; only 12/99 at ≤$5. The test had real power — all **13 trading days had
≥2 cycles**.

**The tails were interrogated, not accepted.** An ordinal-1 mean of `$345.78` against a median of `$30.94`
at n=13 means one cycle carries ~$4.1k, which could have been a cycle-attribution bug invalidating every
median above. Discriminated by pre/burst split + cycle span: cycle 175's `$3,592` is the known 2.10-lot
basket ripping in a fast sweep (burst `+$3,541`), cycle 187's `+690/−578` split is the 23.2-hour
session-break boundary. **5%-trimmed mean `$34.48`** — the tails do not contaminate the central estimate.

**Replica side confirmed too.** `m_cycle_realized` is zeroed per cycle (`StraddleEngine.mqh:1642/1798/2537`),
and the recalculation path passes `m_cycle_started_msc` as a hard lower bound into `CCycleDealLedger::
TryRecalculate`, which triple-filters on **magic, symbol, and `DEAL_TIME_MSC >= cycle_started_msc`**.
`HistorySelect` runs at second resolution so it loads a *superset*; the explicit msc comparison narrows it
exactly. Cycle-scoped by construction. **This question is closed — do not reopen it with a mark-based script.**

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

### D2. The ratchet's money-weighted fingerprint — a PREDICTED HOLE, measured
The ratchet equation in §D was derived from SL-price reconstruction. `tools/forensics/parity_verdict.py`
confirms it a second time with a **completely independent instrument**: close price vs open price only —
no SL reconstruction, no marks, no spread model, no linkage to the SL comment value.

The two-stage design makes a falsifiable prediction about where stops land. Stage 1 activates at 2.0
favourable steps with SL at exact breakeven, then trails 2.0 steps behind, so a peak in `[2.0, 3.0)`
closes in `[0.0, 1.0)`. Stage 2 tightens to 1.0 step at 3.0 steps, so a peak `>= 3.0` closes at `>= 2.0`.
**A correct two-stage ratchet therefore cannot close between 1.0 and 2.0 steps of profit.** A
single-stage trail would fill that band smoothly.

Measured over all 2,480 final-regime SL closures, as **density per unit step width** (raw counts
understate it because the bands differ in width):

| band | positions/step | reading |
|---|---|---|
| breakeven `[-0.25, 0.25)` | **700** | stage-1 activation spike |
| `[0.25, 1.0)` | **755** | stage-1 trail |
| `[1.0, 2.0)` | **138** | **the predicted hole** |
| `[2.0, 3.0)` | **799** | stage-2 floor |

The hole is depleted **5.5×–5.8×** against the bands on either side of it. `median steps locked = 2.134`
sits *on* the stage-2 floor; `p10 = 0.125` sits *on* breakeven. A one-stage trail at 1.0 step would pile
up at 1.0; a one-stage trail at 2.0 could never reach 2.0+. Only two stages with a tighten produce this.

The 138 that *do* land in the hole are **NOT** a pacing signature. That was an earlier, wrong reading
(recorded here and in `StopScheduler.mqh`, both now corrected). See §D3 — they are stop-fill slippage,
and at the level the EA actually *wrote*, the band is empty.

### D3. The instrument hierarchy — and the exact wall (`tools/forensics/attested_stop.py`)
§D2's hole is measured on **fill price**, which conflates two different things. Parity depends on only one:

* the **DECISION** — where the EA *wrote* the stop. This is the rule, and the only thing the replica must match.
* the **EXECUTION** — where the position *filled*. Differs by broker slippage, which **no parameter in
  either EA controls**.

Three instruments measure the decision, in ascending order of quality:

| instrument | what it is | mass in forbidden band `(1.0,2.0)` |
|---|---|---|
| `close_price` | the fill, + slippage | 138 / 2,480 = **5.56%** |
| `position.stop_loss` | newest SL write on the record | 8 / 2,480 = **0.32%** |
| **`[sl <price>]` exit comment** | **the broker's attestation of the level that fired** | 8 / 2,480 = **0.32%** |

The band fills up *exactly* as the measurement degrades. That monotone ordering is the whole argument.

On the attested price — 2,480 samples, no SL reconstruction, no mark, no spread model — the density per
0.05 step across the wall is:

| `[0.50,1.00)` | `[1.00,1.25)` | `[1.25,1.50)` | `[1.50,1.75)` | `[1.75,1.90)` | `[1.90,1.95)` | `[1.95,2.00)` | `[2.00,2.05)` |
|---|---|---|---|---|---|---|---|
| 43.3 | **0.0** | **0.0** | **0.0** | **0.0** | **0.0** | 8.0 | 56.0 |

**The forbidden band `(1.00, 1.95)` is exactly empty — 0 of 2,480** — with large mass immediately on both
sides. The only residue is 8 stops in `[1.95, 2.00)`, and each is **0, 1 or 2 ticks** below 2.0000 (tick
0.01 on a step of ~1.36 = 0.735% of a step): that is `NormalizeDouble`/`MathRound` quantisation plus the
`stops_level` clamp, not a rule difference. This is the strongest ratchet evidence in the project.

**Monotonicity verified on the same population.** `position.stop_loss` equals the attested fired level in
**99.8%** of cases, is tighter in 0.1% (a later ratchet write) and looser in 0.1% (≤ 0.105 steps, clamp
noise). A loosening write would contradict the return conditions at the bottom of `StopScheduler::Calculate`;
effectively none occur.

**7.7% of stops fill BETTER than their own trigger** (192/2,480, median +0.857 steps, max +5.765). Three
hypotheses were tested and two refuted: mislabelled flattens (only 3.1% flatten-adjacent vs 1.1% baseline)
and stale-write pacing (42.2% exceed the 1.0-step bound a tighten can be wrong by). It is genuine
favourable slippage — a bounce between trigger and fill. Not an EA behaviour, not a classifier defect.

> **ACTIVATION IS NOT EXACT BREAKEVEN.** Do not "correct" it to zero. Because the gate is polled on a
> 100 ms timer, the tick that first satisfies `favorable_steps >= 2.0` has usually already overshot to
> `2.0 + e`, so the stop lands at `entry + e*step`. Measured on attested prices: **median +0.124 steps,
> p10 +0.029, p90 +0.222, and 0 of 317 at exact breakeven.** The distribution is **strictly positive**,
> which is the signature of a late poll — a `lock_offset_price` rule would give a constant, and
> `pre_tighten != lock_trigger` would allow negatives. The offset is emergent from polling, not a
> parameter, so the replica reproduces it automatically.

**Hard falsifier passed:** 0 of 2,480 decisions sit below entry. The activation rule holds without
exception across every measurable SL closure. (30 positions *fill* below entry — slippage again.)

**The two derivations agree to four decimals.** §D reached the empty band by SL-price *reconstruction* and
reported mode B spanning `+1.9853 … +17.5221`. §D3 reached it from the broker's *attested* fired price and
found the 8 residue stops spanning `1.9853 … 2.0000`. **The same boundary value, `1.9853`, falls out of two
instruments that share no intermediate quantity.** Likewise §D's "zero negative `locked` values" and §D3's
hard falsifier are the same fact measured twice. Treat the wall as settled.

### D4. Volume-blindness (`tools/forensics/ratchet_edges.py`, panel C)
The ratchet has no volume term, so band structure must be identical across lot tiers. Measured medians
**2.162 / 1.886 / 1.964 / 2.815** steps locked across volumes 0.01 / 0.06 / 0.12 / 0.15, with consistent
breakeven and `>=2.0` shares. Confirmed volume-blind, as coded.

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

### H. The guard-halt divergence class — `latest_30_real_safe.set` IS A PARITY TRAP
Every other section here asks whether the replica computes the same *number* the Target computed. This
class is different in kind and worse. **A guard that fires while the Target keeps trading is not a 1%
divergence** — the replica enters `CYCLE_HALTED` and never returns, so correlation from that instant is
zero. Rule parity is irrelevant if the machine is switched off.

Two mechanisms, both in `StraddleEngine.mqh`, both fed by the same four `m_runtime` numbers:
* `SafetyTriggered()` (2317) — checked from `CheckCycleTargets` (2837); drives `BeginClose(reason, true)`
  (2352), which sets `m_halted=true`. The halt is **two-phase**: the basket flattens first, and only once
  it is flat does `m_state=CYCLE_HALTED` land (2458), logging `cycle_complete`/`halted` and clearing
  persistence. **Terminal** — there is no automatic return.
* `ExposureAllowsRearm()` (2279) — five call sites (1344, 1901, 1942, 2144, 2190). Returns false and the
  level is skipped. **Does not halt and does not log a halt** — the lattice just stops being replaced,
  silently changing the grid geometry the rest of the run depends on. The quieter and more dangerous one.

> **Line numbers in this section have rotted once already** (they read 2293/2814/2434/2255/2136/2173 before
> being re-measured). Prefer the function names; treat the numbers as hints and re-grep before trusting one.

**Production is disarmed, so there is no exposure today.** `STR_SAFETY_ENABLED_DEFAULT` is `false`
(`mql5/StraddleReplicaReal.mq5:12`) and `latest_30_real_exact.set` sets `SafetyEnabled=false`, so
`SafetyTriggered()` returns at 2320 before reading anything and `ExposureAllowsRearm()` returns true
immediately. The Target itself never halted.

But `latest_30_real_safe.set` arms all four, and `tools/forensics/guard_envelope.py` measures its numbers
against the Target's **own historical envelope**. They are not margins; two of them are tripwires and one
of them **the Target already walked through**:

| guard in the "safe" preset | compiled default | Target's measured worst | verdict |
|---|---|---|---|
| `MaxGrossLots = 2.20` | `2.20` | 2.10 lots (cycle 175) | **4.5% margin** — never fired, but razor-thin |
| `DailyLossLimit = 500.0` | **`0.0` = disabled** | **−$668.78** running intraday (2026-07-17) | **BREACHED — halts on 2 of 13 days** |
| `MaxEquityLossPercent = 10.0` | `20.0` | 5.69% pessimistic (cycle 234, $980.05 on a $17,233 balance) | ~1.8× — but **unadjudicated** |
| `MaxSpreadPoints = 1000.0` | `1000.0` | unmeasurable (no bid/ask series) | correctly sized; a $10 gold spread is a real liquidity hole |

**`DailyLossLimit = 500.0` is the single worst configuration value in the project.** `TodayOwnedProfit()`
(2290–2315) is re-evaluated on *every timer tick*, so the binding quantity is the **running intraday
minimum**, not the day's closing P&L. Measured on the final regime:

* **2026-07-14** dips to **−$640.29** and closes at **+$3,145.20** — the *best day in the sample*. The
  replica would have flattened and parked in `CYCLE_HALTED` before earning any of it.
* **2026-07-17** dips to **−$668.78** and recovers to −$250.99. The replica would have locked in −$500 and
  then never traded again — strictly worse than the Target on a day the Target survived.

The Target therefore demonstrably runs with **no daily loss limit**. For parity this value must be `0.0`,
which is also the compiled default — the `.set` file *enables a tripwire the code deliberately leaves off*.

> **Statistic discipline, recorded because this table was wrong once.** An earlier version of this row read
> "−$499.78 (2026-07-06), margin $0.22 = 0.04%". `guard_envelope.py` now reproduces that figure **to the
> cent** and shows what it was: the worst **closing** daily total over the **whole** dataset (2026-07-06 is
> before `FINAL_REGIME_START`). The correct statistic for a tick-polled guard is the running minimum, and it
> is −$668.78 — a breach, not a near-miss. Both statistics are printed side by side in Panel C so the two
> numbers can never look like a contradiction again. **Never size a polled guard from a closing total.**

`MaxGrossLots = 2.20` is *exactly one side's full ladder* (`10×0.01 + 10×0.06 + 10×0.15`), and 4.40 for
both sides. A number that happens to equal one side of a two-sided strategy is a coin flip, not a risk
limit — cycle 175's 2.10 came from base tiers alone, so **one more 0.15 level → 2.25 > 2.20 → halt**.
Panel B tests the quieter mechanism exactly: replaying the exposure timeline and asking
`ExposureAllowsRearm`'s own question at each of the 3,441 fills, **0 would have been refused** at 2.20 (or
at any larger limit). So the silent-truncation risk I expected is **not realised in this dataset** — the
prediction was wrong and the measurement says so. The margin is still only 0.10 lots.

The equity guard is measured against `m_cycle_start_balance`, recaptured fresh each cycle (1641/1797), so it
does **not** amortise: every cycle gets the same leash. It is **UNADJUDICATED and must stay that way** —
`equity = balance + floating`, and the report has no bid/ask series. Note the failure mode that makes a
realised-only measurement useless here: the dangerous instant is right after deployment, when *many legs are
underwater simultaneously and realised is still exactly zero*, so true equity drawdown **exceeds** realised
drawdown. (An earlier Panel D argued the opposite — "floating is positive while the winner runs" — and that
one-sided claim is wrong; it is now refuted in the script's own text.) The pessimistic all-legs-at-their-
worst figure peaks at **5.69%**, and §H's older mark-based **$1,043.86** exceeds it, which is consistent:
a mark-based peak can be worse than the sum of settled losses. Also correcting this section: that $1,043.86
was compared against a *notional* $10k balance, but the observed balance at the worst cycles was
**$15.6k–$17.6k**, so the guard is **not** "already exceeded" at the balances actually observed.

**The account grew ~10× inside this window (balance $1,864.12 → $19,720.46).** `MaxEquityLossPercent` is
proportional and self-scales; `DailyLossLimit` is absolute, so $500 is **27%** of the account at the start
of the window and **2.5%** at the end. A fixed-dollar guard cannot be correctly sized across a 10× balance
change — which is the structural reason the compiled default disables it.

Panels A–C of `guard_envelope.py` are **exact** (volume and settled deal money need no mark). Panel D is
mark-free but pessimistic, and is stated only as an order-of-magnitude. Keep that distinction.

**If these guards are ever wanted, they must sit well OUTSIDE the Target's measured envelope** — a
disaster brake, not a risk budget. Raising live-money limits is the operator's decision; do not change
them silently in either direction.

**Code change made here (log-only, zero parity risk): the terminal `halted` event now names the guard.**
`BeginClose()` logged the reason on `close_begin` (2362), but `close_begin` also fires for *every ordinary
`$30` basket exit*, so the telemetry holds hundreds of them and only one is fatal — and the flatten sweep
in between closes one position per timer tick, so the two lines can be far apart. The terminal event at
2460 logged an **empty** reason. Added `m_halt_reason` (declared beside `m_halted` at 45), set in lockstep
at the single `m_halted=halt_after` assignment (2356), and emitted on the `halted` event. `CYCLE_HALTED`
has no automatic exit, so that line is the last thing the EA ever says: it has to be self-diagnosing. It
is only ever read while `m_halted` is true, so the four `m_halted=false` reset sites need no clear.
Compiles 0 errors / 0 warnings. This changes no trading decision — only what the log tells the operator.

**Fix applied.** Of the five `ExposureAllowsRearm` sites, 1344/1901/1942 already logged
`safety_rearm_blocked`; **2136 and 2173 returned with no log at all** — and those two are the
*trend-rescue replacement* paths that place `lots × trend_rescue_volume_multiplier` (2.0×), i.e. the paths
that hit the cap first. A rescue silently failing to place its replacement leaves the trend side starved
(already structurally fragile via `PendingPriceIsValid`, §G) with nothing in telemetry. Both now log with
reason `max_gross_lots_rescue`. Zero cost while safety is disarmed; pure observability once armed.
Compiles clean (`0 errors, 0 warnings`).

### I. The money-weighted parity verdict (`tools/forensics/parity_verdict.py`)
Parity must be weighted by **money, not parameter count**. "24 of 25 parameters confirmed = 96%" is
meaningless: `stop_scan_newest_first` reorders a scan loop, `cycle_target_money` decides when every basket
in the run terminates. The denominator is `|realised money|` in the final regime — **$31,766.29** across
**3,435 closed positions / 100 cycles**, net **+$7,837.55**.

**There are exactly TWO closure mechanisms, and only two.** No `tp`, no `close_by`, no `<none>`, no
unlinked exits — a structural result, not a summary:

| mechanism | positions | net | share of \|money\| | win rate |
|---|---|---|---|---|
| `basket_flatten` | 955 | −$2,787.30 | 66.0% | 46.7% |
| `sl` | 2,480 | +$10,624.85 | 34.0% | **96.0%** |

That asymmetry is the designed division of labour (§G): the ratchet harvests winners one at a time, so the
sweep is left holding whatever had not yet run. (§G's slightly different totals use a looser
still-open/close-time filter; same measurement, same conclusion.)

Every dollar's governing parameter is either **CONFIRMED** against the Target's own fills or
**UNMEASURABLE** (the dataset cannot distinguish the replica's choice from any other, so any choice
matches). Exactly **one** item is UNMEASURABLE, and it governs $0:
* the commission-inclusion asymmetry (`OwnedFloatingProfit` excludes commission+fee; `m_cycle_realized`
  and `TodayOwnedProfit` include them) — **commission is exactly $0.00 on 901018**. Document it; do not
  "fix" it, because changing it would be inventing a rule.

> CORRECTION: an earlier draft of this section listed `SYMBOL_TRADE_STOPS_LEVEL` /
> `SYMBOL_TRADE_FREEZE_LEVEL` as a second unmeasurable gap, on the grounds that neither appears in
> `TradeGateway.mqh`. That is true of that file and **false as a claim about the EA**. Both are read
> live from the symbol: `STOPS_LEVEL` at `StraddleEngine.mqh:2511`, passed into `CStopScheduler::Calculate`
> on *every* ratchet evaluation, where it clamps the desired SL (`MathMin(desired, bid - stops_level*point)`
> for buys, `MathMax(desired, ask + ...)` for sells); and both at `StraddleEngine.mqh:1317-1318` inside
> `PendingPriceIsValid`. The broker minimum is therefore respected dynamically, per symbol, per
> evaluation — this was never a gap. Do not re-add it to the ledger.

**Unmodelled residual: $296.80 = 0.9% of the denominator** (5/100 cycles below −$25: 231, 270, 256, 263,
192). These are not replica rule failures — `basket_slipcost.py` showed the $30 rule fired correctly
(`pre` sat at the threshold) and the money was lost during the sweep, a sweep the replica reproduces by
construction because `close_interval_seconds = 20` matches. But no discovered rule *predicts* them, so
they stay in the residual. **Money-weighted parity coverage: 99.07%.**

Rule-level parity is complete for everything this dataset can adjudicate. Outcome-level parity is **not**
100% and cannot be: a 100 ms poll on a basket carrying 20–170 $/pt resolves the $30 rule to ±one
tick-jump. That is a property of the strategy, not a defect of the replica — the Target's own exit
distribution has median 29.32 with the same smear (§B1). The parameter set is **exhausted** against this
dataset; the only things that would move the number are a second Target dataset with non-zero commission,
or broker stops-level telemetry from the replica's own account.

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
