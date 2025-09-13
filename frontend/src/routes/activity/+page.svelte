<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { auth } from '$lib/auth.svelte';
	import { http, handleApiError } from '$lib/http';
	import StandardHeaderWithAlert from '../../components/StandardHeaderWithAlert.svelte';
	import StandardBody from '../../components/StandardBody.svelte';
	import Spinner from '../../components/Spinner.svelte';

	interface ActivityPhoto {
		id: string;
		original_filename: string;
		uploaded_at: string;
		processing_status: string;
		latitude?: number;
		longitude?: number;
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
	let error = '';
	let activityData: ActivityGroup[] = [];

	onMount(async () => {
		await loadActivityData();
	});

	async function loadActivityData() {
		try {
			loading = true;
			error = '';

			const response = await http.get('/activity/recent');

			if (!response.ok) {
				throw new Error(`Failed to fetch activity data: ${response.status}`);
			}

			const data = await response.json();

			// Group photos by date and then by user
			const grouped: { [date: string]: ActivityGroup } = {};

			data.forEach((photo: ActivityPhoto) => {
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

		} catch (err) {
			console.error('🢄Error loading activity data:', err);
			error = handleApiError(err);
		} finally {
			loading = false;
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

	function formatTime(dateStr: string): string {
		return new Date(dateStr).toLocaleTimeString('en-US', {
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function getPhotoUrl(photo: ActivityPhoto): string {
		return photo.sizes?.['320']?.url;
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
				<button on:click={loadActivityData} class="retry-button">
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
				{#each activityData as group}
					<div class="day-group">
						<h2 class="day-header">{formatDate(group.date)}</h2>

						{#each Object.entries(group.userGroups) as [username, userPhotos]}
							<div class="user-group">
								<h3 class="user-header">
									{username}
									<span class="photo-count">({userPhotos.length} photo{userPhotos.length !== 1 ? 's' : ''})</span>
								</h3>

								<div class="photo-grid">
									{#each userPhotos as photo}
										<div class="photo-item">
											<div class="photo-thumbnail">
												<img
													src={getPhotoUrl(photo)}
													alt={photo.original_filename}
													loading="lazy"
												/>
												{#if photo.processing_status !== 'completed'}
													<div class="processing-badge">
														{photo.processing_status}
													</div>
												{/if}
											</div>
											<div class="photo-info">
												<p class="filename">{photo.original_filename}</p>
												<p class="time">{formatTime(photo.uploaded_at)}</p>
												{#if photo.latitude && photo.longitude}
													<p class="location">📍 {photo.latitude.toFixed(4)}, {photo.longitude.toFixed(4)}</p>
												{/if}
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{/each}
			</div>
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

	.photo-item {
		border: 1px solid #dee2e6;
		border-radius: 6px;
		overflow: hidden;
		background: #f8f9fa;
		transition: transform 0.2s ease;
	}

	.photo-item:hover {
		transform: translateY(-2px);
		box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
	}

	.photo-thumbnail {
		position: relative;
		width: 100%;
		height: 150px;
		overflow: hidden;
	}

	.photo-thumbnail img {
		width: 100%;
		height: 100%;
		object-fit: cover;
	}

	.processing-badge {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		background: rgba(255, 193, 7, 0.9);
		color: #333;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		font-size: 0.8rem;
		font-weight: 500;
	}

	.photo-info {
		padding: 0.75rem;
	}

	.photo-info p {
		margin: 0 0 0.25rem 0;
		font-size: 0.9rem;
	}

	.filename {
		font-weight: 500;
		color: #333;
		word-break: break-word;
	}

	.time {
		color: #6c757d;
	}

	.location {
		color: #28a745;
		font-size: 0.8rem;
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
