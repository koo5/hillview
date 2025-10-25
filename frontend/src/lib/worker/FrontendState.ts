import type { SourceConfig, Bounds } from '../photoWorkerTypes';

/**
 * FrontendState - Frontend Input State Manager
 *
 * This class manages the "input state" that comes from the frontend:
 * - Config: Source configuration (which photo sources are enabled, their settings)
 * - Area: Current map bounds the user is viewing
 *
 * System Flow:
 * 1. Frontend sends 'configUpdated'/'areaUpdated' messages
 * 2. MessageRouter calls this class to store the data and mark work as pending
 * 3. Main worker loop checks hasPendingWork() and starts processes via ProcessManager
 * 4. PhotoOperations reads this data to perform actual work (loading photos, filtering, etc.)
 * 5. When processes complete, this class marks work as processed
 *
 * This is different from SourcePhotosState which manages "computed state" (photos organized by source).
 *
 * Version Tracking:
 * - Tracks lastUpdateId vs lastProcessedId for each state type using message IDs
 * - Config updates trigger high-priority processes (can abort area processes)
 * - Area updates trigger lower-priority processes
 * - The version gap determines what work needs to be done
 */

interface StateItem {
    lastUpdateId: number;
    lastProcessedId: number;
}

export class FrontendState {
    private configState: StateItem = { lastUpdateId: -1, lastProcessedId: -1 };
    private areaState: StateItem = { lastUpdateId: -1, lastProcessedId: -1 };
    private configData: { sources: SourceConfig[]; [key: string]: any } | null = null;
    private areaData: Bounds | null = null;
    private currentRange: number;

    constructor(defaultRange: number) {
        this.currentRange = defaultRange;
    }

    // Config methods - source configuration from frontend
    updateConfig(data: { sources: SourceConfig[]; [key: string]: any }, messageId: number): void {
        this.configData = data;
        this.configState.lastUpdateId = messageId;
        console.log(`FrontendState: Updated config state (id: ${messageId})`);
    }

    getConfigData(): { sources: SourceConfig[]; [key: string]: any } | null {
        return this.configData;
    }

    markConfigProcessed(messageId: number): void {
        this.configState.lastProcessedId = messageId;
        console.log(`FrontendState: Marked config as processed (id: ${messageId})`);
    }

    isConfigPending(): boolean {
        return this.configState.lastUpdateId !== this.configState.lastProcessedId;
    }

    getConfigUpdateId(): number {
        return this.configState.lastUpdateId;
    }

    // Area methods - map bounds from frontend
    updateArea(data: Bounds, messageId: number, range?: number): void {
        this.areaData = data;
        this.areaState.lastUpdateId = messageId;

        if (range !== undefined) {
            this.currentRange = range;
        }

        console.log(`FrontendState: Updated area state (id: ${messageId})`);
    }

    getAreaData(): Bounds | null {
        return this.areaData;
    }

    markAreaProcessed(messageId: number): void {
        this.areaState.lastProcessedId = messageId;
        console.log(`FrontendState: Marked area as processed (id: ${messageId})`);
    }

    isAreaPending(): boolean {
        return this.areaState.lastUpdateId !== this.areaState.lastProcessedId;
    }

    getAreaUpdateId(): number {
        return this.areaState.lastUpdateId;
    }

    // Range methods - photo range filtering distance
    getCurrentRange(): number {
        return this.currentRange;
    }

    // Work scheduling methods - used by main worker loop
    hasPendingWork(): boolean {
        return this.isConfigPending() || this.isAreaPending();
    }

    getPendingWorkByPriority(): ('config' | 'area')[] {
        const pending: ('config' | 'area')[] = [];

        // Higher priority first - config can abort area processes
        if (this.isConfigPending()) {
            pending.push('config');
        }
        if (this.isAreaPending()) {
            pending.push('area');
        }

        return pending;
    }
}