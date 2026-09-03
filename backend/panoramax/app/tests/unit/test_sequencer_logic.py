"""Pure-logic tests for session splitting, sequence identity assignment and
membership diffing — the sequencer's correctness core, no DB involved."""
import uuid
from datetime import datetime, timedelta

from sequencer import (
	identity_map,
	Membership,
	PhotoStub,
	assign_sequence_ids,
	desired_memberships,
	diff_memberships,
	split_sessions,
)

GAP = timedelta(hours=3)
T0 = datetime(2026, 7, 1, 8, 0, 0)


def stub(i: int, at: datetime, owner: str = 'owner1') -> PhotoStub:
	return PhotoStub(id=f'photo-{i}', owner_id=owner, effective_at=at)


class TestSplitSessions:
	def test_empty(self):
		assert split_sessions([], GAP) == []

	def test_single_photo(self):
		photos = [stub(1, T0)]
		assert split_sessions(photos, GAP) == [photos]

	def test_no_split_within_gap(self):
		photos = [stub(i, T0 + timedelta(hours=i)) for i in range(4)]
		assert split_sessions(photos, GAP) == [photos]

	def test_split_beyond_gap(self):
		morning = [stub(1, T0), stub(2, T0 + timedelta(minutes=10))]
		evening = [stub(3, T0 + timedelta(hours=9)), stub(4, T0 + timedelta(hours=9, minutes=5))]
		assert split_sessions(morning + evening, GAP) == [morning, evening]

	def test_exactly_gap_does_not_split(self):
		photos = [stub(1, T0), stub(2, T0 + GAP)]
		assert split_sessions(photos, GAP) == [photos]

	def test_just_over_gap_splits(self):
		photos = [stub(1, T0), stub(2, T0 + GAP + timedelta(seconds=1))]
		assert split_sessions(photos, GAP) == [[photos[0]], [photos[1]]]

	def test_multiple_splits(self):
		days = [[stub(10 * d + i, T0 + timedelta(days=d, minutes=i)) for i in range(2)]
			for d in range(3)]
		flat = [p for day in days for p in day]
		assert split_sessions(flat, GAP) == days


class TestAssignSequenceIds:
	def test_new_sessions_get_fresh_valid_uuids(self):
		sessions = split_sessions([stub(1, T0), stub(2, T0 + timedelta(hours=9))], GAP)
		assigned = assign_sequence_ids(sessions, {})
		assert len(assigned) == 2
		ids = [seq_id for seq_id, _ in assigned]
		assert len(set(ids)) == 2
		for seq_id in ids:
			uuid.UUID(seq_id)  # must be real UUIDs — catalog casts to UUID PKs

	def test_unchanged_session_keeps_sequence_id(self):
		photos = [stub(1, T0), stub(2, T0 + timedelta(minutes=5))]
		existing = {p.id: 'seq-A' for p in photos}
		assigned = assign_sequence_ids([photos], existing)
		assert assigned == [('seq-A', photos)]

	def test_growing_session_keeps_sequence_id(self):
		old = [stub(1, T0), stub(2, T0 + timedelta(minutes=5))]
		new_photo = stub(3, T0 + timedelta(minutes=10))
		existing = {p.id: 'seq-A' for p in old}
		assigned = assign_sequence_ids([old + [new_photo]], existing)
		assert assigned[0][0] == 'seq-A'

	def test_gap_close_merge_keeps_bigger_sequence(self):
		# two sequences whose photos now fall into one session (e.g. gap config
		# raised): the one contributing more photos keeps its identity
		a = [stub(i, T0 + timedelta(minutes=i)) for i in range(3)]
		b = [stub(10 + i, T0 + timedelta(hours=1, minutes=i)) for i in range(2)]
		existing = {p.id: 'seq-A' for p in a} | {p.id: 'seq-B' for p in b}
		assigned = assign_sequence_ids([a + b], existing)
		assert assigned[0][0] == 'seq-A'

	def test_session_split_bigger_part_keeps_id(self):
		# a sequence split in two (photos removed in the middle): the larger
		# fragment keeps the id, the smaller gets a fresh one
		big = [stub(i, T0 + timedelta(minutes=i)) for i in range(3)]
		small = [stub(10, T0 + timedelta(hours=9))]
		existing = {p.id: 'seq-A' for p in big + small}
		assigned = assign_sequence_ids([big, small], existing)
		assert assigned[0][0] == 'seq-A'
		assert assigned[1][0] != 'seq-A'
		uuid.UUID(assigned[1][0])

	def test_equal_overlap_tie_breaks_on_session_order(self):
		a = [stub(1, T0)]
		b = [stub(2, T0 + timedelta(hours=9))]
		existing = {'photo-1': 'seq-A', 'photo-2': 'seq-A'}
		assigned = assign_sequence_ids([a, b], existing)
		# seq-A goes to the first session; second gets a new id
		assert assigned[0][0] == 'seq-A'
		assert assigned[1][0] != 'seq-A'


class TestDiffMemberships:
	def m(self, pid: str, seq: str, rank: int) -> Membership:
		return Membership(photo_id=pid, sequence_id=seq, rank=rank)

	def test_no_change(self):
		cur = [self.m('p1', 's1', 1), self.m('p2', 's1', 2)]
		ins, upd, dele = diff_memberships(cur, list(cur))
		assert (ins, upd, dele) == ([], [], [])

	def test_insert_update_delete(self):
		cur = [self.m('p1', 's1', 1), self.m('p2', 's1', 2), self.m('p3', 's1', 3)]
		# p2 gone -> p3 moves up, p4 appended
		desired = [self.m('p1', 's1', 1), self.m('p3', 's1', 2), self.m('p4', 's1', 3)]
		ins, upd, dele = diff_memberships(cur, desired)
		assert ins == [self.m('p4', 's1', 3)]
		assert upd == [self.m('p3', 's1', 2)]
		assert dele == ['p2']

	def test_sequence_move_is_update(self):
		cur = [self.m('p1', 's1', 1)]
		desired = [self.m('p1', 's2', 1)]
		ins, upd, dele = diff_memberships(cur, desired)
		assert (ins, dele) == ([], [])
		assert upd == [self.m('p1', 's2', 1)]


class TestDesiredMemberships:
	def test_ranks_are_one_based_per_sequence(self):
		s1 = [stub(1, T0), stub(2, T0 + timedelta(minutes=1))]
		s2 = [stub(3, T0 + timedelta(hours=9))]
		out = desired_memberships([('seq-A', s1), ('seq-B', s2)])
		assert [(m.sequence_id, m.rank) for m in out] == [
			('seq-A', 1), ('seq-A', 2), ('seq-B', 1)]


class TestIdentityMap:
	def test_live_membership_wins_over_former(self):
		m = identity_map({'p1': 'live-seq'}, {'p1': 'old-seq', 'p2': 'old-seq'})
		assert m == {'p1': 'live-seq', 'p2': 'old-seq'}

	def test_emptied_sequence_revives_under_its_own_id(self):
		# all of a sequence's photos left (owner deactivated); when they come
		# back as one session, overlap via former_photo_ids must pick the
		# tombstone's id rather than minting a fresh uuid
		photos = [stub(1, T0), stub(2, T0 + timedelta(minutes=1)), stub(3, T0 + timedelta(minutes=2))]
		former = {p.id: 'tomb' for p in photos}
		assigned = assign_sequence_ids([photos], identity_map({}, former))
		assert assigned[0][0] == 'tomb'

	def test_former_membership_cannot_steal_a_live_sequence(self):
		# seq A is live with photos 1-3; photo 4 once belonged to A but now sits
		# in its own far-away session: A goes to the bigger overlap, 4 gets a
		# fresh id
		live = {'photo-1': 'A', 'photo-2': 'A', 'photo-3': 'A'}
		former = {'photo-4': 'A'}
		big = [stub(1, T0), stub(2, T0 + timedelta(minutes=1)), stub(3, T0 + timedelta(minutes=2))]
		lone = [stub(4, T0 + timedelta(days=30))]
		assigned = assign_sequence_ids([lone, big], identity_map(live, former))
		by_first = {session[0].id: seq for seq, session in assigned}
		assert by_first['photo-1'] == 'A'
		assert by_first['photo-4'] != 'A'
