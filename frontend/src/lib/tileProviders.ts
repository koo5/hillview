import L from 'leaflet';
import 'leaflet-providers';
import { writable, get } from 'svelte/store';
import {localStorageSharedStore} from "$lib/svelte-shared-store";
import { loadEarth } from '$world/earth';
import { earthUrl, earthChannel } from '$lib/world';

const doLog = false;

export interface TileProviderConfig {
    url: string;
    attribution: string;
    maxZoom: number;
    maxNativeZoom?: number;
    minZoom?: number;
    tileSize?: number;
    zoomOffset?: number;
    detectRetina?: boolean;
    crossOrigin?: boolean;
    tms?: boolean;
    noWrap?: boolean;
    zoomReverse?: boolean;
    opacity?: number;
    zIndex?: number;
    bounds?: [[number, number], [number, number]];
    className?: string;
    subdomains?: string;
}

// API Keys configuration
// SECURITY: Frontend API keys for map tiles are industry standard practice (Google Maps, Mapbox, etc.)
// These keys are protected by:
// 1. Referrer/domain restrictions configured in the provider's console
// 2. Read-only access (tile fetching only, no write operations)
// 3. Provider-side rate limiting
// Proxying tiles through backend would add latency and server load with no security benefit.
const API_KEYS = {
    // Configured with referrer restrictions at console.tracestrack.com
    TRACESTRACK: '262a38b16c187cfca361f1776efb9421'
} as const;

// Custom providers (not from leaflet-providers)
const CUSTOM_PROVIDERS: Record<string, TileProviderConfig> = {
    'TracesTrack.Topo': {
        url: `https://tile.tracestrack.com/_/{z}/{x}/{y}.webp?key=${API_KEYS.TRACESTRACK}`,
        attribution: '&copy; <a href="https://tracestrack.com">TracesTrack</a>, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 23, // Allow zooming to higher levels
        maxNativeZoom: 19, // TracesTrack tiles likely go up to zoom 12 (conservative)
    },
    'TracesTrack.TopoContrast': {
        url: `https://tile.tracestrack.com/topo_auto/{z}/{x}/{y}.webp?key=${API_KEYS.TRACESTRACK}&style=contrast+`,
        attribution: '&copy; <a href="https://tracestrack.com">TracesTrack</a>, &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19, // Allow zooming to higher levels
        maxNativeZoom: 12, // TracesTrack tiles likely go up to zoom 12 (conservative)
    },
	'tiles.ueueeu.eu': {
		url: 'https://tiles.ueueeu.eu/tile/{z}/{x}/{y}.png',
		attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
		maxZoom: 23,
		maxNativeZoom: 20,
	},
	'tiles4.ueueeu.eu': {
		url: 'https://tiles4.ueueeu.eu/tile/{z}/{x}/{y}.png',
		attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
		maxZoom: 23,
		maxNativeZoom: 20,
	},
	// The base under earth's orthophoto (see EARTH_ORTHO_PROVIDER): Hillview (world), so the map still shows
	// outside Czechia, where a tile is still downloading, and when earth cannot be reached
	'earth.ortho': {
		url: 'https://tiles4.ueueeu.eu/tile/{z}/{x}/{y}.png',
		attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
		maxZoom: 23,
		maxNativeZoom: 20,
	},
	// DEV-only: internal Ortofoto ČR (ČÚZK) WMTS proxy. Open data under CC BY 4.0.
	'ortofoto.jj.internal': {
		url: 'https://ortofoto.jj.internal/wmts/oi/webmercator/{z}/{x}/{y}.png',
		attribution: 'Ortofoto ČR &copy; <a href="https://www.cuzk.cz">ČÚZK</a>, <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>',
		maxZoom: 23,
		maxNativeZoom: 20,
	}
};

// Available tile providers with descriptions
export const AVAILABLE_PROVIDERS = {
	'tiles4.ueueeu.eu': 'Hillview (world)',
	'earth.ortho': 'Aerial photo (CZ)',
	'tiles.ueueeu.eu': 'Hillview (CZ)',

    // Standard 'leaflet-providers' providers
    'OpenStreetMap.Mapnik': 'OpenStreetMap',
    'OpenStreetMap.DE': 'OpenStreetMap (German)',
    'CartoDB.DarkMatter': 'CartoDB Dark',
    'OpenTopoMap': 'OpenTopoMap',
    'CyclOSM': 'CyclOSM (Cycling)',

    // my Custom providers
    'TracesTrack.Topo': 'TracesTrack Topographic',
    /*'TracesTrack.TopoContrast': 'TracesTrack Topo (High Contrast)',*/

    // DEV-only providers (hidden from the picker unless VITE_DEV_MODE === 'true')
    'ortofoto.jj.internal': 'Ortofoto ČR (DEV)',

} as const;

export type ProviderName = keyof typeof AVAILABLE_PROVIDERS;

// Providers only offered in the picker when running in dev mode
const DEV_ONLY_PROVIDERS: ReadonlySet<ProviderName> = new Set(['ortofoto.jj.internal']);

// Default tile provider
export const DEFAULT_TILE_PROVIDER: ProviderName = 'tiles4.ueueeu.eu';
//'OpenStreetMap.Mapnik';

// Current selected provider (can be changed at runtime)
export const currentTileProvider = localStorageSharedStore<ProviderName>('currentTileProvider', DEFAULT_TILE_PROVIDER);

/**
 * Earth's orthophoto (ČÚZK Ortofoto ČR), drawn as an overlay above the 'earth.ortho' provider's base.
 *
 * Its tile URL names the release the channel serves, so it is read once from earth (loadEarth, the same
 * reader the 3D world uses) rather than written here: VITE_EARTH_URL and VITE_EARTH_CHANNEL, as the 3D world.
 * The picker always offers the layer; without VITE_EARTH_URL it is the base map alone.
 */
export const EARTH_ORTHO_PROVIDER: ProviderName = 'earth.ortho';
// the ortho service's grid is z0-20 (z20 ~ 10 cm/px here, the source is 12.5 cm); finer is Leaflet's upscaling
const EARTH_ORTHO_MAX_NATIVE_ZOOM = 20;

export interface EarthOrthoLayer {
	url: string;
	bounds: [[number, number], [number, number]];
	maxNativeZoom: number;
	attribution: string;
}

/** null until loaded, and for good when earth could not be read (the base map stays alone) */
export const earthOrtho = writable<EarthOrthoLayer | null>(null);
let earthOrthoLoading: Promise<void> | null = null;

// The credit is built from earth's /attribution (network data) and rendered as HTML (Leaflet's attribution
// control, the map's and About's {@html}): every text escaped, and a link only to an http(s) URL, since
// escaping alone would still let a javascript: href through
function escapeHtml(s: string): string {
	return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

function creditLink(url: string | undefined, text: string): string {
	let ok = false;
	try {
		ok = !!url && ['https:', 'http:'].includes(new URL(url).protocol);
	} catch { /* not a URL: the text alone */ }
	return ok ? `<a href="${escapeHtml(url!)}">${escapeHtml(text)}</a>` : escapeHtml(text);
}

// A tile whose ČÚZK sheets are not fetched yet is a 503 with Retry-After: 60 (earth's ortho.py), at once; a busy
// address gets a 429. An <img> cannot read the status, so any failed tile is asked again after that minute, a few
// times. Stock Leaflet would leave it empty (the base map showing through) until panned away and back.
const ORTHO_RETRY_MS = 60_000;
const ORTHO_RETRIES = 3;
const orthoRetries = new WeakMap<HTMLElement, number>();

/** the orthophoto layer's tileerror handler */
export function retryOrthoTile(e: L.TileErrorEvent): void {
	const img = e.tile as HTMLImageElement;
	const n = orthoRetries.get(img) ?? 0;
	if (n >= ORTHO_RETRIES) return;
	orthoRetries.set(img, n + 1);
	const src = img.src;
	setTimeout(() => {
		// gone (pruned or the layer removed) or aborted by Leaflet (src swapped for its empty image): leave it
		// setting the same src fetches again: a failed load is never served from the image cache, nor a 503 from HTTP's
		if (img.isConnected && img.src === src) img.src = src;
	}, ORTHO_RETRY_MS);
}

/** read earth's channel once (on first use of the layer); later calls are no-ops */
export function ensureEarthOrtho(): Promise<void> {
	earthOrthoLoading ??= (async () => {
		if (!earthUrl) {
			console.warn('tileProviders: VITE_EARTH_URL is not set, no orthophoto over the base map');
			return;
		}
		try {
			const earth = await loadEarth(earthUrl, earthChannel);
			const release = earth.releases.ortho;
			if (!release || !earth.orthoExtent || !earth.orthoYear) {
				console.warn(`tileProviders: earth channel ${earthChannel} has no orthophoto`);
				return;
			}
			const src = earth.sources['cuzk-ortho'];
			if (!src) throw new Error('earth: /attribution has no cuzk-ortho');
			const [w, s, e, n] = earth.orthoExtent;
			// ČÚZK's terms: "ČÚZK, <year>", linking the terms; CC BY 4.0
			const attribution = `Ortofoto ČR &copy; ${creditLink(src.url, src.text.replace('{year}', earth.orthoYear))}, ` +
				creditLink(src.terms_url, src.licence);
			earthOrtho.set({
				url: `${earth.base}/t/${encodeURIComponent(release)}/ortho/{z}/{x}/{y}.jpg`,
				bounds: [[s, w], [n, e]],
				maxNativeZoom: EARTH_ORTHO_MAX_NATIVE_ZOOM,
				attribution
			});
		} catch (e) {
			console.warn('tileProviders: earth orthophoto unavailable, showing the base map alone', e);
			earthOrthoLoading = null; // a later selection of the layer asks again
		}
	})();
	return earthOrthoLoading;
}

/**
 * Set the current tile provider
 */
export function setTileProvider(provider: ProviderName): void {
	if (doLog) console.log('tileProviders.setTileProvider()', provider);
    if (provider in AVAILABLE_PROVIDERS) {
        currentTileProvider.set(provider);
    } else {
        console.warn(`Unknown tile provider: ${provider}, keeping current provider`);
    }
}

/**
 * Process attribution templates like {attribution.OpenStreetMap} with actual values
 */
function processAttributionTemplates(attribution: string, providers: any): string {
    if (!attribution) return '';

    if (doLog) console.log('Processing attribution templates in:', attribution);

    // Replace template patterns like {attribution.OpenStreetMap}
    return attribution.replace(/\{attribution\.([^}]+)\}/g, (match, providerName) => {
        if (doLog) console.log(`Found template: ${match}, provider: ${providerName}`);
        if (doLog) console.log(`Looking for provider "${providerName}" in providers:`, providers[providerName]);
        if (doLog) console.log(`Provider options:`, providers[providerName]?.options);

        if (providers[providerName] && providers[providerName].options?.attribution) {
            const replacementAttribution = providers[providerName].options.attribution;
            if (doLog) console.log(`Replacing ${match} with: ${replacementAttribution}`);
            return replacementAttribution;
        }
        // Fallback to a basic OpenStreetMap attribution if not found
        if (providerName === 'OpenStreetMap') {
            if (doLog) console.log('Using OpenStreetMap fallback attribution');
            return '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
        }
        if (doLog) console.log(`No attribution found for provider "${providerName}", keeping original template`);
        return match; // Return original if not found
    });
}

/**
 * Get provider configuration from custom providers or leaflet-providers
 */
export function getProviderConfig(providerName: ProviderName): TileProviderConfig {
	providerName = providerName || DEFAULT_TILE_PROVIDER;

	//console.log('tileProviders.getProviderConfig()', providerName);
    // Check custom providers first
    if (CUSTOM_PROVIDERS[providerName]) {
		//console.log('tileProviders.getProviderConfig() - using custom provider');
        return { ...CUSTOM_PROVIDERS[providerName] };
    }

    // Then check leaflet-providers
    const providers = (L.TileLayer as any).Provider?.providers;

    if (!providers) {
        console.warn('tileProviders: leaflet-providers not loaded, using fallback');
        return getFallbackConfig();
    }

    const parts = providerName.split('.');
    const providerKey = parts[0];
    const variant = parts[1];

    if (!providers[providerKey]) {
        console.warn(`tileProviders: Provider ${providerKey} not found, falling back to OpenStreetMap`);
        return getFallbackConfig();
    }

    const provider = providers[providerKey];
    const processedAttribution = processAttributionTemplates(provider.options?.attribution || '', providers);
    let config: TileProviderConfig = {
        url: provider.url,
        ...provider.options,
        attribution: processedAttribution  // Put this AFTER the spread to ensure it takes precedence
    };

    if (doLog) console.log('Raw attribution from provider:', provider.options?.attribution);
    if (doLog) console.log('Processed attribution:', config.attribution);
    if (doLog) console.log('Available providers keys:', Object.keys(providers));


    // Apply variant if specified
    if (variant && provider.variants && provider.variants[variant]) {
        const variantData = provider.variants[variant];
        if (typeof variantData === 'string') {
            // Simple string variant
            config.url = config.url.replace('{variant}', variantData);
        } else {
            // Complex variant with its own options
            const variantAttribution = variantData.options?.attribution;
            config = {
                ...config,
                ...variantData.options,
                url: variantData.url || config.url,
                attribution: variantAttribution ? processAttributionTemplates(variantAttribution, providers) : config.attribution
            };
        }
    }

    // Set maxNativeZoom from final config's maxZoom (after variant is applied)
    config.maxNativeZoom = config.maxZoom || 19;

    // Set our preferred max zoom (independent of provider)
    config.maxZoom = 24;

    return config;
}

/**
 * Get the current provider configuration
 */
export function getCurrentProviderConfig(): TileProviderConfig {
    return getProviderConfig(get(currentTileProvider) || DEFAULT_TILE_PROVIDER);
}

/**
 * Fallback configuration when leaflet-providers is not available
 */
function getFallbackConfig(): TileProviderConfig {
    return {
        url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    };
}

/**
 * Get provider display name
 */
export function getProviderDisplayName(provider: ProviderName): string {
    return AVAILABLE_PROVIDERS[provider] || provider;
}

/**
 * Get all available providers as array
 */
export function getAvailableProviders(): Array<{key: ProviderName, name: string}> {
    const isDev = import.meta.env.VITE_DEV_MODE === 'true';
    return Object.entries(AVAILABLE_PROVIDERS)
        .filter(([key]) => isDev || !DEV_ONLY_PROVIDERS.has(key as ProviderName))
        .map(([key, name]) => ({
            key: key as ProviderName,
            name
        }));
}

