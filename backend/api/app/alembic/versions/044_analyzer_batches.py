"""Persist analyzer batch ownership and Claude spending reservations.

Revision ID: 044_analyzer_batches
Revises: 043_photo_blurry
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '044_analyzer_batches'
down_revision = '043_photo_blurry'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('analyzer_batches',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('provider_batch_id', sa.String(), unique=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('budget_period', sa.String(), nullable=False),
        sa.Column('reserved_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('actual_usd', sa.Float()),
        sa.Column('manifest', postgresql.JSONB(), nullable=False),
        sa.Column('error', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index('ix_analyzer_batches_status', 'analyzer_batches', ['status'])
    op.create_index('ix_analyzer_batches_budget_period', 'analyzer_batches', ['budget_period'])
    op.add_column('photo_analysis_queue', sa.Column('provider', sa.String()))
    op.add_column('photo_analysis_queue', sa.Column('batch_id', sa.String()))
    op.add_column('photo_analysis_queue', sa.Column('request_id', sa.String()))
    op.add_column('photo_analysis_queue', sa.Column('claude_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.create_foreign_key('fk_photo_analysis_queue_batch', 'photo_analysis_queue', 'analyzer_batches', ['batch_id'], ['id'])
    op.create_index('ix_photo_analysis_queue_batch_id', 'photo_analysis_queue', ['batch_id'])


def downgrade():
    op.drop_index('ix_photo_analysis_queue_batch_id', table_name='photo_analysis_queue')
    op.drop_constraint('fk_photo_analysis_queue_batch', 'photo_analysis_queue', type_='foreignkey')
    for name in ('claude_attempts', 'request_id', 'batch_id', 'provider'):
        op.drop_column('photo_analysis_queue', name)
    op.drop_table('analyzer_batches')
