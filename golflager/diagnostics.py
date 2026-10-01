"""Feilsøking: hvordan så en annonse ut i søkeresultatene fra Finn?

Når du merker en annonse som solgt for hånd, lagrer vi hvordan den så ut på den siste
søkesiden. Teksten kan kopieres fra Innstillinger og sendes til den som lager appen, så
scraperen kan lære seg å kjenne igjen solgte annonser selv.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from bs4 import BeautifulSoup

from .finn_parser import ITEM_ID_RE, _walk, extract_embedded_data
from .scraper import last_pages_dir

MAX_CHARS = 6000


def _find_doc(objects: List[Any], finn_id: str) -> Optional[dict]:
    for obj in objects:
        for d in _walk(obj):
            for key in ("ad_id", "adId", "id", "finnkode"):
                if str(d.get(key, "")) == finn_id:
                    return d
            url = d.get("canonical_url") or d.get("url")
            if isinstance(url, str) and finn_id in ITEM_ID_RE.findall(url):
                return d
    return None


def _card_html(soup: BeautifulSoup, finn_id: str) -> str:
    for link in soup.find_all("a", href=True):
        if finn_id in ITEM_ID_RE.findall(link["href"]):
            card = link
            for _ in range(6):
                if card.parent is None or card.name in ("article", "li"):
                    break
                card = card.parent
            return str(card)
    return ""


def describe_listing(conn: sqlite3.Connection, listing: sqlite3.Row, version: str) -> str:
    """Lager en tekst som viser hvordan annonsen så ut i de siste søkesidene."""
    finn_id = str(listing["finn_id"])
    lines = [
        "Golflager feilsøking: annonse merket som solgt for hånd",
        f"Versjon: {version}",
        f"Finnkode: {finn_id}",
        f"Tittel: {listing['title']}",
        f"Pris: {listing['price']}",
        f"Funnet: {listing['first_seen_at']}  Sist sett i søk: {listing['last_seen_at']}",
    ]
    search = None
    if listing["search_id"]:
        search = conn.execute("SELECT * FROM searches WHERE id = ?",
                              (listing["search_id"],)).fetchone()
    if search is None:
        lines.append("Søk: finnes ikke lenger (slettet), så annonsen blir ikke sjekket.")
    else:
        lines.append(f"Søk: {search['name']} (aktiv: {'ja' if search['active'] else 'nei'})")
        lines.append(f"Lenke: {search['url']}")
        lines.append(f"Sjekket for solgte: {search['last_full_check_at'] or 'aldri'}")

    folder = last_pages_dir(conn)
    pages: List[Path] = []
    if search is not None and folder.exists():
        pages = sorted(folder.glob(f"søk-{search['id']}-side-*.html"))
    found = False
    for page in pages:
        try:
            html = page.read_text(encoding="utf-8")
        except OSError:
            continue
        soup = BeautifulSoup(html, "html.parser")
        doc = _find_doc(extract_embedded_data(soup), finn_id)
        card = _card_html(soup, finn_id)
        if doc is None and not card:
            continue
        found = True
        lines.append(f"\nAnnonsen var med på {page.name}.")
        if doc is not None:
            lines.append("--- Data fra søkesiden ---")
            lines.append(json.dumps(doc, ensure_ascii=False, indent=1, default=str)[:MAX_CHARS])
        if card:
            lines.append("--- HTML-kortet ---")
            lines.append(card[:MAX_CHARS])
        break
    if not found:
        lines.append(f"\nAnnonsen var ikke med i de siste søkesidene ({len(pages)} sider lagret). "
                     "Da forsvinner den ved neste sjekk for solgte annonser.")
    return "\n".join(lines)


def describe_check(form: dict, result: Any, listing: Optional[sqlite3.Row], version: str) -> str:
    """Prissjekken som tekst, så du kan sende den hvis et anslag ser helt feil ut."""
    lines = ["Golflager feilsøking: prissjekk", f"Versjon: {version}"]
    if listing is not None:
        lines += [f"Finnkode: {listing['finn_id']}", f"Tittel: {listing['title']}",
                  f"Rettet for hånd: {'ja' if listing['manual_class'] else 'nei'}"]
    lines += [
        f"Merke: {form.get('brand')}  Modell: {form.get('model')}  Type: {form.get('type')}",
        f"Tilstand: {form.get('condition') or 'ukjent'}  Pris: {form.get('price')}",
        f"Svar: {result.label} ({result.color}), sikkerhet: {result.confidence}",
        f"Forventet salg: {result.expected_sale}  Typisk pris: {result.typical_price}  "
        f"Fortjeneste: {result.profit}",
        f"Begrunnelse: {result.reason}",
        f"Grunnlag: {result.basis}",
    ]
    lines += [f"Merknad: {note}" for note in result.notes]
    if result.comparables:
        lines.append(f"--- Sammenlignet med ({len(result.comparables)}) ---")
        for c in result.comparables[:30]:
            lines.append(f"{c.price} kr | {c.date} | {c.label} | {c.url}")
    return "\n".join(lines)[:MAX_CHARS]
