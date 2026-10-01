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
    assert "Typisk utlagt pris er 3 000 kr. Vi regner med at du får 90 % av det." in r.basis


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
    assert r.color == "gra"
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
    # Et grovt anslag blir grått, aldri «Kanskje», selv om tallene ser bra ut
    assert r.confidence == "grov" and r.color == "gra" and r.label == "Usikker"
    assert "bare andre puttere fra Scotty Cameron" in r.reason


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
    assert any("3 650 kr bundet i lager, som er over budsjettet ditt på 3 000 kr" in note
               for note in r.notes)


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
    assert r.color == "gul" and r.label == "Sjekk nøye"
    assert "Uvanlig billig: vanlig pris er rundt 3 000 kr" in r.reason
    assert "en enklere utgave" in r.reason
    # Tilstand som bare er lest ut av tittelen («pent brukt»), fjerner ikke advarselen
    r = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1200,
              condition=4, condition_from_title=True)
    assert r.suspicious and r.color == "gul"
    # Når du har sett bildene og satt tilstanden, er det ikke lenger mistenkelig
    r = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=1200,
              condition=3)
    assert not r.suspicious and r.color == "gronn"


def test_similar_model_is_never_green(conn):
    for i in range(5):
        add_listing(conn, 9300 + i, "TaylorMade Stealth 2 Plus driver", 4000, "TaylorMade",
                    "Stealth 2 Plus", "driver")
    r = check(conn, brand="TaylorMade", model="Stealth", type_key="driver", price=2200)
    assert r.meets_rule and not r.suspicious
    assert r.confidence == "lav" and r.color == "gul"
    assert "ikke helt samme modell" in r.reason


def test_parts_are_compared_with_parts_only_and_never_green(conn):
    for i in range(5):
        add_listing(conn, 9400 + i, "TaylorMade Stealth driver", 3500, "TaylorMade", "Stealth",
                    "driver")
    # Et hode sammenlignes ikke med hele drivere
    r = check(conn, brand="TaylorMade", model="Stealth", type_key="deler", price=1200)
    assert r.expected_sale is None
    for i in range(5):
        add_listing(conn, 9500 + i, "TaylorMade Stealth driver hode", 1500, "TaylorMade",
                    "Stealth", "deler")
    r = check(conn, brand="TaylorMade", model="Stealth", type_key="deler", price=600)
    assert r.expected_sale == 1350 and r.color == "gul"


def test_balls_and_accessories_are_never_rated(conn):
    r = check(conn, brand="Titleist", model="Pro V1", type_key="tilbehor", price=125)
    assert r.color == "gra" and "vurderer ikke tilbehør" in r.reason
    for i in range(5):
        add_listing(conn, 9500 + i, "Titleist Pro V1 golfballer 24 stk", 600, "Titleist",
                    "Pro V1", "tilbehor")
    r = check(conn, brand="Titleist", model="Pro V1", type_key="tilbehor", price=125)
    assert r.color == "gra" and r.label == "Usikker"
    assert "vurderer ikke tilbehør" in r.reason
    # Baller sammenlignes aldri med køller
    for i in range(5):
        add_listing(conn, 9600 + i, "Titleist TSi2 hybrid", 1500, "Titleist", "TSi2", "hybrid")
    r = check(conn, brand="Titleist", model="Pro V1", type_key="tilbehor", price=125)
    assert all(c.price == 600 for c in r.comparables)


def test_guessed_type_is_never_green(conn):
    for i in range(5):
        add_listing(conn, 9700 + i, "Ping G430 Max driver", 4000, "Ping", "G430 Max", "driver")
    sure = check(conn, brand="Ping", model="G430 Max", type_key="driver", price=2000,
                 title="Ping G430 Max driver")
    assert sure.color == "gronn"
    guessed = check(conn, brand="Ping", model="G430 Max", type_key="driver", price=2000,
                    title="Ping G430 Max", type_known=False)
    assert guessed.color == "gul"
    assert "gjettet ut fra søket" in guessed.reason


def test_junior_ladies_and_left_handed_are_compared_with_their_own_kind(conn):
    for i in range(5):
        add_listing(conn, 9800 + i, "Callaway Rogue driver", 2500, "Callaway", "Rogue", "driver")
    junior = check(conn, brand="Callaway", model="Rogue", type_key="driver", price=600,
                   title="Callaway Rogue junior driver")
    assert junior.expected_sale is None and junior.color == "gra"
    assert "for juniorer" in junior.reason

    for i in range(3):
        add_listing(conn, 9900 + i, "Callaway Rogue driver venstre", 1500, "Callaway", "Rogue",
                    "driver")
    lefty = check(conn, brand="Callaway", model="Rogue", type_key="driver", price=600,
                  title="Callaway Rogue driver LH")
    assert {c.price for c in lefty.comparables} == {1500}
    assert any("venstrehendte" in note for note in lefty.notes)
    # Vanlige køller sammenlignes ikke med venstrehendte
    normal = check(conn, brand="Callaway", model="Rogue", type_key="driver", price=600,
                   title="Callaway Rogue driver")
    assert {c.price for c in normal.comparables} == {2500}

    # Heller ikke dine egne salg av voksenkøller brukes for en juniorkølle
    add_item(conn, brand="Callaway", model="Rogue", type="driver", status="solgt",
             sale_price=2400, sale_date="2026-09-01")
    junior = check(conn, brand="Callaway", model="Rogue", type_key="driver", price=600,
                   title="Callaway Rogue junior driver")
    assert junior.expected_sale is None


def test_wide_price_spread_uses_the_low_end(conn):
    # Vanlige Newport 2 og dyre utgaver med samme modellnavn i tittelen
    for i, price in enumerate([3000, 3200, 3500, 9000, 12000, 15000]):
        add_listing(conn, 9950 + i, "Scotty Cameron Newport 2", price, "Scotty Cameron",
                    "Newport 2", "putter")
    r = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter", price=2000)
    assert r.typical_price == 3275  # nedre kvartil, ikke midtverdien 6250
    assert r.expected_sale == round(3275 * 0.9)
    assert r.confidence == "lav" and r.color != "gronn"
    assert "Prisene spriker mye (fra 3 000 til 15 000 kr)" in r.basis
    assert "spriker mye" in r.reason


def test_two_very_different_prices_use_the_lowest(conn):
    for i, price in enumerate([3000, 15000]):
        add_listing(conn, 9960 + i, "Bettinardi Queen B", price, "Bettinardi", "Queen B", "putter")
    r = check(conn, brand="Bettinardi", model="Queen B", type_key="putter", price=1500)
    assert r.typical_price == 3000


def test_tour_and_collector_putters_are_kept_apart(conn):
    for i in range(3):
        add_listing(conn, 9970 + i, "Scotty Cameron Newport 2 Circle T", 20000, "Scotty Cameron",
                    "Newport 2", "putter")
        add_listing(conn, 9980 + i, "Scotty Cameron Newport 2", 3000, "Scotty Cameron",
                    "Newport 2", "putter")
    normal = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter",
                   price=1800, title="Scotty Cameron Newport 2 putter")
    assert {c.price for c in normal.comparables} == {3000}
    tour = check(conn, brand="Scotty Cameron", model="Newport 2", type_key="putter",
                 price=12000, title="Scotty Cameron Newport 2 Circle T tour only")
    assert {c.price for c in tour.comparables} == {20000}
    assert any("tour- eller samlerutgave" in note for note in tour.notes)
