"""Q4b: what selects burst vs paced flatten mode in the Target EA?

q4a established:
  * deployment and cancellation both run at 101-102 ms/action -> one action per
    100 ms timer tick, exactly the replica's model.
  * flatten closes are bimodal: 69/101 burst at 0.106 s/close, 32/101 pace at
    20.188 s/close, and the paced sweeps are PERFECTLY uniform (0 of 279 internal
    gaps below 1 s, 96.4% in [15,25] s) with a tell-tale alternating 20.2/19.9
    signature -- the fingerprint of a whole-second `TimeCurrent()` comparison
    against a 20 s threshold sampled by a ~100 ms timer.

So close_interval_seconds=20 is real, and something switches it off 69 times.
No basket property separated the groups (identical gross lots, identical $/pt,
similar size, age and hour).  The remaining candidate class is TIME: a settings
change inside the final regime.  If the modes are contiguous in date, parity must
track whichever regime is LAST, and close_interval_seconds is a regime parameter
rather than a constant.

Panel A: every flatten sweep in date order, with its mode.
Panel B: per-day mode counts, to see whether the split is contiguous or interleaved.
Panel C: if interleaved, test the remaining within-day discriminators.
"""
from __future__ import annotations

import statistics
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

SWEEP_GAP = 120.0
BURST_MAX = 1.0


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    live = [p for p in positions
            if (p.open_time >= FINAL_REGIME_START
                or (p.close_time and p.close_time >= FINAL_REGIME_START))]
    closers = sorted((p for p in live if not p.is_open and p.close_time
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

    rows = []
    for s in sweeps:
        g = [(b.close_time - a.close_time).total_seconds() for a, b in zip(s, s[1:])]
        med = statistics.median(g) if g else None
        rows.append(dict(
            t=s[0].close_time,
            n=len(s),
            med=med,
            mode=("?" if med is None else ("burst" if med <= BURST_MAX else "paced")),
            dpp=sum(p.volume for p in s) * CONTRACT,
            net=sum(p.net for p in s),
        ))

    print("=" * 104)
    print("A. EVERY FINAL-REGIME FLATTEN SWEEP IN DATE ORDER")
    print("=" * 104)
    print(f"  {'#':>3} {'close time':<20} {'mode':<6} {'n':>3} {'med gap':>9} "
          f"{'$/pt':>7} {'sweep net':>10}")
    for i, r in enumerate(rows):
        mg = "-" if r["med"] is None else f"{r['med']:.3f}s"
        print(f"  {i:>3} {r['t'].strftime('%Y-%m-%d %H:%M:%S'):<20} {r['mode']:<6} "
              f"{r['n']:>3} {mg:>9} {r['dpp']:>7.2f} {r['net']:>10.2f}")

    print()
    print("=" * 104)
    print("B. PER-DAY MODE COUNTS -- contiguous (regime change) or interleaved?")
    print("=" * 104)
    byday = defaultdict(lambda: [0, 0])
    for r in rows:
        byday[r["t"].date()][0 if r["mode"] == "burst" else 1] += 1
    print(f"  {'date':<12} {'burst':>6} {'paced':>6}   pattern")
    for d in sorted(byday):
        b, p = byday[d]
        seq = "".join("B" if r["mode"] == "burst" else "P"
                      for r in rows if r["t"].date() == d)
        print(f"  {str(d):<12} {b:>6} {p:>6}   {seq}")

    first_paced = next((i for i, r in enumerate(rows) if r["mode"] == "paced"), None)
    last_burst = next((i for i in range(len(rows) - 1, -1, -1)
                       if rows[i]["mode"] == "burst"), None)
    print()
    if first_paced is not None and last_burst is not None:
        print(f"  first paced sweep at index {first_paced} "
              f"({rows[first_paced]['t']})")
        print(f"  last  burst sweep at index {last_burst} "
              f"({rows[last_burst]['t']})")
        if first_paced > last_burst:
            print("  => CONTIGUOUS: all bursts precede all paced sweeps. "
                  "This is a settings change; parity must use the LATER regime.")
        else:
            print("  => INTERLEAVED: the two modes coexist throughout. "
                  "close_interval_seconds is state-dependent, not a date regime.")

    print()
    print("=" * 104)
    print("C. WITHIN-SWEEP DISCRIMINATORS (only meaningful if interleaved)")
    print("=" * 104)
    burst = [r for r in rows if r["mode"] == "burst"]
    paced = [r for r in rows if r["mode"] == "paced"]

    def stat(grp, key):
        v = [x[key] for x in grp]
        return (statistics.median(v), min(v), max(v)) if v else (0, 0, 0)

    for key in ("n", "dpp", "net"):
        bm, bmn, bmx = stat(burst, key)
        pm, pmn, pmx = stat(paced, key)
        print(f"  {key:<6} burst med={bm:>9.2f} [{bmn:>9.2f},{bmx:>9.2f}]   "
              f"paced med={pm:>9.2f} [{pmn:>9.2f},{pmx:>9.2f}]")

    # Does mode persist run-to-run?  A state-dependent switch should show runs.
    seq = "".join("B" if r["mode"] == "burst" else "P" for r in rows)
    runs = []
    cur = seq[0]
    ln = 1
    for ch in seq[1:]:
        if ch == cur:
            ln += 1
        else:
            runs.append((cur, ln))
            cur, ln = ch, 1
    runs.append((cur, ln))
    print(f"\n  mode sequence : {seq}")
    print(f"  runs          : {len(runs)}  "
          f"(a random 69/32 split would give ~{2*69*32/101+1:.0f})")
    print(f"  longest burst run : {max((l for m,l in runs if m=='B'), default=0)}")
    print(f"  longest paced run : {max((l for m,l in runs if m=='P'), default=0)}")


if __name__ == "__main__":
    main()
