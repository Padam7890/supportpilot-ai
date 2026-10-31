import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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
