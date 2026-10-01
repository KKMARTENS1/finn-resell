"""Faste valg som brukes over hele appen."""
from __future__ import annotations

TYPES = [
    ("driver", "Driver"),
    ("fairway", "Fairwaykølle"),
    ("hybrid", "Hybrid"),
    ("putter", "Putter"),
    ("jernsett", "Jernsett"),
    ("wedge", "Wedge"),
    ("bag", "Bag"),
    ("deler", "Deler"),
    ("annet", "Annet"),
]
TYPE_LABELS = dict(TYPES)

STATUSES = [
    ("vurderes", "Vurderes"),
    ("kjopt", "Kjøpt"),
    ("klargjores", "Klargjøres"),
    ("til_salgs", "Til salgs"),
    ("solgt", "Solgt"),
]
STATUS_LABELS = dict(STATUSES)

# Ting som er betalt for, men ikke solgt ennå. Pengene er "bundet" i disse.
IN_STOCK = ("kjopt", "klargjores", "til_salgs")
# Ting som er betalt for (brukes i "totalt investert").
PAID = ("kjopt", "klargjores", "til_salgs", "solgt")

CONDITIONS = [
    (5, "5 – Som ny"),
    (4, "4 – Meget god"),
    (3, "3 – God"),
    (2, "2 – Brukbar"),
    (1, "1 – Slitt"),
]
CONDITION_LABELS = dict(CONDITIONS)

LISTING_STATUSES = {"ny": "Nye", "skjult": "Skjulte", "borte": "Solgt / borte", "kjopt": "Kjøpt"}

VERDICTS = {
    "gronn": "Kjøp",
    "gul": "Kanskje",
    "rod": "La være",
}
