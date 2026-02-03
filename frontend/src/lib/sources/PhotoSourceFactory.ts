/**
 * Factory for creating appropriate photo source loaders
 */

import type { SourceConfig, PhotoId } from '../photoWorkerTypes';
import type { PhotoSourceLoader, PhotoSourceCallbacks } from './PhotoSourceLoader';
import { StreamSourceLoader } from './StreamSourceLoader';
import { DeviceSourceLoader } from './DeviceSourceLoader';

export interface PhotoSourceOptions {
    maxPhotos?: number;
    picks?: Set<PhotoId>;
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

            case 'device':
                console.log(`🢄PhotoSourceFactory: Creating DeviceSourceLoader for ${source.id}`);
                return new DeviceSourceLoader(source, callbacks, options);

            default:
                throw new Error(`Unsupported source type: ${source.type}`);
        }
    }
}
