import config from './playwright.config';
import { T } from './helpers/timeouts';

/** Run against a dev server without the general suite's database reset. */
export default {
	...config,
	testMatch: 'panoramax-contribution.spec.ts',
	globalSetup: './helpers/lockOnlySetup.ts',
	globalTeardown: './helpers/globalTeardown.ts',
	webServer: undefined,
	reporter: 'list' as const,
	expect: { timeout: T(10_000) },
	use: { ...config.use, baseURL: process.env.FRONTEND_URL || 'http://localhost:8212' }
};
