import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.schemas.place_source import PlaceSyncStatus


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Region(Base, TimestampMixin):
    __tablename__ = "regions"
    __table_args__ = (
        UniqueConstraint("province_name", "city_name", name="uq_regions_province_city"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    province_name: Mapped[str] = mapped_column(String(50), nullable=False)
    city_name: Mapped[str] = mapped_column(String(50), nullable=False)
    region_level: Mapped[str] = mapped_column(String(20), nullable=False, default="CITY")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    places: Mapped[list["Place"]] = relationship(back_populates="region")


class Place(Base, TimestampMixin):
    __tablename__ = "places"
    __table_args__ = (
        Index("idx_places_region_category", "region_id", "category"),
        Index("idx_places_name", "name"),
        Index("idx_places_sync_status", "sync_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    road_address: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    image_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sync_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=PlaceSyncStatus.RAW.value,
    )
    canonical_place_key: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    review_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    backend_place_id: Mapped[int | None] = mapped_column(BigInteger)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    region: Mapped[Region] = relationship(back_populates="places")
    sources: Mapped[list["PlaceSource"]] = relationship(back_populates="place")
    events: Mapped[list["Event"]] = relationship(back_populates="place")


class PlaceSource(Base, TimestampMixin):
    __tablename__ = "place_sources"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_place_sources_source_external_id"),
        Index("idx_place_sources_place_id", "place_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("places.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    place: Mapped[Place] = relationship(back_populates="sources")


class Event(Base, TimestampMixin):
    __tablename__ = "events"
    __table_args__ = (Index("idx_events_region_dates", "region_id", "start_date", "end_date"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regions.id"), nullable=False)
    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    place: Mapped[Place | None] = relationship(back_populates="events")


class RegionMetric(Base, TimestampMixin):
    __tablename__ = "region_metrics"
    __table_args__ = (
        UniqueConstraint("region_id", "metric_type", "period", name="uq_region_metrics_unique"),
        Index("idx_region_metrics_type_period", "metric_type", "period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regions.id"), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(80), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class RagDocument(Base, TimestampMixin):
    __tablename__ = "rag_documents"
    __table_args__ = (Index("idx_rag_documents_subject", "subject_type", "subject_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
