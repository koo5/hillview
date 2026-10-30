"""The /dev/suspicious rules, on synthetic sequences shaped like the cases found
in a 2026-10-30 mirror of prod (13.2 km in 8 s with an identical longitude,
5.7 km in 3 s, plain walks and trips that must stay quiet)."""
from datetime import datetime, timedelta

from dev_report import Member, analyze, photo_findings, render, summarize

T0 = datetime(2026, 1, 21, 15, 58, 27)
NOW = datetime(2026, 10, 30, 12, 0)


def m(rank, lat, lon, seconds, *, seq='seq-a', uploaded=None, filename=None):
	at = T0 + timedelta(seconds=seconds)
	return Member(seq, rank, f'{seq}-{rank}', lat, lon, at, uploaded or at + timedelta(minutes=5),
		None, filename, 'alice')


def kinds(sequence):
	return [f.kind for f in photo_findings(sequence, NOW)]


def test_a_walk_and_a_trip_are_quiet():
	walk = [m(i, 50.0 + i * 0.0001, 14.0, i * 15) for i in range(10)]  # ~11 m every 15 s
	trip = [m(0, 47.57004, 14.22083, 0), m(1, 47.53438, 14.12234, 454)]  # 8.4 km at 67 km/h
	assert kinds(walk) == []
	assert kinds(trip) == []


def test_teleport():
	# 5.7 km in 3 s
	assert kinds([m(0, 50.68570, 13.58235, 0), m(1, 50.65351, 13.64450, 3)]) == ['teleport']


def test_one_coordinate_moved_alone():
	# 13.2 km in 8 s, longitude identical to the 1e-6
	found = kinds([m(0, 50.20064, 15.04028, 0), m(1, 50.31939, 15.04028, 8)])
	assert 'one coordinate moved alone' in found and 'teleport' in found


def test_spike_is_one_finding_not_two_teleports():
	# Out 2.2 km and back within 20 s: one glitch, reported once.
	out_and_back = [m(0, 50.0, 14.0, 0), m(1, 50.02, 14.02, 10), m(2, 50.0001, 14.0001, 20)]
	assert kinds(out_and_back) == ['spike']
	# A spike that kept its longitude says so once, on the way out.
	along = [m(0, 50.0, 14.0, 0), m(1, 50.02, 14.0, 10), m(2, 50.0001, 14.0001, 20)]
	assert kinds(along) == ['spike', 'one coordinate moved alone']


def test_capture_times():
	assert kinds([Member('s', 0, 'future', 50, 14, NOW + timedelta(days=3), None, None, None, None)]) == ['capture time']
	assert kinds([Member('s', 0, 'old', 50, 14, datetime(1999, 5, 1), None, None, None, None)]) == ['capture time']
	assert kinds([m(0, 50, 14, 0, uploaded=T0 - timedelta(days=2))]) == ['capture time']
	assert kinds([m(0, 50, 14, 0, uploaded=T0 + timedelta(days=200))]) == []


def test_summary_and_ordering():
	quiet = [m(i, 50.0 + i * 0.001, 14.0, i * 60, seq='quiet') for i in range(3)]  # 111 m apart
	jumpy = [m(0, 50.68570, 13.58235, 0, seq='jumpy'), m(1, 50.65351, 13.64450, 3, seq='jumpy')]
	s = summarize(quiet, 0)
	assert s.photos == 3 and s.duration_s == 120 and s.dot_share == 1.0 and round(s.max_jump_m) == 111
	findings, summaries = analyze(quiet + jumpy, NOW)
	assert [f.kind for f in findings] == ['teleport']
	assert [x.sequence_id for x in summaries] == ['jumpy', 'quiet']


def test_render_escapes_names():
	sequence = [m(0, 50.68570, 13.58235, 0, filename='<b>x</b>.jpg'), m(1, 50.65351, 13.64450, 3, filename='<b>x</b>.jpg')]
	findings, summaries = analyze(sequence, NOW)
	page = render(findings, summaries, lambda _: 'L', lambda _: 'S', NOW)
	assert '&lt;b&gt;x&lt;/b&gt;.jpg' in page and '<b>x</b>' not in page
	assert 'data-testid="suspicious-photos"' in page and 'data-testid="suspicious-sequences"' in page
