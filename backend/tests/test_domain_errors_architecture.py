import ast
from pathlib import Path

from worldsim.domain.errors import DomainError, ErrorCode


def test_error_codes_stable_and_carried() -> None:
    assert ErrorCode.VALIDATION_FAILED.value == "validation_failed"
    assert ErrorCode.IDEMPOTENCY_CONFLICT.value == "idempotency_conflict"
    assert ErrorCode.VERSION_CONFLICT.value == "version_conflict"
    error = DomainError(ErrorCode.INVARIANT_VIOLATED, "no duplicate canon", {"key": "phase-1"})
    assert error.code is ErrorCode.INVARIANT_VIOLATED
    assert error.details == {"key": "phase-1"}
    assert str(error) == "no duplicate canon"


def test_domain_imports_only_stdlib_and_pydantic() -> None:
    forbidden = {
        "sqlalchemy",
        "fastapi",
        "langchain",
        "langgraph",
        "httpx",
        "psycopg",
        "alembic",
        "pytest",
        "tests",
    }
    allowed_external = {"pydantic", "pydantic_settings", "typing_extensions"}
    stdlib = set(__import__("sys").stdlib_module_names)
    domain_root = Path(__file__).parent.parent / "src" / "worldsim" / "domain"
    violations: list[str] = []
    for path in sorted(domain_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in stdlib and top not in allowed_external:
                        violations.append(f"{path.name}: import {alias.name}")
                    if top in forbidden:
                        violations.append(f"{path.name}: forbidden {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                module = (node.module or "").split(".")[0]
                if module == "worldsim":
                    full = node.module or ""
                    if full != "worldsim.domain" and not full.startswith("worldsim.domain."):
                        violations.append(f"{path.name}: cross-layer {full}")
                elif module not in stdlib and module not in allowed_external:
                    violations.append(f"{path.name}: from {node.module}")
                if module in forbidden:
                    violations.append(f"{path.name}: forbidden {node.module}")
    assert violations == []
