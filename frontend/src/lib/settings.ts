import {createRemoteStore} from './remoteStore';
import {invoke} from "@tauri-apps/api/core";
import {BROWSER, TAURI} from "$lib/tauri";
import {localStorageSharedStore} from "$lib/svelte-shared-store";
import {get} from "svelte/store";

export interface Settings {
	auto_upload_enabled: boolean;
	auto_upload_prompt_enabled: boolean;
	wifi_only: boolean;
};

export const settingsDefaults: Settings = {
	auto_upload_enabled: false,
	auto_upload_prompt_enabled: true,
	wifi_only: true
};

const tauriSettingsStore = 	createRemoteStore<Settings>({
		initial: undefined,
		load: async () => {
			try {
				return await invoke('plugin:hillview|cmd', {command: 'get_settings'}) as {
					auto_upload_enabled: boolean;
					auto_upload_prompt_enabled: boolean;
					wifi_only: boolean;
				};
			} catch (err) {
				console.error('Error loading auto upload settings:', err);
				return settingsDefaults;
			}
		},
		save: async (val) => {
			try {
				await invoke('plugin:hillview|cmd', {
					command: 'set_settings',
					params: {
						enabled: val.auto_upload_enabled,
						prompt_enabled: val.auto_upload_prompt_enabled,
						wifi_only: val.wifi_only
					}
				});
			} catch (err) {
				console.error('Error saving auto upload settings:', err);
			}
		}
	});

const browserSettingsStore = localStorageSharedStore('settings', {initialized: true, value: settingsDefaults});


export async function updateSettings(newSettings: Partial<Settings>): Promise<void> {
	if (BROWSER)
	{
		browserSettingsStore.update((current) => {
			const updated = {...current.value, ...newSettings};
			await writeSettingsToIndexedDB(updated);
			return {initialized: true, value: updated};
		});
	}
	else if (TAURI)
	{
		const current = get(tauriSettingsStore);
		const updated = {...current?.value, ...newSettings} as Settings;
		await tauriSettingsStore.persist(updated);
	}
}

export const settings = TAURI ? tauriSettingsStore : browserSettingsStore;

