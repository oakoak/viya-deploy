from amldeploy.viya import job_definitions as jd


def test_content_matches_true_ignores_extra_server_keys():
    expected = {"name": "a", "description": "d", "type": "Compute", "code": "c", "parameters": []}
    existing = dict(expected, id="123", version=7, creationTimeStamp="x")
    assert jd.content_matches(existing, expected)


def test_content_matches_false_on_code_change():
    expected = {"name": "a", "type": "Compute", "code": "c1"}
    existing = {"name": "a", "type": "Compute", "code": "c2"}
    assert not jd.content_matches(existing, expected)


def test_content_matches_false_on_parameters_change():
    expected = {"name": "a", "parameters": [{"name": "p", "type": "CHARACTER"}]}
    existing = {"name": "a", "parameters": []}
    assert not jd.content_matches(existing, expected)


def test_content_matches_missing_optional_both_absent():
    expected = {"name": "a", "code": "c"}
    existing = {"name": "a", "code": "c"}  # description/type/parameters отсутствуют в обоих
    assert jd.content_matches(existing, expected)
