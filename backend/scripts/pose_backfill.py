#!/usr/bin/env python3
"""
Recompute photos.pitch and photos.roll from each photo's capture stamp.

	cd backend
	uv run --frozen --package hillview-tests scripts/pose_backfill.py --dry-run
	uv run --frozen --package hillview-tests scripts/pose_backfill.py

The values are a function of exif_data and the image's shape
(common/capture_pose.py), so this is
idempotent: re-running after a rule change is the same command, and a second
run writes nothing. Only rows whose values change are written. Deleted photos
are left alone. Needs DATABASE_URL.

The first run also corrects the sign: until migration 045, photos.pitch held
the app's positive-down pitch. Unstamped portrait photos keep that value
negated; every other photo without a measurable stamp loses it. See docs/todo/photo-pose-and-level-gates.md for the numbers this
should print on the 2026-11-15 data.

Neither UPDATE trigger on photos looks at pitch or roll, so this does not bump
content_updated_at or Panoramax sequences: the gates see the new values on the
sequencer's next pass.
"""

import argparse
import asyncio
import os
import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# common.database builds an ASYNC engine: a plain postgresql:// URL would make
# SQLAlchemy reach for psycopg2, which is not installed. Accept it anyway.
if os.environ.get("DATABASE_URL"):
	os.environ["DATABASE_URL"] = re.sub(r"^postgres(ql)?://", "postgresql+asyncpg://", os.environ["DATABASE_URL"])

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text
from common.database import SessionLocal
from common.models import Photo
from common.capture_pose import capture_pose

PAGE = 2000
BATCH = 500


def classify(old_pitch, new_pitch, new_roll, counts: Counter) -> None:
	counts["photos"] += 1
	counts["pitch derived"] += new_pitch is not None
	counts["roll derived"] += new_roll is not None
	if old_pitch is not None and new_pitch is None:
		counts["pitch lost"] += 1
	elif old_pitch is None and new_pitch is not None:
		counts["pitch gained"] += 1
	elif old_pitch is not None and new_pitch is not None and old_pitch != new_pitch:
		counts["pitch changed"] += 1
		# The sign fix: a tilted photo whose stored pitch had the other sign.
		counts["pitch sign flipped"] += abs(new_pitch) > 1 and (old_pitch > 0) != (new_pitch > 0)


async def run(args) -> None:
	counts: Counter = Counter()
	changes: list[dict] = []
	last_id = ""
	while True:
		async with SessionLocal() as db:
			rows = (await db.execute(
				select(Photo.id, Photo.exif_data, Photo.width, Photo.height, Photo.pitch, Photo.roll)
				.where(Photo.deleted == False, Photo.id > last_id)
				.order_by(Photo.id)
				.limit(PAGE)
			)).all()
		if not rows:
			break
		last_id = rows[-1].id
		for photo_id, exif_data, width, height, old_pitch, old_roll in rows:
			new_pitch, new_roll = capture_pose(exif_data, width, height)
			classify(old_pitch, new_pitch, new_roll, counts)
			if (new_pitch, new_roll) != (old_pitch, old_roll):
				changes.append({"id": photo_id, "pitch": new_pitch, "roll": new_roll})
		print(f"  read {counts['photos']}", file=sys.stderr)

	for key in ("photos", "pitch derived", "roll derived", "pitch lost", "pitch gained",
				"pitch changed", "pitch sign flipped"):
		print(f"{key:>20}: {counts[key]}", file=sys.stderr)
	print(f"{'rows to write':>20}: {len(changes)}", file=sys.stderr)
	if args.dry_run or not changes:
		return

	stmt = text("UPDATE photos SET pitch = :pitch, roll = :roll WHERE id = :id")
	async with SessionLocal() as db:
		for i in range(0, len(changes), BATCH):
			await db.execute(stmt, changes[i:i + BATCH])
			await db.commit()
			print(f"  wrote {min(i + BATCH, len(changes))}/{len(changes)}", file=sys.stderr)


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--dry-run", action="store_true", help="print the counts, write nothing")
	asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
	main()
