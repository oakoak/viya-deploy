"""
Формат сборки и операции над архивом — упаковка И распаковка в ОДНОМ модуле.

Именно это даёт гарантию, к которой мы стремимся: сборщик и разворачиватель — один код,
один формат, одна FORMAT_VERSION. Сборщик физически не может записать манифест, который
разворачиватель не прочитает.

Архив: build-<name>.tar.gz, внутри один верхний каталог <name>/, а в нём:
    <name>/env/...          - каталоги верхнего уровня репозитория, попавшие в сборку
    <name>/jobs/...
    <name>/BUILD_INFO       - метаданные сборки (KEY=VALUE)
"""
import io
import os
import shutil
import subprocess
import tarfile
import tempfile

from amldeploy.version import FORMAT_VERSION, TOOL_VERSION

# Каталоги верхнего уровня репозитория, попадающие в сборку. Добавление нового каталога сюда
# автоматически даёт ему симлинк на сервере (release.switch_to_build перебирает всё, что внутри).
BUILD_CONTENT_DIRS = ["env", "jobs"]
BUILD_INFO_NAME = "BUILD_INFO"


def format_build_info(build_name, commit, date_iso):
    return (
        f"BUILD_NAME={build_name}\n"
        f"FORMAT_VERSION={FORMAT_VERSION}\n"
        f"TOOL_VERSION={TOOL_VERSION}\n"
        f"BUILD_COMMIT={commit}\n"
        f"BUILD_DATE={date_iso}\n"
    )


def parse_build_info(text):
    info = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        info[key.strip()] = value.strip()
    return info


def check_format_version(info):
    """Сверка версии формата из BUILD_INFO с версией инструмента. Бросает RuntimeError при расхождении."""
    got = info.get("FORMAT_VERSION")
    if str(got) != str(FORMAT_VERSION):
        raise RuntimeError(
            f"Версия формата сборки ({got!r}) не совпадает с версией инструмента ({FORMAT_VERSION}). "
            f"Разворачивание отменено, диск не тронут. Обновите aml-deploy на сервере "
            f"или пересоберите архив совместимым инструментом."
        )


def _within(base, target):
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    return target == base or target.startswith(base + os.sep)


def git_archive_dirs(git_ref, dirs, repo_root):
    """tar-байты каталогов dirs из git-ref (git archive) — только закоммиченное, без рабочих правок и мусора."""
    cmd = ["git", "archive", "--format=tar", git_ref, "--", *dirs]
    result = subprocess.run(cmd, cwd=repo_root, check=True, stdout=subprocess.PIPE)
    return result.stdout


def write_archive(archive_path, build_name, content_root, build_info_text):
    """Собрать build-<name>.tar.gz из каталога content_root (его содержимое ложится под <name>/) + BUILD_INFO.
    Вынесено отдельно от git, чтобы упаковку можно было тестировать без git-репозитория."""
    out_dir = os.path.dirname(os.path.abspath(archive_path))
    os.makedirs(out_dir, exist_ok=True)
    with tarfile.open(archive_path, "w:gz") as out:
        for root, dirs, files in os.walk(content_root):
            dirs.sort()
            for fn in sorted(files):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, content_root).replace(os.sep, "/")
                out.add(full, arcname=f"{build_name}/{rel}")
        data = build_info_text.encode("utf-8")
        info_member = tarfile.TarInfo(f"{build_name}/{BUILD_INFO_NAME}")
        info_member.size = len(data)
        out.addfile(info_member, io.BytesIO(data))
    return archive_path


def build_from_git(git_ref, build_name, commit, date_iso, out_dir, repo_root, content_dirs=None):
    content_dirs = content_dirs or BUILD_CONTENT_DIRS
    tar_bytes = git_archive_dirs(git_ref, content_dirs, repo_root)
    tmp = tempfile.mkdtemp()
    try:
        with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as src:
            src.extractall(tmp)  # пути от git — repo-relative (env/..., jobs/...), доверенные
        info = format_build_info(build_name, commit, date_iso)
        archive_path = os.path.join(out_dir, f"build-{build_name}.tar.gz")
        return write_archive(archive_path, build_name, tmp, info)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def read_build_info_from_archive(archive_path):
    """Вернуть (top_dir, info) — имя верхнего каталога и разобранный BUILD_INFO. Без полной распаковки."""
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.isfile() and os.path.basename(member.name) == BUILD_INFO_NAME:
                top = member.name.split("/", 1)[0]
                text = tar.extractfile(member).read().decode("utf-8")
                return top, parse_build_info(text)
    raise RuntimeError("В архиве отсутствует BUILD_INFO, разворачивание отменено")


def extract_archive(archive_path, dest_parent):
    """Безопасная распаковка (проверка на выход за пределы dest_parent — защита от path traversal)."""
    os.makedirs(dest_parent, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            target = os.path.join(dest_parent, member.name)
            if not _within(dest_parent, target):
                raise RuntimeError(f"Небезопасный путь в архиве: {member.name}")
        tar.extractall(dest_parent)
