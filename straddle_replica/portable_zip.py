from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


def create_portable_zip(source: Path, output: Path) -> None:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            archive.write(path, path.relative_to(source).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    create_portable_zip(args.source, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
