"""Add photo ratings table

Revision ID: c0d43de831b9
Revises: 002_add_file_md5_column
Create Date: 2025-09-12 20:12:39.141246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c0d43de831b9'
down_revision: Union[str, None] = '002_add_file_md5_column'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create photo_ratings table
    op.create_table('photo_ratings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('photo_source', sa.String(length=20), nullable=False),
        sa.Column('photo_id', sa.String(length=255), nullable=False),
        sa.Column('rating', sa.Enum('THUMBS_UP', 'THUMBS_DOWN', name='photoratingtype', create_type=False), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create unique constraint to prevent duplicate ratings
    op.create_unique_constraint(
        'unique_user_photo_rating', 
        'photo_ratings', 
        ['user_id', 'photo_source', 'photo_id']
    )
    
    # Create index for efficient lookups
    op.create_index('idx_photo_ratings_source_photo', 'photo_ratings', ['photo_source', 'photo_id'])


def downgrade() -> None:
    # Drop the table
    op.drop_index('idx_photo_ratings_source_photo', table_name='photo_ratings')
    op.drop_constraint('unique_user_photo_rating', 'photo_ratings', type_='unique')
    op.drop_table('photo_ratings')