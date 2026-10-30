/**
 * The origin a Playwright run targets, and how Chromium has to be launched to
 * reach it. Shared by playwright.config.ts and playwright.screenshots.config.ts
 * so the two suites cannot drift apart on either.
 */
import dns from 'node:dns';
import { isIP } from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Which origin the suite targets, from `scripts/set_host.py`'s managed block in
 * the repo-root .env — so switching host profiles (raw <-> the Caddy h2 origin)
 * needs no shell exports here. An explicit env var still wins, and an absent
 * declaration leaves this undefined, which is what makes `webServer` below
 * spawn the local dev server.
 *
 * Deliberately a 5-line reader rather than a dotenv dependency: one key, and
 * tests-playwright is its own package whose tree we keep small.
 */
export function resolveFrontendUrl(): string | undefined {
  if (process.env.FRONTEND_URL) return process.env.FRONTEND_URL;
  let text: string;
  try {
    text = fs.readFileSync(path.resolve(__dirname, '../../../.env'), 'utf8');
  } catch {
    return undefined;
  }
  // Last active declaration wins, matching dotenv and compose interpolation.
  let value: string | undefined;
  for (const line of text.split('\n')) {
    const match = /^\s*FRONTEND_URL=(.*)$/.exec(line);
    if (match) value = match[1].trim().replace(/^["']|["']$/g, '');
  }
  return value || undefined;
}

/**
 * Chromium-only `--host-resolver-rules` pinning the target host to the address
 * the OS resolves it to (getaddrinfo — /etc/hosts included, same as Firefox and
 * WebKit see).
 *
 * Why: Chromium's own resolver probes for a global IPv6 route and, finding none,
 * stops returning AAAA answers. An IPv6-only name — the Yggdrasil origins
 * (`*-ygg` profiles in hosts.toml, whose names resolve into 200::/7)
 * — then fails every goto with net::ERR_NAME_NOT_RESOLVED in chromium while
 * firefox and webkit pass. Mapping to an address literal skips that probe.
 */
export async function chromiumHostResolverArgs(url: string | undefined): Promise<string[]> {
  if (!url) return [];
  const host = new URL(url).hostname;
  if (isIP(host) || host === 'localhost') return [];
  try {
    const { address, family } = await dns.promises.lookup(host);
    const literal = family === 6 ? `[${address}]` : address;
    return [`--host-resolver-rules=MAP ${host} ${literal}`];
  } catch {
    // Unresolvable here too — let chromium report it like the other browsers.
    return [];
  }
}
