import { describe, it, expect } from 'vitest';
import { getLicenseId, getLicenseLabel, getUserProfileUrl } from './photoUtils';
import type { PhotoData } from './types/photoTypes';

// Minimal mock — functions under test only read `source` and `license` off
// the photo, so we can cast a plain literal to PhotoData.
function mockPhoto(partial: Record<string, any>): PhotoData {
    return partial as any;
}

describe('getLicenseId', () => {
    it('returns explicit license from a Hillview photo', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' }, license: 'ccbysa4+osm' });
        expect(getLicenseId(photo)).toBe('ccbysa4+osm');
    });

    it('returns arr for a Hillview photo with legal_rights=full1 (mapped on backend)', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' }, license: 'arr' });
        expect(getLicenseId(photo)).toBe('arr');
    });

    it('infers ccbysa4-mapillary for a Mapillary photo without explicit license', () => {
        const photo = mockPhoto({ source: { id: 'mapillary', type: 'stream' } });
        expect(getLicenseId(photo)).toBe('ccbysa4-mapillary');
    });

    it('prefers explicit license over Mapillary inference if both present', () => {
        // Defensive: if backend ever sends license on a Mapillary photo, honor it.
        const photo = mockPhoto({ source: { id: 'mapillary', type: 'stream' }, license: 'ccbysa4+osm' });
        expect(getLicenseId(photo)).toBe('ccbysa4+osm');
    });

    it('returns null for non-Mapillary source with no license', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' } });
        expect(getLicenseId(photo)).toBeNull();
    });

    it('returns null for a null photo', () => {
        expect(getLicenseId(null)).toBeNull();
    });

    it('handles string source (not object)', () => {
        const photo = mockPhoto({ source: 'mapillary' });
        expect(getLicenseId(photo)).toBe('ccbysa4-mapillary');
    });
});

describe('getLicenseLabel', () => {
    it('maps arr to All rights reserved', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' }, license: 'arr' });
        expect(getLicenseLabel(photo)).toBe('All rights reserved');
    });

    it('maps ccbysa4+osm to its display label', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' }, license: 'ccbysa4+osm' });
        expect(getLicenseLabel(photo)).toBe('CC BY-SA 4.0 + OSM mapping grant');
    });

    it('maps Mapillary-inferred id to CC BY-SA 4.0 (via Mapillary)', () => {
        const photo = mockPhoto({ source: { id: 'mapillary', type: 'stream' } });
        expect(getLicenseLabel(photo)).toBe('CC BY-SA 4.0 (via Mapillary)');
    });

    it('returns null when no license can be determined', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' } });
        expect(getLicenseLabel(photo)).toBeNull();
    });

    it('falls back to the raw identifier for unknown licenses', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' }, license: 'future-license-v99' });
        expect(getLicenseLabel(photo)).toBe('future-license-v99');
    });
});

describe('getUserProfileUrl', () => {
    it('returns internal profile URL for Hillview photo with owner_id', () => {
        const photo = mockPhoto({
            source: { id: 'hillview', type: 'stream' },
            owner_id: 'user-abc',
        });
        const url = getUserProfileUrl(photo);
        expect(url).toBeDefined();
        expect(url).toContain('user-abc');
    });

    it('returns external Mapillary profile URL when creator username is present', () => {
        const photo = mockPhoto({
            source: { id: 'mapillary', type: 'stream' },
            creator: { id: 'm-123', username: 'alice' },
        });
        expect(getUserProfileUrl(photo)).toBe('https://www.mapillary.com/app/user/alice');
    });

    it('returns undefined for Mapillary photo with no creator username', () => {
        const photo = mockPhoto({ source: { id: 'mapillary', type: 'stream' } });
        expect(getUserProfileUrl(photo)).toBeUndefined();
    });

    it('returns undefined for Hillview photo with no owner_id', () => {
        const photo = mockPhoto({ source: { id: 'hillview', type: 'stream' } });
        expect(getUserProfileUrl(photo)).toBeUndefined();
    });

    it('returns undefined for null photo', () => {
        expect(getUserProfileUrl(null)).toBeUndefined();
    });
});
