from app.contract_validation import find_broken_markdown_links, load_openapi_schema, validate_example_files, validate_openapi_schema


def test_openapi_contract_is_coherent():
    schema = load_openapi_schema()
    assert validate_openapi_schema(schema) == []


def test_examples_json_are_valid_against_models():
    assert validate_example_files() == []


def test_markdown_local_links_resolve():
    assert find_broken_markdown_links() == []
