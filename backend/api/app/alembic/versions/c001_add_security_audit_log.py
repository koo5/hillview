"""Add security audit log table

Revision ID: c001_add_security_audit_log
Revises: c000_initial_complete_setup
Create Date: 2025-08-19 23:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c001_add_security_audit_log'
down_revision: Union[str, None] = 'c000_initial_complete_setup'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create security audit log table
    op.create_table('security_audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('user_identifier', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('event_details', sa.JSON(), nullable=True),
        sa.Column('severity', sa.String(), nullable=False, default='info'),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for efficient querying
    op.create_index(op.f('ix_security_audit_log_event_type'), 'security_audit_log', ['event_type'])
    op.create_index(op.f('ix_security_audit_log_user_identifier'), 'security_audit_log', ['user_identifier'])
    op.create_index(op.f('ix_security_audit_log_ip_address'), 'security_audit_log', ['ip_address'])
    op.create_index(op.f('ix_security_audit_log_timestamp'), 'security_audit_log', ['timestamp'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index(op.f('ix_security_audit_log_timestamp'), table_name='security_audit_log')
    op.drop_index(op.f('ix_security_audit_log_ip_address'), table_name='security_audit_log')
    op.drop_index(op.f('ix_security_audit_log_user_identifier'), table_name='security_audit_log')
    op.drop_index(op.f('ix_security_audit_log_event_type'), table_name='security_audit_log')
    
    # Drop table
    op.drop_table('security_audit_log')