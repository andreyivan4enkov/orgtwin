#!/usr/bin/env python3
"""
Устаревший общий entrypoint. Используйте:

  scripts/run_diagnostic.py  — коммерческий контур
  scripts/run_simulator.py   — научный контур

См. docs/CONTOURS.md
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from orgtwin import __version__
from orgtwin.contours import infer_contour
from orgtwin.experiment.run import run_from_config


def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    warnings.warn(
        "run_experiment.py устарел: используйте run_diagnostic.py или run_simulator.py (docs/CONTOURS.md)",
        DeprecationWarning,
        stacklevel=1,
    )
    p = argparse.ArgumentParser(description="OrgTwin (legacy): см. run_diagnostic / run_simulator")
    p.add_argument("--config", type=Path, required=True)
    args = p.parse_args()
    cfg = args.config if args.config.is_absolute() else ROOT / args.config
    if not cfg.exists():
        raise SystemExit(f"Нет конфига: {cfg}")
    recipe = cfg.read_text(encoding="utf-8")
    import json

    contour = infer_contour(json.loads(recipe))
    print(f"Legacy run; inferred contour={contour}")
    run_from_config(ROOT, cfg, package_version=__version__)


if __name__ == "__main__":
    main()
