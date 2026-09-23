"""Norsk formatering av tall, penger og datoer i sidene."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Union

from flask import Flask

MONTHS = ["jan.", "feb.", "mars", "apr.", "mai", "juni", "juli", "aug.", "sep.", "okt.", "nov.",
          "des."]
NBSP = " "
MINUS = "−"


def tall(value: Any, decimals: int = 0) -> str:
    if value is None or value == "":
        return "–"
    number = float(value)
    text = f"{abs(number):,.{decimals}f}".replace(",", NBSP).replace(".", ",")
    return (MINUS if number < 0 and round(abs(number), decimals) != 0 else "") + text


def kr(value: Any, signed: bool = False) -> str:
    if value is None or value == "":
        return "–"
    text = tall(value)
    if signed and float(value) > 0 and text != "0":
        text = "+" + text
    return f"{text}{NBSP}kr"


def prosent(value: Any, signed: bool = False) -> str:
    if value is None:
        return "–"
    text = tall(value)
    if signed and float(value) > 0 and text != "0":
        text = "+" + text
    return f"{text}{NBSP}%"


def to_datetime(value: Union[str, date, datetime, None]) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def dato(value: Any, short: bool = False) -> str:
    moment = to_datetime(value)
    if moment is None:
        return "–"
    text = f"{moment.day}. {MONTHS[moment.month - 1]}"
    if short and moment.year == datetime.now().year:
        return text
    return f"{text} {moment.year}"


def klokke(value: Any) -> str:
    moment = to_datetime(value)
    return moment.strftime("%H:%M") if moment else "–"


def tid_siden(value: Any) -> str:
    moment = to_datetime(value)
    if moment is None:
        return "–"
    now = datetime.now()
    seconds = (now - moment).total_seconds()
    if seconds < 0:
        minutes = int(-seconds // 60)
        if minutes < 1:
            return "om under ett minutt"
        if minutes < 60:
            return f"om {minutes} min"
        return f"kl. {moment:%H:%M}" if moment.date() == now.date() else dato(moment, short=True)
    if seconds < 60:
        return "akkurat nå"
    if seconds < 3600:
        return f"for {int(seconds // 60)} min siden"
    if moment.date() == now.date():
        return f"i dag kl. {moment:%H:%M}"
    days = (now.date() - moment.date()).days
    if days == 1:
        return f"i går kl. {moment:%H:%M}"
    if days < 7:
        return f"for {days} dager siden"
    return dato(moment, short=True)


def register_filters(app: Flask) -> None:
    app.jinja_env.filters.update(
        tall=tall, kr=kr, prosent=prosent, dato=dato, klokke=klokke, tid_siden=tid_siden
    )
