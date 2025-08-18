/*
 * New Worker Architecture
 *
 * This worker has async processor functions for individual message types and uses photoProcessingUtils.ts.
 * 
 * Core Design:
 * - Main loop stores the last data received (sources, bearing, area, config)
 * - When handleMessage is called:
 *   - Update data immediately (never wait)
 *   - Mark conflicting processes for abortion (don't wait for them)
 *   - Start new processor immediately with latest data
 * 
 * Processing Priority (higher priority can interrupt lower):
 * 1. Config updates (includes sources, affects everything) - can abort area updates
 * 2. Area updates (affects filtering and triggers new loads) - lowest priority
 *
 * Why Priority Matters:
 * - Not just about worker operation length, but total system impact
 * - Example: area update filters and sends large photosInArea to frontend for rendering
 * - If config changes (including sources) during area filtering, the filtering becomes wasted work
 * - Config changes can invalidate all photo data and filtering results
 * - Bearing updates now handled entirely on frontend for simplicity
 *
 * Process Management:
 * - Explicit process table tracking ALL async operations
 * - Every process can be aborted: processConfig (includes sources), processArea
 * - No blocking waits - processes self-terminate when they check shouldAbort()
 * - Multiple processes can be running but aborting simultaneously
 * - Only latest data matters - intermediate values can be overwritten immediately
 * - New high-priority processes start immediately and mark conflicting processes for abortion
 * 
 * Architecture Separation:
 * - new.worker.ts: Process orchestration, message handling, process table management
 * - photoOperations.ts: Pure business logic for photo processing operations  
 * - PhotoLoadingProcess.ts: Individual load/stream operations
 * 
 * Process Types:
 * - Uses PhotoLoadingProcess class for individual load operations
 * - JSON sources: load once and cache, subsequent operations filter cached data
 * - Stream sources: new request for each bounds change
 * - Worker manages process lifecycle, photoOperations.ts handles the actual work
 * - All async operations tracked in process table regardless of complexity
 */

/// <reference lib="webworker" />

import type { PhotoData, SourceConfig, Bounds } from './photoWorkerTypes';
import { MessageQueue } from './MessageQueue';
import { PhotoOperations } from './photoOperations';
import { CullingGrid } from './CullingGrid';
import { AngularRangeCuller } from './AngularRangeCuller';
// Note: Using CullingGrid and AngularRangeCuller instead of photoProcessingUtils functions

declare const __WORKER_VERSION__: string;
export const WORKER_VERSION = __WORKER_VERSION__;
console.log(`NewWorker: Worker script loaded with version: ${WORKER_VERSION}`);


// Process tracking
interface ProcessInfo {
    id: string;
    type: 'config' | 'area' | 'sourcesPhotosInArea';
    messageId: number;
    startTime: number;
    shouldAbort: boolean;
}

const processTable = new Map<string, ProcessInfo>();
let processIdCounter = 0;
let messageIdCounter = 0;

// Current state - only the latest data matters  
const currentState = {
    config: { data: null as { sources: SourceConfig[]; [key: string]: any } | null, lastUpdateId: -1, lastProcessedId: -1 },
    area: { data: null as Bounds | null, lastUpdateId: -1, lastProcessedId: -1 },
    sourcesPhotosInArea: { data: null, lastUpdateId: -1, lastProcessedId: -1 }
};

// Track if we're blocked by running processes
let isBlocked = false;

// Debug timer for monitoring running processes
let processMonitorInterval: NodeJS.Timeout | null = null;

// Photo arrays - per-source tracking for smart culling
const photosInAreaPerSource = new Map<string, PhotoData[]>();
let cullingGrid: CullingGrid | null = null;
const angularRangeCuller = new AngularRangeCuller();

// Version tracking for sourcesPhotosInArea state
let sourcesPhotosInAreaVersion = 0;
let lastProcessedSourcesPhotosInAreaVersion = -1;

// Configuration
const MAX_PHOTOS_IN_AREA = 1000;
const MAX_PHOTOS_IN_RANGE = 300;

// Current range and center for range filtering
let currentRange = 1000; // Default range in meters, updated from area updates

function calculateCenterFromBounds(bounds: Bounds): { lat: number; lng: number } {
    return {
        lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
        lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
    };
}

// Merge and cull photos from all sources, calculate range
function mergeAndCullPhotos(): { photosInArea: PhotoData[], photosInRange: PhotoData[] } {
    if (!currentState.area.data || photosInAreaPerSource.size === 0) {
        console.log(`NewWorker: mergeAndCullPhotos early return - area.data:`, currentState.area.data, 'sources:', photosInAreaPerSource.size);
        return { photosInArea: [], photosInRange: [] };
    }

    console.log(`NewWorker: mergeAndCullPhotos - area bounds:`, currentState.area.data);
    console.log(`NewWorker: mergeAndCullPhotos - source photos counts:`, 
        Array.from(photosInAreaPerSource.entries()).map(([id, photos]) => `${id}: ${photos.length}`));

    // Create/update culling grid for current area
    if (!cullingGrid || currentState.area.lastUpdateId > (cullingGrid as any).lastUpdateId) {
        cullingGrid = new CullingGrid(currentState.area.data);
        (cullingGrid as any).lastUpdateId = currentState.area.lastUpdateId;
        console.log(`NewWorker: Created new culling grid for area bounds:`, currentState.area.data);
    }

    // Apply smart culling for uniform screen coverage
    const photosInArea = cullingGrid.cullPhotos(photosInAreaPerSource, MAX_PHOTOS_IN_AREA);
    console.log(`NewWorker: After culling - ${photosInArea.length} photos in area (max: ${MAX_PHOTOS_IN_AREA})`);
    
    // Log a few photo locations for debugging
    if (photosInArea.length > 0) {
        console.log(`NewWorker: First few photo locations:`, 
            photosInArea.slice(0, 3).map(p => `[${p.coord.lat.toFixed(4)}, ${p.coord.lng.toFixed(4)}]`));
    }
    
    // Calculate center for range filtering
    const center = calculateCenterFromBounds(currentState.area.data);
    
    // Apply angular range culling for uniform angular coverage
    const photosInRange = angularRangeCuller.cullPhotosInRange(
        photosInArea, 
        center, 
        currentRange, 
        MAX_PHOTOS_IN_RANGE
    );
    
    // Sort photos in range by bearing for consistent navigation order
    photosInRange.sort((a, b) => {
        if (a.bearing !== b.bearing) {
            return a.bearing - b.bearing;
        }
        return a.id.localeCompare(b.id); // Stable sort with ID as tiebreaker
    });
    
    console.log(`NewWorker: Merged ${photosInAreaPerSource.size} sources → ${photosInArea.length} in area → ${photosInRange.length} in range with angular coverage`);
    
    return { 
        photosInArea, 
        photosInRange 
    };
}

// Direct photo array transfer (no serialization needed)
function sendPhotosUpdate(): void {
    // Merge and cull photos from all sources
    const { photosInArea, photosInRange } = mergeAndCullPhotos();
    
    // Send raw arrays directly - structured clone algorithm handles transfer efficiently
    postMessage({
        type: 'photosUpdate',
        photosInArea: [...photosInArea],
        photosInRange: [...photosInRange],
        currentRange: currentRange,
        timestamp: Date.now()
    });
    
    console.log(`NewWorker: Sent ${photosInArea.length} area photos + ${photosInRange.length} range photos directly`);
}


// No longer needed - using direct array transfer via structured clone algorithm

const messageQueue = new MessageQueue();
const photoOperations = new PhotoOperations();

// Process priority levels for abortion logic
const PROCESS_PRIORITY = {
    config: 1,
    area: 2
} as const;

function createProcessId(): string {
    return `proc_${++processIdCounter}_${Date.now()}`;
}

function shouldAbortProcess(processId: string): boolean {
    const processInfo = processTable.get(processId);
    return processInfo?.shouldAbort || false;
}

function markConflictingProcessesForAbortion(newProcessType: 'config' | 'area' | 'sourcesPhotosInArea'): void {
    const newPriority = getProcessPriority(newProcessType);
    
    for (const [processId, processInfo] of processTable.entries()) {
        const existingPriority = getProcessPriority(processInfo.type);
        
        // Only abort existing processes if new process has HIGHER priority
        // Config (priority 2) can abort Area (priority 1)
        // Area (priority 1) cannot abort Config (priority 2)
        if (newPriority > existingPriority) {
            console.log(`NewWorker: Marking process ${processId} (${processInfo.type}) for abortion due to higher priority ${newProcessType} update`);
            processInfo.shouldAbort = true;
        }
    }
}

function cleanupProcess(processId: string): void {
    processTable.delete(processId);
    console.log(`NewWorker: Cleaned up process ${processId}`);
}

async function startProcess(type: 'config' | 'area' | 'sourcesPhotosInArea', messageId: number): Promise<void> {
    const processId = createProcessId();
    
    // Mark conflicting processes for abortion
    markConflictingProcessesForAbortion(type);
    
    // Create process info
    const processInfo: ProcessInfo = {
        id: processId,
        type,
        messageId,
        startTime: Date.now(),
        shouldAbort: false
    };
    
    processTable.set(processId, processInfo);
    console.log(`NewWorker: Started ${type} process ${processId}`);
    
    // Start async operation via photoOperations - it will post completion messages back to the queue
    const operationCallbacks = {
        shouldAbort: (id: string) => shouldAbortProcess(id),
        postMessage: (message: any) => messageQueue.addMessage(message),
        updatePhotosInArea: (photos: PhotoData[]) => { 
            // For config updates, distribute photos across per-source tracking
            if (photos.length > 0) {
                // Group by source if available, otherwise use 'default'
                const photosBySource = new Map<string, PhotoData[]>();
                for (const photo of photos) {
                    const sourceId = photo.source?.id || 'default';
                    if (!photosBySource.has(sourceId)) {
                        photosBySource.set(sourceId, []);
                    }
                    photosBySource.get(sourceId)!.push(photo);
                }
                // Update per-source tracking
                for (const [sourceId, sourcePhotos] of photosBySource.entries()) {
                    photosInAreaPerSource.set(sourceId, sourcePhotos);
                }
            }
        },
        updatePhotosInRange: (photos: PhotoData[]) => { 
            // Not used in current implementation - range calculation is done in mergeAndCullPhotos
        },
        getPhotosInArea: () => {
            const allPhotos: PhotoData[] = [];
            for (const photos of photosInAreaPerSource.values()) {
                allPhotos.push(...photos);
            }
            return allPhotos;
        },
        getPhotosInRange: () => {
            // Not used in current implementation
            return [];
        },
        sendPhotosInAreaUpdate: () => sendPhotosUpdate(),
        sendPhotosInRangeUpdate: () => sendPhotosUpdate()
    };

    // Start the actual business logic operations
    try {
        if (type === 'config') {
            console.log(`NewWorker: Calling PROCESSCONFIG for ${processId}`);
            if (currentState.config.data) {
                photoOperations.processConfig(processId, messageId, currentState.config.data, operationCallbacks);
            } else {
                console.warn(`NewWorker: PROCESSCONFIG - Config data is null for process ${processId}`);
            }
        } else if (type === 'area') {
            console.log(`NewWorker: About to call processArea with area:`, currentState.area.data, 'sources:', currentState.config.data?.sources?.length || 0);
            if (currentState.area.data) {
                photoOperations.processArea(
                    processId, 
                    messageId,
                    currentState.area.data, 
                    currentState.config.data?.sources || [], 
                    operationCallbacks
                );
            } else {
                console.warn(`NewWorker: Area data is null for process ${processId}`);
            }
        } else if (type === 'sourcesPhotosInArea') {
            console.log(`NewWorker: Calling processCombinePhotos for ${processId}`);
            photoOperations.processCombinePhotos(
                processId,
                messageId,
                currentState.area.data,
                currentState.config.data?.sources || [],
                operationCallbacks
            );
        }
    } catch (error) {
        console.error(`NewWorker: Error in startProcess ${type}:`, error);
        cleanupProcess(processId);
    }
}

function handleMessage(message: any): void {
	// Handle special cleanup message
	if (message.type === 'cleanup' || message.type === 'terminate') {
		console.log('NewWorker: Received cleanup/terminate message, cleaning up resources');
		
		// Abort all running processes
		for (const [processId, process] of processTable.entries()) {
			console.log(`NewWorker: Aborting process ${processId}`);
			process.shouldAbort = true;
		}
		processTable.clear();
		
		// Clean up photo operations (cancels loaders, clears caches)
		photoOperations.cleanup();
		
		// Stop process monitor
		stopProcessMonitor();
		
		// Clear message queue
		messageQueue.clear();
		
		// Send confirmation
		postMessage({ type: 'cleanupComplete' });
		return;
	}
	
	// Add the message to the queue with unique ID
	messageQueue.addMessage({...message, id: messageIdCounter++});
}

// Export handleMessage for testing
export { handleMessage };



function startProcessMonitor(): void {
	// Start periodic process monitoring (every 10 seconds)
	processMonitorInterval = setInterval(() => {
		listRunningProcesses();
	}, 10000);
	console.log('NewWorker: Process monitor started (10s interval)');
}

function stopProcessMonitor(): void {
	if (processMonitorInterval) {
		clearInterval(processMonitorInterval);
		processMonitorInterval = null;
		console.log('NewWorker: Process monitor stopped');
	}
}

async function loop(): Promise<void> {
	console.log('NewWorker: Starting main event loop');
	
	// Start the process monitor
	startProcessMonitor();
	
	while (true) {
		// Process all messages from the queue
		while (true) {
			let message;
			
			// Check if we need to process anything
			const needsProcessing = hasUnprocessedUpdates();
			const hasQueuedMessages = messageQueue.hasMore();
			
			console.log(`NewWorker: Loop iteration - needsProcessing: ${needsProcessing}, hasQueuedMessages: ${hasQueuedMessages}`);
			
			if (!needsProcessing && !hasQueuedMessages) {
				// Nothing to do, wait for next message
				console.log('NewWorker: Waiting for next message...');
				message = await messageQueue.getNextMessage();
				console.log('NewWorker: Got message from queue:', message?.type);
				isBlocked = false; // Clear blocked flag when we get a new message
			} else if (hasQueuedMessages) {
				// Process queued messages first
				console.log('NewWorker: Processing queued message...');
				message = await messageQueue.getNextMessage();
				console.log('NewWorker: Got queued message:', message?.type);
				isBlocked = false; // Clear blocked flag when we get a new message
			} else if (isBlocked) {
				// We're blocked by running processes, sleep instead of spinning
				console.log('NewWorker: Blocked by running processes, waiting for next message...');
				message = await messageQueue.getNextMessage();
				console.log('NewWorker: Unblocked by message:', message?.type);
				isBlocked = false; // Clear blocked flag
			} else {
				// No more messages but we have unprocessed updates
				console.log('NewWorker: No more messages, processing pending updates...');
				break;
			}
			
			if (!message) {
				console.log('NewWorker: Got null message, continuing...');
				continue; // Handle queue cancellation
			}
			
			console.log(`NewWorker: Processing message ${message.type} (id: ${message.id})`);
			
			// Handle different message types
			switch (message.type) {
				case 'configUpdated':
					updateState('config', message);
					break;
					
				case 'areaUpdated':
					updateState('area', message);
					break;
					
				case 'processComplete':
					handleProcessCompletion(message);
					break;
					
				case 'loadError':
					// Handle loading errors from PhotoLoadingProcess
					console.error('NewWorker: Load error from process:', JSON.stringify(message));
					// Mark the process as failed but continue processing
					if (message.processId) {
						cleanupProcess(message.processId);
					}
					break;
				
				case 'loadProgress':
					// Handle loading progress updates from PhotoLoadingProcess
					console.log(`NewWorker: Load progress from ${message.sourceId}: ${message.loaded}${message.total ? `/${message.total}` : ''}`);
					// Just log progress, no action needed
					break;

				case 'photosAdded':
					// Handle streaming photo updates from StreamSourceLoader
					console.log(`NewWorker: Photos updated from stream ${message.sourceId}: ${message.photos?.length || 0} photos`);
					if (message.photos && Array.isArray(message.photos)) {
						// Replace the photo array for this source (source handles accumulation)
						photosInAreaPerSource.set(message.sourceId, message.photos);
						console.log(`NewWorker: Source ${message.sourceId} set to ${message.photos.length} photos`);
						
						// Update sourcesPhotosInArea version to trigger combine operation
						sourcesPhotosInAreaVersion++;
						updateState('sourcesPhotosInArea', { id: sourcesPhotosInAreaVersion });
					}
					break;
				
				case 'streamComplete':
					// Handle stream completion from StreamSourceLoader
					console.log(`NewWorker: Stream completed for ${message.sourceId}: ${message.totalPhotos || 0} total photos`);
					// Stream is complete, no additional action needed
					break;
					
				case 'exit':
					console.log('NewWorker: Exit requested');
					stopProcessMonitor();
					return;
					
				default:
					console.warn(`NewWorker: Unknown message type: ${message.type}`);
			}
		}
		
		// Start new processes for unprocessed updates (by priority)
		const canProcess = await startPendingProcesses();
		
		// If we're blocked by running processes, set blocked flag and continue loop
		if (!canProcess) {
			isBlocked = true;
			console.log('NewWorker: Cannot process - setting blocked flag');
		}
	}
}

function hasUnprocessedUpdates(): boolean {
	const configUnprocessed = currentState.config.lastUpdateId !== currentState.config.lastProcessedId;
	const areaUnprocessed = currentState.area.lastUpdateId !== currentState.area.lastProcessedId;
	const sourcesPhotosInAreaUnprocessed = currentState.sourcesPhotosInArea.lastUpdateId !== currentState.sourcesPhotosInArea.lastProcessedId;
	const result = configUnprocessed || areaUnprocessed || sourcesPhotosInAreaUnprocessed;
	
	if (result) {
		console.log(`NewWorker: hasUnprocessedUpdates - config: ${configUnprocessed} (update=${currentState.config.lastUpdateId}, processed=${currentState.config.lastProcessedId}), area: ${areaUnprocessed} (update=${currentState.area.lastUpdateId}, processed=${currentState.area.lastProcessedId}), sourcesPhotosInArea: ${sourcesPhotosInAreaUnprocessed} (update=${currentState.sourcesPhotosInArea.lastUpdateId}, processed=${currentState.sourcesPhotosInArea.lastProcessedId})`);
	}
	
	return result;
}

function updateState(type: 'config' | 'area' | 'sourcesPhotosInArea', message: any): void {
	if (!message.internal && message.data) {
		// Update state immediately - no waiting
		currentState[type].data = message.data[type] || message.data.area || message.data;
		currentState[type].lastUpdateId = message.id;
		
		// Update range if provided in area updates
		if (type === 'area' && message.data.range) {
			currentRange = message.data.range;
			console.log(`NewWorker: Updated range to ${currentRange}m`);
		}
		
		console.log(`NewWorker: Updated ${type} state (id: ${message.id})`);
	}
}

function handleProcessCompletion(message: any): void {
	const { processId, processType, messageId, results } = message;
	
	console.log(`NewWorker: Process ${processId} (${processType}) completed`);
	
	// Mark as processed if this is the latest version
	const validProcessType = processType as keyof typeof currentState;
	if (currentState[validProcessType] && currentState[validProcessType].lastUpdateId === messageId) {
		currentState[validProcessType].lastProcessedId = messageId;
		console.log(`NewWorker: Marked ${processType} as processed (id: ${messageId})`);
	}
	
	// Incorporate any results into state
	if (results) {
		// TODO: Handle specific result types
		console.log(`NewWorker: Incorporating results from ${processType} process`);
	}
	
	// Clean up the process
	cleanupProcess(processId);
}

function hasRunningProcess(): boolean {
	for (const [processId, processInfo] of processTable.entries()) {
		if (!processInfo.shouldAbort) {
			return true;
		}
	}
	return false;
}

function listRunningProcesses(): void {
	const runningProcesses = [];
	const abortedProcesses = [];
	
	for (const [processId, processInfo] of processTable.entries()) {
		const duration = Date.now() - processInfo.startTime;
		const processData = {
			id: processId,
			type: processInfo.type,
			messageId: processInfo.messageId,
			duration: `${duration}ms`,
			shouldAbort: processInfo.shouldAbort
		};
		
		if (processInfo.shouldAbort) {
			abortedProcesses.push(processData);
		} else {
			runningProcesses.push(processData);
		}
	}
	
	if (runningProcesses.length > 0 || abortedProcesses.length > 0) {
		console.log(`NewWorker: Process Monitor - Running: ${runningProcesses.length}, Aborting: ${abortedProcesses.length}`);
		
		if (runningProcesses.length > 0) {
			console.log('  Active processes:', runningProcesses);
		}
		
		if (abortedProcesses.length > 0) {
			console.log('  Aborting processes:', abortedProcesses);
		}
		
		// Also log current state for context
		console.log(`  State - Config: update=${currentState.config.lastUpdateId}/processed=${currentState.config.lastProcessedId}, Area: update=${currentState.area.lastUpdateId}/processed=${currentState.area.lastProcessedId}, isBlocked: ${isBlocked}`);
	} else {
		console.log('NewWorker: Process Monitor - No active processes');
	}
}

function getProcessPriority(type: 'config' | 'area' | 'sourcesPhotosInArea'): number {
	// Higher number = higher priority
	if (type === 'config') return 3;
	if (type === 'area') return 2;
	if (type === 'sourcesPhotosInArea') return 1;
	return 0;
}

async function startPendingProcesses(): Promise<boolean> {
	// Only start processes if no active process is running
	if (hasRunningProcess()) {
		console.log('NewWorker: Process already running, waiting for completion');
		return false; // Return false to indicate we're blocked
	}

	// Start processes by priority - higher priority first
	if (currentState.config.lastUpdateId !== currentState.config.lastProcessedId) {
		console.log(`NewWorker: STARTING CONFIG update PROCESS FOR MESSAGE ${currentState.config.lastUpdateId}`);

		await startProcess('config', currentState.config.lastUpdateId);
	} else if (currentState.area.lastUpdateId !== currentState.area.lastProcessedId) {
		console.log(`NewWorker: Starting area update process for message ${currentState.area.lastUpdateId}`);
		await startProcess('area', currentState.area.lastUpdateId);
	} else if (currentState.sourcesPhotosInArea.lastUpdateId !== currentState.sourcesPhotosInArea.lastProcessedId) {
		console.log(`NewWorker: Starting sourcesPhotosInArea update process for message ${currentState.sourcesPhotosInArea.lastUpdateId}`);
		await startProcess('sourcesPhotosInArea', currentState.sourcesPhotosInArea.lastUpdateId);
	} else {
		console.log('NewWorker: No pending processes to start');
	}
	
	return true; // Return true to indicate we successfully started or completed processing
}

// Set up message handler from main thread
self.onmessage = function(e: MessageEvent) {
	console.log('NewWorker: Received message from main thread:', e.data.type);
	handleMessage(e.data);
};

// Start the main loop
loop().catch(error => {
	console.error('NewWorker: Fatal error in main loop:', error);
	stopProcessMonitor();
	postMessage({
		type: 'error',
		error: {
			message: error?.message || 'Unknown error in main loop',
			timestamp: Date.now()
		}
	});
});

console.log('NewWorker: Initialization complete');