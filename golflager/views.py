"""Sidene i appen."""
from __future__ import annotations

import io
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from flask import (Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, send_file, url_for)

from . import stats, updater
from .classify import normalize
from .constants import (CONDITION_LABELS, CONDITIONS, IN_STOCK, LISTING_STATUSES, STATUS_LABELS,
                        STATUSES, TYPE_LABELS, TYPES, VERDICTS)
from .db import (LIMITS, connect, get_settings, log_event, now_str, set_setting, today_str)
from .pricing import PriceData, rule_text
from .scraper import normalize_search_url, suggest_name

bp = Blueprint("main", __name__)

PAGE_SIZE = 60


# ---------------------------------------------------------------------------
# Felles


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def worker():
    return current_app.extensions["scraper"]


@bp.teardown_app_request
def close_db(_exc: Optional[BaseException]) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@bp.before_app_request
def same_origin_only() -> None:
    """Hindrer andre nettsider i å sende skjemaer til appen din."""
    if request.method == "POST":
        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin and origin != "null" and urlsplit(origin).netloc != request.host:
            abort(403)


@bp.app_context_processor
def inject_common() -> Dict[str, Any]:
    conn = get_db()
    settings = get_settings(conn)
    nav_new = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE status = 'ny' AND gone_at IS NULL AND first_seen_at > ?",
        (settings["last_seen_finds_at"] or "0000",),
    ).fetchone()[0]
    return {
        "settings": settings,
        "nav_new": nav_new,
        "scraper_running": worker().running,
        "TYPES": TYPES,
        "TYPE_LABELS": TYPE_LABELS,
        "STATUSES": STATUSES,
        "STATUS_LABELS": STATUS_LABELS,
        "CONDITIONS": CONDITIONS,
        "CONDITION_LABELS": CONDITION_LABELS,
        "VERDICTS": VERDICTS,
        "rule_text": rule_text(settings),
        "url_with": url_with,
        "days_between": stats.days_between,
        "LISTING_TABS": list(LISTING_STATUSES.items()),
        "app_version": current_app.config.get("VERSION", "0"),
        "update_version": (settings["update_available"]
                           if updater.is_newer(settings["update_available"],
                                               current_app.config.get("VERSION", "0"))
                           else ""),
    }


# ---------------------------------------------------------------------------
# Kategorier (type og merke)

UNKNOWN_BRAND = "Ukjent merke"
MAX_BRAND_CHIPS = 12


def url_with(**changes: Any) -> str:
    """Adressen til siden du er på, med noen valg endret (None fjerner et valg)."""
    args = request.args.to_dict()
    args.pop("side", None)
    for key, value in changes.items():
        if value is None or value == "":
            args.pop(key, None)
        else:
            args[key] = value
    return url_for(request.endpoint, **(request.view_args or {}), **args)


def brand_key(brand: Optional[str]) -> str:
    return normalize(brand or "") or normalize(UNKNOWN_BRAND)


def selected_category() -> Tuple[str, str]:
    """Type og merke fra adressen (?type=putter&merke=Scotty Cameron)."""
    type_key = request.args.get("type", "")
    if type_key not in TYPE_LABELS:
        type_key = ""
    brand = request.args.get("merke", "").strip()
    return type_key, brand_key(brand) if brand else ""


def in_category(type_key: str, brand: Optional[str], selected_type: str,
                selected_brand: str) -> bool:
    return ((not selected_type or type_key == selected_type)
            and (not selected_brand or brand_key(brand) == selected_brand))


def category_facets(rows: List[Any], type_of: Any, brand_of: Any, selected_type: str,
                    selected_brand: str) -> Dict[str, Any]:
    """Knappene i kategoriraden med antall. Typene telles innenfor valgt merke, og omvendt."""
    type_counts: Dict[str, int] = {}
    brand_counts: Dict[str, List[Any]] = {}
    for row in rows:
        type_key, brand = type_of(row), (brand_of(row) or "").strip()
        key = brand_key(brand)
        if not selected_brand or key == selected_brand:
            type_counts[type_key] = type_counts.get(type_key, 0) + 1
        if not selected_type or type_key == selected_type:
            entry = brand_counts.setdefault(key, [0, {}])
            entry[0] += 1
            entry[1][brand or UNKNOWN_BRAND] = entry[1].get(brand or UNKNOWN_BRAND, 0) + 1
    types = [{"key": key, "label": label, "count": type_counts.get(key, 0)}
             for key, label in TYPES if type_counts.get(key) or key == selected_type]
    brands = []
    for key, (count, spellings) in brand_counts.items():
        label = max(spellings, key=lambda name: (spellings[name], name))
        brands.append({"key": key, "label": label, "count": count})
    if selected_brand and selected_brand not in brand_counts:
        brands.append({"key": selected_brand, "label": request.args.get("merke", "").strip(),
                       "count": 0})
    unknown = normalize(UNKNOWN_BRAND)
    brands.sort(key=lambda b: (b["key"] == unknown, -b["count"], b["label"].lower()))
    top = brands[:MAX_BRAND_CHIPS]
    more = brands[MAX_BRAND_CHIPS:]
    chosen = [b for b in more if b["key"] == selected_brand]
    return {
        "type": selected_type,
        "brand": selected_brand,
        "types": types,
        "brands": top + chosen,
        "more_brands": [b for b in more if b["key"] != selected_brand],
        "type_total": sum(type_counts.values()),
        "brand_total": sum(entry[0] for entry in brand_counts.values()),
    }


def parse_int(value: Optional[str]) -> Optional[int]:
    text = (value or "").strip().replace(" ", "").replace(" ", "").lower()
    text = text.replace("kr", "").replace(",-", "")
    if not text:
        return None
    negative = text.startswith(("-", "−"))
    text = text.lstrip("-−")
    # «1500,50» og «1500.50» er desimaler. «2.500» er tusenskille.
    decimal = re.fullmatch(r"(\d+)[.,](\d{1,2})", text)
    if decimal:
        number = int(float(f"{decimal.group(1)}.{decimal.group(2)}") + 0.5)  # vanlig avrunding
    else:
        digits = "".join(ch for ch in text.split(",")[0] if ch.isdigit())
        if not digits:
            return None
        number = int(digits)
    return -number if negative else number


def safe_next(default: str) -> str:
    target = request.form.get("next") or request.args.get("next") or ""
    if target.startswith("/") and not target.startswith("//"):
        return target
    return default


def known_values(conn: sqlite3.Connection, column: str) -> List[str]:
    assert column in ("brand", "model")
    values = set()
    for table in ("inventory", "listings"):
        for row in conn.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} != ''"):
            values.add(row[0])
    return sorted(values, key=str.lower)


def enrich_item(item: Dict[str, Any]) -> Dict[str, Any]:
    item["cost"] = stats.item_cost(item)
    item["profit"] = stats.item_profit(item)
    if item["status"] == "solgt":
        item["days"] = stats.days_between(item["purchase_date"], item["sale_date"])
    elif item["status"] in IN_STOCK:
        item["days"] = stats.days_between(item["purchase_date"], today_str())
    else:
        item["days"] = None
    return item


# ---------------------------------------------------------------------------
# Oversikt


@bp.route("/")
def oversikt():
    conn = get_db()
    settings = get_settings(conn)
    data = stats.dashboard(conn, settings)
    rows = conn.execute(
        "SELECT * FROM listings WHERE status = 'ny' AND gone_at IS NULL "
        "ORDER BY first_seen_at DESC, id DESC LIMIT 200"
    ).fetchall()
    prices = PriceData(conn, settings)
    best = []
    for row in rows:
        check = prices.check(row["brand"], row["model"], row["type"], row["price"],
                             condition=row["condition"], exclude_listing_id=row["id"])
        if check.color == "gronn":
            best.append({"listing": row, "check": check})
        if len(best) >= 4:
            break
    return render_template("oversikt.html", d=data, best=best)


# ---------------------------------------------------------------------------
# Nye funn


FIND_SORTS = [
    ("nyeste", "Nyeste først"),
    ("eldste", "Eldste først"),
    ("pris_lav", "Lavest pris"),
    ("pris_hoy", "Høyest pris"),
    ("fortjeneste", "Størst fortjeneste"),
    ("prosent", "Høyest fortjeneste i %"),
]


def _sort_value(value: Optional[float], descending: bool) -> Tuple[bool, float]:
    """Sorteringsnøkkel der manglende verdier alltid havner sist."""
    if value is None:
        return (True, 0.0)
    return (False, -value if descending else value)


def sort_cards(cards: List[Dict[str, Any]], sort_key: str) -> List[Dict[str, Any]]:
    """Kortene kommer inn med nyeste først."""
    if sort_key == "eldste":
        return list(reversed(cards))
    if sort_key in ("pris_lav", "pris_hoy"):
        return sorted(cards, key=lambda c: _sort_value(c["listing"]["price"],
                                                       sort_key == "pris_hoy"))
    if sort_key == "fortjeneste":
        return sorted(cards, key=lambda c: _sort_value(c["check"].profit, True))
    if sort_key == "prosent":
        return sorted(cards, key=lambda c: _sort_value(c["check"].profit_pct, True))
    return cards


def view_condition(view: str) -> Tuple[str, List[Any]]:
    """SQL-vilkår for fanene i Nye funn. Solgte annonser vises bare under «Solgt / borte»."""
    if view == "borte":
        return "l.gone_at IS NOT NULL AND l.status IN ('ny', 'skjult')", []
    if view == "kjopt":
        return "l.status = 'kjopt'", []
    return "l.status = ? AND l.gone_at IS NULL", [view]


def filtered_finds(conn: sqlite3.Connection, args: Any) -> Dict[str, Any]:
    """Annonsene som passer til valgene på Nye funn (fane, farge, søk, type, merke)."""
    settings = get_settings(conn)
    view = args.get("vis", "ny")
    if view not in LISTING_STATUSES:
        view = "ny"
    color = args.get("farge", "")
    search_filter = parse_int(args.get("sok"))
    sort_key = args.get("sorter", "nyeste")
    if sort_key not in dict(FIND_SORTS):
        sort_key = "nyeste"

    condition, params = view_condition(view)
    query = f"""SELECT l.*, s.name AS search_name FROM listings l
                LEFT JOIN searches s ON s.id = l.search_id WHERE {condition}"""
    if search_filter:
        query += " AND l.search_id = ?"
        params.append(search_filter)
    query += " ORDER BY l.first_seen_at DESC, COALESCE(l.published_at, '') DESC, l.id DESC"
    rows = conn.execute(query, params).fetchall()

    prices = PriceData(conn, settings)
    selected_type, selected_brand = selected_category()
    checked = [{"listing": row, "check": prices.check(
        row["brand"], row["model"], row["type"], row["price"], condition=row["condition"],
        exclude_listing_id=row["id"])} for row in rows]
    facets = category_facets(
        [c for c in checked if not color or c["check"].color == color],
        lambda c: c["listing"]["type"], lambda c: c["listing"]["brand"],
        selected_type, selected_brand)
    counts = {"gronn": 0, "gul": 0, "rod": 0}
    cards = []
    for card in checked:
        listing = card["listing"]
        if not in_category(listing["type"], listing["brand"], selected_type, selected_brand):
            continue
        counts[card["check"].color] += 1
        if color and card["check"].color != color:
            continue
        cards.append(card)
    return {
        "view": view, "color": color, "search_filter": search_filter, "sort": sort_key,
        "cards": sort_cards(cards, sort_key), "counts": counts, "cat": facets,
        "settings": settings,
    }


@bp.route("/funn")
def funn():
    conn = get_db()
    found = filtered_finds(conn, request.args)
    settings, view = found["settings"], found["view"]
    page = max(1, parse_int(request.args.get("side")) or 1)
    total = len(found["cards"])
    cards = found["cards"][(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    previous_seen = settings["last_seen_finds_at"] or "0000"
    if view == "ny":
        set_setting(conn, "last_seen_finds_at", now_str())
        conn.commit()
    searches = conn.execute("SELECT id, name FROM searches ORDER BY name").fetchall()
    tab_counts = {}
    for key in LISTING_STATUSES:
        condition, params = view_condition(key)
        tab_counts[key] = conn.execute(
            f"SELECT COUNT(*) FROM listings l WHERE {condition}", params).fetchone()[0]
    return render_template(
        "funn.html",
        cards=cards,
        counts=found["counts"],
        view=view,
        color=found["color"],
        search_filter=found["search_filter"],
        sort=found["sort"],
        sorts=FIND_SORTS,
        searches=searches,
        previous_seen=previous_seen,
        page=page,
        pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        total=total,
        tab_counts=tab_counts,
        brands=known_values(conn, "brand"),
        cat=found["cat"],
    )


@bp.route("/funn/rydd", methods=["POST"])
def funn_rydd():
    """Skjul eller slett alle annonsene som vises med valgene du har nå."""
    conn = get_db()
    action = request.form.get("handling")
    found = filtered_finds(conn, request.args)
    ids = [card["listing"]["id"] for card in found["cards"]]
    if action == "skjul" and found["view"] == "ny":
        new_status, verb = "skjult", "skjult"
    elif action == "slett" and found["view"] in ("skjult", "borte"):
        new_status, verb = "slettet", "slettet"
    else:
        abort(400)
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        conn.execute(
            f"UPDATE listings SET status = ? WHERE id IN ({', '.join('?' * len(chunk))})",
            [new_status] + chunk,
        )
    log_event(conn, "info", f"{len(ids)} annonser ble {verb} fra Nye funn.")
    conn.commit()
    flash(f"{len(ids)} {'annonse' if len(ids) == 1 else 'annonser'} er {verb}.", "ok")
    return redirect(url_for("main.funn", **request.args.to_dict()))


def _listing_or_404(conn: sqlite3.Connection, listing_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@bp.route("/funn/<int:listing_id>/kjopt", methods=["POST"])
def funn_kjopt(listing_id: int):
    conn = get_db()
    listing = _listing_or_404(conn, listing_id)
    if listing["inventory_id"]:
        exists = conn.execute(
            "SELECT id FROM inventory WHERE id = ?", (listing["inventory_id"],)
        ).fetchone()
        if exists:
            return redirect(url_for("main.lager_endre", item_id=listing["inventory_id"]))
    now = now_str()
    cursor = conn.execute(
        """INSERT INTO inventory (brand, model, type, condition, finn_url, purchase_price,
               purchase_date, status, notes, image_url, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'kjopt', ?, ?, ?, ?)""",
        (listing["brand"], listing["model"], listing["type"], listing["condition"] or 3,
         listing["url"], listing["price"],
         today_str(), f"Finn-annonse: {listing['title']}", listing["image_url"], now, now),
    )
    conn.execute(
        "UPDATE listings SET status = 'kjopt', inventory_id = ? WHERE id = ?",
        (cursor.lastrowid, listing_id),
    )
    conn.commit()
    flash("Lagt i lageret. Sjekk at pris, tilstand og kostnader stemmer.", "ok")
    return redirect(url_for("main.lager_endre", item_id=cursor.lastrowid))


@bp.route("/funn/<int:listing_id>/skjul", methods=["POST"])
def funn_skjul(listing_id: int):
    conn = get_db()
    _listing_or_404(conn, listing_id)
    conn.execute("UPDATE listings SET status = 'skjult' WHERE id = ?", (listing_id,))
    conn.commit()
    return redirect(safe_next(url_for("main.funn")))


@bp.route("/funn/<int:listing_id>/slett", methods=["POST"])
def funn_slett(listing_id: int):
    conn = get_db()
    _listing_or_404(conn, listing_id)
    conn.execute("UPDATE listings SET status = 'slettet' WHERE id = ?", (listing_id,))
    conn.commit()
    return redirect(safe_next(url_for("main.funn")))


@bp.route("/funn/<int:listing_id>/solgt", methods=["POST"])
def funn_solgt(listing_id: int):
    """Merk en annonse som solgt for hånd, og ta vare på hvordan den så ut i søket."""
    from .diagnostics import describe_listing

    conn = get_db()
    listing = _listing_or_404(conn, listing_id)
    conn.execute("UPDATE listings SET gone_at = ?, gone_reason = 'manuell' WHERE id = ?",
                 (now_str(), listing_id))
    try:
        text = describe_listing(conn, listing, current_app.config.get("VERSION", "0"))
    except Exception as exc:  # noqa: BLE001 - feilsøkingen skal aldri stoppe knappen
        text = f"Klarte ikke å lage feilsøkingstekst: {exc}"
    set_setting(conn, "diagnostic_text", text)
    conn.commit()
    flash("Annonsen er flyttet til «Solgt / borte». Vil du hjelpe Golflager å oppdage solgte "
          "annonser selv? Gå til Innstillinger → Feilsøking og send teksten der.", "ok")
    return redirect(safe_next(url_for("main.funn")))


@bp.route("/funn/<int:listing_id>/aktiv", methods=["POST"])
def funn_aktiv(listing_id: int):
    conn = get_db()
    _listing_or_404(conn, listing_id)
    conn.execute("UPDATE listings SET gone_at = NULL, gone_reason = NULL WHERE id = ?",
                 (listing_id,))
    conn.commit()
    flash("Annonsen er flyttet tilbake.", "ok")
    return redirect(safe_next(url_for("main.funn")))


@bp.route("/funn/<int:listing_id>/vis", methods=["POST"])
def funn_vis(listing_id: int):
    conn = get_db()
    _listing_or_404(conn, listing_id)
    conn.execute("UPDATE listings SET status = 'ny' WHERE id = ?", (listing_id,))
    conn.commit()
    flash("Annonsen er flyttet tilbake til nye funn.", "ok")
    return redirect(safe_next(url_for("main.funn")))


@bp.route("/funn/<int:listing_id>/rett", methods=["POST"])
def funn_rett(listing_id: int):
    conn = get_db()
    _listing_or_404(conn, listing_id)
    type_key = request.form.get("type", "annet")
    if type_key not in TYPE_LABELS:
        type_key = "annet"
    condition = parse_int(request.form.get("condition"))
    if condition is not None:
        condition = max(1, min(5, condition))
    conn.execute(
        "UPDATE listings SET brand = ?, model = ?, type = ?, condition = ? WHERE id = ?",
        (request.form.get("brand", "").strip(), request.form.get("model", "").strip(), type_key,
         condition, listing_id),
    )
    conn.commit()
    flash("Annonsen er oppdatert, og prissjekken er regnet ut på nytt.", "ok")
    return redirect(safe_next(url_for("main.funn")))


# ---------------------------------------------------------------------------
# Lager


LAGER_SORTS = [
    ("status", "Status"),
    ("nyeste", "Nyeste først"),
    ("eldste", "Eldste først"),
    ("kostnad", "Høyest kostnad"),
    ("fortjeneste", "Størst fortjeneste"),
    ("dager", "Flest dager"),
    ("merke", "Merke A–Å"),
]
STATUS_ORDER = {"vurderes": 0, "kjopt": 1, "klargjores": 2, "til_salgs": 3, "solgt": 4}


def _item_date(item: Dict[str, Any]) -> int:
    value = item["sale_date"] or item["purchase_date"] or item["created_at"][:10]
    return datetime.fromisoformat(value[:10]).toordinal()


def sort_items(items: List[Dict[str, Any]], sort_key: str) -> List[Dict[str, Any]]:
    if sort_key == "nyeste":
        return sorted(items, key=lambda i: -_item_date(i))
    if sort_key == "eldste":
        return sorted(items, key=_item_date)
    if sort_key == "kostnad":
        return sorted(items, key=lambda i: -i["cost"])
    if sort_key == "fortjeneste":
        return sorted(items, key=lambda i: _sort_value(i["profit"], True))
    if sort_key == "dager":
        return sorted(items, key=lambda i: _sort_value(i["days"], True))
    if sort_key == "merke":
        return sorted(items, key=lambda i: (i["brand"].lower(), i["model"].lower()))
    return sorted(items, key=lambda i: (STATUS_ORDER.get(i["status"], 9), -_item_date(i)))


@bp.route("/lager")
def lager():
    conn = get_db()
    status = request.args.get("status", "")
    selected_type, selected_brand = selected_category()
    text = request.args.get("q", "").strip()
    query = "SELECT * FROM inventory WHERE 1 = 1"
    params: List[Any] = []
    if status == "lager":
        query += " AND status IN (?, ?, ?)"
        params.extend(IN_STOCK)
    elif status in STATUS_LABELS:
        query += " AND status = ?"
        params.append(status)
    if text:
        query += " AND (brand LIKE ? OR model LIKE ? OR notes LIKE ?)"
        params.extend([f"%{text}%"] * 3)
    sort_key = request.args.get("sorter", "status")
    if sort_key not in dict(LAGER_SORTS):
        sort_key = "status"
    all_items = [enrich_item(dict(r)) for r in conn.execute(query, params)]
    facets = category_facets(all_items, lambda i: i["type"], lambda i: i["brand"],
                             selected_type, selected_brand)
    items = [i for i in all_items
             if in_category(i["type"], i["brand"], selected_type, selected_brand)]
    items = sort_items(items, sort_key)
    counts = {key: 0 for key, _ in STATUSES}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM inventory GROUP BY status"):
        counts[row["status"]] = row["n"]
    totals = {
        "cost": sum(i["cost"] for i in items if i["status"] != "vurderes"),
        "listed": sum(i["listed_price"] or 0 for i in items if i["status"] == "til_salgs"),
        "profit": sum(i["profit"] or 0 for i in items if i["profit"] is not None),
    }
    return render_template("lager.html", items=items, status=status, q=text, counts=counts,
                           totals=totals, cat=facets, sort=sort_key, sorts=LAGER_SORTS,
                           filtered=bool(status or text or selected_type or selected_brand))


EMPTY_ITEM = {
    "id": None, "brand": "", "model": "", "type": "putter", "condition": 3, "finn_url": "",
    "purchase_price": None, "purchase_date": "", "cost_grip": 0, "cost_shipping": 0,
    "cost_cleaning": 0, "cost_other": 0, "status": "kjopt", "listed_price": None,
    "sale_price": None, "sale_date": "", "notes": "", "image_url": "",
}


def _item_from_form(form: Any) -> Tuple[Dict[str, Any], List[str]]:
    errors: List[str] = []
    item = {
        "brand": form.get("brand", "").strip(),
        "model": form.get("model", "").strip(),
        "type": form.get("type", "annet"),
        "condition": parse_int(form.get("condition")) or 3,
        "finn_url": form.get("finn_url", "").strip(),
        "purchase_price": parse_int(form.get("purchase_price")),
        "purchase_date": form.get("purchase_date", "").strip() or None,
        "cost_grip": parse_int(form.get("cost_grip")) or 0,
        "cost_shipping": parse_int(form.get("cost_shipping")) or 0,
        "cost_cleaning": parse_int(form.get("cost_cleaning")) or 0,
        "cost_other": parse_int(form.get("cost_other")) or 0,
        "status": form.get("status", "kjopt"),
        "listed_price": parse_int(form.get("listed_price")),
        "sale_price": parse_int(form.get("sale_price")),
        "sale_date": form.get("sale_date", "").strip() or None,
        "notes": form.get("notes", "").strip(),
    }
    if not item["brand"]:
        errors.append("Fyll inn merke.")
    if item["type"] not in TYPE_LABELS:
        item["type"] = "annet"
    if item["status"] not in STATUS_LABELS:
        item["status"] = "kjopt"
    item["condition"] = max(1, min(5, item["condition"]))
    for key, label in (("purchase_price", "Kjøpspris"), ("listed_price", "Utlagt pris"),
                       ("sale_price", "Salgspris"), ("cost_grip", "Grep"),
                       ("cost_shipping", "Frakt"), ("cost_cleaning", "Rengjøring"),
                       ("cost_other", "Andre kostnader")):
        if item[key] is not None and item[key] < 0:
            errors.append(f"{label} kan ikke være negativ.")
    for key, label in (("purchase_date", "Kjøpsdato"), ("sale_date", "Salgsdato")):
        if item[key]:
            try:
                datetime.fromisoformat(item[key])
            except ValueError:
                errors.append(f"{label} er ikke en gyldig dato.")
                item[key] = None
    if item["status"] != "vurderes" and item["purchase_price"] is None:
        errors.append("Fyll inn kjøpspris (skriv 0 hvis du fikk den gratis).")
    if item["status"] != "vurderes" and not item["purchase_date"]:
        item["purchase_date"] = today_str()
    if item["status"] == "solgt":
        if item["sale_price"] is None:
            errors.append("Fyll inn salgspris når tingen er solgt.")
        if not item["sale_date"]:
            item["sale_date"] = today_str()
    if (item["purchase_date"] and item["sale_date"]
            and item["sale_date"] < item["purchase_date"] and item["status"] == "solgt"):
        errors.append("Salgsdatoen kan ikke være før kjøpsdatoen.")
    return item, errors


def _item_price_hint(conn: sqlite3.Connection, item: Dict[str, Any]):
    if not item.get("brand"):
        return None
    prices = PriceData(conn, get_settings(conn))
    check = prices.check(item["brand"], item["model"], item["type"],
                         item.get("purchase_price") or 0, condition=item.get("condition"),
                         exclude_inventory_id=item.get("id"))
    return check if check.expected_sale is not None else None


@bp.route("/lager/ny", methods=["GET", "POST"])
def lager_ny():
    conn = get_db()
    if request.method == "POST":
        item, errors = _item_from_form(request.form)
        if errors:
            for error in errors:
                flash(error, "feil")
            return render_template("lager_skjema.html", item={**EMPTY_ITEM, **item}, hint=None,
                                   brands=known_values(conn, "brand"),
                                   models=known_values(conn, "model"))
        now = now_str()
        columns = list(item.keys()) + ["created_at", "updated_at"]
        cursor = conn.execute(
            f"INSERT INTO inventory ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            list(item.values()) + [now, now],
        )
        conn.commit()
        flash(f"{item['brand']} {item['model']} er lagt til i lageret.".replace("  ", " "), "ok")
        if request.form.get("again"):
            return redirect(url_for("main.lager_ny"))
        return redirect(url_for("main.lager", _anchor=f"vare-{cursor.lastrowid}"))
    item = dict(EMPTY_ITEM)
    item["purchase_date"] = today_str()
    return render_template("lager_skjema.html", item=item, hint=None,
                           brands=known_values(conn, "brand"), models=known_values(conn, "model"))


@bp.route("/lager/<int:item_id>", methods=["GET", "POST"])
def lager_endre(item_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        abort(404)
    if request.method == "POST":
        item, errors = _item_from_form(request.form)
        if errors:
            for error in errors:
                flash(error, "feil")
            merged = {**dict(row), **item}
            return render_template("lager_skjema.html", item=merged,
                                   hint=_item_price_hint(conn, merged),
                                   brands=known_values(conn, "brand"),
                                   models=known_values(conn, "model"))
        assignments = ", ".join(f"{key} = ?" for key in item)
        conn.execute(
            f"UPDATE inventory SET {assignments}, updated_at = ? WHERE id = ?",
            list(item.values()) + [now_str(), item_id],
        )
        conn.commit()
        flash("Endringene er lagret.", "ok")
        return redirect(url_for("main.lager", _anchor=f"vare-{item_id}"))
    item = enrich_item(dict(row))
    return render_template("lager_skjema.html", item=item, hint=_item_price_hint(conn, item),
                           brands=known_values(conn, "brand"), models=known_values(conn, "model"))


@bp.route("/lager/<int:item_id>/slett", methods=["POST"])
def lager_slett(item_id: int):
    conn = get_db()
    row = conn.execute("SELECT brand, model FROM inventory WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        abort(404)
    conn.execute("UPDATE listings SET status = 'ny', inventory_id = NULL WHERE inventory_id = ?",
                 (item_id,))
    conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
    conn.commit()
    flash(f"{row['brand']} {row['model']} er slettet.".replace("  ", " "), "ok")
    return redirect(url_for("main.lager"))


# ---------------------------------------------------------------------------
# Prissjekk


@bp.route("/prissjekk")
def prissjekk():
    conn = get_db()
    settings = get_settings(conn)
    args = request.args
    form = {
        "brand": args.get("merke", "").strip(),
        "model": args.get("modell", "").strip(),
        "type": args.get("type", "putter"),
        # Uten valg er utgangspunktet «God». Tomt valg betyr «Vet ikke».
        "condition": parse_int(args.get("tilstand")) if "tilstand" in args else 3,
        "price": parse_int(args.get("pris")),
        "extras": parse_int(args.get("ekstra")),
    }
    listing = None
    listing_id = parse_int(args.get("funn"))
    if listing_id:
        listing = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if listing is not None and not args.get("merke"):
            form.update(brand=listing["brand"], model=listing["model"], type=listing["type"],
                        price=listing["price"], condition=listing["condition"])
    if form["type"] not in TYPE_LABELS:
        form["type"] = "annet"
    if form["condition"] is not None:
        form["condition"] = max(1, min(5, form["condition"]))
    result = None
    if form["brand"] or form["price"] is not None:
        prices = PriceData(conn, settings)
        result = prices.check(
            form["brand"], form["model"], form["type"], form["price"],
            condition=form["condition"], extra_costs=form["extras"],
            exclude_listing_id=listing["id"] if listing is not None else None,
        )
    return render_template("prissjekk.html", form=form, result=result, listing=listing,
                           brands=known_values(conn, "brand"), models=known_values(conn, "model"))


# ---------------------------------------------------------------------------
# Markedspriser


def percentile(values: List[int], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


MARKET_SORTS = [
    ("antall", "Flest annonser"),
    ("pris_lav", "Lavest typisk pris"),
    ("pris_hoy", "Høyest typisk pris"),
    ("merke", "Merke A–Å"),
]


@bp.route("/markedspriser")
def markedspriser():
    conn = get_db()
    group = request.args.get("gruppe", "modell")
    if group not in ("modell", "merke", "type"):
        group = "modell"
    selected_type, selected_brand = selected_category()
    text = request.args.get("q", "").strip().lower()
    months = parse_int(request.args.get("periode"))
    if months is None:
        months = 12
    query = """SELECT brand, model, type, price, last_seen_at FROM listings
               WHERE price >= 50 AND price <= 500000"""
    params: List[Any] = []
    if months:
        since = (datetime.now() - timedelta(days=30 * months)).isoformat(sep=" ",
                                                                          timespec="seconds")
        query += " AND last_seen_at >= ?"
        params.append(since)
    rows = [dict(r) for r in conn.execute(query, params)]
    if text:
        rows = [r for r in rows if text in f"{r['brand']} {r['model']}".lower()]
    facets = category_facets(rows, lambda r: r["type"], lambda r: r["brand"], selected_type,
                             selected_brand)
    rows = [r for r in rows if in_category(r["type"], r["brand"], selected_type, selected_brand)]

    sold = [dict(r) for r in conn.execute(
        "SELECT brand, model, type, sale_price FROM inventory WHERE status = 'solgt' "
        "AND sale_price IS NOT NULL"
    )]

    def key_for(row: Dict[str, Any]) -> Tuple[str, ...]:
        if group == "modell":
            return (normalize(row["brand"]), normalize(row["model"]), row["type"])
        if group == "merke":
            return (normalize(row["brand"]), row["type"])
        return (row["type"],)

    groups: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for row in rows:
        entry = groups.setdefault(key_for(row), {
            "brand": row["brand"] or "Ukjent merke", "model": row["model"], "type": row["type"],
            "prices": [], "last_seen": "",
        })
        entry["prices"].append(int(row["price"]))
        entry["last_seen"] = max(entry["last_seen"], row["last_seen_at"] or "")
    own: Dict[Tuple[str, ...], List[int]] = {}
    for item in sold:
        own.setdefault(key_for(item), []).append(int(item["sale_price"]))

    table = []
    for key, entry in groups.items():
        prices = entry["prices"]
        table.append({
            **entry,
            "count": len(prices),
            "median": median(prices),
            "low": percentile(prices, 0.25),
            "high": percentile(prices, 0.75),
            "min": min(prices),
            "max": max(prices),
            "own": median(own[key]) if key in own else None,
            "own_count": len(own.get(key, [])),
        })
    sort_key = request.args.get("sorter", "antall")
    if sort_key not in dict(MARKET_SORTS):
        sort_key = "antall"
    by_name = lambda r: (r["brand"].lower(), (r["model"] or "").lower(), r["type"])  # noqa: E731
    if sort_key == "pris_lav":
        table.sort(key=lambda r: (r["median"], by_name(r)))
    elif sort_key == "pris_hoy":
        table.sort(key=lambda r: (-r["median"], by_name(r)))
    elif sort_key == "merke":
        table.sort(key=by_name)
    else:
        table.sort(key=lambda r: (-r["count"], by_name(r)))
    return render_template("markedspriser.html", table=table, group=group,
                           q=request.args.get("q", ""), months=months, total=len(rows),
                           cat=facets, sort=sort_key, sorts=MARKET_SORTS)


# ---------------------------------------------------------------------------
# Finn-søk og scraper


@bp.route("/sok")
def sok():
    conn = get_db()
    searches = conn.execute(
        """SELECT s.*, (SELECT COUNT(*) FROM listings l WHERE l.search_id = s.id) AS total
           FROM searches s ORDER BY s.id"""
    ).fetchall()
    events = conn.execute("SELECT * FROM scrape_log ORDER BY id DESC LIMIT 15").fetchall()
    return render_template("sok.html", searches=searches, events=events)


@bp.route("/sok/ny", methods=["POST"])
def sok_ny():
    conn = get_db()
    try:
        url = normalize_search_url(request.form.get("url", ""))
    except ValueError as exc:
        flash(str(exc), "feil")
        return redirect(url_for("main.sok"))
    exists = conn.execute("SELECT id FROM searches WHERE url = ?", (url,)).fetchone()
    if exists:
        flash("Dette søket ligger inne fra før.", "info")
        return redirect(url_for("main.sok"))
    name = request.form.get("name", "").strip() or suggest_name(url)
    type_key = request.form.get("default_type", "")
    if type_key not in TYPE_LABELS:
        type_key = ""
    cursor = conn.execute(
        """INSERT INTO searches (name, url, default_brand, default_type, active, created_at)
           VALUES (?, ?, ?, ?, 1, ?)""",
        (name, url, request.form.get("default_brand", "").strip(), type_key, now_str()),
    )
    log_event(conn, "info", f"La til søket «{name}».")
    conn.commit()
    if get_settings(conn)["scraper_enabled"]:
        worker().request_run(cursor.lastrowid)
        flash(f"«{name}» er lagt til. Scraperen sjekker det om noen sekunder.", "ok")
    else:
        flash(f"«{name}» er lagt til. Slå på scraperen for å begynne å sjekke det.", "ok")
    return redirect(url_for("main.sok"))


@bp.route("/sok/<int:search_id>/endre", methods=["POST"])
def sok_endre(search_id: int):
    conn = get_db()
    type_key = request.form.get("default_type", "")
    if type_key not in TYPE_LABELS:
        type_key = ""
    name = request.form.get("name", "").strip()
    if not name:
        flash("Søket må ha et navn.", "feil")
        return redirect(url_for("main.sok"))
    conn.execute(
        "UPDATE searches SET name = ?, default_brand = ?, default_type = ? WHERE id = ?",
        (name, request.form.get("default_brand", "").strip(), type_key, search_id),
    )
    conn.commit()
    flash("Søket er oppdatert.", "ok")
    return redirect(url_for("main.sok"))


@bp.route("/sok/<int:search_id>/aktiv", methods=["POST"])
def sok_aktiv(search_id: int):
    conn = get_db()
    conn.execute("UPDATE searches SET active = 1 - active WHERE id = ?", (search_id,))
    conn.commit()
    return redirect(url_for("main.sok"))


@bp.route("/sok/<int:search_id>/slett", methods=["POST"])
def sok_slett(search_id: int):
    conn = get_db()
    row = conn.execute("SELECT name FROM searches WHERE id = ?", (search_id,)).fetchone()
    if row is None:
        abort(404)
    conn.execute("DELETE FROM searches WHERE id = ?", (search_id,))
    log_event(conn, "info", f"Slettet søket «{row['name']}».")
    conn.commit()
    flash(f"«{row['name']}» er slettet. Annonsene den fant, er beholdt.", "ok")
    return redirect(url_for("main.sok"))


@bp.route("/scraper/pa", methods=["POST"])
def scraper_pa():
    conn = get_db()
    set_setting(conn, "scraper_enabled", 1)
    set_setting(conn, "scraper_error", "")
    set_setting(conn, "scraper_notice", "")
    set_setting(conn, "scraper_next_run", "")
    log_event(conn, "info", "Scraperen ble slått på.")
    conn.commit()
    worker().wake()
    flash("Scraperen er slått på. Første sjekk starter om noen sekunder.", "ok")
    return redirect(safe_next(url_for("main.sok")))


@bp.route("/scraper/av", methods=["POST"])
def scraper_av():
    conn = get_db()
    set_setting(conn, "scraper_enabled", 0)
    log_event(conn, "info", "Scraperen ble slått av.")
    conn.commit()
    flash("Scraperen er slått av.", "ok")
    return redirect(safe_next(url_for("main.sok")))


@bp.route("/scraper/sjekk", methods=["POST"])
def scraper_sjekk():
    conn = get_db()
    settings = get_settings(conn)
    if not settings["scraper_enabled"]:
        flash("Slå på scraperen først.", "feil")
    elif worker().running:
        flash("Scraperen holder allerede på å sjekke.", "info")
    elif not worker().can_run_manually(conn):
        flash("Siste sjekk var for under to minutter siden. Vent litt, så vi ikke maser på Finn.",
              "info")
    else:
        worker().request_run()
        flash("Sjekker søkene nå. Det tar noen sekunder per søk.", "ok")
    return redirect(url_for("main.sok"))


@bp.route("/avslutt", methods=["POST"])
def avslutt():
    shutdown = current_app.config.get("SHUTDOWN")
    if shutdown is not None:
        log_event(get_db(), "info", "Golflager ble slått av.")
        get_db().commit()
        shutdown()
    return render_template("avsluttet.html", stopped=shutdown is not None)


@bp.route("/oppdater", methods=["POST"])
def oppdater():
    shutdown = current_app.config.get("SHUTDOWN")
    try:
        version = updater.install_latest(current_app.config["DATABASE"])
    except updater.UpdateError as exc:
        flash(str(exc), "feil")
        return redirect(url_for("main.innstillinger", _anchor="oppdatering"))
    conn = get_db()
    log_event(conn, "info", f"Golflager ble oppdatert til versjon {version}.")
    conn.commit()
    if shutdown is None:
        flash(f"Versjon {version} er installert. Start Golflager på nytt for å ta den i bruk.", "ok")
        return redirect(url_for("main.innstillinger", _anchor="oppdatering"))
    log_file = Path(current_app.config["DATABASE"]).parent / "golflager.log"
    updater.restart(log_path=log_file)
    shutdown()
    return render_template("oppdaterer.html", version=version)


@bp.route("/oppdater/sjekk", methods=["POST"])
def oppdater_sjekk():
    conn = get_db()
    try:
        version = updater.check_for_update(conn, force=True)
    except updater.UpdateError as exc:
        flash(str(exc), "feil")
    else:
        if version:
            flash(f"Versjon {version} er klar.", "ok")
        else:
            flash("Du har nyeste versjon.", "ok")
    return redirect(url_for("main.innstillinger", _anchor="oppdatering"))


@bp.route("/scraper/solgte", methods=["POST"])
def scraper_solgte():
    """Se etter solgte annonser i alle søk nå, uten å vente på neste faste sjekk."""
    conn = get_db()
    if not get_settings(conn)["scraper_enabled"]:
        flash("Slå på scraperen først.", "feil")
    elif worker().running:
        flash("Scraperen holder allerede på å sjekke.", "info")
    elif not worker().can_run_manually(conn):
        flash("Siste sjekk var for under to minutter siden. Vent litt, så vi ikke maser på Finn.",
              "info")
    else:
        worker().request_run(full=True)
        flash("Ser etter solgte annonser nå. Det tar noen sekunder per side.", "ok")
    return redirect(url_for("main.sok"))


@bp.route("/feilsoking/tom", methods=["POST"])
def feilsoking_tom():
    conn = get_db()
    set_setting(conn, "diagnostic_text", "")
    conn.commit()
    return redirect(url_for("main.innstillinger"))


@bp.route("/api/status")
def api_status():
    conn = get_db()
    settings = get_settings(conn)
    nav_new = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE status = 'ny' AND gone_at IS NULL AND first_seen_at > ?",
        (settings["last_seen_finds_at"] or "0000",),
    ).fetchone()[0]
    return jsonify(
        version=current_app.config.get("VERSION", "0"),
        running=worker().running,
        enabled=bool(settings["scraper_enabled"]),
        error=settings["scraper_error"],
        last_run=settings["scraper_last_run"],
        new=nav_new,
    )


# ---------------------------------------------------------------------------
# Innstillinger


SETTING_FIELDS = [
    "min_profit_pct", "min_profit_kr", "sale_factor_pct", "default_extra_cost",
    "cond_value_5", "cond_value_4", "cond_value_2", "cond_value_1",
    "min_comparables", "market_months", "budget_kr", "auto_hide_days", "auto_delete_days",
    "scrape_interval_min", "page_delay_s", "pages_per_search", "sold_check_hours",
]


@bp.route("/innstillinger", methods=["GET", "POST"])
def innstillinger():
    conn = get_db()
    if request.method == "POST":
        adjusted = []
        for key in SETTING_FIELDS:
            raw = request.form.get(key, "").strip().replace(",", ".")
            if raw == "":
                continue
            try:
                value = float(raw)
            except ValueError:
                flash(f"«{raw}» er ikke et tall.", "feil")
                continue
            low, high = LIMITS[key]
            if value < low or value > high:
                adjusted.append(key)
                value = max(low, min(high, value))
            if key not in ("min_profit_pct", "sale_factor_pct"):
                value = int(round(value))
            set_setting(conn, key, value)
        mode = request.form.get("rule_mode", "either")
        set_setting(conn, "rule_mode", "both" if mode == "both" else "either")
        conn.commit()
        if adjusted:
            flash("Noen verdier var utenfor det tillatte og er justert.", "info")
        flash("Innstillingene er lagret.", "ok")
        return redirect(url_for("main.innstillinger"))
    return render_template("innstillinger.html", limits=LIMITS,
                           db_file=current_app.config["DATABASE"])


@bp.route("/innstillinger/sikkerhetskopi")
def sikkerhetskopi():
    conn = get_db()
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        target = sqlite3.connect(path)
        conn.backup(target)
        target.close()
        with open(path, "rb") as file:
            data = io.BytesIO(file.read())
    finally:
        os.remove(path)
    return send_file(data, as_attachment=True, mimetype="application/octet-stream",
                     download_name=f"golflager-{datetime.now():%Y-%m-%d}.db")
