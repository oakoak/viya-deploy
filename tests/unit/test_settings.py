import os

from amldeploy.settings import resolve_settings


def test_default_paths_relative_to_root(tmp_path):
    root = str(tmp_path / "custom_config")
    s = resolve_settings(custom_config_root=root)
    assert s.env_file_path == os.path.join(s.root, "aml-deploy.env")
    assert s.build_root == os.path.join(s.root, "build")
    assert s.jobs_config_path == os.path.join(s.root, "jobs", "config.yaml")
    assert s.jobs_schema_path == os.path.join(s.root, "jobs", "config.schema.yaml")
    assert s.logs_dir == os.path.join(s.root, "logs")


def test_env_file_override(tmp_path):
    root = str(tmp_path / "custom_config")
    override = str(tmp_path / "local" / "aml-deploy.local.env")
    s = resolve_settings(custom_config_root=root, env_file=override)
    assert s.env_file_path == os.path.abspath(override)
    # остальные пути всё равно от корня
    assert s.build_root == os.path.join(s.root, "build")


def test_default_root_is_cwd_when_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = resolve_settings()
    assert s.root == os.path.abspath(str(tmp_path))
