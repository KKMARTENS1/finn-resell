"""Hvor appen lagrer dataene sine."""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def data_dir() -> Path:
    """Mappen med databasefilen. Standard er ~/Golflager, så dataene overlever nye versjoner av appen."""
    custom = os.environ.get("GOLFLAGER_DATA_DIR")
    path = Path(custom).expanduser() if custom else Path.home() / "Golflager"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "golflager.db"


def debug_dir() -> Path:
    path = data_dir() / "feilsøking"
    path.mkdir(parents=True, exist_ok=True)
    return path
