import { createRemoteStore } from './remoteStore';
import { invoke } from "@tauri-apps/api/core";

export interface CompassSettings {
	landscape_armor22_workaround: boolean;
}

export const defaultCompassSettings: CompassSettings = {
	landscape_armor22_workaround: false
};

export const compassSettings = createRemoteStore<CompassSettings>({
	initial: undefined,
	load: async () => {
		try {
			const result = await invoke('plugin:hillview|cmd', {
				command: 'get_landscape_compass_armor22_workaround'
			}) as { enabled: boolean };
			return {
				landscape_armor22_workaround: result.enabled
			};
		} catch (e) {
			console.warn('Failed to load compass settings, using defaults:', e);
			return defaultCompassSettings;
		}
	},
	save: async (val) => {
		await invoke('plugin:hillview|cmd', {
			command: 'set_landscape_compass_armor22_workaround',
			params: { enabled: val.landscape_armor22_workaround }
		});
	}
});
