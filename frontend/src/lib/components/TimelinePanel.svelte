<script lang="ts">
	import { fly } from 'svelte/transition';
	import { Maximize2, Minimize2 } from 'lucide-svelte';
	import {
		timelineActive,
		timelineLoading,
		timelinePhotos,
		timelineCursor,
		timelineUserIds,
		timelineHasMore,
		timelineWide,
		jumpToIndex,
		stopTimeline,
		toggleTimelineWide,
	} from '$lib/timeline';

	$: photos = $timelinePhotos;
	$: cursor = $timelineCursor;

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

	function usernameFor(id: string): string {
		for (const p of photos) {
			if ((p as any).creator?.id === id) return (p as any).creator.username || id;
		}
		return id;
	}
</script>

{#if $timelineActive}
	<aside
		class="timeline-panel"
		class:narrow={!$timelineWide}
		data-testid="timeline-panel"
		transition:fly={{ x: 320, duration: 150 }}
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
			{#each $timelineUserIds as uid (uid)}
				<div class="tl-user" data-testid="timeline-user">{usernameFor(uid)}</div>
			{/each}
			<button class="tl-add-user" disabled title="Coming soon" data-testid="timeline-add-user">{$timelineWide ? '+ add user' : '+'}</button>
		</section>

		<div class="tl-status" data-testid="timeline-status">
			{#if $timelineLoading}
				Loading…
			{:else if photos.length}
				{cursor + 1} / {photos.length}
			{:else}
				No photos
			{/if}
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
		height: calc(100vh - (60px + var(--safe-area-inset-top, 0px)));
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
		font-size: 0.9rem;
		color: #374151;
		padding: 2px 0;
	}

	.tl-add-user {
		margin-top: 6px;
		font-size: 0.8rem;
		color: #9ca3af;
		background: none;
		border: 1px dashed #d1d5db;
		border-radius: 6px;
		padding: 4px 8px;
		cursor: not-allowed;
	}

	.tl-status {
		padding: 8px 16px;
		font-size: 0.8rem;
		color: #6b7280;
		border-bottom: 1px solid #f3f4f6;
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
	.tl-user,
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

	.timeline-panel.narrow .tl-users {
		padding: 8px 6px;
	}

	.timeline-panel.narrow .tl-status {
		padding: 6px 8px;
		text-align: center;
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

	.timeline-panel.narrow .tl-add-user {
		width: 100%;
		text-align: center;
	}
</style>
