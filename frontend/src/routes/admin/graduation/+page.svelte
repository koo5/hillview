<script lang="ts">
	import StandardHeaderWithAlert from '$lib/components/StandardHeaderWithAlert.svelte';
	import StandardBody from '$lib/components/StandardBody.svelte';
	import ProfileGate from '$lib/components/ProfileGate.svelte';
	import OsdViewer, { type OsdRect } from '$lib/components/OsdViewer.svelte';
	import { http } from '$lib/http';
	import { formatUtcDateTime } from '$lib/dateUtils';
	import { isAdmin } from '$lib/adminNotifications';
	import { Sprout, Lock, AlertTriangle } from 'lucide-svelte';

	// A graduation package is what the enrichment workbench exported: a JSON ops
	// manifest (each op sets an annotation body, with a precondition) + a TriG
	// provenance appendix. The workbench and this page are deliberately separate
	// systems; the package file is the only channel between them.

	interface PackageRow {
		filename: string;
		package?: string;
		source?: string;
		created_at?: string;
		counts?: { ops?: number; facts?: number };
		n_ops?: number;
		valid: boolean;
		error?: string;
	}
	interface Fact {
		iri: string;
		predicate?: string;
		object?: string;
		status?: string;
		curator?: string;
		decided_at?: string;
	}
	interface PhotoSrc {
		photo_id: string;
		url: string | null;
		fallback_url: string | null;
		pyramid: unknown | null;
		width: number | null;
		height: number | null;
	}
	type OpStatus = 'clean' | 'conflict' | 'already_applied' | 'missing' | 'deleted' | 'new';
	interface Op {
		op?: string; // 'set_annotation_body' | 'create_annotation'
		annotation_id: string;
		current_annotation_id: string | null;
		photo_id: string;
		precondition_body: string | null;
		current_body: string | null;
		suggested_body: string;
		summary: string | null;
		status: OpStatus;
		target: Record<string, unknown> | null;
		current_target?: Record<string, unknown> | null; // set_annotation_target: the old rect
		photo: PhotoSrc | null;
		facts: Fact[];
	}
	interface Preview {
		filename: string;
		source?: string;
		created_at?: string;
		counts?: { ops?: number; facts?: number };
		provenance_available: boolean;
		ops: Op[];
	}

	let packages: PackageRow[] = [];
	let listError = '';
	let listLoading = false;

	let preview: Preview | null = null;
	let previewError = '';
	let previewLoading = false;
	let focusIdx = 0; // which op's OSD viewer is mounted (one at a time)
	let selected: Record<string, boolean> = {}; // annotation_id → apply?
	let applyBusy = false;
	let applyMsg = '';

	const STATUS_LABEL: Record<OpStatus, string> = {
		clean: 'ready',
		conflict: 'changed since export',
		already_applied: 'already applied',
		missing: 'annotation gone',
		deleted: 'annotation deleted',
		new: 'new annotation'
	};
	// an op can be applied unless there's nothing to change / nothing to target
	const applicable = (o: Op) =>
		o.status === 'clean' || o.status === 'conflict' || o.status === 'new';

	let listLoadedOnce = false;
	$: if ($isAdmin && !listLoadedOnce) {
		listLoadedOnce = true;
		loadList();
	}

	async function loadList() {
		listLoading = true;
		listError = '';
		try {
			const res = await http.get('/admin/graduation/packages');
			if (!res.ok) {
				listError = `Failed to load packages (${res.status})`;
				return;
			}
			packages = (await res.json()).packages ?? [];
		} catch {
			listError = 'Network error loading packages.';
		} finally {
			listLoading = false;
		}
	}

	async function openPackage(filename: string) {
		preview = null;
		previewError = '';
		previewLoading = true;
		applyMsg = '';
		focusIdx = 0;
		try {
			const res = await http.get(`/admin/graduation/packages/${encodeURIComponent(filename)}`);
			if (!res.ok) {
				previewError = `Failed to load package (${res.status})`;
				return;
			}
			preview = await res.json();
			// default-select every applicable op; the operator unticks what they skip
			selected = {};
			for (const o of preview?.ops ?? []) selected[o.annotation_id] = applicable(o);
		} catch {
			previewError = 'Network error loading package.';
		} finally {
			previewLoading = false;
		}
	}

	$: focusOp = preview?.ops[focusIdx] ?? null;
	$: selectedCount = preview
		? preview.ops.filter((o) => applicable(o) && selected[o.annotation_id]).length
		: 0;

	function rectFrom(
		target: Record<string, unknown> | null,
		id: string,
		kind: 'current' | 'other',
		label?: string
	): OsdRect | null {
		const g = (target as { selector?: { geometry?: Record<string, number> } })?.selector?.geometry;
		if (!g || g.x == null) return null;
		return { id, x: g.x, y: g.y ?? 0, w: g.w ?? 0.01, h: g.h ?? 0.1, label, kind };
	}
	// the rects to show for the focused op. For a reshape, show BOTH the current
	// rect (amber 'other') and the proposed rect (blue 'current'); otherwise one.
	function opRects(o: Op): OsdRect[] {
		const label = (o.suggested_body || '').split('|')[0].trim() || undefined;
		const proposed = rectFrom(o.target, o.annotation_id, 'current', label);
		if (o.op === 'set_annotation_target') {
			const cur = rectFrom(o.current_target ?? null, o.annotation_id + ':old', 'other', 'current');
			return [cur, proposed].filter(Boolean) as OsdRect[];
		}
		return proposed ? [proposed] : [];
	}

	async function applySelected() {
		if (!preview || selectedCount === 0) return;
		const ids = preview.ops
			.filter((o) => applicable(o) && selected[o.annotation_id])
			.map((o) => o.annotation_id);
		const conflicts = preview.ops.filter(
			(o) => o.status === 'conflict' && selected[o.annotation_id]
		).length;
		const msg =
			`Apply ${ids.length} annotation edit(s) as admin?` +
			(conflicts ? `\n\n${conflicts} of them changed in Hillview since export — applying will supersede the current version.` : '');
		if (!confirm(msg)) return;
		applyBusy = true;
		applyMsg = '';
		try {
			const res = await http.post(
				`/admin/graduation/packages/${encodeURIComponent(preview.filename)}/apply`,
				{ annotation_ids: ids }
			);
			if (!res.ok) {
				applyMsg = `Apply failed (${res.status})`;
				return;
			}
			const out = await res.json();
			applyMsg = `Applied ${out.applied} edit(s)${out.archived ? ' · package fully graduated and archived' : ''}.`;
			if (out.archived) {
				preview = null;
				await loadList();
			} else {
				await openPackage(preview.filename); // re-preview: applied ops flip to already_applied
			}
		} catch {
			applyMsg = 'Network error applying package.';
		} finally {
			applyBusy = false;
		}
	}
</script>

<StandardHeaderWithAlert title="Graduation" showMenuButton={true} fallbackHref="/admin" />

<StandardBody>
	<div class="grad" data-testid="admin-graduation">
		<ProfileGate>
			{#if $isAdmin}
				<header class="grad-header">
					<div class="grad-icon"><Sprout size={26} /></div>
					<div>
						<h1>Graduation</h1>
						<p class="tagline">
							Review and apply annotation edits curated in the enrichment workbench. Drop an
							exported package into the backend incoming directory, then apply its ops here.
						</p>
					</div>
				</header>

				{#if listError}<div class="error">{listError}</div>{/if}

				<div class="layout">
					<!-- package list -->
					<aside class="packages">
						<div class="packages-head">
							<span>Packages</span>
							<button class="mini" on:click={loadList} disabled={listLoading}>refresh</button>
						</div>
						{#if listLoading && packages.length === 0}
							<div class="muted pad">Loading…</div>
						{:else if packages.length === 0}
							<div class="muted pad" data-testid="grad-empty">
								No packages in the incoming directory.
							</div>
						{:else}
							{#each packages as p (p.filename)}
								<button
									class="pkg"
									class:active={preview?.filename === p.filename}
									on:click={() => openPackage(p.filename)}
									data-testid="grad-package"
								>
									<div class="pkg-name">{p.filename}</div>
									{#if p.valid}
										<div class="pkg-meta">
											{p.counts?.ops ?? p.n_ops ?? 0} ops · {p.counts?.facts ?? 0} facts
											{#if p.created_at}· {formatUtcDateTime(p.created_at)}{/if}
										</div>
									{:else}
										<div class="pkg-meta bad">invalid: {p.error ?? 'not a package'}</div>
									{/if}
								</button>
							{/each}
						{/if}
					</aside>

					<!-- selected package -->
					<section class="detail">
						{#if previewError}<div class="error">{previewError}</div>{/if}
						{#if previewLoading}
							<div class="muted pad">Loading package…</div>
						{:else if preview}
							<div class="detail-head">
								<div>
									<b>{preview.filename}</b>
									<span class="muted small">
										· {preview.ops.length} ops
										{#if preview.provenance_available}· provenance ✓{:else}· provenance n/a{/if}
									</span>
								</div>
								<div class="apply-bar">
									{#if applyMsg}<span class="muted small">{applyMsg}</span>{/if}
									<button
										class="apply"
										disabled={applyBusy || selectedCount === 0}
										on:click={applySelected}
										data-testid="grad-apply"
									>
										{applyBusy ? 'applying…' : `Apply ${selectedCount} selected`}
									</button>
								</div>
							</div>

							<div class="op-grid">
								<!-- op list (select + status) -->
								<div class="op-list">
									{#each preview.ops as o, i (o.annotation_id)}
										<div
											class="op-row"
											class:active={i === focusIdx}
											class:disabled={!applicable(o)}
										>
											<input
												type="checkbox"
												disabled={!applicable(o)}
												bind:checked={selected[o.annotation_id]}
												title="apply this edit"
											/>
											<button class="op-pick" on:click={() => (focusIdx = i)}>
												<span class="badge badge-{o.status}">{STATUS_LABEL[o.status]}</span>
												<span class="op-body">{o.suggested_body}</span>
											</button>
										</div>
									{/each}
								</div>

								<!-- focused op detail: OSD + three bodies + provenance -->
								{#if focusOp}
									<div class="op-detail">
										<div class="muted small mono">
											annotation {focusOp.annotation_id.slice(0, 8)} · photo
											<a href="/photo/hillview-{focusOp.photo_id}" target="_blank" rel="noreferrer"
												>{focusOp.photo_id.slice(0, 8)} ↗</a
											>
										</div>

										{#key focusOp.annotation_id}
											{#if focusOp.photo && focusOp.photo.width && focusOp.photo.height && (focusOp.photo.url || focusOp.photo.fallback_url)}
												<OsdViewer
													pyramid={focusOp.photo.pyramid as never}
													url={focusOp.photo.url ?? focusOp.photo.fallback_url ?? ''}
													fallbackUrl={focusOp.photo.pyramid ? focusOp.photo.fallback_url : null}
													width={focusOp.photo.width}
													height={focusOp.photo.height}
													rects={opRects(focusOp)}
													focus={opRects(focusOp).at(-1) ?? null}
													viewHeight={300}
												/>
											{:else}
												<div class="muted pad no-photo">
													{focusOp.status === 'missing' || focusOp.status === 'deleted'
														? 'The target annotation no longer exists, so there is nothing to show or apply.'
														: 'No image available for this annotation.'}
												</div>
											{/if}
										{/key}

										{#if focusOp.status === 'conflict'}
											<div class="conflict-note">
												<AlertTriangle size={15} />
												This annotation changed in Hillview since the package was exported. All three
												versions are shown — applying supersedes the current one.
											</div>
										{/if}
										{#if focusOp.op === 'create_annotation'}
											<div class="create-note">
												New annotation drawn in the workbench — applying creates it on this photo
												(the rectangle shown), attributed to you.
											</div>
										{/if}
										{#if focusOp.op === 'set_annotation_target'}
											<div class="create-note">
												Reshape — <b>amber</b> is the current rectangle, <b>blue</b> the proposed one.
												Applying supersedes the annotation with the new shape (its text is unchanged).
											</div>
										{/if}

										<div class="bodies">
											{#if focusOp.op === 'set_annotation_target'}
												<div class="body-row">
													<span class="body-tag">text (unchanged)</span>
													<code>{focusOp.current_body ?? '(none)'}</code>
												</div>
												<div class="body-row suggested">
													<span class="body-tag">reshape</span>
													<code>{focusOp.summary}</code>
												</div>
											{:else}
												{#if focusOp.op !== 'create_annotation'}
													<div class="body-row">
														<span class="body-tag">workbench saw</span>
														<code>{focusOp.precondition_body ?? '—'}</code>
													</div>
													<div
														class="body-row"
														class:changed={focusOp.status === 'conflict'}
													>
														<span class="body-tag">Hillview now</span>
														<code>{focusOp.current_body ?? '(none)'}</code>
													</div>
												{/if}
												<div class="body-row suggested">
													<span class="body-tag">{focusOp.op === 'create_annotation' ? 'new body' : 'will become'}</span>
													<code>{focusOp.suggested_body}</code>
												</div>
											{/if}
										</div>

										{#if focusOp.facts.length}
											<div class="facts">
												<div class="muted small">Provenance — approved facts behind this edit</div>
												{#each focusOp.facts as f (f.iri)}
													<div class="fact mono">
														{#if f.status === 'approved'}<span class="fact-ok">✓</span>{/if}
														<span class="fact-pred">{f.predicate ?? '?'}</span>
														= {f.object ?? f.iri.slice(-16)}
														{#if f.curator}<span class="muted">· {f.curator}</span>{/if}
														{#if f.decided_at}<span class="muted">· {formatUtcDateTime(f.decided_at)}</span>{/if}
													</div>
												{/each}
											</div>
										{/if}
									</div>
								{/if}
							</div>
						{:else}
							<div class="muted pad">Select a package to review its edits.</div>
						{/if}
					</section>
				</div>
			{:else}
				<div class="forbidden" data-testid="admin-forbidden">
					<Lock size={28} />
					<h2>Not authorized</h2>
					<p>This area is for administrators.</p>
					<a class="home-link" href="/">Back to map</a>
				</div>
			{/if}
		</ProfileGate>
	</div>
</StandardBody>

<style>
	.grad {
		max-width: 1100px;
		margin: 0 auto;
		padding: 0 16px;
	}
	.grad-header {
		display: flex;
		align-items: center;
		gap: 16px;
		margin: 8px 0 24px 0;
	}
	.grad-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 52px;
		height: 52px;
		flex: 0 0 auto;
		background: linear-gradient(135deg, #dcfce7, #bbf7d0);
		border-radius: 14px;
		color: #15803d;
	}
	.grad-header h1 {
		font-size: 1.8rem;
		font-weight: bold;
		color: #1f2937;
		margin: 0;
	}
	.tagline {
		color: #6b7280;
		margin: 4px 0 0 0;
		font-size: 0.9rem;
	}
	.layout {
		display: grid;
		grid-template-columns: 280px 1fr;
		gap: 18px;
		align-items: start;
	}
	.packages {
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		overflow: hidden;
		background: rgba(255, 255, 255, 0.85);
	}
	.packages-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 12px;
		font-weight: 600;
		color: #374151;
		border-bottom: 1px solid #eef2f7;
	}
	.pkg {
		display: block;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		border-bottom: 1px solid #f3f4f6;
		padding: 10px 12px;
		cursor: pointer;
	}
	.pkg:hover {
		background: #f9fafb;
	}
	.pkg.active {
		background: #eef2ff;
	}
	.pkg-name {
		font-size: 0.82rem;
		font-weight: 600;
		color: #1f2937;
		word-break: break-all;
	}
	.pkg-meta {
		font-size: 0.72rem;
		color: #6b7280;
		margin-top: 2px;
	}
	.pkg-meta.bad {
		color: #b91c1c;
	}
	.detail {
		min-width: 0;
	}
	.detail-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		flex-wrap: wrap;
		margin-bottom: 12px;
	}
	.apply-bar {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.apply {
		background: #16a34a;
		color: #fff;
		border: none;
		border-radius: 8px;
		padding: 7px 14px;
		font-weight: 600;
		cursor: pointer;
	}
	.apply:disabled {
		background: #9ca3af;
		cursor: default;
	}
	.op-grid {
		display: grid;
		grid-template-columns: 320px 1fr;
		gap: 16px;
		align-items: start;
	}
	.op-list {
		border: 1px solid #e5e7eb;
		border-radius: 10px;
		overflow: hidden;
		background: rgba(255, 255, 255, 0.85);
	}
	.op-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 8px 10px;
		border-bottom: 1px solid #f3f4f6;
	}
	.op-row.active {
		background: #eef2ff;
	}
	.op-row.disabled {
		opacity: 0.6;
	}
	.op-pick {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
		background: none;
		border: none;
		text-align: left;
		cursor: pointer;
		padding: 0;
	}
	.op-body {
		font-size: 0.8rem;
		color: #1f2937;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.badge {
		align-self: flex-start;
		font-size: 0.66rem;
		font-weight: 700;
		padding: 1px 7px;
		border-radius: 999px;
		text-transform: uppercase;
		letter-spacing: 0.02em;
	}
	.badge-clean {
		background: #dcfce7;
		color: #15803d;
	}
	.badge-new {
		background: #dbeafe;
		color: #1d4ed8;
	}
	.badge-conflict {
		background: #fef3c7;
		color: #b45309;
	}
	.badge-already_applied {
		background: #e0e7ff;
		color: #4338ca;
	}
	.badge-missing,
	.badge-deleted {
		background: #fee2e2;
		color: #b91c1c;
	}
	.op-detail {
		border: 1px solid #e5e7eb;
		border-radius: 10px;
		padding: 14px;
		background: rgba(255, 255, 255, 0.85);
		min-width: 0;
	}
	.conflict-note {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		background: #fffbeb;
		border: 1px solid #fde68a;
		color: #92400e;
		border-radius: 8px;
		padding: 8px 10px;
		font-size: 0.8rem;
		margin-top: 10px;
	}
	.create-note {
		background: #eff6ff;
		border: 1px solid #bfdbfe;
		color: #1e40af;
		border-radius: 8px;
		padding: 8px 10px;
		font-size: 0.8rem;
		margin-top: 10px;
	}
	.bodies {
		margin-top: 12px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.body-row {
		display: grid;
		grid-template-columns: 110px 1fr;
		gap: 10px;
		align-items: baseline;
	}
	.body-row code {
		font-size: 0.82rem;
		word-break: break-word;
		color: #374151;
	}
	.body-tag {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.03em;
		color: #9ca3af;
		text-align: right;
	}
	.body-row.changed code {
		color: #b45309;
		background: #fffbeb;
		border-radius: 4px;
		padding: 1px 4px;
	}
	.body-row.suggested code {
		color: #15803d;
		font-weight: 600;
	}
	.facts {
		margin-top: 12px;
		border-top: 1px solid #f3f4f6;
		padding-top: 10px;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.fact {
		font-size: 0.74rem;
		color: #4b5563;
	}
	.fact-ok {
		color: #16a34a;
		font-weight: 700;
	}
	.fact-pred {
		color: #1f2937;
		font-weight: 600;
	}
	.no-photo {
		border: 1px dashed #e5e7eb;
		border-radius: 8px;
		text-align: center;
	}
	.mono {
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
	}
	.muted {
		color: #6b7280;
	}
	.small {
		font-size: 0.78rem;
	}
	.pad {
		padding: 16px;
	}
	.mini {
		font-size: 0.72rem;
		background: none;
		border: 1px solid #d1d5db;
		border-radius: 6px;
		padding: 2px 8px;
		cursor: pointer;
		color: #374151;
	}
	.error {
		background: #fef2f2;
		border: 1px solid #fecaca;
		color: #991b1b;
		padding: 10px 14px;
		border-radius: 8px;
		margin-bottom: 12px;
		font-size: 0.875rem;
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
	.home-link {
		display: inline-block;
		margin-top: 16px;
		color: #4f46e5;
		text-decoration: none;
		font-weight: 600;
	}
	@media (max-width: 860px) {
		.layout,
		.op-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
