from app.export_openapi import build_schema


def test_schema_paths_are_relative_to_api_prefix() -> None:
    paths = build_schema()["paths"]
    assert isinstance(paths, dict)
    assert "/health" in paths
    assert not any(path.startswith("/mail-in-xas") for path in paths)
