"""POST /api/parse/run — run the annotation-body parser over mirror rows and load
the resulting facts into Oxigraph (per-fact content-addressed graphs + meta graph)."""
import datetime
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from .. import facts, graph
from ..db import wb_engine
from ..parser import parse_body, PARSER_VERSION
from ..runs import create_run, fail_run, finish_run

router = APIRouter()


class ParseRequest(BaseModel):
    scope: str = "all-current"          # all-current | photo | annotations
    photo_id: str | None = None
    annotation_ids: list[str] | None = None
    note: str | None = None


@router.post("/parse/run")
async def parse_run(req: ParseRequest):
    where = "a.is_current AND a.missing_since IS NULL"
    params: dict = {}
    if req.scope == "photo":
        if not req.photo_id:
            raise HTTPException(422, "photo scope needs photo_id")
        where += " AND a.photo_id = :pid"
        params["pid"] = req.photo_id
    elif req.scope == "annotations":
        if not req.annotation_ids:
            raise HTTPException(422, "annotations scope needs annotation_ids")
        where += " AND a.id = ANY(:ids)"
        params["ids"] = req.annotation_ids
    elif req.scope != "all-current":
        raise HTTPException(422, "scope must be all-current | photo | annotations")

    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT a.id, a.photo_id, a.body FROM annotation_mirror a WHERE {where}"),
            params)).all()

    run_id = await create_run(
        kind="annotation_parse",
        params={"scope": req.scope, "photo_id": req.photo_id,
                "annotation_ids": req.annotation_ids,
                "parser_version": PARSER_VERSION},
        note=req.note)
    try:
        parsed = [{"id": r.id, "photo_id": r.photo_id, "parsed": parse_body(r.body)}
                  for r in rows]
        payload = facts.build_run_payload(parsed, run_id)

        # load every fact graph (content-addressed; re-emitting == same graph, idempotent)
        for g_iri, nt in payload["fact_graphs"].items():
            await graph.store.load_turtle(g_iri, nt)
        # meta graph: run resource + fact->run + fact->annotation links (accumulates)
        started = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await graph.store.load_turtle(
            graph.GRAPH_META,
            payload["meta_turtle"] + facts.run_meta_turtle(
                run_id, started, json.dumps({"scope": req.scope})))

        stats = {
            "annotations": len(parsed),
            "facts": payload["n_facts"],
            "oops": sum(1 for p in parsed if p["parsed"].oops),
            "unnamed": sum(1 for p in parsed if p["parsed"].unnamed),
            "uncertain": sum(1 for p in parsed if p["parsed"].uncertain),
            "with_wiki": sum(1 for p in parsed if p["parsed"].wiki_url),
            "with_coords": sum(1 for p in parsed if p["parsed"].coords),
        }
        await finish_run(run_id, stats=stats, graph_iri=graph.run_iri(run_id))
        return {"run_id": str(run_id), "status": "succeeded", "stats": stats}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise HTTPException(500, f"parse run failed: {e}")
