# PostgreSQL: moving to the Alpine PostGIS image

## Why

`postgis/postgis:15-3.5` (Debian) is built `FROM postgres:15-bullseye`, and
upstream docker-postgis keeps its PostgreSQL 14–17 Debian variants on bullseye
on purpose (a "cautious release cycle" that takes PostGIS/GEOS/PROJ from the
Debian repositories; only PG 18 moved to trixie). The official `postgres`
image, however, stopped building bullseye variants in 2025-07 — its last
`15-bullseye` is **15.13**, and its `versions.json` for 15 now lists only
trixie, bookworm and alpine. So every rebuild of `15-3.5` (still happening,
2026-08-24) re-ships PostgreSQL 15.13 on Debian 11 (EOL 2026-08-31): the line
is not discontinued, but it no longer receives PostgreSQL minor releases.
Since 15.13, PostgreSQL 15 has closed 28 CVEs (15.19, 2026-08-13; among them a
pg_dump heap overflow, CVSS 8.8).

The `15-3.5-alpine` tag tracks the official `15-alpine` base and so does get
them: PostgreSQL **15.19**, PostGIS 3.5.7, GEOS 3.14, PROJ 9.8, Alpine 3.24 — an
image scan finds nothing beyond the bundled `gosu` helper's Go stdlib.

Alternatives that stay on Debian/glibc, if musl is unwelcome:
`postgis/postgis:18-3.6` (trixie, PostGIS 3.6.4 — a PostgreSQL major upgrade),
or a small own image `FROM postgres:15-trixie` installing pgdg's
`postgresql-15-postgis-3`, which is docker-postgis's own recipe on a
current base. Either way glibc 2.31 → 2.41 also changes collation, so the
dump/restore below (and the ICU choice) apply to those paths too.

## Status

**Parked (2026-08-25).** Everything below is prepared and was rehearsed
successfully against the dev database, but the switch is not flipped: in
`docker-compose.yml` the alpine image, the `postgres_data_15alpine` volume and
the ICU initdb variables sit commented out next to the live Debian lines
(`postgres`, `umami-init`, `volumes:`). To proceed, swap those commented lines,
re-run the rehearsal, then follow "The migration" below.

## What changes in `docker-compose.yml`

- `postgres` (and `umami-init`, which only needs `psql`) run
  `postgis/postgis:15-3.5-alpine@sha256:22c05d31…`, pinned by digest like umami.
- The data volume is **`postgres_data_15alpine`**, not `postgres_data`. A plain
  `docker compose up` therefore creates a fresh, empty cluster instead of
  starting the musl build on a glibc-initialised data directory (see below).
  The old volume stays defined as the rollback target.
- `LANG: en_US.utf8` + `POSTGRES_INITDB_ARGS: --locale-provider=icu
  --icu-locale=en-US` — the official image's documented recipe for locales on
  the Alpine variants ("Locale Customization" on
  <https://hub.docker.com/_/postgres/>). Only `initdb` reads them, i.e. they
  take effect exactly once, when the new volume is created.

## Why dump/restore, and why ICU

The same major version (15) means the data directory *would* open under the
new image. Don't: the old cluster's text indexes were built under glibc's
`en_US.utf8` collation, and on musl that same locale name is plain byte order
(`A,B,a,b,z,é` instead of `a,A,b,B,é,z`). PostgreSQL would start and quietly
return wrong results from every btree on a text column until a `REINDEX`. A
dump/restore into a freshly initialised cluster rebuilds every index under the
new collation, and choosing the ICU provider at `initdb` makes the new cluster
sort the way the old one did — and keeps sorting that way across future
Alpine/musl upgrades, because ICU's collation does not depend on libc.

Both facts are checked, not assumed, by the rehearsal script.

## Prove it first

```
backend/scripts/pg_rehearse_alpine.py            # add --keep to poke at the result on 127.0.0.1:25433
```

It reads the image and initdb args from `docker-compose.yml`, dumps every
database out of the running `hillview_postgres` (read-only), restores into a
throwaway container + volume, and fails unless: every `pg_restore` exits 0
with an empty stderr; exact per-table row counts are identical; and the
collation probe sorts the same on both sides. It also prints extension
versions, the alembic head and `postgis_full_version()`. Run it on the host
that will be migrated — a dev-sized database (241 MB hillview + 89 MB umami,
82k + 193k rows) dumps in ~6 s and restores in ~12 s; production scales with
size.

## The migration (one maintenance window)

Stop everything that writes, keep postgres up:

```
docker compose stop api worker umami places
```

Dump into a directory you will keep (this is also the rollback copy). Do it
from inside the container so client and server versions match:

```
docker exec hillview_postgres pg_dumpall -U hillview --globals-only > globals.sql
docker exec hillview_postgres pg_dump -U hillview -Fc -f /tmp/hillview.dump hillview
docker exec hillview_postgres pg_dump -U hillview -Fc -f /tmp/umami.dump umami
docker cp hillview_postgres:/tmp/hillview.dump . ; docker cp hillview_postgres:/tmp/umami.dump .
```

Deploy the compose change and bring up only postgres. This creates the empty
ICU cluster on `postgres_data_15alpine`; `docker/postgres/initdb.d` creates the
`umami` database during initdb:

```
docker compose up -d postgres
docker exec hillview_postgres pg_isready -h localhost -U hillview -d hillview
```

Restore. "role already exists" errors from the globals are expected (the
POSTGRES_USER role was created by initdb); `pg_restore` must exit 0 with an
empty stderr — that is what the rehearsal established as normal:

```
docker exec -i hillview_postgres psql -U hillview -d postgres -q < globals.sql
docker cp hillview.dump hillview_postgres:/tmp/ ; docker cp umami.dump hillview_postgres:/tmp/
docker exec hillview_postgres pg_restore -U hillview -d hillview -j 4 /tmp/hillview.dump
docker exec hillview_postgres pg_restore -U hillview -d umami -j 4 /tmp/umami.dump
docker exec hillview_postgres rm /tmp/hillview.dump /tmp/umami.dump
```

Verify before starting the apps:

```
docker exec hillview_postgres psql -U hillview -d hillview -Atc "select version(); select version_num from alembic_version; select postgis_full_version();"
docker exec hillview_postgres psql -U hillview -d hillview -Atc "select string_agg(x, ',' order by x) from unnest(array['b','A','a','B','é','z']) x"   # expect a,A,b,B,é,z
docker exec hillview_postgres psql -U hillview -d hillview -Atc "select datlocprovider::text, daticulocale from pg_database where datname='hillview'"  # expect i | en-US
```

Row counts: compare `select count(*)` per public table against the numbers
from before the stop (the rehearsal script's `table_counts` is the same
query if you want it exact rather than eyeballed).

Then `docker compose up -d`. The api's prestart runs `alembic upgrade head`,
which must be a no-op — the restored `alembic_version` is the head.

## Rollback and cleanup

Rollback, at any point before the old volume is deleted: revert the compose
change (image, volume name, initdb args) and `docker compose up -d postgres`;
the glibc cluster on `postgres_data` was never opened by the new image.

Once satisfied: drop `postgres_data:` from the `volumes:` section and
`docker volume rm hillview_postgres_data`. Keep the dump files for a while
regardless.

## Later ICU upgrades

The cluster now records its ICU collation version. When a future image ships
a newer ICU, PostgreSQL warns `collation version mismatch` on connect; the
answer is `REINDEX` of text-keyed indexes followed by
`ALTER DATABASE hillview REFRESH COLLATION VERSION` — a documented, warned
event, unlike the silent libc case this migration removes.
