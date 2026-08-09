import { apiBase } from './config';

// Minimal fetch wrapper for the workbench API. No auth (loopback-only M0/M1);
// modeled on frontend/src/lib/http.ts but without its Tauri-tainted deps.

export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
	const res = await fetch(apiBase + path, {
		method,
		headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
		body: body !== undefined ? JSON.stringify(body) : undefined
	});
	if (!res.ok) {
		let detail = res.statusText;
		try {
			const j = await res.json();
			detail = j.detail ?? detail;
		} catch {
			/* ignore */
		}
		throw new ApiError(res.status, detail);
	}
	if (res.status === 204) return undefined as T;
	return res.json() as Promise<T>;
}

export const api = {
	get: <T>(path: string) => request<T>('GET', path),
	post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
	put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
	del: <T>(path: string) => request<T>('DELETE', path)
};
