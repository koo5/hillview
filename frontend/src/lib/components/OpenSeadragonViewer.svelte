<script lang="ts">
	/**
	 * OpenSeadragonViewer.svelte
	 *
	 * Full-screen deep-zoom viewer powered by OpenSeadragon.
	 * When the photo has a DZI pyramid (sizes.full.pyramid), it is used for
	 * tile-based deep zoom so the viewer can show the image progressively
	 * without waiting for the full file to download.
	 *
	 * When no pyramid is available, the viewer falls back to a single full-size
	 * image as a Simple Image source so OpenSeadragon still provides pan/zoom.
	 *
	 * Annotorious is mounted on top of the viewer to allow users to create,
	 * view, and edit annotations.  Each edit supersedes the old annotation
	 * (creates a new DB row, marks the old one is_current=false) to preserve
	 * edit history.
	 *
	 * --- Edge-label annotation display (future work) ---
	 * The problem statement requests labels displayed at the screen edge with
	 * a line connecting them to the annotation shape.  This is not part of
	 * standard Annotorious and would require a custom Canvas overlay that
	 * listens to viewport changes and redraws leader lines on every pan/zoom
	 * tick.  A TODO is left at the bottom of this file.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { auth } from '$lib/auth.svelte.js';
	import {
		fetchAnnotations,
		createAnnotation,
		updateAnnotation,
		deleteAnnotation,
		type AnnotationData,
	} from '$lib/annotationApi';
	import type { ZoomViewData } from '$lib/zoomView.svelte';

	export let data: ZoomViewData;
	export let onClose: () => void;

	let container: HTMLDivElement;
	let viewer: any = null;
	let annotator: any = null;
	let annotations: AnnotationData[] = [];
	let annotatingEnabled = false;
	let selectedAnnotation: AnnotationData | null = null;
	let editingAnnotation: AnnotationData | null = null;
	let editBody = '';
	let errorMessage = '';
	let isLoading = true;

	$: isAuthenticated = $auth.is_authenticated;

	async function loadAnnotations() {
		if (!data.photo_id) return;
		try {
			annotations = await fetchAnnotations(data.photo_id);
			syncAnnotationsToViewer();
		} catch (e) {
			console.error('[OSD] Failed to load annotations:', e);
		}
	}

	function syncAnnotationsToViewer() {
		if (!annotator) return;
		try {
			// Clear existing and re-add from server state
			annotator.setAnnotations(
				annotations
					.filter((a) => a.target)
					.map((a) => ({
						'@context': 'http://www.w3.org/ns/anno.jsonld',
						id: a.id,
						type: 'Annotation',
						body: a.body
							? [{ type: 'TextualBody', value: a.body, purpose: 'commenting' }]
							: [],
						target: a.target,
					}))
			);
		} catch (e) {
			console.warn('[OSD] Could not sync annotations to viewer:', e);
		}
	}

	function buildTileSource() {
		const p = data.pyramid;
		if (p && p.type === 'dzi') {
			console.log('[OSD] Using DZI pyramid for tile source:', p);
			return {
				Image: {
					xmlns: 'http://schemas.microsoft.com/deepzoom/2008',
					Url: p.tiles_url + '/',
					Format: p.format,
					Overlap: String(p.overlap),
					TileSize: String(p.tile_size),
					Size: {
						Width: String(p.width),
						Height: String(p.height),
					},
				},
			};
		}
		// Fallback: single full-size image
		console.warn('[OSD] No DZI pyramid available, falling back to single-image source: ', JSON.stringify(p));
		return {
			type: 'image',
			url: data.url,
		};
	}

	onMount(async () => {
		// Dynamic import so the library is not in the SSR bundle
		const [OSD, { createOSDAnnotator }] = await Promise.all([
			import('openseadragon'),
			import('@annotorious/openseadragon'),
		]);

		const OpenSeadragon = OSD.default ?? OSD;

		viewer = new OpenSeadragon.Viewer({
			element: container,
			tileSources: buildTileSource(),
			// Disable default controls – we supply our own close button
			showNavigationControl: false,
			showNavigator: false,
			animationTime: 0.3,
			// Allow dragging even without a button press (touch-friendly)
			gestureSettingsMouse: { clickToZoom: false, dblClickToZoom: true },
			gestureSettingsTouch: { clickToZoom: false, dblClickToZoom: true },
		});

		viewer.addHandler('open', () => {
			isLoading = false;
		});

		viewer.addHandler('open-failed', () => {
			isLoading = false;
			errorMessage = 'Failed to load image';
		});

		// Mount Annotorious on the OSD viewer
		// Drawing starts disabled; the toolbar toggle enables it for authenticated users.
		annotator = createOSDAnnotator(viewer, {
			drawingEnabled: false,
		});

		// When the user finishes drawing a shape, open the text-entry dialog
		annotator.on('createAnnotation', async (annotation: any) => {
			const textBody =
				(annotation.body?.find((b: any) => b.purpose === 'commenting')?.value) ?? '';
			// If the annotation already carries a body (e.g. from a tool), use it;
			// otherwise prompt the user.  Pressing Cancel returns null → discard the shape.
			const prompted = textBody || window.prompt('Add a label for this annotation:');
			if (prompted === null) {
				// User cancelled – remove the shape
				annotator.removeAnnotation(annotation);
				return;
			}
			const body = prompted;
			try {
				const saved = await createAnnotation(data.photo_id!, {
					body,
					target: annotation.target,
				});
				annotations = [...annotations, saved];
				// Replace the temporary client-side id with the server-assigned id
				annotator.removeAnnotation(annotation);
				annotator.addAnnotation({
					...annotation,
					id: saved.id,
					body: [{ type: 'TextualBody', value: body, purpose: 'commenting' }],
				});
			} catch (e) {
				console.error('[OSD] Failed to save annotation:', e);
				annotator.removeAnnotation(annotation);
			}
		});

		annotator.on('updateAnnotation', async (annotation: any, previous: any) => {
			const body =
				annotation.body?.find((b: any) => b.purpose === 'commenting')?.value ?? '';
			try {
				const saved = await updateAnnotation(previous.id, {
					body,
					target: annotation.target,
				});
				annotations = annotations
					.filter((a) => a.id !== previous.id)
					.concat(saved);
			} catch (e) {
				console.error('[OSD] Failed to update annotation:', e);
			}
		});

		annotator.on('deleteAnnotation', async (annotation: any) => {
			try {
				await deleteAnnotation(annotation.id);
				annotations = annotations.filter((a) => a.id !== annotation.id);
			} catch (e) {
				console.error('[OSD] Failed to delete annotation:', e);
			}
		});

		// Load annotations after viewer is ready
		if (data.photo_id) {
			loadAnnotations();
		}
	});

	onDestroy(() => {
		annotator?.destroy?.();
		viewer?.destroy?.();
	});

	function toggleAnnotating() {
		if (!annotator) return;
		annotatingEnabled = !annotatingEnabled;
		annotator.setDrawingEnabled(annotatingEnabled);
		if (annotatingEnabled) {
			annotator.setDrawingTool('rectangle');
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onClose();
	}
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="osd-overlay" data-testid="osd-viewer-overlay">
	<!-- Close button -->
	<button class="close-btn" onclick={onClose} aria-label="Close zoom view" data-testid="osd-viewer-close">
		<svg width="24" height="24" viewBox="0 0 24 24" fill="none">
			<path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
		</svg>
	</button>

	<!-- Annotation toolbar (authenticated users only) -->
	{#if isAuthenticated}
		<div class="annotation-toolbar">
			<button
				class="toolbar-btn"
				class:active={annotatingEnabled}
				onclick={toggleAnnotating}
				title={annotatingEnabled ? 'Stop annotating' : 'Draw annotation'}
				data-testid="osd-annotate-toggle"
			>
				✏️ {annotatingEnabled ? 'Cancel' : 'Annotate'}
			</button>
		</div>
	{/if}

	<!-- Loading indicator -->
	{#if isLoading}
		<div class="loading-overlay">
			<div class="spinner"></div>
		</div>
	{/if}

	<!-- Error message -->
	{#if errorMessage}
		<div class="error-banner">{errorMessage}</div>
	{/if}

	<!-- OpenSeadragon container -->
	<div bind:this={container} class="osd-container"></div>

	<!-- Filename bar -->
	<div class="filename-bar">{data.filename}</div>
</div>

<!--
  TODO: Edge-label annotation display
  Future implementation should add a <canvas> overlay that:
    1. Listens to the OSD viewport-change event
    2. For each annotation, projects its shape centroid into screen space
    3. Finds the nearest screen edge and draws the label there
    4. Draws a leader line from the label to the shape centroid
  This is similar to cartographic callout labels and would require custom
  rendering outside of standard Annotorious.
-->

<style>
	.osd-overlay {
		position: fixed;
		inset: 0;
		background: #000;
		z-index: 999999;
		display: flex;
		flex-direction: column;
	}

	.osd-container {
		flex: 1;
		width: 100%;
		height: 100%;
	}

	/* Annotorious CSS is imported in the parent component */

	.close-btn {
		position: absolute;
		top: calc(12px + var(--safe-area-inset-top, 0px));
		right: calc(12px + var(--safe-area-inset-right, 0px));
		z-index: 10;
		background: rgba(255,255,255,0.85);
		border: none;
		border-radius: 50%;
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		color: #333;
	}

	.close-btn:hover { background: rgba(255,255,255,1); }

	.annotation-toolbar {
		position: absolute;
		top: calc(12px + var(--safe-area-inset-top, 0px));
		left: calc(12px + var(--safe-area-inset-left, 0px));
		z-index: 10;
		display: flex;
		gap: 8px;
	}

	.toolbar-btn {
		background: rgba(255,255,255,0.85);
		border: 2px solid transparent;
		border-radius: 8px;
		padding: 8px 12px;
		cursor: pointer;
		font-size: 14px;
		font-weight: 500;
	}

	.toolbar-btn.active {
		border-color: #4a90e2;
		background: rgba(74,144,226,0.15);
	}

	.toolbar-btn:hover { background: rgba(255,255,255,1); }

	.loading-overlay {
		position: absolute;
		inset: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		background: rgba(0,0,0,0.6);
		z-index: 5;
	}

	.spinner {
		width: 48px;
		height: 48px;
		border: 4px solid rgba(255,255,255,0.3);
		border-top-color: #fff;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin { to { transform: rotate(360deg); } }

	.error-banner {
		position: absolute;
		bottom: 60px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(220,53,69,0.9);
		color: #fff;
		padding: 8px 16px;
		border-radius: 8px;
		font-size: 14px;
		z-index: 10;
	}

	.filename-bar {
		position: absolute;
		bottom: 20px;
		left: 50%;
		transform: translateX(-50%);
		background: rgba(0,0,0,0.7);
		color: #fff;
		padding: 6px 16px;
		border-radius: 20px;
		font-size: 13px;
		max-width: 80vw;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		z-index: 10;
		pointer-events: none;
	}
</style>
