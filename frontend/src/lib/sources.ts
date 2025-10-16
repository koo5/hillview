import type { PhotoData, PhotoSize } from './types/photoTypes';
import { parseCoordinate, parseFraction } from './utils/photoParser';

// Re-export utilities and types for backward compatibility
export { parseCoordinate, parseFraction } from './utils/photoParser';
export type { PhotoData, PhotoSize };
