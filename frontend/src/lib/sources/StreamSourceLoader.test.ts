import { describe, it, expect } from 'vitest';
import { convertStreamPhoto } from './StreamSourceLoader';

describe('convertStreamPhoto', () => {
    const sampleSource = { id: 'hillview', type: 'stream' };

    const basePhoto = {
        id: 'photo-123',
        geometry: { coordinates: [14.5, 50.1] },
        compass_angle: 90,
        thumb_1024_url: 'https://example.com/thumb.jpg',
        filename: 'test.jpg',
    };

    it('preserves license field when present in response', () => {
        const photo = { ...basePhoto, license: 'ccbysa4+osm' };
        const result = convertStreamPhoto(photo, sampleSource);
        expect((result as any).license).toBe('ccbysa4+osm');
    });

    it('preserves arr license for seed content', () => {
        const photo = { ...basePhoto, license: 'arr' };
        const result = convertStreamPhoto(photo, sampleSource);
        expect((result as any).license).toBe('arr');
    });

    it('does not set license when backend omits the field', () => {
        const result = convertStreamPhoto(basePhoto, sampleSource);
        expect((result as any).license).toBeUndefined();
    });

    it('copies creator info when present (Mapillary)', () => {
        const photo = { ...basePhoto, creator: { id: 'user-1', username: 'alice' } };
        const result = convertStreamPhoto(photo, sampleSource);
        expect((result as any).creator).toEqual({ id: 'user-1', username: 'alice' });
    });

    it('builds uid from source.id + photo.id', () => {
        const result = convertStreamPhoto(basePhoto, sampleSource);
        expect(result.uid).toBe('hillview-photo-123');
    });

    it('falls back through bearing candidates', () => {
        const photoWithComputed = { ...basePhoto, computed_compass_angle: 45, bearing: 180 };
        expect(convertStreamPhoto(photoWithComputed, sampleSource).bearing).toBe(45);

        const photoWithCompass = { ...basePhoto, compass_angle: 135, bearing: 180 };
        expect(convertStreamPhoto(photoWithCompass, sampleSource).bearing).toBe(135);

        const photoWithOnlyBearing = { ...basePhoto, compass_angle: undefined, bearing: 180 };
        expect(convertStreamPhoto(photoWithOnlyBearing, sampleSource).bearing).toBe(180);
    });
});
