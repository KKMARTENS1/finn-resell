from datetime import datetime

from conftest import fixture_text

from golflager.finn_parser import (ads_from_embedded, decode_turbo_stream, looks_blocked,
                                   parse_search_page)

BASE = "https://www.finn.no/recommerce/forsale/search?q=scotty"


def test_turbo_stream_page_is_read_from_embedded_data():
    result = parse_search_page(fixture_text("finn_turbo_stream.html"), BASE)
    assert result.source == "data"
    ids = [ad.finn_id for ad in result.ads]
    # Bare trefflisten ("docs"), ikke anbefalinger fra andre steder på siden
    assert ids == ["412345671", "412345672", "412345673", "412345674"]
    first = result.ads[0]
    assert first.title == 'Scotty Cameron Newport 2 putter 34"'
    assert first.price == 2500
    assert first.location == "Oslo"
    assert first.url == "https://www.finn.no/recommerce/forsale/item/412345671"
    assert first.image_url.startswith("https://images.finncdn.no/")
    assert isinstance(first.published_at, datetime)
    assert result.ads[2].trade_type == "Ønskes kjøpt"


def test_turbo_stream_resolves_promises_and_special_values():
    # Samme oppbygning som turbo-stream lager: promise-id er indeksen til promise-verdien,
    # og den utsatte biten fortsetter nummereringen der første linje slapp.
    text = (
        '[{"_1":2,"_3":4,"_5":-5,"_6":-4},"a",{"_7":8},"later",["P",4],"nothing","zero",'
        '"heading","Hei"]\n'
        'P4:[[10],{"_7":11},"Utsatt"]\n'
    )
    root = decode_turbo_stream(text)[0]
    assert root["a"] == {"heading": "Hei"}
    assert root["nothing"] is None
    assert root["zero"] == 0
    assert root["later"] == [{"heading": "Utsatt"}]


def test_html_cards_are_used_when_there_is_no_embedded_data():
    result = parse_search_page(fixture_text("finn_html_kort.html"), BASE)
    assert result.source == "html"
    ads = {ad.finn_id: ad for ad in result.ads}
    assert set(ads) == {"412300001", "412300002", "412300003"}
    putter = ads["412300001"]
    assert putter.title == 'Ping Anser 2 putter, 35"'
    assert putter.price == 1800
    assert putter.location == "Stavanger"
    assert putter.url == "https://www.finn.no/recommerce/forsale/item/412300001"
    assert putter.image_url.endswith("001_123.jpg")
    assert putter.published_at is not None  # «3 t.» betyr for tre timer siden
    driver = ads["412300002"]
    assert driver.price == 4500
    assert driver.location == "Oslo"
    assert driver.image_url.endswith("002_456.jpg")
    assert ads["412300003"].price == 0  # «Gis bort»


def test_remix_context_docs_are_preferred():
    result = parse_search_page(fixture_text("finn_json_ld.html"), BASE)
    assert [ad.finn_id for ad in result.ads] == ["413000003"]
    ad = result.ads[0]
    assert ad.title == "Mizuno JPX 923 jernsett 5-PW"
    assert ad.price == 5200
    assert ad.location == "Tromsø"


def test_json_ld_products_are_understood():
    data = {"itemListElement": [{"item": {
        "@type": "Product", "name": "Odyssey White Hot OG #7 putter",
        "url": "https://www.finn.no/recommerce/forsale/item/413000001",
        "offers": {"price": "1200"}}}]}
    ads = ads_from_embedded([data], BASE)
    assert len(ads) == 1
    assert ads[0].finn_id == "413000001"
    assert ads[0].price == 1200


def test_things_that_are_not_ads_are_ignored():
    data = {"filters": [{"id": "golf", "title": "Golf"}, {"id": 12, "name": "Oslo"}],
            "user": {"id": 123456789, "name": "Ola"}}
    assert ads_from_embedded([data], BASE) == []


def test_captcha_page_is_detected():
    html = fixture_text("finn_captcha.html")
    assert looks_blocked(html)
    assert parse_search_page(html, BASE).ads == []
    assert not looks_blocked(fixture_text("finn_html_kort.html"))
