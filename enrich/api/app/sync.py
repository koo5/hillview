"""Two-tier mirror sync from the hillview source DB. The mirror only GAINS
information:

  * append    — monotone: INSERT rows newer than the watermark
                (COALESCE(record_created_ts, uploaded_at) / created_at).
                Never touches existing rows. Cheap; run often.
  * reconcile — non-destructive repair: compare source-side row hashes
                (md5(to_jsonb(row))) against stored row_hash, upsert changed
                rows, stamp missing_since on rows gone from the source
                (NEVER delete), clear it on reappearance.

Rationale: the source has no updated-at column — analysis/geocode/deleted/
is_current mutate silently — so mutations are only catchable by the reconcile
scan, while inserts are safely watermarkable. See docs/enrichment-workbench.md.

Also runnable as a CLI: python -m app.sync [append|reconcile|backfill]
"""
import asyncio
import sys

from sqlalchemy import text

from .db import hv_engine, wb_engine
from .runs import create_run, fail_run, finish_run

BATCH = 1000

# ---------------------------------------------------------------------------
# column plumbing
# ---------------------------------------------------------------------------

PHOTO_PLAIN = [
    "id", "owner_id", "filename", "original_filename", "file_md5",
    "altitude", "compass_angle", "width", "height",
    "captured_at", "uploaded_at", "effective_at", "record_created_ts",
    "title", "description", "place_name",
    "processing_status", "is_public", "deleted", "version",
]
PHOTO_JSON = ["geocode", "sizes", "exif_data", "analysis", "detected_objects"]

ANN_PLAIN = [
    "id", "photo_id", "user_id", "body",
    "is_current", "superseded_by", "created_at", "event_type",
    # graduated-from-workbench provenance: lets the workbench observe that a
    # native annotation has landed in hillview (and retire the local copy)
    "source_annotation_id",
]
ANN_JSON = ["target"]


def _select_sql(table: str, plain: list[str], json_cols: list[str],
                has_geom: bool, wm_expr: str) -> str:
    cols = list(plain)
    cols += [f"{c}::text AS {c}" for c in json_cols]
    if has_geom:
        cols.append("encode(ST_AsEWKB(geometry), 'hex') AS geom_hex")
    cols.append(f"md5(to_jsonb(t)::text) AS row_hash")
    cols.append(f"{wm_expr} AS wm")
    return f"SELECT {', '.join(cols)} FROM {table} t"


def _upsert_sql(mirror: str, plain: list[str], json_cols: list[str],
                has_geom: bool, on_conflict_update: bool) -> str:
    cols = list(plain) + list(json_cols) + (["geometry"] if has_geom else [])
    cols += ["row_hash", "synced_at", "missing_since"]
    vals = [f":{c}" for c in plain]
    vals += [f"CAST(:{c} AS jsonb)" for c in json_cols]
    if has_geom:
        vals.append("CAST(:geom_hex AS geometry)")
    vals += [":row_hash", "now()", "NULL"]
    sql = (f"INSERT INTO {mirror} ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
           f"ON CONFLICT (id) DO ")
    if on_conflict_update:
        sets = [f"{c} = EXCLUDED.{c}" for c in cols if c != "synced_at"]
        sets.append("synced_at = now()")
        sql += "UPDATE SET " + ", ".join(sets)
    else:
        sql += "NOTHING"
    return sql


PHOTO_WM = "COALESCE(record_created_ts, uploaded_at, 'epoch'::timestamptz)"
ANN_WM = "COALESCE(created_at, 'epoch'::timestamptz)"

SPECS = {
    "photo_mirror": dict(source="photos", plain=PHOTO_PLAIN, json_cols=PHOTO_JSON,
                         has_geom=True, wm_expr=PHOTO_WM),
    "annotation_mirror": dict(source="photo_annotations", plain=ANN_PLAIN,
                              json_cols=ANN_JSON, has_geom=False, wm_expr=ANN_WM),
}


def _params(row, spec) -> dict:
    d = {c: row._mapping[c] for c in spec["plain"] + spec["json_cols"]}
    if spec["has_geom"]:
        d["geom_hex"] = row._mapping["geom_hex"]
    d["row_hash"] = row._mapping["row_hash"]
    return d


# ---------------------------------------------------------------------------
# append tier (monotone)
# ---------------------------------------------------------------------------

async def sync_append() -> dict:
    stats = {}
    for mirror, spec in SPECS.items():
        async with wb_engine.connect() as wb:
            wm_row = (await wb.execute(text(
                "SELECT watermark FROM sync_state WHERE table_name = :t"),
                {"t": mirror})).first()
        watermark = wm_row[0] if wm_row and wm_row[0] else None

        sel = _select_sql(spec["source"], spec["plain"], spec["json_cols"],
                          spec["has_geom"], spec["wm_expr"])
        cond = f"WHERE {spec['wm_expr']} > :wm" if watermark else ""
        q = f"{sel} {cond} ORDER BY wm, id"
        ins = _upsert_sql(mirror, spec["plain"], spec["json_cols"],
                          spec["has_geom"], on_conflict_update=False)

        async with wb_engine.connect() as wb:
            before = (await wb.execute(text(f"SELECT count(*) FROM {mirror}"))).scalar()

        scanned = 0
        new_wm = watermark
        async with hv_engine.connect() as hv:
            result = await hv.stream(text(q), {"wm": watermark} if watermark else {})
            async for chunk in result.partitions(BATCH):
                params = [_params(r, spec) for r in chunk]
                async with wb_engine.begin() as wb:
                    await wb.execute(text(ins), params)
                scanned += len(params)
                new_wm = chunk[-1]._mapping["wm"]

        async with wb_engine.connect() as wb:
            after = (await wb.execute(text(f"SELECT count(*) FROM {mirror}"))).scalar()
        inserted = after - before

        async with wb_engine.begin() as wb:
            await wb.execute(text(
                "INSERT INTO sync_state (table_name, watermark, last_append_at) "
                "VALUES (:t, :wm, now()) "
                "ON CONFLICT (table_name) DO UPDATE SET "
                "watermark = COALESCE(EXCLUDED.watermark, sync_state.watermark), "
                "last_append_at = now()"),
                {"t": mirror, "wm": new_wm})
        stats[mirror] = {"inserted": inserted, "scanned": scanned, "watermark": str(new_wm)}
    return stats


# ---------------------------------------------------------------------------
# reconcile tier (non-destructive repair)
# ---------------------------------------------------------------------------

async def sync_reconcile() -> dict:
    stats = {}
    for mirror, spec in SPECS.items():
        # 1. id -> hash maps on both sides
        async with hv_engine.connect() as hv:
            src = dict((await hv.execute(text(
                f"SELECT id, md5(to_jsonb(t)::text) FROM {spec['source']} t"))).all())
        # annotation_mirror can hold workbench-native rows (origin<>'hillview')
        # that have no source row — they must never be stamped missing
        native = mirror == "annotation_mirror"
        oc = ", origin" if native else ""
        async with wb_engine.connect() as wb:
            mir = {r[0]: (r[1], r[2], (r[3] if native else "hillview"))
                   for r in (await wb.execute(text(
                       f"SELECT id, row_hash, missing_since{oc} FROM {mirror}"))).all()}

        changed = [i for i, h in src.items() if i not in mir or mir[i][0] != h]
        missing = [i for i in mir
                   if i not in src and mir[i][1] is None and mir[i][2] == "hillview"]
        reappeared = [i for i, h in src.items()
                      if i in mir and mir[i][1] is not None and mir[i][0] == h]

        # 2. upsert changed/new rows (missing_since cleared by the upsert itself)
        sel = _select_sql(spec["source"], spec["plain"], spec["json_cols"],
                          spec["has_geom"], spec["wm_expr"])
        ups = _upsert_sql(mirror, spec["plain"], spec["json_cols"],
                          spec["has_geom"], on_conflict_update=True)
        for i in range(0, len(changed), BATCH):
            ids = changed[i:i + BATCH]
            async with hv_engine.connect() as hv:
                rows = (await hv.execute(text(f"{sel} WHERE t.id = ANY(:ids)"),
                                         {"ids": ids})).all()
            if rows:
                async with wb_engine.begin() as wb:
                    await wb.execute(text(ups), [_params(r, spec) for r in rows])

        # 3. stamp vanished rows (never delete); clear reappeared-identical rows
        async with wb_engine.begin() as wb:
            if missing:
                await wb.execute(text(
                    f"UPDATE {mirror} SET missing_since = now() "
                    f"WHERE id = ANY(:ids) AND missing_since IS NULL"),
                    {"ids": missing})
            if reappeared:
                await wb.execute(text(
                    f"UPDATE {mirror} SET missing_since = NULL WHERE id = ANY(:ids)"),
                    {"ids": reappeared})
            # retire a workbench-native annotation once its graduated hillview copy
            # has landed (a mirrored row now references it) — no duplicate, and the
            # export stops re-emitting it
            if native:
                # source_annotation_id is the native annotation's IRI; the local
                # id is its last path segment (regexp is a no-op on a bare id, so
                # this also matches older bare-uuid packages)
                await wb.execute(text(
                    f"UPDATE {mirror} SET missing_since = now(), is_current = false "
                    f"WHERE origin = 'workbench' AND missing_since IS NULL AND id IN "
                    f"(SELECT regexp_replace(source_annotation_id, '^.*/', '') "
                    f" FROM {mirror} WHERE source_annotation_id IS NOT NULL)"))
            await wb.execute(text(
                "INSERT INTO sync_state (table_name, last_reconcile_at, stats) "
                "VALUES (:t, now(), CAST(:s AS jsonb)) "
                "ON CONFLICT (table_name) DO UPDATE SET "
                "last_reconcile_at = now(), stats = EXCLUDED.stats"),
                {"t": mirror, "s": __import__("json").dumps(
                    {"source_rows": len(src), "changed": len(changed),
                     "missing_stamped": len(missing), "reappeared": len(reappeared)})})
        stats[mirror] = {"source_rows": len(src), "changed": len(changed),
                         "missing_stamped": len(missing), "reappeared": len(reappeared)}
    return stats


# ---------------------------------------------------------------------------
# run wrapper + CLI
# ---------------------------------------------------------------------------

sync_lock = asyncio.Lock()


async def run_sync(mode: str) -> dict:
    """Execute one sync tier as a runs-row-tracked operation."""
    fn = {"append": sync_append, "reconcile": sync_reconcile}[mode]
    run_id = await create_run(kind=f"sync_{mode}")
    try:
        stats = await fn()
        await finish_run(run_id, stats=stats)
        return {"run_id": str(run_id), "status": "succeeded", "stats": stats}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise


async def _main(argv: list[str]) -> None:
    modes = argv or ["backfill"]
    if modes == ["backfill"]:
        modes = ["append", "reconcile"]
    for m in modes:
        print(f"== sync {m} ==", flush=True)
        out = await run_sync(m)
        print(out, flush=True)


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
