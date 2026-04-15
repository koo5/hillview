import {createRemoteStore} from './remoteStore';
import {invoke} from "@tauri-apps/api/core";
import {BROWSER, TAURI} from "$lib/tauri";
import {localStorageSharedStore} from "$lib/svelte-shared-store";
import {get} from "svelte/store";
import {writeSettings} from './browser/settingsIndexedDb';

export interface Settings {
	auto_upload_enabled: boolean;
	auto_upload_prompt_enabled: boolean;
	wifi_only: boolean;
	landscape_armor22_workaround: boolean;
};

export const settingsDefaults: Settings = {
	auto_upload_enabled: false,
	auto_upload_prompt_enabled: true,
	wifi_only: false,
	landscape_armor22_workaround: false
};

const tauriSettingsStore = createRemoteStore<Settings>({
	initial: undefined,
	load: async () => {
		try {
			return await invoke('plugin:hillview|cmd', {command: 'get_settings'}) as Settings;
		} catch (err) {
			console.error('Error loading settings:', err);
			return settingsDefaults;
		}
	},
	save: async (val) => {
		try {
			await invoke('plugin:hillview|cmd', {
				command: 'set_settings',
				params: val
			});
		} catch (err) {
			console.error('Error saving settings:', err);
		}
	}
});

const browserSettingsStore = localStorageSharedStore('settings', {
	initialized: true,
	value: settingsDefaults,
	loading: false,
	error: null as unknown
});


export async function getSettings(): Promise<Settings> {
	if (BROWSER) {
		const current = get(browserSettingsStore);
		return current.value;
	} else if (TAURI) {
		// settings load asynchronously, so we need to wait for it to be ready
		let current;
		while (true) {
			current = get(tauriSettingsStore);
			if (current?.value) {
				break;
			}
			console.log('Waiting for settings to load...');
			await new Promise(resolve => setTimeout(resolve, 10));
		}
		return current.value;
	}
	// Fallback to defaults if something goes wrong
	return settingsDefaults;
}


export async function updateSettings(newSettings: Partial<Settings>): Promise<void> {
	if (BROWSER) {
		const current = get(browserSettingsStore);
		const updated = {...current.value, ...newSettings};
		browserSettingsStore.set({...current, value: updated});
		// Also persist to IndexedDB so the upload loop (which reads from IDB) sees the change
		await writeSettings(updated);
	} else if (TAURI) {
		// Wait for the initial load before merging — otherwise `state.value` may still be
		// undefined and the partial update collapses to just `newSettings`, stomping on
		// fields the caller didn't intend to change.
		const currentValue = await getSettings();
		const updated = {...currentValue, ...newSettings};
		await tauriSettingsStore.persist(updated);
	}
}

export const settings = TAURI ? tauriSettingsStore : browserSettingsStore;

// On page load in BROWSER mode, mirror localStorage → IndexedDB so the upload
// loop (service worker / uploadManager.ts, which reads only from IDB) sees the
// user's current settings even if they haven't touched the settings UI this
// session. Without this, IDB can drift stale and auto_upload_enabled reads as
// undefined, causing the upload loop to break early.
if (BROWSER) {
	writeSettings(get(browserSettingsStore).value).catch(err => {
		console.error('Failed to sync settings to IndexedDB on load:', err);
	});
}

