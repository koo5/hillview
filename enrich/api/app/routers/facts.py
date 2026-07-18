"""POST /api/facts/curate — record a curation decision about a fact-graph URI.
Plain DELETE/INSERT on the curation graph; keyed to the content-addressed fact IRI,
so decisions survive re-parses by construction."""
import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import facts, graph

router = APIRouter()


class CurateRequest(BaseModel):
    fact: str                     # fact-graph IRI
    decision: str                 # approved | rejected | proposed
    note: str | None = None


@router.post("/facts/curate")
async def curate(req: CurateRequest):
    if req.decision not in ("approved", "rejected", "proposed"):
        raise HTTPException(422, "decision must be approved | rejected | proposed")
    if not req.fact.startswith(graph.BASE + "/id/fact/"):
        raise HTTPException(422, f"not a fact-graph IRI: {req.fact}")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    await graph.store.update(
        facts.curate_update(req.fact, req.decision, decided_at_iso=now, note=req.note))
    return {"fact": req.fact, "decision": req.decision, "decided_at": now}
