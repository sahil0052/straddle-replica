"""Phase B2: exact closure taxonomy using deal-level linkage."""
from __future__ import annotations

import sys
from collections import Counter

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.linkage import link_exits, exit_reason, SL_RE  # noqa: E402


def main() -> None:
    orders, positions, deals, cycles = load_all()
    exit_order, exit_deal, entry_deal, stats = link_exits(orders, positions, deals)
    print("linkage:", stats)

    closed = [p for p in positions if not p.is_open]
    fr = [p for p in closed if p.open_time >= FINAL_REGIME_START]
    print(f"closed={len(closed)} final_regime_closed={len(fr)}")

    print("\n=== ALL history closure reasons ===")
    print(dict(Counter(exit_reason(p, exit_order) for p in closed)))
    print("\n=== FINAL regime closure reasons ===")
    frc = Counter(exit_reason(p, exit_order) for p in fr)
    print(dict(frc))

    print("\n=== FINAL regime: reason x profit sign ===")
    for r in sorted(frc):
        w = l = z = 0
        tot = 0.0
        for p in fr:
            if exit_reason(p, exit_order) != r:
                continue
            tot += p.net
            if p.net > 1e-9:
                w += 1
            elif p.net < -1e-9:
                l += 1
            else:
                z += 1
        print(f"  {r:<12} n={w+l+z:>5} wins={w:>5} losses={l:>5} zero={z:>5} "
              f"sum_net={tot:>10.2f}")

    # --- SL comment price vs recorded stop_loss vs close price ------------
    print("\n=== SL closures: comment price == recorded SL == close price? ===")
    bad_sl = 0
    bad_close = 0
    n = 0
    worst = []
    for p in fr:
        o = exit_order.get(p.position_id)
        if o is None:
            continue
        m = SL_RE.fullmatch(o.comment or "")
        if not m:
            continue
        n += 1
        csl = float(m.group(1))
        if p.stop_loss is None or abs(p.stop_loss - csl) > 1e-6:
            bad_sl += 1
        d = abs((p.close_price or 0.0) - csl)
        if d > 1e-6:
            bad_close += 1
            worst.append((d, p, csl))
    worst.sort(key=lambda t: -t[0])
    print(f"n={n} recorded_SL!=comment_SL: {bad_sl}   close_price!=comment_SL: {bad_close}")
    for d, p, csl in worst[:10]:
        print(f"   slip={d:.3f} {p.side} lvl={p.comment} entry={p.open_price} "
              f"sl={p.stop_loss} close={p.close_price} comment_sl={csl} net={p.net}")

    # --- the loss-at-SL cases -------------------------------------------
    print("\n=== FINAL regime SL closures with net < 0 ===")
    losers = [p for p in fr if exit_reason(p, exit_order) == "sl" and p.net < -1e-9]
    print("count:", len(losers))
    for p in sorted(losers, key=lambda p: p.net)[:20]:
        o = exit_order[p.position_id]
        drift = (p.stop_loss - p.open_price) * (1 if p.side == "buy" else -1)
        print(f"   {p.open_time} c={p.comment:<8} {p.side:<4} vol={p.volume} "
              f"entry={p.open_price} sl={p.stop_loss} close={p.close_price} "
              f"net={p.net:>7.2f} sl-entry={drift:>7.3f} cyc={p.cycle} {o.comment}")


if __name__ == "__main__":
    main()
