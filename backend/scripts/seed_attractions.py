"""Create or update curated attractions from a JSON file. Safe to run repeatedly.

Usage:
    uv run --project backend python backend/scripts/seed_attractions.py
    uv run --project backend python backend/scripts/seed_attractions.py path/to/file.json

The file holds a JSON array of attraction objects, in the same format as
POST /api/v1/admin/attractions/import. Rows are matched by name and city.
"""

import json
import sys
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.database import SessionLocal  # noqa: E402
from backend.app.schemas.attraction import ImportAttractionsRequest  # noqa: E402
from backend.app.services.AttractionService import AttractionService  # noqa: E402

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "data" / "attractions.json"


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    try:
        body = ImportAttractionsRequest(attractions=json.loads(source.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Cannot read {source}: {exc}", file=sys.stderr)
        return 1
    with SessionLocal() as session:
        try:
            result = AttractionService(session).import_many(body, admin_id=None)
        except HTTPException as exc:
            print(f"Import failed: {exc.detail}", file=sys.stderr)
            return 1
    print(f"Attractions imported: {result.created} created, {result.updated} updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
