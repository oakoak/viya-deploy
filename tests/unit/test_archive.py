import os

import pytest

from amldeploy import archive
from amldeploy.version import FORMAT_VERSION


def test_build_info_roundtrip():
    text = archive.format_build_info("mybuild", "abc123", "2026-01-01T00:00:00Z")
    info = archive.parse_build_info(text)
    assert info["BUILD_NAME"] == "mybuild"
    assert info["FORMAT_VERSION"] == str(FORMAT_VERSION)
    assert info["BUILD_COMMIT"] == "abc123"


def test_check_format_version_ok():
    archive.check_format_version({"FORMAT_VERSION": str(FORMAT_VERSION)})


def test_check_format_version_mismatch():
    with pytest.raises(RuntimeError):
        archive.check_format_version({"FORMAT_VERSION": str(FORMAT_VERSION + 1)})
    with pytest.raises(RuntimeError):
        archive.check_format_version({})  # нет ключа -> тоже несовпадение


def _make_content(tmp_path):
    content = tmp_path / "content"
    (content / "env" / "COR").mkdir(parents=True)
    (content / "env" / "COR" / "a.sas").write_text("proc print; run;\n", encoding="utf-8")
    (content / "jobs").mkdir()
    (content / "jobs" / "config.yaml").write_text("version: 1\n", encoding="utf-8")
    return content


def test_write_read_extract_roundtrip(tmp_path):
    content = _make_content(tmp_path)
    info = archive.format_build_info("b1", "commit1", "2026-01-01T00:00:00Z")
    archive_path = str(tmp_path / "dist" / "build-b1.tar.gz")
    archive.write_archive(archive_path, "b1", str(content), info)
    assert os.path.isfile(archive_path)

    top, parsed = archive.read_build_info_from_archive(archive_path)
    assert top == "b1"
    assert parsed["BUILD_NAME"] == "b1"
    archive.check_format_version(parsed)

    dest = str(tmp_path / "unpacked")
    archive.extract_archive(archive_path, dest)
    assert os.path.isfile(os.path.join(dest, "b1", "env", "COR", "a.sas"))
    assert os.path.isfile(os.path.join(dest, "b1", "jobs", "config.yaml"))
    assert os.path.isfile(os.path.join(dest, "b1", "BUILD_INFO"))
