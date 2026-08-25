"""Phase B4: validate the timestamp-class attribution and re-derive the taxonomy."""
from __future__ import annotations

import sys
from collections import Counter

sys.path.insert(0, r"C:\websites\mt5 2")
from tools.forensics.dataset import load_all, FINAL_REGIME_START  # noqa: E402
from tools.forensics.attribution import build_exit_index, attribute  # noqa: E402


def main() -> None:
    orders, positions, deals, cycles = load_all()
    class_by_time, order_by_time, deal_by_order = build_exit_index(orders, deals)

    print("distinct exit timestamps:", len(class_by_time))
    print("timestamps by class-set:",
          dict(Counter("|".join(sorted(v)) for v in class_by_time.values())))

    reason, mixed, missing = attribute(positions, class_by_time)
    print(f"\nattributed={len(reason)} mixed={mixed} missing={missing}")

    closed = [p for p in positions if not p.is_open]
    fr = [p for p in closed if p.open_time >= FINAL_REGIME_START]
    print("ALL:", dict(Counter(reason.get(p.position_id) for p in closed)))
    print("FR :", dict(Counter(reason.get(p.position_id) for p in fr)))

    # Cross-check: for 'sl' positions, is the recorded stop_loss consistent with
    # one of the [sl X] comments at that timestamp?
    import re
    SL = re.compile(r"^\[sl (\d+(?:\.\d+)?)\]$")
    ok = bad = 0
    for p in fr:
        if reason.get(p.position_id) != "sl":
            continue
        xs = set()
        for o, d in order_by_time.get(p.close_time, []):
            m = SL.fullmatch(o.comment or "")
            if m:
                xs.add(round(float(m.group(1)), 5))
        if p.stop_loss is not None and round(p.stop_loss, 5) in xs:
            ok += 1
        else:
            bad += 1
    print(f"\nSL positions whose recorded SL appears in a [sl X] comment at the "
          f"same instant: ok={ok} bad={bad}")

    # Sanity: STR CLOSE positions should have arbitrary close prices equal to
    # market, and their recorded SL may or may not be set.
    sc = [p for p in fr if reason.get(p.position_id) == "STR CLOSE"]
    print(f"\nSTR CLOSE final regime: n={len(sc)} "
          f"with_SL={sum(1 for p in sc if p.stop_loss)} "
          f"without_SL={sum(1 for p in sc if not p.stop_loss)}")
    slp = [p for p in fr if reason.get(p.position_id) == "sl"]
    print(f"sl final regime: n={len(slp)} "
          f"with_SL={sum(1 for p in slp if p.stop_loss)} "
          f"without_SL={sum(1 for p in slp if not p.stop_loss)}")

    # And how many positions closed at exactly their SL price?
    at_sl = sum(1 for p in slp if p.stop_loss and abs(p.close_price - p.stop_loss) < 1e-9)
    print(f"sl positions closing exactly at recorded SL: {at_sl}/{len(slp)}")


if __name__ == "__main__":
    main()
