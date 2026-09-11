"""CQL2-text `filter` parameter of /api/collections.

Parsing is delegated to pygeofilter — the same library the reference GeoVisio
server uses for its own `filter` parameters (geovisio/utils/cql2.py) — so the
grammar is the real CQL2 grammar, not a home-grown approximation. What we do
here is walk the resulting AST and accept only the subset we can execute:

    status IN ('deleted','ready') AND updated > '2026-01-01T00:00:00Z'

which is the one shape the meta-catalog harvester sends (harvest.py
get_collections), plus small variations (`status = '...'`, `>=`, clauses in
any order, `TIMESTAMP('...')` literals, parentheses). Anything else — other
attributes, OR/NOT, other operators, non-literal operands — is rejected with
a FilterParseError so a client speaking more CQL than we execute fails loudly
instead of silently getting an unfiltered listing.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterator

from pygeofilter import ast
from pygeofilter.parsers.cql2_text import parse as _parse_cql2_text

VALID_STATUSES = {'ready', 'deleted'}


class FilterParseError(ValueError):
	pass


@dataclass
class CollectionsFilter:
	# None = clause absent (defaults applied by the caller), else the allowed set
	statuses: set[str] | None = None
	updated_after: datetime | None = None
	updated_inclusive: bool = False


def parse_collections_filter(raw: str | None) -> CollectionsFilter:
	result = CollectionsFilter()
	if raw is None or raw.strip() == '':
		return result
	try:
		tree = _parse_cql2_text(raw)
	except Exception as e:  # lark UnexpectedToken/UnexpectedCharacters, literal conversion errors, ...
		# first line only: lark appends its full expected-token list, which is
		# grammar internals, not something a 400 body should carry
		reason = (str(e).strip().splitlines() or ['unparseable'])[0]
		raise FilterParseError(f"malformed CQL2 filter: {reason}") from e
	for clause in _conjuncts(tree):
		_apply_clause(clause, result)
	return result


def _conjuncts(node: ast.Node) -> Iterator[ast.Node]:
	"""Flatten a (left-nested) AND tree into its top-level clauses."""
	if isinstance(node, ast.And):
		yield from _conjuncts(node.lhs)
		yield from _conjuncts(node.rhs)
	else:
		yield node


def _apply_clause(node: ast.Node, result: CollectionsFilter) -> None:
	if isinstance(node, ast.In):
		if _attribute(node.lhs) != 'status':
			raise FilterParseError(f"unsupported attribute in IN clause: {_describe(node.lhs)}")
		if node.not_:
			raise FilterParseError("NOT IN is not supported")
		_set_statuses(result, {_status_literal(v) for v in node.sub_nodes})
	elif isinstance(node, ast.Equal):
		if _attribute(node.lhs) != 'status':
			raise FilterParseError(f"unsupported attribute in = clause: {_describe(node.lhs)}")
		_set_statuses(result, {_status_literal(node.rhs)})
	elif isinstance(node, (ast.GreaterThan, ast.GreaterEqual)):
		if _attribute(node.lhs) != 'updated':
			raise FilterParseError(f"unsupported attribute in comparison: {_describe(node.lhs)}")
		if result.updated_after is not None:
			raise FilterParseError("duplicate updated clause")
		result.updated_after = _timestamp_literal(node.rhs)
		result.updated_inclusive = isinstance(node, ast.GreaterEqual)
	else:
		raise FilterParseError(f"unsupported filter clause: {_describe(node)}")


def _set_statuses(result: CollectionsFilter, statuses: set[str]) -> None:
	if result.statuses is not None:
		raise FilterParseError("duplicate status clause")
	if not statuses:
		raise FilterParseError("empty status list")
	result.statuses = statuses


def _attribute(node: object) -> str | None:
	"""Name of an attribute operand (case-folded), or None for anything else."""
	if isinstance(node, ast.Attribute):
		return node.name.lower()
	return None


def _status_literal(value: object) -> str:
	# pygeofilter hands quoted strings through as plain str; an unquoted word
	# comes back as an Attribute node, a number as int/float
	if not isinstance(value, str):
		raise FilterParseError(f"status must be a quoted string literal, got {_describe(value)}")
	if value not in VALID_STATUSES:
		raise FilterParseError(f"unknown status: {value!r}")
	return value


def _timestamp_literal(value: object) -> datetime:
	"""A quoted ISO-8601 string (what the harvester sends) or a CQL2
	TIMESTAMP('...') literal, which pygeofilter already turns into a datetime."""
	if isinstance(value, datetime):
		dt = value
	elif isinstance(value, str):
		try:
			dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
		except ValueError:
			raise FilterParseError(f"unparseable timestamp: {value!r}")
	else:
		# includes date (DATE('...') has no time part, too coarse for a crawl
		# cursor) and arithmetic trees such as an unquoted 2026-01-01
		raise FilterParseError(f"timestamp must be a quoted string or TIMESTAMP() literal, got {_describe(value)}")
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=timezone.utc)
	return dt.astimezone(timezone.utc)


def _describe(node: object) -> str:
	if isinstance(node, ast.Attribute):
		return f"attribute {node.name!r}"
	if isinstance(node, ast.Node):
		return type(node).__name__
	if isinstance(node, (str, int, float, date, datetime)):
		return repr(node)
	return type(node).__name__
