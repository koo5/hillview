import type { PhotoData, SourceConfig, Bounds } from '../photoWorkerTypes';
import type { SourceId } from '../CullingGrid';

export interface MessageHandlers {
    onFrontendConfigUpdated: (data: { sources: SourceConfig[]; [key: string]: any }, messageId: number) => void; // was updateConfig
    onFrontendAreaUpdated: (data: Bounds, messageId: number, range?: number) => void; // was updateArea
    triggerPhotoCombineProcess: () => void; // was updateSourcesPhotosInArea
    markProcessAsComplete: (processId: string, processType: string, messageId: number, results?: any) => void; // was completeProcess
    removeProcessFromTable: (processId: string) => void; // was cleanupProcess
    updateSourcePhotos: (sourceId: SourceId, photos: PhotoData[]) => void; // was setSourcePhotos
    removePhotoFromState: (photoId: string, source: SourceId) => void; // was removePhoto
    removeUserPhotosFromState: (userId: string, source: SourceId) => void; // was removeUserPhotos
    forwardToast: (message: any) => void; // was forwardMessage
    resolveAuthTokenPromise: (token: string) => void; // was handleAuthToken
    cleanupAndShutdown: () => void; // was terminate
}

interface InternalMessage {
    type: string;
    id: number;
    data?: any;
    internal?: boolean;
    [key: string]: any;
}

export class MessageRouter {
    constructor(private handlers: MessageHandlers) {}

    routeMessage(message: InternalMessage): boolean {
        switch (message.type) {
            case 'configUpdated':
                // Frontend sent new source configuration - triggers high priority config process
                this.handlers.onFrontendConfigUpdated(message.data, message.id);
                return true;

            case 'areaUpdated':
                // Frontend sent new area bounds - triggers area process to load photos in new bounds
                this.handlers.onFrontendAreaUpdated(message.data, message.id, message.data?.range);
                return true;

            case 'processComplete':
                // PhotoOperations finished a process - mark state as processed and cleanup
                this.handlers.markProcessAsComplete(
                    message.processId,
                    message.processType,
                    message.messageId,
                    message.results
                );
                return true;

            case 'loadError':
                console.error('MessageRouter: Load error from process:', JSON.stringify(message));
                if (message.processId) {
                    this.handlers.removeProcessFromTable(message.processId);
                }
                return true;

            case 'loadProgress':
                console.log(`MessageRouter: Load progress from ${message.sourceId}: ${message.loaded}${message.total ? `/${message.total}` : ''}`);
                return true;

            case 'photosAdded':
                // StreamSourceLoader accumulated more photos - update source photos and trigger combine
                console.log(`MessageRouter: Photos updated from stream ${message.sourceId}: ${message.photos?.length || 0} photos`);
                this.handlers.updateSourcePhotos(message.sourceId, message.photos);
                this.handlers.triggerPhotoCombineProcess();
                return true;

            case 'streamComplete':
                console.log(`MessageRouter: Stream completed for ${message.sourceId}: ${message.totalPhotos || 0} total photos`);
                return true;

            case 'removePhoto':
                // Frontend removed photo (hidden) - remove from state and send updated photos back
                console.log(`MessageRouter: Removing photo ${message.data.photoId} from ${message.data.source} state`);
                this.handlers.removePhotoFromState(message.data.photoId, message.data.source);
                return true;

            case 'removeUserPhotos':
                // Frontend removed user photos (hidden) - remove from state and send updated photos back
                console.log(`MessageRouter: Removing all photos by user ${message.data.userId} from ${message.data.source} state`);
                this.handlers.removeUserPhotosFromState(message.data.userId, message.data.source);
                return true;

            case 'toast':
                // PhotoOperations wants to show toast message - forward to frontend
                console.log(`MessageRouter: Forwarding toast message: ${message.level} - ${message.message} (source: ${message.source})`);
                this.handlers.forwardToast(message);
                return true;

            case 'authToken':
                // Frontend providing auth token - resolve pending auth promise
                this.handlers.resolveAuthTokenPromise(message.token);
                return true;

            case 'cleanup':
            case 'terminate':
                // Frontend shutting down worker - cleanup all resources and processes
                console.log('MessageRouter: Received cleanup/terminate message');
                this.handlers.cleanupAndShutdown();
                return true;

            default:
                console.warn(`MessageRouter: Unknown message type: ${message.type}`);
                return false;
        }
    }
}