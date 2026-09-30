import pytest
from conftest import add_item, add_listing, add_search

from golflager.db import get_settings

PAGES = ["/", "/funn", "/funn?vis=skjult", "/funn?vis=kjopt", "/lager", "/lager/ny",
         "/prissjekk", "/markedspriser", "/markedspriser?gruppe=merke",
         "/markedspriser?gruppe=type&periode=0", "/sok", "/innstillinger"]


@pytest.mark.parametrize("path", PAGES)
def test_pages_work_when_empty(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert "Golflager" in response.get_data(as_text=True)


@pytest.mark.parametrize("path", PAGES + ["/prissjekk?funn=1", "/lager?status=lager",
                                          "/lager?type=putter&q=scotty", "/funn?farge=gronn"])
def test_pages_work_with_data(client, filled, path):
    assert client.get(path).status_code == 200


def test_dashboard_numbers(client, filled):
    html = client.get("/").get_data(as_text=True)
    # investert: 1650 + 2500 + 6000 = 10 150, bundet: 6000, omsetning 5300, fortjeneste 1350 - 200
    assert "10 150 kr" in html
    assert "6 000 kr" in html
    assert "5 300 kr" in html
    assert "1 150 kr" in html
    assert "Fortjeneste per måned" in html


def test_budget_warning(client, filled, conn):
    client.post("/innstillinger", data={"budget_kr": "5000"})
    html = client.get("/").get_data(as_text=True)
    assert "Du er over budsjettet" in html


def test_buy_from_finds_moves_to_inventory(client, filled, conn):
    listing_id = conn.execute("SELECT id FROM listings WHERE finn_id = '200'").fetchone()[0]
    response = client.post(f"/funn/{listing_id}/kjopt")
    assert response.status_code == 302
    item = conn.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 1").fetchone()
    assert (item["brand"], item["model"], item["purchase_price"], item["status"]) == (
        "Ping", "Anser", 900, "kjopt")
    listing = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    assert listing["status"] == "kjopt" and listing["inventory_id"] == item["id"]
    assert response.headers["Location"].endswith(f"/lager/{item['id']}")


def test_hide_and_unhide(client, filled, conn):
    listing_id = conn.execute("SELECT id FROM listings WHERE finn_id = '200'").fetchone()[0]
    client.post(f"/funn/{listing_id}/skjul", data={"next": "/funn"})
    assert conn.execute("SELECT status FROM listings WHERE id = ?", (listing_id,)).fetchone()[0] == "skjult"
    assert "Ping Anser putter" not in client.get("/funn").get_data(as_text=True)
    assert "Ping Anser putter" in client.get("/funn?vis=skjult").get_data(as_text=True)
    client.post(f"/funn/{listing_id}/vis")
    assert conn.execute("SELECT status FROM listings WHERE id = ?", (listing_id,)).fetchone()[0] == "ny"


def test_correct_classification(client, filled, conn):
    listing_id = conn.execute("SELECT id FROM listings WHERE finn_id = '200'").fetchone()[0]
    client.post(f"/funn/{listing_id}/rett", data={"brand": "Ping", "model": "Anser 2", "type": "putter"})
    assert conn.execute("SELECT model FROM listings WHERE id = ?", (listing_id,)).fetchone()[0] == "Anser 2"


def test_finds_page_marks_seen(client, filled, conn):
    assert get_settings(conn)["last_seen_finds_at"] == ""
    html = client.get("/").get_data(as_text=True)
    assert "nye funn siden sist" in html
    client.get("/funn")
    assert get_settings(conn)["last_seen_finds_at"] != ""


def test_inventory_create_edit_delete(client, conn):
    response = client.post("/lager/ny", data={
        "brand": "Scotty Cameron", "model": "Futura 5W", "type": "putter", "condition": "4",
        "purchase_price": "2 500", "purchase_date": "2026-05-01", "cost_grip": "250",
        "status": "kjopt", "notes": "Nytt grep",
    })
    assert response.status_code == 302
    item = conn.execute("SELECT * FROM inventory").fetchone()
    assert item["purchase_price"] == 2500 and item["cost_grip"] == 250 and item["condition"] == 4

    response = client.post(f"/lager/{item['id']}", data={
        "brand": "Scotty Cameron", "model": "Futura 5W", "type": "putter", "condition": "4",
        "purchase_price": "2500", "purchase_date": "2026-05-01", "cost_grip": "250",
        "status": "solgt", "sale_price": "3900",
    })
    assert response.status_code == 302
    item = conn.execute("SELECT * FROM inventory").fetchone()
    assert item["status"] == "solgt" and item["sale_price"] == 3900 and item["sale_date"]

    client.post(f"/lager/{item['id']}/slett")
    assert conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0


def test_inventory_validation(client, conn):
    response = client.post("/lager/ny", data={"brand": "", "status": "solgt", "type": "putter"})
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Fyll inn merke" in html
    assert "Fyll inn salgspris" in html
    assert conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0] == 0


def test_manual_price_check(client, filled):
    html = client.get("/prissjekk?merke=Scotty+Cameron&modell=Newport+2&type=putter&tilstand=3&pris=1500").get_data(as_text=True)
    assert "Forventet salgspris" in html
    assert "Kjøp" in html
    assert "egne salg" in html or "eget salg" in html


def test_market_prices_page_says_asking_prices(client, filled):
    html = client.get("/markedspriser").get_data(as_text=True)
    assert "utlagte priser, ikke salgspriser" in html
    assert "Newport 2" in html


def test_add_search_validates_and_saves(client, conn):
    client.post("/sok/ny", data={"url": "https://www.google.com"})
    assert conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0] == 0
    client.post("/sok/ny", data={"url": "https://www.finn.no/recommerce/forsale/search?q=scotty+cameron&price_to=3000",
                                 "default_type": "putter"})
    row = conn.execute("SELECT * FROM searches").fetchone()
    assert row["name"] == "Scotty cameron (maks 3 000 kr)"
    assert row["default_type"] == "putter"
    assert "sort=PUBLISHED_DESC" in row["url"]


def test_scraper_toggle(client, conn):
    client.post("/scraper/av")
    assert get_settings(conn)["scraper_enabled"] == 0
    conn.execute("UPDATE settings SET value = 'Blokkert' WHERE key = 'scraper_error'")
    conn.commit()
    assert "Scraperen har stoppet" in client.get("/").get_data(as_text=True)
    client.post("/scraper/pa")
    settings = get_settings(conn)
    assert settings["scraper_enabled"] == 1 and settings["scraper_error"] == ""


def test_settings_are_saved_and_limited(client, conn):
    client.post("/innstillinger", data={"min_profit_pct": "25", "min_profit_kr": "400",
                                        "rule_mode": "both", "scrape_interval_min": "2",
                                        "budget_kr": "15000"})
    settings = get_settings(conn)
    assert settings["min_profit_pct"] == 25.0
    assert settings["min_profit_kr"] == 400
    assert settings["rule_mode"] == "both"
    assert settings["scrape_interval_min"] == 15  # minst 15 minutter
    assert settings["budget_kr"] == 15000


def test_other_websites_cannot_post(client, conn):
    response = client.post("/scraper/av", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert get_settings(conn)["scraper_enabled"] == 1


def test_backup_download(client, filled):
    response = client.get("/innstillinger/sikkerhetskopi")
    assert response.status_code == 200
    assert response.data[:15] == b"SQLite format 3"


def test_many_finds_show_several_pages(client, conn):
    # Mer enn 60 annonser gir sideknapper. Dette krasjet i første versjon.
    for i in range(130):
        add_listing(conn, 700000 + i, f"Scotty Cameron Newport 2 nr {i}", 2000 + i,
                    "Scotty Cameron", "Newport 2", "putter")
    first = client.get("/funn")
    assert first.status_code == 200
    html = first.get_data(as_text=True)
    assert "Side 1 av 3" in html
    assert 'aria-current="page"' in html  # menyen markerer fortsatt riktig side
    second = client.get("/funn?side=2")
    assert second.status_code == 200
    assert "Side 2 av 3" in second.get_data(as_text=True)


def test_errors_show_a_friendly_page_and_are_logged(app, db_path, monkeypatch):
    from pathlib import Path

    from golflager import views

    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False

    def broken(*args, **kwargs):
        raise RuntimeError("testfeil")

    monkeypatch.setattr(views.stats, "dashboard", broken)
    response = app.test_client().get("/")
    assert response.status_code == 500
    html = response.get_data(as_text=True)
    assert "Noe gikk galt" in html and "testfeil" in html
    log_file = Path(db_path).parent / "feilsøking" / "feillogg.txt"
    assert "RuntimeError: testfeil" in log_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("text, expected", [
    ("2500", 2500), ("2 500", 2500), ("2 500 kr", 2500), ("2.500", 2500),
    ("1500,50", 1501), ("1500.50", 1501), ("2500,-", 2500), ("", None), ("abc", None),
])
def test_parse_int_understands_norwegian_numbers(text, expected):
    from golflager.views import parse_int
    assert parse_int(text) == expected


def test_condition_can_be_set_on_a_find(client, filled, conn):
    listing_id = conn.execute("SELECT id FROM listings WHERE finn_id = '200'").fetchone()[0]
    html = client.get("/funn").get_data(as_text=True)
    assert "Tilstand ukjent" in html
    client.post(f"/funn/{listing_id}/rett", data={"brand": "Ping", "model": "Anser",
                                                 "type": "putter", "condition": "1"})
    assert conn.execute("SELECT condition FROM listings WHERE id = ?",
                        (listing_id,)).fetchone()[0] == 1
    assert "1 – Slitt" in client.get("/funn").get_data(as_text=True)
    client.post(f"/funn/{listing_id}/kjopt")
    item = conn.execute("SELECT condition FROM inventory ORDER BY id DESC LIMIT 1").fetchone()
    assert item[0] == 1
    client.post(f"/funn/{listing_id}/rett", data={"brand": "Ping", "model": "Anser",
                                                 "type": "putter", "condition": ""})
    assert conn.execute("SELECT condition FROM listings WHERE id = ?",
                        (listing_id,)).fetchone()[0] is None


def test_price_check_from_find_uses_its_condition(client, filled, conn):
    listing_id = conn.execute("SELECT id FROM listings WHERE finn_id = '200'").fetchone()[0]
    html = client.get(f"/prissjekk?funn={listing_id}").get_data(as_text=True)
    assert '<option value="" selected>Vet ikke</option>' in html


def test_old_database_gets_condition_column(tmp_path):
    import sqlite3

    from golflager import create_app

    path = tmp_path / "gammel.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE listings (id INTEGER PRIMARY KEY AUTOINCREMENT, finn_id TEXT NOT NULL UNIQUE,
            search_id INTEGER, title TEXT NOT NULL, price INTEGER, location TEXT NOT NULL DEFAULT '',
            published_at TEXT, url TEXT NOT NULL, image_url TEXT NOT NULL DEFAULT '',
            brand TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'annet', status TEXT NOT NULL DEFAULT 'ny',
            first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, inventory_id INTEGER);
        INSERT INTO listings (finn_id, title, url, first_seen_at, last_seen_at)
            VALUES ('1', 'Scotty Cameron oppripet', 'u', '2026-09-01', '2026-09-01');
    """)
    old.commit()
    old.close()
    app = create_app(str(path), start_scraper=False)
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT condition FROM listings").fetchone()[0] == 1
    assert app.test_client().get("/funn").status_code == 200


def test_shutdown_button(app, client):
    calls = []
    assert "Kjører fortsatt".lower() in client.post("/avslutt").get_data(as_text=True).lower()
    app.config["SHUTDOWN"] = lambda: calls.append(True)
    html = client.post("/avslutt").get_data(as_text=True)
    assert "Golflager er slått av" in html
    assert calls == [True]
    assert "Slå av Golflager" in client.get("/innstillinger").get_data(as_text=True)


@pytest.fixture
def mixed(conn):
    rows = [
        (800001, "Scotty Cameron Newport 2", 2500, "Scotty Cameron", "Newport 2", "putter"),
        (800002, "Scotty Cameron Phantom X", 3000, "Scotty Cameron", "Phantom X", "putter"),
        (800003, "Ping Anser putter", 900, "Ping", "Anser", "putter"),
        (800004, "Ping G425 driver", 1900, "Ping", "G425", "driver"),
        (800005, "Titleist TSR3 driver", 3100, "Titleist", "TSR3", "driver"),
        (800006, "Golfbag", 500, "", "", "bag"),
    ]
    for finn_id, title, price, brand, model, type_ in rows:
        add_listing(conn, finn_id, title, price, brand, model, type_)
    return conn


def test_finds_can_be_filtered_by_type_and_brand(client, mixed):
    html = client.get("/funn").get_data(as_text=True)
    assert "Putter <span class=\"count\">3</span>" in html
    assert "Scotty Cameron <span class=\"count\">2</span>" in html
    assert "Ukjent merke <span class=\"count\">1</span>" in html

    html = client.get("/funn?type=putter").get_data(as_text=True)
    assert html.count('class="find find--') == 3
    assert "Titleist TSR3" not in html
    # Merkene telles innenfor valgt type
    assert "Ping <span class=\"count\">1</span>" in html

    html = client.get("/funn?type=putter&merke=Scotty+Cameron").get_data(as_text=True)
    assert html.count('class="find find--') == 2
    assert "Vis alle typer og merker" in html
    # Stavemåten i adressen spiller ingen rolle
    html = client.get("/funn?merke=scotty%20cameron").get_data(as_text=True)
    assert html.count('class="find find--') == 2

    html = client.get("/funn?merke=Ukjent+merke").get_data(as_text=True)
    assert html.count('class="find find--') == 1 and "Golfbag" in html

    html = client.get("/funn?type=wedge").get_data(as_text=True)
    assert "Ingen annonser i denne kategorien" in html


def test_category_links_keep_other_choices(client, mixed):
    html = client.get("/funn?vis=ny&farge=gul&type=putter").get_data(as_text=True)
    assert 'href="/funn?vis=ny&amp;farge=gul&amp;type=putter&amp;merke=Ping"' in html
    assert 'href="/funn?vis=ny&amp;type=putter"' in html  # «Alle» i fargevalget beholder typen


def test_inventory_and_market_have_categories(client, filled):
    html = client.get("/lager?type=driver").get_data(as_text=True)
    assert "Ping G425" in html and "Scotty Cameron Newport 2" not in html
    html = client.get("/lager?merke=Scotty+Cameron").get_data(as_text=True)
    assert "Ping G425" not in html and "Newport 2" in html
    html = client.get("/markedspriser?merke=Ping").get_data(as_text=True)
    assert "Anser" in html and "Newport 2" not in html
    html = client.get("/markedspriser?type=putter&gruppe=merke").get_data(as_text=True)
    assert "Scotty Cameron" in html


def test_overview_links_to_categories(client, filled):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/lager?status=solgt&amp;type=putter"' in html
    assert 'href="/lager?status=solgt&amp;merke=Scotty+Cameron"' in html
