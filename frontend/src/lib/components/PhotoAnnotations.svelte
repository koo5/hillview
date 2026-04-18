<script lang="ts">
	import {
		parseAnnotationBody,
		formatDate,
		type PhotoAnnotation
	} from '$lib/photoDisplay';

	export let annotations: PhotoAnnotation[] = [];
	export let heading: string = 'Annotations';
</script>

{#if annotations.length > 0}
	<section class="annotations" data-testid="photo-annotations">
		<h2>{heading}</h2>
		<ul>
			{#each annotations as a (a.id)}
				<li class="annotation" data-testid="photo-annotation">
					<p class="body" data-testid="photo-annotation-body">
						{#each parseAnnotationBody(a.body) as seg, i}
							{#if i > 0}{' '}{/if}
							{#if seg.kind === 'link'}
								<a href={seg.value} rel="ugc nofollow noopener" target="_blank">{seg.value}</a>
							{:else}
								{seg.value}
							{/if}
						{/each}
					</p>
					<p class="attribution">
						{#if a.owner_username}
							<a href={`/users/${a.owner_username}`} data-testid="photo-annotation-owner"
								>@{a.owner_username}</a
							>
						{/if}
						{#if a.created_at}
							<span class="date" data-testid="photo-annotation-date">{formatDate(a.created_at)}</span>
						{/if}
					</p>
				</li>
			{/each}
		</ul>
	</section>
{/if}

<style>
	.annotations {
		margin-top: 1.5rem;
		border-top: 1px solid #eee;
		padding-top: 1rem;
	}

	.annotations h2 {
		font-size: 1.1rem;
		margin: 0 0 0.75rem 0;
	}

	.annotations ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	.annotation {
		padding: 0.5rem 0;
		border-bottom: 1px solid #f1f1f1;
	}

	.annotation:last-child {
		border-bottom: none;
	}

	.annotation .body {
		margin: 0 0 0.25rem 0;
		word-break: break-word;
	}

	.annotation .attribution {
		margin: 0;
		font-size: 0.85rem;
		color: #6c757d;
	}

	.annotation .date {
		margin-left: 0.5rem;
	}
</style>
