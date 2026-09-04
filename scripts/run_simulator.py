#!/usr/bin/env python3
"""
Научный контур: softmax vs FEP, timing, batch-simulation.

  .venv/bin/python scripts/run_simulator.py --config configs/simulator/v0.7.0.json

Не является коммерческим deliverable без отдельного ТЗ.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgtwin import __version__
from orgtwin.contours import CONTOUR_SIMULATOR
from orgtwin.experiment.run import run_from_config


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    p = argparse.ArgumentParser(description="OrgTwin simulator contour (softmax_fep_ab)")
    p.add_argument("--config", type=Path, required=True, help="configs/simulator/vX.Y.Z.json")
    args = p.parse_args()
    cfg = args.config if args.config.is_absolute() else ROOT / args.config
    if not cfg.exists():
        raise SystemExit(f"Нет конфига: {cfg}")
    run_from_config(ROOT, cfg, package_version=__version__, expected_contour=CONTOUR_SIMULATOR)


if __name__ == "__main__":
    main()
