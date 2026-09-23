"""Leser annonsene ut av en søkeresultatside fra Finn.

Finn bygger søkesidene sine med innebygde data (JSON) i tillegg til vanlig HTML.
Vi prøver først de innebygde dataene, og faller tilbake til HTML-kortene.
Vi åpner aldri enkeltannonser: alt hentes fra selve søkesiden.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ITEM_ID_RE = re.compile(r"(?:/item/|finnkode=)(\d{6,12})")
PRICE_TEXT_RE = re.compile(r"^\s*(\d{1,3}(?:[\s  .]\d{3})+|\d+)\s*(?:kr|,-)\s*$", re.I)
PRICE_ANY_RE = re.compile(r"(\d{1,3}(?:[\s  .]\d{3})+|\d+)\s*(?:kr\b|,-)", re.I)
REL_TIME_RE = re.compile(
    r"^(?:for\s+)?(\d+)\s*(min|minutter|minutt|t|time|timer|d|dag|dager|u|uke|uker)\.?(?:\s+siden)?$",
    re.I,
)
ENQUEUE_RE = re.compile(r"streamController\.enqueue\(\s*(\"(?:[^\"\\]|\\.)*\")\s*\)", re.S)
JSON_PARSE_RE = re.compile(r"JSON\.parse\(\s*(\"(?:[^\"\\]|\\.)*\")\s*\)", re.S)
ASSIGN_RE = re.compile(r"window\.(__[A-Za-z0-9_]+)\s*=\s*\{")

BLOCK_MARKERS = (
    "captcha", "are you a robot", "er du en robot", "unusual traffic", "access denied",
    "request blocked", "cf-chl", "just a moment...", "attention required", "datadome",
    "px-captcha", "perimeterx", "too many requests",
)
LABEL_WORDS = {
    "fiks ferdig", "privat", "forhandler", "ny", "til salgs", "gis bort", "ønskes kjøpt",
    "betal med vipps", "frakt", "send", "nyhet", "solgt", "reservert", "lagre", "favoritt",
}


@dataclass
class ParsedAd:
    finn_id: str
    title: str
    url: str
    price: Optional[int] = None
    location: str = ""
    published_at: Optional[datetime] = None
    image_url: str = ""
    trade_type: str = ""


@dataclass
class ParseResult:
    ads: List[ParsedAd] = field(default_factory=list)
    link_ids: Set[str] = field(default_factory=set)
    source: str = "none"


# ---------------------------------------------------------------------------
# Hjelpere


def _to_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(round(value))
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value.split(",")[0])
        return int(digits) if digits else None
    return None


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _parse_time(value: Any) -> Optional[datetime]:
    result: Optional[datetime] = None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value > 1e12:
                result = datetime.fromtimestamp(value / 1000)
            elif value > 1e9:
                result = datetime.fromtimestamp(value)
        elif isinstance(value, str) and value.strip():
            text = value.strip()
            if text.isdigit():
                return _parse_time(int(text))
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            result = parsed
    except (ValueError, OverflowError, OSError):
        return None
    if result is None:
        return None
    if result.year < 2005 or result > datetime.now() + timedelta(days=1):
        return None
    return result.replace(microsecond=0)


def _relative_time(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    match = REL_TIME_RE.match(text.strip())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    now = now or datetime.now()
    if unit.startswith("min"):
        delta = timedelta(minutes=amount)
    elif unit.startswith("t"):
        delta = timedelta(hours=amount)
    elif unit.startswith("d"):
        delta = timedelta(days=amount)
    else:
        delta = timedelta(weeks=amount)
    return (now - delta).replace(second=0, microsecond=0)


def _item_url(finn_id: str) -> str:
    return f"https://www.finn.no/recommerce/forsale/item/{finn_id}"


# ---------------------------------------------------------------------------
# Innebygde data (JSON)


def decode_turbo_stream(text: str) -> List[Any]:
    """Pakker ut «turbo-stream»-formatet som Remix/React Router bruker for sidedata."""
    values: List[Any] = []
    roots: List[int] = []
    promises: Dict[int, int] = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        payload = None
        promise_id = None
        if line.startswith("["):
            payload = line
        else:
            match = re.match(r"^[PE](\d+):(\[.*)$", line, re.S)
            if match:
                promise_id = int(match.group(1))
                payload = match.group(2)
        if payload is None:
            continue
        try:
            chunk = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(chunk, list) or not chunk:
            continue
        start = len(values)
        values.extend(chunk)
        roots.append(start)
        if promise_id is not None:
            promises[promise_id] = start

    cache: Dict[int, Any] = {}

    def hydrate(index: Any, depth: int = 0) -> Any:
        if not isinstance(index, int) or isinstance(index, bool):
            return index
        if index < 0:
            # Spesialverdier: -4 er «minus null», resten er null/undefined/NaN/uendelig.
            return 0 if index == -4 else None
        if index >= len(values) or depth > 200:
            return None
        if index in cache:
            return cache[index]
        raw = values[index]
        if isinstance(raw, list):
            if raw and isinstance(raw[0], str):
                tag, rest = raw[0], raw[1:]
                if tag == "D" and rest:
                    result = rest[0]
                elif tag in ("U", "R", "B") and rest:
                    result = rest[0]
                elif tag == "Z" and rest:
                    result = hydrate(rest[0], depth + 1)
                elif tag == "P" and rest and rest[0] in promises:
                    result = hydrate(promises[rest[0]], depth + 1)
                elif tag == "M":
                    result = {}
                    cache[index] = result
                    for i in range(0, len(rest) - 1, 2):
                        key = hydrate(rest[i], depth + 1)
                        if isinstance(key, (str, int)):
                            result[key] = hydrate(rest[i + 1], depth + 1)
                elif tag == "S":
                    result = [hydrate(i, depth + 1) for i in rest]
                elif tag == "N" and rest and isinstance(rest[0], dict):
                    result = _hydrate_obj(rest[0], hydrate, values, depth, cache, index)
                else:
                    result = None
                cache[index] = result
                return result
            out: List[Any] = []
            cache[index] = out
            out.extend(hydrate(i, depth + 1) for i in raw)
            return out
        if isinstance(raw, dict):
            return _hydrate_obj(raw, hydrate, values, depth, cache, index)
        cache[index] = raw
        return raw

    return [hydrate(root) for root in roots]


def _hydrate_obj(raw: Dict[str, Any], hydrate: Any, values: List[Any], depth: int,
                 cache: Dict[int, Any], index: int) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    cache[index] = out
    for key, value_index in raw.items():
        if key.startswith("_") and key[1:].isdigit():
            key_index = int(key[1:])
            real_key = values[key_index] if key_index < len(values) else None
            if not isinstance(real_key, str):
                continue
            out[real_key] = hydrate(value_index, depth + 1)
        else:
            out[key] = value_index
    return out


def _decode_js_string(literal: str) -> Optional[str]:
    try:
        value = json.loads(literal)
    except ValueError:
        return None
    return value if isinstance(value, str) else None


def extract_embedded_data(soup: BeautifulSoup) -> List[Any]:
    """Finner alle innebygde datastrukturer på siden."""
    found: List[Any] = []
    stream_chunks: List[str] = []
    for script in soup.find_all("script"):
        text = script.string if script.string is not None else script.get_text()
        if not text:
            continue
        script_type = (script.get("type") or "").lower()
        if "json" in script_type:
            try:
                found.append(json.loads(text))
            except ValueError:
                pass
            continue
        for literal in ENQUEUE_RE.findall(text):
            chunk = _decode_js_string(literal)
            if chunk:
                stream_chunks.append(chunk)
        for literal in JSON_PARSE_RE.findall(text):
            decoded = _decode_js_string(literal)
            if decoded:
                try:
                    found.append(json.loads(decoded))
                except ValueError:
                    pass
        for match in ASSIGN_RE.finditer(text):
            try:
                obj, _ = json.JSONDecoder().raw_decode(text, match.end() - 1)
                found.append(obj)
            except ValueError:
                pass
    if stream_chunks:
        try:
            found.extend(decode_turbo_stream("".join(stream_chunks)))
        except (RecursionError, ValueError, TypeError):
            pass
    return found


def _walk(obj: Any) -> Iterable[Dict[str, Any]]:
    stack = [obj]
    seen: Set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, (dict, list)):
            if id(current) in seen:
                continue
            seen.add(id(current))
        if isinstance(current, dict):
            yield current
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))


def _price_from(value: Any) -> Optional[int]:
    if isinstance(value, dict):
        for key in ("amount", "value", "price", "total", "main"):
            if key in value:
                return _price_from(value[key])
        return None
    return _to_int(value)


def _image_from(d: Dict[str, Any]) -> str:
    image = d.get("image")
    if isinstance(image, dict):
        url = _first_str(image.get("url"), image.get("src"), image.get("uri"))
        if url:
            return url
    if isinstance(image, str):
        return image
    if isinstance(image, list) and image:
        first = image[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return _first_str(first.get("url"), first.get("src"))
    for key in ("image_urls", "images"):
        items = d.get(key)
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return _first_str(first.get("url"), first.get("src"))
    return ""


def _location_from(d: Dict[str, Any]) -> str:
    location = d.get("location")
    if isinstance(location, str):
        return location.strip()
    if isinstance(location, dict):
        return _first_str(
            location.get("name"), location.get("city"), location.get("postalName"),
            location.get("postal_name"), location.get("area"),
        )
    return _first_str(d.get("local_area_name"), d.get("area"), d.get("municipality"))


def ad_from_dict(d: Dict[str, Any], base_url: str = "https://www.finn.no/") -> Optional[ParsedAd]:
    title = _first_str(d.get("heading"), d.get("title"), d.get("name"))
    if not title:
        return None
    url = _first_str(d.get("canonical_url"), d.get("url"), d.get("link"), d.get("href"),
                     d.get("ad_url"))
    url_match = ITEM_ID_RE.search(url) if url else None
    raw_id = None
    for key in ("ad_id", "adId", "finnkode", "id"):
        candidate = d.get(key)
        if candidate is not None and re.fullmatch(r"\d{6,12}", str(candidate)):
            raw_id = str(candidate)
            break
    finn_id = raw_id or (url_match.group(1) if url_match else None)
    if not finn_id:
        return None
    looks_like_ad = bool(url_match) or "ad_id" in d or "price" in d or "offers" in d
    if not looks_like_ad:
        return None
    if url:
        url = urljoin(base_url, url)
    if not url or not ITEM_ID_RE.search(url):
        url = _item_url(finn_id)
    price = _price_from(d.get("price"))
    if price is None and isinstance(d.get("offers"), dict):
        price = _price_from(d["offers"].get("price"))
    published = None
    for key in ("timestamp", "published", "published_at", "publishedAt", "datePosted", "created"):
        if key in d:
            published = _parse_time(d.get(key))
            if published:
                break
    image = _image_from(d)
    return ParsedAd(
        finn_id=finn_id,
        title=title[:300],
        url=url,
        price=price,
        location=_location_from(d)[:120],
        published_at=published,
        image_url=urljoin(base_url, image) if image else "",
        trade_type=_first_str(d.get("trade_type"), d.get("tradeType")),
    )


def ads_from_embedded(objects: List[Any], base_url: str) -> List[ParsedAd]:
    docs_ads: List[ParsedAd] = []
    other_ads: List[ParsedAd] = []
    for obj in objects:
        for d in _walk(obj):
            docs = d.get("docs")
            if isinstance(docs, list):
                for doc in docs:
                    if isinstance(doc, dict):
                        ad = ad_from_dict(doc, base_url)
                        if ad:
                            docs_ads.append(ad)
            ad = ad_from_dict(d, base_url)
            if ad:
                other_ads.append(ad)
    # Hvis siden har en egen trefflist ("docs"), bruker vi bare den, så vi slipper anbefalinger o.l.
    return _dedupe(docs_ads if docs_ads else other_ads)


# ---------------------------------------------------------------------------
# HTML-kort (reserveløsning)


def _card_for_link(link: Any, finn_id: str) -> Any:
    card = link
    for _ in range(8):
        parent = card.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        other_ids = {m for a in parent.find_all("a", href=True)
                     for m in ITEM_ID_RE.findall(a["href"])}
        if other_ids - {finn_id}:
            break
        card = parent
        if card.name in ("article", "li"):
            break
    return card


def _leaf_texts(card: Any) -> List[str]:
    """Alle tekstbitene i kortet, hver for seg («Oslo», «1 t.», «2 500 kr» …)."""
    return [text for text in card.stripped_strings if text]


def ads_from_html(soup: BeautifulSoup, base_url: str) -> List[ParsedAd]:
    ads: Dict[str, ParsedAd] = {}
    order: List[str] = []
    for link in soup.find_all("a", href=True):
        match = ITEM_ID_RE.search(link["href"])
        if not match:
            continue
        finn_id = match.group(1)
        card = _card_for_link(link, finn_id)
        title = link.get_text(" ", strip=True) or (link.get("aria-label") or "").strip()
        image_url = ""
        img = card.find("img")
        if img is not None:
            image_url = (img.get("src") or img.get("data-src") or "").strip()
            if not image_url and img.get("srcset"):
                image_url = img["srcset"].split(",")[0].strip().split(" ")[0]
            if not title:
                title = (img.get("alt") or "").strip()
        texts = _leaf_texts(card)
        price: Optional[int] = None
        for text in texts:
            if PRICE_TEXT_RE.match(text):
                price = _to_int(PRICE_TEXT_RE.match(text).group(1))
                break
            if text.lower() == "gis bort":
                price = 0
                break
        if price is None:
            card_text = card.get_text(" ", strip=True)
            if title:
                card_text = card_text.replace(title, " ")
            any_match = PRICE_ANY_RE.search(card_text)
            if any_match:
                price = _to_int(any_match.group(1))
        published = None
        time_el = card.find("time")
        if time_el is not None and time_el.get("datetime"):
            published = _parse_time(time_el["datetime"])
        location = ""
        for text in texts:
            lower = text.lower()
            if text == title or PRICE_TEXT_RE.match(text) or PRICE_ANY_RE.search(text):
                continue
            relative = _relative_time(text)
            if relative:
                published = published or relative
                continue
            if lower in LABEL_WORDS or len(text) > 40 or text.isdigit():
                continue
            if title and text in title:
                continue
            if not location:
                location = text
        existing = ads.get(finn_id)
        if existing:
            existing.title = existing.title or title
            existing.image_url = existing.image_url or image_url
            existing.price = existing.price if existing.price is not None else price
            existing.location = existing.location or location
            continue
        if not title:
            continue
        ads[finn_id] = ParsedAd(
            finn_id=finn_id,
            title=title[:300],
            url=_item_url(finn_id) if "/item/" not in link["href"] else urljoin(base_url, link["href"]),
            price=price,
            location=location[:120],
            published_at=published,
            image_url=urljoin(base_url, image_url) if image_url else "",
            trade_type="Ønskes kjøpt" if any(t.lower() == "ønskes kjøpt" for t in texts) else "",
        )
        order.append(finn_id)
    return [ads[i] for i in order if i in ads]


# ---------------------------------------------------------------------------


def _dedupe(ads: List[ParsedAd]) -> List[ParsedAd]:
    seen: Dict[str, ParsedAd] = {}
    for ad in ads:
        if ad.finn_id not in seen:
            seen[ad.finn_id] = ad
    return list(seen.values())


def _merge(primary: List[ParsedAd], secondary: List[ParsedAd]) -> List[ParsedAd]:
    extra = {ad.finn_id: ad for ad in secondary}
    for ad in primary:
        other = extra.get(ad.finn_id)
        if not other:
            continue
        ad.location = ad.location or other.location
        ad.image_url = ad.image_url or other.image_url
        ad.published_at = ad.published_at or other.published_at
        if ad.price is None:
            ad.price = other.price
    return primary


def parse_search_page(html: str, base_url: str = "https://www.finn.no/") -> ParseResult:
    soup = BeautifulSoup(html, "html.parser")
    link_ids = {m for a in soup.find_all("a", href=True) for m in ITEM_ID_RE.findall(a["href"])}
    embedded = ads_from_embedded(extract_embedded_data(soup), base_url)
    from_html = ads_from_html(soup, base_url)
    if embedded:
        ads, source = _merge(embedded, from_html), "data"
    elif from_html:
        ads, source = from_html, "html"
    else:
        ads, source = [], "none"
    return ParseResult(ads=ads, link_ids=link_ids, source=source)


def looks_blocked(html: str) -> bool:
    lower = html.lower()
    return any(marker in lower for marker in BLOCK_MARKERS)
