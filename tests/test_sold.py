"""Hvordan Golflager oppdager at annonser er solgt eller borte fra Finn."""
import json
from datetime import datetime, timedelta

import pytest
from conftest import add_search

from golflager.db import get_settings, set_setting
from golflager.finn_parser import ad_from_dict, parse_search_page
from golflager.scraper import run_checks


def page(ids, sold=(), total=None):
    docs = []
    for i in ids:
        doc = {"ad_id": i, "heading": f"Scotty Cameron putter {i}", "price": {"amount": 2000},
               "canonical_url": f"https://www.finn.no/recommerce/forsale/item/{i}"}
        if i in sold:
            doc["flags"] = ["sold"]
        docs.append(doc)
    data = {"docs": docs}
    if total is not None:
        data["metadata"] = {"result_size": {"match_count": total}}
    return "<html><script type='application/json'>" + json.dumps(data) + "</script></html>"


def no_sleep(_):
    pass


@pytest.fixture
def search(conn):
    add_search(conn)
    return conn


def statuses(conn):
    return {r["finn_id"]: (r["gone_reason"] or "aktiv")
            for r in conn.execute("SELECT finn_id, gone_reason FROM listings")}


def test_sold_labels_are_read():
    assert ad_from_dict({"ad_id": 412345678, "heading": "x", "price": 1, "flags": ["SOLD"]}).sold
    assert ad_from_dict({"ad_id": 412345678, "heading": "x", "price": 1,
                         "labels": [{"id": "sold", "text": "Solgt"}]}).sold
    assert not ad_from_dict({"ad_id": 412345678, "heading": "x", "price": 1,
                             "flags": ["private"]}).sold
    html = ('<article><a href="/recommerce/forsale/item/412300009">Ping putter</a>'
            '<span>Solgt</span><span>900 kr</span></article>')
    assert parse_search_page(html).ads[0].sold
    assert parse_search_page(page([412300001], total=17)).total == 17


def test_missing_ads_are_marked_sold_after_full_check(search):
    now = datetime.now()
    run_checks(search, fetch=lambda url: page([412300001, 412300002, 412300003, 412300004]),
               sleep=no_sleep, now=now)
    # Seks timer senere er én annonse borte
    later = now + timedelta(hours=7)
    search.execute("UPDATE listings SET first_seen_at = ?",
                   ((now - timedelta(hours=1)).isoformat(sep=" ", timespec="seconds"),))
    search.commit()
    summary = run_checks(search, fetch=lambda url: page([412300001, 412300002, 412300004]),
                         sleep=no_sleep, now=later)
    assert summary["gone"] == 1
    assert statuses(search)["412300003"] == "borte"


def test_sold_label_is_used_right_away(search):
    run_checks(search, fetch=lambda url: page([412300001, 412300002], sold={412300002}),
               sleep=no_sleep)
    assert statuses(search) == {"412300001": "aktiv", "412300002": "solgt"}


def test_ad_that_comes_back_is_active_again(search):
    search.execute("UPDATE settings SET value = '0' WHERE key = 'sold_check_hours'")
    search.commit()
    run_checks(search, fetch=lambda url: page([412300001], sold={412300001}), sleep=no_sleep)
    assert statuses(search)["412300001"] == "solgt"
    run_checks(search, fetch=lambda url: page([412300001]), sleep=no_sleep)
    assert statuses(search)["412300001"] == "aktiv"


def test_full_check_only_now_and_then(search):
    calls = []

    def fetch(url):
        calls.append(url)
        return page(list(range(412300100, 412300100 + 50)))  # alltid fulle sider

    now = datetime.now()
    run_checks(search, fetch=fetch, sleep=no_sleep, now=now)
    assert len(calls) == 2  # side 2 er lik side 1, altså forbi siste side
    calls.clear()
    run_checks(search, fetch=fetch, sleep=no_sleep, now=now + timedelta(minutes=30))
    assert len(calls) == 1  # vanlig sjekk: bare første side
    set_setting(search, "sold_check_hours", 0)
    search.commit()
    calls.clear()
    run_checks(search, fetch=fetch, sleep=no_sleep, now=now + timedelta(days=2))
    assert len(calls) == 1


def test_too_big_search_marks_nothing(search):
    now = datetime.now()
    first = list(range(412300200, 412300210))
    run_checks(search, fetch=lambda url: page(first, total=500), sleep=no_sleep, now=now)
    search.execute("UPDATE listings SET first_seen_at = '2026-01-01 00:00:00'")
    search.commit()

    def endless(url):
        number = int(url.split("page=")[1]) if "page=" in url else 1
        start = 412300300 + number * 10
        return page(list(range(start, start + 10)), total=500)

    summary = run_checks(search, fetch=endless, sleep=no_sleep, now=now + timedelta(hours=7))
    assert summary["gone"] == 0
    assert set(statuses(search).values()) == {"aktiv"}
    assert any("mer enn 5 sider" in r[0] for r in search.execute("SELECT message FROM scrape_log"))


def test_safety_stop_when_too_many_vanish(search):
    now = datetime.now()
    ids = list(range(412300400, 412300408))
    run_checks(search, fetch=lambda url: page(ids), sleep=no_sleep, now=now)
    search.execute("UPDATE listings SET first_seen_at = '2026-01-01 00:00:00'")
    search.commit()
    summary = run_checks(search, fetch=lambda url: page(ids[:2]), sleep=no_sleep,
                         now=now + timedelta(hours=7))
    assert summary["gone"] == 0
    assert set(statuses(search).values()) == {"aktiv"}
    assert any("ser rart ut" in r[0] for r in search.execute("SELECT message FROM scrape_log"))


def test_sold_ads_have_their_own_tab(client, search):
    run_checks(search, fetch=lambda url: page([412300501, 412300502], sold={412300502}),
               sleep=no_sleep)
    html = client.get("/funn").get_data(as_text=True)
    assert "putter 412300501" in html and "putter 412300502" not in html
    assert "Solgt / borte <span class=\"count\">1</span>" in html
    html = client.get("/funn?vis=borte").get_data(as_text=True)
    assert "putter 412300502" in html and "Finn viser annonsen som solgt" in html
    assert ">Kjøpt</button>" not in html
    # Telleren i menyen teller ikke solgte annonser
    assert get_settings(search)["last_seen_finds_at"] != ""
    client.post("/funn/rydd?vis=borte", data={"handling": "slett"})
    assert search.execute("SELECT status FROM listings WHERE finn_id = '412300502'"
                          ).fetchone()[0] == "slettet"


def test_old_database_gets_sold_columns(tmp_path):
    import sqlite3

    from golflager import create_app

    path = tmp_path / "gammel.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE listings (id INTEGER PRIMARY KEY AUTOINCREMENT, finn_id TEXT NOT NULL UNIQUE,
            search_id INTEGER, title TEXT NOT NULL, price INTEGER, location TEXT NOT NULL DEFAULT '',
            published_at TEXT, url TEXT NOT NULL, image_url TEXT NOT NULL DEFAULT '',
            brand TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'annet', condition INTEGER, status TEXT NOT NULL DEFAULT 'ny',
            first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, inventory_id INTEGER);
        CREATE TABLE searches (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            url TEXT NOT NULL, default_brand TEXT NOT NULL DEFAULT '',
            default_type TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, last_checked_at TEXT, last_count INTEGER, last_new INTEGER,
            last_note TEXT NOT NULL DEFAULT '');
    """)
    old.commit()
    old.close()
    app = create_app(str(path), start_scraper=False)
    conn = sqlite3.connect(path)
    listing_columns = {r[1] for r in conn.execute("PRAGMA table_info(listings)")}
    search_columns = {r[1] for r in conn.execute("PRAGMA table_info(searches)")}
    assert {"gone_at", "gone_reason"} <= listing_columns
    assert "last_full_check_at" in search_columns
    assert app.test_client().get("/funn?vis=borte").status_code == 200


def test_more_ways_finn_can_mark_sold():
    base = {"ad_id": 412345678, "heading": "Solgt: Stealth 3 wood", "price": {"amount": 1200}}
    assert not ad_from_dict(base).sold  # «Solgt» i tittelen teller ikke
    assert ad_from_dict({**base, "disposed": True}).sold
    assert ad_from_dict({**base, "ad_status": "DISPOSED"}).sold
    assert ad_from_dict({**base, "labels": [{"id": "x", "text": "Solgt"}]}).sold
    assert not ad_from_dict({**base, "flags": ["private", "shipping_exists"]}).sold


def test_check_for_sold_now_forces_full_check(search):
    calls = []

    def fetch(url):
        calls.append(url)
        return page(list(range(412300600, 412300650)))

    now = datetime.now()
    run_checks(search, fetch=fetch, sleep=no_sleep, now=now)
    calls.clear()
    run_checks(search, fetch=fetch, sleep=no_sleep, now=now + timedelta(minutes=5),
               force_full=True)
    assert len(calls) == 2  # blar gjennom hele søket selv om det ikke har gått 6 timer


def test_worker_can_be_asked_for_full_check(db_path, search):
    from golflager.scraper import ScraperWorker

    calls = []
    worker = ScraperWorker(db_path, fetch=lambda url: calls.append(url) or page(
        list(range(412300700, 412300750))), sleep=no_sleep)
    worker.tick()
    calls.clear()
    worker.request_run(full=True)
    worker.tick()
    assert len(calls) == 2


def test_mark_as_sold_by_hand_with_diagnostics(client, search):
    data = page([412300801, 412300802])
    data = data.replace('"heading": "Scotty Cameron putter 412300802"',
                        '"heading": "Scotty Cameron putter 412300802", "labels": '
                        '[{"id": "ukjent_merke", "text": "Noe nytt"}]')
    run_checks(search, fetch=lambda url: data, sleep=no_sleep)
    listing_id = search.execute("SELECT id FROM listings WHERE finn_id = '412300802'"
                                ).fetchone()[0]
    response = client.post(f"/funn/{listing_id}/solgt", data={"next": "/funn"})
    assert response.status_code == 302
    row = search.execute("SELECT gone_reason FROM listings WHERE id = ?", (listing_id,)).fetchone()
    assert row[0] == "manuell"
    text = get_settings(search)["diagnostic_text"]
    assert "412300802" in text and "Data fra søkesiden" in text and "Noe nytt" in text
    html = client.get("/innstillinger").get_data(as_text=True)
    assert "Feilsøking" in html and "Kopier teksten" in html
    html = client.get("/funn?vis=borte").get_data(as_text=True)
    assert "Du merket annonsen som solgt" in html
    client.post(f"/funn/{listing_id}/aktiv")
    assert search.execute("SELECT gone_at FROM listings WHERE id = ?",
                          (listing_id,)).fetchone()[0] is None
    client.post("/feilsoking/tom")
    assert get_settings(search)["diagnostic_text"] == ""


def test_diagnostics_when_ad_is_missing_from_search(client, search):
    run_checks(search, fetch=lambda url: page([412300901]), sleep=no_sleep)
    search.execute("""INSERT INTO listings (finn_id, search_id, title, price, url, first_seen_at,
                      last_seen_at) VALUES ('412300999', 1, 'Borte', 100, 'u', '2026-09-01',
                      '2026-09-01')""")
    search.commit()
    listing_id = search.execute("SELECT id FROM listings WHERE finn_id = '412300999'"
                                ).fetchone()[0]
    client.post(f"/funn/{listing_id}/solgt")
    assert "var ikke med i de siste søkesidene" in get_settings(search)["diagnostic_text"]


def test_check_sold_now_button(client, search, app):
    calls = []
    app.extensions["scraper"].request_run = lambda search_id=None, full=False: calls.append(full)
    html = client.post("/scraper/solgte", follow_redirects=True).get_data(as_text=True)
    assert calls == [True] and "Ser etter solgte annonser nå" in html
    assert "Se etter solgte nå" in client.get("/sok").get_data(as_text=True)
