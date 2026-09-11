"""Sequence synthesis: split each owner's eligible photos into time-gap sessions
and persist them as panoramax.sequences / sequence_photos.

Why synthesized persisted sequences (not one ever-growing collection per user):
the meta-catalog's incremental sync is collection-level — any change re-fetches
ALL items of the collection — so giant collections are an unbounded recurring
harvest cost. Sessions split on a capture-time gap (~3h default, env-tunable).
No distance split: the catalog only draws lines between consecutive items <75m
apart, so sparse sequences just render as dots.

The run is a full deterministic recompute diffed against stored state, applying
only actual changes (so sequences.updated_at — the harvester's crawl signal,
bumped by the membership triggers — moves only when membership really changed).
Photos have no updated-at column to drive a cheaper incremental pass, and the
diff makes the recompute idempotent anyway. Stability rules:

- A session keeps the UUID of the existing sequence it overlaps most (greedy,
  larger overlap first; ties break on session order). Brand-new sessions get
  fresh UUIDs — real UUIDs, the catalog casts collection ids to UUID PKs.
- A sequence whose photos all left (deleted / hidden / license flip / gap
  merge) loses its membership rows; the membership trigger tombstones it
  (status='deleted'). Tombstones are never hard-deleted and revive if the
  sequencer repopulates them.
- Revival actually finds the tombstone: the membership trigger records the
  last sequence of every departed photo in panoramax.departed_photos, and
  identity overlap counts those too (live membership wins). So a user deactivated and reactivated, or a photo flagged
  and un-flagged, comes back under the same collection uuid instead of a new
  one the catalog would have to drop and re-harvest.
"""
import argparse
import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from eligibility import ELIGIBLE_PHOTO_WHERE, PHOTO_ORDER_BY
from settings import Scope, active_scope, sequencer_interval_s, session_gap_hours

logger = logging.getLogger('panoramax.sequencer')


@dataclass(frozen=True)
class PhotoStub:
	id: str
	owner_id: str
	effective_at: datetime


@dataclass(frozen=True)
class Membership:
	photo_id: str
	sequence_id: str
	rank: int


def split_sessions(photos: list[PhotoStub], gap: timedelta) -> list[list[PhotoStub]]:
	"""Split an owner's capture-ordered photos wherever consecutive effective_at
	differ by more than `gap`."""
	sessions: list[list[PhotoStub]] = []
	current: list[PhotoStub] = []
	prev_at: datetime | None = None
	for photo in photos:
		if prev_at is not None and photo.effective_at - prev_at > gap:
			sessions.append(current)
			current = []
		current.append(photo)
		prev_at = photo.effective_at
	if current:
		sessions.append(current)
	return sessions


def assign_sequence_ids(
	sessions: list[list[PhotoStub]],
	existing_seq_of_photo: dict[str, str],
) -> list[tuple[str, list[PhotoStub]]]:
	"""Give each session a stable sequence UUID.

	Overlap counting is against current membership; the greedy pass hands each
	existing sequence to the single session overlapping it most, so a session
	that swallowed two sequences (a gap closed) keeps the bigger one's identity
	and the other tombstones.
	"""
	overlaps: list[tuple[int, int, str]] = []  # (overlap, session_idx, seq_id)
	for idx, session in enumerate(sessions):
		counts: dict[str, int] = {}
		for photo in session:
			seq = existing_seq_of_photo.get(photo.id)
			if seq:
				counts[seq] = counts.get(seq, 0) + 1
		for seq, count in counts.items():
			overlaps.append((count, idx, seq))
	# larger overlap first; deterministic tie-break on (session order, seq id)
	overlaps.sort(key=lambda t: (-t[0], t[1], t[2]))

	assigned: dict[int, str] = {}
	used_seqs: set[str] = set()
	for count, idx, seq in overlaps:
		if idx in assigned or seq in used_seqs:
			continue
		assigned[idx] = seq
		used_seqs.add(seq)

	result = []
	for idx, session in enumerate(sessions):
		seq_id = assigned.get(idx) or str(uuid.uuid4())
		result.append((seq_id, session))
	return result


def identity_map(
	live: dict[str, str], former: dict[str, str],
) -> dict[str, str]:
	"""photo -> sequence used for overlap counting: live membership first,
	then the sequence a photo last belonged to (departed_photos), so an
	emptied sequence can be recognised when its photos come back."""
	merged = dict(former)
	merged.update(live)
	return merged


def desired_memberships(
	assigned_sessions: list[tuple[str, list[PhotoStub]]],
) -> list[Membership]:
	out = []
	for seq_id, session in assigned_sessions:
		for rank, photo in enumerate(session, start=1):
			out.append(Membership(photo_id=photo.id, sequence_id=seq_id, rank=rank))
	return out


def diff_memberships(
	current: list[Membership], desired: list[Membership]
) -> tuple[list[Membership], list[Membership], list[str]]:
	"""-> (to_insert, to_update, photo_ids_to_delete). Only actual changes, so
	an unchanged owner produces zero writes and zero updated_at churn."""
	current_by_photo = {m.photo_id: m for m in current}
	desired_by_photo = {m.photo_id: m for m in desired}
	to_insert = [m for pid, m in desired_by_photo.items() if pid not in current_by_photo]
	to_update = [
		m for pid, m in desired_by_photo.items()
		if pid in current_by_photo and current_by_photo[pid] != m
	]
	to_delete = [pid for pid in current_by_photo if pid not in desired_by_photo]
	return to_insert, to_update, to_delete


async def run_once(engine: AsyncEngine, scope: Scope | None = None, gap: timedelta | None = None) -> dict:
	"""One full synthesis pass. Returns counters for logging/tests."""
	scope = scope or active_scope()
	gap = gap or timedelta(hours=session_gap_hours())

	async with engine.begin() as conn:
		rows = (await conn.execute(text(f"""
			SELECT p.id, p.owner_id, p.effective_at
			FROM photos p
			JOIN users u ON u.id = p.owner_id
			WHERE {ELIGIBLE_PHOTO_WHERE}
			ORDER BY p.owner_id, {PHOTO_ORDER_BY}
		"""), {'scope_legal_rights': scope.legal_rights})).all()
		photos = [PhotoStub(id=r[0], owner_id=r[1], effective_at=r[2]) for r in rows]

		rows = (await conn.execute(text("""
			SELECT sp.photo_id, sp.sequence_id, sp.rank, s.owner_id
			FROM panoramax.sequence_photos sp
			JOIN panoramax.sequences s ON s.id = sp.sequence_id
			WHERE s.scope = :scope
		"""), {'scope': scope.id})).all()
		current = [Membership(photo_id=r[0], sequence_id=str(r[1]), rank=r[2]) for r in rows]

		rows = (await conn.execute(text("""
			SELECT d.photo_id, d.sequence_id
			FROM panoramax.departed_photos d
			JOIN panoramax.sequences s ON s.id = d.sequence_id
			WHERE s.scope = :scope
		"""), {'scope': scope.id})).all()
		former_seq_of_photo = {r[0]: str(r[1]) for r in rows}

		existing_seq_ids = {m.sequence_id for m in current} | set(former_seq_of_photo.values())
		existing_seq_of_photo = identity_map(
			{m.photo_id: m.sequence_id for m in current}, former_seq_of_photo)

		# per-owner sessions -> globally desired memberships
		desired: list[Membership] = []
		new_sequences: list[tuple[str, str]] = []  # (seq_id, owner_id)
		by_owner: dict[str, list[PhotoStub]] = {}
		for photo in photos:
			by_owner.setdefault(photo.owner_id, []).append(photo)
		for owner_id, owner_photos in by_owner.items():
			sessions = split_sessions(owner_photos, gap)
			assigned = assign_sequence_ids(sessions, existing_seq_of_photo)
			for seq_id, session in assigned:
				if seq_id not in existing_seq_ids:
					new_sequences.append((seq_id, owner_id))
			desired.extend(desired_memberships(assigned))

		to_insert, to_update, to_delete = diff_memberships(current, desired)

		for seq_id, owner_id in new_sequences:
			await conn.execute(text("""
				INSERT INTO panoramax.sequences (id, scope, status, owner_id)
				VALUES (:id, :scope, 'ready', :owner_id)
			"""), {'id': uuid.UUID(seq_id), 'scope': scope.id, 'owner_id': owner_id})

		# rank-unique is DEFERRABLE INITIALLY DEFERRED, so delete/update/insert
		# order inside this transaction can't collide transiently
		if to_delete:
			await conn.execute(
				text("DELETE FROM panoramax.sequence_photos WHERE photo_id = ANY(:pids)"),
				{'pids': to_delete})
		for m in to_update:
			await conn.execute(text("""
				UPDATE panoramax.sequence_photos
				SET sequence_id = :seq, rank = :rank
				WHERE photo_id = :pid
			"""), {'seq': uuid.UUID(m.sequence_id), 'rank': m.rank, 'pid': m.photo_id})
		for m in to_insert:
			await conn.execute(text("""
				INSERT INTO panoramax.sequence_photos (photo_id, sequence_id, rank)
				VALUES (:pid, :seq, :rank)
			"""), {'pid': m.photo_id, 'seq': uuid.UUID(m.sequence_id), 'rank': m.rank})

	counters = {
		'eligible_photos': len(photos),
		'sequences_created': len(new_sequences),
		'memberships_inserted': len(to_insert),
		'memberships_updated': len(to_update),
		'memberships_deleted': len(to_delete),
	}
	if any(v for k, v in counters.items() if k != 'eligible_photos'):
		logger.info("sequencer pass: %s", counters)
	else:
		logger.debug("sequencer pass: no changes (%d eligible photos)", len(photos))
	return counters


async def wait_for_schema(engine: AsyncEngine) -> None:
	"""The api container applies migration 030 in its prestart; this container
	may win the race, so poll instead of crashing."""
	while True:
		try:
			async with engine.connect() as conn:
				present = (await conn.execute(
					text("SELECT to_regclass('panoramax.sequences')"))).scalar()
			if present:
				return
			logger.warning("panoramax schema not migrated yet, waiting…")
		except Exception as e:
			logger.warning("database not reachable yet (%s), waiting…", e)
		await asyncio.sleep(5)


async def loop(engine: AsyncEngine) -> None:
	await wait_for_schema(engine)
	interval = sequencer_interval_s()
	while True:
		try:
			await run_once(engine)
		except Exception:
			logger.exception("sequencer pass failed")
		await asyncio.sleep(interval)


def main() -> None:
	parser = argparse.ArgumentParser(description="Panoramax sequence synthesizer")
	parser.add_argument('--once', action='store_true', help="run a single pass and exit")
	args = parser.parse_args()
	logging.basicConfig(level=logging.INFO)

	from db import get_engine
	engine = get_engine()
	if args.once:
		asyncio.run(run_once(engine))
	else:
		asyncio.run(loop(engine))


if __name__ == '__main__':
	main()
