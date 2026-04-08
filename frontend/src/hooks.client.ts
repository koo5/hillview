import * as Sentry from "@sentry/sveltekit";
import {handleErrorWithSentry, replayIntegration} from "@sentry/sveltekit";
import {invoke} from "@tauri-apps/api/core";
import {backendUrl} from "$lib/config";
import {TAURI} from "$lib/tauri";



function handleException(event: any)
{
	// Extract the actual Error from the Event wrapper.
	// unhandledrejection → event.reason, error event → event.error
	const error = event.reason ?? event.error ?? event.message ?? event;
	console.warn('UNCAUGHT ERROR:', error);
	if (error?.stack) {
		console.error('Stack trace:\n', error.stack);
	}
}

window?.addEventListener('unhandledrejection', handleException);
window?.addEventListener('error', handleException);


const sentryEnabled = /^(true|1|yes|on)$/i.test((import.meta.env.VITE_SENTRY_ENABLED || '').trim());
console.log('🢄Sentry enabled:', sentryEnabled);
if (sentryEnabled)
{
	console.log('🢄Initializing Sentry');
	Sentry.init({
		dsn: import.meta.env.VITE_SENTRY_DSN,
		enableLogs: true,
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
				colorScheme: "system",
				triggerLabel: "Bug",
				autoInject: false,
			}),
		],
	});
}

export async function handleError(eee: any): Promise<{ message: string }> {
	console.error('🢄handleError:', eee.error);
	if (sentryEnabled) {
		return await handleErrorWithSentry(eee);
	} else

	return { message: eee.message || 'An error occurred' };

}


export const init = () => {
	if (TAURI)
	{
		invoke('plugin:hillview|cmd', { command: 'set_backend_url', params: { url: backendUrl }});
	}
	console.log('🢄client initialized');
};
