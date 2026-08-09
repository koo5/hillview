<script lang="ts">
	import { adminNotifications, isAdmin } from '$lib/adminNotifications';

	// 'corner' floats over a positioned parent (the hamburger buttons); 'inline'
	// sits at the end of a flex row (the Admin menu item).
	export let variant: 'corner' | 'inline' = 'corner';

	$: total = $adminNotifications.total;
	$: show = $isAdmin && total > 0;
	$: display = total > 99 ? '99+' : String(total);
</script>

{#if show}
	<span
		class="admin-badge {variant}"
		data-testid="admin-notification-badge"
		aria-label={`${total} unhandled admin items`}
		title={`${total} unhandled admin items`}
	>{display}</span>
{/if}

<style>
	.admin-badge {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 18px;
		height: 18px;
		padding: 0 5px;
		box-sizing: border-box;
		border-radius: 9px;
		background: #dc2626;
		color: #fff;
		font-size: 0.7rem;
		font-weight: 700;
		line-height: 1;
	}

	.admin-badge.corner {
		position: absolute;
		top: -2px;
		right: -2px;
		box-shadow: 0 0 0 2px white;
		pointer-events: none;
	}

	.admin-badge.inline {
		margin-left: auto;
	}
</style>
