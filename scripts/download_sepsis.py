#!/usr/bin/env python3
"""Скачать Sepsis Cases event log в data/raw/ (тяжёлый .xes не коммитим)."""

from __future__ import annotations

import gzip
import hashlib
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
URL = "https://data.4tu.nl/file/33632f3c-5c48-40cf-8d8f-2db57f5a6ce7/643dccf2-985a-459e-835c-a82bce1c0339"
MD5 = "b5671166ac71eb20680d3c74616c43d2"
GZ = RAW / "Sepsis_Cases_Event_Log.xes.gz"
XES = RAW / "Sepsis_Cases_Event_Log.xes"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if not GZ.exists() or hashlib.md5(GZ.read_bytes()).hexdigest() != MD5:
        print(f"Качаю Sepsis log {URL} …")
        urllib.request.urlretrieve(URL, GZ)
    digest = hashlib.md5(GZ.read_bytes()).hexdigest()
    if digest != MD5:
        raise SystemExit(f"MD5 mismatch: {digest} != {MD5}")
    print(f"OK {GZ} md5={digest}")
    if not XES.exists():
        with gzip.open(GZ, "rb") as src, open(XES, "wb") as dst:
            shutil.copyfileobj(src, dst)
        print(f"Распаковано → {XES}")
    else:
        print(f"Уже есть {XES}")


if __name__ == "__main__":
    main()
