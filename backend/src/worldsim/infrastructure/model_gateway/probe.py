"""Manual live OpenRouter probe (owned by S0-MODEL-001).

Opt-in only: set ``WORLDSIM_MODEL_LIVE_PROBE=1`` plus
``WORLDSIM_PROVIDER__OPENROUTER_API_KEY``. Capped at ten seconds, never
part of any promotion gate.
"""

from __future__ import annotations

import asyncio
import os
import sys

from pydantic import SecretStr

from worldsim.infrastructure.model_gateway.openrouter import OpenRouterGateway
from worldsim.infrastructure.model_gateway.profiles import get_profile
from worldsim.infrastructure.settings import get_settings

PROBE_TIMEOUT_S = 10.0


def main(argv: list[str]) -> int:
    if os.environ.get("WORLDSIM_MODEL_LIVE_PROBE") != "1":
        print(
            "refusing live probe: set WORLDSIM_MODEL_LIVE_PROBE=1 "
            "and WORLDSIM_PROVIDER__OPENROUTER_API_KEY",
            file=sys.stderr,
        )
        return 2
    del argv
    settings = get_settings()
    key = settings.provider.openrouter_api_key
    if key is None:
        print("refusing live probe: no OpenRouter API key configured", file=sys.stderr)
        return 2
    api_key = SecretStr(key.get_secret_value())
    profile = get_profile("openrouter", "chat-v1")
    gateway = OpenRouterGateway(
        profile,
        api_key=api_key,
        base_url=settings.provider.openrouter_base_url,
        timeout_s=PROBE_TIMEOUT_S,
    )

    async def _probe() -> int:
        result = await gateway.probe()
        print(result.model_dump_json())
        return 0 if result.ok else 1

    return asyncio.run(_probe())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
