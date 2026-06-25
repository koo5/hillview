<script lang="ts">
	import { fly } from 'svelte/transition';
	import { Maximize2, Minimize2, ChevronUp, ChevronDown } from 'lucide-svelte';
	import {
		timelineActive,
		timelineLoading,
		timelinePhotos,
		timelineCursor,
		timelineUsers,
		timelineHasMore,
		timelineWide,
		jumpToIndex,
		stepTimeline,
		stopTimeline,
		toggleTimelineWide,
		addTimelineUser,
		removeTimelineUser,
	} from '$lib/timeline';
	import { http } from '$lib/http';

	$: photos = $timelinePhotos;
	$: cursor = $timelineCursor;

	// Back/forward enablement: a step is possible if there's a loaded neighbour or
	// the server said there's an unloaded chunk in that direction (stepTimeline pulls it).
	$: canOlder = photos.length > 0 && (cursor > 0 || $timelineHasMore.before);
	$: canNewer = photos.length > 0 && (cursor < photos.length - 1 || $timelineHasMore.after);

	let listEl: HTMLDivElement | undefined;

	// Keep the current row scrolled into view as the cursor moves.
	$: if (listEl && $timelineActive) {
		const el = listEl.querySelector(`[data-tl-index="${cursor}"]`);
		if (el) (el as HTMLElement).scrollIntoView({ block: 'nearest' });
	}

	function fmtWhen(ts: unknown): string {
		if (ts === undefined || ts === null) return '';
		const d = new Date(ts as any);
		return isNaN(d.getTime()) ? String(ts) : d.toLocaleString();
	}

	function thumbUrl(p: any): string | null {
		// `url` is the index's thumb_url (set by indexToPhoto).
		return p?.url || null;
	}

	// Add-user picker state.
	let showPicker = false;
	let pickerQuery = '';
	let pickerLoading = false;
	let allUsers: { id: string; username: string; photo_count: number }[] = [];

	$: trackedIds = new Set($timelineUsers.map((u) => u.id));
	$: candidates = allUsers
		.filter(
			(u) =>
				u.username &&
				!trackedIds.has(u.id) &&
				u.username.toLowerCase().includes(pickerQuery.trim().toLowerCase()),
		)
		.slice(0, 20);

	async function openPicker() {
		timelineWide.set(true); // the search UI needs room
		showPicker = true;
		if (allUsers.length === 0) {
			pickerLoading = true;
			try {
				const res = await http.get('/users/');
				if (res.ok) allUsers = await res.json();
			} catch (e) {
				console.error('Timeline: failed to load users', e);
			} finally {
				pickerLoading = false;
			}
		}
	}

	function closePicker() {
		showPicker = false;
		pickerQuery = '';
	}

	async function pick(u: { id: string; username: string }) {
		closePicker();
		await addTimelineUser({ id: u.id, username: u.username });
	}
</script>

{#if $timelineActive}
	<aside
		class="timeline-panel"
		class:narrow={!$timelineWide}
		data-testid="timeline-panel"
		transition:fly={{ x: 320, duration: 100 }}
	>
		<header class="tl-header">
			<span class="tl-title">Timeline</span>
			<div class="tl-header-actions">
				<button
					class="tl-icon-btn"
					on:click={toggleTimelineWide}
					data-testid="timeline-width-toggle"
					aria-label={$timelineWide ? 'Narrow panel' : 'Widen panel'}
					title={$timelineWide ? 'Narrow' : 'Wide'}
				>
					{#if $timelineWide}<Minimize2 size={16} />{:else}<Maximize2 size={16} />{/if}
				</button>
				<button class="tl-icon-btn" on:click={stopTimeline} data-testid="timeline-close" aria-label="Close timeline">✕</button>
			</div>
		</header>

		<section class="tl-users" data-testid="timeline-users">
			<div class="tl-section-title">Users</div>
			{#each $timelineUsers as u (u.id)}
				<div class="tl-user" data-testid="timeline-user">
					<span class="tl-user-name">{u.username}</span>
					{#if $timelineUsers.length > 1}
						<button
							class="tl-user-remove"
							on:click={() => removeTimelineUser(u.id)}
							data-testid="timeline-user-remove"
							aria-label={`Remove ${u.username}`}
							title="Remove from timeline"
						>×</button>
					{/if}
				</div>
			{/each}

			<button
				class="tl-add-user"
				on:click={() => (showPicker ? closePicker() : openPicker())}
				data-testid="timeline-add-user"
				title="Add a user to the timeline"
			>{$timelineWide ? '+ add user' : '+'}</button>

			{#if showPicker}
				<div class="tl-picker" data-testid="timeline-user-picker">
					<!-- svelte-ignore a11y-autofocus -->
					<input
						class="tl-picker-input"
						type="text"
						placeholder="Search users…"
						autocomplete="off"
						bind:value={pickerQuery}
						data-testid="timeline-user-search"
						autofocus
					/>
					<div class="tl-picker-list">
						{#if pickerLoading}
							<div class="tl-picker-empty">Loading…</div>
						{:else if candidates.length === 0}
							<div class="tl-picker-empty">No matching users</div>
						{:else}
							{#each candidates as u (u.id)}
								<button
									class="tl-picker-option"
									on:click={() => pick(u)}
									data-testid="timeline-user-option"
								>
									<span class="tl-picker-name">{u.username}</span>
									<span class="tl-picker-count">{u.photo_count}</span>
								</button>
							{/each}
						{/if}
					</div>
				</div>
			{/if}
		</section>

		<div class="tl-nav" data-testid="timeline-nav">
			<button
				class="tl-icon-btn tl-nav-btn"
				on:click={() => stepTimeline('older')}
				disabled={!canOlder}
				data-testid="timeline-prev"
				aria-label="Back to older photo"
				title="Older (,)"
			>
				<ChevronUp size={18} />
			</button>
			<div class="tl-status" data-testid="timeline-status">
				{#if $timelineLoading}
					Loading…
				{:else if photos.length}
					{cursor + 1} / {photos.length}
				{:else}
					No photos
				{/if}
			</div>
			<button
				class="tl-icon-btn tl-nav-btn"
				on:click={() => stepTimeline('newer')}
				disabled={!canNewer}
				data-testid="timeline-next"
				aria-label="Forward to newer photo"
				title="Newer (.)"
			>
				<ChevronDown size={18} />
			</button>
		</div>

		<div class="tl-list" bind:this={listEl} data-testid="timeline-list">
			{#if $timelineHasMore.before}
				<div class="tl-more" data-testid="timeline-more-before">earlier photos not loaded</div>
			{/if}
			{#each photos as p, i (p.uid)}
				<button
					class="tl-row"
					class:active={i === cursor}
					data-tl-index={i}
					data-testid="timeline-row"
					on:click={() => jumpToIndex(i)}
				>
					{#if thumbUrl(p)}
						<img class="tl-thumb" src={thumbUrl(p)} alt="" loading="lazy" />
					{:else}
						<div class="tl-thumb tl-thumb-empty"></div>
					{/if}
					<span class="tl-when">{fmtWhen(p.captured_at)}{#if (p as any).timeIsUpload}<span class="tl-up" title="upload time (no capture time)">↥</span>{/if}</span>
				</button>
			{/each}
			{#if $timelineHasMore.after}
				<div class="tl-more" data-testid="timeline-more-after">later photos not loaded</div>
			{/if}
		</div>
	</aside>
{/if}

<style>
	.timeline-panel {
		position: fixed;
		top: calc(60px + var(--safe-area-inset-top, 0px));
		right: calc(0px + var(--safe-area-inset-right, 0px));
		width: 300px;
		max-width: 85vw;
		/* Stop above the hunter bottom bar (Filters / Tile / Timeline) so those stay
		   clickable while walking; overlapping the source buttons above it is fine. */
		bottom: calc(56px + var(--safe-area-inset-bottom, 0px));
		background: white;
		z-index: 130100;
		box-shadow: -2px 0 10px rgba(0, 0, 0, 0.2);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.tl-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 16px;
		border-bottom: 1px solid #e5e7eb;
	}

	.tl-title {
		font-weight: 600;
		color: #1f2937;
	}

	.tl-header-actions {
		display: flex;
		align-items: center;
		gap: 2px;
	}

	.tl-icon-btn {
		display: flex;
		align-items: center;
		border: none;
		background: none;
		font-size: 1.1rem;
		cursor: pointer;
		color: #6b7280;
		padding: 4px 8px;
		line-height: 1;
	}

	.tl-users {
		padding: 10px 16px;
		border-bottom: 1px solid #e5e7eb;
	}

	.tl-section-title {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #9ca3af;
		margin-bottom: 4px;
	}

	.tl-user {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 6px;
		font-size: 0.9rem;
		color: #374151;
		padding: 2px 0;
	}

	.tl-user-name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.tl-user-remove {
		flex-shrink: 0;
		border: none;
		background: none;
		color: #9ca3af;
		cursor: pointer;
		font-size: 1rem;
		line-height: 1;
		padding: 0 4px;
	}

	.tl-user-remove:hover {
		color: #dc2626;
	}

	.tl-add-user {
		margin-top: 6px;
		font-size: 0.8rem;
		color: #6b7280;
		background: none;
		border: 1px dashed #d1d5db;
		border-radius: 6px;
		padding: 4px 8px;
		cursor: pointer;
	}

	.tl-add-user:hover {
		background: #f3f4f6;
	}

	.tl-picker {
		margin-top: 6px;
		border: 1px solid #e5e7eb;
		border-radius: 6px;
		overflow: hidden;
	}

	.tl-picker-input {
		width: 100%;
		box-sizing: border-box;
		border: none;
		border-bottom: 1px solid #e5e7eb;
		padding: 6px 8px;
		font-size: 0.85rem;
		outline: none;
	}

	.tl-picker-list {
		max-height: 200px;
		overflow-y: auto;
	}

	.tl-picker-empty {
		padding: 8px;
		font-size: 0.8rem;
		color: #9ca3af;
	}

	.tl-picker-option {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		width: 100%;
		border: none;
		background: none;
		text-align: left;
		padding: 6px 8px;
		cursor: pointer;
		font-size: 0.85rem;
		color: #374151;
	}

	.tl-picker-option:hover {
		background: #f3f4f6;
	}

	.tl-picker-count {
		flex-shrink: 0;
		color: #9ca3af;
		font-size: 0.75rem;
	}

	.tl-nav {
		display: flex;
		align-items: center;
		border-bottom: 1px solid #f3f4f6;
	}

	.tl-nav-btn {
		flex-shrink: 0;
	}

	.tl-nav-btn:disabled {
		color: #d1d5db;
		cursor: default;
	}

	.tl-status {
		flex: 1;
		text-align: center;
		padding: 8px 16px;
		font-size: 0.8rem;
		color: #6b7280;
	}

	.tl-list {
		flex: 1;
		overflow-y: auto;
		padding: 4px 0;
	}

	.tl-more {
		padding: 6px 16px;
		font-size: 0.7rem;
		color: #9ca3af;
		font-style: italic;
	}

	.tl-row {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		border: none;
		background: none;
		text-align: left;
		padding: 6px 16px;
		cursor: pointer;
	}

	.tl-row:hover {
		background: #f3f4f6;
	}

	.tl-row.active {
		background: #fff1ea;
		box-shadow: inset 3px 0 0 #ff6d3a;
	}

	.tl-thumb {
		width: 48px;
		height: 36px;
		object-fit: cover;
		border-radius: 4px;
		flex-shrink: 0;
		background: #e5e7eb;
	}

	.tl-thumb-empty {
		background: #e5e7eb;
	}

	.tl-when {
		font-size: 0.8rem;
		color: #374151;
	}

	.tl-up {
		color: #9ca3af;
		font-size: 0.7rem;
		margin-left: 4px;
	}

	/* Ellipsize text so it degrades gracefully when the panel is narrow. */
	.tl-title,
	.tl-status {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Narrow mode: thumbnails-only column. */
	.timeline-panel.narrow {
		width: 96px;
	}

	.timeline-panel.narrow .tl-title,
	.timeline-panel.narrow .tl-section-title,
	.timeline-panel.narrow .tl-when {
		display: none;
	}

	/* Compact mode is thumbnail-only navigation: the user/add-user section needs
	   room to be useful, so hide it here (the add-user picker forces wide anyway). */
	.timeline-panel.narrow .tl-users {
		display: none;
	}

	.timeline-panel.narrow .tl-status {
		padding: 6px 4px;
	}

	.timeline-panel.narrow .tl-nav-btn {
		padding: 4px 2px;
	}

	.timeline-panel.narrow .tl-row {
		justify-content: center;
		padding: 4px;
		gap: 0;
	}

	.timeline-panel.narrow .tl-thumb {
		width: 72px;
		height: 54px;
	}
</style>
