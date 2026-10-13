"""Print the OpenAPI schema as JSON, for generating the frontend's TypeScript types.

Usage:  uv run python -m app.export_openapi > openapi.json

Paths are written relative to the API prefix (e.g. "/health", not "/mail-in-xas/api/health"),
so one schema serves every environment; the frontend adds the prefix at runtime.
No database connection is needed.
"""

import json
import sys

from app.config import Settings
from app.main import create_app


def build_schema() -> dict[str, object]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="local",
        mongodb_uri="mongodb://unused",
        mongodb_db="unused",
    )
    schema = create_app(settings).openapi()
    prefix = settings.api_prefix
    schema["paths"] = {path.removeprefix(prefix): item for path, item in schema["paths"].items()}
    return schema


if __name__ == "__main__":
    json.dump(build_schema(), sys.stdout, indent=2)
    sys.stdout.write("\n")
