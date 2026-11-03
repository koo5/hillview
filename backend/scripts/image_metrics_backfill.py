#!/usr/bin/env python3
"""
Backfill photos.image_metrics.sharpness — the DB ends of a three-step pipeline.

	cd backend
	uv run --frozen --package hillview-tests scripts/image_metrics_backfill.py export > todo.jsonl
	(worker) sharpness_cli.py todo.jsonl results.jsonl
	uv run --frozen --package hillview-tests scripts/image_metrics_backfill.py apply results.jsonl

The middle step lives in the worker and never touches the database; this
script only reads rows out and writes results back. Needs DATABASE_URL.

export: completed, undeleted photos with a full variant and no sharpness yet
(--remeasure: all of them; --below-version N: those measured by an older
version), narrower than BACKFILL_MAX_SOURCE_WIDTH unless --include-large. Each line carries the full variant's URL and pixel size, the frame
the detections are in, and EVERY recorded detection box. All boxes are masked,
not only those flagged blurred: older photos were anonymized under earlier
thresholds and the normalized flag reconstructs, not records, what was painted.

apply: writes each result's sharpness document (plus the URL it was measured
on and when) into image_metrics->'sharpness', leaving other keys alone. Error
lines are skipped. Neither UPDATE trigger on photos looks at image_metrics, so
this does not bump content_updated_at or Panoramax sequences.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func, or_, text, Integer
from common.database import SessionLocal
from common.models import Photo

BATCH = 500

# Not backfilled: sources this wide are curated camera work (in the 2026-11
# data exactly the Canon EOS 5DS frames and the hand-stitched panoramas), which
# practically never has the whole-frame shake or defocus this metric is for.
# They stay unmeasured (NULL); the worker measures new uploads of any size.
BACKFILL_MAX_SOURCE_WIDTH = 8_000


def boxes_of(detected_objects) -> list[list[int]]:
	if not isinstance(detected_objects, dict):
		return []
	boxes = []
	for obj in detected_objects.get("objects") or []:
		b = obj.get("bbox") if isinstance(obj, dict) else None
		if b and all(k in b for k in ("x1", "y1", "x2", "y2")):
			boxes.append([b["x1"], b["y1"], b["x2"], b["y2"]])
	return boxes


async def export(args):
	sharpness = Photo.image_metrics['sharpness']
	stmt = (
		select(Photo.id, Photo.sizes, Photo.width, Photo.height, Photo.detected_objects)
		.where(Photo.processing_status == 'completed', Photo.deleted == False)
	)
	if not args.include_large:
		stmt = stmt.where(or_(Photo.width.is_(None), Photo.width < BACKFILL_MAX_SOURCE_WIDTH))
	if args.below_version is not None:
		stmt = stmt.where(or_(sharpness.is_(None),
			func.coalesce(sharpness['version'].astext.cast(Integer), 0) < args.below_version))
	elif not args.remeasure:
		stmt = stmt.where(or_(Photo.image_metrics.is_(None), sharpness.is_(None)))
	stmt = stmt.order_by(func.random() if args.sample else Photo.id)
	if args.limit:
		stmt = stmt.limit(args.limit)

	async with SessionLocal() as db:
		rows = (await db.execute(stmt)).all()

	written = no_full = 0
	for photo_id, sizes, width, height, detected in rows:
		full = (sizes or {}).get("full") or {}
		if not full.get("url") or not full.get("width") or not full.get("height"):
			no_full += 1
			continue
		print(json.dumps({
			"id": photo_id,
			"url": full["url"],
			"width": full["width"],
			"height": full["height"],
			"source_width": width or full["width"],
			"source_height": height or full["height"],
			"boxes": boxes_of(detected),
		}))
		written += 1
	print(f"exported {written}, skipped {no_full} without a full variant", file=sys.stderr)


async def apply(args):
	measured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
	params, errors, bad = [], 0, 0
	with (open(args.results) if args.results != "-" else sys.stdin) as f:
		for line in f:
			if not line.strip():
				continue
			row = json.loads(line)
			if "sharpness" not in row:
				errors += 1
				continue
			if not isinstance(row["sharpness"], dict) or "version" not in row["sharpness"]:
				bad += 1
				continue
			doc = {**row["sharpness"], "source_url": row.get("url"), "measured_at": measured_at}
			params.append({"id": row["id"], "doc": json.dumps(doc)})

	print(f"{len(params)} results to apply, {errors} error lines skipped, {bad} malformed", file=sys.stderr)
	if args.dry_run or not params:
		return

	stmt = text("""
		UPDATE photos
		SET image_metrics = coalesce(image_metrics, '{}'::jsonb) || jsonb_build_object('sharpness', CAST(:doc AS jsonb))
		WHERE id = :id
	""")
	updated = 0
	async with SessionLocal() as db:
		for i in range(0, len(params), BATCH):
			batch = params[i:i + BATCH]
			await db.execute(stmt, batch)
			await db.commit()
			updated += len(batch)
			print(f"  {updated}/{len(params)}", file=sys.stderr)


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	sub = parser.add_subparsers(dest="command", required=True)

	ex = sub.add_parser("export", help="photos to measure, as JSONL on stdout")
	ex.add_argument("--limit", type=int)
	ex.add_argument("--sample", action="store_true", help="random order (with --limit: a random sample)")
	ex.add_argument("--include-large", action="store_true",
					help=f"also export sources {BACKFILL_MAX_SOURCE_WIDTH}+ px wide (skipped by default)")
	group = ex.add_mutually_exclusive_group()
	group.add_argument("--remeasure", action="store_true", help="include photos already measured")
	group.add_argument("--below-version", type=int, metavar="N", help="only unmeasured or measured by a version < N")

	ap = sub.add_parser("apply", help="write sharpness_cli.py results into image_metrics")
	ap.add_argument("results", help="results JSONL, or - for stdin")
	ap.add_argument("--dry-run", action="store_true")

	args = parser.parse_args()
	asyncio.run(export(args) if args.command == "export" else apply(args))


if __name__ == "__main__":
	main()
