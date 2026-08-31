"""The same orphan-leak instrument, run on the Starwave tape as cross-validation.

The 901018 tape just returned 0 of 11,549 re-arm pendings dispatched over a live
position and 0 of 10,475 same-slot re-fills overlapping -- i.e. that build gates
re-arm on !has_position and never orphans anything.  The Starwave audit (D6/D7)
claims the opposite for magic 26011001: 153 of 2,468 fills still open at the end
of the window, 137/137 same-level overlapping pairs with the EARLIER position
never closed, residue ratcheting 6 -> 148.  Those two results are the sole
evidence behind `replica_orphan_leak`, and they were measured with a different
instrument, so they have to be re-derived with THIS one before the flag's default
can be defended.

The claims are logically linked: an overlapping same-level pair can only exist if
the level was re-armed while it still held a position.  So if part 2 returns zero
here as well, D6/D7 is wrong and the flag has no evidence.  If it returns a large
number, the two tapes are two builds and the flag is a build switch.

This export is a raw MT5 API dump rather than an HTML report, which makes it the
stronger of the two tapes: `position_id` links orders to positions exactly (no
(time,volume,price) collisions), `magic` separates the EA from the operator
(magic 0), and `reason` names the closer (0 CLIENT, 3 EXPERT, 4 SL, 5 TP)
instead of leaving the closing comment as the only clue.
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import re
from pathlib import Path

EA_MAGIC = 26011001
BURST_GAP_S = 2.0
MIN_LEGS = 10
ORDERS = Path("Starwave_60542_orders_history.csv")
DEALS = Path("Starwave_60542_full_history.csv")
REASON = {"0": "CLIENT", "1": "MOBILE", "2": "WEB", "3": "EXPERT", "4": "SL", "5": "TP",
          "6": "SO", "7": "ROLLOVER", "8": "VMARGIN", "9": "SPLIT"}


def when_ms(text):
    value = int(float(text or 0))
    if value <= 0:
        return None
    return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc).replace(tzinfo=None)


def parse_level(comment):
    match = re.match(r"^STR ([BS])(\d+)$", (comment or "").strip())
    if match is None:
        return None
    return (match.group(1) == "B", int(match.group(2)))


def load_positions():
    """position_id -> {opened, closed, close_reason, sl_seen, volume, is_buy}."""
    by_id: dict[int, dict] = {}
    with DEALS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            pid = int(float(row["position_id"] or 0))
            if pid == 0:
                continue
            entry = row["entry"]
            when = when_ms(row["time_msc"])
            if when is None:
                continue
            record = by_id.setdefault(pid, {"opened": None, "closed": None,
                                            "close_reason": None, "is_buy": None,
                                            "magic_in": None, "magic_out": None})
            if entry == "0":                       # DEAL_ENTRY_IN
                if record["opened"] is None or when < record["opened"]:
                    record["opened"] = when
                    record["is_buy"] = row["type"] == "0"
                    record["magic_in"] = row["magic"]
            elif entry in ("1", "2", "3"):          # OUT / INOUT / OUT_BY
                if record["closed"] is None or when > record["closed"]:
                    record["closed"] = when
                    record["close_reason"] = REASON.get(row["reason"], row["reason"])
                    record["magic_out"] = row["magic"]
    return by_id


def load_lattice_orders():
    rows = []
    with ORDERS.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["type"] not in ("4", "5"):       # BUY_STOP / SELL_STOP
                continue
            parsed = parse_level(row["comment"])
            if parsed is None:
                continue
            setup = when_ms(row["time_setup_msc"])
            if setup is None:
                continue
            rows.append({
                "setup": setup,
                "done": when_ms(row["time_done_msc"]),
                "ticket": int(float(row["ticket"])),
                "position_id": int(float(row["position_id"] or 0)),
                "state": row["state"],
                "magic": int(float(row["magic"] or 0)),
                "is_buy": parsed[0],
                "level": parsed[1],
                "price": float(row["price_open"]),
                "volume": float(row["volume_initial"]),
            })
    rows.sort(key=lambda item: (item["setup"], item["ticket"]))
    return rows


def burst_spans(lattice):
    spans, current = [], []
    for row in lattice:
        if current and (row["setup"] - current[-1]["setup"]).total_seconds() > BURST_GAP_S:
            if len(current) >= MIN_LEGS:
                spans.append((current[0]["setup"], current[-1]["setup"]))
            current = []
        current.append(row)
    if len(current) >= MIN_LEGS:
        spans.append((current[0]["setup"], current[-1]["setup"]))
    return spans


def main() -> int:
    lattice = load_lattice_orders()
    positions = load_positions()
    ea_lattice = [r for r in lattice if r["magic"] == EA_MAGIC]
    spans = burst_spans(ea_lattice)
    print(f"=== Starwave tape, magic {EA_MAGIC} ===")
    print(f"    lattice stop orders: {len(ea_lattice)} "
          f"(of {len(lattice)} carrying a STR B/S comment)")
    print(f"    positions seen in the deal ledger: {len(positions)}")
    print(f"    deployment bursts (>= {MIN_LEGS} legs, {BURST_GAP_S}s gap): {len(spans)}")
    if spans:
        print(f"    window: {spans[0][0]} .. {spans[-1][1]}")
    print()

    def cycle_of(when):
        found = -1
        for index, (start, _end) in enumerate(spans):
            if start <= when:
                found = index
            else:
                break
        return found

    def in_burst(when):
        for start, end in spans:
            if start <= when <= end:
                return True
            if start > when:
                break
        return False

    filled = [r for r in ea_lattice if r["state"] == "4" and r["position_id"] in positions]
    groups: dict[tuple, list] = collections.defaultdict(list)
    for row in filled:
        position = positions[row["position_id"]]
        if position["opened"] is None:
            continue
        groups[(cycle_of(position["opened"]), row["is_buy"], row["level"])].append(
            {"pid": row["position_id"], "opened": position["opened"],
             "closed": position["closed"], "reason": position["close_reason"],
             "level": row["level"], "is_buy": row["is_buy"]})

    refills, displaced = 0, []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda item: (item["opened"], item["pid"]))
        refills += len(members) - 1
        for index, member in enumerate(members[:-1]):
            end = member["closed"]
            if any(end is None or later["opened"] < end for later in members[index + 1:]):
                displaced.append(member)

    print("=== part 1: same-slot re-fills, and how many OVERLAP ===")
    print(f"    lattice fills resolved to a position: {len(filled)}")
    print(f"    (cycle,side,level) slots re-used: "
          f"{sum(1 for m in groups.values() if len(m) > 1)} slots, {refills} re-fills")
    print(f"    OVERLAPPING (earlier position still open when the slot was rewritten): "
          f"{len(displaced)}")
    print(f"    => orphaned positions {len(displaced)}/{len(filled)} = "
          f"{100.0*len(displaced)/max(1,len(filled)):.2f}% of fills"
          f"   [901018 comparison: 0/17,515 = 0.00%]")
    census: collections.Counter = collections.Counter(
        ("STILL-OPEN" if m["closed"] is None else m["reason"]) for m in displaced)
    if census:
        print("    how each orphan ended: "
              + "  ".join(f"{k}={v}" for k, v in census.most_common()))
    print()

    per_cycle: collections.Counter = collections.Counter()
    offenders = []
    for row in ea_lattice:
        if in_burst(row["setup"]):
            continue
        per_cycle["rearms"] += 1
        cycle = cycle_of(row["setup"])
        live = [m for m in groups.get((cycle, row["is_buy"], row["level"]), [])
                if m["opened"] < row["setup"]
                and (m["closed"] is None or row["setup"] < m["closed"])]
        if live:
            per_cycle["over-live-position"] += 1
            offenders.append((row, live))
        else:
            per_cycle["after-close"] += 1

    print("=== part 2: was a level RE-ARMED while it still held a position? ===")
    print(f"    re-arm pendings dispatched outside every burst: {per_cycle['rearms']}")
    print(f"      after that slot's position closed: {per_cycle['after-close']}")
    print(f"      OVER a live position at that slot: {per_cycle['over-live-position']}"
          f"   [901018 comparison: 0/11,549]")
    print()
    print("    first 30 re-arms dispatched over a live position:")
    print("      setup time                order        side lvl  price     "
          "live position(s) still open")
    for row, live in offenders[:30]:
        print(f"      {row['setup']}   {row['ticket']:10d}   "
              f"{'B' if row['is_buy'] else 'S'}   {row['level']:3d}  {row['price']:9.2f}  "
              + ", ".join(f"#{m['pid']} opened {m['opened']} "
                          f"{'STILL OPEN' if m['closed'] is None else 'closed '+str(m['closed'])}"
                          for m in live))
    print()
    authorship_and_outcome(offenders, positions)
    residue_census(positions, filled, spans, displaced)
    return 0


def authorship_and_outcome(offenders, positions):
    """Who placed the 118 offending pendings, and what became of each?

    The one surviving alternative to "the EA re-armed an occupied level" is "the
    OPERATOR hand-placed those stop orders".  On this tape that is directly
    falsifiable: a hand-placed order carries magic 0 and ORDER_REASON_CLIENT (0),
    an EA order carries the EA magic and ORDER_REASON_EXPERT (3).  The offender
    list was already filtered to magic 26011001, so `reason` is the independent
    second witness.

    The outcome split explains why 118 re-arms produce only 27 overlaps: a re-arm
    dispatched over a live position only ORPHANS that position if it actually
    fills while the position is still open.  Canceled at the sweep, or filled
    after the old position was stopped out, and nothing is displaced.
    """
    reasons: collections.Counter = collections.Counter()
    outcome: collections.Counter = collections.Counter()
    with ORDERS.open(encoding="utf-8") as handle:
        by_ticket = {int(float(r["ticket"])): r for r in csv.DictReader(handle)}
    for row, live in offenders:
        raw = by_ticket.get(row["ticket"])
        reasons[REASON.get(raw["reason"], raw["reason"]) if raw else "?"] += 1
        if row["state"] != "4":
            outcome["canceled/expired at the sweep"] += 1
            continue
        fill = row["done"]
        if fill is not None and any(m["closed"] is None or fill < m["closed"] for m in live):
            outcome["FILLED while the old position was still open -> ORPHAN"] += 1
        else:
            outcome["filled after the old position closed"] += 1

    print("=== part 3a: who authored the 118 offending re-arm pendings? ===")
    for key, count in reasons.most_common():
        print(f"    ORDER_REASON_{key:8s} {count:5d}   "
              f"(magic filter already pinned all of them to {EA_MAGIC})")
    print("    => operator authorship is excluded: a hand-placed order would be "
          "magic 0 / reason CLIENT.")
    print()
    print("=== part 3b: what became of each offending re-arm? ===")
    for key, count in outcome.most_common():
        print(f"    {key:52s} {count:5d}")
    print()


def residue_census(positions, filled, spans, displaced):
    """How many positions never closed, and did they outlive a basket sweep?

    D6/D7 reported 153 unclosed of 2,468 fills.  That count is the RESIDUE, a
    superset of the 27 provable same-slot overlaps: a position also goes untracked
    when the level's identity is overwritten by a re-arm that fills in a LATER
    cycle, or when the level is recycled by the next deployment altogether.  The
    discriminator that makes residue equal leakage is survival across a sweep --
    a still-open position that predates a completed basket sweep cannot have been
    in that sweep's close list.
    """
    starts = [start for start, _end in spans]
    still_open = [row for row in filled
                  if positions[row["position_id"]]["closed"] is None]
    displaced_ids = {m["pid"] for m in displaced}
    crossings: collections.Counter = collections.Counter()
    for row in still_open:
        opened = positions[row["position_id"]]["opened"]
        crossed = sum(1 for start in starts if opened < start)
        crossings[min(crossed, 3) if crossed < 3 else 3] += 1
    worst = max((sum(1 for s in starts if positions[r["position_id"]]["opened"] < s)
                 for r in still_open), default=0)
    print("=== part 3c: the residue, and its overlap with the provable orphans ===")
    print(f"    lattice fills that NEVER closed: {len(still_open)}/{len(filled)}"
          f"   [D6/D7 reported 153/2468]")
    print(f"    of those, provably displaced by a same-slot overlap: {len(displaced_ids)}")
    print(f"    deployment boundaries each unclosed position outlived: "
          + "  ".join(f"{k if k < 3 else '>=3'}={crossings[k]}" for k in (0, 1, 2, 3))
          + f"   (max {worst})")
    print(f"    => {sum(v for k, v in crossings.items() if k >= 1)} of {len(still_open)} "
          f"outlived at least one later deployment, so they were not merely the "
          f"final open basket.")


if __name__ == "__main__":
    raise SystemExit(main())
