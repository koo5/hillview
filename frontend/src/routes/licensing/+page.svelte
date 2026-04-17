<svelte:head>
	<title>Licensing - Hillview</title>
</svelte:head>

<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import { CreativeCommons, Calendar, Copyright, MapPin } from 'lucide-svelte';
	import MyExternalLink from '$lib/components/MyExternalLink.svelte';
</script>

<StandardHeaderWithAlert
	title="Licensing"
	showMenuButton={true}
	fallbackHref="/"
/>

<StandardBody>
	<div class="legal-document">
		<header class="document-header">
			<div class="document-icon">
				<CreativeCommons size={48} />
			</div>
			<h1>Licensing</h1>
			<div class="document-meta">
				<div class="meta-item">
					<Calendar size={16} />
					<span>Last updated: April 2026</span>
				</div>
			</div>
		</header>

		<section class="document-section">
			<h2>Overview</h2>
			<p>
				When you upload a photo to Hillview, you choose a license that determines how others may use it.
				This page explains the licensing options available and what each one means.
			</p>
		</section>

		<section class="document-section">
			<h2>
				<CreativeCommons size={24} />
				CC BY-SA 4.0 + OSM grant
			</h2>
			<p>
				The primary license for user-contributed photos on Hillview. It consists of two parts:
			</p>

			<h3>Part 1 — Creative Commons Attribution-ShareAlike 4.0 International</h3>
			<p>
				You grant the public the right to copy, redistribute, remix, transform, and build upon
				your photo for any purpose (including commercially), under these conditions:
			</p>
			<ul>
				<li>
					<strong>Attribution:</strong> users must give appropriate credit, provide a link to the
					license, and indicate if changes were made.
				</li>
				<li>
					<strong>ShareAlike:</strong> if users remix, transform, or build upon the photo, they
					must distribute their contributions under the same license.
				</li>
			</ul>
			<p>
				Full license text: <MyExternalLink href="https://creativecommons.org/licenses/by-sa/4.0/">creativecommons.org/licenses/by-sa/4.0</MyExternalLink>
			</p>

			<h3>Part 2 — OpenStreetMap mapping grant</h3>
			<p>
				In addition to CC BY-SA 4.0, you grant permission to use your photo as reference material
				for creating, improving, or validating contributions to the OpenStreetMap database.
				This includes tracing geometries, identifying features, recording factual observations,
				and any workflow supporting such contributions.
			</p>
			<p>
				Data that OpenStreetMap mappers extract from your photo and submit to the
				OpenStreetMap database becomes part of OSM under the Open Database License (ODbL).
				This grant does <strong>not</strong> authorize extraction of data from your photo for
				any other purpose or license.
			</p>

			<h3>What this means in practice</h3>
			<ul>
				<li>Anyone may display, share, and remix your photo as long as they attribute you and share-alike.</li>
				<li>OpenStreetMap mappers may freely use your photo as reference for OSM work.</li>
				<li>Commercial reuse of the photo is permitted under CC BY-SA 4.0.</li>
				<li>Commercial extraction of data from the photo (outside of OSM contributions) is <em>not</em> authorized by the OSM grant and remains constrained by CC BY-SA 4.0 share-alike.</li>
			</ul>
		</section>

		<section class="document-section">
			<h2>
				<Copyright size={24} />
				All rights reserved
			</h2>
			<p>
				Some photos on Hillview — typically the founder's seed content — are displayed under
				all rights reserved. You may view these photos on Hillview, but they are not licensed
				for copying, redistribution, or reuse without explicit permission.
			</p>
		</section>

		<section class="document-section">
			<h2>
				<CreativeCommons size={24} />
				Mapillary photos
			</h2>
			<p>
				Hillview displays photos from <MyExternalLink href="https://www.mapillary.com">Mapillary</MyExternalLink>
				alongside user-contributed photos. Mapillary licenses its user-contributed imagery
				under CC BY-SA 4.0 per its own terms. These photos are not covered by Hillview's
				OSM grant — only by the underlying CC BY-SA 4.0 license granted by the original
				Mapillary contributor. When reusing a Mapillary photo, please attribute both the
				original contributor and Mapillary as required by Mapillary's
				<MyExternalLink href="https://www.mapillary.com/terms">terms</MyExternalLink>.
			</p>
		</section>

		<section class="document-section">
			<h2>
				<MapPin size={24} />
				Why this approach?
			</h2>
			<p>
				Hillview is a community-driven project that benefits from open contribution and from
				being a useful reference for OpenStreetMap. The CC BY-SA 4.0 license aligns Hillview
				with other open-imagery platforms like Mapillary, KartaView, and Panoramax. The
				additional OSM grant makes Hillview unambiguously usable for OSM mapping — the
				primary practical use case for geotagged reference photography.
			</p>
		</section>

		<section class="document-section">
			<h2>Questions?</h2>
			<p>
				If you have questions about licensing, please reach out via the
				<a href="/contact" class="legal-link">contact form</a>
				or the <MyExternalLink href="https://github.com/koo5/hillview/issues">GitHub issue tracker</MyExternalLink>.
			</p>
		</section>
	</div>
</StandardBody>

<style>
	.legal-document {
		max-width: 800px;
		margin: 0 auto;
		background: white;
		border-radius: 12px;
		box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
		overflow: hidden;
	}

	.document-header {
		text-align: center;
		padding: 40px 32px;
		background: linear-gradient(135deg, #f8fafc, #e2e8f0);
		border-bottom: 1px solid #e5e7eb;
	}

	.document-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 80px;
		height: 80px;
		background: linear-gradient(135deg, #3b82f6, #1d4ed8);
		border-radius: 20px;
		color: white;
		margin-bottom: 16px;
	}

	.document-header h1 {
		font-size: 2.25rem;
		font-weight: bold;
		color: #1f2937;
		margin: 0 0 16px 0;
	}

	.document-meta {
		display: flex;
		justify-content: center;
		gap: 24px;
		flex-wrap: wrap;
	}

	.meta-item {
		display: flex;
		align-items: center;
		gap: 8px;
		color: #6b7280;
		font-size: 0.875rem;
	}

	.document-section {
		padding: 32px;
		border-bottom: 1px solid #f3f4f6;
	}

	.document-section:last-of-type {
		border-bottom: none;
	}

	.document-section h2 {
		font-size: 1.5rem;
		font-weight: 600;
		color: #1f2937;
		margin: 0 0 16px 0;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.document-section h3 {
		font-size: 1.125rem;
		font-weight: 600;
		color: #1f2937;
		margin: 24px 0 12px 0;
	}

	.document-section p {
		color: #4b5563;
		line-height: 1.7;
		margin: 0 0 16px 0;
		font-size: 1rem;
	}

	.document-section ul {
		color: #4b5563;
		line-height: 1.7;
		margin: 0 0 16px 0;
		padding-left: 24px;
	}

	.document-section li {
		margin-bottom: 8px;
	}

	.legal-link {
		color: #3b82f6;
		text-decoration: underline;
		transition: color 0.2s ease;
	}

	.legal-link:hover {
		color: #1d4ed8;
	}

	@media (max-width: 768px) {
		.legal-document {
			margin: 0;
			border-radius: 0;
		}

		.document-header {
			padding: 32px 24px;
		}

		.document-header h1 {
			font-size: 1.875rem;
		}

		.document-section {
			padding: 24px;
		}
	}
</style>
