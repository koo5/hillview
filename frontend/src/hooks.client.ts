/*
import * as Sentry from "@sentry/sveltekit";
import {handleErrorWithSentry, replayIntegration} from "@sentry/sveltekit";
 */

import {invoke} from "@tauri-apps/api/core";
import {backendUrl} from "$lib/config";
import {TAURI} from "$lib/tauri";
import {getCurrent} from "@tauri-apps/plugin-deep-link";
import {navigateWithHistory} from "$lib/navigation.svelte";



function handleException(event: any)
{
	console.warn('UNCAUGHT ERROR:', event);
	console.error(JSON.stringify(event, null, 2));
	console.error('Stack trace:\n', event.error?.stack);
}

window?.addEventListener('unhandledrejection', handleException);
window?.addEventListener('error', handleException);


/*const sentryEnabled = /^(true|1|yes|on)$/i.test((import.meta.env.VITE_SENTRY_ENABLED || '').trim());
console.log('🢄Sentry enabled:', sentryEnabled);
if (sentryEnabled)
{
	console.log('🢄Initializing Sentry');
	Sentry.init({
		dsn: import.meta.env.VITE_SENTRY_DSN || 'https://0cd95912362bc25ef123532e78c3d594@o4509657094881280.ingest.de.sentry.io/4509657109692496',

		_experiments: {enableLogs: true},

		tracesSampleRate: 1.0,

		// This sets the sample rate to be 10%. You may want this to be 100% while
		// in development and sample at a lower rate in production
		replaysSessionSampleRate: 0,

		// If the entire session is not sampled, use the below sample rate to sample
		// sessions when an error occurs.
		replaysOnErrorSampleRate: 1,

		// If you don't want to use Session Replay, just remove the line below:
		integrations: [
			replayIntegration(),
			Sentry.consoleLoggingIntegration({}),
			Sentry.feedbackIntegration({
				// Additional SDK configuration goes in here, for example:
				colorScheme: "system",
				triggerLabel: "Bug",
			}),
		],
	});
}
*/
export async function handleError(eee: any): Promise<{ message: string }> {
	console.error('🢄handleError:', eee.error);
	/*if (sentryEnabled) {
		return await handleErrorWithSentry(eee);
	} else
	*/
	return { message: eee.message || 'An error occurred' };

}


export const init = () => {
	if (TAURI)
	{
		invoke('plugin:hillview|set_upload_config', { config: {server_url: backendUrl }});
	}
	console.log('🢄client initialized');
};
