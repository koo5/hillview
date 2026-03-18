import { test, expect } from './fixtures';
import { recreateTestUsers, loginAsTestUser } from './helpers/testUsers';

import { uploadPhoto, testPhotos } from './helpers/photoUpload';
import { ensureSourceEnabled } from './helpers/sourceHelpers';
import { BACKEND_URL } from './helpers/adminAuth';

// ─── Helpers ───────────────────────────────────────────────────────────

type Page = import('@playwright/test').Page;

/** Fetch current annotations for a photo from the API. */
async function apiAnnotations(photoId: string) {
  const res = await fetch(`${BACKEND_URL}/api/annotations/photos/${photoId}`);
  return res.json();
}

/** Get the bounding box of the OSD canvas — waits for it to be visible. */
async function canvasBox(page: Page) {
  const canvas = page.locator('.openseadragon-canvas');
  await canvas.waitFor({ state: 'visible' });
  const box = await canvas.boundingBox();
  expect(box).toBeTruthy();
  return box!;
}

/**
 * Draw a rectangle on the OSD canvas at the given fractional region
 * and fill the label via the edit panel.
 */
async function drawAnnotation(
  page: Page,
  label: string,
  region = { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 },
) {
  // Ensure OSD viewer is open before interacting with canvas
  await expect(page.locator('[data-testid="osd-viewer-overlay"]')).toBeVisible({ timeout: 5000 });

  // Draw mode is one-shot (turns off after each shape), so re-enter it
  await enterDrawMode(page);

  const box = await canvasBox(page);

  const startX = box.x + box.width * region.x1;
  const startY = box.y + box.height * region.y1;
  const endX = box.x + box.width * region.x2;
  const endY = box.y + box.height * region.y2;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(endX, endY, { steps: 10 });
  await page.mouse.up();

  // The edit panel opens automatically after drawing
  const editPanel = page.locator('[data-testid="osd-edit-body-panel"]');
  await editPanel.waitFor({ state: 'visible', timeout: 10000 });

  // Fill label and save
  const input = page.locator('[data-testid="osd-edit-body-input"]');
  await input.fill(label);
  await page.click('[data-testid="osd-edit-body-save"]');
  await expect(editPanel).not.toBeVisible({ timeout: 5000 });

  // Wait for server persist
  await page.waitForTimeout(1000);

  return box;
}

/**
 * Click the center of the given fractional region on the canvas.
 * Used to select an annotation we drew at that region.
 */
async function clickRegion(page: Page, region = { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 }) {
  const box = await canvasBox(page);
  const cx = box.x + box.width * ((region.x1 + region.x2) / 2);
  const cy = box.y + box.height * ((region.y1 + region.y2) / 2);
  await page.mouse.click(cx, cy);
}

/**
 * Drag from the center of `fromRegion` by `(dx, dy)` fraction of canvas size.
 * Used to move an annotation that's already selected for editing.
 */
async function dragAnnotation(
  page: Page,
  fromRegion: { x1: number; y1: number; x2: number; y2: number },
  dx: number,
  dy: number,
) {
  const box = await canvasBox(page);
  const startX = box.x + box.width * ((fromRegion.x1 + fromRegion.x2) / 2);
  const startY = box.y + box.height * ((fromRegion.y1 + fromRegion.y2) / 2);
  const endX = startX + box.width * dx;
  const endY = startY + box.height * dy;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(endX, endY, { steps: 10 });
  await page.mouse.up();
  await page.waitForTimeout(300);
}

/** Wait for the edit panel to appear. */
async function waitForEditPanel(page: Page) {
  const panel = page.locator('[data-testid="osd-edit-body-panel"]');
  await panel.waitFor({ state: 'visible', timeout: 10000 });
  return panel;
}

/** Open the OSD viewer by clicking the main photo. */
async function openViewer(page: Page) {
  const mainPhoto = page.locator('[data-testid="main-photo"]');
  await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });
  await mainPhoto.click();
  await page.locator('[data-testid="osd-viewer-overlay"]').waitFor({ state: 'visible', timeout: 15000 });
  // Wait for OpenSeadragon canvas to initialize (tiled mode)
  await page.locator('.openseadragon-canvas').waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForTimeout(500);
}

/** Close the OSD viewer. */
async function closeViewer(page: Page) {
  await page.click('[data-testid="osd-viewer-close"]');
  await expect(page.locator('[data-testid="osd-viewer-overlay"]')).not.toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(500);
}

/** Enter edit mode (idempotent — won't toggle off if already active). */
async function enterEditMode(page: Page) {
  const btn = page.locator('[data-testid="osd-annotate-edit"]');
  await btn.waitFor({ state: 'visible', timeout: 5000 });
  const isActive = await btn.evaluate(el => el.classList.contains('active'));
  if (!isActive) await btn.click();
}

/** Enter draw mode (idempotent — won't toggle off if already active). */
async function enterDrawMode(page: Page) {
  const btn = page.locator('[data-testid="osd-annotate-draw"]');
  await btn.waitFor({ state: 'visible', timeout: 5000 });
  const isActive = await btn.evaluate(el => el.classList.contains('active'));
  if (!isActive) await btn.click();
}

/** Select an annotation in edit mode and wait for panel. */
async function selectAnnotation(page: Page, region = { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 }) {
  await clickRegion(page, region);
  return waitForEditPanel(page);
}

/** Read the current value from the edit panel input. */
async function editPanelValue(page: Page) {
  return page.locator('[data-testid="osd-edit-body-input"]').inputValue();
}

/** Save the current edit via the panel button. */
async function clickSave(page: Page) {
  await page.click('[data-testid="osd-edit-body-save"]');
  await expect(page.locator('[data-testid="osd-edit-body-panel"]')).not.toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(500);
}

/** Cancel the current edit via the panel button. */
async function clickCancel(page: Page) {
  await page.click('[data-testid="osd-edit-body-cancel"]');
  await expect(page.locator('[data-testid="osd-edit-body-panel"]')).not.toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(500);
}

/** Delete via the edit panel button. */
async function clickDelete(page: Page) {
  await page.click('[data-testid="osd-edit-body-delete"]');
  await expect(page.locator('[data-testid="osd-edit-body-panel"]')).not.toBeVisible({ timeout: 5000 });
  await page.waitForTimeout(500);
}

/** Change the label text in the edit panel (clear + fill). */
async function setLabel(page: Page, text: string) {
  const input = page.locator('[data-testid="osd-edit-body-input"]');
  await input.clear();
  await input.fill(text);
}

// ─── Tests ─────────────────────────────────────────────────────────────

test.describe('Annotation Tests', () => {
  test.describe.configure({ mode: 'serial' });

  let photoId: string;

  test.beforeEach(async ({ page, testUsers }) => {

    // Recreate test users (also cleans photos)
    await recreateTestUsers();

    // Login
    await loginAsTestUser(page, testUsers.passwords.test);

    // Upload a geotagged test photo
    await uploadPhoto(page, testPhotos[0]);

    // Navigate to the map centred on the test photo's GPS coords
    await page.goto('/?lat=50.1153&lon=14.4938&zoom=18');
    await page.waitForLoadState('networkidle');

    // Enable Hillview source
    await ensureSourceEnabled(page, 'hillview', true);

    // Wait for the gallery photo to appear
    const mainPhoto = page.locator('[data-testid="main-photo"]');
    await mainPhoto.waitFor({ state: 'visible', timeout: 30000 });

    // Extract photo_id
    photoId = await mainPhoto.evaluate((el) => {
      const data = JSON.parse(el.getAttribute('data-photo') || '{}');
      return data.id;
    });
    expect(photoId).toBeTruthy();

    // Open the OSD zoom view (waits for OSD canvas to initialize)
    await openViewer(page);
  });

  // ── Basic CRUD ──

  test('should create an annotation on a photo', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'test-label');

    const annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('test-label');
  });

  test('should edit an annotation label', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'original-label');

    await enterEditMode(page);
    await selectAnnotation(page);
    await setLabel(page, 'updated-label');
    await clickSave(page);

    await page.waitForTimeout(500);
    const annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('updated-label');
  });

  test('should delete an annotation via edit panel', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'to-delete');

    let annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);

    await enterEditMode(page);
    await selectAnnotation(page);
    await clickDelete(page);

    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(0);
  });

  // ── Cancel reverts ──

  test('should cancel a label edit without persisting', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'keep-me');

    await enterEditMode(page);
    await selectAnnotation(page);

    // Verify the input shows the current label
    expect(await editPanelValue(page)).toBe('keep-me');

    // Change text then cancel
    await setLabel(page, 'nope-changed');
    await clickCancel(page);

    // API should still have the original label
    await page.waitForTimeout(500);
    const annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('keep-me');
  });

  test('should cancel a new annotation without persisting', async ({ page }) => {
    await enterDrawMode(page);

    // Start drawing but cancel instead of saving
    const box = await canvasBox(page);
    await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.3);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6, { steps: 10 });
    await page.mouse.up();

    await waitForEditPanel(page);
    await setLabel(page, 'will-be-cancelled');
    await clickCancel(page);

    // Nothing should be persisted
    await page.waitForTimeout(500);
    const annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(0);
  });

  // ── Viewer open/close round-trips ──

  test('should persist annotation across viewer close/reopen', async ({ page }) => {
    // Create
    await enterDrawMode(page);
    await drawAnnotation(page, 'survives-close');

    // Close and reopen
    await closeViewer(page);
    await openViewer(page);

    // Switch to edit mode and verify the annotation is still clickable
    await enterEditMode(page);
    await selectAnnotation(page);
    expect(await editPanelValue(page)).toBe('survives-close');
    await clickCancel(page);
  });

  test('should handle multiple create-close-reopen cycles', async ({ page }) => {
    // Round 1: create annotation, close viewer
    await enterDrawMode(page);
    await drawAnnotation(page, 'round-1');
    await closeViewer(page);

    // Round 2: reopen, create a second annotation in a different spot
    await openViewer(page);
    await enterDrawMode(page);
    await drawAnnotation(page, 'round-2', { x1: 0.1, y1: 0.6, x2: 0.35, y2: 0.85 });
    await closeViewer(page);

    // Verify both persisted
    const annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(2);
    const bodies = annotations.map((a: any) => a.body).sort();
    expect(bodies).toEqual(['round-1', 'round-2']);

    // Round 3: reopen, edit one, close, verify
    await openViewer(page);
    await enterEditMode(page);
    await selectAnnotation(page); // clicks center of default region = round-1
    await setLabel(page, 'round-1-edited');
    await clickSave(page);
    await closeViewer(page);

    await page.waitForTimeout(500);
    const updated = await apiAnnotations(photoId);
    expect(updated).toHaveLength(2);
    const updatedBodies = updated.map((a: any) => a.body).sort();
    expect(updatedBodies).toEqual(['round-1-edited', 'round-2']);
  });

  // ── Move + save / move + cancel ──

  test('should persist position change after move + save', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'moveable');

    // Grab the original target from API
    let annotations = await apiAnnotations(photoId);
    const originalTarget = annotations[0].target;

    // Edit mode: select, move, save
    await enterEditMode(page);
    await selectAnnotation(page);
    await dragAnnotation(page, { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 }, 0.1, 0.1);
    await clickSave(page);

    // Verify position changed on server
    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('moveable');
    expect(annotations[0].target).not.toEqual(originalTarget);
  });

  test('should revert position change after move + cancel', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'stay-put');

    // Grab the original target
    let annotations = await apiAnnotations(photoId);
    const originalTarget = annotations[0].target;

    // Edit mode: select, move, cancel
    await enterEditMode(page);
    await selectAnnotation(page);
    await dragAnnotation(page, { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 }, 0.15, 0.15);
    await clickCancel(page);

    // Position should be unchanged on server
    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('stay-put');
    expect(annotations[0].target).toEqual(originalTarget);
  });

  // ── Complex multi-step workflows ──

  test('should handle create → move → cancel → move → save → edit text → save', async ({ page }) => {
    const region = { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 };

    // Step 1: Create
    await enterDrawMode(page);
    await drawAnnotation(page, 'workflow-label', region);

    let annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    const targetAfterCreate = annotations[0].target;

    // Step 2: Move and cancel — position should revert
    await enterEditMode(page);
    await selectAnnotation(page, region);
    await dragAnnotation(page, region, 0.1, 0.1);
    await clickCancel(page);

    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations[0].target).toEqual(targetAfterCreate);

    // Step 3: Move and save — position should update
    await selectAnnotation(page, region);
    await dragAnnotation(page, region, -0.05, -0.05);
    await clickSave(page);

    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations[0].target).not.toEqual(targetAfterCreate);
    const targetAfterMove = annotations[0].target;

    // Step 4: Edit text only, save
    await selectAnnotation(page, region);
    await setLabel(page, 'workflow-renamed');
    await clickSave(page);

    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('workflow-renamed');
    // Target should be approximately the same (no move this time)
    expect(annotations[0].target).toEqual(targetAfterMove);
  });

  test('should handle multiple annotations: create, edit different ones, delete one', async ({ page }) => {
    const regionA = { x1: 0.1, y1: 0.15, x2: 0.3, y2: 0.35 };
    const regionB = { x1: 0.4, y1: 0.4, x2: 0.65, y2: 0.65 };
    const regionC = { x1: 0.7, y1: 0.15, x2: 0.9, y2: 0.35 };

    // Create three annotations in different spots
    await enterDrawMode(page);
    await drawAnnotation(page, 'alpha', regionA);
    await drawAnnotation(page, 'beta', regionB);
    await drawAnnotation(page, 'gamma', regionC);

    let annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(3);

    // Edit beta's label
    await enterEditMode(page);
    await selectAnnotation(page, regionB);
    expect(await editPanelValue(page)).toBe('beta');
    await setLabel(page, 'beta-v2');
    await clickSave(page);

    // Delete gamma
    await selectAnnotation(page, regionC);
    expect(await editPanelValue(page)).toBe('gamma');
    await clickDelete(page);

    // Verify: alpha unchanged, beta updated, gamma gone
    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(2);
    const bodies = annotations.map((a: any) => a.body).sort();
    expect(bodies).toEqual(['alpha', 'beta-v2']);
  });

  test('should survive: create → close → reopen → edit → cancel → edit → save → close → reopen → delete', async ({ page }) => {
    // Create
    await enterDrawMode(page);
    await drawAnnotation(page, 'resilient');

    // Close and reopen
    await closeViewer(page);
    await openViewer(page);

    // Edit label but cancel
    await enterEditMode(page);
    await selectAnnotation(page);
    expect(await editPanelValue(page)).toBe('resilient');
    await setLabel(page, 'nope');
    await clickCancel(page);

    // Verify cancel didn't persist
    let annotations = await apiAnnotations(photoId);
    expect(annotations[0].body).toBe('resilient');

    // Edit label and save this time
    await selectAnnotation(page);
    await setLabel(page, 'resilient-v2');
    await clickSave(page);

    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations[0].body).toBe('resilient-v2');

    // Close and reopen again
    await closeViewer(page);
    await openViewer(page);

    // Delete
    await enterEditMode(page);
    await selectAnnotation(page);
    expect(await editPanelValue(page)).toBe('resilient-v2');
    await clickDelete(page);

    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(0);
  });

  test('should handle rapid mode switching without breaking state', async ({ page }) => {
    // Create an annotation
    await enterDrawMode(page);
    await drawAnnotation(page, 'mode-test');

    // Rapidly switch modes
    await enterEditMode(page);
    await enterDrawMode(page);
    await enterEditMode(page);
    await enterDrawMode(page);
    await enterEditMode(page);

    // After all the switching, the annotation should still be selectable
    await selectAnnotation(page);
    expect(await editPanelValue(page)).toBe('mode-test');
    await clickCancel(page);

    // And still persisted
    const annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('mode-test');
  });

  test('should handle draw → cancel → draw → save cycle', async ({ page }) => {
    await enterDrawMode(page);

    // Draw and cancel
    const box = await canvasBox(page);
    await page.mouse.move(box.x + box.width * 0.3, box.y + box.height * 0.3);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.6, { steps: 10 });
    await page.mouse.up();
    await waitForEditPanel(page);
    await clickCancel(page);

    // Nothing persisted
    let annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(0);

    // Draw again and save this time
    await drawAnnotation(page, 'second-attempt');

    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('second-attempt');
  });

  test('should auto-save when clicking away from annotation in edit mode', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'auto-save-me');

    await enterEditMode(page);
    await selectAnnotation(page);
    await setLabel(page, 'auto-saved');

    // Click on empty area (far corner) instead of pressing Save
    const box = await canvasBox(page);
    await page.mouse.click(box.x + box.width * 0.95, box.y + box.height * 0.95);

    // Panel should close (auto-save on deselect)
    await expect(page.locator('[data-testid="osd-edit-body-panel"]')).not.toBeVisible({ timeout: 5000 });

    await page.waitForTimeout(1000);
    const annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('auto-saved');
  });

  test('should handle move + text change + save together', async ({ page }) => {
    const region = { x1: 0.3, y1: 0.3, x2: 0.6, y2: 0.6 };

    await enterDrawMode(page);
    await drawAnnotation(page, 'combo-test', region);

    let annotations = await apiAnnotations(photoId);
    const originalTarget = annotations[0].target;

    // Select, move, change text, save — all in one edit session
    await enterEditMode(page);
    await selectAnnotation(page, region);
    await dragAnnotation(page, region, 0.05, 0.05);
    await setLabel(page, 'combo-updated');
    await clickSave(page);

    await page.waitForTimeout(500);
    annotations = await apiAnnotations(photoId);
    expect(annotations).toHaveLength(1);
    expect(annotations[0].body).toBe('combo-updated');
    expect(annotations[0].target).not.toEqual(originalTarget);
  });

  test('should handle Escape key to cancel edit', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'escape-test');

    await enterEditMode(page);
    await selectAnnotation(page);
    await setLabel(page, 'should-not-persist');
    await page.keyboard.press('Escape');

    await expect(page.locator('[data-testid="osd-edit-body-panel"]')).not.toBeVisible({ timeout: 5000 });

    await page.waitForTimeout(500);
    const annotations = await apiAnnotations(photoId);
    expect(annotations[0].body).toBe('escape-test');
  });

  test('should handle Enter key to save edit', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'enter-test');

    await enterEditMode(page);
    await selectAnnotation(page);
    await setLabel(page, 'enter-saved');

    // Focus the input and press Enter
    await page.locator('[data-testid="osd-edit-body-input"]').focus();
    await page.keyboard.press('Enter');

    await expect(page.locator('[data-testid="osd-edit-body-panel"]')).not.toBeVisible({ timeout: 5000 });

    await page.waitForTimeout(500);
    const annotations = await apiAnnotations(photoId);
    expect(annotations[0].body).toBe('enter-saved');
  });

  // ── Label layout (canvas-rendered) ──

  /**
   * Read the resolved label draw commands exposed by the debug hook.
   * Returns an empty array if labels haven't rendered yet.
   */
  async function getLabelCmds(page: Page) {
    return page.evaluate(() => (window as any).__labelDebugCmds ?? []);
  }

  /**
   * Wait until __labelDebugCmds has at least `count` entries.
   * Labels are drawn on rAF after annotations sync, so we poll briefly.
   */
  async function waitForLabels(page: Page, count: number, timeoutMs = 5000) {
    await page.waitForFunction(
      (n) => ((window as any).__labelDebugCmds ?? []).length >= n,
      count,
      { timeout: timeoutMs },
    );
    return getLabelCmds(page);
  }

  test('labels appear for each annotation', async ({ page }) => {
    await enterDrawMode(page);
    await drawAnnotation(page, 'label-A', { x1: 0.2, y1: 0.2, x2: 0.4, y2: 0.4 });
    await drawAnnotation(page, 'label-B', { x1: 0.6, y1: 0.6, x2: 0.8, y2: 0.8 });

    const cmds = await waitForLabels(page, 2);
    expect(cmds).toHaveLength(2);
    const labels = cmds.map((c: any) => c.label).sort();
    expect(labels).toEqual(['label-A', 'label-B']);
  });

  test('labels on same edge do not overlap', async ({ page }) => {
    // Create 3 annotations near the left edge — all should assign to 'left'
    await enterDrawMode(page);
    await drawAnnotation(page, 'L1', { x1: 0.05, y1: 0.15, x2: 0.15, y2: 0.25 });
    await drawAnnotation(page, 'L2', { x1: 0.05, y1: 0.35, x2: 0.15, y2: 0.45 });
    await drawAnnotation(page, 'L3', { x1: 0.05, y1: 0.55, x2: 0.15, y2: 0.65 });

    const cmds = await waitForLabels(page, 3);
    expect(cmds).toHaveLength(3);

    // All should be on the left edge
    for (const cmd of cmds) {
      expect(cmd.edge).toBe('left');
    }

    // Sort by vertical position and check no bounding-box overlaps
    const sorted = [...cmds].sort((a: any, b: any) => a.ty - b.ty);
    for (let i = 1; i < sorted.length; i++) {
      const prev = sorted[i - 1];
      const curr = sorted[i];
      // Previous pill bottom must not exceed current pill top
      expect(prev.ty + prev.pillH).toBeLessThanOrEqual(curr.ty);
    }
  });

  test('labels stay within canvas bounds', async ({ page }) => {
    // Annotations near edges but away from toolbar to stress boundary clamping
    await enterDrawMode(page);
    await drawAnnotation(page, 'TL', { x1: 0.05, y1: 0.15, x2: 0.18, y2: 0.28 });
    await drawAnnotation(page, 'BR', { x1: 0.82, y1: 0.72, x2: 0.95, y2: 0.85 });

    const cmds = await waitForLabels(page, 2);
    expect(cmds).toHaveLength(2);

    // Read canvas dimensions
    const dims = await page.evaluate(() => {
      const c = document.querySelector('[data-testid="osd-label-canvas"]') as HTMLCanvasElement | null;
      return c ? { w: c.width, h: c.height } : null;
    });
    expect(dims).toBeTruthy();

    for (const cmd of cmds) {
      expect(cmd.tx).toBeGreaterThanOrEqual(0);
      expect(cmd.ty).toBeGreaterThanOrEqual(0);
      expect(cmd.tx + cmd.pillW).toBeLessThanOrEqual(dims!.w);
      expect(cmd.ty + cmd.pillH).toBeLessThanOrEqual(dims!.h);
    }
  });

  test('labels update after annotation is moved', async ({ page }) => {
    // Create annotation on the left side → label should be on left edge
    const regionLeft = { x1: 0.05, y1: 0.4, x2: 0.15, y2: 0.6 };
    await enterDrawMode(page);
    await drawAnnotation(page, 'mover', regionLeft);

    let cmds = await waitForLabels(page, 1);
    expect(cmds[0].edge).toBe('left');

    // Move annotation to the right side
    await enterEditMode(page);
    await selectAnnotation(page, regionLeft);
    await dragAnnotation(page, regionLeft, 0.7, 0);
    await clickSave(page);

    // Wait for label to re-render with updated position
    await page.waitForTimeout(500);
    cmds = await getLabelCmds(page);
    expect(cmds).toHaveLength(1);
    expect(cmds[0].edge).toBe('right');
  });

  // ── Cleanup ──

  // No afterEach needed — beforeEach calls recreateTestUsers() which
  // resets all state, and logs in fresh each time.
});
