"""Tall og grafer til forsiden."""
from __future__ import annotations

import math
import sqlite3
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from .constants import IN_STOCK, PAID, TYPE_LABELS, TYPES

MONTHS = ["jan", "feb", "mar", "apr", "mai", "jun", "jul", "aug", "sep", "okt", "nov", "des"]


def item_cost(item: Dict[str, Any]) -> int:
    return int(
        (item.get("purchase_price") or 0)
        + (item.get("cost_grip") or 0)
        + (item.get("cost_shipping") or 0)
        + (item.get("cost_cleaning") or 0)
        + (item.get("cost_other") or 0)
    )


def item_profit(item: Dict[str, Any]) -> Optional[int]:
    if item.get("status") != "solgt" or item.get("sale_price") is None:
        return None
    return int(item["sale_price"]) - item_cost(item)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


def days_between(start: Optional[str], end: Optional[str]) -> Optional[int]:
    a, b = _parse_date(start), _parse_date(end)
    if a is None or b is None:
        return None
    return max(0, (b - a).days)


def nice_step(span: float, target: int = 4) -> float:
    if span <= 0:
        return 1
    raw = span / target
    power = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mult * power:
            return mult * power
    return 10 * power


def month_chart(sold: List[Dict[str, Any]], months: int = 12,
                today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    keys: List[str] = []
    y, m = today.year, today.month
    for _ in range(months):
        keys.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    keys.reverse()
    totals = {k: 0 for k in keys}
    counts = {k: 0 for k in keys}
    for item in sold:
        key = (item.get("sale_date") or "")[:7]
        if key in totals:
            totals[key] += item_profit(item) or 0
            counts[key] += 1
    values = [totals[k] for k in keys]
    top = max([0] + values)
    bottom = min([0] + values)
    if top == bottom == 0:
        top = 1000
    step = nice_step(top - bottom)
    top = math.ceil(top / step) * step if top > 0 else 0
    bottom = math.floor(bottom / step) * step if bottom < 0 else 0
    span = (top - bottom) or 1
    ticks = []
    value = bottom
    while value <= top + 1e-9:
        ticks.append({"value": value, "pos": (top - value) / span * 100})
        value += step
    zero_pos = top / span * 100
    bars = []
    for k in keys:
        v = totals[k]
        year, month = int(k[:4]), int(k[5:])
        bars.append({
            "key": k,
            "label": MONTHS[month - 1],
            "full_label": f"{MONTHS[month - 1]} {year}",
            "value": v,
            "count": counts[k],
            "height": abs(v) / span * 100,
            "negative": v < 0,
            "first_of_year": month == 1,
        })
    return {"bars": bars, "ticks": ticks, "zero_pos": zero_pos, "has_data": any(counts.values())}


def dashboard(conn: sqlite3.Connection, settings: Dict[str, Any]) -> Dict[str, Any]:
    items = [dict(r) for r in conn.execute("SELECT * FROM inventory")]
    paid = [i for i in items if i["status"] in PAID]
    in_stock = [i for i in items if i["status"] in IN_STOCK]
    sold = [i for i in items if i["status"] == "solgt" and i["sale_price"] is not None]

    invested = sum(item_cost(i) for i in paid)
    bound = sum(item_cost(i) for i in in_stock)
    revenue = sum(int(i["sale_price"]) for i in sold)
    profit = sum(item_profit(i) or 0 for i in sold)
    avg_profit = profit / len(sold) if sold else None
    day_counts = [d for d in (days_between(i["purchase_date"], i["sale_date"]) for i in sold)
                  if d is not None]
    avg_days = sum(day_counts) / len(day_counts) if day_counts else None
    total_sold_cost = sum(item_cost(i) for i in sold)
    margin = profit / total_sold_cost * 100 if total_sold_cost else None

    def ranking(key: str, label_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        groups: Dict[str, Dict[str, Any]] = {}
        for item in sold:
            raw = item[key] or ""
            name = raw or "Ukjent merke"
            if label_map:
                name = label_map.get(raw, name)
            group = groups.setdefault(name, {"name": name, "key": raw or name, "profit": 0,
                                             "count": 0})
            group["profit"] += item_profit(item) or 0
            group["count"] += 1
        rows = sorted(groups.values(), key=lambda g: g["profit"], reverse=True)[:6]
        biggest = max([abs(r["profit"]) for r in rows] + [1])
        for row in rows:
            row["avg"] = row["profit"] / row["count"]
            row["width"] = abs(row["profit"]) / biggest * 100
        return rows

    type_rows = []
    for type_key, label in TYPES:
        sold_n = sum(1 for i in sold if i["type"] == type_key)
        stock_n = sum(1 for i in in_stock if i["type"] == type_key)
        if sold_n or stock_n:
            type_rows.append({"key": type_key, "label": label, "sold": sold_n, "stock": stock_n,
                              "total": sold_n + stock_n})
    biggest_type = max([r["total"] for r in type_rows] + [1])
    for row in type_rows:
        row["sold_w"] = row["sold"] / biggest_type * 100
        row["stock_w"] = row["stock"] / biggest_type * 100

    budget = int(settings["budget_kr"])
    budget_pct = bound / budget * 100 if budget > 0 else None
    if budget_pct is None:
        budget_state = "none"
    elif budget_pct > 100:
        budget_state = "over"
    elif budget_pct >= 90:
        budget_state = "near"
    else:
        budget_state = "ok"

    last_seen = settings["last_seen_finds_at"] or "0000"
    new_finds = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE status = 'ny' AND gone_at IS NULL AND first_seen_at > ?", (last_seen,)
    ).fetchone()[0]
    open_finds = conn.execute(
        "SELECT COUNT(*) FROM listings WHERE status = 'ny' AND gone_at IS NULL"
    ).fetchone()[0]

    return {
        "invested": invested,
        "bound": bound,
        "revenue": revenue,
        "profit": profit,
        "avg_profit": avg_profit,
        "avg_days": avg_days,
        "margin": margin,
        "sold_count": len(sold),
        "stock_count": len(in_stock),
        "item_count": len(items),
        "top_types": ranking("type", TYPE_LABELS),
        "top_brands": ranking("brand"),
        "type_rows": type_rows,
        "months": month_chart(sold),
        "budget": budget,
        "budget_pct": budget_pct,
        "budget_state": budget_state,
        "new_finds": new_finds,
        "open_finds": open_finds,
    }
