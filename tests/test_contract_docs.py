from app.contract_validation import (
    find_broken_markdown_links,
    find_invalid_api_references,
    load_openapi_schema,
    validate_example_files,
    validate_openapi_schema,
)


def test_openapi_schema_is_valid():
    schema = load_openapi_schema()
    assert validate_openapi_schema(schema) == []


def test_markdown_links_are_valid():
    assert find_broken_markdown_links() == []


def test_markdown_runtime_paths_match_openapi():
    schema = load_openapi_schema()
    assert find_invalid_api_references(schema=schema) == []


def test_example_files_are_valid():
    assert validate_example_files() == []
