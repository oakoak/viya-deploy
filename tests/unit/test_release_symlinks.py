import os

import pytest

from amldeploy import archive, release
from amldeploy.settings import resolve_settings


def _make_build(root, name, files):
    """Создать build/<name>/ с каталогами и файлами {rel_path: content}. Плюс BUILD_INFO."""
    build_dir = os.path.join(root, "build", name)
    for rel, content in files.items():
        full = os.path.join(build_dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
    with open(os.path.join(build_dir, "BUILD_INFO"), "w", encoding="utf-8") as f:
        f.write(archive.format_build_info(name, "c", "d"))
    return build_dir


def test_switch_creates_atomic_symlinks(tmp_path):
    root = str(tmp_path / "custom_config")
    _make_build(root, "b1", {"env/a.sas": "x", "jobs/config.yaml": "version: 1"})
    s = resolve_settings(custom_config_root=root)

    release.switch_to_build(s, "b1", log=lambda *_: None)

    env_link = os.path.join(root, "env")
    jobs_link = os.path.join(root, "jobs")
    assert os.path.islink(env_link)
    assert os.readlink(env_link) == os.path.join("build", "b1", "env")
    assert os.path.islink(jobs_link)
    # разрешается через симлинк до реального файла
    assert os.path.isfile(os.path.join(root, "env", "a.sas"))
    # BUILD_INFO (файл, не каталог) не должен получить симлинк
    assert not os.path.exists(os.path.join(root, "BUILD_INFO"))
    # маркер текущей сборки
    with open(os.path.join(root, "build", ".current")) as f:
        assert f.read().strip() == "b1"


def test_switch_flips_between_builds(tmp_path):
    root = str(tmp_path / "custom_config")
    _make_build(root, "b1", {"env/a.sas": "one", "jobs/x": "1"})
    _make_build(root, "b2", {"env/a.sas": "two", "jobs/x": "2"})
    s = resolve_settings(custom_config_root=root)

    release.switch_to_build(s, "b1", log=lambda *_: None)
    assert open(os.path.join(root, "env", "a.sas")).read() == "one"

    release.switch_to_build(s, "b2", log=lambda *_: None)
    assert os.readlink(os.path.join(root, "env")) == os.path.join("build", "b2", "env")
    assert open(os.path.join(root, "env", "a.sas")).read() == "two"


def test_switch_missing_build_raises(tmp_path):
    s = resolve_settings(custom_config_root=str(tmp_path / "custom_config"))
    with pytest.raises(RuntimeError):
        release.switch_to_build(s, "nope", log=lambda *_: None)


def test_list_builds_marks_current(tmp_path):
    root = str(tmp_path / "custom_config")
    _make_build(root, "b1", {"env/a": "1"})
    _make_build(root, "b2", {"env/a": "2"})
    s = resolve_settings(custom_config_root=root)
    release.switch_to_build(s, "b2", log=lambda *_: None)

    lines = []
    names = release.list_builds(s, log=lines.append)
    assert names == ["b1", "b2"]
    joined = "\n".join(lines)
    assert "* b2" in joined and "(активна)" in joined


def test_deploy_archive_end_to_end(tmp_path):
    # готовим content -> архив
    content = tmp_path / "content"
    (content / "env").mkdir(parents=True)
    (content / "env" / "a.sas").write_text("hello", encoding="utf-8")
    (content / "jobs").mkdir()
    (content / "jobs" / "config.yaml").write_text("version: 1", encoding="utf-8")
    info = archive.format_build_info("rel1", "c1", "2026-01-01T00:00:00Z")
    archive_path = str(tmp_path / "build-rel1.tar.gz")
    archive.write_archive(archive_path, "rel1", str(content), info)

    root = str(tmp_path / "custom_config")
    s = resolve_settings(custom_config_root=root)
    name = release.deploy_archive(s, archive_path, log=lambda *_: None)

    assert name == "rel1"
    assert os.path.isdir(os.path.join(root, "build", "rel1"))
    assert os.readlink(os.path.join(root, "env")) == os.path.join("build", "rel1", "env")
    assert open(os.path.join(root, "env", "a.sas")).read() == "hello"
