/**
 * Shared utilities for Leaflet map interaction in Playwright tests
 */

/**
 * Set the map view programmatically by finding the Leaflet map instance.
 */
export async function setMapLocation(page: any, lat: number, lng: number, zoom: number = 18, locationName?: string) {
  // Ensure map container is visible
  const mapContainer = page.locator('.leaflet-container').first();
  await mapContainer.waitFor({ state: 'visible', timeout: 10000 });

  const mapFound = await page.evaluate(([lat, lng, zoom, locationName]: [number, number, number, string]) => {
    // Try multiple ways to access the Leaflet map
    const maps = [
      (window as any).map,
      (window as any).leafletMap,
      (document.querySelector('.leaflet-container') as any)?._leaflet_map
    ];

    for (const mapComponent of maps) {
      if (mapComponent && mapComponent.setView) {
        console.log(`📍 Setting map view to ${locationName || `${lat}, ${lng}`}`);
        mapComponent.setView([lat, lng], zoom);
        return true;
      }
    }
    console.log('❌ Could not find map component to set view');
    return false;
  }, [lat, lng, zoom, locationName]);

  if (!mapFound) {
    throw new Error(`Failed to set map location to ${locationName || `${lat}, ${lng}`} - could not find map component`);
  }

  // Give the map a moment to update
  await page.waitForTimeout(1000);
}
