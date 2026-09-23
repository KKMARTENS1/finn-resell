from datetime import datetime, timedelta

import pytest
import requests
from conftest import add_search, fixture_text

from golflager import scraper
from golflager.db import get_settings, set_setting
from golflager.scraper import (FinnError, NetworkError, ScraperWorker, normalize_search_url,
                               page_url, run_checks, suggest_name)

TURBO = fixture_text("finn_turbo_stream.html")


def no_sleep(_seconds):
    pass


# ---------------------------------------------------------------------------
# Lenker


def test_normalize_search_url_adds_newest_first():
    url = normalize_search_url("finn.no/recommerce/forsale/search?q=scotty+cameron&price_to=3000&page=3")
    assert url.startswith("https://www.finn.no/recommerce/forsale/search?")
    assert "sort=PUBLISHED_DESC" in url
    assert "page=" not in url
    assert "price_to=3000" in url


def test_normalize_keeps_existing_sort():
    url = normalize_search_url("https://www.finn.no/recommerce/forsale/search?q=ping&sort=PRICE_ASC")
    assert url.count("sort=") == 1 and "PRICE_ASC" in url


@pytest.mark.parametrize("bad", [
    "", "https://www.google.com/search?q=golf",
    "https://www.finn.no/recommerce/forsale/item/412345678",
    "https://www.finn.no/",
])
def test_normalize_rejects_bad_links(bad):
    with pytest.raises(ValueError):
        normalize_search_url(bad)


def test_page_url_and_name():
    url = "https://www.finn.no/recommerce/forsale/search?q=scotty+cameron&price_to=3000"
    assert page_url(url, 1) == url
    assert page_url(url, 2).endswith("page=2")
    assert suggest_name(url) == "Scotty cameron (maks 3 000 kr)"


# ---------------------------------------------------------------------------
# Henting


class FakeResponse:
    def __init__(self, status=200, text="<html></html>",
                 url="https://www.finn.no/recommerce/forsale/search?q=x"):
        self.status_code = status
        self.text = text
        self.url = url
        self.encoding = "utf-8"


@pytest.mark.parametrize("status, words", [(403, "nektet tilgang"), (429, "for mange"),
                                           (500, "feilkode 500")])
def test_fetch_stops_on_error_codes(monkeypatch, status, words):
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: FakeResponse(status))
    with pytest.raises(FinnError) as err:
        scraper.fetch_page("https://www.finn.no/recommerce/forsale/search?q=x")
    assert words in str(err.value)


def test_fetch_never_follows_to_login(monkeypatch):
    monkeypatch.setattr(scraper.requests, "get", lambda *a, **k: FakeResponse(
        url="https://login.schibsted.com/authn/?client=finn"))
    with pytest.raises(FinnError) as err:
        scraper.fetch_page("https://www.finn.no/recommerce/forsale/search?q=x")
    assert "logger aldri inn" in str(err.value)


def test_fetch_sends_no_cookies_and_honest_agent(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse(text="ok")

    monkeypatch.setattr(scraper.requests, "get", fake_get)
    assert scraper.fetch_page("https://www.finn.no/recommerce/forsale/search?q=x") == "ok"
    assert "cookies" not in seen
    assert "Golflager" in seen["headers"]["User-Agent"]


def test_network_problem_is_not_a_block(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("no network")

    monkeypatch.setattr(scraper.requests, "get", boom)
    with pytest.raises(NetworkError):
        scraper.fetch_page("https://www.finn.no/recommerce/forsale/search?q=x")


# ---------------------------------------------------------------------------
# En runde


def test_run_checks_stores_new_ads_and_skips_wanted(conn):
    add_search(conn, default_brand="Scotty Cameron", default_type="putter")
    fetched = []
    summary = run_checks(conn, fetch=lambda url: fetched.append(url) or TURBO, sleep=no_sleep)
    assert summary == {"checked": 1, "new": 3}
    assert len(fetched) == 1  # bare søkesiden, ingen enkeltannonser
    rows = {r["finn_id"]: r for r in conn.execute("SELECT * FROM listings")}
    assert "412345673" not in rows  # «Ønskes kjøpt»
    putter = rows["412345671"]
    assert (putter["brand"], putter["model"], putter["type"]) == ("Scotty Cameron", "Newport 2", "putter")
    assert putter["status"] == "ny"
    driver = rows["412345672"]
    assert (driver["brand"], driver["type"]) == ("Titleist", "driver")
    history = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
    assert history == 3


def test_second_run_finds_nothing_new_but_tracks_price_changes(conn):
    add_search(conn)
    run_checks(conn, fetch=lambda url: TURBO, sleep=no_sleep)
    changed = TURBO.replace("2500", "2200")
    summary = run_checks(conn, fetch=lambda url: changed, sleep=no_sleep)
    assert summary["new"] == 0
    row = conn.execute("SELECT id, price FROM listings WHERE finn_id = '412345671'").fetchone()
    assert row["price"] == 2200
    prices = [r[0] for r in conn.execute(
        "SELECT price FROM price_history WHERE listing_id = ? ORDER BY id", (row["id"],))]
    assert prices == [2500, 2200]


def test_hidden_listing_stays_hidden(conn):
    add_search(conn)
    run_checks(conn, fetch=lambda url: TURBO, sleep=no_sleep)
    conn.execute("UPDATE listings SET status = 'skjult' WHERE finn_id = '412345671'")
    run_checks(conn, fetch=lambda url: TURBO, sleep=no_sleep)
    status = conn.execute("SELECT status FROM listings WHERE finn_id = '412345671'").fetchone()[0]
    assert status == "skjult"


def test_waits_between_pages(conn):
    add_search(conn, url="https://www.finn.no/recommerce/forsale/search?q=a&sort=PUBLISHED_DESC")
    add_search(conn, url="https://www.finn.no/recommerce/forsale/search?q=b&sort=PUBLISHED_DESC")
    waits = []
    run_checks(conn, fetch=lambda url: TURBO, sleep=waits.append)
    assert len(waits) == 1
    assert 5 <= waits[0] <= 9


def test_captcha_stops_with_message(conn):
    add_search(conn)
    with pytest.raises(FinnError) as err:
        run_checks(conn, fetch=lambda url: fixture_text("finn_captcha.html"), sleep=no_sleep)
    assert "robot-sjekk" in str(err.value)


def test_changed_layout_stops_instead_of_guessing(conn):
    add_search(conn)
    html = '<html><body><a href="/recommerce/forsale/item/412345678"><img src="x.jpg"></a></body></html>'
    with pytest.raises(FinnError) as err:
        run_checks(conn, fetch=lambda url: html, sleep=no_sleep)
    assert "endret" in str(err.value)


def test_empty_search_is_fine(conn):
    add_search(conn)
    summary = run_checks(conn, fetch=lambda url: "<html><body>Ingen treff</body></html>",
                         sleep=no_sleep)
    assert summary == {"checked": 1, "new": 0}
    note = conn.execute("SELECT last_note FROM searches").fetchone()[0]
    assert "Ingen treff" in note


# ---------------------------------------------------------------------------
# Bakgrunnsjobben


def test_worker_stops_and_turns_off_on_block(db_path, conn):
    add_search(conn)

    def blocked(url):
        raise FinnError("Finn nektet tilgang (feilkode 403).")

    worker = ScraperWorker(db_path, fetch=blocked, sleep=no_sleep)
    worker.tick()
    conn.commit()
    settings = get_settings(conn)
    assert settings["scraper_enabled"] == 0
    assert "403" in settings["scraper_error"]
    # Den prøver ikke igjen av seg selv
    calls = []
    worker.fetch = lambda url: calls.append(url) or TURBO
    worker.tick(now=datetime.now() + timedelta(days=1))
    assert calls == []


def test_worker_respects_interval_and_manual_runs(db_path, conn):
    add_search(conn)
    calls = []
    worker = ScraperWorker(db_path, fetch=lambda url: calls.append(url) or TURBO, sleep=no_sleep)
    worker.tick()
    assert len(calls) == 1
    worker.tick()  # ikke tid ennå
    assert len(calls) == 1
    worker.tick(now=datetime.now() + timedelta(minutes=31))
    assert len(calls) == 2
    worker.request_run()
    worker.tick()
    assert len(calls) == 3
    assert get_settings(conn)["scraper_enabled"] == 1


def test_worker_network_problems_stop_after_three(db_path, conn):
    add_search(conn)

    def offline(url):
        raise NetworkError("Fikk ikke kontakt med Finn (ConnectionError).")

    worker = ScraperWorker(db_path, fetch=offline, sleep=no_sleep)
    for attempt in range(2):
        worker.request_run()
        worker.tick()
        settings = get_settings(conn)
        assert settings["scraper_enabled"] == 1
        assert "Prøver igjen" in settings["scraper_notice"]
    worker.request_run()
    worker.tick()
    settings = get_settings(conn)
    assert settings["scraper_enabled"] == 0
    assert "internett" in settings["scraper_error"]


def test_worker_does_nothing_when_off(db_path, conn):
    add_search(conn)
    set_setting(conn, "scraper_enabled", 0)
    conn.commit()
    calls = []
    worker = ScraperWorker(db_path, fetch=lambda url: calls.append(url) or TURBO, sleep=no_sleep)
    worker.request_run()
    worker.tick()
    assert calls == []
