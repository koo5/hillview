import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import { locationTracking } from '$lib/location.svelte';

describe('Location Toggle State', () => {
    it('should have working location tracking store', () => {
        // Test that the store works
        locationTracking.set(false);
        expect(get(locationTracking)).toBe(false);
        
        locationTracking.set(true);
        expect(get(locationTracking)).toBe(true);
    });

    it('should export the locationTracking store', () => {
        // Test that our module exports what we expect
        expect(locationTracking).toBeDefined();
        expect(typeof locationTracking.set).toBe('function');
        expect(typeof locationTracking.subscribe).toBe('function');
    });
});