<script lang="ts">
	import { Sparkles, Pencil, Trash2, Image as ImageIcon, Crosshair, MessageSquare, LogIn } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { http } from '$lib/http';
	import { auth } from '$lib/auth.svelte';
	import { zoomLink, type AnnotationEvent } from '$lib/annotationEvents';

	// One row per annotation chain the caller has touched, collapsed to the chain's
	// current tip. The backend is deliberately judicious: it exposes only the final
	// surviving version's text (never an intermediate replacer, which could be spam)
	// and never who changed it.
	interface Contribution {
		chain_tip_id: string;
		photo_id: string;
		my_roles: string[];
		status: 'live' | 'removed';
		mine_is_current: boolean;
		current_body: string | null;
		created_at: string;
		photo_lat: number | null;
		photo_lon: number | null;
		photo_bearing: number | null;
		photo_width: number | null;
		target: unknown;
	}

	interface Summary {
		total: number;
		standing: number;
		changed_by_others: number;
		removed: number;
		photos: number;
	}

	let contributions: Contribution[] = [];
	let summary: Summary = { total: 0, standing: 0, changed_by_others: 0, removed: 0, photos: 0 };
	let truncated = false;
	let loading = false;
	let error = '';

	// Load once the session is confirmed; is_authenticated is the auth truth.
	let loadedOnce = false;
	$: if ($auth.is_authenticated && !loadedOnce) {
		loadedOnce = true;
		load();
	}

	async function load() {
		loading = true;
		error = '';
		try {
			const res = await http.get('/annotations/contributions');
			if (!res.ok) {
				error = `Failed to load your contributions (${res.status})`;
				return;
			}
			const data = await res.json();
			contributions = data.contributions ?? [];
			summary = data.summary ?? summary;
			truncated = !!data.truncated;
		} catch (e) {
			error = 'Network error loading your contributions.';
		} finally {
			loading = false;
		}
	}

	// The stat cards. "Standing" is the headline — the contributions still live as
	// the caller's own work, and the seed of any future contributor payout.
	$: stats = [
		{ key: 'standing', label: 'Standing', value: summary.standing, icon: Sparkles },
		{ key: 'changed', label: 'Edited by others', value: summary.changed_by_others, icon: Pencil },
		{ key: 'removed', label: 'Removed', value: summary.removed, icon: Trash2 },
		{ key: 'photos', label: 'Photos', value: summary.photos, icon: ImageIcon },
	];

	function roleLabel(roles: string[]): string {
		if (roles.includes('created')) return 'You added this';
		if (roles.includes('updated')) return 'You edited this';
		if (roles.includes('deleted')) return 'You removed this';
		return 'Your contribution';
	}

	// What became of the caller's contribution. Never names who changed it — for a
	// user-facing view that stays need-to-know.
	function note(c: Contribution): { tone: 'muted' | 'alert'; text: string } | null {
		if (c.status === 'removed') {
			return c.mine_is_current
				? { tone: 'muted', text: 'You removed this annotation.' }
				: { tone: 'alert', text: 'This annotation was removed by another contributor.' };
		}
		if (c.mine_is_current) return null; // standing — the status pill already says so
		return { tone: 'alert', text: 'Edited by another contributor — showing the current version.' };
	}

	// zoomLink reads photo_id/target/photo_{lat,lon,bearing,width}; a Contribution
	// carries exactly those, so reuse it directly. Removed chains have no target
	// and yield null (no spot to point at).
	function zoomFor(c: Contribution): string | null {
		return zoomLink(c as unknown as AnnotationEvent);
	}
</script>

<StandardHeaderWithAlert title="Your contributions" showMenuButton={true} fallbackHref="/" />

<StandardBody>
	<div class="contributions" data-testid="contributions-page">
		<ProfileGate>
			{#if $auth.is_authenticated}
				<p class="intro">
					Every annotation you've added, edited, or removed, collapsed to its current
					version. <strong>Standing</strong> contributions — still live as your own work —
					are what a future contributor reward would be based on.
				</p>

				<div class="summary" data-testid="contributions-summary">
					{#each stats as s}
						<div class="stat" data-testid={`contributions-stat-${s.key}`}>
							<svelte:component this={s.icon} size={16} />
							<span class="stat-value" data-testid={`contributions-stat-${s.key}-value`}>{s.value}</span>
							<span class="stat-label">{s.label}</span>
						</div>
					{/each}
				</div>

				{#if error}
					<div class="error" data-testid="contributions-error">{error}</div>
				{/if}

				{#if loading && contributions.length === 0}
					<div class="empty">Loading…</div>
				{:else if contributions.length === 0}
					<div class="empty" data-testid="contributions-empty">
						<MessageSquare size={24} />
						<p>You haven't annotated any photos yet.</p>
						<a class="cta" href="/">Explore the map</a>
					</div>
				{:else}
					{#if truncated}
						<div class="truncated" data-testid="contributions-truncated">
							Showing your most recent contributions.
						</div>
					{/if}
					<ul class="list">
						{#each contributions as c (c.chain_tip_id)}
							{@const n = note(c)}
							{@const zoom = zoomFor(c)}
							<li
								class="item"
								data-testid="contributions-item"
								data-status={c.status}
								data-mine-current={c.mine_is_current}
							>
								<div class="item-head">
									<span
										class="status"
										class:live={c.status === 'live'}
										data-testid="contributions-status"
									>{c.status === 'live' ? 'Current' : 'Removed'}</span>
									<span class="role" data-testid="contributions-role">{roleLabel(c.my_roles)}</span>
									<span class="spacer"></span>
									{#if zoom}
										<a class="zoom" href={zoom} data-testid="contributions-zoom" title="Open the photo zoomed to this spot"><Crosshair size={13} /> zoom to spot</a>
									{/if}
									<a class="photo-link" href={`/photo/hillview-${c.photo_id}`} data-testid="contributions-photo-link" title={`Open photo ${c.photo_id}`}>photo</a>
								</div>

								{#if c.status === 'removed'}
									<div class="body removed" data-testid="contributions-body">(this annotation was removed)</div>
								{:else}
									<div class="body" data-testid="contributions-body">{c.current_body}</div>
								{/if}

								{#if n}
									<div class="note" class:alert={n.tone === 'alert'} data-testid="contributions-note">{n.text}</div>
								{/if}
							</li>
						{/each}
					</ul>
				{/if}
			{:else}
				<div class="signin" data-testid="contributions-signin">
					<LogIn size={28} />
					<h2>Sign in to see your contributions</h2>
					<p>Your annotation history and contribution overview live here once you're logged in.</p>
					<a class="cta" href="/login">Log in</a>
				</div>
			{/if}
		</ProfileGate>
	</div>
</StandardBody>

<style>
	.contributions {
		max-width: 760px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.intro {
		color: #6b7280;
		font-size: 0.9rem;
		margin: 8px 0 16px 0;
	}

	.intro strong {
		color: #15803d;
	}

	.summary {
		display: grid;
		grid-template-columns: repeat(4, 1fr);
		gap: 10px;
		margin-bottom: 20px;
	}

	.stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 10px;
		padding: 12px 8px;
		color: #6b7280;
	}

	.stat :global(svg) {
		color: #9ca3af;
	}

	/* Standing is the headline number — green like the "Current" status. */
	.stat[data-testid='contributions-stat-standing'] :global(svg) {
		color: #16a34a;
	}

	.stat-value {
		font-size: 1.4rem;
		font-weight: 700;
		color: #1f2937;
		line-height: 1.1;
	}

	.stat-label {
		font-size: 0.72rem;
		text-align: center;
	}

	@media (max-width: 480px) {
		.summary {
			grid-template-columns: repeat(2, 1fr);
		}
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
		color: #6b7280;
		font-size: 0.8rem;
		margin-bottom: 10px;
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

	.list {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.item {
		background: rgba(255, 255, 255, 0.9);
		border: 1px solid #e5e7eb;
		border-radius: 10px;
		padding: 12px 14px;
	}

	/* Removed contributions read dimmer than live ones. */
	.item[data-status='removed'] {
		opacity: 0.75;
	}

	.item-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		margin-bottom: 6px;
	}

	.status {
		font-size: 0.68rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		padding: 3px 8px;
		border-radius: 999px;
		background: #fee2e2;
		color: #b91c1c;
	}

	.status.live {
		background: #dcfce7;
		color: #15803d;
	}

	.role {
		font-size: 0.78rem;
		font-weight: 600;
		color: #4b5563;
	}

	.spacer {
		flex: 1 1 auto;
	}

	.zoom,
	.photo-link {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		color: #4f46e5;
		text-decoration: none;
		font-size: 0.78rem;
		font-weight: 600;
	}

	.zoom:hover,
	.photo-link:hover {
		text-decoration: underline;
	}

	.body {
		color: #374151;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.body.removed {
		color: #9ca3af;
		font-style: italic;
	}

	.note {
		margin-top: 6px;
		font-size: 0.8rem;
		color: #6b7280;
	}

	.note.alert {
		color: #b45309;
		background: #fef3c7;
		display: inline-block;
		padding: 2px 10px;
		border-radius: 8px;
	}

	.signin {
		text-align: center;
		padding: 64px 24px;
		color: #4b5563;
	}

	.signin :global(svg) {
		color: #9ca3af;
		margin-bottom: 12px;
	}

	.signin h2 {
		margin: 0 0 8px 0;
		color: #1f2937;
	}

	.cta {
		display: inline-block;
		margin-top: 16px;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
	}

	.cta:hover {
		text-decoration: underline;
	}
</style>
