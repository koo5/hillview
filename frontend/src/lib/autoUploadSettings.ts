import {createRemoteStore} from './remoteStore';
import {invoke} from "@tauri-apps/api/core";

export interface AutoUploadSettings {
	auto_upload_enabled: boolean;
	auto_upload_prompt_enabled: boolean;
	wifi_only: boolean;
};

export const autoUploadSettingsDefaults: AutoUploadSettings = {
	auto_upload_enabled: false,
	auto_upload_prompt_enabled: true,
	wifi_only: true
};

export const autoUploadSettings = createRemoteStore<AutoUploadSettings>({
	initial: undefined,
	load: async () => {
		try {
			return await invoke('plugin:hillview|get_upload_status') as {
				auto_upload_enabled: boolean;
				auto_upload_prompt_enabled: boolean;
				wifi_only: boolean;
			};
		} catch (err) {
			console.error('Error loading auto upload settings:', err);
			return autoUploadSettingsDefaults;
		}
	},
	save: async (val) => {
		try {
			await invoke('plugin:hillview|set_auto_upload_enabled', {
				enabled: val.auto_upload_enabled,
				prompt_enabled: val.auto_upload_prompt_enabled,
				wifi_only: val.wifi_only
			});
		} catch (err) {
			console.error('Error saving auto upload settings:', err);
		}
	}
});

