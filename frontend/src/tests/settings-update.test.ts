import { describe, it, expect, vi, beforeEach } from 'vitest';

// Force TAURI mode before importing settings — the test targets the TAURI branch
// of updateSettings, which is where the partial-update race condition lived.
vi.mock('$lib/tauri', () => ({
    TAURI: true,
    BROWSER: false,
    TAURI_MOBILE: true,
    TAURI_DESKTOP: false,
    isTauriAvailable: () => true,
}));

// Mock $app/environment (imported transitively via svelte-shared-store)
vi.mock('$app/environment', () => ({
    browser: true,
}));

// Controllable invoke mock — each test sets up the response map.
vi.mock('@tauri-apps/api/core', () => ({
    invoke: vi.fn(),
}));

// Stub out IDB write — not relevant in TAURI mode, but imported by settings.ts.
vi.mock('$lib/browser/settingsIndexedDb', () => ({
    writeSettings: vi.fn(),
}));

const { invoke } = await import('@tauri-apps/api/core');
const mockInvoke = vi.mocked(invoke);

describe('updateSettings (TAURI, partial updates)', () => {
    beforeEach(async () => {
        // Reset modules so tauriSettingsStore starts fresh each test — otherwise
        // the previous test's load result is cached in the store's closure.
        vi.resetModules();
        mockInvoke.mockReset();
    });

    /**
     * Regression test for the silent field-stomping bug:
     * calling updateSettings({ auto_upload_enabled: false }) must not cause
     * auto_upload_prompt_enabled / wifi_only / landscape_armor22_workaround
     * to be dropped from the set_settings params.
     */
    it('merges partial updates against the loaded store value, not undefined', async () => {
        const existing = {
            auto_upload_enabled: true,
            auto_upload_prompt_enabled: true,
            wifi_only: true,
            landscape_armor22_workaround: false,
        };

        mockInvoke.mockImplementation((async (_cmd: string, args?: any) => {
            if (args?.command === 'get_settings') return existing;
            if (args?.command === 'set_settings') return undefined;
            throw new Error(`unexpected invoke: ${JSON.stringify(args)}`);
        }) as any);

        const { updateSettings } = await import('$lib/settings');
        await updateSettings({ auto_upload_enabled: false });

        const setCall = mockInvoke.mock.calls.find(
            ([, args]: any[]) => args?.command === 'set_settings'
        );
        expect(setCall, 'set_settings must be invoked').toBeDefined();
        expect(setCall![1]).toEqual({
            command: 'set_settings',
            params: {
                auto_upload_enabled: false,           // our override
                auto_upload_prompt_enabled: true,     // preserved from load
                wifi_only: true,                      // preserved from load
                landscape_armor22_workaround: false,  // preserved from load
            },
        });
    });

    /**
     * Race-condition regression test. Before the fix, updateSettings read
     * tauriSettingsStore synchronously via get(); if load() hadn't finished yet,
     * state.value was undefined and the spread collapsed to just newSettings.
     * The fix makes updateSettings await getSettings() first.
     *
     * Here we delay the get_settings response to simulate a slow load and
     * invoke updateSettings immediately — the resulting set_settings payload
     * must still be the full merge, not a partial.
     */
    it('waits for settings load before persisting', async () => {
        const existing = {
            auto_upload_enabled: true,
            auto_upload_prompt_enabled: true,
            wifi_only: true,
            landscape_armor22_workaround: true,
        };

        let resolveLoad: (v: any) => void = () => {};
        const loadPromise = new Promise<any>((r) => { resolveLoad = r; });

        mockInvoke.mockImplementation((async (_cmd: string, args?: any) => {
            if (args?.command === 'get_settings') return loadPromise;
            if (args?.command === 'set_settings') return undefined;
            throw new Error(`unexpected invoke: ${JSON.stringify(args)}`);
        }) as any);

        const { updateSettings } = await import('$lib/settings');
        // Kick off updateSettings before the load has resolved.
        const updatePromise = updateSettings({ auto_upload_enabled: false });

        // Give the event loop a few ticks so the polling loop inside getSettings
        // has a chance to run and observe the still-undefined store value.
        await new Promise((r) => setTimeout(r, 30));

        // set_settings must NOT have been called yet — updateSettings is waiting.
        const prematureSetCall = mockInvoke.mock.calls.find(
            ([, args]: any[]) => args?.command === 'set_settings'
        );
        expect(prematureSetCall, 'set_settings must not fire before load resolves').toBeUndefined();

        // Now let the load finish.
        resolveLoad(existing);
        await updatePromise;

        const setCall = mockInvoke.mock.calls.find(
            ([, args]: any[]) => args?.command === 'set_settings'
        );
        expect(setCall![1]).toEqual({
            command: 'set_settings',
            params: {
                auto_upload_enabled: false,
                auto_upload_prompt_enabled: true,
                wifi_only: true,
                landscape_armor22_workaround: true,
            },
        });
    });
});
