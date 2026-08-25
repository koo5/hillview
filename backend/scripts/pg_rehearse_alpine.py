#!/usr/bin/env python3
"""Rehearse the PostgreSQL image move (Debian/glibc -> Alpine/musl) on a throwaway cluster.

Dumps every user database out of the running postgres container (read-only --
the source is never written to), starts the target image on a scratch volume
and port, restores the dumps, and checks what the real migration must get
right:
  - pg_restore exits 0 with an empty stderr for every database
  - exact per-table row counts are identical, source vs. rehearsal
  - extension versions, alembic head, PostGIS/GEOS/PROJ versions
  - text collation: the sort order of a probe list matches the source. On musl
    the libc en_US locale is byte order, which is why docker-compose.yml passes
    POSTGRES_INITDB_ARGS="--locale-provider=icu --icu-locale=en-US"; this
    script reads both the image and those args from the compose file so it
    rehearses exactly what `docker compose up` would create.

The migration itself is documented in docs/postgres-alpine-migration.md; this
script is its "prove it first" step and can be re-run any time (each run
recreates the rehearsal container and volume from scratch).

Usage:
    backend/scripts/pg_rehearse_alpine.py                    # hillview_postgres -> 127.0.0.1:25433
    backend/scripts/pg_rehearse_alpine.py --keep             # leave the rehearsal cluster running afterwards
    backend/scripts/pg_rehearse_alpine.py --source other_pg --port 25434 --image postgis/postgis:15-3.5-alpine
"""

import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "docker-compose.yml"
NAME = "pg_rehearsal"
VOLUME = "pg_rehearsal_data"
PROBE = "select string_agg(x, ',' order by x) from unnest(array['b','A','a','B','é','z']) x"


def sh(cmd, check=True, capture=True, stdin=None):
	r = subprocess.run(cmd, check=False, capture_output=capture, text=True, stdin=stdin)
	if check and r.returncode:
		sys.exit(f"failed ({r.returncode}): {' '.join(cmd)}\n{(r.stderr or '')[:2000]}")
	return r


def compose_defaults():
	text = COMPOSE.read_text()
	svc = re.search(r"^  postgres:\n(.*?)(?=^  \S)", text, re.M | re.S).group(1)
	image = re.search(r"^\s+image:\s*(\S+)", svc, re.M).group(1)
	m = re.search(r'POSTGRES_INITDB_ARGS:\s*"([^"]*)"', svc)
	return image, (m.group(1) if m else "")


def psql(container, user, db, sql):
	return sh(["docker", "exec", container, "psql", "-U", user, "-d", db, "-Atc", sql]).stdout.strip()


def table_counts(container, user, db):
	tables = psql(container, user, db, "select tablename from pg_tables where schemaname='public' order by 1").split()
	return {t: int(psql(container, user, db, f'select count(*) from "{t}"')) for t in tables}


def main():
	image, initdb_args = compose_defaults()
	ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
	ap.add_argument("--source", default="hillview_postgres", help="running source container (default hillview_postgres)")
	ap.add_argument("--image", default=image, help=f"target image (default: from docker-compose.yml)")
	ap.add_argument("--initdb-args", default=initdb_args, help="POSTGRES_INITDB_ARGS (default: from docker-compose.yml)")
	ap.add_argument("--port", type=int, default=25433, help="host port for the rehearsal cluster")
	ap.add_argument("--keep", action="store_true", help="leave the rehearsal container/volume running")
	args = ap.parse_args()

	env = lambda k: sh(["docker", "exec", args.source, "printenv", k]).stdout.strip()
	user, password, main_db = env("POSTGRES_USER"), env("POSTGRES_PASSWORD"), env("POSTGRES_DB")
	dbs = psql(args.source, user, "postgres", "select datname from pg_database where not datistemplate and datname<>'postgres' order by 1").split()
	print(f"source {args.source}: databases {dbs}")
	print(f"target {args.image}\n       initdb args: {args.initdb_args!r}")
	failures = []

	# under $HOME, not /tmp: `docker cp` resolves the host path in the daemon,
	# which does not see a sandboxed or per-user /tmp
	scratch = Path.home() / "tmp"
	with tempfile.TemporaryDirectory(prefix="pg-rehearsal-", dir=scratch if scratch.is_dir() else Path.home()) as tmp:
		t0 = time.monotonic()
		globals_sql = Path(tmp, "globals.sql")
		globals_sql.write_text(sh(["docker", "exec", args.source, "pg_dumpall", "-U", user, "--globals-only"]).stdout)
		for db in dbs:
			sh(["docker", "exec", args.source, "pg_dump", "-U", user, "-Fc", "-f", f"/tmp/{db}.dump", db])
			sh(["docker", "cp", f"{args.source}:/tmp/{db}.dump", f"{tmp}/{db}.dump"])
			sh(["docker", "exec", args.source, "rm", f"/tmp/{db}.dump"])
		sizes = ", ".join(f"{db} {Path(tmp, db + '.dump').stat().st_size >> 20} MB" for db in dbs)
		print(f"dumped in {time.monotonic() - t0:.0f}s ({sizes})")

		sh(["docker", "rm", "-f", NAME], check=False)
		sh(["docker", "volume", "rm", "-f", VOLUME], check=False)
		run = ["docker", "run", "-d", "--name", NAME,
		       "-e", f"POSTGRES_DB={main_db}", "-e", f"POSTGRES_USER={user}", "-e", f"POSTGRES_PASSWORD={password}",
		       "-p", f"127.0.0.1:{args.port}:5432", "-v", f"{VOLUME}:/var/lib/postgresql/data",
		       "-v", f"{REPO}/docker/postgres/initdb.d:/docker-entrypoint-initdb.d:ro"]
		if args.initdb_args:
			run += ["-e", f"POSTGRES_INITDB_ARGS={args.initdb_args}"]
		sh(run + [args.image])
		# the entrypoint's init-time server listens on the unix socket only, so
		# TCP readiness means the final server is up
		for _ in range(90):
			if sh(["docker", "exec", NAME, "pg_isready", "-h", "localhost", "-U", user, "-d", main_db], check=False).returncode == 0:
				break
			time.sleep(2)
		else:
			sys.exit("rehearsal cluster never became ready; see `docker logs pg_rehearsal`")

		t1 = time.monotonic()
		with open(globals_sql) as f:
			sh(["docker", "exec", "-i", NAME, "psql", "-U", user, "-d", "postgres", "-q"], check=False, stdin=f)
		for db in dbs:
			if db != main_db:
				psql(NAME, user, "postgres", f'create database "{db}"') if not psql(NAME, user, "postgres", f"select 1 from pg_database where datname='{db}'") else None
			sh(["docker", "cp", f"{tmp}/{db}.dump", f"{NAME}:/tmp/{db}.dump"])
			r = sh(["docker", "exec", NAME, "pg_restore", "-U", user, "-d", db, "-j", "4", f"/tmp/{db}.dump"], check=False)
			status = "ok" if r.returncode == 0 and not r.stderr.strip() else "PROBLEM"
			print(f"restore {db}: exit={r.returncode} stderr_lines={len(r.stderr.splitlines())} -> {status}")
			if status != "ok":
				failures.append(f"restore {db}"); print(r.stderr[:1500])
		print(f"restored in {time.monotonic() - t1:.0f}s")

	for db in dbs:
		src, dst = table_counts(args.source, user, db), table_counts(NAME, user, db)
		diff = {t: (src.get(t), dst.get(t)) for t in set(src) | set(dst) if src.get(t) != dst.get(t)}
		print(f"row counts {db}: {len(src)} tables, {sum(src.values())} rows -> {'IDENTICAL' if not diff else 'MISMATCH ' + str(diff)}")
		if diff:
			failures.append(f"row counts {db}")

	print("target:", psql(NAME, user, main_db, "select version()"))
	print("       ", psql(NAME, user, main_db, "select string_agg(extname||' '||extversion, ', ' order by 1) from pg_extension"))
	print("       ", "alembic", psql(NAME, user, main_db, "select version_num from alembic_version"))
	print("       ", psql(NAME, user, main_db, "select postgis_full_version()")[:110])
	print("       ", "locale provider/collation:", psql(NAME, user, main_db, f"select datlocprovider::text||' '||coalesce(daticulocale,'-')||' '||datcollate from pg_database where datname='{main_db}'"))
	src_order, dst_order = psql(args.source, user, main_db, PROBE), psql(NAME, user, main_db, PROBE)
	print(f"collation probe: source {src_order} / rehearsal {dst_order} -> {'SAME' if src_order == dst_order else 'DIFFERENT'}")
	if src_order != dst_order:
		failures.append("collation order differs (missing --locale-provider=icu?)")

	if not args.keep:
		sh(["docker", "rm", "-f", NAME]); sh(["docker", "volume", "rm", "-f", VOLUME])
	else:
		print(f"rehearsal cluster kept on 127.0.0.1:{args.port}  (docker rm -f {NAME}; docker volume rm {VOLUME})")
	if failures:
		sys.exit("FAILED: " + "; ".join(failures))
	print("REHEARSAL PASSED")


if __name__ == "__main__":
	main()
