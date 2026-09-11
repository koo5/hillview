/**
 * The SSR ticket cookie's name, on its own so the server hook can import it
 * without pulling the browser-side writer — and, through it, $lib/tauri — into
 * the server bundle. Read by hooks.server.ts, written by ssrTicketCookie.ts.
 */
export const SSR_TICKET_COOKIE = 'hv_ssr';
