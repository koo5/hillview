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


# every predicate facts.facts_for can emit — only these are the parser's to retire
PARSER_PREDICATES = ("onPhoto", "labelText", "context", "wikipediaPage", "webPage",
                     "embeddedCoords", "typeGuess", "uncertain", "oopsMarker",
                     "unnamed", "poiKey")


async def _retire_stale_parser_facts(ann_ids: list[str], emitted: set[str],
                                     run_id) -> int:
    """Reject (noted) the uncurated parser-predicate facts about `ann_ids` whose
    fact graph is not in `emitted`. → number retired."""
    if not ann_ids:
        return 0
    preds = " ".join(f"hv:{p}" for p in PARSER_PREDICATES)
    retired = 0
    for i in range(0, len(ann_ids), 400):
        values = " ".join(f"<{graph.annotation_iri(a)}>" for a in ann_ids[i:i + 400])
        res = await graph.store.query(f"""{graph.PREFIXES}
SELECT ?f WHERE {{
  VALUES ?ann {{ {values} }}
  VALUES ?p {{ {preds} }}
  GRAPH ?f {{ ?ann ?p ?o }}
  FILTER NOT EXISTS {{ GRAPH <{graph.GRAPH_CURATION}> {{ ?f hv:status ?s }} }}
}}""")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for b in res["results"]["bindings"]:
            f = b["f"]["value"]
            if f in emitted:
                continue
            await graph.store.update(facts.curate_update(
                f, "rejected", now,
                note=f"superseded by re-parse (parser v{PARSER_VERSION}, run {run_id})"))
            retired += 1
    return retired


async def parse_annotations(where: str, params: dict, scope: str,
                            photo_id: str | None = None,
                            annotation_ids: list[str] | None = None,
                            note: str | None = None) -> dict:
    """Parse the current annotation rows matching `where` into facts, as one
    annotation_parse run. Content-addressed: re-emitting an unchanged body is a
    no-op on the fact graphs (curation survives). Shared by the endpoint and the
    post-sync derivation (sync.sync_and_derive)."""
    async with wb_engine.connect() as conn:
        rows = (await conn.execute(text(
            f"SELECT a.id, a.photo_id, a.body FROM annotation_mirror a WHERE {where}"),
            params)).all()

    run_id = await create_run(
        kind="annotation_parse",
        params={"scope": scope, "photo_id": photo_id,
                "annotation_ids": annotation_ids,
                "parser_version": PARSER_VERSION},
        note=note)
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
                run_id, started, json.dumps({"scope": scope})))

        # retire what this parse no longer says: uncurated parser facts about
        # these annotations whose fact graph is not among the ones just emitted
        # (a body edit or a parser fix — e.g. v5's ")"-keeping wiki titles —
        # otherwise leaves the old statement standing next to the new one, and
        # downstream picks between them arbitrarily). Curated facts are never
        # touched: an approved label / attached page is a human decision.
        retired = await _retire_stale_parser_facts(
            [p["id"] for p in parsed], set(payload["fact_graphs"]), run_id)

        stats = {
            "annotations": len(parsed),
            "facts": payload["n_facts"],
            "retired": retired,
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
        raise


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
    try:
        return await parse_annotations(where, params, req.scope, req.photo_id,
                                       req.annotation_ids, req.note)
    except Exception as e:
        raise HTTPException(500, f"parse run failed: {e}")
