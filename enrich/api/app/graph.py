"""Oxigraph client (HTTP SPARQL protocol) + the workbench IRI scheme.

Conventions (docs/enrichment-workbench.md): plain SPARQL 1.1 quads, every graph
name a minted URI — no RDF-star, no reification, no blank nodes. Fact-graph
content addressing lives in facts.py; this module is transport + namespaces."""
import httpx

from . import config

# Identifier namespace: rdf.hillview.cz — deliberately DISTINCT from the web app's
# hillview.cz, so URIs read as identifiers, not web addresses. The rdf subdomain can
# later serve a dereferencing RDF viewer. Web pages are referenced explicitly via
# dedicated predicates (hv:webPage, hv:wikipediaPage) — never conflated with IRIs.
BASE = "https://rdf.hillview.cz"
NS = f"{BASE}/ns#"
WEB_BASE = "https://hillview.cz"
GRAPH_META = f"{BASE}/id/graph/meta"
GRAPH_CURATION = f"{BASE}/id/graph/curation"
LOCAL_ADMIN = f"{BASE}/id/user/local-admin"

PREFIXES = f"""\
PREFIX hv: <{NS}>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
"""


def photo_iri(photo_id: str) -> str:
    return f"{BASE}/id/photo/{photo_id}"


def annotation_iri(ann_id: str) -> str:
    return f"{BASE}/id/annotation/{ann_id}"


def run_iri(run_id) -> str:
    return f"{BASE}/id/run/{run_id}"


def fact_iri(hash16: str) -> str:
    return f"{BASE}/id/fact/{hash16}"


def geo_uri(lat: float, lon: float) -> str:
    """RFC 5870 point identifier, canonical 5-decimal form (≈1 m). Used as the
    anchorCandidate object for author/curator-pinned points and body-embedded
    coords — the canonical form makes body-serialization → re-parse → re-mint
    land on the SAME fact IRI (idempotent round-trip)."""
    return f"geo:{lat:.5f},{lon:.5f}"


def parse_geo_uri(uri: str) -> tuple[float, float] | None:
    """geo:lat,lon → (lat, lon). Coords live in the identifier itself, so geo:
    candidates need no coords metadata facts."""
    if not uri.startswith("geo:"):
        return None
    try:
        lat, lon = uri[4:].split(";")[0].split(",")[:2]
        return float(lat), float(lon)
    except ValueError:
        return None


def proto_annotation_iri(hash16: str) -> str:
    """Workbench-born annotation candidate (reverse POI-placement workflow).
    hash16 = sha256(f"{photo_id}|{wiki_url}")[:16] — deterministic, so re-placing
    the same POI on the same pano re-mints the same proto and stays idempotent."""
    return f"{BASE}/id/proto-annotation/{hash16}"


def poi_iri(poi_id: str) -> str:
    """An abstract Point Of Interest — the shared subject that several annotations
    (across different photos) can each depict, via `annotation hv:depicts poi`.
    It's a first-class node so the triangulated location and a label hang off IT,
    not off any one annotation. Minted with a uuid at creation (a durable entity,
    not a content-derived fact)."""
    return f"{BASE}/id/poi/{poi_id}"


def photo_web_url(photo_id: str) -> str:
    """The human-facing web page for a photo — an explicit external reference,
    used as the OBJECT of hv:webPage, never as an identifier. The web app keys
    photos by cross-source uid (frontend getCanonicalPhotoUrl): hillview-{id}."""
    return f"{WEB_BASE}/photo/hillview-{photo_id}"


class GraphStore:
    def __init__(self, base_url: str | None = None, client: httpx.AsyncClient | None = None):
        self.base = (base_url or config.OXIGRAPH_URL).rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=60)

    async def query(self, sparql: str) -> dict:
        """SELECT/ASK → SPARQL-JSON dict."""
        r = await self._client.post(
            f"{self.base}/query",
            content=sparql.encode(),
            headers={"Content-Type": "application/sparql-query",
                     "Accept": "application/sparql-results+json"},
        )
        r.raise_for_status()
        return r.json()

    async def update(self, sparql: str) -> None:
        r = await self._client.post(
            f"{self.base}/update",
            content=sparql.encode(),
            headers={"Content-Type": "application/sparql-update"},
        )
        r.raise_for_status()

    async def load_turtle(self, graph_iri: str, turtle: str) -> None:
        """Bulk-load triples into one named graph (Graph Store protocol POST)."""
        r = await self._client.post(
            f"{self.base}/store",
            params={"graph": graph_iri},
            content=turtle.encode(),
            headers={"Content-Type": "text/turtle"},
        )
        r.raise_for_status()

    async def ping(self) -> None:
        await self.query("ASK { }")

    async def aclose(self) -> None:
        await self._client.aclose()


store = GraphStore()
