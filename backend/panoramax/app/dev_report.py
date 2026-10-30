"""DEV_MODE-only report: the federated photos and sequences most likely to look
wrong in Panoramax, so they can be inspected before (or instead of) shipping.

Reads what this service serves: sequence members passing the same eligibility
predicate as /api/collections/{id}/items, in sequence order. The findings are
computed here rather than in SQL so each rule has a unit test:

- teleport: a jump from the previous photo implying more than TELEPORT_KMH
- spike: one photo far away while its neighbours are close to each other
- one coordinate moved alone: a far jump keeping latitude or longitude
  exactly, which real movement does not do (a corrupted or edited fix)
- capture time: in the future, before 2000, or after the upload

Long jumps at plausible speed are not findings (they were real trips, see the
2026-10-30 survey in docs/panoramax-federation.md), but they rank sequences.
"""
import html
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from string import Template
from typing import Callable

from eligibility import ELIGIBLE_PHOTO_WHERE

# Faster than a train; slower jumps between sparse photos were real travel.
TELEPORT_KMH = 150
# Below this a high implied speed is GPS jitter between photos a second apart.
TELEPORT_MIN_M = 200
# A spike goes at least this far out and back...
SPIKE_M = 1000
# ...while the photos either side of it stay this close to each other.
SPIKE_BACK_M = 200
# A jump this long that keeps one coordinate to ~0.1 m.
ONE_AXIS_MIN_M = 500
ONE_AXIS_EPSILON = 1e-6
# The explorer draws no line between consecutive photos this far apart.
CATALOG_LINE_M = 75
EARLIEST_CAPTURE = datetime(2000, 1, 1)

MEMBERS_SQL = f"""
	SELECT sp.sequence_id::text AS sequence_id, sp.rank, p.id,
		ST_Y(p.geometry) AS lat, ST_X(p.geometry) AS lon,
		p.captured_at, p.uploaded_at AT TIME ZONE 'UTC' AS uploaded_at,
		p.compass_angle AS bearing, p.original_filename AS filename, u.username
	FROM panoramax.sequence_photos sp
	JOIN photos p ON p.id = sp.photo_id
	JOIN users u ON u.id = p.owner_id
	WHERE {ELIGIBLE_PHOTO_WHERE}
	ORDER BY sp.sequence_id, sp.rank
"""


@dataclass(frozen=True)
class Member:
	sequence_id: str
	rank: int
	id: str
	lat: float
	lon: float
	captured_at: datetime
	uploaded_at: datetime | None
	bearing: float | None
	filename: str | None
	username: str | None


@dataclass(frozen=True)
class Finding:
	kind: str
	severity: float  # comparable within the report: higher is worse
	detail: str
	member: Member
	previous: Member | None = None


@dataclass(frozen=True)
class SequenceSummary:
	sequence_id: str
	photos: int
	duration_s: float
	max_jump_m: float
	max_kmh: float
	dot_share: float  # consecutive pairs the explorer draws as separate dots
	findings: int
	first: Member


def metres(a: Member, b: Member) -> float:
	p1, p2 = math.radians(a.lat), math.radians(b.lat)
	h = (math.sin((p2 - p1) / 2) ** 2
		+ math.cos(p1) * math.cos(p2) * math.sin(math.radians(b.lon - a.lon) / 2) ** 2)
	return 2 * 6371000 * math.asin(math.sqrt(h))


def _kmh(a: Member, b: Member, distance: float) -> float:
	return distance / max((b.captured_at - a.captured_at).total_seconds(), 1) * 3.6


def photo_findings(sequence: list[Member], now: datetime) -> list[Finding]:
	"""Findings for one sequence's members, in rank order."""
	out = []
	after_spike = False
	for i, m in enumerate(sequence):
		prev = sequence[i - 1] if i else None
		nxt = sequence[i + 1] if i + 1 < len(sequence) else None
		returning, after_spike = after_spike, False
		if prev:
			d = metres(prev, m)
			kmh = _kmh(prev, m, d)
			if nxt and d >= SPIKE_M and metres(m, nxt) >= SPIKE_M and metres(prev, nxt) < SPIKE_BACK_M:
				out.append(Finding('spike', d, f'{d:,.0f} m out and back; its neighbours are '
					f'{metres(prev, nxt):,.0f} m apart', m, prev))
				after_spike = True
			# The leg back from a spike is the same glitch, already reported.
			elif not returning and d >= TELEPORT_MIN_M and kmh > TELEPORT_KMH:
				out.append(Finding('teleport', kmh, f'{d:,.0f} m in {(m.captured_at - prev.captured_at).total_seconds():,.0f} s '
					f'({kmh:,.0f} km/h)', m, prev))
			if not returning and d >= ONE_AXIS_MIN_M:
				kept = ('longitude' if abs(m.lon - prev.lon) < ONE_AXIS_EPSILON
					else 'latitude' if abs(m.lat - prev.lat) < ONE_AXIS_EPSILON else None)
				if kept:
					out.append(Finding('one coordinate moved alone', d, f'{d:,.0f} m jump with an identical {kept}', m, prev))
		if m.captured_at > now + timedelta(days=1):
			out.append(Finding('capture time', 1e6, f'captured in the future ({m.captured_at:%Y-%m-%d %H:%M})', m))
		elif m.captured_at < EARLIEST_CAPTURE:
			out.append(Finding('capture time', 1e6, f'captured before 2000 ({m.captured_at:%Y-%m-%d})', m))
		elif m.uploaded_at and m.captured_at > m.uploaded_at + timedelta(hours=1):
			out.append(Finding('capture time', (m.captured_at - m.uploaded_at).total_seconds() / 3600,
				f'captured {m.captured_at:%Y-%m-%d %H:%M}, after its upload at {m.uploaded_at:%Y-%m-%d %H:%M}', m))
	return out


def summarize(sequence: list[Member], findings: int) -> SequenceSummary:
	pairs = list(zip(sequence, sequence[1:]))
	jumps = [(metres(a, b), a, b) for a, b in pairs]
	return SequenceSummary(
		sequence_id=sequence[0].sequence_id,
		photos=len(sequence),
		duration_s=(sequence[-1].captured_at - sequence[0].captured_at).total_seconds(),
		max_jump_m=max((d for d, _, _ in jumps), default=0.0),
		max_kmh=max((_kmh(a, b, d) for d, a, b in jumps if d >= TELEPORT_MIN_M), default=0.0),
		dot_share=sum(d >= CATALOG_LINE_M for d, _, _ in jumps) / len(jumps) if jumps else 0.0,
		findings=findings,
		first=sequence[0],
	)


def analyze(members: list[Member], now: datetime) -> tuple[list[Finding], list[SequenceSummary]]:
	"""All findings, worst first per kind, and every sequence's summary, the
	ones with findings first, then by their longest jump."""
	by_sequence: dict[str, list[Member]] = {}
	for m in members:
		by_sequence.setdefault(m.sequence_id, []).append(m)
	findings, summaries = [], []
	for sequence in by_sequence.values():
		found = photo_findings(sequence, now)
		findings += found
		summaries.append(summarize(sequence, len(found)))
	findings.sort(key=lambda f: (f.kind, -f.severity))
	summaries.sort(key=lambda s: (-s.findings, -s.max_jump_m))
	return findings, summaries


PAGE = Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Suspicious federated photos</title>
<style>
body { font: 14px/1.4 system-ui, sans-serif; margin: 1.5rem; }
table { border-collapse: collapse; margin-bottom: 2rem; }
th, td { border-bottom: 1px solid #ddd; padding: .3rem .6rem; text-align: left; vertical-align: top; }
th { background: #f4f4f4; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
</style></head><body>
<h1>Suspicious federated photos</h1>
<p>$summary</p>
<h2>Photos</h2>
<table data-testid="suspicious-photos">
<tr><th>finding</th><th>detail</th><th>photo</th><th>previous</th><th>owner</th></tr>
$photo_rows
</table>
<h2>Sequences</h2>
<p>With findings first, then by their longest jump. "Dots" is the share of consecutive
photos the explorer draws without a line ($line_m m or more apart).</p>
<table data-testid="suspicious-sequences">
<tr><th>sequence</th><th>photos</th><th>duration</th><th>longest jump</th><th>fastest</th><th>dots</th><th>findings</th><th>owner</th></tr>
$sequence_rows
</table>
</body></html>
""")


def render(findings: list[Finding], summaries: list[SequenceSummary], photo_links: Callable[[Member], str],
		sequence_links: Callable[[Member], str], generated: datetime, limit: int = 200) -> str:
	"""The report page. `photo_links` and `sequence_links` return HTML for one
	member's links (already escaped)."""
	e = html.escape
	photo_rows = '\n'.join(
		f'<tr><td>{e(f.kind)}</td><td>{e(f.detail)}</td>'
		f'<td>{e(f.member.filename or f.member.id)}<br>{photo_links(f.member)}</td>'
		f'<td>{photo_links(f.previous) if f.previous else ""}</td><td>{e(f.member.username or "")}</td></tr>'
		for f in findings[:limit])
	sequence_rows = '\n'.join(
		f'<tr><td>{sequence_links(s.first)}</td><td class="num">{s.photos}</td>'
		f'<td class="num">{s.duration_s / 60:,.0f} min</td><td class="num">{s.max_jump_m:,.0f} m</td>'
		f'<td class="num">{s.max_kmh:,.0f} km/h</td><td class="num">{s.dot_share:.0%}</td>'
		f'<td class="num">{s.findings}</td><td>{e(s.first.username or "")}</td></tr>'
		for s in summaries[:limit])
	kinds: dict[str, int] = {}
	for f in findings:
		kinds[f.kind] = kinds.get(f.kind, 0) + 1
	summary = (f'{len(findings)} findings in {sum(1 for s in summaries if s.findings)} of {len(summaries)} '
		f'sequences ({", ".join(f"{e(k)}: {n}" for k, n in sorted(kinds.items())) or "none"}); '
		f'showing up to {limit} rows each. Generated {generated:%Y-%m-%d %H:%M} UTC.')
	return PAGE.substitute(summary=summary, photo_rows=photo_rows, sequence_rows=sequence_rows,
		line_m=CATALOG_LINE_M)
