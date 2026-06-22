# Content licensing model — photos and annotations

## Context

Hillview's content (photos and annotations) is **bi-licensed** at the per-artifact
level. The contributor chooses, for each piece of content they create, between:

- **`full1`** — full dedication to the Hillview project. Contributor retains
  copyright; grants the Hillview project broad rights including the right to
  include the content in paid / restricted-access tiers in the future.
- **`CC`** — commons-compatible. The exact CC variant is the current Hillview
  default (`CC BY-SA 4.0 + OSM grant` for photos; the equivalent for
  annotations). Compatible with Panoramax / OSM-style downstream redistribution.

Both choices are first-class. Hillview deliberately wants a mix:

- `CC` content keeps Hillview commons-aligned, allows downstream contribution to
  open ecosystems (Panoramax, OSM, Wikidata), and earns goodwill in those spaces.
- `full1` content is the **anchor for any future monetization** (paid tiers,
  pack sales, etc.). Without `full1` content existing from day 1, Hillview can
  never paywall anything without retroactively changing terms — the 27crags
  trap, which this design explicitly avoids.

This avoids the trap by being honest from day 1: users who choose `full1` know
their contribution may be paywalled later; users who choose `CC` know theirs
won't be.

## Defaults

- **Photos**: default `CC`. Most contributors are expected to leave the default
  and contribute openly; the strategic asset on the photo side is the open
  commons.
- **Annotations**: default `full1`. Annotations are the curated knowledge layer
  and are where most of the platform's long-term commercial value sits;
  defaulting closed protects this without preventing opt-in openness.

These defaults are deliberately asymmetric. The asymmetry should be explained
on the license-selector UI so it doesn't read as arbitrary — one sentence per
direction is enough ("photos default open because their value is in the commons;
annotations default project-dedicated because their value is in the curated
knowledge layer").

A user's selected license becomes their **sticky preference** and applies to all
future content they create, on any device (see "Preference sync" below). The
preference can be flipped at any time and affects only content created *after*
the flip.

## Where the license is selected (UX)

- **Photo upload**: license toggle visible at upload time. The selector shows
  the current value, lets the user change it, and surfaces the meaning of each
  option in plain language.
- **Annotation editor**: license icon inside the annotation edit popup. Tooltip
  or expanded explanation shows what each option means, including the paywall
  intent for `full1`.

The user-facing copy must be plain and direct, not legalese:

- `full1`: "You keep your copyright. Hillview may include this in paid tiers
  later to support development. Choose this to support the project."
- `CC`: "Anyone can reuse this under [CC BY-SA + OSM grant / equivalent].
  Choose this to contribute to the open commons."

A short link to a longer policy page should sit under both options.

## License-lock rules

The license on a piece of content can be changed by the **original creator
(first actual content contributor)** as long as no other user has contributed
to it. Once another user contributes, the license is **locked** and cannot be
changed.

Both directions are allowed while the content is still single-author:
`full1` → `CC` and `CC` → `full1`. This trusts the original author with full
flexibility over their own content while they're its sole contributor; the
moment someone else builds on it, the license becomes a contract that other
contributors have relied on, and locking it preserves that trust.

### What counts as "contribution by another user"

For an **annotation chain**: any other user submitting a row that edits body
or target. Admin approval / rejection of a pending row is not a contribution
(it's a moderation action). View / rate / flag are not contributions.

For a **photo**: photos aren't text-edited so "another user builds on it" is
not really a meaningful event. The license on a photo is changeable by its
owner at any time, but changes are **forward-only** — they do not retroactively
un-authorize past uses. A `full1` photo already included in a paid pack stays
in that pack; a future flip to `CC` only affects subsequent inclusion decisions.

### Locked state

Once locked, the license cannot be changed by anyone (including admin) without
an explicit out-of-band process. v1 has no such process. If a genuine mistake
needs correction, manual DB intervention by Jindřich is the escape valve. Not
worth UI for.

### Hard-delete and license lock

Rejected annotation submissions are hard-deleted (per
`annotation-admin-queue.md`). A hard-deleted contribution does *not* count
toward license-lock — the chain history is what currently exists, not what
ever existed. So if user B's contribution to A's chain is hard-deleted by
admin, A regains the ability to change the license.

This has a theoretical gaming vector ("invite B to submit garbage so admin
deletes it, freeing you up"), but the original creator can already change the
license freely while sole contributor, so there's no real attack.

## First-filler rule (annotations)

Blank markers — an annotation with a target (rectangle / shape) but no body
text — do not yet have a license. The rectangle-creator has contributed
*target* but not *content*. The license is claimed by the **first user to
submit a non-empty body** for that chain.

From the perspective of license-lock, the body-filler is treated as the
original creator. Subsequent users editing body or target are "other
contributors" and trigger the lock.

Trivial / edge cases:

- A user submits empty-body chain → no license claimed yet, blank marker state
  persists.
- A user submits non-empty body → license claimed at submission. (If they're
  untrusted and the row goes through moderation, the claim is provisional
  until approval; see "Interaction with admin queue" below.)
- Rectangle-creator and first body-filler are different users → license is
  claimed by body-filler. Rectangle-creator's subsequent edit of target
  triggers license-lock (they're now a second contributor relative to the
  body-filler).

## Cross-device preference sync

The user's license preference is persisted on their user profile (backend),
not in localStorage. New devices and new browser sessions read the preference
from the profile. Changing the preference on any device propagates to the
profile.

**Critical**: changing the preference on one device must not affect
already-submitted content (including pending submissions) on another device.
The preference applies only to *new* content created after the change.

## User-facing communication of paywall intent

The 27crags lesson is that surprise retroactive paywalling destroys trust,
even when permitted by terms. The mitigation here is *proactive, repeated*
communication that `full1` content may be paywalled in the future:

1. **At first interaction with the license toggle**: tooltip text says it
   plainly. This is the primary touchpoint; do not bury it.
2. **Reminder popup** after ~15 `full1` submissions (or comparable engagement
   threshold — exact trigger TBD): "Thanks for contributing to Hillview's
   project-dedicated corpus. As a reminder, this content may be included in
   future paid tiers to fund development. Switch to CC at any time if you
   prefer your content stay openly licensed."
3. **Per-user visible state**: the user's annotations / photos list should
   show a small license indicator on each item, so users can always see at a
   glance what they've contributed under what license.
4. **In contributor onboarding / docs**: the policy lives on a clearly-linked
   page, visible from the license toggle tooltip and from account settings.

The principle: a user who later says "I didn't realize" should be wrong; the
information should have been in front of them multiple times.

## Interaction with the annotation admin queue

Per `annotation-admin-queue.md`, untrusted users' submissions go through
moderation. License interaction:

- License is **claimed at submission time** (stored on the pending row).
- On approval: license sticks with the annotation chain as set.
- On rejection (hard delete): the license claim disappears with the row.
  Anyone else can later submit a body fill with their own license choice.

### Race between pending untrusted submission and trusted edit

If user A (untrusted) submits a pending `CC` body fill on a previously-blank
marker, and *before A's approval* user B (trusted) submits a non-trivial body
fill with `full1`, the trusted edit applies immediately and claims the
license as `full1`. When admin reviews A's pending row, the chain is no
longer blank — admin reviews A's submission as an edit to a `full1` chain.
A's license preference is moot because the chain is already licensed.

This is consistent with the broader rule: license is claimed by the first
*effective* body-fill, where "effective" means landing in the live chain.
Pending rows that never make it into the chain claim nothing.

## Anti-gaming

The plausible gaming pattern: user A creates `full1` annotation, later wants
it as `CC`; deletes and recreates with `CC` preference active.

Mitigations:

- **Only the original creator and admin can delete an annotation.** Regular
  users cannot delete each other's contributions. This neutralizes the
  cross-user version of the attack.
- **For self-deletion-and-recreate**: while the user is sole contributor,
  this is legal — they can just change the license directly, so no need to
  go through delete-and-recreate. If they delete-and-recreate on a chain
  someone else has contributed to (locked), the new annotation has a
  different chain (`root_id`), and the old chain's history is gone (which
  affects sightline integrity). This is detectable abuse and falls under
  the general vandalism policy.
- **Bulk re-license attempts**: a user with strong preference shift trying
  to relicense their entire history en masse. Detectable from access logs;
  if needed, rate-limit license-change actions per user per day.

The general principle: don't over-engineer technical protection against an
attack pattern that has trivial alternatives (just change the license
directly while sole contributor). Treat real abuse as vandalism per
existing policies.

## Out of scope / acknowledged future work

- **Concurrent edits across users**: a general collaborative-editing problem,
  not specific to licensing. Unlikely to occur in practice given current
  scale. UI for conflict resolution will be designed when it actually
  matters. Until then, last-write-wins per existing behaviour.
- **License-locked content escape hatch**: no UI path to relicense
  contributor-locked content. Manual DB intervention by Jindřich is the
  escape valve in genuine cases.
- **License history audit log**: each license change isn't logged in v1.
  Add `content_license_changes` table later if disputes warrant.
- **Separate visibility for `full1` vs `CC` content**: in v1, both display
  identically. A future paywall implementation would gate `full1` content
  for non-subscribers.
- **Bulk export differentiation**: the bulk export commitment from the
  licensing-model discussion may need to surface only `CC` content (since
  `full1` content is project-dedicated and shouldn't necessarily leak in
  bulk exports). Decide closer to actual export implementation.

## Definition of done

- [ ] Schema: photo and annotation rows carry an explicit license identifier
      (photos already have `legal_rights`; annotations need an equivalent
      column).
- [ ] User profile carries `default_content_license` preference, with sync
      across devices.
- [ ] Upload flow honours per-photo selection, defaults to user preference,
      falls back to system default if no preference set.
- [ ] Annotation editor surfaces license toggle; honours user preference;
      applies first-filler rule for previously-blank chains.
- [ ] License-lock rule enforced: original creator can change while sole
      contributor; locked once another user contributes.
- [ ] License change is forward-only on photos (does not retroactively
      un-authorize past uses).
- [ ] User-facing copy on license selector explains `full1` paywall intent
      plainly at first contact.
- [ ] Reminder popup at engagement threshold (default 15 `full1` submissions;
      configurable).
- [ ] User's content listing pages show per-item license indicator.
- [ ] Tests: license-lock transitions, first-filler rule edge cases,
      preference sync, race between pending untrusted submission and trusted
      edit.
