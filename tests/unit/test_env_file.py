import pytest

from amldeploy import env_file


def test_parse_basic():
    text = "a=1\nb = two \n# comment\n\nc=with=eq\n"
    values = env_file.parse_env(text)
    assert values == {"a": "1", "b": "two", "c": "with=eq"}


def test_parse_skips_comments_blank_and_no_eq():
    text = "# only comment\n   \nnoeqhere\nkey=val\n"
    assert env_file.parse_env(text) == {"key": "val"}


def test_empty_value_is_valid_not_missing():
    values = env_file.parse_env("SOME_EMPTY_KEY=\nx=1\n")
    assert "SOME_EMPTY_KEY" in values
    assert values["SOME_EMPTY_KEY"] == ""
    # require: ключ есть -> возвращает пустую строку, не падает
    assert env_file.require(values, "SOME_EMPTY_KEY") == ""


def test_require_missing_raises_keyerror():
    with pytest.raises(KeyError):
        env_file.require({"a": "1"}, "b")


def test_require_nonempty():
    values = {"pass": "", "host": "h"}
    assert env_file.require_nonempty(values, "host") == "h"
    with pytest.raises(ValueError):
        env_file.require_nonempty(values, "pass")
    with pytest.raises(KeyError):
        env_file.require_nonempty(values, "absent")


def test_load_env_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        env_file.load_env(str(tmp_path / "nope.env"))


def test_load_env_roundtrip(tmp_path):
    p = tmp_path / "aml-deploy.env"
    p.write_text("k1=v1\nk2=v2\n", encoding="utf-8")
    assert env_file.load_env(str(p)) == {"k1": "v1", "k2": "v2"}
