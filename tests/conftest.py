from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from golflager import create_app  # noqa: E402
from golflager.db import connect, now_str  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "golflager.db"
    create_app(str(path), start_scraper=False)  # lager tabellene
    return str(path)


@pytest.fixture
def conn(db_path):
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def app(db_path):
    application = create_app(db_path, start_scraper=False)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def add_item(conn, **fields):
    now = now_str()
    item = {
        "brand": "Scotty Cameron", "model": "Newport 2", "type": "putter", "condition": 3,
        "purchase_price": 2000, "purchase_date": "2026-01-10", "status": "kjopt",
        "cost_grip": 0, "cost_shipping": 0, "cost_cleaning": 0, "cost_other": 0,
        "created_at": now, "updated_at": now,
    }
    item.update(fields)
    columns = ", ".join(item)
    marks = ", ".join("?" for _ in item)
    cursor = conn.execute(f"INSERT INTO inventory ({columns}) VALUES ({marks})", list(item.values()))
    conn.commit()
    return cursor.lastrowid


def add_listing(conn, finn_id, title, price, brand="", model="", type_="annet", status="ny",
                seen=None):
    seen = seen or now_str()
    cursor = conn.execute(
        """INSERT INTO listings (finn_id, title, price, url, brand, model, type, status,
               first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (str(finn_id), title, price, f"https://www.finn.no/recommerce/forsale/item/{finn_id}",
         brand, model, type_, status, seen, seen),
    )
    conn.commit()
    return cursor.lastrowid


def add_search(conn, url="https://www.finn.no/recommerce/forsale/search?q=scotty&sort=PUBLISHED_DESC",
               name="Scotty", default_brand="", default_type=""):
    cursor = conn.execute(
        """INSERT INTO searches (name, url, default_brand, default_type, active, created_at)
           VALUES (?, ?, ?, ?, 1, ?)""",
        (name, url, default_brand, default_type, now_str()),
    )
    conn.commit()
    return cursor.lastrowid
