"""One-pass mirror sync from the hillview source DB. The mirror only GAINS
information: compare source-side row hashes (md5(to_jsonb(row))) against the
stored row_hash, upsert changed AND new rows, stamp missing_since on rows gone
from the source (NEVER delete), clear it on reappearance. Workbench-native rows
(origin <> 'hillview') have no source row and are never stamped.

Rationale: the source has no updated-at column — analysis, geocode, deleted,
is_current, compass_angle all mutate silently — so a full scan is the only thing
that can see a mutation at all. See docs/enrichment-workbench.md.

REMOVED 2026-08-06 — the `append` tier, which INSERTed rows newer than a
watermark (COALESCE(record_created_ts, uploaded_at) / created_at). It was a
latency optimization for a live-DB source that never materialized, and against a
dump-fed source it was a trap: it can never update an existing row (the watermark
filter skips it, and its ON CONFLICT DO NOTHING would skip it anyway), so a
prod-side edit — a corrected compass_angle, say — stayed invisible while both
sides looked self-consistent. It also could not see dump rows at all, since those
carry their prod created_at, behind the watermark. Nothing was lost by removing
it: the scan below already inserts what it inserted, because `changed` includes
every id absent from the mirror.

If the workbench is ever pointed at a LIVE hillview DB and this full scan becomes
too expensive, bring it back as an INTERNAL fast path — never as a mode a human
picks — and only ever PAIRED with a periodic full scan, because a
watermark-bounded pass is structurally incapable of seeing an older row mutate.
sync_state.watermark is left in place, unmaintained, for that day.

Also runnable as a CLI: python -m app.sync
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
    # Per-DEVICE identity (SHA256 fingerprint of the uploading client's public key).
    # 100% populated in production (28.3 k/28.3 k rows, 1424 distinct keys), which makes
    # it the reliable "same camera" signal for app photos — owner alone is not, since one
    # account can upload from several devices, and the app strips camera EXIF entirely.
    # Recon uses it to decide whether one focal is physically shared across a cluster.
    "client_public_key_id",
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
                has_geom: bool) -> str:
    cols = list(plain)
    cols += [f"{c}::text AS {c}" for c in json_cols]
    if has_geom:
        cols.append("encode(ST_AsEWKB(geometry), 'hex') AS geom_hex")
    cols.append(f"md5(to_jsonb(t)::text) AS row_hash")
    return f"SELECT {', '.join(cols)} FROM {table} t"


def _upsert_sql(mirror: str, plain: list[str], json_cols: list[str],
                has_geom: bool) -> str:
    """INSERT … ON CONFLICT DO UPDATE. Always an upsert: a row already in the
    mirror is exactly the case that needs writing (its source changed), which is
    what the removed append tier got backwards."""
    cols = list(plain) + list(json_cols) + (["geometry"] if has_geom else [])
    cols += ["row_hash", "synced_at", "missing_since"]
    vals = [f":{c}" for c in plain]
    vals += [f"CAST(:{c} AS jsonb)" for c in json_cols]
    if has_geom:
        vals.append("CAST(:geom_hex AS geometry)")
    vals += [":row_hash", "now()", "NULL"]
    sets = [f"{c} = EXCLUDED.{c}" for c in cols if c != "synced_at"]
    sets.append("synced_at = now()")
    return (f"INSERT INTO {mirror} ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
            f"ON CONFLICT (id) DO UPDATE SET " + ", ".join(sets))


# "when did this row appear" per table. Unused by the pass below, which scans
# everything — kept because they are the one piece a live-DB fast path would need,
# and rederiving them means rediscovering that photos have no single creation
# timestamp (record_created_ts is absent on older rows).
PHOTO_WM = "COALESCE(record_created_ts, uploaded_at, 'epoch'::timestamptz)"
ANN_WM = "COALESCE(created_at, 'epoch'::timestamptz)"

SPECS = {
    "photo_mirror": dict(source="photos", plain=PHOTO_PLAIN, json_cols=PHOTO_JSON,
                         has_geom=True),
    "annotation_mirror": dict(source="photo_annotations", plain=ANN_PLAIN,
                              json_cols=ANN_JSON, has_geom=False),
}


def _params(row, spec) -> dict:
    d = {c: row._mapping[c] for c in spec["plain"] + spec["json_cols"]}
    if spec["has_geom"]:
        d["geom_hex"] = row._mapping["geom_hex"]
    d["row_hash"] = row._mapping["row_hash"]
    return d


# ---------------------------------------------------------------------------
# the sync pass (non-destructive repair)
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
                          spec["has_geom"])
        ups = _upsert_sql(mirror, spec["plain"], spec["json_cols"],
                          spec["has_geom"])
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


APPEND_GONE = ("the append tier was removed — run the plain sync, which inserts new "
               "rows too and, unlike append, also catches edits to rows already "
               "mirrored (see app/sync.py)")


async def run_sync(mode: str = "sync") -> dict:
    """Execute the sync as a runs-row-tracked operation. `mode` is tolerated for
    older callers: 'reconcile' is this pass's historical name; 'append' is refused
    loudly rather than silently doing something subtly different."""
    if mode == "append":
        raise ValueError(APPEND_GONE)
    if mode not in ("sync", "reconcile"):
        raise ValueError(f"unknown sync mode: {mode}")
    # run kind stays sync_reconcile: the runs history and the /runs filter are
    # full of it, and renaming would orphan every past row for no gain
    run_id = await create_run(kind="sync_reconcile")
    try:
        stats = await sync_reconcile()
        await finish_run(run_id, stats=stats)
        return {"run_id": str(run_id), "status": "succeeded", "stats": stats}
    except Exception as e:
        await fail_run(run_id, f"{type(e).__name__}: {e}")
        raise


async def _main(argv: list[str]) -> None:
    # old invocations (reconcile | backfill) still land on the one pass
    if "append" in argv:
        raise SystemExit(APPEND_GONE)
    print("== sync ==", flush=True)
    print(await run_sync(), flush=True)


if __name__ == "__main__":
    asyncio.run(_main(sys.argv[1:]))
