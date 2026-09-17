"""Model-call cost accounting (owned by S3-PROV-001).

Every traced call gets one cost row. The pricing table is versioned
in code and recorded per row, so a later price change never rewrites
history. Two honest estimates exist for unpriced work, both labeled:
provider calls that report no usage are estimated from prompt bytes,
and models absent from the pricing table fall back to the default
rate. Fake calls report zero tokens and land as byte estimates.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: Pricing table version recorded on every row.
PRICING_VERSION = "s3-prov-v1"

#: USD per 1k tokens by model prefix. OpenRouter's `auto` router can
#: serve anything, so unknown models fall back to DEFAULT_RATE and
#: are marked estimated.
_RATES: dict[str, tuple[float, float]] = {
    "openai/gpt-4o-mini": (0.00015, 0.0006),
    "openai/gpt-4o": (0.0025, 0.01),
    "anthropic/claude-3-5-haiku": (0.0008, 0.004),
    "google/gemini-flash-1.5": (0.000075, 0.0003),
    "fake-": (0.0, 0.0),
}
DEFAULT_RATE: tuple[float, float] = (0.001, 0.003)

#: Characters per token for byte-based estimates (matches context accounting).
CHARS_PER_TOKEN = 4


class ModelCost(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: UUID
    pricing_version: str = Field(default=PRICING_VERSION, max_length=32)
    model: str = Field(default="", max_length=256)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    prompt_cost_usd: float = Field(ge=0.0)
    completion_cost_usd: float = Field(ge=0.0)
    estimated: bool = False


def compute_cost(
    call_id: UUID,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    prompt_chars: int,
) -> ModelCost:
    """Cost for one call; byte-estimated when usage is unreported."""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        prompt_tokens = max(1, prompt_chars // CHARS_PER_TOKEN)
        rate = _rate_for(model)
        return ModelCost(
            call_id=call_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
            prompt_cost_usd=prompt_tokens / 1000.0 * rate[0],
            completion_cost_usd=0.0,
            estimated=True,
        )
    rate = _rate_for(model)
    estimated = rate == DEFAULT_RATE and not model.startswith("fake-")
    return ModelCost(
        call_id=call_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        prompt_cost_usd=prompt_tokens / 1000.0 * rate[0],
        completion_cost_usd=completion_tokens / 1000.0 * rate[1],
        estimated=estimated,
    )


def _rate_for(model: str) -> tuple[float, float]:
    for prefix, rate in _RATES.items():
        if model.startswith(prefix):
            return rate
    return DEFAULT_RATE
