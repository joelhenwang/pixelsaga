"""Committed OpenAPI generation (owned by S0-API-001).

Run from the repo root (``make contracts`` does this) so the checked-in
``content/schemas/openapi.json`` always matches the served contract.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldsim.infrastructure.settings import Settings
from worldsim.interfaces.http.app import create_app


def export_openapi(out: Path) -> None:
    app = create_app(Settings())
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export worldsim OpenAPI")
    parser.add_argument("--out", type=Path, default=Path("content/schemas/openapi.json"))
    args = parser.parse_args(argv)
    export_openapi(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
