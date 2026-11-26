"""Record each photo's Panoramax outcome from the sequencer's last pass.

Why a photo is or is not federated was computed on every pass and thrown away,
so answering it meant re-running the gates by hand. The sequencer now keeps
one row per photo: a member of a sequence, suppressed by the photo that
represents its grid cell and bearing sector, or ineligible with the gates
(panoramax/app/eligibility.py GATES) it failed. The photo page reads it.

It records the outcome, not a re-computation: the api never evaluates the
gates itself, so the page cannot disagree with what the sequencer did.
decided_at is when the current outcome was first recorded; the pass writes
only rows that changed. sequencer_passes holds when each scope's last pass
ran, so a reader can tell "not decided yet" from "decided long ago".

winner_id has no foreign key: the winner may be deleted before the next pass
rewrites the row, and a dangling id there is harmless.

Revision ID: 040_panoramax_photo_status
Revises: 039_photo_location_accuracy
"""
from alembic import op

revision = '040_panoramax_photo_status'
down_revision = '039_photo_location_accuracy'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.execute("""
		CREATE TABLE panoramax.photo_status (
			photo_id VARCHAR PRIMARY KEY REFERENCES photos(id) ON DELETE CASCADE,
			scope VARCHAR NOT NULL,
			outcome VARCHAR NOT NULL CHECK (outcome IN ('member', 'suppressed', 'ineligible')),
			winner_id VARCHAR,
			failed_gates VARCHAR[] NOT NULL DEFAULT '{}',
			decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)
	""")
	op.execute("""
		CREATE TABLE panoramax.sequencer_passes (
			scope VARCHAR PRIMARY KEY,
			finished_at TIMESTAMPTZ NOT NULL
		)
	""")
	# Same conditional grant as 033; provision_panoramax_role.sh re-applies it.
	op.execute("""
		DO $$
		BEGIN
			IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'panoramax_ro') THEN
				GRANT SELECT, INSERT, UPDATE, DELETE
					ON panoramax.photo_status, panoramax.sequencer_passes TO panoramax_ro;
			END IF;
		END $$;
	""")


def downgrade() -> None:
	op.execute("DROP TABLE IF EXISTS panoramax.sequencer_passes")
	op.execute("DROP TABLE IF EXISTS panoramax.photo_status")
