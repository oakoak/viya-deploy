import os

import pytest

from amldeploy.version import FORMAT_VERSION
from amldeploy.viya.config import loader

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "jobs", "config.schema.yaml")
with open(_SCHEMA_PATH, "r", encoding="utf-8") as _f:
    SCHEMA_TEXT = _f.read()

VALID = f"""\
version: {FORMAT_VERSION}
root_folder_path: /Environment
modules:
  - folder_name: M
    jobs:
      - name: J
        code: "proc print; run;"
        parameters:
          - name: p
            type: CHARACTER
        schedule:
          type: daily
          every: 1
          at: "03:00"
"""


def _load(text):
    return loader.load_and_validate_text(text, SCHEMA_TEXT)


def test_valid_config_applies_defaults():
    cfg = _load(VALID)
    job = cfg["modules"][0]["jobs"][0]
    assert job["type"] == "Compute"                 # дефолт job.type
    assert job["parameters"][0]["version"] == 1     # дефолт parameters[].version


def test_defaults_add_empty_parameters_list():
    cfg = f"""\
version: {FORMAT_VERSION}
root_folder_path: /Environment
modules:
  - folder_name: M
    jobs:
      - name: NoParams
        code: "x"
"""
    job = _load(cfg)["modules"][0]["jobs"][0]
    assert job["parameters"] == []          # каноническая форма сервера -> идемпотентность
    assert job["type"] == "Compute"


def test_defaults_add_empty_description():
    cfg = f"""\
version: {FORMAT_VERSION}
root_folder_path: /Environment
modules:
  - folder_name: M
    jobs:
      - name: J
        code: "x"
"""
    job = _load(cfg)["modules"][0]["jobs"][0]
    # update() мержит только верхнеуровневые ключи, присутствующие в job -> без дефолта здесь
    # "изменение" (None != "") никогда не сходится, сколько раз job ни передеплоивай.
    assert job["description"] == ""


def test_version_mismatch_raises():
    bad = VALID.replace(f"version: {FORMAT_VERSION}", f"version: {FORMAT_VERSION + 99}")
    with pytest.raises(RuntimeError, match="version"):
        _load(bad)


def test_schema_error_missing_root_folder_path():
    bad = VALID.replace("root_folder_path: /Environment\n", "")
    with pytest.raises(RuntimeError, match="schema"):
        _load(bad)


def test_duplicate_job_name_raises():
    dup = f"""\
version: {FORMAT_VERSION}
root_folder_path: /Environment
modules:
  - folder_name: M
    jobs:
      - name: J
        code: "a"
      - name: J
        code: "b"
"""
    with pytest.raises(RuntimeError, match="дубл"):
        _load(dup)


def test_unknown_timezone_raises():
    bad = VALID.replace('at: "03:00"', 'at: "03:00"\n          timezone: Mars/Phobos')
    with pytest.raises(RuntimeError, match="timezone"):
        _load(bad)


def test_bad_schedule_time_pattern_rejected_by_schema():
    bad = VALID.replace('at: "03:00"', 'at: "3am"')
    with pytest.raises(RuntimeError, match="schema"):
        _load(bad)
