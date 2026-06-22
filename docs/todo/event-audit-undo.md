# Annotation event audit + undo (lightweight moderation)

## Context

The full annotation admin-approval queue (`annotation-admin-queue.md`) is the
right design for a contributor scale we don't currently have. At present scale
(zero to a handful of untrusted contributors), preventive moderation is
overengineered. Reactive moderation is sufficient.

This task is the reactive-moderation alternative: an admin event-log page with
per-event undo buttons. Free-for-all annotation editing continues; when
something bad happens, admin sees it in the log and reverts it.

## Design intent

- Free-for-all annotation editing continues (unchanged from current behaviour).
- Every annotation change is already an append-only event in
  `photo_annotations` (rows with `event_type` and `superseded_by` chain
  pointers).
- An admin-only page lists recent events in reverse-chronological order, with
  filters (by photo, by user, by event type, by date range).
- Each event has an "undo" button that creates a new event restoring prior
  state. The append-only history is preserved — undo doesn't hard-delete.

The data model needs no change. This is a UI feature plus a small backend
endpoint set.

## Undo semantics (append-only)

For each event type, "undo" produces a new event that restores prior state:

- **Undo a `created` event** → new `deleted` event for the same chain.
- **Undo an `updated` event** → new `updated` event with the body/target of
  the row that was superseded.
- **Undo a `deleted` event** → new `created` (or restored) event with the
  body/target of the last live row before deletion.

The undo event records `reviewed_by=admin.id` (or a similar field) so the
audit trail captures *who* reverted *what* and *when*. The annotation chain's
history is fully reconstructable from the event log.

## Pages and endpoints

Backend:
- `GET /api/admin/annotation-events?limit=N&offset=M&filters...` — paginated
  list. Restricted to ADMIN / MODERATOR.
- `POST /api/admin/annotation-events/{id}/undo` — performs the undo as
  described.

Frontend:
- `/admin/annotation-events` page — list view with filters and per-row undo
  button. Each row shows: timestamp, user, photo thumbnail, event type, brief
  body/target preview, undo button.
- Visible only to admin / moderator role. Hidden from regular users in
  navigation.

## Non-goals (v1)

- Trust scoring, auto-promotion, untrusted-user queues — all deferred to the
  heavy admin-queue plan, triggered if/when audit-and-undo proves insufficient.
- Per-user "rollback all changes by this user since X" mass action. Wait for
  it to be needed.
- Notifications to users whose changes were undone. Maybe later; for now,
  silent revert + admin can manually message if escalation needed.
- Permanent rejection log distinct from the undo events themselves.

## Migration / upgrade path

If at some point an untrusted contributor (or several) generates enough
problematic edits that audit-and-undo becomes a burden, the heavy admin queue
(`annotation-admin-queue.md`) is the upgrade path. The audit-and-undo page
stays — it complements the queue rather than being replaced by it (audit-log
view is useful even with preventive moderation in place).

## Definition of done

- [ ] Admin events list endpoint with filters.
- [ ] Undo endpoint with the three undo-semantic cases.
- [ ] Admin-only `/admin/annotation-events` page in frontend.
- [ ] Hidden from non-admin users in navigation.
- [ ] Tests: each undo type produces the correct restored state; audit trail
      captures the reverting admin.
