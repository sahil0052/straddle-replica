"""Deterministic generator for the two ProfitBricks2K standalone builds.

mql5/ProfitBricks2K.mq5 and mql5/ProfitBricks2K_AllInOne.mq5 are byte-identical
mechanical concatenations of the eight modular includes.  They used to be
maintained by hand, which drifted: before this generator existed the standalone
copies were 33 lines behind mql5/include (12 in StraddleTypes.mqh, 21 in
ProfileCatalog.mqh), so both shipped WITHOUT the replica_orphan_leak field and
without the eight profile assignments that turn the Target EA's orphan leak on.
They compiled cleanly and were silently a different EA.

The transform, reverse-engineered from the last hand-mirrored file and byte-exact
against git HEAD (see --verify):

    <header block, verbatim from the existing standalone -- the only per-binary
     part, carrying the #property block and this binary's STR_DEFAULT_* pins>
    for each section:
        "", ""                                 two blank lines
        "// " + "=" * 68
        "// SECTION: " + label
        "// " + "=" * 68
        ""                                     one blank line
        <include body, verbatim, with every '#include "..."' line replaced by
         '// included inline' so line numbers still line up with the include>

Usage:
    python tools/bundle_standalone.py --verify   # HEAD includes -> HEAD standalone
    python tools/bundle_standalone.py --check    # worktree includes -> on-disk files
    python tools/bundle_standalone.py --write    # worktree includes -> both files
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE_DIR = ROOT / "mql5" / "include"
TARGETS = [
    ROOT / "mql5" / "ProfitBricks2K.mq5",
    ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5",
]

# (include filename, section label) in bundle order.
SECTIONS = [
    ("StraddleTypes.mqh", "StraddleTypes.mqh"),
    ("ProfileCatalog.mqh", "ProfileCatalog.mqh"),
    ("StopScheduler.mqh", "StopScheduler.mqh"),
    ("BasketEvaluator.mqh", "BasketEvaluator.mqh"),
    ("CycleDealLedger.mqh", "CycleDealLedger.mqh"),
    ("TradeGateway.mqh", "TradeGateway.mqh"),
    ("StraddleEngine.mqh", "StraddleEngine.mqh"),
    ("StraddleReplicaApp.mqh", "StraddleReplicaApp.mqh (Event Handlers & Inputs)"),
]

RULE = "// " + "=" * 68
INCLUDE_RE = re.compile(r'^#include\s+"[^"]+"\s*$')
FIRST_MARKER = "// SECTION: StraddleTypes.mqh"
PLACEHOLDER = "// included inline"


def body_lines(text: str) -> list[str]:
    """Include body with #include directives neutralised, trailing blank trimmed."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [PLACEHOLDER if INCLUDE_RE.match(line) else line for line in lines]


def header_of(standalone_text: str) -> list[str]:
    """The per-binary header: everything before the first section's rule line.

    bundle() emits two blank lines before every rule, and the files carry three
    between the header's last directive and the first rule, so the slice keeps
    exactly one of them.
    """
    lines = standalone_text.replace("\r\n", "\n").split("\n")
    marker = lines.index(FIRST_MARKER)
    # marker-1 is the opening rule; marker-2 and marker-3 are the blank joiner.
    return lines[: marker - 3]


def bundle(header: list[str], sources: dict[str, str]) -> str:
    out = list(header)
    for filename, label in SECTIONS:
        out.append("")
        out.append("")
        out.append(RULE)
        out.append(f"// SECTION: {label}")
        out.append(RULE)
        out.append("")
        out.extend(body_lines(sources[filename]))
    return "\n".join(out) + "\n"


def worktree_includes() -> dict[str, str]:
    return {
        name: (INCLUDE_DIR / name).read_text(encoding="utf-8") for name, _ in SECTIONS
    }


def build_from_worktree() -> str:
    """The standalone text the current mql5/include tree implies."""
    return bundle(header_of(TARGETS[0].read_text(encoding="utf-8")), worktree_includes())


def first_divergence(want: str, got: str) -> str:
    for number, (a, b) in enumerate(zip(want.split("\n"), got.split("\n")), start=1):
        if a != b:
            return f"  line {number}\n    expected: {a!r}\n    actual  : {b!r}"
    return (
        f"  length only: expected {len(want.split(chr(10)))} lines, "
        f"actual {len(got.split(chr(10)))} lines"
    )


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def verify() -> int:
    """Round-trip git HEAD: HEAD's includes must rebuild HEAD's standalone."""

    def show(rev_path: str) -> str:
        out = subprocess.run(
            ["git", "show", rev_path], cwd=ROOT, capture_output=True, check=True
        )
        return out.stdout.decode("utf-8")

    head = show("HEAD:mql5/ProfitBricks2K.mq5")
    sources = {name: show(f"HEAD:mql5/include/{name}") for name, _ in SECTIONS}
    built = bundle(header_of(head), sources)
    print(f"HEAD standalone : {len(head):>7} chars  {digest(head)}")
    print(f"rebuilt         : {len(built):>7} chars  {digest(built)}")
    if head == built:
        print("VERIFY OK - bundler reproduces HEAD byte-for-byte")
        return 0
    print("VERIFY FAILED - first divergence:")
    print(first_divergence(head, built))
    return 1


def check() -> int:
    """The on-disk standalones must equal what the worktree includes imply."""
    built = build_from_worktree()
    bad = 0
    for target in TARGETS:
        actual = target.read_text(encoding="utf-8")
        ok = actual == built
        bad |= 0 if ok else 1
        print(
            f"{'OK      ' if ok else 'DRIFTED '}{target.relative_to(ROOT)}  "
            f"{len(actual)} chars  {digest(actual)}"
        )
        if not ok:
            print(first_divergence(built, actual))
    if not bad:
        print("CHECK OK - both standalones match mql5/include")
    return bad


def write() -> int:
    data = build_from_worktree().encode("utf-8")
    for target in TARGETS:
        target.write_bytes(data)
        print(
            f"wrote {target.relative_to(ROOT)}  {len(data)} bytes  "
            f"{data.decode('utf-8').count(chr(10))} lines  "
            f"{hashlib.sha256(data).hexdigest()[:16]}"
        )
    return 0


MODES = {"--verify": verify, "--check": check, "--write": write}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    if mode not in MODES:
        print(f"usage: {Path(__file__).name} [{' | '.join(MODES)}]")
        sys.exit(2)
    sys.exit(MODES[mode]())
