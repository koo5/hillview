#!/usr/bin/env python3
"""Warn when the container the suite targets is older than its source.

The suite's frontend target is `FRONTEND_URL` (Playwright's baseURL), defaulting
to the live Vite dev server on :8212. Override it to the built frontend container
on :3000 and the tests run compiled output that holds NO source — so editing
frontend/src without rebuilding silently tests stale code (this is exactly how a
Firefox-only upload bug hid behind a not-rebuilt frontend).

So we resolve FRONTEND_URL first:
  - dev server (:8212) or any non-watched port -> source is live / not ours: skip
  - a remote host                              -> image isn't local to inspect: skip
  - localhost:3000 (the frontend container)    -> compare its *image build time*
    against the mtimes of the source paths that feed its build; warn + list newer.

Backend isn't keyed here: in the dev compose api/worker bind-mount their source
(`./backend/api/app`, `./backend/worker`), so they're always live.

Exit code: 0 always, unless --strict is passed and the target is stale (then 1).
"""
import argparse
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Must match the Playwright config default (frontend/tests-playwright/playwright.config.ts).
FRONTEND_URL_DEFAULT = "http://localhost:8212"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", ""}

# Published port the suite may target -> the built container behind it and the
# source paths (relative to repo root) baked into its image. The dev server
# (:8212) is intentionally absent: it serves live source, nothing to rebuild.
FRONTEND_TARGET = {
	"container": "hillview_frontend",
	"sources": [
		"frontend/src",
		"frontend/static",
		"frontend/package.json",
		"frontend/bun.lock",
		"frontend/Dockerfile",
		"frontend/svelte.config.js",
		"frontend/vite.config.ts",
	],
}

TARGETS = {3000: FRONTEND_TARGET}

# Hosts whose origin is a Caddy vhost proxying into the built frontend container
# rather than the dev server. Keyed by host because they answer on :443, which no
# port rule can distinguish from any other https origin — and these are exactly
# the profiles that serve compiled output, so skipping them would disable this
# check precisely where it is needed. Keep in sync with scripts/host_profiles.py.
CADDY_FRONTEND_HOSTS = {
	"hv.jj.internal",
	"hv.dev4.local",
	"hv.dev4.jj.internal",
}

MAX_LISTED = 12


def _docker(*args):
	"""Run a docker command, returning stripped stdout or None on any failure."""
	try:
		out = subprocess.run(
			["docker", *args],
			capture_output=True, text=True, timeout=15,
		)
	except (FileNotFoundError, subprocess.TimeoutExpired):
		return None
	if out.returncode != 0:
		return None
	return out.stdout.strip()


def image_built_at(container):
	"""UTC epoch seconds when the container's *image* was built, or None."""
	image = _docker("inspect", "-f", "{{.Image}}", container)
	if not image:
		return None  # container not running / not found
	created = _docker("inspect", "-f", "{{.Created}}", image)
	if not created:
		return None
	return _parse_rfc3339(created)


def _parse_rfc3339(s):
	"""Parse docker's RFC3339 timestamp (nanoseconds + 'Z') to UTC epoch seconds."""
	s = s.strip().replace("Z", "+00:00")
	# Python's fromisoformat rejects >6 fractional digits; trim nanoseconds.
	if "." in s:
		head, frac = s.split(".", 1)
		# frac looks like "123456789+00:00"
		digits = frac[:len(frac) - len(frac.lstrip("0123456789"))]
		rest = frac[len(digits):]
		s = f"{head}.{digits[:6]}{rest}"
	try:
		return datetime.fromisoformat(s).astimezone(timezone.utc).timestamp()
	except ValueError:
		return None


def newer_files(paths, built_at):
	"""Files under `paths` whose mtime is newer than `built_at`."""
	stale = []
	for rel in paths:
		abspath = os.path.join(REPO, rel)
		if not os.path.exists(abspath):
			continue
		if os.path.isfile(abspath):
			candidates = [abspath]
		else:
			candidates = (
				os.path.join(root, f)
				for root, _dirs, files in os.walk(abspath)
				for f in files
			)
		for f in candidates:
			try:
				if os.path.getmtime(f) > built_at:
					stale.append(os.path.relpath(f, REPO))
			except OSError:
				continue
	return sorted(stale)


def frontend_url():
	"""FRONTEND_URL from the environment, else scripts/set_host.py's block in .env.

	Same resolution order as playwright.config.ts, so this check and the suite
	can never disagree about which origin is being tested.
	"""
	if os.environ.get("FRONTEND_URL"):
		return os.environ["FRONTEND_URL"]
	value = None
	try:
		with open(os.path.join(REPO, ".env")) as handle:
			for line in handle:
				match = re.match(r"^\s*FRONTEND_URL=(.*)$", line)
				if match:  # last active declaration wins
					value = match.group(1).strip().strip("\"'")
	except OSError:
		return FRONTEND_URL_DEFAULT
	return value or FRONTEND_URL_DEFAULT


def resolve_target():
	"""(target, url) for the container the suite hits, or (None, url) to skip."""
	url = frontend_url()
	parsed = urllib.parse.urlparse(url)
	if (parsed.hostname or "") in CADDY_FRONTEND_HOSTS:
		# A Caddy vhost fronting the built frontend container. Whether that
		# container is local is settled by looking it up rather than by the
		# hostname — the dev4 vhosts are local when run ON dev4, remote here —
		# and main() already skips cleanly when it isn't running.
		return FRONTEND_TARGET, url
	port = parsed.port or (443 if parsed.scheme == "https" else 80)
	target = TARGETS.get(port)
	if target is None:
		print(f"freshness: tests target {url} — live dev server or unwatched port; "
		      f"skipping image check")
		return None, url
	if (parsed.hostname or "") not in LOCAL_HOSTS:
		print(f"freshness: tests target remote {url} — image is not local to inspect; "
		      f"skipping")
		return None, url
	return target, url


def main():
	ap = argparse.ArgumentParser(description=__doc__)
	ap.add_argument("--strict", action="store_true",
	                help="exit 1 if the targeted container is stale (default: warn only)")
	opts = ap.parse_args()

	target, _url = resolve_target()
	if target is None:
		return 0

	container = target["container"]
	built_at = image_built_at(container)
	if built_at is None:
		print(f"freshness: {container} not running — skipped")
		return 0

	stale = newer_files(target["sources"], built_at)
	if not stale:
		print(f"freshness: {container} image is up to date with the working tree")
		return 0

	built_str = datetime.fromtimestamp(built_at, timezone.utc).isoformat(timespec="seconds")
	print(f"\n⚠️  freshness: {container} image was built {built_str}, but "
	      f"{len(stale)} source file(s) are newer — tests may run STALE code:")
	for f in stale[:MAX_LISTED]:
		print(f"      {f}")
	if len(stale) > MAX_LISTED:
		print(f"      ... and {len(stale) - MAX_LISTED} more")

	return 1 if opts.strict else 0


if __name__ == "__main__":
	sys.exit(main())
