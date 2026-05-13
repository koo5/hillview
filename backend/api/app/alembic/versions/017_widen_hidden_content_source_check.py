"""Widen hidden_content CHECK constraints to include 'panoramax'.

The original 001_initial_schema migration capped photo_source and
target_user_source at ('mapillary', 'hillview') via DB-level CHECK
constraints. Panoramax was added as a third source loader, with route-level
validation matching Mapillary; this migration widens the underlying constraints
so HiddenPhoto / HiddenUser rows for Panoramax content are accepted.

The photo_ratings and flagged_photos tables only enforce the whitelist at the
route layer (no DB CHECK), so they require no schema change.

Revision ID: 017_widen_hidden_panoramax
Revises: 016_add_legal_rights
Create Date: 2026-05-12

"""
from typing import Sequence, Union

from alembic import op

revision: str = '017_widen_hidden_panoramax'
down_revision: Union[str, None] = '016_add_legal_rights'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.drop_constraint('check_photo_source', 'hidden_photos', type_='check')
	op.create_check_constraint(
		'check_photo_source',
		'hidden_photos',
		"photo_source IN ('mapillary', 'hillview', 'panoramax')",
	)

	op.drop_constraint('check_target_user_source', 'hidden_users', type_='check')
	op.create_check_constraint(
		'check_target_user_source',
		'hidden_users',
		"target_user_source IN ('mapillary', 'hillview', 'panoramax')",
	)


def downgrade() -> None:
	# Reverting only narrows the constraint; rows with 'panoramax' must be
	# removed beforehand or this will fail at validation time.
	op.drop_constraint('check_photo_source', 'hidden_photos', type_='check')
	op.create_check_constraint(
		'check_photo_source',
		'hidden_photos',
		"photo_source IN ('mapillary', 'hillview')",
	)

	op.drop_constraint('check_target_user_source', 'hidden_users', type_='check')
	op.create_check_constraint(
		'check_target_user_source',
		'hidden_users',
		"target_user_source IN ('mapillary', 'hillview')",
	)
