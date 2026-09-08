from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    configured = os.getenv("DESP_APP_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "DESP Studio"


def output_dir() -> Path:
    path = app_data_dir() / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_dir() -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir) / "desp_desktop_app"
    return Path(__file__).resolve().parents[1]
