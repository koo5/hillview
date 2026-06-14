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

## Foundation (do this first — useful regardless)

Reverse-geocode and **store** a structured place on every photo. This is a
**DB backfill, not a pipeline step** — most photos never go through the pipeline.

- **Geocoder:** OSM-based (self-hosted Nominatim/Photon, or an offline Czech
  OSM extract — small, no rate limits/cost; ~27k lookups). On-brand with the
  OSM-aligned licensing. Czech names for free (`name:cs`).
- **Granularity is everything:** resolve to the *named feature / park /
  neighborhood / suburb / district*, NOT a street address. Prefer OSM
  `leisure=park`, `place=suburb|neighbourhood`, named viewpoints. A raw
  "Na Hřebenech II 1718, Praha 4" is worse than "Prosek".
- **Store:** a place slug + display name (+ maybe district/city) on the photo,
  or a `places` table with a photo→place association. Reused by: place pages,
  in-app area filtering, and JSON-LD enrichment.
- Backfill the existing 27k; geocode new photos on ingest (DB-side, e.g. on the
  authorize-upload / processed path — wherever geo is finalized).

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
without putting the place name in the title. Cheap once the place data is stored
— wire it into `buildPhotoImageJsonLd` (frontend) from a new `place`/
`place_name` field on the public photo serializer.

## Decisions still open

- Place taxonomy / slug scheme (and collision handling across cities).
- Threshold for which areas earn a page.
- Whether place lives as columns on `photos` or a `places` table + join.
- Czech vs bilingual place names (project currently mono-cs for SEO).
