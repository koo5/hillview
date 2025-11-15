
import { createRemoteStore } from './remoteStore';
import {invoke} from "@tauri-apps/api/core";

interface AutoUploadSettings {
	autoUploadEnabled: boolean;
	autoUploadPromptEnabled: boolean;
};

export const autoUploadSettings = createRemoteStore<AutoUploadSettings>({
	initial: undefined,
	load: async () => {
		return await invoke('plugin:hillview|get_upload_status') as {
			autoUploadEnabled: boolean;
			autoUploadPromptEnabled: boolean;
		};
	},
	save: async (val) => {
		await invoke('plugin:hillview|set_auto_upload_enabled', {
			enabled: val.autoUploadEnabled,
			promptEnabled: val.autoUploadPromptEnabled
		});

	}
});

