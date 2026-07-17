<script lang="ts">
	import { page } from '$app/stores';
	import { MessageSquare, Lock, User as UserIcon, RotateCcw, Crosshair, ShieldAlert, ArrowLeft } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { isAdmin, isModerator } from '$lib/adminNotifications';
	import { parsePhotoUidParts } from '$lib/urlUtils';
	import {
		type AnnotationEvent,
		prevLabel,
		modAction,
		isOrdinary,
		bodyPreview,
		undoLabel,
		groupIntoChains,
		chainTip,
		chainZoomLink,
	} from '$lib/annotationEvents';

	$: uid = $page.params.uid;
	// Annotations hang off the raw photo id; the route is keyed by uid (source-id).
	$: photoId = uid ? parsePhotoUidParts(uid)?.id ?? null : null;

	let events: AnnotationEvent[] = [];
	let chains: AnnotationEvent[][] = [];
	let loading = false;
	let error = '';
	let truncated = false;

	// Load once the profile confirms moderator (isModerator may be false while the
	// profile is still resolving), and again whenever the photo id changes.
	let loadedFor = '';
	$: if ($isModerator && photoId && loadedFor !== photoId) {
		loadedFor = photoId;
		loadEvents();
	}

	const PAGE_LIMIT = 200;

	async function loadEvents() {
		if (!photoId) return;
		loading = true;
		error = '';
		try {
			const res = await http.get(
				`/admin/annotation-events?photo_id=${encodeURIComponent(photoId)}&limit=${PAGE_LIMIT}`
			);
			if (!res.ok) {
				error = `Failed to load history (${res.status})`;
				return;
			}
			const data = await res.json();
			events = data.events ?? [];
			truncated = events.length >= PAGE_LIMIT;
			chains = groupIntoChains(events);
		} catch (e) {
			error = 'Network error loading history.';
		} finally {
			loading = false;
		}
	}

	// A chain is "live" if its current tip isn't a delete tombstone.
	function isLive(chain: AnnotationEvent[]): boolean {
		return chainTip(chain).event_type !== 'deleted';
	}

	// --- Undo (moderator action; only the current tip of a chain is undoable) ---
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
			loadedFor = ''; // force a reload of the (now-changed) chain
			await loadEvents();
		} catch (e) {
			error = 'Network error performing undo.';
		} finally {
			undoBusy = false;
		}
	}
</script>

<StandardHeaderWithAlert title="Annotation history" showMenuButton={true} fallbackHref={uid ? `/photo/${uid}` : '/'} />

<StandardBody>
	<div class="history" data-testid="photo-annotation-history-page">
		<ProfileGate>
			{#if $isModerator}
				<a class="back" href={uid ? `/photo/${uid}` : '/'} data-testid="photo-annotation-history-back">
					<ArrowLeft size={14} /> Back to photo
				</a>

				<p class="intro">
					Every annotation on this photo, grouped by its edit chain — newest activity first.
					History is append-only; only the current version of a chain can be undone.
				</p>

				{#if error}
					<div class="error" data-testid="photo-annotation-history-error">{error}</div>
				{/if}

				{#if loading && chains.length === 0}
					<div class="empty">Loading…</div>
				{:else if chains.length === 0}
					<div class="empty" data-testid="photo-annotation-history-empty">
						<MessageSquare size={24} />
						<p>No annotations on this photo yet.</p>
					</div>
				{:else}
					{#if truncated}
						<div class="truncated">Showing the most recent {PAGE_LIMIT} events; older ones are omitted.</div>
					{/if}
					<ul class="chains">
						{#each chains as chain (chainTip(chain).id)}
							{@const tip = chainTip(chain)}
							{@const zoom = chainZoomLink(chain)}
							<li class="chain" data-testid="photo-annotation-history-chain" data-live={isLive(chain)}>
								<div class="chain-head">
									<span
										class="status"
										class:live={isLive(chain)}
										data-testid="photo-annotation-history-status"
									>{isLive(chain) ? 'Current' : 'Removed'}</span>
									{#if zoom}
										<a class="zoom-link" href={zoom} data-testid="photo-annotation-history-zoom" title="Open the photo zoomed to this annotation"><Crosshair size={12} /> zoom to spot</a>
									{/if}
									<button
										class="undo-btn"
										data-testid="photo-annotation-history-undo"
										title={undoLabel(tip)}
										on:click={() => openUndo(tip)}
									><RotateCcw size={13} /> {undoLabel(tip)}</button>
								</div>

								<!-- Newest first within a chain (current tip on top), matching the
								     newest-first order of the chains themselves. -->
								<ol class="timeline">
									{#each chain.slice().reverse() as ev (ev.id)}
										<li
											class="event"
											class:is-tip={ev.id === tip.id}
											data-testid="photo-annotation-history-event"
											data-event-type={ev.event_type}
											data-event-id={ev.id}
											data-actor-role={ev.actor_role}
										>
											<span class="type type-{ev.event_type}" data-testid="photo-annotation-history-type">{ev.event_type}</span>
											<div class="event-main">
												<div class="event-meta">
													<span class="user" class:ordinary={isOrdinary(ev)} data-testid="photo-annotation-history-user"><UserIcon size={12} /> {ev.username ?? ev.user_id}</span>
													<span class="dot">·</span>
													<span>{formatUtcDateTime(ev.created_at)}</span>
												</div>
												<div class="event-body">{bodyPreview(ev)}</div>
												{#if ev.prev_body != null && ev.prev_body !== ''}
													<div class="prev-body" data-testid="photo-annotation-history-prev-body">{prevLabel(ev)}: <span class="prev-text">{ev.prev_body}</span></div>
												{/if}
												{#if ev.moderation}
													<div class="mod-note" data-testid="photo-annotation-history-moderation" title="Moderator action">
														<ShieldAlert size={12} /> moderator {modAction(ev.moderation)}{ev.moderation.reason ? ` — "${ev.moderation.reason}"` : ' (no reason given)'}
													</div>
												{/if}
											</div>
										</li>
									{/each}
								</ol>
							</li>
						{/each}
					</ul>
				{/if}
			{:else}
				<div class="forbidden" data-testid="photo-annotation-history-forbidden">
					<Lock size={28} />
					<h2>Not authorized</h2>
					<p>Annotation history is for moderators and administrators.</p>
					<a class="home-link" href={uid ? `/photo/${uid}` : '/'}>Back to photo</a>
				</div>
			{/if}
		</ProfileGate>
	</div>
</StandardBody>

{#if undoTarget}
	<div class="undo-overlay" data-testid="photo-annotation-history-undo-dialog">
		<div class="undo-modal">
			<h3>{undoLabel(undoTarget)}?</h3>
			<p class="undo-note">
				This appends a reversing event (history is preserved) and notifies the author.
				A reason is optional and shown to them.
			</p>
			<textarea
				class="undo-reason"
				data-testid="photo-annotation-history-undo-reason"
				bind:value={undoReason}
				rows="3"
				placeholder="Reason (optional) — shown to the author"
				disabled={undoBusy}
			></textarea>
			<div class="undo-actions">
				<button class="btn-cancel" data-testid="photo-annotation-history-undo-cancel" on:click={closeUndo} disabled={undoBusy}>Cancel</button>
				<button class="btn-undo" data-testid="photo-annotation-history-undo-confirm" on:click={confirmUndo} disabled={undoBusy}>
					{undoBusy ? 'Undoing…' : 'Undo'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.history {
		max-width: 720px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.back {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		color: #4f46e5;
		text-decoration: none;
		font-size: 0.85rem;
		font-weight: 600;
		margin: 8px 0;
	}

	.back:hover {
		text-decoration: underline;
	}

	.intro {
		color: #6b7280;
		font-size: 0.9rem;
		margin: 4px 0 16px 0;
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

	.truncated {
		color: #92400e;
		background: #fffbeb;
		border: 1px solid #fde68a;
		padding: 8px 12px;
		border-radius: 8px;
		font-size: 0.8rem;
		margin-bottom: 12px;
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

	.chains {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.chain {
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 14px 16px;
	}

	.chain[data-live='false'] {
		background: #fafafa;
		border-style: dashed;
	}

	.chain-head {
		display: flex;
		align-items: center;
		gap: 12px;
		margin-bottom: 10px;
	}

	.status {
		font-size: 0.68rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 3px 10px;
		border-radius: 999px;
		color: #6b7280;
		background: #f3f4f6;
	}

	.status.live {
		color: #15803d;
		background: #dcfce7;
	}

	.zoom-link {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
		font-size: 0.78rem;
	}

	.zoom-link:hover {
		text-decoration: underline;
	}

	.undo-btn {
		margin-left: auto;
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

	.timeline {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
		border-left: 2px solid #e5e7eb;
		padding-left: 14px;
	}

	.event {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		position: relative;
	}

	/* Emphasize the current version — the tip of the chain. */
	.event.is-tip .event-body {
		font-weight: 500;
	}

	.type {
		flex: 0 0 auto;
		margin-top: 1px;
		font-size: 0.66rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 2px 8px;
		border-radius: 999px;
		min-width: 58px;
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

	.event-body {
		margin-top: 4px;
		color: #374151;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.prev-body {
		margin-top: 4px;
		font-size: 0.8rem;
		color: #9ca3af;
	}

	.prev-body .prev-text {
		color: #6b7280;
		text-decoration: line-through;
	}

	.mod-note {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		margin-top: 6px;
		font-size: 0.8rem;
		color: #b45309;
		background: #fef3c7;
		padding: 3px 10px;
		border-radius: 8px;
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
