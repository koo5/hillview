import * as Sentry from "@sentry/sveltekit";
import {handleErrorWithSentry, replayIntegration} from "@sentry/sveltekit";
import {sequence} from "@sveltejs/kit/hooks";

const sentryEnabled = /^(true|1|yes|on)$/i.test((process.env.VITE_SENTRY_ENABLED || '').trim());

if (sentryEnabled)
{

Sentry.init({
    dsn: 'https://0cd95912362bc25ef123532e78c3d594@o4509657094881280.ingest.de.sentry.io/4509657109692496',

    _experiments: {enableLogs: true},

    tracesSampleRate: 1.0,

    // This sets the sample rate to be 10%. You may want this to be 100% while
    // in development and sample at a lower rate in production
    replaysSessionSampleRate: 1,

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
// If you have a custom error handler, pass it to `handleErrorWithSentry`
export const handleError = sentryEnabled
	? handleErrorWithSentry()
	: ({ error }) => {
			console.error('Unhandled error:', error);
		};

//export const handle = sentryEnabled ? sequence(sentryHandle()) : sequence();

export const init = () => {console.log('🢄client initialized');};
