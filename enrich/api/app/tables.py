"""SQLAlchemy Core table definitions mirroring enrich/db/init/001_schema.sql.

Core (not ORM): the API mostly does bulk upserts and read joins; no unit-of-work
needed. Keep in lockstep with the SQL file — that file is the source of truth."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from geoalchemy2 import Geometry

metadata = sa.MetaData()

photo_mirror = sa.Table(
    "photo_mirror", metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("owner_id", sa.Text),
    sa.Column("filename", sa.Text),
    sa.Column("original_filename", sa.Text),
    sa.Column("file_md5", sa.Text),
    sa.Column("geometry", Geometry("POINT", srid=4326)),
    sa.Column("altitude", sa.Float),
    sa.Column("compass_angle", sa.Float),
    sa.Column("width", sa.Integer),
    sa.Column("height", sa.Integer),
    sa.Column("captured_at", sa.DateTime(timezone=False)),
    sa.Column("uploaded_at", sa.DateTime(timezone=True)),
    sa.Column("effective_at", sa.DateTime(timezone=False)),
    sa.Column("record_created_ts", sa.DateTime(timezone=True)),
    sa.Column("title", sa.Text),
    sa.Column("description", sa.Text),
    sa.Column("place_name", sa.Text),
    sa.Column("geocode", JSONB),
    sa.Column("sizes", JSONB),
    sa.Column("exif_data", JSONB),
    sa.Column("analysis", JSONB),
    sa.Column("detected_objects", JSONB),
    sa.Column("processing_status", sa.Text),
    sa.Column("is_public", sa.Boolean),
    sa.Column("deleted", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("version", sa.Integer),
    sa.Column("row_hash", sa.Text),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("missing_since", sa.DateTime(timezone=True)),
)

annotation_mirror = sa.Table(
    "annotation_mirror", metadata,
    sa.Column("id", sa.Text, primary_key=True),
    sa.Column("photo_id", sa.Text, nullable=False),
    sa.Column("user_id", sa.Text),
    sa.Column("body", sa.Text),
    sa.Column("target", JSONB),
    sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("superseded_by", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("event_type", sa.Text),
    sa.Column("row_hash", sa.Text),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("missing_since", sa.DateTime(timezone=True)),
)

runs = sa.Table(
    "runs", metadata,
    sa.Column("id", UUID(as_uuid=True), primary_key=True,
              server_default=sa.text("gen_random_uuid()")),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("params", JSONB, nullable=False, server_default=sa.text("'{}'")),
    sa.Column("status", sa.Text, nullable=False, server_default="running"),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("artifacts_dir", sa.Text),
    sa.Column("graph_iri", sa.Text),
    sa.Column("stats", JSONB),
    sa.Column("error", sa.Text),
    sa.Column("note", sa.Text),
)

sync_state = sa.Table(
    "sync_state", metadata,
    sa.Column("table_name", sa.Text, primary_key=True),
    sa.Column("watermark", sa.DateTime(timezone=True)),
    sa.Column("last_append_at", sa.DateTime(timezone=True)),
    sa.Column("last_reconcile_at", sa.DateTime(timezone=True)),
    sa.Column("stats", JSONB),
)
