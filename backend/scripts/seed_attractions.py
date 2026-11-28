"""Create or update curated attractions from a JSON file. Safe to run repeatedly.

Usage:
    uv run --project backend python backend/scripts/seed_attractions.py
    uv run --project backend python backend/scripts/seed_attractions.py path/to/file.json

The file holds a JSON array of attraction objects; see backend/data/attractions.json.
Rows are matched by name and city (ignoring case) and replaced with the file's
values. To hide an attraction from travelers, set "is_active": false and rerun.
"""

import json
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.core.database import SessionLocal  # noqa: E402
from backend.app.schemas.attraction import AttractionSeedFile  # noqa: E402
from backend.app.services.AttractionService import AttractionService  # noqa: E402

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "data" / "attractions.json"


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FILE
    try:
        file = AttractionSeedFile(attractions=json.loads(source.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"Cannot read {source}: {exc}", file=sys.stderr)
        return 1
    with SessionLocal() as session:
        try:
            result = AttractionService(session).seed(file)
        except ValueError as exc:
            print(f"Import failed: {exc}", file=sys.stderr)
            return 1
    print(f"Attractions imported: {result.created} created, {result.updated} updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
