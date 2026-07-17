/**
 * OpenSeadragon viewer initialization — extracted verbatim from
 * OpenSeadragonViewer.svelte for reuse by the enrichment workbench:
 * shared option defaults, initial-source selection (fallback thumbnail vs
 * main source), and the fallback→main progressive swap.
 */
import { buildTileSource, type DziPyramid } from './tileSource';

/** The main app's viewer options, sans element/tileSources. Consumers spread
 *  these and override per-context (e.g. the workbench enables the navigator). */
export const OSD_VIEWER_DEFAULTS = {
	zoomPerScroll: 2.5,
	drawer: 'canvas' as const,
	showNavigationControl: false,
	showNavigator: false,
	animationTime: 0.3,
	// Allow dragging even without a button press (touch-friendly)
	gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
	gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
	immediateRender: false,
	imageLoaderLimit: 1,
	// Allow zooming well beyond native resolution (default is 1.1)
	maxZoomPixelRatio: 4,
	imageSmoothingEnabled: false,
	placeholderFillStyle: '#009900'
	// Note: crossOriginPolicy is set per-source (on DZI tile sources), NOT here.
	// Setting it on the viewer would apply to fallback images too, which share
	// URLs with regular <img> tags. If the browser cached a non-CORS response,
	// loading with crossOrigin='anonymous' would fail (CORS cache poisoning).
};

/** If a fallback thumbnail is available (likely browser-cached), open with it
 *  immediately and swap the main source in later (swapInMainSource); otherwise
 *  open the main source directly. */
export function initialSourceFor(
	fallbackUrl: string | null | undefined,
	pyramid: DziPyramid | null | undefined,
	url: string
): { usingFallback: boolean; source: Record<string, unknown> } {
	const usingFallback = !!fallbackUrl;
	return {
		usingFallback,
		source: usingFallback
			? { type: 'image', url: fallbackUrl as string }
			: buildTileSource(pyramid, url)
	};
}

/**
 * Add the real source on top of an open fallback image — it renders over the
 * fallback as tiles arrive, then the fallback is removed once fully loaded.
 * Call from the viewer's 'open' handler when initialSourceFor said usingFallback.
 */
export function swapInMainSource(
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	viewer: any,
	mainSource: Record<string, unknown>
): void {
	console.log('[OSD] Fallback loaded, spinner dismissed. Adding main source...');
	viewer.addTiledImage({
		tileSource: mainSource,
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		success: (event: any) => {
			const mainItem = event.item;
			const removeFallback = () => {
				const fallbackItem = viewer.world.getItemAt(0);
				if (fallbackItem && fallbackItem !== mainItem && viewer.world.getItemCount() > 1) {
					viewer.world.removeItem(fallbackItem);
					console.log('[OSD] Fallback image removed');
				}
			};
			// Listen on the TiledImage itself for fully-loaded-change,
			// which fires reliably for DZI sources (unlike world metrics-change).
			if (mainItem.getFullyLoaded()) {
				removeFallback();
			} else {
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				const onLoaded = (e: any) => {
					if (!e.fullyLoaded) return;
					mainItem.removeHandler('fully-loaded-change', onLoaded);
					removeFallback();
				};
				mainItem.addHandler('fully-loaded-change', onLoaded);
			}
		},
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		error: (event: any) => {
			// Main source failed — keep the fallback visible
			console.warn('[OSD] Main tile source failed to load, keeping fallback');
			throw new Error(
				`[OSD] addTiledImage error: ${event?.message || event?.source || JSON.stringify(event)}`
			);
		}
	});
}
