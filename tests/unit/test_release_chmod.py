import os
import stat

from amldeploy import archive, release
from amldeploy.settings import resolve_settings


def test_ensure_scripts_executable_sets_bit_only_on_sh(tmp_path):
    build_dir = tmp_path / "build" / "b1"
    sh_path = build_dir / "env" / "COR" / "scripts" / "get_param.sh"
    sas_path = build_dir / "env" / "COR" / "macro" / "m_x.sas"
    os.makedirs(sh_path.parent, exist_ok=True)
    os.makedirs(sas_path.parent, exist_ok=True)
    sh_path.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    sas_path.write_text("%put hi;", encoding="utf-8")
    os.chmod(sh_path, 0o644)
    os.chmod(sas_path, 0o644)

    changed = release.ensure_scripts_executable(str(build_dir), log=lambda *_: None)

    assert os.path.join("env", "COR", "scripts", "get_param.sh") in changed
    assert os.stat(sh_path).st_mode & stat.S_IXUSR
    # .sas файлы не трогаем
    assert not (os.stat(sas_path).st_mode & stat.S_IXUSR)


def test_ensure_scripts_executable_is_idempotent(tmp_path):
    build_dir = tmp_path / "build" / "b1"
    sh_path = build_dir / "env" / "a.sh"
    os.makedirs(sh_path.parent, exist_ok=True)
    sh_path.write_text("#!/bin/bash\n", encoding="utf-8")
    os.chmod(sh_path, 0o755)

    changed = release.ensure_scripts_executable(str(build_dir), log=lambda *_: None)

    assert changed == []


def test_deploy_archive_marks_sh_scripts_executable(tmp_path):
    # архив с .sh как 644 (git на Windows-маунте не сохраняет исполняемый бит)
    content = tmp_path / "content"
    scripts_dir = content / "env" / "VI" / "scripts"
    os.makedirs(scripts_dir, exist_ok=True)
    script = scripts_dir / "vi_reindex.sh"
    script.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    os.chmod(script, 0o644)

    info = archive.format_build_info("rel1", "c1", "2026-01-01T00:00:00Z")
    archive_path = str(tmp_path / "build-rel1.tar.gz")
    archive.write_archive(archive_path, "rel1", str(content), info)

    root = str(tmp_path / "custom_config")
    s = resolve_settings(custom_config_root=root)
    release.deploy_archive(s, archive_path, log=lambda *_: None)

    deployed_script = os.path.join(root, "build", "rel1", "env", "VI", "scripts", "vi_reindex.sh")
    assert os.stat(deployed_script).st_mode & stat.S_IXUSR
