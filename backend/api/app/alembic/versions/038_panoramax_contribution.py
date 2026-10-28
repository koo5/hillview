"""Panoramax consent, moderation gates and separate publication history.

The detections data migration has already populated explicit blurred flags.
Revision ID: 038_panoramax_contribution
Revises: 037_photo_bestof_eligible
"""
from alembic import op
import sqlalchemy as sa

revision = '038_panoramax_contribution'
down_revision = '037_photo_bestof_eligible'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('panoramax_contributor', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('photos', sa.Column('panoramax_owner_share', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('photos', sa.Column('panoramax_moderator_approved', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('user_moderation', sa.Column('old_panoramax_contributor', sa.Boolean(), nullable=True))
    op.add_column('user_moderation', sa.Column('new_panoramax_contributor', sa.Boolean(), nullable=True))
    op.create_table(
        'photo_outflow_license_history',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('photo_id', sa.String(length=255), nullable=False),
        sa.Column('photo_owner_id', sa.String(), nullable=True),
        sa.Column('photo_owner_username', sa.String(), nullable=True),
        sa.Column('old_license', sa.String(), nullable=True),
        sa.Column('new_license', sa.String(), nullable=True),
        sa.Column('cause', sa.String(length=32), nullable=False),
        sa.Column('actor_user_id', sa.String(), nullable=False),
        sa.Column('actor_username', sa.String(), nullable=True),
        sa.Column('actor_role', sa.String(), nullable=True),
        sa.Column('actor_was_owner', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_photo_outflow_license_history_photo', 'photo_outflow_license_history', ['photo_id'])
    op.create_index('idx_photo_outflow_license_history_owner', 'photo_outflow_license_history', ['photo_owner_id'])
    op.create_index('idx_photo_outflow_license_history_actor', 'photo_outflow_license_history', ['actor_user_id'])
    op.create_index('idx_photo_outflow_license_history_created', 'photo_outflow_license_history', ['created_at'])

    op.execute("""
        CREATE OR REPLACE FUNCTION panoramax.bump_sequence_on_photo_change() RETURNS trigger AS $$
        BEGIN
            IF (OLD.deleted IS DISTINCT FROM NEW.deleted
                OR OLD.is_public IS DISTINCT FROM NEW.is_public
                OR OLD.panoramax_owner_share IS DISTINCT FROM NEW.panoramax_owner_share
                OR OLD.panoramax_moderator_approved IS DISTINCT FROM NEW.panoramax_moderator_approved
                OR OLD.detected_objects::text IS DISTINCT FROM NEW.detected_objects::text
                OR OLD.legal_rights IS DISTINCT FROM NEW.legal_rights
                OR OLD.geometry::text IS DISTINCT FROM NEW.geometry::text
                OR OLD.compass_angle IS DISTINCT FROM NEW.compass_angle
                OR OLD.captured_at IS DISTINCT FROM NEW.captured_at
                OR OLD.effective_at IS DISTINCT FROM NEW.effective_at
                OR OLD.sizes::text IS DISTINCT FROM NEW.sizes::text
                OR OLD.title IS DISTINCT FROM NEW.title
                OR OLD.description IS DISTINCT FROM NEW.description
                OR OLD.processing_status IS DISTINCT FROM NEW.processing_status) THEN
                UPDATE panoramax.sequences s
                SET updated_at = now()
                FROM panoramax.sequence_photos sp
                WHERE sp.photo_id = NEW.id AND s.id = sp.sequence_id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
		CREATE OR REPLACE FUNCTION photos_stamp_content_updated_at() RETURNS trigger AS $$
		BEGIN
			IF (OLD.title IS DISTINCT FROM NEW.title
				OR OLD.description IS DISTINCT FROM NEW.description
				OR OLD.keywords IS DISTINCT FROM NEW.keywords
				OR OLD.featured IS DISTINCT FROM NEW.featured
				OR OLD.panoramax_owner_share IS DISTINCT FROM NEW.panoramax_owner_share
				OR OLD.legal_rights IS DISTINCT FROM NEW.legal_rights
				OR OLD.compass_angle IS DISTINCT FROM NEW.compass_angle
				OR OLD.place_name IS DISTINCT FROM NEW.place_name) THEN
				NEW.content_updated_at := now();
			END IF;
			RETURN NEW;
		END;
		$$ LANGUAGE plpgsql;
	""")
    op.execute("UPDATE panoramax.sequences SET scope='p1' WHERE scope='cc'")


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION panoramax.bump_sequence_on_photo_change() RETURNS trigger AS $$
        BEGIN
            IF (OLD.deleted IS DISTINCT FROM NEW.deleted
                OR OLD.is_public IS DISTINCT FROM NEW.is_public
                OR OLD.legal_rights IS DISTINCT FROM NEW.legal_rights
                OR OLD.geometry::text IS DISTINCT FROM NEW.geometry::text
                OR OLD.compass_angle IS DISTINCT FROM NEW.compass_angle
                OR OLD.captured_at IS DISTINCT FROM NEW.captured_at
                OR OLD.effective_at IS DISTINCT FROM NEW.effective_at
                OR OLD.sizes::text IS DISTINCT FROM NEW.sizes::text
                OR OLD.title IS DISTINCT FROM NEW.title
                OR OLD.description IS DISTINCT FROM NEW.description
                OR OLD.processing_status IS DISTINCT FROM NEW.processing_status) THEN
                UPDATE panoramax.sequences s
                SET updated_at = now()
                FROM panoramax.sequence_photos sp
                WHERE sp.photo_id = NEW.id AND s.id = sp.sequence_id;
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
		CREATE OR REPLACE FUNCTION photos_stamp_content_updated_at() RETURNS trigger AS $$
		BEGIN
			IF (OLD.title IS DISTINCT FROM NEW.title
				OR OLD.description IS DISTINCT FROM NEW.description
				OR OLD.keywords IS DISTINCT FROM NEW.keywords
				OR OLD.featured IS DISTINCT FROM NEW.featured
				OR OLD.legal_rights IS DISTINCT FROM NEW.legal_rights
				OR OLD.compass_angle IS DISTINCT FROM NEW.compass_angle
				OR OLD.place_name IS DISTINCT FROM NEW.place_name) THEN
				NEW.content_updated_at := now();
			END IF;
			RETURN NEW;
		END;
		$$ LANGUAGE plpgsql;
	""")
    op.execute("UPDATE panoramax.sequences SET scope='cc' WHERE scope='p1'")
    op.drop_table('photo_outflow_license_history')
    op.drop_column('user_moderation', 'new_panoramax_contributor')
    op.drop_column('user_moderation', 'old_panoramax_contributor')
    op.drop_column('photos', 'panoramax_moderator_approved')
    op.drop_column('photos', 'panoramax_owner_share')
    op.drop_column('users', 'panoramax_contributor')
