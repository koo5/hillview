#!/usr/bin/env python3
"""Dependency audit + cooloff-aware refresh for every lockfile in the repo.

Policy (see backend/pyproject.toml [tool.uv] and frontend/bunfig.toml [install]):
  - cooloff: never resolve a version published in the last COOLOFF_DAYS
  - minimal-fix: for CVE work move only the vulnerable packages, to the
    reported fix version -- not "everything to latest"

How each toolchain enforces the cooloff, and why this script exists:
  uv     `exclude-newer` is a fixed date in backend/pyproject.toml. It MUST be
         there (not only on the CLI): uv stamps it into uv.lock, and a later
         plain `uv lock`/`uv sync`/`uv add` with a different value throws the
         whole lockfile away and re-resolves from scratch. So a refresh means
         "advance the date, then upgrade" -- that's `deps.py backend`.
  bun    `minimumReleaseAge` in bunfig.toml is relative, nothing to advance.
         `bun update <name>` has two traps this script guards against: a name
         that is NOT a direct dependency gets ADDED to package.json as one, and
         a direct dependency gets its range rewritten to the resolved version.
  cargo  has no cooloff at all. `deps.py cargo` does one `cargo update -p X
         --precise Y` per crate (cargo rejects several --precise in one call)
         and prints the crates.io publish date so you can eyeball the age.

Usage:
    scripts/deps.py audit                          # osv-scanner over every lockfile present
    scripts/deps.py cooloff                        # show the configured window vs. today
    scripts/deps.py backend pillow==12.3.0 h2      # advance exclude-newer, uv lock --upgrade-package each
    scripts/deps.py backend --all                  # advance exclude-newer, uv lock --upgrade
    scripts/deps.py backend pillow --young pillow  # exempt a package whose fix is younger than the window
    scripts/deps.py frontend                       # bun update (all, within ranges); ranges restored after
    scripts/deps.py frontend @sentry/sveltekit     # same, one direct dep (non-direct names are refused)
    scripts/deps.py cargo tauri==2.11.1 rand@0.8.5==0.8.6
    scripts/deps.py images                         # osv-scanner over every image running on this host
    scripts/deps.py images caddy:2-alpine          # ... or the given images (OS packages + bundled deps)
    scripts/deps.py --days 30 backend --all        # wider window for this run
    scripts/deps.py -n backend --all               # print the commands, run nothing

osv-scanner is the snap build: its recursive walk dies on $HOME dotfiles, so
lockfiles are always passed explicitly; it also cannot see the docker CLI, so
images are `docker save`d to a tarball under $HOME (not /tmp, which a snap
sees as its own private one) and scanned with --archive.
"""

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

COOLOFF_DAYS = 14
REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
FRONTEND = REPO / "frontend"
SRC_TAURI = FRONTEND / "src-tauri"

# Every lockfile osv-scanner knows how to read. Missing ones are skipped.
LOCKFILES = [
	"backend/uv.lock",
	"enrich/api/uv.lock",
	"enrich/terrain/requirements.txt",
	"frontend/bun.lock",
	"frontend/src-tauri/Cargo.lock",
	"frontend/tests-appium/bun.lock",
	"frontend/tests-playwright/bun.lock",
	"enrich/web/bun.lock",
]

EXCLUDE_NEWER_RE = re.compile(r'^(exclude-newer\s*=\s*")([^"]+)(")', re.M)


def run(cmd, cwd, dry_run, check=True):
	print(f"$ (cd {Path(cwd).relative_to(REPO) if cwd != REPO else '.'} && {' '.join(cmd)})")
	if dry_run:
		return 0
	return subprocess.run(cmd, cwd=cwd, check=check).returncode


def cutoff(days):
	"""UTC midnight `days` ago, in the form uv stores in uv.lock."""
	d = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days)
	return f"{d.isoformat()}T00:00:00Z"


def current_exclude_newer():
	m = EXCLUDE_NEWER_RE.search((BACKEND / "pyproject.toml").read_text())
	return m.group(2) if m else None


def set_exclude_newer(value, dry_run):
	path = BACKEND / "pyproject.toml"
	text = path.read_text()
	if not EXCLUDE_NEWER_RE.search(text):
		sys.exit(f"{path}: no `exclude-newer = ...` line under [tool.uv]; add one first")
	print(f"exclude-newer: {current_exclude_newer()} -> {value}")
	if not dry_run:
		path.write_text(EXCLUDE_NEWER_RE.sub(rf"\g<1>{value}\g<3>", text, count=1))


def cmd_cooloff(args):
	print(f"window:               {args.days} days -> cutoff {cutoff(args.days)}")
	print(f"backend exclude-newer: {current_exclude_newer()}")
	m = re.search(r"minimumReleaseAge\s*=\s*(\d+)", (FRONTEND / "bunfig.toml").read_text())
	if m:
		print(f"frontend bunfig:       {int(m.group(1)) // 86400} days (minimumReleaseAge = {m.group(1)})")
	print("cargo:                 no cooloff support; check crates.io dates by hand (deps.py cargo prints them)")


def cmd_audit(args):
	present = [p for p in LOCKFILES if (REPO / p).exists()]
	cmd = ["osv-scanner", "scan", "source"]
	for p in present:
		cmd += ["-L", p]
	if args.json:
		cmd += ["--format", "json"]
	# exit 1 = vulnerabilities found, which is the answer, not an error
	rc = run(cmd, REPO, args.dry_run, check=False)
	sys.exit(rc)


def cmd_images(args):
	images = args.images
	if not images:
		# Everything running on this host, not `docker compose config --images`:
		# the compose file needs its overlays (external volumes etc.) to even
		# parse, and the caddy/umami side lives in other projects anyway.
		out = subprocess.run(["docker", "ps", "--format", "{{.Image}}"], capture_output=True, text=True, check=True).stdout
		images = sorted(set(out.split()))
	print("images: " + " ".join(images))
	worst = 0
	work = Path(tempfile.mkdtemp(prefix="osv-images-", dir=Path.home()))
	try:
		for image in images:
			tar = work / (re.sub(r"[^A-Za-z0-9_.-]", "_", image) + ".tar")
			print(f"\n##### {image}")
			if run(["docker", "save", image, "-o", str(tar)], REPO, args.dry_run, check=False):
				print("(not present locally -- docker pull it first)")
				continue
			rc = run(["osv-scanner", "scan", "image", "--archive", str(tar)], REPO, args.dry_run, check=False)
			worst = max(worst, rc)
			tar.unlink(missing_ok=True)
	finally:
		shutil.rmtree(work, ignore_errors=True)
	sys.exit(worst)


def cmd_backend(args):
	if not args.packages and not args.all:
		sys.exit("backend: give package specs (pillow==12.3.0 h2 ...) or --all")
	set_exclude_newer(cutoff(args.days), args.dry_run)
	cmd = ["uv", "lock"]
	if args.all:
		cmd.append("--upgrade")
	for spec in args.packages:
		cmd += ["--upgrade-package", spec]
	now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
	for pkg in args.young:
		cmd += ["--exclude-newer-package", f"{pkg}={now}"]
	run(cmd, BACKEND, args.dry_run)
	run(["git", "diff", "--stat", "--", "backend/pyproject.toml", "backend/uv.lock"], REPO, args.dry_run, check=False)


def cmd_frontend(args):
	pkg_json = FRONTEND / "package.json"
	before = pkg_json.read_bytes()
	declared = json.loads(before)
	direct = set(declared.get("dependencies", {})) | set(declared.get("devDependencies", {}))
	bad = [p for p in args.packages if p not in direct]
	if bad:
		sys.exit(f"frontend: not direct dependencies (bun update would ADD them): {' '.join(bad)}\n"
		         "         for a transitive CVE floor, add it to package.json \"overrides\" and run bun install")
	run(["bun", "update", *args.packages], FRONTEND, args.dry_run)
	if not args.dry_run and pkg_json.read_bytes() != before:
		# bun rewrote the updated deps' ranges to the resolved versions. The
		# lock keeps the resolution; the declared range is ours to decide.
		pkg_json.write_bytes(before)
		print("package.json ranges restored (bun had rewritten them); re-syncing lock")
		run(["bun", "install"], FRONTEND, args.dry_run)
	run(["git", "diff", "--stat", "--", "frontend/package.json", "frontend/bun.lock"], REPO, args.dry_run, check=False)


def crate_published(name, version):
	try:
		req = urllib.request.Request(f"https://crates.io/api/v1/crates/{name}/versions",
		                             headers={"User-Agent": "hillview scripts/deps.py"})
		for v in json.load(urllib.request.urlopen(req, timeout=15))["versions"]:
			if v["num"] == version:
				return v["created_at"][:10]
	except Exception:
		pass
	return None


def cmd_cargo(args):
	if not args.specs:
		sys.exit("cargo: give crate specs: tauri==2.11.1 rand@0.8.5==0.8.6 ...")
	limit = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=args.days)
	for spec in args.specs:
		if "==" not in spec:
			sys.exit(f"cargo: {spec}: need crate==version (cargo has no cooloff; pick the version yourself)")
		pkg, version = spec.split("==", 1)
		published = crate_published(pkg.split("@")[0], version)
		if published:
			age = "YOUNGER than the cooloff window" if dt.date.fromisoformat(published) > limit else "ok"
			print(f"{pkg} {version}: published {published} ({age})")
		run(["cargo", "update", "-p", pkg, "--precise", version], SRC_TAURI, args.dry_run)
	run(["git", "diff", "--stat", "--", "frontend/src-tauri/Cargo.lock"], REPO, args.dry_run, check=False)


def main():
	ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
	ap.add_argument("--days", type=int, default=COOLOFF_DAYS, help=f"cooloff window (default {COOLOFF_DAYS})")
	ap.add_argument("-n", "--dry-run", action="store_true", help="print commands, change nothing")
	sub = ap.add_subparsers(dest="cmd", required=True)

	p = sub.add_parser("audit", help="osv-scanner over every lockfile present")
	p.add_argument("--json", action="store_true")
	p.set_defaults(fn=cmd_audit)

	p = sub.add_parser("images", help="osv-scanner over docker images (default: every image running on this host)")
	p.add_argument("images", nargs="*", help="image refs; empty = images of all running containers")
	p.set_defaults(fn=cmd_images)

	p = sub.add_parser("cooloff", help="show the configured cooloff vs. today")
	p.set_defaults(fn=cmd_cooloff)

	p = sub.add_parser("backend", help="advance exclude-newer, then uv lock --upgrade[-package]")
	p.add_argument("packages", nargs="*", help="uv --upgrade-package specs, e.g. pillow==12.3.0")
	p.add_argument("--all", action="store_true", help="uv lock --upgrade (everything, still aged)")
	p.add_argument("--young", action="append", default=[], metavar="PKG",
	               help="exempt PKG from the cooloff (its CVE fix is younger than the window)")
	p.set_defaults(fn=cmd_backend)

	p = sub.add_parser("frontend", help="bun update within ranges; declared ranges restored afterwards")
	p.add_argument("packages", nargs="*", help="direct dependencies only; empty = all")
	p.set_defaults(fn=cmd_frontend)

	p = sub.add_parser("cargo", help="cargo update -p X --precise Y, one crate per call")
	p.add_argument("specs", nargs="*", help="crate==version, or crate@oldver==version for multi-version crates")
	p.set_defaults(fn=cmd_cargo)

	args = ap.parse_args()
	args.fn(args)


if __name__ == "__main__":
	main()
