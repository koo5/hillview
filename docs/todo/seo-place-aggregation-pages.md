# SEO: place/area aggregation pages

## Context

Hillview has ~27.5k public photos but only ~70 carry any title/description/
keywords. The vast majority are **single frames** (random streets, details,
views), not panoramas — only ~50 are panos. Per-photo SEO works for the panos
(distinctive vistas, real search demand, hand-titled), but **not** for the
single frames.

The tempting move — reverse-geocode every frame and title it with its place
("Prosek") — is a trap. The place *word* is a genuine text-ranking signal that
coordinates alone don't provide, BUT sharing one place name across hundreds of
co-located frames manufactures near-duplicate thin pages. Google clusters those,
ranks ~one, ignores the rest, and *en masse* it trips the **doorway-pages**
guideline (mass-generated pages with minimal unique content) — a sitewide
quality risk. There's also no search demand for "a random side street in
Prosek." Precedent: Mapillary / KartaView / Street View do not publish
individual frames as indexable pages; the corpus's value is the aggregate map +
data, not millions of landing pages.

So: **don't render place as per-frame titles.** Capture the place value in *one
strong page per area* instead.

## The idea

`/place/<slug>` aggregation pages — one authoritative, indexable page per
neighborhood / park / named area that legitimately owns "panoramas & views of
<place>". Each page is real, unique content (not thin): a map of the area, a
grid of its photos linking to the curated `/photo/<uid>` detail pages, the best
pano surfaced, and a short place blurb. One strong `/place/prosek` beats 500
thin "Prosek" frames.

## Foundation — DONE (the place data exists)

Reverse-geocoded and **stored** on every photo via `scripts/backfill_places.py`
(a DB backfill, NOT a pipeline step — most photos never go through the pipeline).
Done for the Czech corpus against a self-hosted Nominatim; the ~766 non-CZ
(Spain/Austria) are left placeless until a global geocoder pass.

Columns on `photos` (migrations 019 + 020), all re-derivable from a stored raw
`geocode` JSONB with `--rederive` (no re-geocoding):

- `geocode` JSONB — raw `{address, display_name}` kept so the derived fields below
  can be recomputed cheaply when the rules change.
- **Leaf** — `place_name` ("Prosek, Praha") + `place_slug` ("prosek-praha-cz").
  Neighborhood/locality granularity, NOT a street address. Slug carries a coarse
  admin tail (city+country, or okres for standalone towns) so it's globally
  unique AND stable across all photos at the same place.
- **Hub (parent)** — `place_parent_name` ("Praha") + `place_parent_slug`
  ("praha-cz"). The city/area a leaf rolls up to.

**Two-level hierarchy** — the key model. A single flat place per photo is wrong:
Prosek and Kobylisy are both *in* Praha, so a flat scheme makes three sibling
buckets and no `/place/praha` hub. As built on the real data:

- **57 hubs**, e.g. `praha-cz` (17,108 photos / 92 neighborhoods),
  `ricany-cz` (1,880 / 20), `jilove-u-prahy-cz` (1,303), `sazava-cz` (1,204).
- **312 leaves**, e.g. `prosek-praha-cz` (1,175), `kobylisy-praha-cz` (937).
- Prosek and Kobylisy both `place_parent_slug = praha-cz`, so the Praha hub
  aggregates them; bare-`Praha` photos (no neighborhood resolved) have no leaf
  page but still appear on the hub. Hub page = `WHERE place_parent_slug = X`;
  leaf page = `WHERE place_slug = Y`.
- Admin labels are stripped (`_clean_admin`: "SO POÚ Říčany" → "Říčany",
  "SO Praha 6" → "Praha 6"), so names are clean for both levels.

Remaining foundation work: geocode **new photos on ingest** (DB-side, e.g. the
authorize-upload / processed path); a `--retry-no-place` pass with a **global**
geocoder for the 766 non-CZ; apply to **prod** (migrations 019+020 + run the
script against prod).

## The page

- SSR'd route like `/bestof` and `/photo/[uid]` (needs a `.web` shadow with
  `ssr = true` + the Dockerfile copy, plus a `+page.server.ts` loader).
- Content: `<h1>` "Panoramas & views — <place>, Praha", a map of the area, a
  thumbnail grid (PhotoItem, linking to `/photo/<uid>`), the top pano, short
  blurb. Real unique content per page is what keeps it out of doorway territory.
- JSON-LD `CollectionPage` + `ItemList` of the photos, and a `Place` with name +
  geo for the area.
- **Which places get a page:** gate on a threshold (e.g. ≥N photos, or ≥1
  curated/interesting photo) so you don't generate a thin page per hamlet.
- **Sitemap:** add the place-page URLs (they're strong, indexable) — slots into
  the existing sitemap index alongside the curated photo URLs.

## Related, smaller: contentLocation.name enrichment

Independent of the place pages, the **photo** JSON-LD can carry the resolved
place name (today `contentLocation` is just `geo` coordinates). schema.org
`ImageObject.contentLocation` is a `Place`, which takes `name` (and optional
`address`):

```json
"contentLocation": {
  "@type": "Place",
  "name": "Prosek, Praha",
  "geo": { "@type": "GeoCoordinates", "latitude": 50.117, "longitude": 14.488 }
}
```

Strengthens Google's place understanding of the (panorama) pages we do index,
without putting the place name in the title. **Already wired** (`place_name` on
the public serializer → `contentLocation.name` in `buildPhotoImageJsonLd`); live
once those rows have a place and the frontend is rebuilt.

## Decisions — resolved / still open

Resolved during the foundation backfill:
- **Storage:** columns on `photos` (leaf + parent), not a `places` table — the
  hubs/leaves are just `GROUP BY` / `WHERE` on indexed slug columns.
- **Slug scheme & collisions:** leaf = place + city/okres + country; hub =
  city + country. Globally unique, stable per place. Admin labels stripped.

Still open (page-build time):
- **Threshold for which areas earn a page** — e.g. ≥N photos, or ≥1 curated
  photo. With 57 hubs / 312 leaves, most leaves are small; likely build hub
  pages for all and leaf pages only above a threshold.
- Czech vs bilingual place names (project currently mono-cs for SEO).
- The 766 non-CZ photos (global-geocoder pass) before their place pages exist.
