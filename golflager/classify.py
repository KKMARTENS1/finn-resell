"""Gjetter merke, modell og type ut fra en annonsetittel."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Merker i prioritert rekkefølge: de mest spesifikke først (Scotty Cameron før Titleist osv.).
BRANDS: List[Tuple[str, List[str]]] = [
    ("Scotty Cameron", [r"scotty\s*cameron", r"\bscotty\b", r"\bcameron\b"]),
    ("Odyssey", [r"\bodyssey\b"]),
    ("L.A.B. Golf", [r"\bl\.?\s?a\.?\s?b\.?\s*golf\b", r"\blab\s+golf\b"]),
    ("Bettinardi", [r"\bbettinardi\b"]),
    ("Evnroll", [r"\bevnroll\b"]),
    ("Titleist", [r"\btitleist\b", r"\bvokey\b"]),
    ("Ping", [r"\bping\b"]),
    ("TaylorMade", [r"\btaylor\s*made\b"]),
    ("Callaway", [r"\bcallaway\b"]),
    ("Cobra", [r"\bcobra\b"]),
    ("Mizuno", [r"\bmizuno\b"]),
    ("Srixon", [r"\bsrixon\b"]),
    ("Cleveland", [r"\bcleveland\b"]),
    ("Wilson", [r"\bwilson\b"]),
    ("PXG", [r"\bpxg\b"]),
    ("Honma", [r"\bhonma\b"]),
    ("Miura", [r"\bmiura\b"]),
    ("Tour Edge", [r"\btour\s*edge\b"]),
    ("XXIO", [r"\bxxio\b"]),
    ("Yonex", [r"\byonex\b"]),
    ("Bridgestone", [r"\bbridgestone\b"]),
    ("Benross", [r"\bbenross\b"]),
    ("Ben Sayers", [r"\bben\s*sayers\b"]),
    ("MacGregor", [r"\bmac\s*gregor\b"]),
    ("Adams", [r"\badams\b"]),
    ("Nike", [r"\bnike\b"]),
    ("Sun Mountain", [r"\bsun\s*mountain\b"]),
    ("Big Max", [r"\bbig\s*max\b"]),
    ("Ogio", [r"\bogio\b"]),
    ("Vessel", [r"\bvessel\b"]),
    ("Jones", [r"\bjones\b"]),
    ("Motocaddy", [r"\bmotocaddy\b"]),
    ("PowaKaddy", [r"\bpowa\s*kaddy\b"]),
    ("Clicgear", [r"\bclic\s*gear\b"]),
    ("JuCad", [r"\bjucad\b"]),
    ("Garmin", [r"\bgarmin\b"]),
    ("Bushnell", [r"\bbushnell\b"]),
    ("FootJoy", [r"\bfoot\s*joy\b"]),
    ("Ecco", [r"\becco\b"]),
]
_BRAND_RES = [(name, [re.compile(p, re.IGNORECASE) for p in pats]) for name, pats in BRANDS]

# Undermerker som hører til modellnavnet (f.eks. "Vokey SM9" hos Titleist).
_MODEL_PREFIX_WORDS = {"vokey"}

# Typeord. Ordet som står først i tittelen vinner, så "putter med headcover" blir putter,
# mens "headcover til putter" blir annet.
_TYPE_PATTERNS: List[Tuple[str, str]] = [
    (
        "annet",
        r"head\s*covers?|hodetrekk|\bcovers?\b|golftralle|\btralle\b|trolley|golfvogn|\bvogn\b"
        r"|avstandsmåler|rangefinder|golfsko|\bsko\b|hanske|golfballer|\bballer\b|\bballs?\b"
        r"|\bgps\b|paraply|puttematte|putte\s*matte|treningsnett|golfsett|halvsett"
        r"|komplett\s+sett|nybegynnersett|juniorsett|startsett",
    ),
    (
        "bag",
        r"golfbag|bærebag|vognbag|standbag|stand\s*bag|cart\s*bag|carry\s*bag|tour\s*bag"
        r"|staff\s*bag|\bbag\b",
    ),
    (
        "putter",
        r"putter|\bnewport\b|\bphantom\b|\bspider\b|two[\s-]?ball|\banser\b|white\s*hot"
        r"|\bfutura\b|\bsquareback\b|\bfastback\b|\bgolo\b|\bdel\s*mar\b",
    ),
    (
        "wedge",
        r"wedge|\bvokey\b|\bsm\s?\d{1,2}\b|\brtx\b|\bcbx\b|\bmg\s?\d\b|\bjaws\b"
        r"|\b(?:4[6-9]|5\d|6[0-4])\s*(?:°|grader|deg\b)",
    ),
    ("driver", r"\bdriver|\b1[\s-]?wood\b|\b1[\s-]?tre\b"),
    (
        "jernsett",
        r"jernsett|jern\s*sett|iron\s*set|\birons\b|\bjern\b"
        r"|\b[3-7]\s*-\s*(?:pw|p|gw|aw|sw|9)\b|\b[3-7]\s*til\s*(?:pw|p)\b",
    ),
    (
        "annet",
        r"fairway|\bhybrid|\brescue\b|\butility\b|\b[2-9][\s-]?(?:wood|tre|jern|iron)\b"
        r"|\bskaft\b|\bshaft\b",
    ),
]
_TYPE_RES = [(t, re.compile(p, re.IGNORECASE)) for t, p in _TYPE_PATTERNS]

# Ord som avslutter et modellnavn i tittelen.
_STOP_WORDS = {
    "driver", "drivere", "putter", "putters", "wedge", "wedger", "jernsett", "jern", "irons",
    "iron", "bag", "golfbag", "selges", "selger", "til", "salgs", "med", "m/", "og", "for", "i",
    "på", "pent", "pen", "brukt", "ny", "nye", "nytt", "som", "herre", "dame", "junior",
    "høyre", "venstre", "lh", "rh", "left", "right", "hand", "stiff", "regular", "senior",
    "ladies", "flex", "skaft", "shaft", "grep", "grip", "headcover", "cover", "tommer", "inch",
    "sett", "set", "fairway", "hybrid", "wood", "golf", "kølle", "køller", "ønskes", "kjøpt",
    "kjøpes", "inkl", "inkl.", "inkludert", "lite", "nesten", "original", "originalt", "the",
    "x-stiff", "strøken", "strøkent", "fin", "fint", "god", "godt", "tilstand", "loft",
    "lengde", "lie", "grader", "herrer", "damer", "komplett", "demo",
}
_LEADING_SKIP = {"selges", "selger", "pent", "brukt", "ny", "nye", "nytt", "strøken", "by",
                 "fra", "from", "golf", "-", "–", "|", "/", ":"}
_SEPARATORS = {"-", "–", "—", "|", "/", "+", "&", ":", "•", "·"}


def normalize(text: str) -> str:
    """Gjør tekst sammenlignbar: 'Newport 2' og 'newport2' blir like."""
    return re.sub(r"[^a-z0-9æøå]", "", (text or "").lower())


def detect_brand(title: str) -> Tuple[Optional[str], Optional[Tuple[int, int]]]:
    for name, patterns in _BRAND_RES:
        for pattern in patterns:
            match = pattern.search(title)
            if match:
                return name, match.span()
    return None, None


def detect_type(title: str) -> Optional[str]:
    best: Optional[Tuple[int, int, str]] = None
    for order, (type_key, pattern) in enumerate(_TYPE_RES):
        match = pattern.search(title)
        if match and (best is None or (match.start(), order) < (best[0], best[1])):
            best = (match.start(), order, type_key)
    return best[2] if best else None


_TYPE_WORD_RE = re.compile(
    r"putter|driver|wedge|jern|irons?\b|bag$|bagger?\b|fairway|hybrid|headcover|hodetrekk"
    r"|tralle|golfsett",
    re.IGNORECASE,
)


def _is_spec_token(token: str) -> bool:
    """Lengder, loft og lignende som ikke hører til modellnavnet (34", 10.5°, 35, 4-PW)."""
    if any(ch in token for ch in ('"', "”", "''", "°")):
        return True
    if re.fullmatch(r"\d\s*-\s*(?:pw|p|gw|aw|sw|\d)", token, re.IGNORECASE):
        return True
    if re.fullmatch(r"\d+(?:[.,]\d+)?(?:cm|in|tommer)?", token, re.IGNORECASE):
        number = float(re.sub(r"[^\d.,]", "", token).replace(",", "."))
        if "." in token or "," in token:
            return number >= 8  # loft som 9.0 og 10.5 (men ikke Phantom 5.5)
        # Lengder (33–36) og loft (46–64) står ofte etter modellen. Årstall også.
        return 20 <= number <= 70 or 1990 <= number <= 2100
    return False


def extract_model(title: str, brand_span: Optional[Tuple[int, int]] = None) -> str:
    if brand_span:
        start = brand_span[0]
        matched = title[brand_span[0]:brand_span[1]].strip().lower()
        if matched not in _MODEL_PREFIX_WORDS:
            start = brand_span[1]
        text = title[start:]
    else:
        text = title
    tokens = text.split()
    model: List[str] = []
    for raw in tokens:
        token = raw.strip("()[]{}!?;\"'*")
        ends_clause = raw.endswith((",", ".", ";", ":", ")"))
        token = token.rstrip(",.;:")
        if not token:
            continue
        lower = token.lower()
        if not model and lower not in _MODEL_PREFIX_WORDS and (
                lower in _LEADING_SKIP or _is_known_brand_word(lower)):
            continue
        is_stop_word = lower in _STOP_WORDS and token != "OG"  # «OG» = original, ikke «og»
        if (is_stop_word or lower in _SEPARATORS or _is_spec_token(token)
                or _TYPE_WORD_RE.search(lower)):
            break
        model.append(token)
        if ends_clause or len(model) >= 4:
            break
    return " ".join(model)


def _is_known_brand_word(word: str) -> bool:
    for _, patterns in _BRAND_RES:
        for pattern in patterns:
            if pattern.fullmatch(word):
                return True
    return False


def classify(title: str, default_brand: str = "", default_type: str = "") -> Tuple[str, str, str]:
    """Returnerer (merke, modell, type) for en annonsetittel."""
    brand, span = detect_brand(title)
    type_key = detect_type(title) or default_type or "annet"
    model = extract_model(title, span)
    return brand or default_brand or "", model, type_key


WANTED_RE = re.compile(
    r"^\s*(?:ønskes\s+kjøpt|ønsker\s+å\s+kjøpe|kjøpes|søker|leter\s+etter)\b", re.IGNORECASE
)


def is_wanted_ad(title: str) -> bool:
    """«Ønskes kjøpt»-annonser er ikke noe du kan kjøpe."""
    return bool(WANTED_RE.search(title or ""))


# ---------------------------------------------------------------------------
# Tilstand fra tittelen

_NEGATED_WEAR_RE = re.compile(
    r"\b(?:ingen|uten|null|nesten\s+ingen)\s+(?:synlige\s+)?(?:riper|ripe|skader|skade|merker"
    r"|bruksmerker|brukspreg|slitasje|hakk|skrammer)\b",
    re.IGNORECASE,
)
_MILD_WEAR_RE = re.compile(
    r"\b(?:små|lette|minimale|minimalt|lite|noen\s+få|få|litt)\s+(?:med\s+)?(?:riper|ripe|merker"
    r"|bruksmerker|brukspreg|slitasje|skrammer)\b",
    re.IGNORECASE,
)
# 1 – Slitt: tydelige skader eller kraftig slitasje
_SEVERE_RE = re.compile(
    r"oppripe\w*|\bdefekt\w*|\bknekt\w*|ødelagt|til\s+deler|\brust(?:en|et|ete|flekker)?\b"
    r"|\bbulk(?:er|et|ete)?\b|\bsprekk\w*|\bskadet\b|\bskader?\b|mye\s+riper|masse\s+riper"
    r"|hardt\s+brukt|kraftig\w*\s+(?:brukt|slitt|slitasje|riper)|trenger\s+reparasjon",
    re.IGNORECASE,
)
# 2 – Brukbar: vanlig, synlig slitasje
_WORN_RE = re.compile(
    r"\bslitt\w*|slitasje|\briper\b|\bripe\b|ripete|brukspreg|bruksmerker|skrammer|\bhakk\b"
    r"|mye\s+brukt|godt\s+brukt|en\s+del\s+brukt|trenger\s+nytt\s+grep|\bok\s+stand\b|brukbar",
    re.IGNORECASE,
)
_AS_NEW_RE = re.compile(
    r"som\s+ny|ubrukt|aldri\s+brukt|\bi\s+plast\b|med\s+plast|helt\s+ny\b|strøken|\bmint\b"
    r"|ny\s+i\s+eske",
    re.IGNORECASE,
)
_GOOD_RE = re.compile(
    r"pent\s+brukt|lite\s+brukt|\bpen\s+stand|god\s+stand|fin\s+stand|meget\s+god|veldig\s+god"
    r"|nesten\s+ny|\bpen\b|\bpent\b|\bfin\b",
    re.IGNORECASE,
)


def detect_condition(title: str) -> Optional[int]:
    """Gjetter tilstand (1–5) ut fra ord i tittelen. None betyr at tittelen ikke sier noe.

    Er det tegn på slitasje, vinner den laveste tilstanden, så prissjekken heller er for
    forsiktig enn for optimistisk.
    """
    negated = bool(_NEGATED_WEAR_RE.search(title or ""))  # «ingen riper» er et godt tegn
    text = _NEGATED_WEAR_RE.sub(" ", title or "")
    if _SEVERE_RE.search(text):
        return 1
    mild = bool(_MILD_WEAR_RE.search(text))
    text = _MILD_WEAR_RE.sub(" ", text)
    if _WORN_RE.search(text):
        return 2
    if mild:
        return 3
    if _AS_NEW_RE.search(text):
        return 5
    if _GOOD_RE.search(text) or negated:
        return 4
    return None
