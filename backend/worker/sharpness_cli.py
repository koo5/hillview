#!/usr/bin/env python3
"""
Measure sharpness for a list of photos: the backfill's middle step.

	scripts/image_metrics_backfill.py export  >  todo.jsonl     (reads the DB)
	worker/sharpness_cli.py todo.jsonl results.jsonl          (this: HTTP + CPU, no DB)
	scripts/image_metrics_backfill.py apply   <  results.jsonl  (writes the DB)

The worker has no database access by design, so this step reads and writes
files only. Each input line is

	{"id", "url", "width", "height", "source_width", "source_height", "boxes": [[x1, y1, x2, y2], ...]}

— url, width and height of the photo's full variant (already anonymized, as
stored), the frame the boxes were detected in, and the boxes that were
actually blurred. Each output line is {"id", "url", "sharpness": {...}} or
{"id", "url", "error": "..."}.

Resumable: ids that already have a sharpness line in the output are skipped,
error lines are retried, new lines are appended.

--local reads from a storage backup first and downloads only what it lacks;
each result line says which ("fetched": "local" | "http"):

	uv run sharpness_cli.py todo.jsonl results.jsonl --local https://pics.hillview.cz/opt/=/shared44/pics/opt/

	uv run sharpness_cli.py todo.jsonl results.jsonl --jobs 4
	uv run sharpness_cli.py todo.jsonl - --limit 20      # a quick look, to stdout
"""

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Sequence
from pathlib import Path

import httpx

import sharpness

USER_AGENT = "hillview-image-metrics/1"
TIMEOUT = httpx.Timeout(60.0, connect=15.0)
CHUNK = 1000   # jobs handed to the pool at a time, instead of one future per photo up front

# glibc gives each thread its own malloc arena, and the decode/download
# buffers (about 1.4 MB per photo) fragment them: RSS grew ~1.3 MB per photo,
# 2 GB after 400, while Python's own heap stayed flat at 4.6 MB. Capping the
# arenas at 2 held RSS flat at ~270 MB. Must happen before any thread starts.
M_ARENA_MAX = -8


def cap_malloc_arenas(n: int = 2) -> None:
	try:
		import ctypes
		ctypes.CDLL("libc.so.6").mallopt(M_ARENA_MAX, n)
	except OSError:
		pass   # not glibc: nothing to cap


def done_ids(path: Path) -> set[str]:
	if not path.exists():
		return set()
	done = set()
	with path.open() as f:
		for line in f:
			line = line.strip()
			if line:
				row = json.loads(line)
				if "sharpness" in row:
					done.add(row["id"])
	return done


def parse_local(specs: list[str]) -> list[tuple[str, Path]]:
	"""--local URL_PREFIX=DIR pairs, longest prefix first."""
	pairs = []
	for spec in specs:
		prefix, sep, directory = spec.partition("=")
		if not sep or not prefix or not directory:
			sys.exit(f"--local expects URL_PREFIX=DIR, got {spec!r}")
		root = Path(directory).resolve()
		if not root.is_dir():
			sys.exit(f"--local {spec!r}: {root} is not a directory")
		pairs.append((prefix, root))
	return sorted(pairs, key=lambda p: -len(p[0]))


def read_local(url: str, local: Sequence[tuple[str, Path]]) -> bytes | None:
	"""The file a local mirror holds for this URL, or None. Never resolves outside the mirror."""
	for prefix, root in local:
		if url.startswith(prefix):
			path = (root / url[len(prefix):]).resolve()
			if path.is_relative_to(root) and path.is_file():
				return path.read_bytes()
			return None
	return None


def fetch(client: httpx.Client, url: str, local: Sequence[tuple[str, Path]]) -> tuple[bytes, str]:
	data = read_local(url, local)
	if data is not None:
		return data, "local"
	response = client.get(url)
	response.raise_for_status()
	return response.content, "http"


def measure_one(client: httpx.Client, job: dict, local: Sequence[tuple[str, Path]] = ()) -> dict:
	out = {"id": job["id"], "url": job["url"]}
	try:
		data, out["fetched"] = fetch(client, job["url"], local)
		out["sharpness"] = sharpness.measure_bytes(
			data, job["width"], job["height"],
			boxes=job.get("boxes") or (),
			source_size=(job.get("source_width") or job["width"], job.get("source_height") or job["height"]),
		)
	except Exception as e:
		out["error"] = f"{type(e).__name__}: {e}"
	return out


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("input", type=Path, help="JSONL from image_metrics_backfill.py export")
	parser.add_argument("output", help="JSONL to append results to, or - for stdout (no resume)")
	parser.add_argument("--jobs", type=int, default=4, help="parallel downloads+measurements (default 4)")
	parser.add_argument("--limit", type=int, help="stop after this many photos")
	parser.add_argument("--local", action="append", default=[], metavar="URL_PREFIX=DIR",
						help="read URLs under URL_PREFIX from DIR when the file is there (a storage "
							 "backup), else download; repeatable")
	args = parser.parse_args()
	cap_malloc_arenas()
	local = parse_local(args.local)

	to_stdout = args.output == "-"
	skip = set() if to_stdout else done_ids(Path(args.output))
	with args.input.open() as f:
		jobs = [job for job in (json.loads(line) for line in f if line.strip()) if job["id"] not in skip]
	if args.limit is not None:
		jobs = jobs[:args.limit]
	print(f"{len(jobs)} to measure, {len(skip)} already done", file=sys.stderr)

	out = sys.stdout if to_stdout else open(args.output, "a")
	lock = threading.Lock()
	ok = failed = 0
	try:
		with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client, \
				ThreadPoolExecutor(max_workers=args.jobs) as pool:
			rows = (row for i in range(0, len(jobs), CHUNK)
					for row in pool.map(lambda job: measure_one(client, job, local), jobs[i:i + CHUNK]))
			for n, row in enumerate(rows, 1):
				with lock:
					out.write(json.dumps(row) + "\n")
					out.flush()
				if "error" in row:
					failed += 1
					print(f"  {row['id']}: {row['error']}", file=sys.stderr)
				else:
					ok += 1
				if n % 100 == 0:
					print(f"{n}/{len(jobs)}: {ok} ok, {failed} failed", file=sys.stderr)
	finally:
		if not to_stdout:
			out.close()
	print(f"done: {ok} ok, {failed} failed", file=sys.stderr)
	sys.exit(1 if failed and not ok else 0)


if __name__ == "__main__":
	main()
