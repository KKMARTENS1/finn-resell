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


@pytest.fixture
def filled(conn):
    add_search(conn)
    add_item(conn, status="solgt", purchase_price=1500, sale_price=3000,
             purchase_date="2026-02-01", sale_date="2026-02-21", cost_grip=150)
    add_item(conn, brand="Ping", model="G425", type="driver", status="solgt",
             purchase_price=2500, sale_price=2300, purchase_date="2026-03-01",
             sale_date="2026-04-01")
    add_item(conn, brand="Titleist", model="T100", type="jernsett", status="til_salgs",
             purchase_price=6000, listed_price=8000)
    add_item(conn, brand="Odyssey", model="#7", status="vurderes", purchase_price=None,
             purchase_date=None)
    for i, price in enumerate([2800, 3000, 3200]):
        add_listing(conn, 100 + i, f"Scotty Cameron Newport 2 nr {i}", price, "Scotty Cameron",
                    "Newport 2", "putter")
    add_listing(conn, 200, "Ping Anser putter", 900, "Ping", "Anser", "putter")
    return conn


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
