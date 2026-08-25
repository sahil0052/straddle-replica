from __future__ import annotations

import argparse
import glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc


def load_unique(root: Path, prefix: str) -> list[dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    pattern = str(root / "*" / f"{prefix}-*.jsonl")
    for name in sorted(glob.glob(pattern)):
        with Path(name).open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                ticket = int(row.get("ticket") or 0)
                if not ticket:
                    continue
                current = rows.get(ticket)
                if current is None or str(
                    row.get("capture_time_utc") or ""
                ) < str(current.get("capture_time_utc") or ""):
                    rows[ticket] = row
    return list(rows.values())


def group_by_gap(
    rows: list[dict[str, Any]],
    field: str,
    maximum_gap_ms: int,
) -> list[list[dict[str, Any]]]:
    ordered = sorted(rows, key=lambda row: int(row.get(field) or 0))
    groups: list[list[dict[str, Any]]] = []
    for row in ordered:
        if (
            not groups
            or int(row[field]) - int(groups[-1][-1][field])
            > maximum_gap_ms
        ):
            groups.append([])
        groups[-1].append(row)
    return groups


def utc_text(server_time_msc: int, server_offset_ms: int) -> str:
    return datetime.fromtimestamp(
        (server_time_msc - server_offset_ms) / 1000,
        tz=UTC,
    ).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-root", required=True, type=Path)
    parser.add_argument("--server-offset-ms", type=int, default=0)
    args = parser.parse_args()

    orders = load_unique(args.python_root, "history-orders")
    deals = load_unique(args.python_root, "history-deals")

    canceled = [
        row
        for row in orders
        if int(row.get("state") or -1) == 2
        and str(row.get("comment") or "").startswith("STR ")
    ]
    cancellations = []
    for group in group_by_gap(canceled, "time_done_msc", 1_000):
        if len(group) < 10:
            continue
        comments = [str(row["comment"]) for row in group]
        remaining = comments.copy()
        expected = []
        for level in range(30, 0, -1):
            for side in ("S", "B"):
                comment = f"STR {side}{level}"
                while comment in remaining:
                    expected.append(comment)
                    remaining.remove(comment)
        cancellations.append(
            {
                "start_utc": utc_text(
                    int(group[0]["time_done_msc"]),
                    args.server_offset_ms,
                ),
                "count": len(group),
                "reverse_deployment_order_exact": comments == expected,
                "ticket_descending_exact": [
                    int(row["ticket"]) for row in group
                ]
                == sorted(
                    (int(row["ticket"]) for row in group),
                    reverse=True,
                ),
                "tickets": [int(row["ticket"]) for row in group],
                "comments": comments,
            }
        )

    entry_comment: dict[int, str] = {}
    for row in sorted(deals, key=lambda value: int(value.get("time_msc") or 0)):
        comment = str(row.get("comment") or "")
        if (
            int(row.get("entry", -1)) in {0, 2}
            and comment.startswith("STR ")
        ):
            entry_comment.setdefault(
                int(row.get("position_id") or 0),
                comment,
            )

    close_deals = [
        row
        for row in deals
        if int(row.get("entry", -1)) in {1, 3}
        and row.get("comment") == "STR CLOSE"
    ]
    residual_closes = []
    for group in group_by_gap(close_deals, "time_msc", 25_000):
        position_ids = [
            int(row.get("position_id") or 0) for row in group
        ]
        residual_closes.append(
            {
                "start_utc": utc_text(
                    int(group[0]["time_msc"]),
                    args.server_offset_ms,
                ),
                "count": len(group),
                "gaps_ms": [
                    int(right["time_msc"]) - int(left["time_msc"])
                    for left, right in zip(group, group[1:])
                ],
                "position_ids": position_ids,
                "position_id_ascending_exact": position_ids
                == sorted(position_ids),
                "position_id_descending_exact": position_ids
                == sorted(position_ids, reverse=True),
                "comments": [
                    entry_comment.get(
                        int(row.get("position_id") or 0),
                        "UNKNOWN",
                    )
                    for row in group
                ],
            }
        )

    print(
        json.dumps(
            {
                "cancellations": cancellations,
                "residual_closes": residual_closes,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
