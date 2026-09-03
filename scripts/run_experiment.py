#!/usr/bin/env python3
"""
Единая точка входа OrgTwin.

  .venv/bin/python scripts/run_experiment.py --config configs/experiments/v0.7.0.json

Различие версий — в JSON, не в копиях run_v*.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgtwin import __version__
from orgtwin.experiment.run import run_from_config


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    p = argparse.ArgumentParser(description="OrgTwin: один скрипт, версия = JSON-конфиг")
    p.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Путь к configs/experiments/vX.Y.Z.json",
    )
    args = p.parse_args()
    cfg = args.config if args.config.is_absolute() else ROOT / args.config
    if not cfg.exists():
        raise SystemExit(f"Нет конфига: {cfg}")
    run_from_config(ROOT, cfg, package_version=__version__)


if __name__ == "__main__":
    main()
