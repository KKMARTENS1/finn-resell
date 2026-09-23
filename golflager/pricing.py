"""Prissjekken: hva kan en ting selges for, og lønner det seg å kjøpe den?

Rekkefølge for sammenligning:
1. Dine egne salg av samme merke, modell og type.
2. Markedsprisene (utlagte priser på Finn), ganget med salgsfaktoren.
3. Hvis modellen ikke finnes: samme merke og type (grovt anslag, merkes som usikkert).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

from .classify import normalize
from .constants import IN_STOCK


@dataclass
class Comparable:
    label: str
    price: int
    adjusted: int
    source: str  # "salg" eller "marked"
    date: str = ""
    condition: Optional[int] = None
    url: str = ""


@dataclass
class PriceCheck:
    price: Optional[int]
    expected_sale: Optional[int] = None
    extra_costs: int = 0
    total_cost: Optional[int] = None
    profit: Optional[int] = None
    profit_pct: Optional[float] = None
    meets_rule: bool = False
    color: str = "gul"  # gronn / gul / rod
    decision: str = "Usikker"
    label: str = "Kanskje"
    reason: str = ""
    basis: str = ""
    source: str = ""  # salg / marked / ""
    confidence: str = "ingen"  # god / lav / ingen
    max_price: Optional[int] = None
    comparables: List[Comparable] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _model_match(query_key: str, candidate_key: str) -> Optional[str]:
    if not query_key:
        return None
    if query_key == candidate_key:
        return "exact"
    if candidate_key and min(len(query_key), len(candidate_key)) >= 3 and (
        query_key in candidate_key or candidate_key in query_key
    ):
        return "similar"
    return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def rule_text(settings: Dict[str, Any]) -> str:
    joiner = "eller" if settings["rule_mode"] == "either" else "og"
    return (
        f"minst {settings['min_profit_pct']:g} % {joiner} minst "
        f"{settings['min_profit_kr']:,} kr fortjeneste".replace(",", " ")
    )


class PriceData:
    """Laster salg og markedspriser én gang, så mange annonser kan sjekkes raskt."""

    def __init__(self, conn: sqlite3.Connection, settings: Dict[str, Any]) -> None:
        self.settings = settings
        self.sold = [dict(r) for r in conn.execute(
            """SELECT id, brand, model, type, condition, sale_price, sale_date, finn_url,
                      cost_grip + cost_shipping + cost_cleaning + cost_other AS extras
               FROM inventory WHERE status = 'solgt' AND sale_price > 0"""
        )]
        for item in self.sold:
            item["brand_key"] = normalize(item["brand"])
            item["model_key"] = normalize(item["model"])
        since = (datetime.now() - timedelta(days=30 * int(settings["market_months"]))).isoformat(
            sep=" ", timespec="seconds"
        )
        self.market = [dict(r) for r in conn.execute(
            """SELECT id, finn_id, title, brand, model, type, price, url, first_seen_at
               FROM listings
               WHERE price >= 50 AND price <= 500000 AND last_seen_at >= ?""",
            (since,),
        )]
        for item in self.market:
            item["brand_key"] = normalize(item["brand"])
            item["model_key"] = normalize(item["model"])
        self.extras_by_type: Dict[str, float] = {}
        grouped: Dict[str, List[int]] = {}
        for item in self.sold:
            grouped.setdefault(item["type"], []).append(item["extras"] or 0)
        for type_key, values in grouped.items():
            self.extras_by_type[type_key] = sum(values) / len(values)
        row = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(purchase_price, 0) + cost_grip + cost_shipping"
            " + cost_cleaning + cost_other), 0) AS bound FROM inventory WHERE status IN (?, ?, ?)",
            IN_STOCK,
        ).fetchone()
        self.bound_now = int(row["bound"])

    # -----------------------------------------------------------------

    def estimate_extras(self, type_key: str) -> int:
        if type_key in self.extras_by_type:
            return int(round(self.extras_by_type[type_key]))
        return int(self.settings["default_extra_cost"])

    def _own_sales(self, brand_key: str, model_key: str, type_key: str, level: str,
                   exclude_inventory_id: Optional[int]) -> List[Dict[str, Any]]:
        out = []
        for item in self.sold:
            if item["id"] == exclude_inventory_id:
                continue
            if item["type"] != type_key or item["brand_key"] != brand_key:
                continue
            match = _model_match(model_key, item["model_key"])
            if level == "broad" or match == level:
                out.append(item)
        return out

    def _market(self, brand_key: str, model_key: str, type_key: str, level: str,
                exclude_listing_id: Optional[int]) -> List[Dict[str, Any]]:
        out = []
        for item in self.market:
            if item["id"] == exclude_listing_id:
                continue
            if item["type"] != type_key or item["brand_key"] != brand_key:
                continue
            match = _model_match(model_key, item["model_key"])
            if level == "broad" or match == level:
                out.append(item)
        return out

    def check(
        self,
        brand: str,
        model: str,
        type_key: str,
        price: Optional[int],
        condition: Optional[int] = None,
        extra_costs: Optional[int] = None,
        exclude_listing_id: Optional[int] = None,
        exclude_inventory_id: Optional[int] = None,
    ) -> PriceCheck:
        s = self.settings
        brand_key, model_key = normalize(brand), normalize(model)
        step = float(s["condition_step_pct"]) / 100
        factor = float(s["sale_factor_pct"]) / 100
        min_comp = int(s["min_comparables"])
        result = PriceCheck(price=price)

        tiers = [
            ("salg", "exact"), ("salg", "similar"), ("marked", "exact"), ("marked", "similar"),
            ("salg", "broad"), ("marked", "broad"),
        ]
        chosen: List[Dict[str, Any]] = []
        chosen_source = chosen_level = ""
        if brand_key:
            for source, level in tiers:
                if source == "salg":
                    rows = self._own_sales(brand_key, model_key, type_key, level,
                                           exclude_inventory_id)
                else:
                    rows = self._market(brand_key, model_key, type_key, level,
                                        exclude_listing_id)
                if rows:
                    chosen, chosen_source, chosen_level = rows, source, level
                    break

        if chosen_source == "salg":
            comps = []
            for item in chosen:
                adjust = 1.0
                if condition and item["condition"]:
                    adjust = _clamp(1 + step * (condition - int(item["condition"])), 0.5, 1.5)
                comps.append(Comparable(
                    label=f"{item['brand']} {item['model']}".strip(),
                    price=int(item["sale_price"]),
                    adjusted=int(round(item["sale_price"] * adjust)),
                    source="salg",
                    date=item["sale_date"] or "",
                    condition=item["condition"],
                    url=item["finn_url"] or "",
                ))
            result.expected_sale = int(round(median(c.adjusted for c in comps)))
            result.comparables = sorted(comps, key=lambda c: c.date, reverse=True)
            n = len(comps)
            what = {"exact": "samme modell", "similar": "lignende modell",
                    "broad": "samme merke og type"}[chosen_level]
            result.basis = f"Basert på {n} {'eget salg' if n == 1 else 'egne salg'} ({what})."
            result.confidence = "lav" if chosen_level == "broad" else "god"
        elif chosen_source == "marked":
            adjust = _clamp(1 + step * ((condition or 3) - 3), 0.5, 1.5)
            comps = [Comparable(
                label=item["title"],
                price=int(item["price"]),
                adjusted=int(round(item["price"] * factor * adjust)),
                source="marked",
                date=(item["first_seen_at"] or "")[:10],
                url=item["url"],
            ) for item in chosen]
            typical = median(c.price for c in comps)
            result.expected_sale = int(round(typical * factor * adjust))
            result.comparables = sorted(comps, key=lambda c: c.date, reverse=True)
            n = len(comps)
            what = {"exact": "samme modell", "similar": "lignende modeller",
                    "broad": "samme merke og type"}[chosen_level]
            result.basis = (
                f"Basert på {n} {'annonse' if n == 1 else 'annonser'} på Finn ({what}). "
                f"Typisk utlagt pris er {int(typical):,} kr, og vi regner med at du får "
                f"{s['sale_factor_pct']:g} % av det.".replace(",", " ")
            )
            if chosen_level == "broad" or n < min_comp:
                result.confidence = "lav"
            else:
                result.confidence = "god"
        result.source = chosen_source

        result.extra_costs = (
            int(extra_costs) if extra_costs is not None else self.estimate_extras(type_key)
        )

        if price is None:
            result.reason = "Annonsen har ingen pris, så fortjenesten kan ikke regnes ut."
            result.color, result.label, result.decision = "gul", "Ukjent pris", "Usikker"
            return result
        if result.expected_sale is None:
            result.reason = (
                "Fant ingen egne salg eller annonser å sammenligne med. "
                "Sjekk prisen selv, eller legg inn merke og modell."
                if brand_key else "Merket er ukjent, så det finnes ingenting å sammenligne med."
            )
            result.color, result.label, result.decision = "gul", "Ingen data", "Usikker"
            return result

        expected = result.expected_sale
        extras = result.extra_costs
        total_cost = price + extras
        profit = expected - total_cost
        pct = (profit / total_cost * 100) if total_cost > 0 else (100.0 if profit > 0 else 0.0)
        result.total_cost, result.profit, result.profit_pct = total_cost, profit, pct

        min_pct = float(s["min_profit_pct"])
        min_kr = int(s["min_profit_kr"])
        either = s["rule_mode"] == "either"

        def meets(pct_req: float, kr_req: float) -> bool:
            ok_pct = pct >= pct_req
            ok_kr = profit >= kr_req
            return (ok_pct or ok_kr) if either else (ok_pct and ok_kr)

        result.meets_rule = meets(min_pct, min_kr) and profit > 0
        near = meets(min_pct / 2, min_kr / 2) and profit > 0

        by_kr = expected - extras - min_kr
        by_pct = expected / (1 + min_pct / 100) - extras
        max_price = max(by_kr, by_pct) if either else min(by_kr, by_pct)
        result.max_price = max(0, int(max_price // 10 * 10))

        if result.meets_rule:
            result.decision = "Kjøp"
            if result.confidence == "god":
                result.color, result.label = "gronn", "Kjøp"
                result.reason = "Oppfyller regelen din."
            else:
                result.color, result.label = "gul", "Kanskje"
                result.reason = "Oppfyller regelen din, men det finnes lite å sammenligne med."
        else:
            result.decision = "La være"
            if near:
                result.color, result.label = "gul", "Kanskje"
                result.reason = (
                    "Gir litt fortjeneste, men under kravet ditt. Kanskje verdt det hvis du får "
                    "prisen ned."
                )
            else:
                result.color, result.label = "rod", "La være"
                result.reason = (
                    "Gir tap." if profit <= 0 else "Fortjenesten er for lav i forhold til kravet ditt."
                )

        budget = int(s["budget_kr"])
        if budget > 0 and self.bound_now + total_cost > budget:
            result.notes.append(
                f"Kjøpet gjør at du får {self.bound_now + total_cost:,} kr bundet i lager, "
                f"som er over budsjettet ditt på {budget:,} kr.".replace(",", " ")
            )
        return result
