"""How much resolution does the instrument actually have?  And is $30 safe without it?

basket_calibrate.py Panel A is the result that reorganises everything.  Evaluated at
t0 -- the instant the Target itself chose to flatten, where its own value WAS the
threshold -- my reconstruction reads:

    median 25.23    mean 12.25    only 16/99 inside [28,34]    p10 -35.59  p90 +47.70

So the instrument has a roughly +/-$40 error band at the one point where the true
answer is known.  Every "gated cycle" I have been reasoning about crossed at a value
between 30.91 and 227.30.  All but two of those sit inside the band.  The 10 gated
cycles and the 59-66 "sub-30 flattens" are the two tails of my own measurement error,
which is why they never dissolved under any single correction: starvation, decision
instant, half-spread, size scaling.  I was tuning a model against noise.

Panel C of that run says the same thing in the shape of the numbers.  Tightening the
stale-mark filter should shrink an artifact and leave a rule alone.  Instead the whole
population degraded together -- on-time 30 -> 24, sub-30 59 -> 67, gated flat at 8-10.
A rule does not behave that way.  An instrument losing samples does.

Two things to establish here.

1. WHERE the error comes from, so the bound is principled rather than empirical.  The
   suspect is the mark.  At the flatten the EA values the basket against a live
   bid/ask; I use the close price of one position in a sweep that closes ~20 positions
   at ~20 different prices.  On a basket carrying 50-150 $/point of gross exposure, a
   0.5-point mark error is $25-75.  If measured mark error x gross reproduces the
   observed band, the diagnosis is confirmed and the instrument's floor is known.

2. Whether the $30 rule still stands without marks at all.  It should: a flatten is a
   burst that closes everything, so the money the cycle banks is
   `threshold - closing slippage`, and that quantity needs no mark.  This decomposes
   c.realized by WHEN each position closed, which also tests the attribution fault
   flagged in basket_leadtime.py's docstring and never actually measured -- the one
   remaining candidate for why cycles read +632 and +518 when the rule fires at 30.
"""
from __future__ import annotations

import statistics
import sys
from datetime import timedelta

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402

TARGET = 30.0
SWEEP = 300.0        # seconds after the first STR CLOSE that count as "the burst"


def main() -> None:
    orders, positions, deals, cycles = load_all()
    fin = [c for c in cycles if c.start >= FINAL_REGIME_START]

    # ---- A. mark dispersion inside a single flatten sweep -----------------
    print("=" * 104)
    print("A. WHERE THE ERROR COMES FROM -- price dispersion inside one flatten burst")
    print("=" * 104)
    print("  The EA marks the basket once, at a live bid/ask.  I mark it with one close")
    print("  price out of the ~20 in the sweep.  The spread of those prices IS my error.")
    print()
    disp, implied = [], []
    for c in fin:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl:
            continue
        t0 = min(cl)
        sw = [p for p in c.positions if p.close_time and p.close_price
              and t0 - timedelta(seconds=5) <= p.close_time <= t0 + timedelta(seconds=SWEEP)]
        if len(sw) < 3:
            continue
        pr = [p.close_price for p in sw]
        gross = sum(p.volume * CONTRACT for p in sw)
        d = max(pr) - min(pr)
        disp.append(d)
        implied.append(d * gross / 2.0)     # half the range x gross = $ error
    print(f"  cycles with a >=3-position sweep: {len(disp)}")
    print(f"  price range within the sweep (points): median {statistics.median(disp):.3f}"
          f"   p90 {sorted(disp)[9*len(disp)//10]:.3f}   max {max(disp):.3f}")
    print(f"  implied $ error (half-range x gross): median ${statistics.median(implied):.2f}"
          f"   p90 ${sorted(implied)[9*len(implied)//10]:.2f}"
          f"   max ${max(implied):.2f}")
    print()
    print("  compare with the observed calibration band at t0: p10 -35.59, p90 +47.70.")
    print("  If these match, the instrument floor is mark dispersion x gross exposure,")
    print("  and no amount of rule-tuning can see through it.")

    # ---- B. is $30 confirmable WITHOUT any mark? --------------------------
    print()
    print("=" * 104)
    print("B. THE MARK-FREE ESTIMATOR -- what the cycle actually BANKED")
    print("=" * 104)
    print("  A flatten closes the whole basket, so realised_at_exit = threshold - slip.")
    print("  This uses only settled deal money.  No mark, no spread assumption.")
    print()
    rows = []
    for c in fin:
        cl = [o.open_time for o in c.orders
              if o.comment and o.comment.strip().upper().startswith("STR CLOSE")]
        if not cl:
            continue
        t0 = min(cl)
        pre = burst = post = 0.0
        npre = nburst = npost = 0
        for p in c.positions:
            if p.is_open or not p.close_time:
                continue
            if p.close_time < t0 - timedelta(seconds=5):
                pre += p.net; npre += 1
            elif p.close_time <= t0 + timedelta(seconds=SWEEP):
                burst += p.net; nburst += 1
            else:
                post += p.net; npost += 1
        rows.append(dict(i=c.index, pre=pre, burst=burst, post=post,
                         npre=npre, nburst=nburst, npost=npost,
                         total=pre + burst + post, final=c.realized))

    tot = [r["pre"] + r["burst"] for r in rows]
    print(f"  cycles: {len(rows)}")
    print(f"  realised at the exit burst (pre + burst), NO post-sweep money:")
    print(f"    median {statistics.median(tot):>8.2f}   mean {statistics.mean(tot):>8.2f}")
    print(f"    p25 {sorted(tot)[len(tot)//4]:>8.2f}   p75 {sorted(tot)[3*len(tot)//4]:>8.2f}")
    print(f"    inside [20,40]: {sum(1 for x in tot if 20<=x<=40)}/{len(tot)}"
          f"   inside [25,35]: {sum(1 for x in tot if 25<=x<=35)}/{len(tot)}")

    # ---- C. the attribution fault, finally measured ----------------------
    print()
    print("=" * 104)
    print("C. THE ATTRIBUTION FAULT -- money credited to a cycle that closed LATER")
    print("=" * 104)
    print("  dataset.py assigns a position to the cycle its OPEN time falls in.  Anything")
    print("  closing after the flatten sweep is money this cycle never had at its")
    print("  decision.  This is the last untested candidate for the +632 / +518 reads.")
    print()
    bad = [r for r in rows if r["npost"] > 0]
    print(f"  cycles with money settling AFTER their own flatten sweep: {len(bad)}/{len(rows)}")
    if bad:
        print(f"  {'cyc':>5} {'pre':>9} {'burst':>9} {'POST':>9} {'total':>9}"
              f" {'n post':>7}  reading")
        for r in sorted(bad, key=lambda r: -abs(r["post"]))[:14]:
            note = ("POST dominates -> `final` is not this cycle's exit value"
                    if abs(r["post"]) > abs(r["pre"] + r["burst"]) else "minor")
            print(f"  {r['i']:>5} {r['pre']:>9.2f} {r['burst']:>9.2f} {r['post']:>9.2f}"
                  f" {r['total']:>9.2f} {r['npost']:>7}  {note}")
        pt = [r["pre"] + r["burst"] for r in bad]
        print(f"\n  those cycles' exit value WITHOUT the post-sweep money:"
              f" median {statistics.median(pt):.2f}")

    print()
    print("=" * 104)
    print("D. VERDICT ON THE INSTRUMENT")
    print("=" * 104)
    band = sorted(implied)[9 * len(implied) // 10]
    print(f"  mark-driven error floor (p90): ${band:.2f} per reading.")
    print(f"  the $30 threshold is {30.0/band:.2f}x that floor.")
    print("  -> a marked reconstruction CANNOT adjudicate a $30 threshold on baskets")
    print("     this heavy.  The rule's VALUE is established by the mark-free burst")
    print("     total; its TIMING is below the noise floor and must not be claimed")
    print("     either way.  The 10 'gated' cycles are retracted as an artifact.")


if __name__ == "__main__":
    main()
