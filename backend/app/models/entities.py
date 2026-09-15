from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# Primary key column helper compatible with both Postgres BigInteger and SQLite Integer autoincrement
def pk_bigint_column():
    return Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )


# Association table between incidents and observations
incident_observations = Table(
    "incident_observations",
    Base.metadata,
    Column(
        "incident_id",
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("candidate_incidents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "observation_id",
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("observations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'revoked')", name="ck_devices_status"),
    )

    device_id = Column(String(128), primary_key=True)
    public_key = Column(Text, nullable=False)
    trust_score = Column(Float, nullable=False, default=0.5)
    registered_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    status = Column(String(32), nullable=False, default="active")

    observations = relationship("Observation", back_populates="device")


class Reviewer(Base):
    __tablename__ = "reviewers"
    __table_args__ = (
        CheckConstraint("role IN ('reviewer', 'admin')", name="ck_reviewers_role"),
    )

    id = pk_bigint_column()
    email = Column(String(320), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(32), nullable=False, default="reviewer")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    reviewed_incidents = relationship("CandidateIncident", back_populates="reviewer")


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        CheckConstraint(
            "violation_type IN ('wrong_side', 'red_light')",
            name="ck_observations_violation_type",
        ),
        CheckConstraint(
            "(violation_type = 'red_light' AND wrong_way_status IS NULL) OR "
            "(violation_type = 'wrong_side' AND wrong_way_status IN "
            "('unconfirmed', 'confirmed', 'rejected'))",
            name="ck_observations_wrong_way_status",
        ),
    )

    id = pk_bigint_column()
    device_id = Column(String(128), ForeignKey("devices.device_id"), nullable=False)
    violation_type = Column(String(32), nullable=False)
    plate_no = Column(Text, nullable=False)  # ALWAYS stores hashed plate number
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    location = Column(Text, nullable=False)
    ts = Column(DateTime(timezone=True), nullable=False)
    event_nonce = Column(String(128), nullable=False, unique=True)
    signature = Column(Text, nullable=False)
    wrong_way_status = Column(String(32), nullable=True)

    device = relationship("Device", back_populates="observations")
    incidents = relationship(
        "CandidateIncident",
        secondary=incident_observations,
        back_populates="observations",
    )


class CandidateIncident(Base):
    __tablename__ = "candidate_incidents"
    __table_args__ = (
        CheckConstraint(
            "violation_type IN ('wrong_side', 'red_light')",
            name="ck_candidate_incidents_violation_type",
        ),
        CheckConstraint(
            "status IN ('candidate', 'corroborated', 'corroborated_no_evidence', 'confirmed', 'rejected')",
            name="ck_candidate_incidents_status",
        ),
    )

    id = pk_bigint_column()
    violation_type = Column(String(32), nullable=False)
    plate_no = Column(Text, nullable=False)  # ALWAYS stores hashed plate number
    geo_cluster = Column(Text, nullable=True)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(32), nullable=False, default="candidate")
    reviewed_by = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("reviewers.id"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    reviewer = relationship("Reviewer", back_populates="reviewed_incidents")
    observations = relationship(
        "Observation",
        secondary=incident_observations,
        back_populates="incidents",
    )
    evidence_items = relationship("Evidence", back_populates="incident", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"

    incident_id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("candidate_incidents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    device_id = Column(String(128), ForeignKey("devices.device_id"), primary_key=True)
    event_nonce = Column(String(128), primary_key=True)
    requested_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    storage_ref = Column(Text, nullable=True)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)

    incident = relationship("CandidateIncident", back_populates="evidence_items")
    device = relationship("Device")
