"""The CQL2-text subset parser must accept exactly what the meta-catalog
harvester sends (see its harvest.py get_collections) and reject everything
else loudly."""
from datetime import datetime, timezone

import pytest

from cql import CollectionsFilter, FilterParseError, parse_collections_filter


class TestHarvesterShapes:
	def test_no_filter_full_harvest(self):
		assert parse_collections_filter(None) == CollectionsFilter()
		assert parse_collections_filter('') == CollectionsFilter()
		assert parse_collections_filter('   ') == CollectionsFilter()

	def test_exact_incremental_filter(self):
		# verbatim shape from harvest.py:67
		f = parse_collections_filter(
			"status IN ('deleted','ready') AND updated > '2026-07-01T12:34:56Z'")
		assert f.statuses == {'deleted', 'ready'}
		assert f.updated_after == datetime(2026, 7, 1, 12, 34, 56, tzinfo=timezone.utc)
		assert f.updated_inclusive is False

	def test_timestamp_with_offset(self):
		f = parse_collections_filter("updated > '2026-07-01T12:00:00+02:00'")
		assert f.updated_after == datetime(2026, 7, 1, 10, 0, tzinfo=timezone.utc)

	def test_naive_timestamp_assumed_utc(self):
		f = parse_collections_filter("updated > '2026-07-01T12:00:00'")
		assert f.updated_after.tzinfo == timezone.utc


class TestGrammarTolerance:
	def test_clauses_in_reverse_order(self):
		f = parse_collections_filter(
			"updated > '2026-01-01T00:00:00Z' AND status IN ('ready')")
		assert f.statuses == {'ready'}
		assert f.updated_after is not None

	def test_case_insensitive_keywords(self):
		f = parse_collections_filter(
			"STATUS in ('ready','deleted') and UPDATED > '2026-01-01T00:00:00Z'")
		assert f.statuses == {'ready', 'deleted'}

	def test_status_equality(self):
		assert parse_collections_filter("status = 'deleted'").statuses == {'deleted'}
		assert parse_collections_filter("status='ready'").statuses == {'ready'}

	def test_updated_gte_is_inclusive(self):
		f = parse_collections_filter("updated >= '2026-01-01T00:00:00Z'")
		assert f.updated_inclusive is True

	def test_spaces_inside_in_list(self):
		f = parse_collections_filter("status IN ( 'ready' , 'deleted' )")
		assert f.statuses == {'ready', 'deleted'}

	def test_cql2_timestamp_literal(self):
		# proper CQL2 spelling, which the harvester doesn't use but a spec-
		# following client would
		f = parse_collections_filter("updated > TIMESTAMP('2026-07-01T12:00:00Z')")
		assert f.updated_after == datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)

	def test_parenthesised_clause(self):
		f = parse_collections_filter(
			"status IN ('ready') AND (updated >= '2026-01-01T00:00:00Z')")
		assert f.statuses == {'ready'}
		assert f.updated_inclusive is True

	def test_quoted_identifier(self):
		assert parse_collections_filter("\"status\" = 'deleted'").statuses == {'deleted'}

	def test_three_clauses_left_nested(self):
		# pygeofilter nests `a AND b AND c` as And(And(a, b), c); the inner And
		# must be flattened, not rejected as an unknown clause — which shows up
		# as the third clause reaching the duplicate check
		with pytest.raises(FilterParseError, match='duplicate status'):
			parse_collections_filter(
				"status IN ('ready') AND updated > '2026-01-01T00:00:00Z' AND status IN ('deleted')")


class TestRejection:
	@pytest.mark.parametrize('bad', [
		"garbage",
		"status IN (ready)",              # unquoted literal → Attribute node
		"status IN ('bogus')",            # unknown status
		"status IN ()",                   # grammar error
		"updated > 2026-01-01",           # unquoted → arithmetic 2026-1-1
		"updated > 'not-a-date'",
		"updated > DATE('2026-01-01')",   # date literal has no time part
		"updated > 20260101",             # numeric literal
		"updated < '2026-01-01T00:00:00Z'",   # unsupported operator
		"created > '2026-01-01T00:00:00Z'",   # unsupported field
		"status = 'ready' OR status = 'deleted'",  # OR not in the subset
		"NOT status = 'ready'",
		"status NOT IN ('ready')",
		"status IS NULL",
		"status LIKE 'read%'",
		"'ready' = status",               # attribute must be the lhs
		"status = 'ready' AND status = 'deleted'",  # duplicate clause
		"updated > '2026-01-01T00:00:00Z' AND updated > '2026-01-02T00:00:00Z'",
		"status = 'ready' AND (updated > '2026-01-01T00:00:00Z' OR status = 'deleted')",
	])
	def test_rejects(self, bad):
		with pytest.raises(FilterParseError):
			parse_collections_filter(bad)

	def test_error_message_names_the_offender(self):
		with pytest.raises(FilterParseError, match='created'):
			parse_collections_filter("created > '2026-01-01T00:00:00Z'")
		with pytest.raises(FilterParseError, match='NOT IN'):
			parse_collections_filter("status NOT IN ('ready')")
