"""Add site_state: one row per named piece of site-wide derived state.

First use: the sitemap's <lastmod> for /bestof. The ranking changes whenever a
rating is added, flipped or removed, an annotation event lands, a photo is
soft-deleted or a large panorama arrives — and two of those (rating removal is
a hard delete, soft-delete is a bare boolean flip) leave no timestamp, while
deriving from the ones that do over-fires on deep-page churn. So instead of
inferring from inputs, the sitemap fingerprints the OUTPUT: on each fetch it
hashes page 1 of the ranking as a crawler sees it and, when the hash differs
from the stored one, records the new hash and now(). That row's updated_at is
the lastmod. It lags until the next sitemap fetch, which is exactly the moment
lastmod is read, so nothing is lost. See GET /api/bestof/lastmod.

Generic key/JSON shape so the next such value doesn't need a table.

Revision ID: 035_site_state
Revises: 034_photo_content_updated_at
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '035_site_state'
down_revision: Union[str, None] = '034_photo_content_updated_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
	op.create_table(
		'site_state',
		sa.Column('key', sa.Text(), primary_key=True),
		sa.Column('value', postgresql.JSONB(), nullable=False),
		sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
	)


def downgrade() -> None:
	op.drop_table('site_state')
