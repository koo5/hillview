"""Add title and keywords columns to photos table.

Splits the single user-editable caption into a concise ``title`` (the headline
— og:title, <title>, schema.org name) and a longer ``description`` body, and
adds ``keywords`` (TEXT[]) for alternate place names / search synonyms
(schema.org keywords).

The old ``description`` field was used *as* the title (the photo page rendered
it via displayTitle), and every populated value is a short label (<= 35 chars:
"Grébovka", "Park Sacré Coeur", "Grébovka -> východ"), so each is promoted to
``title`` and ``description`` is freed for the new longer body. Empty-string
descriptions (the bulk of rows — the pipeline wrote "" when none was given) are
normalized to NULL in the same pass. NULL descriptions are left untouched.

Revision ID: 018_add_title_keywords
Revises: 017_widen_hidden_panoramax
Create Date: 2026-06-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '018_add_title_keywords'
down_revision: Union[str, None] = '017_widen_hidden_panoramax'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('photos', sa.Column('title', sa.Text(), nullable=True))
    op.add_column('photos', sa.Column('keywords', sa.ARRAY(sa.Text()), nullable=True))
    # Promote the old caption (used as the title) into the new title column and
    # free description for longer body text. NULLIF maps the empty-string
    # placeholders to a NULL title rather than a blank one; description is
    # cleared for every previously-set row. title is freshly added (universally
    # NULL), so there is nothing to overwrite. Touches ~25k rows.
    op.execute("UPDATE photos SET title = NULLIF(description, ''), description = NULL WHERE description IS NOT NULL")


def downgrade() -> None:
    # Move titles back into description before dropping the columns, so the
    # pre-split caption is preserved. (Rows whose description was a normalized
    # empty string stay NULL — semantically identical to the original "".)
    op.execute("UPDATE photos SET description = title WHERE description IS NULL AND title IS NOT NULL")
    op.drop_column('photos', 'keywords')
    op.drop_column('photos', 'title')
