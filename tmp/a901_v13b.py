"""V13 -- prove the standalone contains every include VERBATIM, and derive the
per-section offset law from the file itself rather than from arithmetic.

PART 1  section-by-section line-for-line comparison of the standalone's body
        slices against mql5/include/*.mqh.  Any line that differs is printed in
        full, so the only tolerated differences (the bundler's
        `// included inline` placeholders standing in for local #include lines)
        are visible rather than assumed.
PART 2  the derived offset law applied to every construct this audit cites, with
        the standalone text printed next to the include text at each site.
"""

from pathlib import Path

ROOT = Path(".")
SA = ROOT / "mql5" / "ProfitBricks2K.mq5"
SA2 = ROOT / "mql5" / "ProfitBricks2K_AllInOne.mq5"
INC = ROOT / "mql5" / "include"

ORDER = [
    "StraddleTypes.mqh",
    "ProfileCatalog.mqh",
    "StopScheduler.mqh",
    "BasketEvaluator.mqh",
    "CycleDealLedger.mqh",
    "TradeGateway.mqh",
    "StraddleEngine.mqh",
    "StraddleReplicaApp.mqh",
]


def lines_of(path):
    text = path.read_text(encoding="utf-8")
    out = text.split("\n")
    if out and out[-1] == "":
        out.pop()  # the phantom element a trailing newline produces
    return out


sa = lines_of(SA)
print(f"standalone {SA.name}: {len(sa)} lines")
print(f"identical to {SA2.name}: {lines_of(SA2) == sa}")

labels = {}
for i, line in enumerate(sa, 1):
    if line.startswith("// SECTION:"):
        labels[line.split("// SECTION:", 1)[1].strip().split()[0]] = i
print(f"labels found: {len(labels)}")

print("\n=== PART 1  verbatim body comparison ===")
print(f"{'section':26s} {'lines':>5s}  {'body span':>13s}  {'law':>10s}  diffs")
total_body = 0
offsets = {}
prev_end = 20  # header ends here if the framing is 6 lines per section
for name in ORDER:
    inc = lines_of(INC / name)
    start = labels[name] + 3
    end = start + len(inc) - 1
    got = sa[start - 1 : end]
    diffs = [(start + j, a, b) for j, (a, b) in enumerate(zip(got, inc)) if a != b]
    offsets[name] = start - 1
    print(
        f"{name:26s} {len(inc):5d}  {start:6d}..{end:<6d}  +{start-1:<9d}  {len(diffs)}"
    )
    for ln, a, b in diffs:
        print(f"      :{ln:5d} standalone: {a.strip()!r}")
        print(f"             include   : {b.strip()!r}")
    lead = labels[name] - prev_end  # framing lines before this label
    print(f"      framing before label: {lead}   (label at :{labels[name]})")
    prev_end = end
    total_body += len(inc)

print(f"\nbodies {total_body}   header+framing {len(sa) - total_body}"
      f"   last body ends :{prev_end}  file ends :{len(sa)}")
print(f"identity: 20 + {len(sa) - total_body - 20} + {total_body} = {len(sa)}"
      f"   -> {20 + (len(sa) - total_body - 20) + total_body == len(sa)}")

print("\n=== PART 2  cited constructs through the derived law ===")
CITES = [
    ("StraddleTypes.mqh", 156),
    ("ProfileCatalog.mqh", 17),
    ("ProfileCatalog.mqh", 30),
    ("ProfileCatalog.mqh", 478),
    ("ProfileCatalog.mqh", 730),
    ("StopScheduler.mqh", 126),
    ("StopScheduler.mqh", 162),
    ("CycleDealLedger.mqh", 17),
    ("StraddleEngine.mqh", 1244),
    ("StraddleEngine.mqh", 3169),
    ("StraddleEngine.mqh", 3446),
    ("StraddleEngine.mqh", 3448),
    ("StraddleEngine.mqh", 3826),
    ("StraddleReplicaApp.mqh", 24),
    ("StraddleReplicaApp.mqh", 100),
    ("StraddleReplicaApp.mqh", 126),
    ("StraddleReplicaApp.mqh", 165),
]
cache = {n: lines_of(INC / n) for n in ORDER}
bad = 0
for name, n in CITES:
    pred = offsets[name] + n
    a = sa[pred - 1]
    b = cache[name][n - 1]
    ok = a == b
    bad += 0 if ok else 1
    print(f"{name.replace('.mqh',''):22s}:{n:<5d} -> :{pred:<5d} {'OK ' if ok else 'BAD'} {b.strip()[:88]!r}")
print(f"\nmismatched citations: {bad}")
