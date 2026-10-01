"""SQLite-databasen: tabeller, innstillinger og små hjelpefunksjoner."""
from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS searches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    url             TEXT NOT NULL,
    default_brand   TEXT NOT NULL DEFAULT '',
    default_type    TEXT NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    last_checked_at TEXT,
    last_count      INTEGER,
    last_new        INTEGER,
    last_note       TEXT NOT NULL DEFAULT '',
    last_full_check_at TEXT
);

CREATE TABLE IF NOT EXISTS inventory (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    brand          TEXT NOT NULL DEFAULT '',
    model          TEXT NOT NULL DEFAULT '',
    type           TEXT NOT NULL DEFAULT 'annet',
    condition      INTEGER NOT NULL DEFAULT 3,
    finn_url       TEXT NOT NULL DEFAULT '',
    purchase_price INTEGER,
    purchase_date  TEXT,
    cost_grip      INTEGER NOT NULL DEFAULT 0,
    cost_shipping  INTEGER NOT NULL DEFAULT 0,
    cost_cleaning  INTEGER NOT NULL DEFAULT 0,
    cost_other     INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'kjopt',
    listed_price   INTEGER,
    sale_price     INTEGER,
    sale_date      TEXT,
    notes          TEXT NOT NULL DEFAULT '',
    image_url      TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    finn_id       TEXT NOT NULL UNIQUE,
    search_id     INTEGER REFERENCES searches(id) ON DELETE SET NULL,
    title         TEXT NOT NULL,
    price         INTEGER,
    location      TEXT NOT NULL DEFAULT '',
    published_at  TEXT,
    url           TEXT NOT NULL,
    image_url     TEXT NOT NULL DEFAULT '',
    brand         TEXT NOT NULL DEFAULT '',
    model         TEXT NOT NULL DEFAULT '',
    type          TEXT NOT NULL DEFAULT 'annet',
    condition     INTEGER,
    status        TEXT NOT NULL DEFAULT 'ny',
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    inventory_id  INTEGER REFERENCES inventory(id) ON DELETE SET NULL,
    gone_at       TEXT,
    gone_reason   TEXT
);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status, first_seen_at);

CREATE TABLE IF NOT EXISTS price_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    price      INTEGER NOT NULL,
    seen_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history_listing ON price_history(listing_id);

CREATE TABLE IF NOT EXISTS scrape_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      TEXT NOT NULL,
    level   TEXT NOT NULL,
    message TEXT NOT NULL
);
"""

# Standardverdier. Typen til standardverdien bestemmer hvordan verdien leses tilbake.
DEFAULT_SETTINGS: Dict[str, Any] = {
    # Prisregel
    "min_profit_pct": 30.0,
    "min_profit_kr": 500,
    "rule_mode": "either",  # "either" = holder med én av dem, "both" = begge må oppfylles
    # Anslag i prissjekken
    "sale_factor_pct": 90.0,  # utlagt pris på Finn -> forventet salgspris
    "default_extra_cost": 150,
    # Hva en ting er verdt i prosent av samme ting i «God» stand (tilstand 3)
    "cond_value_5": 115,
    "cond_value_4": 105,
    "cond_value_2": 80,
    "cond_value_1": 60,
    "min_comparables": 3,
    "market_months": 12,
    # Budsjett
    "budget_kr": 20000,
    # Scraper
    "scrape_interval_min": 30,
    "page_delay_s": 5,
    "pages_per_search": 1,
    "scraper_enabled": 1,
    "sold_check_hours": 6,  # se etter solgte annonser (0 = av)
    "scraper_error": "",
    "scraper_notice": "",
    "scraper_last_run": "",
    "scraper_next_run": "",
    # Når brukeren sist så på "Nye funn"
    "last_seen_finds_at": "",
    # Rydding i Nye funn (0 = aldri)
    "auto_hide_days": 30,
    "auto_delete_days": 60,
    # Feilsøking: hvordan en annonse du merket som solgt, så ut i søket
    "diagnostic_text": "",
    # Oppdateringer fra GitHub
    "update_available": "",
    "update_checked_at": "",
}

LIMITS = {
    "scrape_interval_min": (15, 24 * 60),
    "page_delay_s": (3, 60),
    "pages_per_search": (1, 3),
    "min_profit_pct": (0, 500),
    "min_profit_kr": (0, 1_000_000),
    "sale_factor_pct": (30, 150),
    "default_extra_cost": (0, 100_000),
    "cond_value_5": (50, 200),
    "cond_value_4": (50, 200),
    "cond_value_2": (10, 150),
    "cond_value_1": (5, 150),
    "min_comparables": (1, 50),
    "market_months": (1, 120),
    "budget_kr": (0, 10_000_000),
    "auto_hide_days": (0, 3650),
    "sold_check_hours": (0, 168),
    "auto_delete_days": (0, 3650),
}


def now_str() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def today_str() -> str:
    return datetime.now().date().isoformat()


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate(conn)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (key, str(value))
            )
        conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES ('secret_key', ?)",
            (secrets.token_hex(24),),
        )
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Oppdaterer databaser laget av eldre versjoner av appen."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(listings)")}
    if "condition" not in columns:
        from .classify import detect_condition

        conn.execute("ALTER TABLE listings ADD COLUMN condition INTEGER")
        for row in conn.execute("SELECT id, title FROM listings").fetchall():
            condition = detect_condition(row["title"])
            if condition is not None:
                conn.execute("UPDATE listings SET condition = ? WHERE id = ?",
                             (condition, row["id"]))
    for column in ("gone_at", "gone_reason"):
        if column not in columns:
            conn.execute(f"ALTER TABLE listings ADD COLUMN {column} TEXT")
    search_columns = {row["name"] for row in conn.execute("PRAGMA table_info(searches)")}
    if "last_full_check_at" not in search_columns:
        conn.execute("ALTER TABLE searches ADD COLUMN last_full_check_at TEXT")


def _convert(raw: Optional[str], default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(default, float):
        try:
            return float(raw)
        except ValueError:
            return default
    if isinstance(default, int):
        try:
            return int(float(raw))
        except ValueError:
            return default
    return raw


def get_settings(conn: sqlite3.Connection) -> Dict[str, Any]:
    raw = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}
    return {key: _convert(raw.get(key), default) for key, default in DEFAULT_SETTINGS.items()}


def get_raw_setting(conn: sqlite3.Connection, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)", (key, str(value)))


def log_event(conn: sqlite3.Connection, level: str, message: str) -> None:
    conn.execute(
        "INSERT INTO scrape_log(at, level, message) VALUES (?, ?, ?)", (now_str(), level, message)
    )
    conn.execute(
        "DELETE FROM scrape_log WHERE id NOT IN (SELECT id FROM scrape_log ORDER BY id DESC LIMIT 200)"
    )
