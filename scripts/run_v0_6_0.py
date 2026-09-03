#!/usr/bin/env python3
"""Обёртка совместимости → scripts/run_experiment.py + configs/experiments/v0.6.0.json"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
raise SystemExit(subprocess.call(
    [sys.executable, str(ROOT / "scripts" / "run_experiment.py"),
     "--config", str(ROOT / "configs" / "experiments" / "v0.6.0.json")],
))
