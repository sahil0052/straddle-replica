"""Crude brace/paren/bracket balance checker for MQL5 sources.

Strips // and /* */ comments and string/char literals, then counts delimiters.
Reports the deepest unclosed opener line when a mismatch is found.
"""
import sys

BS = chr(92)


def strip(src: str) -> str:
    out = []
    keep_line = []
    i = 0
    n = len(src)
    line = 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                if src[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue
        if c == '"':
            i += 1
            while i < n and src[i] != '"':
                if src[i] == BS:
                    i += 1
                i += 1
            i += 1
            continue
        if c == "'":
            i += 1
            while i < n and src[i] != "'":
                if src[i] == BS:
                    i += 1
                i += 1
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def check(path: str) -> int:
    src = open(path, encoding="utf-8", errors="replace").read()
    clean = strip(src)
    print(f"{path}: {src.count(chr(10)) + 1} lines")
    bad = 0
    pairs = [("{", "}", "brace"), ("(", ")", "paren"), ("[", "]", "bracket")]
    for opener, closer, name in pairs:
        o = clean.count(opener)
        c = clean.count(closer)
        status = "OK" if o == c else "MISMATCH"
        if o != c:
            bad = 1
        print(f"  {name:8s} open={o} close={c} {status}")
    # locate first negative depth per pair
    for opener, closer, name in pairs:
        depth = 0
        line = 1
        for ch in clean:
            if ch == "\n":
                line += 1
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth < 0:
                    print(f"  {name}: extra '{closer}' at line {line}")
                    bad = 1
                    break
        if depth > 0:
            print(f"  {name}: {depth} unclosed '{opener}' at EOF")
            bad = 1
    return bad


if __name__ == "__main__":
    rc = 0
    for arg in sys.argv[1:]:
        rc |= check(arg)
    sys.exit(rc)
