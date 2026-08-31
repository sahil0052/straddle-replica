"""V13 -- standalone anti-drift: prove the bundle is a pure, lossless concatenation.

Reproduces tools/bundle_standalone.py's accounting independently of its own
--check/--write paths, so a bug in the bundler cannot hide behind itself:

  PART 1  line accounting: header + 8*framing + sum(include bodies) == standalone
  PART 2  byte-level: the two targets are the same bytes; hash matches --check
  PART 3  no unresolved local #include survives (i.e. it really is standalone)
  PART 4  the per-section offset law, checked against the V12.8 citations
  PART 5  every include body appears in the bundle verbatim, in bundle order
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import bundle_standalone as bs  # noqa: E402

TARGET = ROOT / "mql5" / "ProfitBricks2K.mq5"
ALLINONE = ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5"


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    lines = text.split("\n")
    srcs = bs.worktree_includes()

    print("=== PART 1 -- line accounting ===")
    header = bs.header_of(text)
    print(f"header_of() keeps        {len(header):>6} lines")
    first_rule = next(i for i, ln in enumerate(lines) if ln == bs.RULE)
    print(f"first RULE at file line  {first_rule + 1:>6}")
    framing = 0
    body_total = 0
    for name, _label in bs.SECTIONS:
        body = bs.body_lines(srcs[name])
        body_total += len(body)
        framing += 6  # blank, blank, RULE, label, RULE, blank
        print(f"  {name:<26} body {len(body):>5} lines")
    print(f"body subtotal            {body_total:>6}")
    print(f"framing (8 x 6)          {framing:>6}")
    predicted = len(header) + framing + body_total
    actual = len(lines)
    print(f"predicted total          {predicted:>6}")
    print(f"actual  total            {actual:>6}")
    print(f"LINE ACCOUNTING          {'EXACT' if predicted == actual else 'MISMATCH'}")

    print()
    print("=== PART 2 -- byte identity and hash ===")
    a, b = TARGET.read_bytes(), ALLINONE.read_bytes()
    print(f"ProfitBricks2K.mq5       {len(a):>7} bytes")
    print(f"ProfitBricks2K_AllInOne  {len(b):>7} bytes")
    print(f"same bytes               {a == b}")
    print(f"sha256[:16]              {bs.digest(text)}")
    print(f"full sha256              {hashlib.sha256(a).hexdigest()}")
    rebuilt = bs.build_from_worktree()
    print(f"rebuild == on-disk       {rebuilt == text}")

    print()
    print("=== PART 3 -- is it actually standalone? ===")
    local = [
        (i + 1, ln) for i, ln in enumerate(lines) if ln.strip().startswith('#include "')
    ]
    system = [
        (i + 1, ln) for i, ln in enumerate(lines) if ln.strip().startswith("#include <")
    ]
    print(f"unresolved local #include \"...\"  {len(local)}")
    for n, ln in local[:10]:
        print(f"   :{n} {ln.strip()}")
    print(f"system #include <...> (legal)     {len(system)}")
    for n, ln in system[:10]:
        print(f"   :{n} {ln.strip()}")
    ph = sum(1 for ln in lines if ln == bs.PLACEHOLDER)
    src_incl = sum(
        1
        for name, _ in bs.SECTIONS
        for ln in srcs[name].split("\n")
        if bs.INCLUDE_RE.match(ln)
    )
    print(f"'{bs.PLACEHOLDER}' count         {ph}")
    print(f"local #include lines in includes  {src_incl}")
    print(f"every include neutralised        {ph == src_incl}")

    print()
    print("=== PART 4 -- per-section offset law ===")
    labels = {}
    for i, ln in enumerate(lines):
        if ln.startswith("// SECTION: "):
            labels[ln[len("// SECTION: ") :]] = i + 1
    for name, label in bs.SECTIONS:
        at = labels[label]
        print(f"  {label:<48} label :{at:<5} body starts :{at + 3}  law: N -> {at + 2}+N")

    eng = labels["StraddleEngine.mqh"]
    app = labels["StraddleReplicaApp.mqh (Event Handlers & Inputs)"]
    cat = labels["ProfileCatalog.mqh"]
    checks = [
        ("StraddleEngine.mqh", 3169, eng, "m_runtime.symbol=_Symbol;"),
        ("StraddleEngine.mqh", 1521, eng, "ContractScale"),
        ("StraddleReplicaApp.mqh", 36, app, 'input string    TradeSymbol'),
        ("StraddleReplicaApp.mqh", 24, app, "cycle_target_money=26.5"),
        ("ProfileCatalog.mqh", 478, cat, "cycle_target_money=26.5"),
    ]
    print()
    for src, n, base, needle in checks:
        want = base + 2 + n
        src_line = srcs[src].split("\n")[n - 1]
        got = lines[want - 1]
        ok = src_line == got and needle in got
        print(f"  {src}:{n} -> :{want}  {'OK  ' if ok else 'FAIL'}  {got.strip()[:64]}")

    print()
    print("=== PART 5 -- bodies appear verbatim, in bundle order ===")
    cursor = 0
    for name, label in bs.SECTIONS:
        body = "\n".join(bs.body_lines(srcs[name]))
        idx = text.find(body, cursor)
        print(f"  {name:<26} verbatim {'YES' if idx >= 0 else 'NO '} at char {idx}")
        if idx < 0:
            return 1
        cursor = idx + len(body)
    print(f"bundle order preserved   True (monotone cursor, ends at {cursor} of {len(text)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
