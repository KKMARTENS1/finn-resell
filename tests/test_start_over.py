"""«Start på nytt»: alle annonser slettes, men lageret og innstillingene beholdes."""
import json
from datetime import datetime, timedelta
from pathlib import Path

from conftest import add_item, add_listing, add_search

from golflager.cleanup import start_over
from golflager.db import get_settings, set_setting
from golflager.scraper import run_checks


def page(ads):
    """En søkeside der hver annonse er (finnkode, publisert)."""
    docs = []
    for finn_id, published in ads:
        doc = {"ad_id": finn_id, "heading": f"Ping Anser putter {finn_id}",
               "price": {"amount": 1500},
               "canonical_url": f"https://www.finn.no/recommerce/forsale/item/{finn_id}"}
        if published is not None:
            doc["timestamp"] = int(published.timestamp() * 1000)
        docs.append(doc)
    return ("<html><script type='application/json'>" + json.dumps({"docs": docs})
            + "</script></html>")


def no_sleep(_):
    pass


def test_start_over_deletes_ads_but_keeps_inventory_and_settings(conn, db_path):
    add_search(conn)
    add_item(conn, status="solgt", sale_price=3000, sale_date="2026-09-01")
    add_listing(conn, 840001, "Ping Anser putter", 900, "Ping", "Anser", "putter")
    add_listing(conn, 840002, "Gammel annonse", 900, status="skjult")
    set_setting(conn, "min_profit_kr", 700)
    conn.commit()

    backup = start_over(conn)

    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0] == 1
    assert get_settings(conn)["min_profit_kr"] == 700
    assert backup.exists() and backup.parent == Path(db_path).parent / "sikkerhetskopier"


def test_only_new_ads_show_up_after_starting_over(conn):
    add_search(conn)
    start_over(conn, only_new=True)
    now = datetime.now()
    old, new = now - timedelta(days=3), now + timedelta(minutes=5)
    run_checks(conn, fetch=lambda url: page([(412310001, old), (412310002, new),
                                              (412310003, None)]),
               sleep=no_sleep, force_full=True)
    statuses = dict(conn.execute("SELECT finn_id, status FROM listings").fetchall())
    # Annonser som lå ute fra før (eller er uten dato ved første sjekk), blir skjult
    assert statuses == {"412310001": "skjult", "412310002": "ny", "412310003": "skjult"}

    # Det gjelder bare første gjennomgang. Etterpå er nye treff nye som vanlig.
    assert conn.execute("SELECT hide_before FROM searches").fetchone()[0] is None
    run_checks(conn, fetch=lambda url: page([(412310004, None), (412310005, old),
                                              (412310002, new)]),
               sleep=no_sleep, force_full=True)
    statuses = dict(conn.execute("SELECT finn_id, status FROM listings").fetchall())
    assert statuses["412310004"] == "ny" and statuses["412310005"] == "ny"


def test_start_over_can_fetch_everything_again_or_delete_searches(conn):
    add_search(conn)
    start_over(conn, only_new=False)
    old = datetime.now() - timedelta(days=3)
    run_checks(conn, fetch=lambda url: page([(412320001, old)]), sleep=no_sleep, force_full=True)
    assert conn.execute("SELECT status FROM listings").fetchone()[0] == "ny"

    start_over(conn, keep_searches=False)
    assert conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0] == 0


def test_new_searches_are_not_affected(conn):
    add_search(conn)
    start_over(conn, only_new=True)
    add_search(conn, url="https://www.finn.no/recommerce/forsale/search?q=ping", name="Ping")
    old = datetime.now() - timedelta(days=3)
    ping_id = conn.execute("SELECT id FROM searches WHERE name = 'Ping'").fetchone()[0]
    run_checks(conn, search_ids={ping_id}, fetch=lambda url: page([(412330001, old)]),
               sleep=no_sleep, force_full=True)
    assert conn.execute("SELECT status FROM listings").fetchone()[0] == "ny"


def test_start_over_button(client, conn):
    add_search(conn)
    add_item(conn)
    add_listing(conn, 850001, "Ping Anser putter", 900, "Ping", "Anser", "putter")
    html = client.get("/innstillinger").get_data(as_text=True)
    assert "Start på nytt" in html and "Slett alle annonser" in html
    response = client.post("/innstillinger/start-pa-nytt",
                           data={"visning": "nye", "behold_sok": "1"}, follow_redirects=True)
    html = response.get_data(as_text=True)
    assert "Alle annonser er slettet" in html and "Lageret ditt er som før" in html
    assert conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 1
    assert conn.execute("SELECT hide_before FROM searches").fetchone()[0]
