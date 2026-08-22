-- Mirror Hillview's photos.terrain_overlay so the workbench can see which
-- overlays have LANDED.
--
-- Graduation here has no acknowledgement channel by design: the workbench
-- never learns that a package was applied, it observes that the values
-- changed (same as body text, same as annotation rects). For terrain
-- overlays the observable is this column — the graduation view compares the
-- approved hv:terrainOverlayFit against mirrored terrain_overlay->'fit' and
-- moves the item to "landed" when they match.
--
-- Only `fit` is compared, never the whole document: the baked skyline is a
-- function of the render (which may be re-rendered at a different grid) and
-- hillview-side fine-tuning lands in `user_adjust`, so comparing more than
-- the fit would resurrect settled items forever.
--
-- Existing mirror rows stay NULL until the next reconcile re-reads them.

ALTER TABLE photo_mirror ADD COLUMN IF NOT EXISTS terrain_overlay jsonb;
