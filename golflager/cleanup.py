"""Automatisk rydding i Nye funn, så listene ikke blir fulle av gamle annonser.

Slettede annonser får status «slettet». De vises ikke noe sted, men prisene brukes fortsatt i
markedsprisene, og annonsen dukker ikke opp igjen som ny når scraperen ser den på Finn.
"""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from .db import get_settings, log_event, now_str, set_setting


def _cutoff(now: datetime, days: int) -> str:
    return (now - timedelta(days=days)).replace(microsecond=0).isoformat(sep=" ")


def cleanup_listings(conn: sqlite3.Connection, now: Optional[datetime] = None) -> Tuple[int, int]:
    """Skjuler gamle nye funn og sletter gamle skjulte. Returnerer (skjult, slettet)."""
    settings = get_settings(conn)
    now = now or datetime.now()
    hidden = deleted = 0
    if settings["auto_hide_days"] > 0:
        hidden = conn.execute(
            "UPDATE listings SET status = 'skjult' WHERE status = 'ny' AND first_seen_at < ?",
            (_cutoff(now, settings["auto_hide_days"]),),
        ).rowcount
    if settings["auto_delete_days"] > 0:
        deleted = conn.execute(
            "UPDATE listings SET status = 'slettet' WHERE status = 'skjult' AND first_seen_at < ?",
            (_cutoff(now, settings["auto_delete_days"]),),
        ).rowcount
    if hidden or deleted:
        parts = []
        if hidden:
            parts.append(f"skjulte {hidden} nye funn eldre enn {settings['auto_hide_days']} dager")
        if deleted:
            parts.append(f"slettet {deleted} skjulte annonser eldre enn "
                         f"{settings['auto_delete_days']} dager")
        log_event(conn, "info", "Automatisk rydding: " + " og ".join(parts) + ".")
    conn.commit()
    return hidden, deleted


def start_over(conn: sqlite3.Connection, keep_searches: bool = True,
               only_new: bool = True) -> Path:
    """Sletter alle annonser fra Finn, men beholder lageret, salgene og innstillingene.

    Tar en sikkerhetskopi av hele databasen først og returnerer hvor den ligger.
    `only_new`: annonser som allerede ligger ute på Finn, vises ikke som nye funn igjen
    (de lagres som skjulte og brukes bare i markedsprisene).
    """
    db_file = Path(conn.execute("PRAGMA database_list").fetchone()["file"])
    folder = db_file.parent / "sikkerhetskopier"
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / f"før-start-på-nytt-{datetime.now():%Y-%m-%d-%H%M%S}.db"
    target = sqlite3.connect(str(backup))
    try:
        conn.backup(target)
    finally:
        target.close()

    now = now_str()
    conn.execute("UPDATE listings SET inventory_id = NULL")
    conn.execute("DELETE FROM price_history")
    conn.execute("DELETE FROM listings")
    conn.execute("DELETE FROM scrape_log")
    if keep_searches:
        conn.execute(
            "UPDATE searches SET last_checked_at = NULL, last_count = NULL, last_new = NULL, "
            "last_note = '', last_full_check_at = NULL, hide_before = ?",
            (now if only_new else None,),
        )
    else:
        conn.execute("DELETE FROM searches")
    set_setting(conn, "diagnostic_text", "")
    set_setting(conn, "scraper_notice", "")
    set_setting(conn, "last_seen_finds_at", now)
    log_event(conn, "info", f"Start på nytt: alle annonser ble slettet. Sikkerhetskopi: {backup}")
    conn.commit()
    shutil.rmtree(db_file.parent / "feilsøking" / "siste-søk", ignore_errors=True)
    return backup
