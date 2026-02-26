/**
 * Factory for creating appropriate photo source loaders
 */

import type { SourceConfig, PhotoId, QueryOptions } from '../photoWorkerTypes';
import type { PhotoSourceLoader, PhotoSourceCallbacks } from './PhotoSourceLoader';
import { StreamSourceLoader } from './StreamSourceLoader';

export interface PhotoSourceOptions {
    maxPhotos?: number;
    picks?: Set<PhotoId>;
    queryOptions?: QueryOptions;
}

export class PhotoSourceFactory {
    static createLoader(source: SourceConfig, callbacks: PhotoSourceCallbacks, options?: PhotoSourceOptions): PhotoSourceLoader {
        console.log(`🢄PhotoSourceFactory: Creating loader for source:`, {
            id: source.id,
            type: source.type,
            enabled: source.enabled,
            options
        });

        switch (source.type) {
            case 'stream':
                console.log(`🢄PhotoSourceFactory: Creating StreamSourceLoader for ${source.id}`);
                return new StreamSourceLoader(source, callbacks, options);

            default:
                throw new Error(`Unsupported source type: ${source.type}`);
        }
    }
}
