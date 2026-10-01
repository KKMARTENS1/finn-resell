import re
from datetime import datetime, timedelta

import pytest
from conftest import add_listing, add_search, fixture_text

from golflager.cleanup import cleanup_listings
from golflager.db import get_settings, set_setting
from golflager.pricing import PriceData
from golflager.scraper import run_checks


def card_titles(html):
    return re.findall(r'<h3 class="find__title"><a [^>]*>([^<]+)</a>', html)


@pytest.fixture
def finds(conn):
    for i in range(3):
        add_listing(conn, 900 + i, f"Marked {i}", 3000, "Scotty Cameron", "Newport 2", "putter",
                    status="skjult")
    now = datetime.now()
    rows = [
        (1, "Billig putter", 800, "putter", 3),
        (2, "Dyr putter", 2900, "putter", 2),
        (3, "Mellom putter", 1500, "putter", 1),
        (4, "Driver uten pris", None, "driver", 0),
    ]
    for finn_id, title, price, type_, hours in rows:
        seen = (now - timedelta(hours=hours)).replace(microsecond=0).isoformat(sep=" ")
        add_listing(conn, finn_id, title, price, "Scotty Cameron", "Newport 2", type_, seen=seen)
    return conn


def test_finds_sort_by_price_and_profit(client, finds):
    assert card_titles(client.get("/funn").get_data(as_text=True)) == [
        "Driver uten pris", "Mellom putter", "Dyr putter", "Billig putter"]
    assert card_titles(client.get("/funn?sorter=eldste").get_data(as_text=True)) == [
        "Billig putter", "Dyr putter", "Mellom putter", "Driver uten pris"]
    assert card_titles(client.get("/funn?sorter=pris_lav").get_data(as_text=True)) == [
        "Billig putter", "Mellom putter", "Dyr putter", "Driver uten pris"]
    assert card_titles(client.get("/funn?sorter=pris_hoy").get_data(as_text=True)) == [
        "Dyr putter", "Mellom putter", "Billig putter", "Driver uten pris"]
    assert card_titles(client.get("/funn?sorter=fortjeneste").get_data(as_text=True))[0] == \
        "Billig putter"
    html = client.get("/funn?sorter=pris_lav&type=putter").get_data(as_text=True)
    assert card_titles(html) == ["Billig putter", "Mellom putter", "Dyr putter"]
    # Kategori- og sidelenker beholder sorteringen
    assert "sorter=pris_lav" in re.search(r'href="([^"]*merke=Scotty[^"]*)"', html).group(1)


def test_hide_all_visible_uses_the_filters(client, finds, conn):
    response = client.post("/funn/rydd?vis=ny&type=putter", data={"handling": "skjul"})
    assert response.status_code == 302
    assert "type=putter" in response.headers["Location"]
    statuses = dict(conn.execute("SELECT title, status FROM listings WHERE finn_id < 900"))
    assert statuses == {"Billig putter": "skjult", "Dyr putter": "skjult",
                        "Mellom putter": "skjult", "Driver uten pris": "ny"}


def test_delete_hidden_and_single_delete(client, finds, conn):
    client.post("/funn/rydd?vis=ny", data={"handling": "skjul"})
    listing_id = conn.execute("SELECT id FROM listings WHERE finn_id = '1'").fetchone()[0]
    client.post(f"/funn/{listing_id}/slett")
    assert conn.execute("SELECT status FROM listings WHERE id = ?",
                        (listing_id,)).fetchone()[0] == "slettet"
    client.post("/funn/rydd?vis=skjult&type=driver", data={"handling": "slett"})
    assert conn.execute("SELECT status FROM listings WHERE finn_id = '4'").fetchone()[0] == "slettet"
    assert conn.execute("SELECT status FROM listings WHERE finn_id = '2'").fetchone()[0] == "skjult"
    html = client.get("/funn?vis=skjult").get_data(as_text=True)
    assert "Billig putter" not in html and "Dyr putter" in html


def test_bulk_action_must_match_the_tab(client, finds):
    assert client.post("/funn/rydd?vis=ny", data={"handling": "slett"}).status_code == 400
    assert client.post("/funn/rydd?vis=skjult", data={"handling": "skjul"}).status_code == 400


def test_deleted_listing_stays_deleted_and_counts_in_market(conn):
    add_search(conn)
    turbo = fixture_text("finn_turbo_stream.html")
    run_checks(conn, fetch=lambda url: turbo, sleep=lambda s: None)
    conn.execute("UPDATE listings SET status = 'slettet' WHERE finn_id = '412345671'")
    conn.commit()
    summary = run_checks(conn, fetch=lambda url: turbo, sleep=lambda s: None)
    assert summary["new"] == 0
    assert conn.execute("SELECT status FROM listings WHERE finn_id = '412345671'").fetchone()[0] \
        == "slettet"
    market_ids = {row["finn_id"] for row in PriceData(conn, get_settings(conn)).market}
    assert "412345671" in market_ids


def test_automatic_cleanup(conn):
    now = datetime(2026, 10, 1, 12, 0)
    for finn_id, days, status in [(1, 5, "ny"), (2, 40, "ny"), (3, 50, "skjult"),
                                  (4, 70, "skjult"), (5, 90, "kjopt")]:
        seen = (now - timedelta(days=days)).isoformat(sep=" ")
        add_listing(conn, finn_id, f"Annonse {finn_id}", 1000, status=status, seen=seen)
    assert cleanup_listings(conn, now=now) == (1, 1)
    statuses = dict(conn.execute("SELECT finn_id, status FROM listings"))
    assert statuses == {"1": "ny", "2": "skjult", "3": "skjult", "4": "slettet", "5": "kjopt"}
    events = [r[0] for r in conn.execute("SELECT message FROM scrape_log")]
    assert any("Automatisk rydding" in e for e in events)


def test_automatic_cleanup_can_be_turned_off(conn):
    set_setting(conn, "auto_hide_days", 0)
    set_setting(conn, "auto_delete_days", 0)
    conn.commit()
    old = (datetime.now() - timedelta(days=400)).isoformat(sep=" ", timespec="seconds")
    add_listing(conn, 1, "Gammel", 1000, seen=old)
    add_listing(conn, 2, "Gammel skjult", 1000, status="skjult", seen=old)
    assert cleanup_listings(conn) == (0, 0)


def test_inventory_and_market_sorting(client, filled):
    html = client.get("/lager?sorter=kostnad").get_data(as_text=True)
    names = re.findall(r'<div class="item-name"><a [^>]*>([^<]+)</a>', html)
    assert names[0].startswith("Titleist T100")  # 6000 kr
    html = client.get("/lager?sorter=merke").get_data(as_text=True)
    names = re.findall(r'<div class="item-name"><a [^>]*>([^<]+)</a>', html)
    assert [n.split()[0] for n in names] == sorted(n.split()[0] for n in names)
    html = client.get("/markedspriser?sorter=pris_lav").get_data(as_text=True)
    assert html.index("Anser") < html.index("Newport 2")
    html = client.get("/markedspriser?sorter=pris_hoy").get_data(as_text=True)
    assert html.index("Newport 2") < html.index("Anser")


def test_settings_for_cleanup(client, conn):
    client.post("/innstillinger", data={"auto_hide_days": "14", "auto_delete_days": "0"})
    settings = get_settings(conn)
    assert settings["auto_hide_days"] == 14 and settings["auto_delete_days"] == 0


def test_age_filter_lets_you_hide_only_old_finds(client, conn):
    old = (datetime.now() - timedelta(days=20)).isoformat(sep=" ", timespec="seconds")
    add_listing(conn, 820001, "Gammel Ping Anser putter", 900, "Ping", "Anser", "putter")
    add_listing(conn, 820002, "Ny Ping Anser putter", 900, "Ping", "Anser", "putter")
    conn.execute("UPDATE listings SET first_seen_at = ?, published_at = ? WHERE finn_id = '820001'",
                 (old, old))
    conn.commit()
    html = client.get("/funn?alder=14").get_data(as_text=True)
    assert "Gammel Ping Anser" in html and "Ny Ping Anser" not in html
    client.post("/funn/rydd?alder=14", data={"handling": "skjul"})
    statuses = dict(conn.execute("SELECT finn_id, status FROM listings").fetchall())
    assert statuses == {"820001": "skjult", "820002": "ny"}
