"""Model-call cost records (owned by S3-PROV-001)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from worldsim.infrastructure.models import Base


class CostRow(Base):
    __tablename__ = "model_cost"

    call_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    world_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("world.id", name="fk_cost_world"), nullable=True
    )
    pricing_version: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(256), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer)
    completion_tokens: Mapped[int] = mapped_column(Integer)
    prompt_cost_usd: Mapped[float] = mapped_column(Float)
    completion_cost_usd: Mapped[float] = mapped_column(Float)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False)
