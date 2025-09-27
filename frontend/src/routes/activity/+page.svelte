<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/auth.svelte';
	import { http, handleApiError } from '$lib/http';
	import { myGoto } from '$lib/navigation.svelte';
	import { constructPhotoMapUrl, constructUserProfileUrl } from '$lib/urlUtils';
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import Spinner from '../../components/Spinner.svelte';
	import LoadMoreButton from '$lib/components/LoadMoreButton.svelte';
	import PhotoItem from '$lib/components/PhotoItem.svelte';

	interface ActivityPhoto {
		id: string;
		original_filename: string;
		uploaded_at: string;
		processing_status: string;
		latitude?: number;
		longitude?: number;
		bearing?: number;
		width?: number;
		height?: number;
		sizes?: Record<string, { path: string; url: string; width: number; height: number }>;
		owner_username: string;
		owner_id: string;
	}

	interface ActivityGroup {
		date: string;
		photos: ActivityPhoto[];
		userGroups: { [username: string]: ActivityPhoto[] };
	}

	let loading = true;
	let loadingMore = false;
	let error = '';
	let activityData: ActivityGroup[] = [];
	let totalPhotoCount = 0;
	let hasMorePhotos = false;
	let nextCursor: string | null = null;

	onMount(async () => {
		await loadActivityData();
	});

	async function loadActivityData(cursor?: string) {
		try {
			if (cursor) {
				loadingMore = true;
			} else {
				loading = true;
			}
			error = '';

			const url = cursor
				? `/activity/recent?cursor=${encodeURIComponent(cursor)}`
				: '/activity/recent';
			const response = await http.get(url);

			if (!response.ok) {
				throw new Error(`Failed to fetch activity data: ${response.status}`);
			}

			const data = await response.json();
			const photos = data.photos || [];

			hasMorePhotos = data.has_more || false;
			nextCursor = data.next_cursor || null;

			// Group photos by date and then by user
			const grouped: { [date: string]: ActivityGroup } = {};

			// If loading more, start with existing data
			if (cursor && activityData.length > 0) {
				activityData.forEach(group => {
					grouped[group.date] = { ...group };
				});
			}

			photos.forEach((photo: ActivityPhoto) => {
				const date = new Date(photo.uploaded_at).toISOString().split('T')[0];

				if (!grouped[date]) {
					grouped[date] = {
						date,
						photos: [],
						userGroups: {}
					};
				}

				grouped[date].photos.push(photo);

				if (!grouped[date].userGroups[photo.owner_username]) {
					grouped[date].userGroups[photo.owner_username] = [];
				}
				grouped[date].userGroups[photo.owner_username].push(photo);
			});

			// Convert to array and sort by date (newest first)
			activityData = Object.values(grouped).sort((a, b) =>
				new Date(b.date).getTime() - new Date(a.date).getTime()
			);

			// Update total count
			if (!cursor) {
				totalPhotoCount = photos.length;
			} else {
				totalPhotoCount += photos.length;
			}

		} catch (err) {
			console.error('🢄Error loading activity data:', err);
			error = handleApiError(err);
		} finally {
			loading = false;
			loadingMore = false;
		}
	}

	async function loadMorePhotos() {
		if (nextCursor && !loadingMore) {
			await loadActivityData(nextCursor);
		}
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		const today = new Date();
		const yesterday = new Date(today);
		yesterday.setDate(yesterday.getDate() - 1);

		if (date.toDateString() === today.toDateString()) {
			return 'Today';
		} else if (date.toDateString() === yesterday.toDateString()) {
			return 'Yesterday';
		} else {
			return date.toLocaleDateString('en-US', {
				weekday: 'long',
				year: 'numeric',
				month: 'long',
				day: 'numeric'
			});
		}
	}


	function formatPhotoCount(count: number, username: string, groupIndex: number, userIndex: number): string {
		// Show + if this is the last user group in the last day group and we have more photos to load
		// This indicates there might be more photos from this user that haven't loaded yet
		const isLastGroup = groupIndex === activityData.length - 1;
		const isLastUserInGroup = userIndex === Object.entries(activityData[groupIndex].userGroups).length - 1;

		if (hasMorePhotos && isLastGroup && isLastUserInGroup) {
			return `${count}+`;
		}
		return count.toString();
	}

	function viewUserProfile(userId: string) {
		myGoto(constructUserProfileUrl(userId));
	}
</script>

<svelte:head>
	<title>Activity - Hillview</title>
</svelte:head>

<StandardHeaderWithAlert
	title="Recent Activity"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>

		{#if loading}
			<div class="loading-container">
				<Spinner />
				<p>Loading recent activity...</p>
			</div>
		{:else if error}
			<div class="error">
				<p>Error loading activity: {error}</p>
				<button on:click={() => loadActivityData()} class="retry-button">
					Try Again
				</button>
			</div>
		{:else if activityData.length === 0}
			<div class="empty-state">
				<p>No recent activity found.</p>
				<p>Photos will appear here as they are uploaded to Hillview.</p>
			</div>
		{:else}
			<div class="activity-list">
				{#each activityData as group, groupIndex}
					<div class="day-group">
						<h2 class="day-header">{formatDate(group.date)}</h2>

						{#each Object.entries(group.userGroups) as [username, userPhotos], userIndex}
							<div class="user-group">
								<h3 class="user-header">
									<button class="username-link" on:click={() => viewUserProfile(userPhotos[0].owner_id)}>
										{username}
									</button>
									<span class="photo-count">({formatPhotoCount(userPhotos.length, username, groupIndex, userIndex)} photo{userPhotos.length !== 1 ? 's' : ''})</span>
								</h3>

								<div class="photo-grid">
									{#each userPhotos as photo}
										<PhotoItem
											{photo}
											variant="thumbnail"
											showDates={false}
											showTime={true}
											showDescription={false}
										/>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{/each}
			</div>

			<LoadMoreButton
				hasMore={hasMorePhotos && !loading}
				loading={loadingMore}
				onLoadMore={loadMorePhotos}
			/>
		{/if}
</StandardBody>

<style>



	.loading-container {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 4rem 0;
		gap: 1rem;
	}

	.error {
		text-align: center;
		padding: 2rem;
		background: white;
		border-radius: 8px;
		border: 1px solid #dc3545;
		color: #dc3545;
	}

	.retry-button {
		background: #dc3545;
		color: white;
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 4px;
		cursor: pointer;
		margin-top: 1rem;
	}

	.retry-button:hover {
		background: #c82333;
	}

	.empty-state {
		text-align: center;
		padding: 4rem 2rem;
		background: white;
		border-radius: 8px;
		color: #666;
	}

	.activity-list {
		display: flex;
		flex-direction: column;
		gap: 2rem;
	}

	.day-group {
		background: white;
		border-radius: 8px;
		padding: 1.5rem;
		box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
	}

	.day-header {
		margin: 0 0 1.5rem 0;
		font-size: 1.5rem;
		font-weight: 600;
		color: #333;
		border-bottom: 2px solid #4a90e2;
		padding-bottom: 0.5rem;
	}

	.user-group {
		margin-bottom: 2rem;
	}

	.user-group:last-child {
		margin-bottom: 0;
	}

	.user-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0 0 1rem 0;
		font-size: 1.2rem;
		font-weight: 500;
		color: #495057;
	}

	.username-link {
		background: none;
		border: none;
		color: #4a90e2;
		font-size: inherit;
		font-weight: inherit;
		cursor: pointer;
		text-decoration: underline;
		padding: 0;
		margin: 0;
		font-family: inherit;
		transition: color 0.2s ease;
	}

	.username-link:hover {
		color: #357abd;
	}

	.photo-count {
		font-size: 0.9rem;
		color: #6c757d;
		font-weight: normal;
	}

	.photo-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 1rem;
	}


	@media (max-width: 768px) {

		.photo-grid {
			grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
			gap: 0.75rem;
		}

		.day-group {
			padding: 1rem;
		}

	}
</style>
