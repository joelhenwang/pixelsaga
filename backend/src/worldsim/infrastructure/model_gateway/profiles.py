"""Versioned model profiles (owned by S0-MODEL-001)."""

from __future__ import annotations

from worldsim.application.ports.model_gateway import ModelProfile, UnknownProfileError

FAKE_TEST_PROFILE = ModelProfile(
    name="fake",
    version="test-v1",
    adapter="fake",
    model_id="fake-echo",
    max_context_tokens=4096,
    capabilities=["chat", "embed"],
)

STAGE0_SCRIPTED_PROFILE = ModelProfile(
    name="fake",
    version="stage0-v1",
    adapter="fake",
    model_id="fake-stage0-tick",
    max_context_tokens=4096,
    capabilities=["chat"],
)

CHARACTER_FAKE_PROFILE = ModelProfile(
    name="character",
    version="decision-fake-v1",
    adapter="fake",
    model_id="fake-character-decision",
    max_context_tokens=4096,
    capabilities=["chat", "json_mode"],
)

REACTION_FAKE_PROFILE = ModelProfile(
    name="reaction",
    version="react-fake-v1",
    adapter="fake",
    model_id="fake-reaction",
    max_context_tokens=4096,
    capabilities=["chat", "json_mode"],
)

RESOLVER_FAKE_PROFILE = ModelProfile(
    name="resolver",
    version="resolve-fake-v1",
    adapter="fake",
    model_id="fake-resolver",
    max_context_tokens=8192,
    capabilities=["chat", "json_mode"],
)

NARRATOR_FAKE_PROFILE = ModelProfile(
    name="narrator",
    version="narrate-fake-v1",
    adapter="fake",
    model_id="fake-narrator",
    max_context_tokens=8192,
    capabilities=["chat", "json_mode"],
)

SUMMARY_FAKE_PROFILE = ModelProfile(
    name="summary",
    version="summary-fake-v1",
    adapter="fake",
    model_id="fake-summary",
    max_context_tokens=4096,
    capabilities=["chat", "json_mode"],
)
DIRECTOR_FAKE_PROFILE = ModelProfile(
    name="director",
    version="direct-fake-v1",
    adapter="fake",
    model_id="fake-director",
    max_context_tokens=4096,
    capabilities=["chat", "json_mode"],
)
OPENROUTER_CHAT_PROFILE = ModelProfile(
    name="openrouter",
    version="chat-v1",
    adapter="openrouter",
    model_id="openrouter/auto",
    max_context_tokens=128000,
    capabilities=["chat", "json_mode"],
)

OPENROUTER_EMBED_PROFILE = ModelProfile(
    name="openrouter",
    version="embed-v1",
    adapter="openrouter",
    model_id="openai/text-embedding-3-small",
    max_context_tokens=8192,
    capabilities=["embed"],
)

PROFILES: dict[tuple[str, str], ModelProfile] = {
    (profile.name, profile.version): profile
    for profile in (
        FAKE_TEST_PROFILE,
        STAGE0_SCRIPTED_PROFILE,
        CHARACTER_FAKE_PROFILE,
        REACTION_FAKE_PROFILE,
        RESOLVER_FAKE_PROFILE,
        NARRATOR_FAKE_PROFILE,
        OPENROUTER_CHAT_PROFILE,
        OPENROUTER_EMBED_PROFILE,
    )
}


def get_profile(name: str, version: str) -> ModelProfile:
    try:
        return PROFILES[(name, version)]
    except KeyError as exc:
        raise UnknownProfileError(f"unknown model profile: {name}@{version}") from exc
