import { chromium } from 'playwright';

const url = process.argv[2] || 'https://hillview.cz/bestof';
const block = process.argv[3] !== 'noblock';

const browser = await chromium.launch();
const page = await browser.newPage();

const blocked = [];
if (block) {
	// Googlebot's renderer refuses subresources disallowed by robots.txt
	await page.route('**/api/**', (route) => {
		blocked.push(route.request().url());
		return route.abort();
	});
}

const consoleLines = [];
page.on('console', (m) => consoleLines.push(`[${m.type()}] ${m.text().slice(0, 200)}`));

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(4000);

const text = (await page.locator('body').innerText()).replace(/\s+/g, ' ').trim();
console.log('URL          :', url);
console.log('API blocked  :', block, `(${blocked.length} requests aborted)`);
blocked.slice(0, 5).forEach((u) => console.log('   aborted  :', u));
console.log('photo cards  :', await page.locator('[data-testid="bestof-photo-card"]').count());
console.log('summaries    :', await page.locator('[data-testid="bestof-annotation-summary"]').count());
console.log('/photo/ links:', await page.locator('a[href^="/photo/"]').count());
console.log('has "Error loading":', text.includes('Error loading'));
console.log('has "No photos yet":', text.includes('No photos yet'));
console.log('has "Loading best" :', text.includes('Loading best'));
console.log('--- rendered text ---');
console.log(text.slice(0, 500));
console.log('--- console ---');
consoleLines.slice(0, 15).forEach((l) => console.log(l));

await browser.close();
