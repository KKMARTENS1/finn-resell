"""Automatisk rydding i Nye funn, så listene ikke blir fulle av gamle annonser.

Slettede annonser får status «slettet». De vises ikke noe sted, men prisene brukes fortsatt i
markedsprisene, og annonsen dukker ikke opp igjen som ny når scraperen ser den på Finn.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Tuple

from .db import get_settings, log_event


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
