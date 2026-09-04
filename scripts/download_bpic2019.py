#!/usr/bin/env python3
"""Скачать BPI Challenge 2019 в data/raw/ (не коммитим тяжёлый .xes)."""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
URL = "https://data.4tu.nl/file/35ed7122-966a-484e-a0e1-749b64e3366d/864493d1-3a58-47f6-ad6f-27f95f995828"
MD5 = "4eb909242351193a61e1c15b9c3cc814"
XES = RAW / "BPI_Challenge_2019.xes"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if XES.exists():
        digest = hashlib.md5(XES.read_bytes()).hexdigest()
        if digest == MD5:
            print(f"Уже есть {XES} md5={digest}")
            return
        print(f"MD5 не совпал ({digest}), качаю заново…")
        XES.unlink()
    print(f"Качаю BPIC2019 (~695 MiB) {URL} …")
    urllib.request.urlretrieve(URL, XES)
    digest = hashlib.md5(XES.read_bytes()).hexdigest()
    if digest != MD5:
        raise SystemExit(f"MD5 mismatch: {digest} != {MD5}")
    print(f"OK {XES} md5={digest}")


if __name__ == "__main__":
    main()
