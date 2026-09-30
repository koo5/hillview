# The photo outbox

**Anything the client would normally just call the API for, but which has to
survive being offline — or being said before the photo has ever reached the
server — is a row in `photo_outbox` saying what the client WANTS to be true.
One row per (account, photo, kind, item), replaced in place.**

Ratings and deletions ride it today. Tags, descriptions and voice notes are
the reason it is shaped this way rather than hard-wired to ratings.

Sibling of [upload-one-funnel.md](upload-one-funnel.md): the file drain sends
photos, this sends everything else about them, and both are steps of the same
worker.

## A row is a state, not a message

This is the decision everything else follows from.

An outbox of MESSAGES has to keep "liked 9:01, unliked 9:02, liked 9:03" in
order, send all three, and decide what to do when the middle one fails. An
outbox of STATES keeps one row saying "liked" and has one call to make.
Re-stating a wish overwrites it; sending it twice is harmless; order stops
being a thing that can be wrong.

It works because the APIs this feeds are idempotent by the same key a row is
keyed on — a rating is unique per user and photo, a description is a scalar,
a tag set is a set, a deletion is terminal. `itemId` carries the kinds that
are genuinely multi-valued, a voice note among several, where "removed" is
another state rather than another kind of record.

## Dirty is a comparison, and clearing it is a compare-and-set

`revision` rises on every local write; `syncedRevision` is what the server
last accepted. Dirty is `syncedRevision < revision`.

The pusher captures the revision it is about to send and clears only that one
(`markSynced ... AND revision = :sentRevision`). An edit made while the
request is in flight has already moved the revision, so the row stays dirty
instead of being called clean for a value the server never saw.

Timestamps cannot do this. Two taps inside one millisecond, or a clock that
steps, and the comparison silently stops discriminating. The revision is a
counter precisely so it cannot.

## Keyed by account, never purged

`userId` — the access token's `sub`, decoded but never verified, because it
partitions local rows and makes no authorization decision — is part of the
key. Signing out leaves every row alone. They are simply not eligible while
someone else is signed in, and they resume if that account returns. A like
queued as one account can never leave as another.

## Two gates, no dependency graph

- **Has the server ever seen this photo?** `getPushable` joins `photos` and
  requires `serverPhotoId`. A wish about a photo that has not been uploaded
  is not an error and not a queued dependency; it is simply not selected. The
  upload lands the id and the next pass picks it up.
- **Is it due?** Backoff lives in Kotlin (`isDueNow`), as it does for the
  file drain: SQL says what is owed, Kotlin says what is due.

## Deletion, which is the asymmetric one

`PhotoEntity.deleted` is what the SERVER says — an observation. A wanted
deletion is a row here — an intention. They are deliberately not the same
field, because a status sync reporting "not deleted" would otherwise cancel a
deletion the user asked for while offline.

The requirement is that a deleted photo either never uploads, or is deleted
as soon as it lands. Three cases, and only the third is interesting:

| when the user asks | what happens |
| --- | --- |
| never uploaded | the candidate queries exclude it (the `NOT EXISTS` on this table), so the file is never offered to the drain at all |
| already uploaded | an ordinary outbox row, pushed like a rating |
| mid-upload | the bytes cannot be recalled, so it is a POST-CONDITION: the instant the upload writes `serverPhotoId`, `PhotoOutboxPusher.afterUpload` deletes on the far side |

Note the upload gate asks what is WANTED, not what is pending: a deletion
already accepted by the server still keeps the photo out of the queue.

Withdrawing a deletion only means anything before it is pushed. After that
there is nothing to take back, and the row stays as the record that it
happened.

## Adding a kind

1. A `OUTBOX_KIND_*` constant and the JSON shape it puts in `valueJson`.
2. A branch in `PhotoOutboxPusher.push`, returning true only when the server
   is in the wanted state — including the cases where it already was (a 404
   on a withdrawal is success, not failure).
3. A wish-setter and a read-back on `PhotoOutbox`. The read-back is not
   optional: the UI has to show what the user said the instant they said it,
   which is hours before the server hears about it.

An unknown kind is left alone rather than dropped, so a row written by a
newer version survives a downgrade.

## Auditing it

```bash
# only PhotoOutbox may write wishes; only the pusher may clear them
grep -rn "outboxDao()" frontend2 shared-kt --include=*.kt | grep -v Test
```
