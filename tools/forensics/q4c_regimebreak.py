"""Q4c: a settings change lands mid-"final regime" on 2026-07-24.  What else moved?

q4b found the flatten close mode is perfectly contiguous: 69 burst sweeps from
Jul 14 to Jul 24 09:10, then 32 paced sweeps from Jul 24 15:48 to Jul 30 17:10.
Two runs where a random 69/32 split gives ~45.  That is an operator settings
change (or a new EA build), not a state-dependent switch, and it means
close_interval_seconds=20 is CORRECT for the regime parity must track.

But it also means the window AGENTS.md calls "the final regime" contains a
discontinuity, and every invariant measured over Jul 14-30 is potentially a blend
of two configurations.  The $30 basket target, the two-stage trail, the lot tiers
and the step were all fitted across the break.

This script splits at the break and re-measures each invariant on both sides.
Anything that differs is a contaminated constant and parity must take the LATE
value.  Anything that matches is strengthened, not weakened, by the split.
"""
from __future__ import annotations

import bisect
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

BREAK = datetime(2026, 7, 24, 12, 0, 0)   # between the last burst and first paced sweep
SWEEP_GAP = 120.0


def side(t: datetime) -> str:
    return "EARLY" if t < BREAK else "LATE"


def show(label: str, early: list[float], late: list[float], fmt: str = "8.4f") -> None:
    def d(v):
        if not v:
            return f"{'n=0':>26}"
        return (f"n={len(v):<5} med={statistics.median(v):{fmt}} "
                f"[{min(v):{fmt}},{max(v):{fmt}}]")
    print(f"  {label:<28} EARLY {d(early)}")
    print(f"  {'':<28} LATE  {d(late)}")


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    fin_pos = [p for p in positions
               if (p.open_time >= FINAL_REGIME_START
                   or (p.close_time and p.close_time >= FINAL_REGIME_START))]

    # ------------------------------------------------------------------ panel 1
    print("=" * 100)
    print("1. BASKET TARGET -- model-free: realized_since_cycle_start + flatten_net")
    print("=" * 100)
    closers = sorted((p for p in fin_pos if not p.is_open and p.close_time
                      and reason.get(p.position_id) == "STR CLOSE"),
                     key=lambda p: p.close_time)
    sweeps, cur = [], [closers[0]]
    for prev, nxt in zip(closers, closers[1:]):
        if (nxt.close_time - prev.close_time).total_seconds() <= SWEEP_GAP:
            cur.append(nxt)
        else:
            sweeps.append(cur)
            cur = [nxt]
    sweeps.append(cur)
    sweeps = [s for s in sweeps if s[0].close_time >= FINAL_REGIME_START]

    others = sorted((p for p in fin_pos if not p.is_open and p.close_time
                     and reason.get(p.position_id) != "STR CLOSE"),
                    key=lambda p: p.close_time)
    otimes = [p.close_time for p in others]

    e_tot, l_tot = [], []
    for i in range(1, len(sweeps)):
        lo = sweeps[i - 1][-1].close_time
        hi = sweeps[i][0].close_time
        a, b = bisect.bisect_right(otimes, lo), bisect.bisect_left(otimes, hi)
        realized = sum(p.net for p in others[a:b])
        total = realized + sum(p.net for p in sweeps[i])
        (e_tot if side(hi) == "EARLY" else l_tot).append(total)
    show("exact flatten total $", e_tot, l_tot, "9.2f")
    for lab, v in (("EARLY", e_tot), ("LATE", l_tot)):
        if v:
            near = sum(1 for x in v if 25.0 <= x <= 45.0)
            print(f"  {lab:<5} in [25,45]: {near}/{len(v)} ({100*near/len(v):.0f}%)   "
                  f"below 0: {sum(1 for x in v if x < 0)}")

    # ------------------------------------------------------------------ panel 2
    print()
    print("=" * 100)
    print("2. TRAIL RATCHET -- locked = dir*(sl-entry)/step; the empty band is the proof")
    print("=" * 100)
    cstarts = [c.start for c in cycles]
    e_lock, l_lock = [], []
    for p in fin_pos:
        if p.is_open or not p.stop_loss or p.stop_loss <= 0.0:
            continue
        j = bisect.bisect_right(cstarts, p.open_time) - 1
        if j < 0:
            continue
        st = getattr(cycles[j], "step", None)
        if not st or st <= 0:
            continue
        lk = p.dir * (p.stop_loss - p.open_price) / st
        (e_lock if side(p.open_time) == "EARLY" else l_lock).append(lk)
    for lab, v in (("EARLY", e_lock), ("LATE", l_lock)):
        if not v:
            print(f"  {lab}: none")
            continue
        a = [x for x in v if x < 1.0]
        b = [x for x in v if x >= 1.0]
        neg = sum(1 for x in v if x < -1e-9)
        print(f"  {lab:<5} n={len(v):<5} negatives={neg}")
        if a:
            print(f"        mode A (locked<1) n={len(a):<5} "
                  f"{min(a):+.4f} .. {max(a):+.4f}")
        if b:
            print(f"        mode B (locked>=1) n={len(b):<5} "
                  f"{min(b):+.4f} .. {max(b):+.4f}")
        if a and b:
            print(f"        EMPTY BAND ({max(a):.4f}, {min(b):.4f})  "
                  f"width {min(b)-max(a):.4f}  <-- must be ~1.00 step")

    # ------------------------------------------------------------------ panel 3
    print()
    print("=" * 100)
    print("3. LOT TIERS by level band, and levels_per_side")
    print("=" * 100)
    tiers = {"EARLY": defaultdict(Counter), "LATE": defaultdict(Counter)}
    maxlv = {"EARLY": 0, "LATE": 0}
    for o in orders:
        if not o.is_grid or o.open_time < FINAL_REGIME_START or o.level is None:
            continue
        s = side(o.open_time)
        band = "L1-10" if o.level <= 10 else ("L11-20" if o.level <= 20 else "L21-30")
        tiers[s][band][round(o.volume, 2)] += 1
        maxlv[s] = max(maxlv[s], o.level)
    for s in ("EARLY", "LATE"):
        print(f"  {s:<5} max level = {maxlv[s]}")
        for band in ("L1-10", "L11-20", "L21-30"):
            c = tiers[s][band]
            tot = sum(c.values())
            print(f"        {band:<7} {dict(sorted(c.items()))}"
                  + (f"   (n={tot})" if tot else ""))

    # ------------------------------------------------------------------ panel 4
    print()
    print("=" * 100)
    print("4. STEP SPACING and fitted anchor/step divisor")
    print("=" * 100)
    e_st, l_st, e_dv, l_dv = [], [], [], []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        st = getattr(c, "step", None)
        an = getattr(c, "anchor", None)
        if not st or st <= 0:
            continue
        (e_st if side(c.start) == "EARLY" else l_st).append(st)
        if an:
            (e_dv if side(c.start) == "EARLY" else l_dv).append(an / st)
    show("step (points)", e_st, l_st, "8.4f")
    show("anchor / step", e_dv, l_dv, "9.2f")

    # ------------------------------------------------------------------ panel 5
    print()
    print("=" * 100)
    print("5. RE-ARM DELAY -- position close -> replacement order placed at same level")
    print("=" * 100)
    pos_by_id = {p.position_id: p for p in positions}
    percyc = defaultdict(list)
    for o in orders:
        if o.is_grid and o.open_time >= FINAL_REGIME_START and o.level is not None:
            percyc[(o.cycle, o.side, o.level)].append(o)
    e_rd, l_rd = [], []
    for key, seq in percyc.items():
        seq.sort(key=lambda o: o.open_time)
        for prev, nxt in zip(seq, seq[1:]):
            if prev.state != "filled":
                continue
            p = pos_by_id.get(prev.order_id)
            if not p or p.is_open or not p.close_time:
                continue
            d = (nxt.open_time - p.close_time).total_seconds()
            if 0.0 <= d <= 300.0:
                (e_rd if side(nxt.open_time) == "EARLY" else l_rd).append(d)
    show("re-arm delay (s)", e_rd, l_rd, "8.2f")
    for lab, v in (("EARLY", e_rd), ("LATE", l_rd)):
        if not v:
            continue
        b5 = sum(1 for x in v if 4.5 <= x <= 6.5)
        b20 = sum(1 for x in v if 19.0 <= x <= 22.0)
        print(f"  {lab:<5} near 5s: {b5:<4} near 20s: {b20:<4} "
              f"other: {len(v)-b5-b20}")

    # ------------------------------------------------------------------ panel 6
    print()
    print("=" * 100)
    print("6. CADENCES -- deployment and cancel, both predicted = InterOrderDelayMs")
    print("=" * 100)
    e_dep, l_dep = [], []
    for c in cycles:
        if c.start < FINAL_REGIME_START:
            continue
        t = [o.open_time for o in c.burst_orders]
        g = [(b - a).total_seconds() for a, b in zip(t, t[1:])]
        if g:
            (e_dep if side(c.start) == "EARLY" else l_dep).append(statistics.median(g))
    show("deployment gap (s)", e_dep, l_dep, "8.4f")

    canc = sorted((o for o in orders if o.is_grid and o.state == "canceled"
                   and o.end_time and o.end_time >= FINAL_REGIME_START),
                  key=lambda o: o.end_time)
    cs, cur2 = [], [canc[0]]
    for prev, nxt in zip(canc, canc[1:]):
        if (nxt.end_time - prev.end_time).total_seconds() <= SWEEP_GAP:
            cur2.append(nxt)
        else:
            cs.append(cur2)
            cur2 = [nxt]
    cs.append(cur2)
    e_cn, l_cn, e_sz, l_sz = [], [], [], []
    for s in [x for x in cs if len(x) >= 5]:
        t = [o.end_time for o in s]
        g = [(b - a).total_seconds() for a, b in zip(t, t[1:])]
        if side(t[0]) == "EARLY":
            e_cn.append(statistics.median(g)); e_sz.append(float(len(s)))
        else:
            l_cn.append(statistics.median(g)); l_sz.append(float(len(s)))
    show("cancel gap (s)", e_cn, l_cn, "8.4f")
    show("pendings per cancel sweep", e_sz, l_sz, "8.1f")

    # ------------------------------------------------------------------ panel 7
    print()
    print("=" * 100)
    print("7. MISC -- take-profits, rescue volumes, cycle duration")
    print("=" * 100)
    for lab in ("EARLY", "LATE"):
        sel = [p for p in fin_pos if side(p.open_time) == lab]
        tp = sum(1 for p in sel if p.take_profit and p.take_profit > 0.0)
        print(f"  {lab:<5} positions={len(sel):<6} with TP={tp}")
    resc = {"EARLY": Counter(), "LATE": Counter()}
    for o in orders:
        if o.is_grid and o.open_time >= FINAL_REGIME_START:
            v = round(o.volume, 2)
            if v in (0.12, 0.30, 0.02):
                resc[side(o.open_time)][v] += 1
    for lab in ("EARLY", "LATE"):
        print(f"  {lab:<5} rescue/odd volumes: {dict(sorted(resc[lab].items()))}")
    e_du, l_du = [], []
    for i in range(1, len(sweeps)):
        lo = sweeps[i - 1][-1].close_time
        hi = sweeps[i][0].close_time
        (e_du if side(hi) == "EARLY" else l_du).append((hi - lo).total_seconds() / 60.0)
    show("cycle duration (min)", e_du, l_du, "8.1f")


if __name__ == "__main__":
    main()
