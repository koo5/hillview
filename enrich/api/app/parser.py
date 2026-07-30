"""Annotation-body parser — ported from scripts/enrich/resolve_anchors.py:parse_body,
but PURE and TOTAL (never returns None) and emitting flags as data rather than skips.

An annotation body is a `|`-separated string like:
    Ještěd | highest point around | https://cs.wikipedia.org/wiki/Ještěd | 50.732N, 15.008E
Segments: [0] name (may end with ? / contain (?) = uncertain), then any of a context
phrase, a Wikipedia URL, embedded coordinates. `oops…` marks a stitching error (not a
real target); a bare `?`/empty name = unnamed. Geocoding/Wikipedia *lookups* are M2.
"""
import re
import urllib.parse
from dataclasses import dataclass, field

PARSER_VERSION = "2"   # 2: type keywords match on word boundaries (v1 substring-matched
                       #    "hrad" inside "Zahradní" → castle, "vrch" in "Vrchlického", …)

# lat first, lon second (matches the source convention: "50.73N, 15.00E")
COORD_RE = re.compile(r"(\d{1,2}\.\d{3,})\s*[NnSs]?[,\s]+(\d{1,2}\.\d{3,})\s*[EeWw]?")
WIKI_RE = re.compile(r"https?://(\w{2,3})\.wikipedia\.org/wiki/([^\s|)]+)")
URL_RE = re.compile(r"https?://")

# cheap keyword type heuristic (optional hint; not authoritative)
TYPE_KEYWORDS = {
    "tower": "tower", "věž": "tower", "vysílač": "tower", "rozhledna": "tower",
    "church": "church", "kostel": "church", "chrám": "church", "katedrála": "church",
    "hill": "hill", "hora": "hill", "vrch": "hill", "kopec": "hill",
    "peak": "peak", "štít": "peak",
    "castle": "castle", "hrad": "castle", "zámek": "castle",
    "bridge": "bridge", "most": "bridge",
    "stadium": "stadium", "stadion": "stadium",
    "arena": "arena",
}


@dataclass
class ParsedBody:
    raw: str
    segments: list[str]
    name: str | None = None
    context: str | None = None
    coords: tuple[float, float] | None = None            # (lat, lon)
    wiki: tuple[str, str] | None = None                  # (lang, title)
    wiki_url: str | None = None
    type_guess: str | None = None
    uncertain: bool = False
    oops: bool = False
    unnamed: bool = False


def _type_guess(*texts: str | None) -> str | None:
    blob = " ".join(t for t in texts if t).lower()
    for kw, t in TYPE_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}\b", blob):
            return t
    return None


def parse_body(body: str | None) -> ParsedBody:
    raw = body or ""
    parts = [p.strip() for p in raw.split("|")] if raw else []
    result = ParsedBody(raw=raw, segments=parts)

    name0 = parts[0] if parts else ""
    if name0.lower() == "oops" or raw.lower().startswith("oops"):
        result.oops = True

    for p in parts:
        m = COORD_RE.search(p)
        if m and result.coords is None:
            result.coords = (float(m.group(1)), float(m.group(2)))
        w = WIKI_RE.search(p)
        if w and result.wiki is None:
            result.wiki = (w.group(1), urllib.parse.unquote(w.group(2)).replace("_", " "))
            result.wiki_url = w.group(0)

    if len(parts) > 1 and not URL_RE.search(parts[1]) and not COORD_RE.search(parts[1]):
        result.context = parts[1] or None

    name = name0.rstrip("?").replace("(?)", "").strip()
    result.uncertain = name0.endswith("?") or "(?)" in name0
    if not name or name == "?":
        result.unnamed = True
    else:
        result.name = name

    if not result.oops:
        result.type_guess = _type_guess(result.name, result.context)
    return result
