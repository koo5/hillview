import L from 'leaflet';
import 'leaflet-providers';
import { writable, get } from 'svelte/store';

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
const API_KEYS = {
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
	}
};

// Available tile providers with descriptions
export const AVAILABLE_PROVIDERS = {
	'tiles.ueueeu.eu': 'tiles.ueueeu.eu',

    // Standard 'leaflet-providers' providers
    'OpenStreetMap.Mapnik': 'OpenStreetMap',
    'OpenStreetMap.DE': 'OpenStreetMap (German)',
    'CartoDB.DarkMatter': 'CartoDB Dark',
    'OpenTopoMap': 'OpenTopoMap',
    'CyclOSM': 'CyclOSM (Cycling)',

    // my Custom providers
    'TracesTrack.Topo': 'TracesTrack Topographic',
    /*'TracesTrack.TopoContrast': 'TracesTrack Topo (High Contrast)',*/

} as const;

export type ProviderName = keyof typeof AVAILABLE_PROVIDERS;

// Default tile provider
export const DEFAULT_TILE_PROVIDER: ProviderName = 'tiles.ueueeu.eu';//'OpenStreetMap.Mapnik';

// Current selected provider (can be changed at runtime)
export const currentTileProvider = writable<ProviderName>(DEFAULT_TILE_PROVIDER);

/**
 * Set the current tile provider
 */
export function setTileProvider(provider: ProviderName): void {
	console.log('tileProviders.setTileProvider()', provider);
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

    console.log('Processing attribution templates in:', attribution);

    // Replace template patterns like {attribution.OpenStreetMap}
    return attribution.replace(/\{attribution\.([^}]+)\}/g, (match, providerName) => {
        console.log(`Found template: ${match}, provider: ${providerName}`);
        console.log(`Looking for provider "${providerName}" in providers:`, providers[providerName]);
        console.log(`Provider options:`, providers[providerName]?.options);

        if (providers[providerName] && providers[providerName].options?.attribution) {
            const replacementAttribution = providers[providerName].options.attribution;
            console.log(`Replacing ${match} with: ${replacementAttribution}`);
            return replacementAttribution;
        }
        // Fallback to a basic OpenStreetMap attribution if not found
        if (providerName === 'OpenStreetMap') {
            console.log('Using OpenStreetMap fallback attribution');
            return '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
        }
        console.log(`No attribution found for provider "${providerName}", keeping original template`);
        return match; // Return original if not found
    });
}

/**
 * Get provider configuration from custom providers or leaflet-providers
 */
export function getProviderConfig(providerName: ProviderName): TileProviderConfig {
	console.log('tileProviders.getProviderConfig()', providerName);
    // Check custom providers first
    if (CUSTOM_PROVIDERS[providerName]) {
		console.log('tileProviders.getProviderConfig() - using custom provider');
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

    console.log('Raw attribution from provider:', provider.options?.attribution);
    console.log('Processed attribution:', config.attribution);
    console.log('Available providers keys:', Object.keys(providers));


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
    return Object.entries(AVAILABLE_PROVIDERS).map(([key, name]) => ({
        key: key as ProviderName,
        name
    }));
}

