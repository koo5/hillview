"""Enrichment Workbench API.

Admin-only by network posture for M0/M1: every published port binds 127.0.0.1 and
there is no auth. Graduation path: hillview's backend/api/app/auth.py:622
require_admin() — add as a router-level dependency when this grows real exposure."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, graph
from .routers import (annotations, calibrate, facts, geocode, graduation, health,
                      matching, parse, photos, poi, proto, runs, sparql, sync)


@asynccontextmanager
async def lifespan(app: FastAPI):
    applied = await db.init_schema()
    print(f"schema applied: {applied}", flush=True)
    yield
    await graph.store.aclose()
    await db.wb_engine.dispose()
    await db.hv_engine.dispose()


app = FastAPI(title="Hillview Enrichment Workbench", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(sync.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(parse.router, prefix="/api")
app.include_router(sparql.router, prefix="/api")
app.include_router(annotations.router, prefix="/api")
app.include_router(facts.router, prefix="/api")
app.include_router(geocode.router, prefix="/api")
app.include_router(calibrate.router, prefix="/api")
app.include_router(matching.router, prefix="/api")
app.include_router(proto.router, prefix="/api")
app.include_router(photos.router, prefix="/api")
app.include_router(graduation.router, prefix="/api")
app.include_router(poi.router, prefix="/api")
