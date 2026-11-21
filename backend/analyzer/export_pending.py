#!/usr/bin/env python3
"""
Export the photos that have no analysis yet, one file per photo.

For every completed, undeleted photo whose photos.analysis is empty (SQL NULL
or a JSON null), oldest effective_at first, write <outdir>/<photo id> holding
just the photo's 640_llm variant URL — the image analyzer.py sends to the
model (see get_image_url in analyzer.py).

Unlike get_image_url this takes the llm variant only, no fallback to the
plain 640/1024/full sizes: a photo without one is reported and skipped.

Existing files are rewritten only when the URL changed; files for photos that
have since been analysed are left alone (--prune removes them).

The order lives in <outdir>/.order: one photo id per line, oldest effective_at
first, exactly the ids that have a file. Filenames carry no order and git keeps
no mtimes, so this manifest is the only ordering that survives a clone.

	uv run export_pending.py /home/koom/repos/koo5/aaa/0/aaa
	uv run export_pending.py --dry-run /home/koom/repos/koo5/aaa/0/aaa
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from sqlalchemy import select, func, or_
from common.database import SessionLocal
from common.models import Photo

LLM_SIZE = "640_llm"
ORDER_FILE = ".order"   # a dotfile, so --prune never takes it for a photo


def llm_url(sizes: dict | None) -> str | None:
	return ((sizes or {}).get(LLM_SIZE) or {}).get("url")


async def pending_photos():
	"""(id, sizes) of every photo still lacking an analysis, oldest effective_at first."""
	stmt = (
		select(Photo.id, Photo.sizes)
		.where(Photo.processing_status == 'completed')
		.where(Photo.deleted == False)
		.where(or_(Photo.analysis.is_(None), func.jsonb_typeof(Photo.analysis) == 'null'))
		# effective_at is trigger-maintained; NULLs (shouldn't exist) go last. id breaks ties for a stable order.
		.order_by(Photo.effective_at.asc().nulls_last(), Photo.id.asc())
	)
	async with SessionLocal() as db:
		return (await db.execute(stmt)).all()


def write_if_changed(path: Path, content: str) -> bool:
	if path.exists() and path.read_text() == content:
		return False
	tmp = path.with_name(f".{path.name}.tmp")
	tmp.write_text(content)
	os.replace(tmp, path)
	return True


async def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("outdir", type=Path)
	parser.add_argument("--dry-run", action="store_true", help="report what would be written, write nothing")
	parser.add_argument("--prune", action="store_true",
						help="delete files whose photo is no longer pending (dotfiles are never touched)")
	args = parser.parse_args()

	if not args.outdir.is_dir():
		sys.exit(f"{args.outdir}: not a directory")

	rows = await pending_photos()
	written = unchanged = 0
	no_llm = []
	ordered_ids = []

	for photo_id, sizes in rows:
		url = llm_url(sizes)
		if not url:
			no_llm.append(photo_id)
			continue
		ordered_ids.append(photo_id)
		if args.dry_run:
			print(f"{photo_id}\t{url}")
			continue
		if write_if_changed(args.outdir / photo_id, url + "\n"):
			written += 1
		else:
			unchanged += 1

	pending_ids = set(ordered_ids)
	order_changed = False
	if not args.dry_run:
		order_changed = write_if_changed(args.outdir / ORDER_FILE, "".join(f"{i}\n" for i in ordered_ids))

	pruned = 0
	if args.prune:
		for path in args.outdir.iterdir():
			if path.is_file() and not path.name.startswith(".") and path.name not in pending_ids:
				if not args.dry_run:
					path.unlink()
				pruned += 1

	print(f"{len(rows)} photos lack an analysis: {written} written, {unchanged} unchanged, "
		  f"{len(no_llm)} skipped (no {LLM_SIZE} variant)"
		  + (f", {pruned} {'would be ' if args.dry_run else ''}pruned" if args.prune else "")
		  + ("" if args.dry_run else f"; {ORDER_FILE} {'updated' if order_changed else 'unchanged'}"),
		  file=sys.stderr)
	if no_llm:
		print(f"no {LLM_SIZE}: " + " ".join(no_llm), file=sys.stderr)


if __name__ == "__main__":
	asyncio.run(main())
