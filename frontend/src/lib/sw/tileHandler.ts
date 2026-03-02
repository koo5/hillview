// Tile fetch interception for service worker
// Intercepts tile requests and returns error tiles on failure

declare const self: ServiceWorkerGlobalScope;

interface TileProvider {
    name: string;
    url: string;
    subdomains?: string;
}

let currentTileProvider: TileProvider | null = null;

/** Handle SET_TILE_PROVIDER messages from the main thread */
export function handleMessage(event: ExtendableMessageEvent): boolean {
    const { type, data } = event.data;
    if (type === 'SET_TILE_PROVIDER') {
        currentTileProvider = data;
        console.log('[SW] Updated tile provider:', currentTileProvider);
        return true;
    }
    return false;
}

/** If the request is a tile for the current provider, intercept it */
export function handleFetch(event: FetchEvent): void {
    if (currentTileProvider && isTileRequestForProvider(event.request.url, currentTileProvider)) {
        event.respondWith(handleTileRequest(event.request));
    }
}

function isTileRequestForProvider(requestUrl: string, provider: TileProvider): boolean {
    let pattern = provider.url
        .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        .replace('\\{z\\}', '\\d+')
        .replace('\\{x\\}', '\\d+')
        .replace('\\{y\\}', '\\d+');

    if (provider.subdomains) {
        pattern = pattern.replace('\\{s\\}', `[${provider.subdomains}]`);
    }

    return new RegExp('^' + pattern + '$').test(requestUrl);
}

async function handleTileRequest(request: Request): Promise<Response> {
    try {
        const response = await fetch(request);
        if (response.ok) return response;

        console.log('[SW] Tile request failed', {
            url: request.url,
            status: response.status,
            provider: currentTileProvider?.name
        });
        return createErrorTile(`${currentTileProvider?.name} failed (${response.status})`);
    } catch (error: any) {
        console.log('[SW] Tile request error', {
            url: request.url,
            error: error.message,
            provider: currentTileProvider?.name
        });
        return createErrorTile('Network error');
    }
}

async function createErrorTile(errorMessage: string): Promise<Response> {
    const canvas = new OffscreenCanvas(256, 256);
    const ctx = canvas.getContext('2d')!;

    // Background
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(0, 0, 256, 256);

    // Border
    ctx.strokeStyle = '#dee2e6';
    ctx.lineWidth = 1;
    ctx.strokeRect(0, 0, 256, 256);

    // Error icon (simple X)
    ctx.strokeStyle = '#dc3545';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(100, 100);
    ctx.lineTo(156, 156);
    ctx.moveTo(156, 100);
    ctx.lineTo(100, 156);
    ctx.stroke();

    // Error text
    ctx.fillStyle = '#6c757d';
    ctx.font = '14px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Tile Loading Error', 128, 180);

    ctx.font = '12px system-ui, sans-serif';
    ctx.fillText(errorMessage, 128, 200);

    ctx.font = '11px system-ui, sans-serif';
    ctx.fillText('Please try selecting a different provider', 128, 220);

    drawLucideMapIcon(ctx, 120, 232, 16, '#6c757d');

    const blob = await canvas.convertToBlob({ type: 'image/png' });
    return new Response(blob, {
        headers: {
            'Content-Type': 'image/png',
            'Cache-Control': 'no-cache'
        }
    });
}

function drawLucideMapIcon(ctx: OffscreenCanvasRenderingContext2D, x: number, y: number, size: number, color: string): void {
    ctx.strokeStyle = color;
    ctx.fillStyle = 'none';
    ctx.lineWidth = 1.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    const scale = size / 24;
    ctx.save();
    ctx.translate(x, y);
    ctx.scale(scale, scale);

    const mainPath = new Path2D('M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z');
    ctx.stroke(mainPath);

    ctx.beginPath();
    ctx.moveTo(15, 5.764);
    ctx.lineTo(15, 20.764);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(9, 3.236);
    ctx.lineTo(9, 18.236);
    ctx.stroke();

    ctx.restore();
}
