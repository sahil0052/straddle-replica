"""Q3o: stop guessing constants -- score candidate exit rules by WHEN they fire.

Every exit rule proposed so far has been checked for coverage ("is it true at the
decision?").  That is the weak half of the test.  The strong half is prematurity: a
rule that is also true two hours earlier is refuted, because the EA did not close then.

So for every cycle reconstruct the full ledger series and, for each candidate rule,
find the FIRST tick at which the rule is true.  Then:

    lead = decision_time - first_true_time

    lead ~ 0        the rule fires when the EA fired            -> admissible
    lead >> 0       the rule would have fired early             -> REFUTED
    never true      the rule misses this exit                   -> incomplete

A correct rule has lead ~ 0 on nearly every cycle.  This single number scores coverage
and falsification together, and it lets the data choose the constants instead of me.
"""
from __future__ import annotations

import statistics
import sys
from bisect import bisect_left, bisect_right

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START, CONTRACT  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402

GRACE = 25.0          # ticks inside this window of the decision count as "at" it


def build_series():
    orders, positions, deals, cycles = load_all()
    class_by_time, _, _ = build_exit_index(orders, deals)
    reason, _, _ = attribute(positions, class_by_time)

    live = [p for p in positions
            if (p.open_time >= FINAL_REGIME_START
                or (p.close_time and p.close_time >= FINAL_REGIME_START))]
    live.sort(key=lambda p: p.open_time)
    open_times = [p.open_time for p in live]
    prints = sorted([(p.open_time, p.open_price) for p in live] +
                    [(p.close_time, p.close_price) for p in live
                     if p.close_time and p.close_price])
    pt_t = [t for t, _ in prints]
    pt_p = [x for _, x in prints]

    closers = sorted((p for p in live if not p.is_open and p.close_time
                      and reason.get(p.position_id) == "STR CLOSE"),
                     key=lambda p: p.close_time)
    sweeps, cur = [], [closers[0]]
    for prev, nxt in zip(closers, closers[1:]):
        if (nxt.close_time - prev.close_time).total_seconds() <= 120.0:
            cur.append(nxt)
        else:
            sweeps.append(cur)
            cur = [nxt]
    sweeps.append(cur)
    sweeps = [s for s in sweeps if s[0].close_time >= FINAL_REGIME_START]

    out = []
    for i, sw in enumerate(sweeps):
        if i == 0:
            continue
        S = sweeps[i - 1][-1].close_time
        dec = sw[0].close_time
        i0, i1 = bisect_left(pt_t, S), bisect_right(pt_t, dec)
        ser = []
        for k in range(i0, i1):
            t, m = pt_t[k], pt_p[k]
            r = f = v = 0.0
            nop = 0
            hi = bisect_right(open_times, t)
            for p in live[:hi]:
                if not p.is_open and p.close_time and p.close_time <= t:
                    if p.close_time > S:
                        r += p.net
                else:
                    f += p.dir * (m - p.open_price) * p.volume * CONTRACT
                    v += p.volume
                    nop += 1
            ser.append((t, r, f, r + f, v * CONTRACT, nop))
        if not ser:
            continue
        mk = sw[0].close_price
        fl_at = sum(p.dir * (mk - p.open_price) * p.volume * CONTRACT for p in sw)
        r_at = sum(p.net for p in live if not p.is_open and p.close_time
                   and S < p.close_time < dec)
        out.append(dict(idx=i, S=S, dec=dec, ser=ser,
                        realized_at=r_at, floating_at=fl_at, marked=r_at + fl_at,
                        dpp=sum(p.volume for p in sw) * CONTRACT, n=len(sw),
                        hrs=(dec - S).total_seconds() / 3600.0))
    return out


def score(rows, rule, label):
    """First-true-time scoring for one candidate rule."""
    leads, missed, early = [], [], []
    for r in rows:
        dec = r["dec"]
        hit = None
        for t, real, flt, net, dpp, nop in r["ser"]:
            if rule(real, flt, net, dpp, nop):
                hit = t
                break
        if hit is None:
            # is it true at the decision itself, using the exact marked values?
            if rule(r["realized_at"], r["floating_at"], r["marked"],
                    r["dpp"], r["n"]):
                leads.append(0.0)
            else:
                missed.append(r["idx"])
            continue
        lead = (dec - hit).total_seconds()
        leads.append(lead)
        if lead > 300.0:
            early.append((r["idx"], lead))
    n = len(rows)
    ok = sum(1 for x in leads if x <= GRACE)
    med = statistics.median(leads) if leads else float("nan")
    print(f"  {label:<52} fires {len(leads):>3}/{n}  at-decision {ok:>3}  "
          f"early>5m {len(early):>3}  missed {len(missed):>3}  "
          f"med lead {med:>9.1f}s")
    return dict(label=label, leads=leads, missed=missed, early=early, ok=ok)


def main() -> None:
    rows = build_series()
    print(f"cycles with a reconstructable series: {len(rows)}\n")

    print("=" * 118)
    print("A.  SINGLE-THRESHOLD RULES ON NET  (net = realized_since_start + floating)")
    print("=" * 118)
    for T in (10, 20, 25, 28, 30, 32, 35, 40, 50):
        score(rows, lambda re, fl, ne, dp, no, T=T: ne >= T, f"net >= {T}")

    print("\n" + "=" * 118)
    print("B.  PURE BREAKEVEN RULES  (would fire on the way up, so must be gated)")
    print("=" * 118)
    for T in (0, 10, 20):
        score(rows, lambda re, fl, ne, dp, no, T=T: ne >= T, f"net >= {T} (ungated)")

    print("\n" + "=" * 118)
    print("C.  TWO-RULE FAMILY:  net >= 30   OR   (floating <= -F  AND  net >= B)")
    print("    the gate is a deeply-underwater basket that has clawed back to flat")
    print("=" * 118)
    for F in (100, 150, 200, 250, 300):
        for B in (0, 5, 10):
            score(rows,
                  lambda re, fl, ne, dp, no, F=F, B=B: ne >= 30 or (fl <= -F and ne >= B),
                  f"net>=30 or (floating<=-{F} and net>={B})")

    print("\n" + "=" * 118)
    print("D.  TWO-RULE FAMILY:  net >= 30   OR   (realized >= R  AND  net >= B)")
    print("=" * 118)
    for R in (50, 100, 150, 200, 300):
        for B in (0, 5, 10):
            score(rows,
                  lambda re, fl, ne, dp, no, R=R, B=B: ne >= 30 or (re >= R and ne >= B),
                  f"net>=30 or (realized>=${R} and net>={B})")

    print("\n" + "=" * 118)
    print("E.  SCALED TARGET:  does the threshold scale with basket size?")
    print("    net >= min(30, k * dollars_per_point)  -- a heavy basket settles for less")
    print("=" * 118)
    for k in (0.25, 0.5, 0.75, 1.0, 1.5):
        score(rows, lambda re, fl, ne, dp, no, k=k: ne >= min(30.0, k * dp),
              f"net >= min(30, {k} * $/pt)")
    for k in (2.0, 3.0, 5.0):
        score(rows, lambda re, fl, ne, dp, no, k=k: ne >= k * no,
              f"net >= {k} * open_positions")

    print("\n" + "=" * 118)
    print("F.  WHERE DOES THE PLAIN net>=30 RULE GO WRONG?  full lead distribution")
    print("=" * 118)
    res = score(rows, lambda re, fl, ne, dp, no: ne >= 30.0, "net >= 30 (reference)")
    v = sorted(res["leads"])
    for lo, hi in [(-1, 25), (25, 60), (60, 300), (300, 1800), (1800, 7200),
                   (7200, 10**9)]:
        n = sum(1 for x in v if lo < x <= hi)
        print(f"    lead ({lo:>7},{hi if hi < 10**9 else 'inf':>7}] {n:>4} {'#' * n}")
    print(f"\n  cycles the rule MISSES entirely (net never reached 30): "
          f"{len(res['missed'])}")
    print(f"    {res['missed']}")
    print(f"\n  cycles where it would have fired >5 min early: {len(res['early'])}")
    for idx, lead in sorted(res["early"], key=lambda x: -x[1])[:15]:
        r = next(x for x in rows if x["idx"] == idx)
        print(f"    idx={idx:<4} lead={lead/60:>8.1f}m  $/pt={r['dpp']:>6.1f}  "
              f"hrs={r['hrs']:>6.1f}  marked={r['marked']:>9.2f}")


if __name__ == "__main__":
    main()
