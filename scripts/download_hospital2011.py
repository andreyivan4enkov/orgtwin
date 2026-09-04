#!/usr/bin/env python3
"""Скачать Hospital log (BPIC 2011) в data/raw/ (тяжёлый .xes не коммитим)."""

from __future__ import annotations

import gzip
import hashlib
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
URL = "https://data.4tu.nl/file/5ea5bb88-feaa-4e6f-a743-6460a755e05b/6f9640f9-0f1e-44d2-9495-ef9d1bd82218"
MD5 = "482adef27906fb3f0b66989798edd987"
GZ = RAW / "Hospital_log.xes.gz"
XES = RAW / "Hospital_log.xes"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    if not GZ.exists() or hashlib.md5(GZ.read_bytes()).hexdigest() != MD5:
        print(f"Качаю Hospital BPIC2011 {URL} …")
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
