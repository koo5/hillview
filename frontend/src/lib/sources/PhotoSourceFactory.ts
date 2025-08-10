/**
 * Factory for creating appropriate photo source loaders
 */

import type { SourceConfig } from '../photoWorkerTypes';
import type { PhotoSourceLoader, PhotoSourceCallbacks } from './PhotoSourceLoader';
import { JsonSourceLoader, type JsonSourceCallbacks } from './JsonSourceLoader';
import { StreamSourceLoader } from './StreamSourceLoader';
import { DeviceSourceLoader } from './DeviceSourceLoader';

export class PhotoSourceFactory {
    static createLoader(source: SourceConfig, callbacks: PhotoSourceCallbacks): PhotoSourceLoader {
        switch (source.type) {
            case 'json':
                // JSON sources need caching callbacks
                return new JsonSourceLoader(source, callbacks as JsonSourceCallbacks);
                
            case 'stream':
                return new StreamSourceLoader(source, callbacks);
                
            case 'device':
                return new DeviceSourceLoader(source, callbacks);
                
            default:
                throw new Error(`Unsupported source type: ${source.type}`);
        }
    }
}