from app.contract_validation import find_broken_markdown_links, find_documented_unknown_api_paths, load_openapi_schema, validate_example_files, validate_openapi_schema


def test_openapi_schema_is_valid():
    schema = load_openapi_schema()
    assert validate_openapi_schema(schema) == []


def test_markdown_links_are_valid():
    assert find_broken_markdown_links() == []


def test_example_files_are_valid():
    assert validate_example_files() == []


def test_docs_do_not_reference_unknown_api_paths():
    schema = load_openapi_schema()
    assert find_documented_unknown_api_paths(schema=schema) == []
