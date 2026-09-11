"""Create initial RoadSense schema.

Revision ID: 0001_initial_schema
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(128), primary_key=True),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("trust_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.CheckConstraint("status IN ('active', 'suspended', 'revoked')", name="ck_devices_status"),
    )
    op.create_table(
        "reviewers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="reviewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role IN ('reviewer', 'admin')", name="ck_reviewers_role"),
    )
    op.create_table(
        "observations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(128), sa.ForeignKey("devices.device_id"), nullable=False),
        sa.Column("violation_type", sa.String(32), nullable=False),
        sa.Column("plate_no", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_nonce", sa.String(128), nullable=False, unique=True),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("wrong_way_status", sa.String(32), nullable=True),
        sa.CheckConstraint(
            "violation_type IN ('wrong_side', 'red_light')",
            name="ck_observations_violation_type",
        ),
        sa.CheckConstraint(
            "(violation_type = 'red_light' AND wrong_way_status IS NULL) OR "
            "(violation_type = 'wrong_side' AND wrong_way_status IN "
            "('unconfirmed', 'confirmed', 'rejected'))",
            name="ck_observations_wrong_way_status",
        ),
    )
    op.execute(
        "ALTER TABLE observations ALTER COLUMN location TYPE geography(Point, 4326) "
        "USING ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography"
    )
    op.create_index("ix_observations_plate_no", "observations", ["plate_no"])
    op.create_index("ix_observations_location", "observations", ["location"], postgresql_using="gist")
    op.create_index("ix_observations_ts", "observations", ["ts"])
    op.create_table(
        "candidate_incidents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("violation_type", sa.String(32), nullable=False),
        sa.Column("plate_no", sa.Text(), nullable=False),
        sa.Column("geo_cluster", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="candidate"),
        sa.Column("reviewed_by", sa.BigInteger(), sa.ForeignKey("reviewers.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "violation_type IN ('wrong_side', 'red_light')",
            name="ck_candidate_incidents_violation_type",
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'corroborated', 'corroborated_no_evidence', 'confirmed', 'rejected')",
            name="ck_candidate_incidents_status",
        ),
    )
    op.create_index("ix_candidate_incidents_plate_no", "candidate_incidents", ["plate_no"])
    op.execute(
        "ALTER TABLE candidate_incidents ALTER COLUMN geo_cluster TYPE geography(Point, 4326) "
        "USING NULL::geography"
    )
    op.create_index("ix_candidate_incidents_geo_cluster", "candidate_incidents", ["geo_cluster"], postgresql_using="gist")
    op.create_table(
        "incident_observations",
        sa.Column("incident_id", sa.BigInteger(), sa.ForeignKey("candidate_incidents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("observation_id", sa.BigInteger(), sa.ForeignKey("observations.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "evidence",
        sa.Column("incident_id", sa.BigInteger(), sa.ForeignKey("candidate_incidents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("device_id", sa.String(128), sa.ForeignKey("devices.device_id"), primary_key=True),
        sa.Column("event_nonce", sa.String(128), primary_key=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_ref", sa.Text(), nullable=True),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("evidence")
    op.drop_table("incident_observations")
    op.drop_index("ix_candidate_incidents_geo_cluster", table_name="candidate_incidents")
    op.drop_index("ix_candidate_incidents_plate_no", table_name="candidate_incidents")
    op.drop_table("candidate_incidents")
    op.drop_index("ix_observations_ts", table_name="observations")
    op.drop_index("ix_observations_location", table_name="observations")
    op.drop_index("ix_observations_plate_no", table_name="observations")
    op.drop_table("observations")
    op.drop_table("reviewers")
    op.drop_table("devices")
