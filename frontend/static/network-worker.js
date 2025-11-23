// Network service worker for handling tile loading failures

let currentTileProvider = null;

// Listen for messages from the main thread
self.addEventListener('message', (event) => {
    const { type, data } = event.data;

    switch (type) {
        case 'SET_TILE_PROVIDER':
            currentTileProvider = data;
            console.log('Network worker: Updated tile provider:', currentTileProvider);
            break;

        default:
            console.warn('Network worker: Unknown message type:', type);
    }
});

// Intercept fetch requests
self.addEventListener('fetch', (event) => {
    const request = event.request;

    // Handle tile requests for current provider
    if (currentTileProvider && isTileRequestForProvider(request.url, currentTileProvider)) {
        event.respondWith(handleTileRequest(request));
    }
});

function isTileRequestForProvider(requestUrl, provider) {
    // Convert provider URL template to regex pattern
    let pattern = provider.url
        .replace(/[.*+?^${}()|[\]\\]/g, '\\$&') // Escape special regex chars
        .replace('\\{z\\}', '\\d+')              // Replace {z} with digits
        .replace('\\{x\\}', '\\d+')              // Replace {x} with digits
        .replace('\\{y\\}', '\\d+');             // Replace {y} with digits

    // Handle subdomains if present
    if (provider.subdomains) {
        pattern = pattern.replace('\\{s\\}', `[${provider.subdomains}]`);
    }

    const regex = new RegExp('^' + pattern + '$');
    return regex.test(requestUrl);
}

async function handleTileRequest(request) {
    try {
        // Try the original request first
        const response = await fetch(request);

        if (response.ok) {
            return response;
        }

        console.log('Network worker: Tile request failed', {
            url: request.url,
            status: response.status,
            provider: currentTileProvider?.name
        });

        // Return an informative error tile
        return createErrorTile(`${currentTileProvider?.name} failed (${response.status})`);

    } catch (error) {
        console.log('Network worker: Tile request error', {
            url: request.url,
            error: error.message,
            provider: currentTileProvider?.name
        });

        return createErrorTile('Network error');
    }
}

function createErrorTile(errorMessage) {
    // Create a simple error tile with text
    const canvas = new OffscreenCanvas(256, 256);
    const ctx = canvas.getContext('2d');

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

    // Suggestion text with map icon
    ctx.font = '11px system-ui, sans-serif';
    ctx.fillText('Please try selecting a different provider', 128, 220);

    // Draw small map icon after the text
    drawLucideMapIcon(ctx, 120, 232, 16, '#6c757d');

    return canvas.convertToBlob({ type: 'image/png' })
        .then(blob => new Response(blob, {
            headers: {
                'Content-Type': 'image/png',
                'Cache-Control': 'no-cache'
            }
        }));
}

function drawLucideMapIcon(ctx, x, y, size, color) {
    ctx.strokeStyle = color;
    ctx.fillStyle = 'none';
    ctx.lineWidth = 1.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Scale factor to fit the size (Lucide icons are 24x24)
    const scale = size / 24;

    ctx.save();
    ctx.translate(x, y);
    ctx.scale(scale, scale);

    // Main map shape path from Lucide
    const mainPath = new Path2D('M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z');
    ctx.stroke(mainPath);

    // Vertical line on right
    ctx.beginPath();
    ctx.moveTo(15, 5.764);
    ctx.lineTo(15, 20.764);
    ctx.stroke();

    // Vertical line on left
    ctx.beginPath();
    ctx.moveTo(9, 3.236);
    ctx.lineTo(9, 18.236);
    ctx.stroke();

    ctx.restore();
}

// Error reporting to main thread
function reportError(error, context) {
    const message = {
        type: 'ERROR',
        error: error.message || String(error),
        context: context,
        timestamp: Date.now()
    };

    // Send to all clients
    self.clients.matchAll().then(clients => {
        clients.forEach(client => {
            client.postMessage(message);
        });
    }).catch(err => {
        console.error('Failed to send error to clients:', err);
    });
}

// Global error handler
self.addEventListener('error', (event) => {
    reportError(event.error, 'Global error');
});

// Unhandled promise rejection handler
self.addEventListener('unhandledrejection', (event) => {
    reportError(new Error(event.reason), 'Unhandled promise rejection');
});

// Service worker lifecycle
self.addEventListener('install', (event) => {
    console.log('Network worker: Installing');
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    console.log('Network worker: Activating');
    event.waitUntil(self.clients.claim());
});
