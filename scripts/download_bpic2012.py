#!/usr/bin/env python3
"""Скачать BPI Challenge 2012 в data/raw/ (не коммитим тяжёлый .xes)."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
URL = "https://data.4tu.nl/file/533f66a4-8911-4ac7-8612-1235d65d1f37/3276db7f-8bee-4f2b-88ee-92dbffb5a893"
MD5 = "74c7ba9aba85bfcb181a22c9d565e5b5"
GZ = RAW / "BPI_Challenge_2012.xes.gz"
XES = RAW / "BPI_Challenge_2012.xes"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if not GZ.exists():
        print(f"Качаю {URL} …")
        urllib.request.urlretrieve(URL, GZ)
    digest = hashlib.md5(GZ.read_bytes()).hexdigest()
    if digest != MD5:
        raise SystemExit(f"MD5 mismatch: {digest} != {MD5}")
    print(f"OK {GZ} md5={digest}")
    if not XES.exists():
        import gzip
        import shutil

        with gzip.open(GZ, "rb") as src, open(XES, "wb") as dst:
            shutil.copyfileobj(src, dst)
        print(f"Распаковано → {XES}")
    else:
        print(f"Уже есть {XES}")


if __name__ == "__main__":
    main()
