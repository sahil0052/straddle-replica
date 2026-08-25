"""Structural sanity check on the edited StraddleEngine.mqh.

MetaEditor is the only real syntax authority, but a compile hot-reloads the EA on a
live account, so verify what can be verified statically first:
  - brace/paren balance for the whole file, against HEAD
  - the CheckCycleTargets body is well-formed and self-closing
  - no local declared and then left unused by the deletion
  - members referenced only by the deleted code are still used elsewhere
"""
from __future__ import annotations

import re
import subprocess

PATH = "mql5/include/StraddleEngine.mqh"

BLOCK = re.compile(r"/\*.*?\*/", re.S)
LINE = re.compile(r"//[^\n]*")
DQ = re.compile(r'"(?:\\.|[^"\\])*"')
SQ = re.compile(r"'(?:\\.|[^'\\])*'")


def strip(s: str) -> str:
    """Remove comments and string/char literals so brace counting is meaningful."""
    s = BLOCK.sub("", s)
    s = LINE.sub("", s)
    s = DQ.sub('""', s)
    s = SQ.sub("''", s)
    return s


def balance(label: str, s: str) -> None:
    c = strip(s)
    print(f"  {label:<9} braces {c.count('{'):>5} / {c.count('}'):>5}   "
          f"parens {c.count('('):>5} / {c.count(')'):>5}   "
          f"lines {len(s.splitlines()):>5}")


def extract(src: str, sig: str) -> str:
    m = re.search(re.escape(sig) + r"\s*\{", src)
    if not m:
        raise SystemExit(f"signature not found: {sig}")
    i = m.end() - 1
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    raise SystemExit(f"unbalanced body for {sig}")


def main() -> None:
    src = open(PATH, encoding="utf-8", errors="replace").read()
    head = subprocess.run(["git", "show", f"HEAD:{PATH}"],
                          capture_output=True, text=True, errors="replace").stdout

    print("WHOLE-FILE BALANCE (must match between HEAD and EDITED)")
    balance("HEAD", head)
    balance("EDITED", src)

    body = extract(src, "void CheckCycleTargets(void)")
    code = strip(body)
    live = [ln for ln in code.splitlines() if ln.strip()]
    print(f"\nCheckCycleTargets: {len(body.splitlines())} lines "
          f"({len(live)} code lines), braces {code.count('{')}/{code.count('}')}")

    print("\n  locals -- a count of 1 means declared but never used (MQL5 warning)")
    for v in ("scale", "target", "floating", "basket", "safety_reason"):
        n = len(re.findall(r"\b" + v + r"\b", code))
        flag = "  <-- UNUSED" if n <= 1 else ""
        print(f"    {v:<14} {n} occurrence(s){flag}")

    print("\n  exit paths remaining in the function")
    for mm in re.finditer(r"BeginClose\([^;]*\);", code):
        print("    " + " ".join(mm.group(0).split()))

    outside = strip(src.replace(body, ""))
    print("\n  members the deleted code used -- still referenced elsewhere?")
    for v in ("m_trend_rescue_side", "m_anchor", "trend_rescue_enabled"):
        n = len(re.findall(r"\b" + v + r"\b", outside))
        flag = "  <-- NOW DEAD" if n == 0 else ""
        print(f"    {v:<22} {n} reference(s) outside the function{flag}")

    print("\n  removed identifiers must not survive anywhere in the file")
    for v in ("grid_recenter", "rescue_breakeven", "recenter_bid", "dist_from_anchor",
              "cycle_net", "rescue_breakeven_reached"):
        n = len(re.findall(r"\b" + v + r"\b", strip(src)))
        flag = "  <-- STILL PRESENT IN CODE" if n else ""
        print(f"    {v:<26} {n}{flag}")


if __name__ == "__main__":
    main()
