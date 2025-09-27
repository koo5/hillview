/**
 * Factory for creating appropriate photo source loaders
 */

import type { SourceConfig } from '../photoWorkerTypes';
import type { PhotoSourceLoader, PhotoSourceCallbacks } from './PhotoSourceLoader';
import { StreamSourceLoader } from './StreamSourceLoader';
import { DeviceSourceLoader } from './DeviceSourceLoader';

export interface PhotoSourceOptions {
    maxPhotos?: number;
}

export class PhotoSourceFactory {
    static createLoader(source: SourceConfig, callbacks: PhotoSourceCallbacks, options?: PhotoSourceOptions): PhotoSourceLoader {
        switch (source.type) {
            case 'stream':
                return new StreamSourceLoader(source, callbacks, options);

            case 'device':
                return new DeviceSourceLoader(source, callbacks);

            default:
                throw new Error(`Unsupported source type: ${source.type}`);
        }
    }
}