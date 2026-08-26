"""Add the `panoramax` PG schema: synthesized sequences for the Panoramax federation.

Hillview joins the Panoramax federation by serving a GeoVisio-compatible read
API (backend/panoramax/) whose "collections" are sequences synthesized from
users' photos by per-owner time-gap session splitting. This migration is purely
additive to the existing schema: the only touch on existing tables is an AFTER
UPDATE trigger on photos (+ FKs from the new tables).

Design constraints (from the meta-catalog harvester, see docs/panoramax-federation.md):
- Sequence ids must be real UUIDs — the meta-catalog casts `content->>'id'` to
  UUID primary-key columns.
- Tombstones are never hard-deleted: a sequence that loses all members flips to
  status='deleted' and must keep being served (the harvester's incremental sync
  lists `status IN ('deleted','ready') AND updated > <ts>` — the updated_at bump
  is the only channel through which deletions propagate to the catalog).
- owner_id is ON DELETE SET NULL so tombstones survive account deletion.
- UNIQUE(photo_id) on membership: a photo belongs to at most one sequence, which
  stays correct across future scopes because scopes partition by license.
- The (scope, updated_at) index serves the harvester's incremental crawl filter.
- Membership triggers fire on cascaded deletes too (PG fires row triggers on the
  referencing table when a photos hard-delete cascades), so photo hard-deletes
  bump/tombstone sequences without any app-side code.

NOT here by design: backfill (the sequencer's first run does it) and role
creation (panoramax_ro is provisioning/initdb territory, not alembic — see
docker/postgres/). Grants ARE applied here, guarded on the role's existence,
because on a fresh cluster the schema doesn't exist yet at initdb time.

Revision ID: 030_add_panoramax_schema
Revises: 029_share_links
Create Date: 2026-08-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '030_add_panoramax_schema'
down_revision: Union[str, None] = '029_share_links'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS panoramax")

    op.execute("""
        CREATE TABLE panoramax.sequences (
            id UUID PRIMARY KEY,
            scope VARCHAR NOT NULL,
            status VARCHAR NOT NULL DEFAULT 'ready'
                CONSTRAINT sequences_status_check CHECK (status IN ('ready', 'deleted')),
            owner_id VARCHAR REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # Incremental-crawl index: the harvester filters by scope-wide status +
    # `updated > <ts>`; scope leads so a second instance scope stays cheap.
    op.execute("""
        CREATE INDEX ix_panoramax_sequences_scope_updated
        ON panoramax.sequences (scope, updated_at)
    """)
    op.execute("""
        CREATE INDEX ix_panoramax_sequences_owner
        ON panoramax.sequences (owner_id)
    """)

    # PK is photo_id (globally unique membership). The (sequence_id, rank)
    # uniqueness is DEFERRABLE so the sequencer can renumber ranks within a
    # transaction without transient collisions.
    op.execute("""
        CREATE TABLE panoramax.sequence_photos (
            photo_id VARCHAR PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
            sequence_id UUID NOT NULL REFERENCES panoramax.sequences(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            CONSTRAINT sequence_photos_rank_unique UNIQUE (sequence_id, rank)
                DEFERRABLE INITIALLY DEFERRED
        )
    """)
    op.execute("""
        CREATE INDEX ix_panoramax_sequence_photos_seq_rank
        ON panoramax.sequence_photos (sequence_id, rank)
    """)

    # Any change to a member photo that alters what the federation sees
    # (visibility, license, position, heading, capture time, derivatives,
    # title/description, processing state, soft-delete) bumps the owning
    # sequence's updated_at so the harvester re-crawls that collection.
    # geometry is compared as text (exact EWKB hex; PostGIS `=` is bbox
    # equality) and sizes as text (json has no equality operator).
    op.execute("""
        CREATE FUNCTION panoramax.bump_sequence_on_photo_change() RETURNS trigger AS $$
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
        CREATE TRIGGER panoramax_photo_change_trg
        AFTER UPDATE ON photos
        FOR EACH ROW EXECUTE FUNCTION panoramax.bump_sequence_on_photo_change();
    """)

    # Membership changes bump the sequence, and a sequence emptied by deletes is
    # tombstoned (status='deleted'), never removed. Covers the sequencer's own
    # writes AND cascaded deletes from photos/users hard-deletes.
    op.execute("""
        CREATE FUNCTION panoramax.bump_sequence_on_membership() RETURNS trigger AS $$
        BEGIN
            IF TG_OP IN ('INSERT', 'UPDATE') THEN
                -- a sequence gaining a member is live by definition: revive
                -- tombstones the sequencer repopulates, and bump updated_at
                UPDATE panoramax.sequences
                SET updated_at = now(), status = 'ready'
                WHERE id = NEW.sequence_id;
            END IF;
            IF TG_OP IN ('UPDATE', 'DELETE')
               AND (TG_OP = 'DELETE' OR OLD.sequence_id IS DISTINCT FROM NEW.sequence_id) THEN
                UPDATE panoramax.sequences
                SET updated_at = now()
                WHERE id = OLD.sequence_id;
                UPDATE panoramax.sequences s
                SET status = 'deleted', updated_at = now()
                WHERE s.id = OLD.sequence_id
                  AND s.status <> 'deleted'
                  AND NOT EXISTS (
                      SELECT 1 FROM panoramax.sequence_photos sp
                      WHERE sp.sequence_id = OLD.sequence_id
                  );
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER panoramax_membership_trg
        AFTER INSERT OR UPDATE OR DELETE ON panoramax.sequence_photos
        FOR EACH ROW EXECUTE FUNCTION panoramax.bump_sequence_on_membership();
    """)

    # Grants for the dedicated read-mostly role, applied only if provisioning
    # already created it (fresh clusters: docker/postgres/initdb.d creates the
    # role before the api container ever runs alembic; existing deployments:
    # scripts/provision_panoramax_role.sh, which re-applies these grants itself).
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panoramax_ro') THEN
                GRANT USAGE ON SCHEMA public TO panoramax_ro;
                GRANT SELECT ON photos, users, photo_ratings, flagged_photos
                    TO panoramax_ro;
                GRANT USAGE ON SCHEMA panoramax TO panoramax_ro;
                GRANT SELECT, INSERT, UPDATE, DELETE
                    ON panoramax.sequences, panoramax.sequence_photos TO panoramax_ro;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS panoramax_photo_change_trg ON photos")
    op.execute("DROP FUNCTION IF EXISTS panoramax.bump_sequence_on_photo_change()")
    op.execute("DROP TRIGGER IF EXISTS panoramax_membership_trg ON panoramax.sequence_photos")
    op.execute("DROP FUNCTION IF EXISTS panoramax.bump_sequence_on_membership()")
    op.execute("DROP TABLE IF EXISTS panoramax.sequence_photos")
    op.execute("DROP TABLE IF EXISTS panoramax.sequences")
    op.execute("DROP SCHEMA IF EXISTS panoramax")
