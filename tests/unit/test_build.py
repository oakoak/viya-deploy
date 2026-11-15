import os
import subprocess

import pytest

from amldeploy import archive, build

# Реальная схема из репозитория — build валидирует config.yaml именно против неё.
_REPO_SCHEMA = os.path.join(os.path.dirname(__file__), "..", "..", "..", "jobs", "config.schema.yaml")

VALID_CONFIG = """\
version: 1
root_folder_path: /Environment
modules:
  - folder_name: M
    jobs:
      - name: J
        code: "proc print data=sashelp.class; run;"
"""


def _init_repo(path, config_text=VALID_CONFIG):
    def git(*args):
        subprocess.run(["git", *args], cwd=path, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.makedirs(path, exist_ok=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    git("config", "commit.gpgsign", "false")
    os.makedirs(os.path.join(path, "env", "COR"))
    os.makedirs(os.path.join(path, "jobs"))
    with open(os.path.join(path, "env", "COR", "a.sas"), "w") as f:
        f.write("proc print; run;\n")
    with open(os.path.join(path, "jobs", "config.yaml"), "w") as f:
        f.write(config_text)
    with open(_REPO_SCHEMA, "r", encoding="utf-8") as src, \
            open(os.path.join(path, "jobs", "config.schema.yaml"), "w", encoding="utf-8") as dst:
        dst.write(src.read())
    with open(os.path.join(path, "ignoreme.txt"), "w") as f:
        f.write("not in build\n")
    git("add", "-A")
    git("commit", "-q", "-m", "init")


def test_run_build_produces_archive_with_env_and_jobs(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    out = str(tmp_path / "dist")

    archive_path = build.run_build(repo, build_name="testbuild", git_ref="HEAD",
                                   out_dir=out, log=lambda *_: None)
    assert os.path.isfile(archive_path)
    assert archive_path.endswith("build-testbuild.tar.gz")

    top, info = archive.read_build_info_from_archive(archive_path)
    assert top == "testbuild"
    assert info["BUILD_NAME"] == "testbuild"
    archive.check_format_version(info)
    assert len(info["BUILD_COMMIT"]) >= 7

    dest = str(tmp_path / "unpacked")
    archive.extract_archive(archive_path, dest)
    assert os.path.isfile(os.path.join(dest, "testbuild", "env", "COR", "a.sas"))
    assert os.path.isfile(os.path.join(dest, "testbuild", "jobs", "config.yaml"))
    # только env/ и jobs/ едут в сборку — прочее из репозитория не попадает
    assert not os.path.exists(os.path.join(dest, "testbuild", "ignoreme.txt"))


def test_build_name_slash_becomes_underscore(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    out = str(tmp_path / "dist")
    archive_path = build.run_build(repo, build_name="feature/x", git_ref="HEAD",
                                   out_dir=out, log=lambda *_: None)
    assert archive_path.endswith("build-feature_x.tar.gz")


def test_build_fails_on_config_version_mismatch(tmp_path):
    # config.version=2, а FORMAT_VERSION инструмента=1 -> build падает ДО упаковки
    bad = VALID_CONFIG.replace("version: 1", "version: 2")
    repo = str(tmp_path / "repo")
    _init_repo(repo, config_text=bad)
    out = str(tmp_path / "dist")
    with pytest.raises(RuntimeError, match="version"):
        build.run_build(repo, build_name="b", git_ref="HEAD", out_dir=out, log=lambda *_: None)
    assert not os.path.exists(os.path.join(out, "build-b.tar.gz"))
