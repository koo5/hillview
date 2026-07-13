<script lang="ts">
	import { ShieldCheck, Flag, MessageSquare, ScrollText, Lock } from 'lucide-svelte';
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import { isModerator } from '$lib/adminNotifications';
</script>

<StandardHeaderWithAlert title="Moderate" showMenuButton={true} fallbackHref="/" />

<StandardBody>
	<div class="moderate" data-testid="moderate-dashboard">
		<ProfileGate>
			{#if $isModerator}
				<header class="mod-header">
					<div class="mod-icon"><ShieldCheck size={28} /></div>
					<div>
						<h1>Moderate</h1>
						<p class="mod-tagline">Content moderation tools.</p>
					</div>
				</header>

				<section class="card-grid">
					<a class="mod-card" href="/admin/flags" data-testid="moderate-card-flags">
						<div class="card-top">
							<Flag size={20} />
							<span class="card-title">Flagged photos</span>
						</div>
						<div class="card-sub">review and resolve open flags</div>
					</a>

					<a class="mod-card" href="/admin/annotations" data-testid="moderate-card-annotations">
						<div class="card-top">
							<MessageSquare size={20} />
							<span class="card-title">Annotation activity</span>
						</div>
						<div class="card-sub">creates, edits, deletes — with undo</div>
					</a>

					<a class="mod-card" href="/admin/audit" data-testid="moderate-card-audit">
						<div class="card-top">
							<ScrollText size={20} />
							<span class="card-title">Moderation audit</span>
						</div>
						<div class="card-sub">a log of moderation deletions</div>
					</a>
				</section>
			{:else}
				<div class="forbidden" data-testid="moderate-forbidden">
					<Lock size={28} />
					<h2>Not authorized</h2>
					<p>This area is for moderators.</p>
					<a class="home-link" href="/">Back to map</a>
				</div>
			{/if}
		</ProfileGate>
	</div>
</StandardBody>

<style>
	.moderate {
		max-width: 900px;
		margin: 0 auto;
		padding: 0 16px;
	}

	.mod-header {
		display: flex;
		align-items: center;
		gap: 16px;
		margin: 8px 0 32px 0;
	}

	.mod-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 56px;
		height: 56px;
		flex: 0 0 auto;
		background: linear-gradient(135deg, #dcfce7, #bbf7d0);
		border-radius: 14px;
		color: #15803d;
	}

	.mod-header h1 {
		font-size: 2rem;
		font-weight: bold;
		color: #1f2937;
		margin: 0;
	}

	.mod-tagline {
		color: #6b7280;
		margin: 4px 0 0 0;
	}

	.card-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
		gap: 16px;
	}

	.mod-card {
		display: block;
		text-decoration: none;
		color: inherit;
		background: rgba(255, 255, 255, 0.85);
		border: 1px solid #e5e7eb;
		border-radius: 14px;
		padding: 20px;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
		transition: box-shadow 0.15s ease, transform 0.15s ease;
	}

	.mod-card:hover {
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
		transform: translateY(-1px);
	}

	.card-top {
		display: flex;
		align-items: center;
		gap: 8px;
		color: #4b5563;
	}

	.card-title {
		font-weight: 600;
		font-size: 0.95rem;
	}

	.card-sub {
		font-size: 0.8rem;
		color: #6b7280;
		margin-top: 8px;
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
