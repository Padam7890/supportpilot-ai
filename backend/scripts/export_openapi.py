import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# OpenAPI generation imports the application but must not require local service
# credentials or live services. These dummy values are only used to satisfy
# Settings validation; exporting the schema never opens a database or Redis
# connection. Existing environment or .env values still take precedence.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://openapi:openapi@127.0.0.1:1/openapi",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")
os.environ.setdefault(
    "JWT_SECRET",
    "openapi-contract-generation-only-secret-not-for-authentication",
)

from app.main import app


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI contract")
    parser.add_argument("--check", action="store_true", help="Fail if the checked-in schema is stale")
    args = parser.parse_args()

    output = Path(__file__).resolve().parents[1] / "openapi.json"
    rendered = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not output.exists() or output.read_text() != rendered:
            print(f"{output} is stale; run python scripts/export_openapi.py")
            return 1
        return 0

    output.write_text(rendered)
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
