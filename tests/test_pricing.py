from conftest import add_item, add_listing

from golflager.db import get_settings, set_setting
from golflager.pricing import PriceData


def check(conn, **kwargs):
    return PriceData(conn, get_settings(conn)).check(**kwargs)


def test_own_sales_are_used_first(conn):
    add_item(conn, status="solgt", purchase_price=1500, sale_price=3000, sale_date="2026-03-01",
             condition=3, cost_grip=100)
    add_item(conn, status="solgt", purchase_price=1600, sale_price=3400, sale_date="2026-04-01",
             condition=3, cost_grip=100)
    # Markedet sier noe helt annet, men egne salg går foran
    for i in range(5):
        add_listing(conn, 9000 + i, "Scotty Cameron Newport 2", 9000, "Scotty Cameron",
                    "Newport 2", "putter")
    r = check(conn, brand="scotty cameron", model="Newport2", type_key="putter", price=2000,
              condition=3)
    assert r.source == "salg"
    assert r.expected_sale == 3200  # median av 3000 og 3400
    assert r.extra_costs == 100  # snittet av egne ekstrakostnader for putter
    assert r.profit == 3200 - 2000 - 100
    assert r.meets_rule
    assert r.color == "gronn"
    assert r.decision == "Kjøp"


def test_condition_adjusts_own_sales(conn):
    add_item(conn, status="solgt", sale_price=3000, sale_date="2026-03-01", condition=3)
    r = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1000,
              condition=5)
    assert r.expected_sale == 3450  # «Som ny» er verdt 115 % av «God»


def test_market_prices_with_sale_factor(conn):
    for i, price in enumerate([2800, 3000, 3200]):
        add_listing(conn, 1000 + i, f"Ping Anser {i}", price, "Ping", "Anser", "putter")
    r = check(conn, brand="Ping", model="Anser", type_key="putter", price=1500)
    assert r.source == "marked"
    assert r.expected_sale == 2700  # 90 % av median 3000
    assert r.extra_costs == 150  # standard
    assert r.profit == 2700 - 1500 - 150
    assert r.color == "gronn"
    assert "utlagt pris" in r.basis


def test_few_market_prices_give_yellow(conn):
    add_listing(conn, 2001, "Ping Anser", 3000, "Ping", "Anser", "putter")
    r = check(conn, brand="Ping", model="Anser", type_key="putter", price=1000)
    assert r.meets_rule
    assert r.confidence == "lav"
    assert r.color == "gul"
    assert r.decision == "Kjøp"


def test_rule_either_and_both(conn):
    for i in range(3):
        add_listing(conn, 3000 + i, "Cobra", 1000, "Cobra", "Aerojet", "driver")
    # Forventet 900, kjøpspris 500 + 150 ekstra = 650 -> fortjeneste 250 (38 %)
    r = check(conn, brand="Cobra", model="Aerojet", type_key="driver", price=500)
    assert r.profit == 250
    assert r.meets_rule  # 38 % holder når én av reglene er nok
    set_setting(conn, "rule_mode", "both")
    r = check(conn, brand="Cobra", model="Aerojet", type_key="driver", price=500)
    assert not r.meets_rule  # 250 kr er under 500 kr
    assert r.decision == "La være"
    assert r.color == "gul"  # men i nærheten


def test_loss_is_red_and_max_price_is_given(conn):
    for i in range(3):
        add_listing(conn, 4000 + i, "Callaway Paradym", 2000, "Callaway", "Paradym", "driver")
    r = check(conn, brand="Callaway", model="Paradym", type_key="driver", price=2500)
    assert r.profit < 0
    assert r.color == "rod"
    assert r.decision == "La være"
    # Forventet 1800, ekstra 150. 30 %: 1800/1.3 - 150 = 1234 -> 1230. 500 kr: 1150. Høyeste: 1230
    assert r.max_price == 1230


def test_no_data_and_no_price(conn):
    r = check(conn, brand="Ukjent", model="X", type_key="putter", price=1000)
    assert r.expected_sale is None
    assert r.color == "gul"
    assert r.label == "Ingen data"
    add_listing(conn, 5000, "Ping Anser", 3000, "Ping", "Anser", "putter")
    r = check(conn, brand="Ping", model="Anser", type_key="putter", price=None)
    assert r.label == "Ukjent pris"


def test_similar_and_broad_matches(conn):
    for i in range(3):
        add_listing(conn, 6000 + i, "x", 4000, "Scotty Cameron", "Special Select Newport 2",
                    "putter")
    r = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1000)
    assert "lignende" in r.basis
    r = check(conn, brand="Scotty Cameron", model="Futura", type_key="putter", price=1000)
    assert "samme merke og type" in r.basis
    assert r.confidence == "lav"


def test_listing_is_not_compared_with_itself(conn):
    listing_id = add_listing(conn, 7000, "Ping Anser", 900, "Ping", "Anser", "putter")
    r = check(conn, brand="Ping", model="Anser", type_key="putter", price=900,
              exclude_listing_id=listing_id)
    assert r.expected_sale is None


def test_budget_note(conn):
    set_setting(conn, "budget_kr", 3000)
    add_item(conn, status="kjopt", purchase_price=2500)
    for i in range(3):
        add_listing(conn, 8000 + i, "Ping Anser", 3000, "Ping", "Anser", "putter")
    r = check(conn, brand="Ping", model="Anser", type_key="putter", price=1000)
    assert any("over budsjettet" in note for note in r.notes)


def test_worn_listing_is_valued_lower(conn):
    for i in range(3):
        add_listing(conn, 9100 + i, "Scotty Cameron Newport 2", 3000, "Scotty Cameron",
                    "Newport 2", "putter")
    good = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1600,
                 condition=3)
    worn = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1600,
                 condition=1)
    assert good.expected_sale == 2700 and good.color == "gronn"
    assert worn.expected_sale == 1620  # 60 % av 2700
    assert worn.color == "rod" and worn.decision == "La være"


def test_suspiciously_cheap_with_unknown_condition_is_yellow(conn):
    for i in range(3):
        add_listing(conn, 9200 + i, "Scotty Cameron Newport 2", 3000, "Scotty Cameron",
                    "Newport 2", "putter")
    r = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1200)
    assert r.meets_rule and r.suspicious
    assert r.color == "gul" and r.label == "Sjekk tilstand"
    assert "Uvanlig billig" in r.reason
    # Når du har sett bildene og satt tilstanden, er det ikke lenger mistenkelig
    r = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1200,
              condition=3)
    assert not r.suspicious and r.color == "gronn"
