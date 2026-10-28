"""Add a neutral eligibility switch for the Best of listing.

Existing and new photos remain eligible by default. This affects only the
Best of selection; it carries no classification or reason.

Revision ID: 037_photo_bestof_eligible
Revises: 036_photo_analysis_queue, 036_photo_imu_samples_url
"""
from alembic import op
import sqlalchemy as sa

revision = '037_photo_bestof_eligible'
down_revision = ('036_photo_analysis_queue', '036_photo_imu_samples_url')
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column('photos', sa.Column('bestof_eligible', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
	op.drop_column('photos', 'bestof_eligible')
