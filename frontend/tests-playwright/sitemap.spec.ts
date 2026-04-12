import { test, expect } from './fixtures';

test.describe('Sitemap', () => {
	test('sitemap.xml is well-formed XML', async ({ page }) => {
		const response = await page.request.get('/sitemap.xml');
		expect(response.ok()).toBe(true);
		expect(response.headers()['content-type']).toContain('application/xml');

		const body = await response.text();

		// Parse as XML in the browser — DOMParser rejects malformed XML (e.g. bare &)
		const parseError = await page.evaluate((xml) => {
			const doc = new DOMParser().parseFromString(xml, 'application/xml');
			const err = doc.querySelector('parsererror');
			return err ? err.textContent : null;
		}, body);

		expect(parseError, `Sitemap is not well-formed XML:\n${parseError}`).toBeNull();
	});

	test('sitemap.xml contains expected structure', async ({ page }) => {
		const response = await page.request.get('/sitemap.xml');
		const body = await response.text();

		// Must have XML declaration and urlset root
		expect(body).toContain('<?xml version="1.0"');
		expect(body).toContain('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"');

		// Must contain at least the static paths
		expect(body).toContain('/about');
		expect(body).toContain('/contact');

		// Must not contain unescaped & in URLs (& must always be &amp; inside XML)
		const locMatches = body.matchAll(/<loc>(.*?)<\/loc>/g);
		for (const match of locMatches) {
			const locContent = match[1];
			// After XML parsing, &amp; becomes &, but in raw XML text bare & is invalid.
			// Check that no bare & exists (& not followed by amp; or lt; or gt; or quot; or apos; or #)
			const bareAmpersand = /&(?!amp;|lt;|gt;|quot;|apos;|#)/;
			expect(
				bareAmpersand.test(locContent),
				`Found unescaped & in <loc>: ${locContent}`
			).toBe(false);
		}
	});
});
