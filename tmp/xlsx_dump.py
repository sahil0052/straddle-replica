"""Dependency-free streaming xlsx -> CSV dumper for ReportHistory-901018.xlsx.

openpyxl/pandas are not installed in this venv and the sheet is 158 MB
uncompressed, so this streams xl/worksheets/sheet1.xml with iterparse and
resolves shared strings from a single pre-loaded table.  Sparse rows are padded
by column letter so column indices are stable across the report's sections.
"""
from __future__ import annotations

import csv
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def column_index(ref: str) -> int:
    """'BC12' -> 54 (0-based column)."""
    total = 0
    for char in ref:
        if char.isdigit():
            break
        total = total * 26 + (ord(char.upper()) - 64)
    return total - 1


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    out = []
    with archive.open("xl/sharedStrings.xml") as stream:
        for event, element in ET.iterparse(stream, events=("end",)):
            if element.tag == f"{NS}si":
                out.append("".join(node.text or "" for node in element.iter(f"{NS}t")))
                element.clear()
    return out


def rows(archive: zipfile.ZipFile, table: list[str]):
    with archive.open("xl/worksheets/sheet1.xml") as stream:
        for event, element in ET.iterparse(stream, events=("end",)):
            if element.tag != f"{NS}row":
                continue
            cells: dict[int, str] = {}
            for cell in element.iterfind(f"{NS}c"):
                ref = cell.get("r") or ""
                index = column_index(ref) if ref else len(cells)
                kind = cell.get("t")
                if kind == "inlineStr":
                    node = cell.find(f"{NS}is")
                    value = (
                        "".join(t.text or "" for t in node.iter(f"{NS}t"))
                        if node is not None
                        else ""
                    )
                else:
                    node = cell.find(f"{NS}v")
                    value = node.text if node is not None and node.text else ""
                    if kind == "s" and value != "":
                        value = table[int(value)]
                cells[index] = value
            if not cells:
                yield []
                element.clear()
                continue
            width = max(cells) + 1
            yield [cells.get(i, "") for i in range(width)]
            element.clear()


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "ReportHistory-901018.xlsx")
    destination = Path(sys.argv[2] if len(sys.argv) > 2 else "tmp/report_901018.csv")
    archive = zipfile.ZipFile(source)
    table = shared_strings(archive)
    print(f"shared strings: {len(table)}")
    count = 0
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in rows(archive, table):
            writer.writerow(row)
            count += 1
            if count % 5000 == 0:
                print(f"  {count} rows", flush=True)
    print(f"wrote {destination} rows={count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
