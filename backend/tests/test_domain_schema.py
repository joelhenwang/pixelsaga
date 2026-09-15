import json
from pathlib import Path

from worldsim.domain.schema import REGISTRY, export_bundle

COMMITTED = Path(__file__).parent.parent.parent / "content" / "schemas" / "domain-schema.json"


def test_schema_bundle_covers_registry_and_matches_committed() -> None:
    bundle = export_bundle()
    assert bundle["schema_version"] == 1
    assert set(bundle["models"]) == {model.__name__ for model in REGISTRY}
    assert "WorldEventRecord" in bundle["models"]
    assert "MoveAction" in bundle["models"]
    committed = json.loads(COMMITTED.read_text(encoding="utf-8"))
    assert committed == bundle
