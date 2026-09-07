/**
 * Panoramax is fetched browser-side straight from the public instance
 * (https://api.panoramax.xyz/api/search), so unlike Mapillary there is no
 * backend mock to switch on. These helpers intercept the request in the page
 * instead; a spec that wants photos registers its own route on top of the empty
 * default from fixtures.ts — Playwright matches routes in reverse registration
 * order, so the spec's wins.
 *
 * WEBKIT: none of this applies. The fetch is issued by the photo worker, and
 * Playwright cannot route a worker's requests in WebKit (probed on 1.59.1 —
 * neither page.route nor context.route fires; chromium and firefox both do).
 * Keeping the public internet out of the suite there is fixtures.ts's job: it
 * turns the source off before the app boots, so nothing is ever requested. A
 * spec that needs Panoramax photos on the map is chromium/firefox only.
 */
import type { Page } from '@playwright/test';

export const PANORAMAX_SEARCH = /api\.panoramax\.xyz\/api\/search/;

export interface MockPanoramaxItem {
  id: string;
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: Record<string, any>;
  assets: Record<string, { href: string }>;
  providers: Array<{ id: string; name: string; roles: string[] }>;
}

/** STAC items spread in a small circle around a centre, as convertPanoramaxItem expects them. */
export function createMockPanoramaxItems(centerLat: number, centerLng: number, count = 5): MockPanoramaxItem[] {
  const items: MockPanoramaxItem[] = [];
  for (let i = 1; i <= count; i++) {
    const angle = (i * 360) / count;
    const distance = 0.00015 * ((i % 2) + 1);
    const lat = centerLat + distance * Math.sin((angle * Math.PI) / 180);
    const lng = centerLng + distance * Math.cos((angle * Math.PI) / 180);
    items.push({
      id: `mock-pano-${String(i).padStart(3, '0')}`,
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, lat] },
      properties: {
        'view:azimuth': angle % 360,
        datetime: `2024-03-0${(i % 9) + 1}T12:00:00Z`,
        license: 'CC-BY-SA-4.0'
      },
      assets: {
        thumb: { href: `https://mock.panoramax.test/${i}/thumb.jpg` },
        hd: { href: `https://mock.panoramax.test/${i}/hd.jpg` }
      },
      providers: [{ id: `mock-producer-${(i % 2) + 1}`, name: `mock_producer_${(i % 2) + 1}`, roles: ['producer'] }]
    });
  }
  return items;
}

/** Answer the instance's search with `items` (empty by default). */
export async function mockPanoramaxSearch(page: Page, items: MockPanoramaxItem[] = []): Promise<void> {
  await page.route(PANORAMAX_SEARCH, route =>
    route.fulfill({ json: { type: 'FeatureCollection', features: items } })
  );
}
