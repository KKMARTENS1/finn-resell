"""Scraperen: sjekker Finn-søkene dine jevnlig og lagrer nye annonser.

Regler den følger:
- Den logger aldri inn på noen Finn-konto, og sender ingen informasjonskapsler.
- Den henter bare søkeresultatsidene, aldri enkeltannonser.
- Den sjekker sjelden (standard hvert 30. minutt) og venter noen sekunder mellom hver side.
- Hvis den blir blokkert eller får en feilmelding, stopper den og sier fra i appen.
  Den prøver aldri å komme rundt en blokkering.
"""
from __future__ import annotations

import logging
import os
import random
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from .classify import classify, detect_condition, is_wanted_ad
from .db import connect, get_settings, log_event, now_str, set_setting
from .finn_parser import ITEM_ID_RE, ParsedAd, looks_blocked, parse_search_page

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 Golflager/1.0 (privat bruk)"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "nb-NO,nb;q=0.9,no;q=0.8,en;q=0.5",
}
MANUAL_MIN_GAP = timedelta(minutes=2)
MAX_NETWORK_FAILURES = 3


class FinnError(Exception):
    """Finn blokkerte oss eller svarte med feil. Scraperen skal stoppe."""


class NetworkError(Exception):
    """Fikk ikke kontakt med Finn (f.eks. ingen internett). Prøver igjen senere."""


# ---------------------------------------------------------------------------
# Søkelenker


def normalize_search_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ValueError("Lim inn en lenke til et søk på Finn.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url.lstrip("/")
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in ("finn.no", "www.finn.no", "m.finn.no"):
        raise ValueError("Lenken må gå til finn.no.")
    path = parts.path or "/"
    if "search" not in path.lower():
        if ITEM_ID_RE.search(url):
            raise ValueError(
                "Dette ser ut som en enkeltannonse. Lim inn lenken til selve søket "
                "(siden med listen over treff)."
            )
        raise ValueError(
            "Dette ser ikke ut som et søk. Gjør søket på Finn, og kopier lenken fra adressefeltet."
        )
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "page"]
    if path.startswith("/recommerce/") and not any(k == "sort" for k, _ in query):
        query.append(("sort", "PUBLISHED_DESC"))  # nyeste først, så vi ser nye annonser
    return urlunsplit(("https", "www.finn.no", path, urlencode(query), ""))


def page_url(url: str, page: int) -> str:
    if page <= 1:
        return url
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "page"] + [("page", str(page))]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def suggest_name(url: str) -> str:
    params = dict(parse_qsl(urlsplit(url).query))
    name = params.get("q", "").strip() or "Finn-søk"
    name = name[:1].upper() + name[1:]
    if params.get("price_to", "").isdigit():
        amount = f"{int(params['price_to']):,}".replace(",", " ")
        name += f" (maks {amount} kr)"
    return name


# ---------------------------------------------------------------------------
# Henting


def fetch_page(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
    except requests.exceptions.RequestException as exc:
        raise NetworkError(f"Fikk ikke kontakt med Finn ({exc.__class__.__name__}).") from exc
    final = urlsplit(response.url)
    host = (final.hostname or "").lower()
    target = (final.path + "?" + final.query).lower()
    if (not host.endswith("finn.no") or host.startswith("login.")
            or any(word in target for word in ("login", "logg-inn", "innlogging", "/auth"))):
        raise FinnError(
            "Finn sendte scraperen videre til en innloggingsside eller en annen nettside. "
            "Scraperen logger aldri inn, så den har stoppet."
        )
    status = response.status_code
    if status in (401, 403):
        raise FinnError(
            f"Finn nektet tilgang (feilkode {status}). Det betyr som regel at Finn blokkerer "
            "automatiske besøk. Scraperen har stoppet og prøver ikke å komme rundt dette."
        )
    if status == 429:
        raise FinnError(
            "Finn sier at det kommer for mange besøk (feilkode 429). Scraperen har stoppet. "
            "Vent noen timer, og sett gjerne opp tiden mellom sjekkene før du slår den på igjen."
        )
    if status >= 400:
        raise FinnError(f"Finn svarte med feilkode {status}. Scraperen har stoppet.")
    if not response.encoding:
        response.encoding = "utf-8"
    return response.text


# ---------------------------------------------------------------------------
# Lagring


def store_ads(conn: sqlite3.Connection, search: sqlite3.Row, ads: Iterable[ParsedAd],
              now: Optional[str] = None) -> Tuple[int, int]:
    """Lagrer annonsene. Returnerer (antall nye, antall vi har sett før)."""
    now = now or now_str()
    new = known = 0
    for ad in ads:
        if is_wanted_ad(ad.title) or "ønskes" in ad.trade_type.lower():
            continue
        published = ad.published_at.isoformat(sep=" ") if ad.published_at else None
        row = conn.execute(
            "SELECT id, price FROM listings WHERE finn_id = ?", (ad.finn_id,)
        ).fetchone()
        if row is None:
            brand, model, type_key = classify(
                ad.title, search["default_brand"] or "", search["default_type"] or ""
            )
            cursor = conn.execute(
                """INSERT INTO listings (finn_id, search_id, title, price, location, published_at,
                       url, image_url, brand, model, type, condition, status, first_seen_at,
                       last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ny', ?, ?)""",
                (ad.finn_id, search["id"], ad.title, ad.price, ad.location, published, ad.url,
                 ad.image_url, brand, model, type_key, detect_condition(ad.title), now, now),
            )
            if ad.price is not None:
                conn.execute(
                    "INSERT INTO price_history (listing_id, price, seen_at) VALUES (?, ?, ?)",
                    (cursor.lastrowid, ad.price, now),
                )
            new += 1
            continue
        known += 1
        conn.execute(
            """UPDATE listings SET last_seen_at = ?, title = ?,
                   location = CASE WHEN ? != '' THEN ? ELSE location END,
                   image_url = CASE WHEN ? != '' THEN ? ELSE image_url END,
                   published_at = COALESCE(published_at, ?)
               WHERE id = ?""",
            (now, ad.title, ad.location, ad.location, ad.image_url, ad.image_url, published,
             row["id"]),
        )
        if ad.price is not None and ad.price != row["price"]:
            conn.execute("UPDATE listings SET price = ? WHERE id = ?", (ad.price, row["id"]))
            conn.execute(
                "INSERT INTO price_history (listing_id, price, seen_at) VALUES (?, ?, ?)",
                (row["id"], ad.price, now),
            )
    return new, known


def _save_debug_copy(conn: sqlite3.Connection, html: str, label: str) -> str:
    """Lagrer siden Finn sendte, så det er lett å finne ut hva som skjedde."""
    try:
        db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
        folder = Path(db_file).parent / "feilsøking" if db_file else Path.cwd() / "feilsøking"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"finn-{label}-{datetime.now():%Y%m%d-%H%M%S}.html"
        path.write_text(html, encoding="utf-8")
        for old in sorted(folder.glob("finn-*.html"))[:-5]:
            old.unlink()
        return str(path)
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Én runde med sjekker


def run_checks(
    conn: sqlite3.Connection,
    search_ids: Optional[Set[int]] = None,
    fetch: Callable[[str], str] = fetch_page,
    sleep: Callable[[float], None] = time.sleep,
    should_continue: Callable[[], bool] = lambda: True,
) -> Dict[str, int]:
    settings = get_settings(conn)
    searches: List[sqlite3.Row] = conn.execute(
        "SELECT * FROM searches WHERE active = 1 ORDER BY id"
    ).fetchall()
    if search_ids:
        searches = [s for s in searches if s["id"] in search_ids]
    pages = max(1, min(3, int(settings["pages_per_search"])))
    delay = max(3, int(settings["page_delay_s"]))
    total_new = checked = 0
    first_request = True
    for search in searches:
        found = new_here = 0
        for page in range(1, pages + 1):
            if not should_continue():
                return {"checked": checked, "new": total_new}
            if not first_request:
                sleep(delay + random.uniform(0, 4))
            first_request = False
            url = page_url(search["url"], page)
            html = fetch(url)
            result = parse_search_page(html, url)
            if not result.ads:
                if looks_blocked(html):
                    copy = _save_debug_copy(conn, html, "blokkert")
                    raise FinnError(
                        "Finn viser en robot-sjekk (captcha) i stedet for søkeresultater. "
                        "Scraperen har stoppet og prøver ikke å komme rundt dette."
                        + (f" En kopi av siden er lagret i {copy}." if copy else "")
                    )
                if result.link_ids:
                    copy = _save_debug_copy(conn, html, "ukjent-format")
                    raise FinnError(
                        "Finn ser ut til å ha endret hvordan søkesiden er bygd opp, så scraperen "
                        "klarte ikke å lese annonsene. Den har stoppet for ikke å lagre feil data."
                        + (f" En kopi av siden er lagret i {copy}." if copy else "")
                    )
                break
            new, known = store_ads(conn, search, result.ads)
            conn.commit()
            found += len(result.ads)
            new_here += new
            # Treffene er sortert med nyeste først. Har vi sett noen før, er resten gamle.
            if known > 0 or len(result.ads) < 10:
                break
        note = "" if found else (
            "Ingen treff. Hvis du vet at søket har treff på Finn, kan Finn ha endret nettsiden."
        )
        conn.execute(
            "UPDATE searches SET last_checked_at = ?, last_count = ?, last_new = ?, last_note = ? "
            "WHERE id = ?",
            (now_str(), found, new_here, note, search["id"]),
        )
        conn.commit()
        total_new += new_here
        checked += 1
    return {"checked": checked, "new": total_new}


def stop_with_error(conn: sqlite3.Connection, message: str) -> None:
    set_setting(conn, "scraper_enabled", 0)
    set_setting(conn, "scraper_error", message)
    set_setting(conn, "scraper_notice", "")
    log_event(conn, "feil", message)
    conn.commit()


def _parse(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Bakgrunnstråden


class ScraperWorker:
    def __init__(self, db_path: str, fetch: Callable[[str], str] = fetch_page,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.db_path = db_path
        self.fetch = fetch
        self.sleep = sleep
        self.running = False
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._manual = False
        self._only: Set[int] = set()
        self._network_failures = 0
        self._last_cleanup = 0.0
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="finn-scraper", daemon=True)
            self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def request_run(self, search_id: Optional[int] = None) -> None:
        with self._lock:
            if search_id is None:
                self._manual = True
            else:
                self._only.add(search_id)
        self._wake.set()

    def _loop(self) -> None:
        self._wake.wait(3)
        while True:
            self._wake.clear()
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - scraperen skal aldri krasje appen
                log.exception("Uventet feil i scraperen")
                try:
                    conn = connect(self.db_path)
                    stop_with_error(conn, f"Uventet feil i scraperen: {exc}. Scraperen har stoppet.")
                    conn.close()
                except sqlite3.Error:
                    pass
            self._check_for_update()
            self._cleanup()
            self._wake.wait(20)

    def _cleanup(self) -> None:
        if self._last_cleanup and time.monotonic() - self._last_cleanup < 3600:
            return
        self._last_cleanup = time.monotonic()
        from .cleanup import cleanup_listings

        try:
            conn = connect(self.db_path)
            try:
                cleanup_listings(conn)
            finally:
                conn.close()
        except sqlite3.Error as exc:
            log.warning("Klarte ikke å rydde i gamle annonser: %s", exc)

    def _check_for_update(self) -> None:
        if os.environ.get("GOLFLAGER_NO_UPDATE_CHECK"):
            return
        from .updater import UpdateError, check_for_update

        try:
            conn = connect(self.db_path)
            try:
                check_for_update(conn)
            finally:
                conn.close()
        except (UpdateError, sqlite3.Error, ValueError) as exc:
            log.info("Fant ikke ut om det finnes en ny versjon: %s", exc)

    def tick(self, now: Optional[datetime] = None) -> None:
        conn = connect(self.db_path)
        try:
            settings = get_settings(conn)
            with self._lock:
                manual, only = self._manual, set(self._only)
                self._manual, self._only = False, set()
            if not settings["scraper_enabled"]:
                return
            now = now or datetime.now()
            next_run = _parse(settings["scraper_next_run"])
            due = next_run is None or now >= next_run
            if not (due or manual or only):
                return
            if not conn.execute("SELECT 1 FROM searches WHERE active = 1 LIMIT 1").fetchone():
                return  # ingen søk å sjekke ennå
            full_round = due or manual
            self.running = True
            try:
                summary = run_checks(
                    conn,
                    search_ids=None if full_round else only,
                    fetch=self.fetch,
                    sleep=self.sleep,
                    should_continue=lambda: bool(get_settings(conn)["scraper_enabled"]),
                )
                self._network_failures = 0
                message = (
                    f"Sjekket {summary['checked']} søk, fant {summary['new']} nye annonser."
                )
                set_setting(conn, "scraper_notice", "")
                log_event(conn, "info", message)
            except NetworkError as exc:
                self._network_failures += 1
                if self._network_failures >= MAX_NETWORK_FAILURES:
                    stop_with_error(
                        conn,
                        f"{exc} Det har skjedd {self._network_failures} ganger på rad, så "
                        "scraperen har stoppet. Sjekk internettforbindelsen og slå den på igjen.",
                    )
                else:
                    notice = f"{exc} Prøver igjen ved neste sjekk."
                    set_setting(conn, "scraper_notice", notice)
                    log_event(conn, "advarsel", notice)
            except FinnError as exc:
                stop_with_error(conn, str(exc))
            finally:
                self.running = False
            set_setting(conn, "scraper_last_run", now_str())
            if full_round:
                interval = max(15, int(settings["scrape_interval_min"]))
                set_setting(
                    conn, "scraper_next_run",
                    (datetime.now() + timedelta(minutes=interval)).replace(microsecond=0)
                    .isoformat(sep=" "),
                )
            conn.commit()
        finally:
            conn.close()

    def can_run_manually(self, conn: sqlite3.Connection) -> bool:
        last = _parse(get_settings(conn)["scraper_last_run"])
        return last is None or datetime.now() - last >= MANUAL_MIN_GAP
