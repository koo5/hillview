"""POST /api/sparql — raw query passthrough to Oxigraph (the full-quads-fun page).
Updates only behind ENRICH_ALLOW_RAW_UPDATE=1; curation goes through /api/facts/curate."""
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config, graph

router = APIRouter()


class SparqlRequest(BaseModel):
    query: str | None = None
    update: str | None = None


@router.post("/sparql")
async def sparql(req: SparqlRequest):
    if req.update is not None:
        if not config.ALLOW_RAW_UPDATE:
            raise HTTPException(403, "raw updates disabled (set ENRICH_ALLOW_RAW_UPDATE=1)")
        try:
            await graph.store.update(req.update)
        except httpx.HTTPStatusError as e:
            raise HTTPException(400, e.response.text[:2000])
        return {"ok": True}
    if not req.query:
        raise HTTPException(422, "provide query or update")
    try:
        return await graph.store.query(req.query)
    except httpx.HTTPStatusError as e:
        raise HTTPException(400, e.response.text[:2000])
