import pytest

from golflager.classify import classify, detect_condition, is_wanted_ad, normalize


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
        ("Scotty Cameron headcover putter", ("Scotty Cameron", "", "annet")),
        ("Scotty Cameron putter med headcover", ("Scotty Cameron", "", "putter")),
        ("Callaway Rogue fairway 3", ("Callaway", "Rogue", "annet")),
        ("Titleist 7-jern T200", ("Titleist", "", "annet")),
    ],
)
def test_classify_titles(title, expected):
    assert classify(title) == expected


def test_defaults_from_search_are_used_when_title_is_vague():
    assert classify("Newport 2, 35 tommer", "Scotty Cameron", "putter") == (
        "Scotty Cameron", "Newport 2", "putter")
    # Tydelig type i tittelen vinner over standardtypen
    assert classify("Scotty Cameron headcover", "", "putter")[2] == "annet"


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
