
import { createRemoteStore } from './remoteStore';
import {invoke} from "@tauri-apps/api/core";

interface AutoUploadSettings {
	auto_upload_enabled: boolean;
	auto_upload_prompt_enabled: boolean;
};

export const autoUploadSettings = createRemoteStore<AutoUploadSettings>({
	initial: undefined,
	load: async () => {
		return await invoke('plugin:hillview|get_upload_status') as {
			auto_upload_enabled: boolean;
			auto_upload_prompt_enabled: boolean;
		};
	},
	save: async (val) => {
		await invoke('plugin:hillview|set_auto_upload_enabled', {
			enabled: val.auto_upload_enabled,
			prompt_enabled: val.auto_upload_prompt_enabled
		});

	}
});

