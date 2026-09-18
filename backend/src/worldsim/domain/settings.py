"""Provider connections, pinned profile revisions, and operator preferences.

Secrets never live here: a connection names an environment variable, and
reads report only whether that variable is currently set. Profile revisions
carry nonsecret model IDs plus supported sampling values; stories pin a
revision so later edits cannot bleed into running worlds.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from worldsim.domain.time import utcnow

SUPPORTED_SAMPLING = ("temperature", "top_p", "top_k")


class AdapterKind(StrEnum):
    FAKE = "fake"
    OPENROUTER = "openrouter"


class ProviderConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    adapter: AdapterKind
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=512)
    credential_env: str | None = Field(default=None, max_length=128)
    allow_local_endpoint: bool = False
    config_version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utcnow)


class ProviderProfileRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    connection_id: UUID
    revision: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=128)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=100)
    max_tokens: int = Field(default=512, ge=1, le=4096)
    capabilities: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class GameplayDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pacing: str = Field(default="measured", max_length=32)
    autoplay_dwell: str = Field(default="normal", max_length=16)


class AccessibilityPrefs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    font_scale: int = Field(default=100, ge=75, le=200)
    motion: str = Field(default="system", max_length=16)


class LocalProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str = Field(default="Storyteller", max_length=64)
    avatar: str = Field(default="J", max_length=8)


class ApplicationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operator: str = Field(default="local", min_length=1, max_length=64)
    gameplay: GameplayDefaults = Field(default_factory=GameplayDefaults)
    accessibility: AccessibilityPrefs = Field(default_factory=AccessibilityPrefs)
    profile: LocalProfile = Field(default_factory=LocalProfile)
    version: int = Field(default=0, ge=0)
