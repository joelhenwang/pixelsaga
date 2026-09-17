"""Provider selection for the composition root (owned by S3-PROV-001).

Settings choose the profile; this module builds the per-role
gateways. No call site branches on provider: everything downstream
sees the ModelGateway port. The Stage 0 scripted path stays fake;
only the Stage 1 role set follows the active profile.
"""

from __future__ import annotations

from collections.abc import Callable

from worldsim.application.ports.model_gateway import ModelGateway, ModelProfile
from worldsim.infrastructure.model_gateway.fake import FakeGateway
from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.profiles import (
    CHARACTER_FAKE_PROFILE,
    DIRECTOR_FAKE_PROFILE,
    NARRATOR_FAKE_PROFILE,
    OPENROUTER_CHAT_PROFILE,
    REACTION_FAKE_PROFILE,
    RESOLVER_FAKE_PROFILE,
    STAGE0_DEFAULT_BEAT,
    SUMMARY_FAKE_PROFILE,
)
from worldsim.infrastructure.model_gateway.retry import RetryingGateway
from worldsim.infrastructure.settings import Settings

ROLE_NAMES = ("character", "reaction", "resolver", "narrator", "director", "summary")

FAKE_PROFILES: dict[str, ModelProfile] = {
    "character": CHARACTER_FAKE_PROFILE,
    "reaction": REACTION_FAKE_PROFILE,
    "resolver": RESOLVER_FAKE_PROFILE,
    "narrator": NARRATOR_FAKE_PROFILE,
    "director": DIRECTOR_FAKE_PROFILE,
    "summary": SUMMARY_FAKE_PROFILE,
}


def gateways_for_settings(
    settings: Settings,
    fake_factory: Callable[[], FakeGateway] | None = None,
) -> tuple[dict[str, ModelGateway], dict[str, ModelProfile]]:
    """Per-role gateways and profiles for the active provider selection.

    An injected fake factory (tests scripting model behavior) wins over
    the fake profile; the live profile never consults it.
    """
    if fake_factory is not None and settings.provider.active_profile == "fake":
        return (
            {role: fake_factory() for role in ROLE_NAMES},
            dict(FAKE_PROFILES),
        )
    if settings.provider.active_profile == "openrouter":
        key = settings.provider.openrouter_api_key
        assert key is not None, "settings reject openrouter without credentials"
        profile = OPENROUTER_CHAT_PROFILE.model_copy(
            update={"model_id": settings.provider.openrouter_model}
        )
        gateways: dict[str, ModelGateway] = {
            role: RetryingGateway(
                OpenRouterGateway(
                    profile,
                    api_key=key,
                    base_url=settings.provider.openrouter_base_url,
                )
            )
            for role in ROLE_NAMES
        }
        profiles = {role: profile for role in ROLE_NAMES}
        return gateways, profiles
    return (
        {
            role: FakeGateway(profile=FAKE_PROFILES[role], default_text=STAGE0_DEFAULT_BEAT)
            for role in ROLE_NAMES
        },
        dict(FAKE_PROFILES),
    )
