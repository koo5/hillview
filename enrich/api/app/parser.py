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

PARSER_VERSION = "7"   # 7: an "id=<key>" segment is a POI key (hv:poiKey) — the author's
                       #    handle tying annotations of one subject together — not a label
                       # 6: wikipedia URL = everything after /wiki/ minus ?query/#fragment
                       #    (mobile share links append ?uselang=en); non-wiki URLs are
                       #    kept as links (hv:webPage); a hillview.cz link carrying only
                       #    lat/lon(/zoom) counts as the body's coordinates; a wiki-only
                       #    body takes the page title as its (proposed) label
                       # 5: wikipedia titles keep balanced parens — "…_(Čáslav)" no
                       #    longer loses its ")" (a bare wrapping ")" is still left out)
                       # 4: southern/western coords parse — S/W letters and leading
                       #    minus both sign the value; lon accepts 3 integer digits
                       #    (100-180°); pattern mirrored in the frontend TS twin
                       # 3: decimal-comma coords ("50,0620061, 14,8864855") parse; per-
                       #    segment roles emitted (coords no longer misfiled as context;
                       #    URL-/coords-first bodies count as unnamed)
                       # 2: type keywords match on word boundaries (v1 substring-matched
                       #    "hrad" inside "Zahradní" → castle, "vrch" in "Vrchlického", …)

# lat first, lon second (matches the source convention: "50.73N, 15.00E");
# [.,] decimal separator — Czech bodies also write "50,0620061, 14,8864855";
# southern/western values may be marked either way, "-33.8568" or "33.8568S".
# TS twin: frontend/src/lib/utils/coordParser.ts (clickable coords in the
# zoomview) — keep the pattern and semantics in sync both ways.
COORD_RE = re.compile(r"(-?\d{1,2}[.,]\d{3,})\s*([NnSs])?[,\s]+(-?\d{1,3}[.,]\d{3,})\s*([EeWw])?")
# a wikipedia URL is whatever follows /wiki/ up to whitespace or the segment
# pipe; the title is that path with its ?query / #fragment dropped (mobile share
# links append ?uselang=en) and a wrapping ")" removed only when it is unbalanced
# — titles legitimately contain "(…)", commas, dots, anything
WIKI_RE = re.compile(r"https?://(\w{2,3})(?:\.m)?\.wikipedia\.org/wiki/([^\s|]+)")
URL_RE = re.compile(r"https?://[^\s|]+")
# a hillview.cz view link — the annotator pointing at a map/photo view
HILLVIEW_RE = re.compile(r"https?://(?:www\.)?hillview\.cz/\?([^\s|]+)")
# "id=vcelka": the author's key for the subject itself, shared by every
# annotation of it (a POI handle; the geocoder treats same-key annotations as
# namesakes, and it is the hook for an explicit POI link later)
POI_KEY_RE = re.compile(r"^id\s*=\s*([\w.-]+)$", re.I)


def _wiki_from_match(m: re.Match) -> tuple[str, str, str]:
    """→ (lang, title, canonical url) from a WIKI_RE match."""
    lang, raw = m.group(1), m.group(2)
    raw = raw.split("#")[0].split("?")[0]
    while raw.endswith(")") and raw.count(")") > raw.count("("):
        raw = raw[:-1]
    raw = raw.rstrip(".,;")
    title = urllib.parse.unquote(raw).replace("_", " ")
    return lang, title, f"https://{lang}.wikipedia.org/wiki/{raw}"


def hillview_link_coords(url: str) -> tuple[float, float] | None:
    """A hillview.cz link whose query is nothing but lat/lon (zoom allowed)
    points at a place, so its position IS the annotator's coordinates. With
    anything else on it (photo=…, bearing=…) the lat/lon is just the map centre
    of some view — kept as a link for the operator, not as coordinates."""
    m = HILLVIEW_RE.match(url)
    if not m:
        return None
    q = urllib.parse.parse_qs(m.group(1), keep_blank_values=True)
    if not {"lat", "lon"} <= set(q) or not set(q) <= {"lat", "lon", "zoom"}:
        return None
    try:
        return float(q["lat"][0]), float(q["lon"][0])
    except (ValueError, IndexError):
        return None

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
    # Per-segment interpretation, parallel to segments: name | context | coords |
    # wiki | url | other. The ONE place segment identity is decided — downstream
    # (graduation etc.) addresses segments by role, never by re-matching regexes.
    roles: list[str] = field(default_factory=list)
    name: str | None = None
    context: str | None = None
    coords: tuple[float, float] | None = None            # (lat, lon)
    wiki: tuple[str, str] | None = None                  # (lang, title)
    wiki_url: str | None = None
    links: list[str] = field(default_factory=list)       # non-wiki URLs, body order
    coords_from_link: bool = False                       # coords came from a hillview link
    poi_key: str | None = None                           # "id=<key>" segment
    type_guess: str | None = None
    uncertain: bool = False
    oops: bool = False
    unnamed: bool = False


def _coord_float(s: str) -> float:
    return float(s.replace(",", "."))


def _hemisphere(value: float, letter: str | None, negative: str) -> float:
    """A leading minus already signed the value; an S/W letter forces the
    southern/western hemisphere. N/E (and no letter) leave it as parsed."""
    return -abs(value) if (letter or "").upper() == negative else value


def _coords_from_match(m: re.Match) -> tuple[float, float]:
    return (_hemisphere(_coord_float(m.group(1)), m.group(2), "S"),
            _hemisphere(_coord_float(m.group(3)), m.group(4), "W"))


def _segment_role(i: int, seg: str) -> str:
    if POI_KEY_RE.match(seg):
        return "poiKey"
    if WIKI_RE.search(seg):
        return "wiki"
    # segment 0 is the name slot; it only counts as coords when it is NOTHING
    # but a coordinate pair (embedded coords after a name stay part of the name)
    if COORD_RE.search(seg) and (i > 0 or COORD_RE.fullmatch(seg)):
        return "coords"
    if URL_RE.search(seg):
        return "url"
    if i == 0:
        return "name"
    if i == 1:
        return "context"
    return "other"


def _type_guess(*texts: str | None) -> str | None:
    blob = " ".join(t for t in texts if t).lower()
    for kw, t in TYPE_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}\b", blob):
            return t
    return None


def parse_body(body: str | None) -> ParsedBody:
    raw = body or ""
    parts = [p.strip() for p in raw.split("|")] if raw else []
    result = ParsedBody(raw=raw, segments=parts,
                        roles=[_segment_role(i, p) for i, p in enumerate(parts)])

    name0 = parts[0] if parts else ""
    if name0.lower() == "oops" or raw.lower().startswith("oops"):
        result.oops = True

    for p in parts:
        k = POI_KEY_RE.match(p)
        if k and result.poi_key is None:
            result.poi_key = k.group(1)
            continue
        m = COORD_RE.search(p)
        if m and result.coords is None:
            result.coords = _coords_from_match(m)
        w = WIKI_RE.search(p)
        if w and result.wiki is None:
            lang, title, url = _wiki_from_match(w)
            result.wiki = (lang, title)
            result.wiki_url = url
        for u in URL_RE.findall(p):
            if not WIKI_RE.match(u):
                result.links.append(u.rstrip(".,;)"))
    if result.coords is None:
        for u in result.links:
            c = hillview_link_coords(u)
            if c:
                result.coords, result.coords_from_link = c, True
                break

    if len(parts) > 1 and result.roles[1] == "context":
        result.context = parts[1] or None

    if parts and result.roles[0] != "name":
        # first segment is a wiki URL / pure coordinates — no name to extract;
        # a wikipedia page title is the next best name (proposed like any label)
        result.unnamed = True
        if result.wiki and not any(r == "name" for r in result.roles):
            result.name = result.wiki[1]
    else:
        name = name0.rstrip("?").replace("(?)", "").strip()
        result.uncertain = name0.endswith("?") or "(?)" in name0
        if not name or name == "?":
            result.unnamed = True
        else:
            result.name = name

    if not result.oops:
        result.type_guess = _type_guess(result.name, result.context)
    return result
