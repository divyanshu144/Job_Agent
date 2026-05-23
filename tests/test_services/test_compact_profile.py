from backend.services.profile_builder import build_compact_profile


def test_includes_yaml_and_cv():
    result = build_compact_profile("name: Alice\nskills: [Python]", "Five years of ML engineering.")
    assert "name: Alice" in result
    assert "Five years" in result


def test_truncates_cv_at_500_chars():
    long_cv = "x" * 1000
    result = build_compact_profile("name: Alice", long_cv)
    assert result.count("x") == 500


def test_does_not_include_github_readmes():
    result = build_compact_profile("name: Alice", "cv text")
    assert "## GitHub:" not in result
