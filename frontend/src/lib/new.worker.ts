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
import { PhotoLoadingProcess, type PhotoLoadingCallbacks } from './PhotoLoadingProcess';
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
    type: 'config' | 'area';
    messageId: number;
    startTime: number;
    shouldAbort: boolean;
}

const processTable = new Map<string, ProcessInfo>();
let processIdCounter = 0;
let messageIdCounter = 0;

// Current state - only the latest data matters  
const currentState = {
    config: { data: null as { sources: SourceConfig[]; [key: string]: any } | null, lastUpdateId: 0, lastProcessedId: 0 },
    area: { data: null as Bounds | null, lastUpdateId: 0, lastProcessedId: 0 }
};

// Photo arrays - per-source tracking for smart culling
const photosInAreaPerSource = new Map<string, PhotoData[]>();
let cullingGrid: CullingGrid | null = null;
const angularRangeCuller = new AngularRangeCuller();

// Configuration
const MAX_PHOTOS_IN_AREA = 700;
const MAX_PHOTOS_IN_RANGE = 200;

// Current range and center for range filtering
let currentRange = 1000; // Default range in meters

function calculateCenterFromBounds(bounds: Bounds): { lat: number; lng: number } {
    return {
        lat: (bounds.top_left.lat + bounds.bottom_right.lat) / 2,
        lng: (bounds.top_left.lng + bounds.bottom_right.lng) / 2
    };
}

// Merge and cull photos from all sources, calculate range
function mergeAndCullPhotos(): { photosInArea: PhotoData[], photosInRange: PhotoData[] } {
    if (!currentState.area.data || photosInAreaPerSource.size === 0) {
        return { photosInArea: [], photosInRange: [] };
    }

    // Create/update culling grid for current area
    if (!cullingGrid || currentState.area.lastUpdateId > (cullingGrid as any).lastUpdateId) {
        cullingGrid = new CullingGrid(currentState.area.data);
        (cullingGrid as any).lastUpdateId = currentState.area.lastUpdateId;
    }

    // Apply smart culling for uniform screen coverage
    const photosInArea = cullingGrid.cullPhotos(photosInAreaPerSource, MAX_PHOTOS_IN_AREA);
    
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

function markConflictingProcessesForAbortion(newProcessType: 'config' | 'area'): void {
    const newPriority = PROCESS_PRIORITY[newProcessType];
    
    for (const [processId, processInfo] of processTable.entries()) {
        const existingPriority = PROCESS_PRIORITY[processInfo.type];
        
        // Mark for abortion if new process has higher priority (lower number)
        if (newPriority <= existingPriority) {
            console.log(`NewWorker: Marking process ${processId} (${processInfo.type}) for abortion due to ${newProcessType} update`);
            processInfo.shouldAbort = true;
        }
    }
}

function cleanupProcess(processId: string): void {
    processTable.delete(processId);
    console.log(`NewWorker: Cleaned up process ${processId}`);
}

async function startProcess(type: 'config' | 'area', messageId: number): Promise<void> {
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
        updatePhotosInAreaForSource: (sourceId: string, photos: PhotoData[]) => { 
            photosInAreaPerSource.set(sourceId, photos);
        },
        getPhotosInAreaPerSource: () => new Map(photosInAreaPerSource),
        sendPhotosUpdate: () => sendPhotosUpdate()
    };

    // Start the actual business logic operations
    if (type === 'config') {
        photoOperations.processConfig(processId, currentState.config.data, operationCallbacks);
    } else if (type === 'area') {
        photoOperations.processArea(
            processId, 
            currentState.area.data, 
            currentState.config.data?.sources || [], 
            operationCallbacks
        );
    }
}

function handleMessage(message: any): void {
	// Add the message to the queue with unique ID
	messageQueue.addMessage({...message, id: messageIdCounter++});
}



async function loop(): Promise<void> {
	console.log('NewWorker: Starting main event loop');
	
	while (true) {
		// Process all messages from the queue
		while (true) {
			let message;
			
			// Check if we need to process anything
			const needsProcessing = hasUnprocessedUpdates();
			
			if (!needsProcessing && !messageQueue.hasMore()) {
				// Nothing to do, wait for next message
				message = await messageQueue.getNextMessage();
			} else if (messageQueue.hasMore()) {
				// Process queued messages first
				message = await messageQueue.getNextMessage();
			} else {
				// No more messages but we have unprocessed updates
				break;
			}
			
			if (!message) continue; // Handle queue cancellation
			
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
					
				case 'exit':
					console.log('NewWorker: Exit requested');
					return;
					
				default:
					console.warn(`NewWorker: Unknown message type: ${message.type}`);
			}
		}
		
		// Start new processes for unprocessed updates (by priority)
		await startPendingProcesses();
	}
}

function hasUnprocessedUpdates(): boolean {
	return (
		currentState.config.lastUpdateId !== currentState.config.lastProcessedId ||
		currentState.area.lastUpdateId !== currentState.area.lastProcessedId
	);
}

function updateState(type: 'config' | 'area', message: any): void {
	if (!message.internal && message.data) {
		// Update state immediately - no waiting
		currentState[type].data = message.data[type] || message.data;
		currentState[type].lastUpdateId = message.id;
		console.log(`NewWorker: Updated ${type} state (id: ${message.id})`);
	}
}

function handleProcessCompletion(message: any): void {
	const { processId, processType, messageId, results } = message;
	
	console.log(`NewWorker: Process ${processId} (${processType}) completed`);
	
	// Mark as processed if this is the latest version
	if (currentState[processType].lastUpdateId === messageId) {
		currentState[processType].lastProcessedId = messageId;
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

async function startPendingProcesses(): Promise<void> {
	// Start processes by priority - higher priority first
	if (currentState.config.lastUpdateId !== currentState.config.lastProcessedId) {
		await startProcess('config', currentState.config.lastUpdateId);
	} else if (currentState.area.lastUpdateId !== currentState.area.lastProcessedId) {
		await startProcess('area', currentState.area.lastUpdateId);
	}
}

// Set up message handler from main thread
self.onmessage = function(e: MessageEvent) {
	console.log('NewWorker: Received message from main thread:', e.data.type);
	handleMessage(e.data);
};

// Start the main loop
loop().catch(error => {
	console.error('NewWorker: Fatal error in main loop:', error);
	postMessage({
		type: 'error',
		error: {
			message: error?.message || 'Unknown error in main loop',
			timestamp: Date.now()
		}
	});
});

console.log('NewWorker: Initialization complete');