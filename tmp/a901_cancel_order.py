"""Does the Target cancel before it closes? The catalog and the banked metric disagree.

`ProfileCatalog.mqh` assigns `config.cancel_before_close=true` at only ten sites --
193 (JUNE_2K), 261 (LATEST_30) and 424/458/492/528/562/599 (the six STARWAVE_*),
plus 676 (the custom mirror) -- while `ResetProfile` defaults it to `false` at 31.
So HISTORICAL_50, HISTORICAL_60, AGGRESSIVE_30 and LOW_RISK_30 inherit `false`:
an 8-true / 4-false split identical to `replica_orphan_leak`.

That contradicts the banked V5 number.  `tmp/a901_v4578.py:313-317` scored
"cancel-before-close adherence" at 271/282 = 96.10% with HISTORICAL_50 at 100/100,
and its criterion is literal:

    if any(window_lo <= when.timestamp() <= first.timestamp() for when in cancels):
        bucket["cancel_ok"] += 1

i.e. "at least one lattice pending was cancelled in the 10 s window before the
first close".  With the flag `false`, `BeginClose()` (StraddleEngine.mqh:2754-2770)
sets `m_state=CYCLE_CLOSING` immediately, `CloseOnePosition()` drains every
position before `CancelOneOrder()` ever runs, and so EVERY cancel must land after
the LAST close.  That era should score ~0, not 100/100.  One of the two is wrong.

A one-sided window test cannot settle it, so this probe measures the ordering
directly and symmetrically.  Per cycle: take the terminal close group (the last
run of basket closes with no internal gap over 60 s) and every lattice pending
whose cancel time falls in that cycle, then classify

    CANCEL_FIRST  every cancel precedes the FIRST close   <- flag true
    CLOSE_FIRST   every cancel follows the LAST close     <- flag false
    INTERLEAVED   anything else

against each era's configured flag.  The classes are mutually exclusive and
exhaustive, so neither answer can hide in the definition.

Two confounds are handled rather than assumed away:

  * a HALTING close ignores the flag -- `m_state=(halt_after ? CYCLE_CLOSING :
    replica_close_state)` -- so a `true` era can legitimately show CLOSE_FIRST
    cycles.  Reported as its own column instead of being folded into a rate.
  * cancels are attributed by their END time, not by the placing order's open
    time, so a pending that outlives its own cycle cannot be scored against the
    wrong sweep.  The cross-boundary count is printed.

Parts 3 and 4 then answer V5's other two questions on the same population: the
per-close cadence (the "113 ms burst" claim) and the reverse-ticket LIFO rate.
"""
from __future__ import annotations

import collections
import statistics
import sys
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.forensics.dataset import load_all  # noqa: E402
from tools.forensics.linkage import CLOSE_BY_RE, SL_RE, TP_RE, link_exits  # noqa: E402

ERAS = [
    ("HISTORICAL_50", datetime(2026, 6, 23, 16, 17, 27), datetime(2026, 7, 2, 15, 24, 57)),
    ("HISTORICAL_60", datetime(2026, 7, 2, 15, 24, 57), datetime(2026, 7, 13, 11, 2, 45)),
    ("AGGRESSIVE_30", datetime(2026, 7, 13, 11, 2, 45), datetime(2026, 7, 13, 12, 32, 29)),
    ("LOW_RISK_30", datetime(2026, 7, 13, 12, 32, 29), datetime(2026, 7, 13, 15, 59, 39)),
    ("STARWAVE_30", datetime(2026, 7, 13, 15, 59, 39), datetime(2027, 1, 1)),
]

# What ProfileCatalog.mqh actually configures for each era, with the assignment
# site.  `false` rows are inherited from ResetProfile (line 31); no per-profile
# assignment exists for them.
CONFIGURED = {
    "HISTORICAL_50": (False, "inherited, ProfileCatalog.mqh:31"),
    "HISTORICAL_60": (False, "inherited, ProfileCatalog.mqh:31"),
    "AGGRESSIVE_30": (False, "inherited, ProfileCatalog.mqh:31"),
    "LOW_RISK_30": (False, "inherited, ProfileCatalog.mqh:31"),
    "STARWAVE_30": (True, "ProfileCatalog.mqh:261 (LATEST_30) / 424 (STARWAVE_30)"),
}

GROUP_GAP = 60.0  # seconds; splits a cycle's closes into liquidation groups


def era_of(when):
    for name, start, end in ERAS:
        if start <= when < end:
            return name
    return "?"


def is_basket_close(order) -> bool:
    """An EA market close: market type, filled, and NOT an SL/TP/close-by exit.

    `stamp_close_comment=false` on HISTORICAL_50/60 makes those closes carry an
    EMPTY comment, so the comment cannot be required to read `STR CLOSE`.  The
    in-source census at StraddleEngine.mqh:2878-2886 established that all 2,732
    empty-comment closes and all 1,010 `STR CLOSE` closes resolve to
    DEAL_ENTRY_OUT, so the type/state/comment triple is sufficient here.
    """
    if order.order_type not in ("buy", "sell") or order.state != "filled":
        return False
    comment = (order.comment or "").strip()
    if comment and comment != "STR CLOSE":
        return False
    if SL_RE.fullmatch(comment) or TP_RE.fullmatch(comment):
        return False
    if CLOSE_BY_RE.fullmatch(comment):
        return False
    return True


def groups(times, gap=GROUP_GAP):
    out = []
    for when in sorted(times):
        if out and (when - out[-1][-1]).total_seconds() <= gap:
            out[-1].append(when)
        else:
            out.append([when])
    return out


def main() -> int:
    orders, positions, deals, cycles = load_all()
    exit_order, _ed, _en, _st = link_exits(orders, positions, deals)
    position_of_order = {o.order_id: pid for pid, o in exit_order.items()}
    starts = [c.start for c in cycles]
    era_by_cycle = {c.index: era_of(c.start) for c in cycles}

    def which(when):
        index = bisect_right(starts, when) - 1
        return index if index >= 0 else -1

    # closes, by the cycle containing the close; cancels, by the cycle containing
    # the CANCEL time rather than the placement time.
    closes = collections.defaultdict(list)
    cancels = collections.defaultdict(list)
    cross_boundary = 0
    cancel_total = 0
    for order in orders:
        if is_basket_close(order):
            closes[which(order.open_time)].append(order)
            continue
        if order.is_grid and order.state == "canceled" and order.end_time is not None:
            cancel_total += 1
            home = which(order.end_time)
            if home != order.cycle:
                cross_boundary += 1
            cancels[home].append(order)

    print("=== part 0: population ===")
    print(f"    orders {len(orders)}   lattice pendings cancelled {cancel_total}   "
          f"basket close orders {sum(len(v) for v in closes.values())}")
    print(f"    cancels whose END time falls in a LATER cycle than their placement: "
          f"{cross_boundary} ({100.0*cross_boundary/max(1,cancel_total):.2f}%)")
    print(f"    cycles {len(cycles)}   with >=1 close {sum(1 for k in closes if k >= 0)}"
          f"   with >=1 cancel {sum(1 for k in cancels if k >= 0)}")
    print()
    print("    configured flag per era (what the replica would do):")
    for era, _s, _e in ERAS:
        flag, site = CONFIGURED[era]
        print(f"      {era:16s} cancel_before_close = {str(flag).lower():5s}   [{site}]")
    print()

    print("=== part 1: observed ordering of cancels against the terminal close group ===")
    print("    CANCEL_FIRST = every cancel before the first close (flag true)")
    print("    CLOSE_FIRST  = every cancel after the last close   (flag false)")
    print()
    verdicts = collections.defaultdict(collections.Counter)
    detail = collections.defaultdict(list)
    for cycle in cycles:
        close_orders = closes.get(cycle.index, [])
        cancel_orders = cancels.get(cycle.index, [])
        if not close_orders or not cancel_orders:
            continue
        runs = groups([o.open_time for o in close_orders])
        terminal = runs[-1]
        first_close, last_close = terminal[0], terminal[-1]
        before = sum(1 for o in cancel_orders if o.end_time < first_close)
        after = sum(1 for o in cancel_orders if o.end_time > last_close)
        total = len(cancel_orders)
        if before == total:
            verdict = "CANCEL_FIRST"
        elif after == total:
            verdict = "CLOSE_FIRST"
        else:
            verdict = "INTERLEAVED"
        era = era_by_cycle[cycle.index]
        verdicts[era][verdict] += 1
        detail[era].append({
            "cycle": cycle.index,
            "verdict": verdict,
            "n_cancel": total,
            "n_close": len(terminal),
            "groups": len(runs),
            "before": before,
            "after": after,
            "first_close": first_close,
            "last_close": last_close,
            "first_cancel": min(o.end_time for o in cancel_orders),
            "last_cancel": max(o.end_time for o in cancel_orders),
            "closes": [o for o in close_orders if first_close <= o.open_time <= last_close],
        })
    print(f"    {'era':16s} {'flag':>6} {'cycles':>7} {'CANCEL_FIRST':>13} "
          f"{'CLOSE_FIRST':>12} {'INTERLEAVED':>12}   matches flag")
    for era, _s, _e in ERAS:
        counter = verdicts.get(era)
        if not counter:
            continue
        flag = CONFIGURED[era][0]
        n = sum(counter.values())
        want = "CANCEL_FIRST" if flag else "CLOSE_FIRST"
        print(f"    {era:16s} {str(flag).lower():>6} {n:>7d} "
              f"{counter['CANCEL_FIRST']:>13d} {counter['CLOSE_FIRST']:>12d} "
              f"{counter['INTERLEAVED']:>12d}   "
              f"{counter[want]:>4d}/{n} = {100.0*counter[want]/n:6.2f}%")
    grand = collections.Counter()
    for counter in verdicts.values():
        grand.update(counter)
    print(f"    {'ALL':16s} {'':>6} {sum(grand.values()):>7d} "
          f"{grand['CANCEL_FIRST']:>13d} {grand['CLOSE_FIRST']:>12d} "
          f"{grand['INTERLEAVED']:>12d}")
    print()

    print("=== part 2: worked timelines, three cycles per era ===")
    print("      cyc  verdict       nC  nX grp   first cancel"
          "              first close                last close")
    for era, _s, _e in ERAS:
        rows = detail.get(era, [])
        if not rows:
            continue
        pick = rows[:2] + rows[len(rows) // 2:len(rows) // 2 + 1] + rows[-1:]
        seen = set()
        for row in pick:
            if row["cycle"] in seen:
                continue
            seen.add(row["cycle"])
            print(f"      {row['cycle']:3d}  {row['verdict']:12s} {row['n_cancel']:3d} "
                  f"{row['n_close']:3d} {row['groups']:3d}   {row['first_cancel']}   "
                  f"{row['first_close']}   {row['last_close']}   [{era}]")
    print()

    print("=== part 3: per-close cadence inside the terminal group ===")
    print("    V5 asks about a 113 ms burst per position.  Gap = consecutive close")
    print("    send times inside one terminal group, so it measures the pacer only.")
    print(f"    {'era':16s} {'gaps':>7} {'p05':>9} {'p50':>9} {'p95':>9} "
          f"{'<10ms':>7} {'10-95ms':>8} {'95-135ms':>9} {'>=135ms':>8}")
    for era, _s, _e in ERAS:
        gaps = []
        for row in detail.get(era, []):
            times = sorted(o.open_time for o in row["closes"])
            gaps.extend((b - a).total_seconds() * 1000.0
                        for a, b in zip(times, times[1:]))
        if not gaps:
            continue
        gaps.sort()
        n = len(gaps)
        print(f"    {era:16s} {n:>7d} {gaps[int(0.05*n)]:>9.1f} {gaps[n//2]:>9.1f} "
              f"{gaps[int(0.95*n)]:>9.1f} "
              f"{sum(1 for g in gaps if g < 10):>7d} "
              f"{sum(1 for g in gaps if 10 <= g < 95):>8d} "
              f"{sum(1 for g in gaps if 95 <= g < 135):>9d} "
              f"{sum(1 for g in gaps if g >= 135):>8d}")
    print()

    print("=== part 4: reverse-ticket LIFO inside the terminal group ===")
    print("    the engine sweeps strictly descending by POSITION TICKET")
    print("    (CollectTrackedPositionTickets 370-396 + the descending walks at")
    print("    2851 / 2897).  Pair-inversion rate = share of ordered close pairs")
    print("    whose tickets descend; 1.000 is exact reverse-ticket LIFO.")
    print(f"    {'era':16s} {'sweeps':>7} {'legs':>7} {'pairs':>8} {'inversion':>10} "
          f"{'exact rev':>10} {'exact fwd':>10}")
    for era, _s, _e in ERAS:
        pairs = concord = legs = sweeps = exact_rev = exact_fwd = 0
        for row in detail.get(era, []):
            seq = []
            for order in sorted(row["closes"], key=lambda o: (o.open_time, o.order_id)):
                pid = position_of_order.get(order.order_id)
                if pid is not None:
                    seq.append(pid)
            if len(seq) < 2:
                continue
            sweeps += 1
            legs += len(seq)
            local = local_ok = 0
            for i in range(len(seq)):
                for j in range(i + 1, len(seq)):
                    local += 1
                    if seq[j] < seq[i]:
                        local_ok += 1
            pairs += local
            concord += local_ok
            if local_ok == local:
                exact_rev += 1
            elif local_ok == 0:
                exact_fwd += 1
        if not pairs:
            continue
        print(f"    {era:16s} {sweeps:>7d} {legs:>7d} {pairs:>8d} "
              f"{concord/pairs:>10.3f} {exact_rev:>10d} {exact_fwd:>10d}")
    print()

    print("=== part 5: the old metric, recomputed, to locate the disagreement ===")
    print("    a901_v4578.py asked only 'is there a cancel in the 10 s BEFORE the")
    print("    first close'.  Run both tests on the same cycles and print them")
    print("    side by side: if the old test scores high where the symmetric one")
    print("    says CLOSE_FIRST, the old test was measuring the NEXT cycle's cancels.")
    print(f"    {'era':16s} {'cycles':>7} {'old: cancel in 10s pre-window':>31} "
          f"{'symmetric: CANCEL_FIRST':>25}")
    for era, _s, _e in ERAS:
        rows = detail.get(era, [])
        if not rows:
            continue
        old = 0
        for row in rows:
            lo = row["first_close"].timestamp() - 10.0
            hi = row["first_close"].timestamp()
            hits = [o for o in cancels[row["cycle"]] if lo <= o.end_time.timestamp() <= hi]
            if hits:
                old += 1
        new = sum(1 for r in rows if r["verdict"] == "CANCEL_FIRST")
        print(f"    {era:16s} {len(rows):>7d} {old:>13d} = {100.0*old/len(rows):>6.2f}%"
              f"{'':>10} {new:>10d} = {100.0*new/len(rows):>6.2f}%")
    print()

    print("=== part 6: how long is the cancel phase, and does it overlap the closes? ===")
    print("    span = last cancel - first cancel; lead = first close - last cancel")
    print("    (positive lead means the cancel phase finished before any close).")
    for era, _s, _e in ERAS:
        rows = detail.get(era, [])
        if not rows:
            continue
        spans = sorted((r["last_cancel"] - r["first_cancel"]).total_seconds() for r in rows)
        leads = sorted((r["first_close"] - r["last_cancel"]).total_seconds() for r in rows)
        print(f"    {era:16s} n={len(rows):4d}  cancel span (s) p05 {spans[int(0.05*len(spans))]:9.2f}"
              f"  p50 {statistics.median(spans):9.2f}  p95 {spans[int(0.95*len(spans))]:10.2f}")
        print(f"    {'':16s}         lead   (s) p05 {leads[int(0.05*len(leads))]:9.2f}"
              f"  p50 {statistics.median(leads):9.2f}  p95 {leads[int(0.95*len(leads))]:10.2f}"
              f"   negative lead {sum(1 for v in leads if v < 0)}/{len(leads)}")
    print()

    # ---------------------------------------------------------------- controls
    # Parts 3 and 4 are contaminated by the operator.  `close by` is
    # PositionCloseBy, which has NO call site anywhere in the EA, so its 12
    # occurrences date hand actions exactly and are an INDEPENDENT marker -- not
    # derived from cadence or ordering, which are the things being measured.
    manual = sorted(o.open_time for o in orders if o.order_type == "close by")
    contaminated = set()
    for era, _s, _e in ERAS:
        for row in detail.get(era, []):
            lo = row["first_close"].timestamp() - 60.0
            hi = row["last_close"].timestamp() + 60.0
            if any(lo <= when.timestamp() <= hi for when in manual):
                contaminated.add(row["cycle"])

    print("=== part 7: operator-contaminated sweeps, by the `close by` marker ===")
    print(f"    `close by` orders on the tape: {len(manual)}   "
          f"span {manual[0]} .. {manual[-1]}")
    print(f"    terminal sweeps with a `close by` within +-60 s: {len(contaminated)}"
          f" -> cycles {sorted(contaminated)}")
    print()
    print("      cyc  era              verdict       legs  min gap(ms)  median(ms)"
          "  inversion  nearest `close by`")
    for era, _s, _e in ERAS:
        for row in detail.get(era, []):
            if row["cycle"] not in contaminated:
                continue
            times = sorted(o.open_time for o in row["closes"])
            gaps = [(b - a).total_seconds() * 1000.0 for a, b in zip(times, times[1:])]
            seq = [position_of_order.get(o.order_id) for o in
                   sorted(row["closes"], key=lambda o: (o.open_time, o.order_id))]
            seq = [s for s in seq if s is not None]
            pairs = ok = 0
            for i in range(len(seq)):
                for j in range(i + 1, len(seq)):
                    pairs += 1
                    ok += 1 if seq[j] < seq[i] else 0
            near = min((abs((row["first_close"] - w).total_seconds()), w) for w in manual)
            print(f"      {row['cycle']:3d}  {era:16s} {row['verdict']:12s} "
                  f"{len(times):4d} {min(gaps, default=0.0):12.1f} "
                  f"{statistics.median(gaps) if gaps else 0.0:11.1f} "
                  f"{(ok/pairs) if pairs else float('nan'):10.3f}  "
                  f"{near[0]:8.3f} s before")
    print()

    print("=== part 8: parts 3 and 4 again, with the contaminated sweeps removed ===")
    print("    if the operator owns every sub-cadence burst and every forward sweep,")
    print("    the EA-only population must be single-moded at ~100 ms and 1.000.")
    print(f"    {'era':16s} {'sweeps':>7} {'legs':>6} {'gaps':>6} {'p05':>7} {'p50':>7} "
          f"{'p95':>8} {'<10ms':>6} {'10-95':>6} {'95-135':>7} {'>=135':>6} "
          f"{'inversion':>10} {'exact rev':>10}")
    grand = collections.Counter()
    for era, _s, _e in ERAS:
        rows = [r for r in detail.get(era, []) if r["cycle"] not in contaminated]
        if not rows:
            continue
        gaps = []
        pairs = concord = sweeps = exact_rev = legs = 0
        for row in rows:
            times = sorted(o.open_time for o in row["closes"])
            gaps.extend((b - a).total_seconds() * 1000.0
                        for a, b in zip(times, times[1:]))
            seq = [position_of_order.get(o.order_id) for o in
                   sorted(row["closes"], key=lambda o: (o.open_time, o.order_id))]
            seq = [s for s in seq if s is not None]
            if len(seq) < 2:
                continue
            sweeps += 1
            legs += len(seq)
            local = local_ok = 0
            for i in range(len(seq)):
                for j in range(i + 1, len(seq)):
                    local += 1
                    local_ok += 1 if seq[j] < seq[i] else 0
            pairs += local
            concord += local_ok
            if local_ok == local:
                exact_rev += 1
        gaps.sort()
        n = len(gaps)
        if not n:
            continue
        if era != "STARWAVE_30":
            grand["sweeps"] += sweeps
            grand["legs"] += legs
            grand["exact_rev"] += exact_rev
            grand["pairs"] += pairs
            grand["concord"] += concord
        print(f"    {era:16s} {sweeps:>7d} {legs:>6d} {n:>6d} {gaps[int(0.05*n)]:>7.1f} "
              f"{gaps[n//2]:>7.1f} {gaps[int(0.95*n)]:>8.1f} "
              f"{sum(1 for g in gaps if g < 10):>6d} "
              f"{sum(1 for g in gaps if 10 <= g < 95):>6d} "
              f"{sum(1 for g in gaps if 95 <= g < 135):>7d} "
              f"{sum(1 for g in gaps if g >= 135):>6d} "
              f"{(concord/pairs) if pairs else float('nan'):>10.3f} "
              f"{exact_rev:>4d}/{sweeps}")
    print(f"    {'the three zero-interval eras (H50+H60+LOW_RISK_30)':50s} "
          f"sweeps {grand['sweeps']}  legs {grand['legs']}  "
          f"pairs {grand['pairs']}  inversion "
          f"{grand['concord']/grand['pairs'] if grand['pairs'] else float('nan'):.4f}  "
          f"exact reverse {grand['exact_rev']}/{grand['sweeps']}")
    print()

    print("=== part 9: is the cancel->close handoff quantised to the OnTimer period? ===")
    print("    `CancelOneOrder()` sets m_state=CYCLE_CLOSING and RETURNS; the first")
    print("    close therefore cannot be sent until the NEXT OnTimer tick.  With")
    print("    OnTimer = MathMax(20, inter_order_delay_ms) = 100 ms, the lead from")
    print("    the last cancel to the first close must be one tick, not zero.")
    leads = []
    for era, _s, _e in ERAS:
        for row in detail.get(era, []):
            if row["cycle"] in contaminated or row["verdict"] != "CANCEL_FIRST":
                continue
            leads.append((row["first_close"] - row["last_cancel"]).total_seconds() * 1000.0)
    leads.sort()
    if leads:
        n = len(leads)
        print(f"    CANCEL_FIRST sweeps, operator-free: n={n}")
        print(f"    lead (ms): min {leads[0]:.0f}  p05 {leads[int(0.05*n)]:.0f}  "
              f"p50 {leads[n//2]:.0f}  p95 {leads[int(0.95*n)]:.0f}  max {leads[-1]:.0f}")
        buckets = collections.Counter()
        for value in leads:
            if value < 95:
                buckets["<95"] += 1
            elif value < 135:
                buckets["95-135"] += 1
            elif value < 1000:
                buckets["135-1000"] += 1
            else:
                buckets[">=1000"] += 1
        print("    " + "   ".join(f"{k} {v}" for k, v in
                                  sorted(buckets.items(), key=lambda kv: -kv[1])))
        inside = sum(1 for v in leads if 95 <= v < 135)
        print(f"    leads inside one 100 ms OnTimer tick [95,135): "
              f"{inside}/{n} = {100.0*inside/n:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
