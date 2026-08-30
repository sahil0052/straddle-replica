"""Independent check that each SECTION block in the standalone equals its include.

Parses the on-disk standalone by its '// SECTION: <label>' markers instead of
re-running the bundler, so a bug in bundle() cannot hide itself.  The only
permitted difference is a '#include "..."' line rendered as '// included inline'.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIR = ROOT / "mql5" / "include"
RULE = "// " + "=" * 68
INCLUDE_RE = re.compile(r'^#include\s+"[^"]+"\s*$')

LABEL_TO_FILE = {
    "StraddleTypes.mqh": "StraddleTypes.mqh",
    "ProfileCatalog.mqh": "ProfileCatalog.mqh",
    "StopScheduler.mqh": "StopScheduler.mqh",
    "BasketEvaluator.mqh": "BasketEvaluator.mqh",
    "CycleDealLedger.mqh": "CycleDealLedger.mqh",
    "TradeGateway.mqh": "TradeGateway.mqh",
    "StraddleEngine.mqh": "StraddleEngine.mqh",
    "StraddleReplicaApp.mqh (Event Handlers & Inputs)": "StraddleReplicaApp.mqh",
}


def sections(lines: list[str]) -> list[tuple[str, int, int]]:
    """(label, body_start, body_end_exclusive) for each marker block."""
    marks = [
        (i, line[len("// SECTION: "):])
        for i, line in enumerate(lines)
        if line.startswith("// SECTION: ")
    ]
    out = []
    for pos, (i, label) in enumerate(marks):
        assert lines[i - 1] == RULE and lines[i + 1] == RULE, f"bad rules at {i+1}"
        assert lines[i + 2] == "", f"missing blank after marker at {i+1}"
        start = i + 3
        if pos + 1 < len(marks):
            end = marks[pos + 1][0] - 3  # two blanks + opening rule
            assert lines[end] == "" and lines[end + 1] == "", (
                f"joiner before {marks[pos+1][1]} is not two blank lines"
            )
        else:
            end = len(lines)
            while end > start and lines[end - 1] == "":
                end -= 1
        out.append((label, start, end))
    return out


def main() -> int:
    target = ROOT / "mql5" / (sys.argv[1] if len(sys.argv) > 1 else "ProfitBricks2K.mq5")
    lines = target.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    bad = 0
    found = sections(lines)
    print(f"{target.name}: {len(lines)} lines, {len(found)} sections")
    for label, start, end in found:
        filename = LABEL_TO_FILE.get(label)
        if filename is None:
            print(f"  UNKNOWN SECTION LABEL {label!r}")
            bad = 1
            continue
        src = (INCLUDE_DIR / filename).read_text(encoding="utf-8")
        want = src.replace("\r\n", "\n").split("\n")
        if want and want[-1] == "":
            want.pop()
        want = ["// included inline" if INCLUDE_RE.match(x) else x for x in want]
        got = lines[start:end]
        status = "OK" if got == want else "MISMATCH"
        print(
            f"  {filename:24s} standalone {start+1:5d}-{end:5d} "
            f"({len(got):4d} lines) vs include ({len(want):4d}) {status}"
        )
        if got != want:
            bad = 1
            for n, (a, b) in enumerate(zip(got, want), start=start + 1):
                if a != b:
                    print(f"    first diff standalone line {n}")
                    print(f"      standalone: {a!r}")
                    print(f"      include   : {b!r}")
                    break
    print("ALL SECTIONS MATCH" if not bad else "SECTION MISMATCH")
    return bad


if __name__ == "__main__":
    sys.exit(main())
