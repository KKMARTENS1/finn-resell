import pytest

from golflager.classify import (classify, detect_condition, detect_variant, is_wanted_ad,
                                normalize, title_type)


@pytest.mark.parametrize(
    "title, expected",
    [
        ('Scotty Cameron Newport 2 putter 34"', ("Scotty Cameron", "Newport 2", "putter")),
        ("Titleist Scotty Cameron Special Select Newport 2.5", ("Scotty Cameron", "Special Select Newport 2.5", "putter")),
        ("Selger Scotty Cameron Phantom X 5.5, pent brukt", ("Scotty Cameron", "Phantom X 5.5", "putter")),
        ("Ping G425 Max driver 10.5 stiff", ("Ping", "G425 Max", "driver")),
        ("TaylorMade Stealth 2 driver", ("TaylorMade", "Stealth 2", "driver")),
        ("Titleist T100 jernsett 4-PW", ("Titleist", "T100", "jernsett")),
        ("Mizuno JPX 923 Hot Metal 5-PW", ("Mizuno", "JPX 923 Hot Metal", "jernsett")),
        ("Titleist Vokey SM9 56 grader", ("Titleist", "Vokey SM9", "wedge")),
        ("Vokey SM8 52.08", ("Titleist", "Vokey SM8", "wedge")),
        ("Odyssey White Hot OG #7 putter", ("Odyssey", "White Hot OG #7", "putter")),
        ("Sun Mountain C-130 vognbag", ("Sun Mountain", "C-130", "bag")),
        ("Scotty Cameron headcover putter", ("Scotty Cameron", "", "deler")),
        ("Scotty Cameron putter med headcover", ("Scotty Cameron", "", "putter")),
        ("Callaway Rogue fairway 3", ("Callaway", "Rogue", "fairway")),
        ("Titleist 7-jern T200", ("Titleist", "", "annet")),
    ],
)
def test_classify_titles(title, expected):
    assert classify(title) == expected


def test_defaults_from_search_are_used_when_title_is_vague():
    assert classify("Newport 2, 35 tommer", "Scotty Cameron", "putter") == (
        "Scotty Cameron", "Newport 2", "putter")
    # Tydelig type i tittelen vinner over standardtypen
    assert classify("Scotty Cameron headcover", "", "putter")[2] == "deler"


def test_normalize_makes_spellings_match():
    assert normalize("Newport 2") == normalize("newport2") == "newport2"
    assert normalize("SM 9") == normalize("SM9")


def test_wanted_ads_are_detected():
    assert is_wanted_ad("Ønskes kjøpt: Scotty Cameron")
    assert is_wanted_ad("KJØPES - Ping putter")
    assert not is_wanted_ad("Scotty Cameron, ønskes solgt raskt")


@pytest.mark.parametrize("title, expected", [
    ("Scotty Cameron Newport 2 oppripet", 1),
    ("Callaway driver, knekt skaft", 1),
    ("Driver med bulk i hodet", 1),
    ("Vokey SM9 mye brukt", 2),
    ("Ping Anser putter, slitt grep", 2),
    ("Putter med brukspreg", 2),
    ("Odyssey putter, noen små riper", 3),
    ("Titleist TSR3 pent brukt", 4),
    ("Ping G425 ingen riper", 4),
    ("Scotty Cameron som ny", 5),
    ("Mizuno jernsett, strøken stand", 5),
    ("Scotty Cameron Newport 2", None),
    ("Titleist T100 rustfritt stål", None),
])
def test_condition_from_title(title, expected):
    assert detect_condition(title) == expected


@pytest.mark.parametrize("title, expected", [
    # Deler: hoder, skaft, headcovers og grep sammenlignes ikke med hele køller
    ("TaylorMade Stealth driver hode", ("TaylorMade", "Stealth", "deler")),
    ("Ping G425 Max driverhode 10.5", ("Ping", "G425 Max", "deler")),
    ("Titleist TSR3 driver, kun hode", ("Titleist", "TSR3", "deler")),
    ("Callaway Paradym driver uten skaft", ("Callaway", "Paradym", "deler")),
    ("Fujikura Ventus Blue 6S driverskaft", ("Fujikura", "Ventus Blue 6S", "deler")),
    ("Ventus TR Blue skaft til TaylorMade driver", ("TaylorMade", "", "deler")),
    ("Driver shaft Tensei AV Blue 65 stiff", ("", "", "deler")),
    ("TaylorMade driver headcover", ("TaylorMade", "", "deler")),
    ("Golf Pride grep 13 stk", ("Golf Pride", "", "deler")),
    # Hele køller med skaft, grep eller headcover er fortsatt hele køller
    ("TaylorMade Stealth 2 driver med Ventus skaft", ("TaylorMade", "Stealth 2", "driver")),
    ("Scotty Cameron Newport 2 putter m/headcover", ("Scotty Cameron", "Newport 2", "putter")),
    ("Scotty Cameron putter med SuperStroke grep", ("Scotty Cameron", "", "putter")),
    ("Mizuno JPX 923 jernsett med KBS skaft", ("Mizuno", "JPX 923", "jernsett")),
    ("Jernsett med Dynamic Gold skaft", ("", "", "jernsett")),
    ("Driver med bulk i hodet", ("", "", "driver")),
    # Fairway, hybrid og pakker
    ("TaylorMade Stealth 3 wood", ("TaylorMade", "Stealth", "fairway")),
    ("TaylorMade Stealth 2 Plus 3-wood", ("TaylorMade", "Stealth 2 Plus", "fairway")),
    ("Titleist TSR2 3w", ("Titleist", "TSR2", "fairway")),
    ("Ping G425 hybrid 4", ("Ping", "G425", "hybrid")),
    ("TaylorMade Stealth driver + 3-tre", ("TaylorMade", "Stealth", "annet")),
    ("Ping driver og putter", ("Ping", "", "annet")),
])
def test_parts_bundles_and_wood_types(title, expected):
    assert classify(title) == expected


@pytest.mark.parametrize("title, default_type, expected", [
    ("Titleist Pro V1 golfballer 12 stk", "hybrid", "tilbehor"),
    ("Titleist Pro V1 12 stk", "hybrid", "tilbehor"),
    ("Callaway Chrome Soft 2 dusin", "driver", "tilbehor"),
    ("Lakeballs 50 stk", "hybrid", "tilbehor"),
    ("Motocaddy M1 elektrisk tralle", "", "tilbehor"),
    ("Garmin Approach S62", "driver", "tilbehor"),
    ("FootJoy golfsko str 43", "", "tilbehor"),
    ("Bushnell Tour V5 avstandsmåler", "", "tilbehor"),
    ("Callaway hybrid 4 + 12 baller", "", "hybrid"),
    ("Odyssey 2-Ball putter", "", "putter"),
    ("Odyssey Two Ball", "", "putter"),
    ("Golfsett komplett med bag", "", "annet"),
])
def test_accessories(title, default_type, expected):
    assert classify(title, "", default_type)[2] == expected


def test_title_type_is_none_when_only_the_search_knows():
    assert title_type("Ping G430 Max") is None
    assert title_type("Ping G430 Max driver") == "driver"
    assert title_type("Titleist Pro V1") == "tilbehor"


@pytest.mark.parametrize("title, expected", [
    ("Ping G425 driver", ""),
    ("Ping G425 venstre driver", "venstre"),
    ("Scotty Cameron Newport 2 LH", "venstre"),
    ("Callaway Big Bertha dame driver", "dame"),
    ("Ladies Ping G Le2 driver", "dame"),
    ("US Kids juniorsett", "junior"),
    ("TaylorMade Junior driver venstrehendt", "junior,venstre"),
])
def test_variants(title, expected):
    assert detect_variant(title) == expected
