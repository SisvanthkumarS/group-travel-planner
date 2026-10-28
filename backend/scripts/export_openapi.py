"""Generate or verify the checked-in API contract without connecting to a database."""

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.main import app  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
target = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
schema = app.openapi()
if args.check:
    if not target.exists() or yaml.safe_load(target.read_text(encoding="utf-8")) != schema:
        sys.exit("OpenAPI drift detected. Run pnpm run openapi and commit docs/openapi.yaml.")
    print("OpenAPI schema is up to date.")
else:
    target.write_text(yaml.safe_dump(schema, sort_keys=False), encoding="utf-8")
