"""Hillview property and analysis filters shared by map and timeline queries."""
from typing import List, Optional

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import Float, and_, case, func, literal, or_

from common.models import Photo


class AnalysisFilters(BaseModel):
	"""Filters based on photo analysis data"""
	time_of_day: Optional[str] = None  # day, night, dawn_dusk
	location_type: Optional[str] = None  # indoors, outdoors, mixed
	min_farthest_distance: Optional[float] = None  # farthest object must be at least X meters away
	max_closest_distance: Optional[float] = None  # closest object must be at most X meters away
	min_scenic_score: Optional[int] = None  # 1-5, minimum scenic beauty score
	visibility_distance: Optional[str] = None  # near, medium, far, panoramic
	tallest_building: Optional[str] = None  # none, low_rise, mid_rise, high_rise, skyscraper
	features: Optional[List[str]] = None  # any of these features (OR logic)
	show_unanalyzed: bool = True  # include photos without analysis data


class PropertyFilters(BaseModel):
	min_width: Optional[int] = Field(default=None, ge=1, strict=True)


class PhotoFilters(BaseModel):
	analysis: AnalysisFilters = Field(default_factory=AnalysisFilters)
	properties: PropertyFilters = Field(default_factory=PropertyFilters)


def parse_photo_filters(
	filters: Optional[str] = Query(None, description="JSON object with analysis and properties filters"),
	analysis_filters: Optional[str] = Query(None, description="Legacy flat analysis filters"),
) -> Optional[PhotoFilters]:
	# Existing clients can continue sending the old flat analysis object.
	if filters and filters != 'null':
		value, parameter = filters, 'filters'
	elif analysis_filters and analysis_filters != 'null':
		value, parameter = analysis_filters, 'analysis_filters'
	else:
		return None
	try:
		if parameter == 'analysis_filters':
			return PhotoFilters(analysis=AnalysisFilters.model_validate_json(value))
		return PhotoFilters.model_validate_json(value)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=f"Invalid {parameter}: {exc}") from exc


def _build_analysis_conditions(filters: AnalysisFilters) -> list:
	"""Build a list of SQLAlchemy conditions from analysis filter fields."""
	conditions = []

	if filters.time_of_day:
		conditions.append(Photo.analysis['time_of_day'].astext == filters.time_of_day)

	if filters.location_type:
		conditions.append(Photo.analysis['location_type'].astext == filters.location_type)

	if filters.min_farthest_distance is not None:
		conditions.append(
			Photo.analysis['farthest_object_distance'].astext.cast(Float) >= filters.min_farthest_distance
		)

	if filters.max_closest_distance is not None:
		conditions.append(
			Photo.analysis['closest_object_distance'].astext.cast(Float) <= filters.max_closest_distance
		)

	if filters.min_scenic_score is not None:
		conditions.append(
			Photo.analysis['scenic_score'].astext.cast(Float) >= filters.min_scenic_score
		)

	if filters.visibility_distance:
		conditions.append(Photo.analysis['visibility_distance'].astext == filters.visibility_distance)

	if filters.tallest_building:
		conditions.append(Photo.analysis['tallest_building'].astext == filters.tallest_building)

	if filters.features:
		# OR logic: any of the features matches
		feature_conditions = [Photo.analysis['features'].contains([f]) for f in filters.features]
		conditions.append(or_(*feature_conditions))

	return conditions


def _filter_predicate(filters: PhotoFilters):
	"""Return one pass predicate, or None when no constraints are active.

	Unanalyzed inclusion applies only to analysis constraints. Property checks
	always apply, including to unanalyzed photos and photos with unknown width.
	"""
	conditions = _build_analysis_conditions(filters.analysis)
	if conditions:
		analysis_passes = and_(Photo.analysis.isnot(None), *conditions)
		if filters.analysis.show_unanalyzed:
			analysis_passes = or_(Photo.analysis.is_(None), analysis_passes)
		passes = [analysis_passes]
	else:
		passes = []

	if filters.properties.min_width is not None:
		passes.append(Photo.width >= filters.properties.min_width)

	return func.coalesce(and_(*passes), False) if passes else None


def apply_photo_filters(query, filters: PhotoFilters):
	"""Timeline queries exclude nonmatching photos using the map's predicate."""
	passes = _filter_predicate(filters)
	return query.where(passes) if passes is not None else query


def build_filter_expressions(filters: PhotoFilters):
	"""Map queries flag nonmatches and rank matches before the result limit.

	Matching featured photos come first, followed by analyzed matches, included
	unanalyzed photos, and finally nonmatches. Property-only filters do not
	distinguish analyzed from unanalyzed photos.
	"""
	passes = _filter_predicate(filters)
	if passes is None:
		return None, None

	analysis_active = bool(_build_analysis_conditions(filters.analysis))
	analyzed_match = and_(passes, Photo.analysis.isnot(None)) if analysis_active else passes
	filtered_expr = case((passes, False), else_=True).label('filtered')
	sort_priority_expr = case(
		(and_(Photo.featured == True, passes), literal(0)),
		(analyzed_match, literal(1)),
		(passes, literal(2)),
		else_=literal(3),
	).label('sort_priority')
	return filtered_expr, sort_priority_expr
