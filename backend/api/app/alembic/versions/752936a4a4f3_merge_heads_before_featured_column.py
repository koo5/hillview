"""Merge heads before featured column

Revision ID: 752936a4a4f3
Revises: 012_add_analysis_column, 014_annotation_event_type
Create Date: 2026-03-18 01:28:58.780164

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '752936a4a4f3'
down_revision: Union[str, None] = ('012_add_analysis_column', '014_annotation_event_type')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass