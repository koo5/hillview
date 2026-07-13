<script lang="ts">
	import { MessageSquare, Lock, User as UserIcon, RotateCcw, Crosshair } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { isAdmin, isModerator } from '$lib/adminNotifications';

	interface AnnotationEvent {
		id: string;
		photo_id: string;
		user_id: string;
		username: string | null;
		actor_role: string | null;
		event_type: 'created' | 'updated' | 'deleted' | string;
		body: string | null;
		target: unknown;
		is_current: boolean;
		superseded_by: string | null;
		created_at: string;
		photo_lat: number | null;
		photo_lon: number | null;
		photo_bearing: number | null;
		photo_width: number | null;
	}

	// Events by ordinary users (anyone who isn't an admin or moderator) are the
	// ones worth an admin's attention, so their username is highlighted.
	function isOrdinary(ev: AnnotationEvent): boolean {
		return !['admin', 'moderator'].includes((ev.actor_role ?? '').toLowerCase());
	}

	// Annotations live on hillview photos, so the detail page is /photo/hillview-{id}.
	function photoUrl(ev: AnnotationEvent): string {
		return `/photo/hillview-${ev.photo_id}`;
	}

	// Pixel-space bbox of the annotation target. Handles both the Annotorious v3
	// RECTANGLE selector (geometry.bounds in image pixels — what the app writes)
	// and the older FragmentSelector `xywh=pixel:` form.
	function targetXywh(ev: AnnotationEvent): { x: number; y: number; w: number; h: number } | null {
		const sel = (ev.target as any)?.selector ?? ev.target;
		if (!sel) return null;

		const b = sel.geometry?.bounds;
		if (b && [b.minX, b.minY, b.maxX, b.maxY].every((n: unknown) => typeof n === 'number')) {
			return { x: b.minX, y: b.minY, w: b.maxX - b.minX, h: b.maxY - b.minY };
		}

		const value = typeof sel === 'string' ? sel : sel?.value;
		if (typeof value === 'string') {
			const m = value.match(/xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/);
			if (m) {
				const [, x, y, w, h] = m.map(Number);
				return { x, y, w, h };
			}
		}
		return null;
	}

	// A zoomview "share link": the map URL opens the photo zoomed to the annotation.
	// OSD viewport bounds normalize BOTH axes by the image width, so px/width.
	function zoomLink(ev: AnnotationEvent): string | null {
		const xy = targetXywh(ev);
		if (!xy || !ev.photo_width || ev.photo_lat == null || ev.photo_lon == null) return null;
		const W = ev.photo_width;
		const b = { x1: xy.x / W, y1: xy.y / W, x2: (xy.x + xy.w) / W, y2: (xy.y + xy.h) / W };
		const p = new URLSearchParams({
			lat: String(ev.photo_lat),
			lon: String(ev.photo_lon),
			zoom: '20',
			photo: `hillview-${ev.photo_id}`,
			x1: b.x1.toFixed(6),
			y1: b.y1.toFixed(6),
			x2: b.x2.toFixed(6),
			y2: b.y2.toFixed(6),
		});
		if (ev.photo_bearing != null) p.set('bearing', String(ev.photo_bearing));
		return `/?${p.toString()}`;
	}

	const FILTERS = ['all', 'created', 'updated', 'deleted'] as const;
	type Filter = (typeof FILTERS)[number];

	let events: AnnotationEvent[] = [];
	let loading = false;
	let error = '';
	let filter: Filter = 'all';

	// Load once the profile confirms admin (isAdmin may be false while the profile
	// is still loading), and again whenever the filter changes.
	let loadedOnce = false;
	$: if ($isModerator && !loadedOnce) {
		loadedOnce = true;
		loadEvents();
	}

	async function loadEvents() {
		loading = true;
		error = '';
		try {
			const qs = filter === 'all' ? '?limit=100' : `?event_type=${filter}&limit=100`;
			const res = await http.get('/admin/annotation-events' + qs);
			if (!res.ok) {
				error = `Failed to load events (${res.status})`;
				return;
			}
			const data = await res.json();
			events = data.events ?? [];
		} catch (e) {
			error = 'Network error loading events.';
		} finally {
			loading = false;
		}
	}

	function setFilter(f: Filter) {
		if (filter === f) return;
		filter = f;
		loadEvents();
	}

	// A tombstone (deleted) carries no body; created/updated show a short preview.
	function bodyPreview(ev: AnnotationEvent): string {
		if (ev.event_type === 'deleted') return '(annotation removed)';
		const b = (ev.body ?? '').trim();
		return b === '' ? '(empty)' : b;
	}

	// Undo — only the current tip of a chain can be reverted (backend enforces it too).
	let undoTarget: AnnotationEvent | null = null;
	let undoReason = '';
	let undoBusy = false;

	function openUndo(ev: AnnotationEvent) {
		undoTarget = ev;
		undoReason = '';
	}

	function closeUndo() {
		if (undoBusy) return;
		undoTarget = null;
	}

	async function confirmUndo() {
		if (!undoTarget) return;
		undoBusy = true;
		error = '';
		try {
			const res = await http.post(`/admin/annotation-events/${undoTarget.id}/undo`, {
				reason: undoReason.trim() || null,
			});
			if (!res.ok) {
				error = `Undo failed (${res.status})`;
				return;
			}
			undoTarget = null;
			await loadEvents();
		} catch (e) {
			error = 'Network error performing undo.';
		} finally {
			undoBusy = false;
		}
	}

	// What the undo of this event will do, for the button/dialog wording.
	function undoLabel(ev: AnnotationEvent): string {
		if (ev.event_type === 'created') return 'Remove this annotation';
		if (ev.event_type === 'deleted') return 'Restore this annotation';
		return 'Revert this edit';
	}
</script>

<StandardHeaderWithAlert title="Annotation activity" showMenuButton={true} fallbackHref={$isAdmin ? '/admin' : '/moderate'} />

<StandardBody>
	<div class="admin-annotations" data-testid="admin-annotations-page">
		<ProfileGate>
			{#if $isModerator}
				<p class="intro">
					Every create, edit, and delete, newest first. History is append-only —
					rollback controls are coming in a later update.
				</p>

				<div class="toolbar">
					<div class="filters">
						{#each FILTERS as f}
							<button
								class="filter"
								class:active={filter === f}
								data-testid={`admin-annotations-filter-${f}`}
								on:click={() => setFilter(f)}
							>{f === 'all' ? 'All' : f}</button>
						{/each}
					</div>
				</div>

				{#if error}
					<div class="error" data-testid="admin-annotations-error">{error}</div>
				{/if}

				{#if loading && events.length === 0}
					<div class="empty">Loading…</div>
				{:else if events.length === 0}
					<div class="empty" data-testid="admin-annotations-empty">
						<MessageSquare size={24} />
						<p>No annotation activity{filter === 'all' ? ' yet' : ` of type "${filter}"`}.</p>
					</div>
				{:else}
					<ul class="event-list">
						{#each events as ev (ev.id)}
							<li
								class="event"
								data-testid="admin-annotation-event"
								data-event-type={ev.event_type}
								data-event-id={ev.id}
								data-actor-role={ev.actor_role}
							>
								<span class="type type-{ev.event_type}" data-testid="admin-annotation-type">{ev.event_type}</span>
								<div class="event-main">
									<div class="event-meta">
										<span
											class="user"
											class:ordinary={isOrdinary(ev)}
											data-testid="admin-annotation-user"
										><UserIcon size={12} /> {ev.username ?? ev.user_id}</span>
										<span class="dot">·</span>
										<span>{formatUtcDateTime(ev.created_at)}</span>
										<span class="dot">·</span>
										<a class="photo" href={photoUrl(ev)} data-testid="admin-annotation-photo-link" title={`Open photo ${ev.photo_id}`}>photo {ev.photo_id.slice(0, 8)}…</a>
										{#if zoomLink(ev)}
											<a class="zoom-link" href={zoomLink(ev)} data-testid="admin-annotation-zoom-link" title="Open the photo zoomed to this annotation"><Crosshair size={12} /> zoom</a>
										{/if}
									</div>
									<div class="event-body">{bodyPreview(ev)}</div>
								</div>
								{#if ev.is_current}
									<button
										class="undo-btn"
										data-testid="admin-annotation-undo"
										title={undoLabel(ev)}
										on:click={() => openUndo(ev)}
									><RotateCcw size={14} /> Undo</button>
								{:else}
									<span class="superseded-tag" data-testid="admin-annotation-superseded" title="A later event replaced this one; only the current version of a chain can be undone">superseded</span>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			{:else}
				<div class="forbidden" data-testid="admin-forbidden">
					<Lock size={28} />
					<h2>Not authorized</h2>
					<p>This area is for administrators.</p>
					<a class="home-link" href="/">Back to map</a>
				</div>
			{/if}
		</ProfileGate>
	</div>
</StandardBody>

{#if undoTarget}
	<div class="undo-overlay" data-testid="admin-undo-dialog">
		<div class="undo-modal">
			<h3>{undoLabel(undoTarget)}?</h3>
			<p class="undo-note">
				This appends a reversing event (history is preserved) and notifies the author.
				A reason is optional and shown to them.
			</p>
			<textarea
				class="undo-reason"
				data-testid="admin-undo-reason"
				bind:value={undoReason}
				rows="3"
				placeholder="Reason (optional) — shown to the author"
				disabled={undoBusy}
			></textarea>
			<div class="undo-actions">
				<button class="btn-cancel" data-testid="admin-undo-cancel" on:click={closeUndo} disabled={undoBusy}>Cancel</button>
				<button class="btn-undo" data-testid="admin-undo-confirm" on:click={confirmUndo} disabled={undoBusy}>
					{undoBusy ? 'Undoing…' : 'Undo'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.admin-annotations {
		max-width: 760px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.intro {
		color: #6b7280;
		font-size: 0.9rem;
		margin: 8px 0 12px 0;
	}

	.toolbar {
		display: flex;
		justify-content: flex-end;
		margin-bottom: 16px;
	}

	.filters {
		display: inline-flex;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		overflow: hidden;
	}

	.filter {
		padding: 6px 14px;
		background: white;
		border: none;
		cursor: pointer;
		font-size: 0.8rem;
		color: #4b5563;
		text-transform: capitalize;
	}

	.filter.active {
		background: #4f46e5;
		color: white;
	}

	.error {
		background: #fef2f2;
		border: 1px solid #fecaca;
		color: #991b1b;
		padding: 10px 14px;
		border-radius: 8px;
		margin-bottom: 16px;
		font-size: 0.875rem;
	}

	.empty {
		text-align: center;
		color: #6b7280;
		padding: 48px 16px;
	}

	.empty :global(svg) {
		color: #9ca3af;
		margin-bottom: 8px;
	}

	.event-list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.event {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 10px;
		padding: 12px 14px;
	}

	.type {
		flex: 0 0 auto;
		margin-top: 2px;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 3px 8px;
		border-radius: 999px;
		min-width: 62px;
		text-align: center;
	}

	.type-created {
		background: #dcfce7;
		color: #15803d;
	}

	.type-updated {
		background: #dbeafe;
		color: #1e40af;
	}

	.type-deleted {
		background: #fee2e2;
		color: #b91c1c;
	}

	.event-main {
		min-width: 0;
		flex: 1;
	}

	.event-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		color: #6b7280;
		font-size: 0.75rem;
	}

	.event-meta .user {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		color: #374151;
		font-weight: 600;
	}

	/* Ordinary (non-admin/moderator) actors get an alert-styled name pill. */
	.event-meta .user.ordinary {
		color: #b45309;
		background: #fef3c7;
		padding: 1px 8px;
		border-radius: 999px;
	}

	.dot {
		color: #d1d5db;
	}

	.photo {
		font-family: monospace;
		color: #4f46e5;
		text-decoration: none;
	}

	.photo:hover {
		text-decoration: underline;
	}

	.zoom-link {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
	}

	.zoom-link:hover {
		text-decoration: underline;
	}

	.superseded-tag {
		flex: 0 0 auto;
		align-self: center;
		font-size: 0.68rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: #9ca3af;
		background: #f3f4f6;
		padding: 3px 8px;
		border-radius: 999px;
	}

	.event-body {
		margin-top: 4px;
		color: #374151;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.undo-btn {
		flex: 0 0 auto;
		align-self: center;
		display: inline-flex;
		align-items: center;
		gap: 5px;
		padding: 5px 10px;
		border: 1px solid #d1d5db;
		background: white;
		border-radius: 8px;
		font-size: 0.78rem;
		color: #374151;
		cursor: pointer;
		transition: background 0.15s ease;
	}

	.undo-btn:hover {
		background: #f3f4f6;
	}

	.undo-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.4);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 130200;
		padding: 16px;
	}

	.undo-modal {
		background: white;
		border-radius: 14px;
		padding: 24px;
		max-width: 440px;
		width: 100%;
		box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
	}

	.undo-modal h3 {
		margin: 0 0 8px 0;
		color: #1f2937;
	}

	.undo-note {
		margin: 0 0 14px 0;
		color: #6b7280;
		font-size: 0.85rem;
	}

	.undo-reason {
		width: 100%;
		box-sizing: border-box;
		padding: 10px 12px;
		border: 1px solid #d1d5db;
		border-radius: 8px;
		font-size: 0.9rem;
		font-family: inherit;
		resize: vertical;
	}

	.undo-actions {
		display: flex;
		justify-content: flex-end;
		gap: 10px;
		margin-top: 16px;
	}

	.btn-cancel,
	.btn-undo {
		padding: 8px 18px;
		border-radius: 8px;
		font-weight: 600;
		cursor: pointer;
		border: 1px solid #d1d5db;
		background: white;
		color: #374151;
	}

	.btn-undo {
		background: #b45309;
		border-color: #b45309;
		color: #fff;
	}

	.btn-undo:disabled,
	.btn-cancel:disabled {
		opacity: 0.6;
		cursor: default;
	}

	.forbidden {
		text-align: center;
		padding: 64px 24px;
		color: #4b5563;
	}

	.forbidden :global(svg) {
		color: #9ca3af;
		margin-bottom: 12px;
	}

	.forbidden h2 {
		margin: 0 0 8px 0;
		color: #1f2937;
	}

	.home-link {
		display: inline-block;
		margin-top: 16px;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
	}

	.home-link:hover {
		text-decoration: underline;
	}
</style>
