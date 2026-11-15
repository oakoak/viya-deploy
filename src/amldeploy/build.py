"""
Подкоманда build: собирает архив (env/ + jobs/ + BUILD_INFO) из git-ref.
Выполняется на dev/CI-машине (нужен git). Имя сборки по умолчанию — имя текущей git-ветки
(слеши -> '_').

Проверка config.version == FORMAT_VERSION выполняется ДО упаковки (fail fast) — подключается
вместе с config-loader; здесь оставлен явный хук _validate_config.
"""
import datetime
import os
import subprocess

from amldeploy import archive
from amldeploy import audit_log


def _git(args, repo_root):
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    return result.stdout.strip()


def derive_build_name(git_ref, repo_root):
    name = _git(["rev-parse", "--abbrev-ref", git_ref], repo_root)
    if not name or name == "HEAD":
        raise RuntimeError(
            f"Не удалось определить имя ветки для '{git_ref}'. Задайте имя сборки явно (-n/--name)."
        )
    return name.replace("/", "_")


def _validate_config(repo_root, git_ref, log):
    """Проверка jobs/config.yaml из git-ref (schema + бизнес-правила + version == FORMAT_VERSION),
    ДО упаковки. Валидируется именно то содержимое, что попадёт в архив (из git-ref, не из рабочей
    копии). Fail fast: если версия конфига не совпадает с версией инструмента — сборка не создаётся."""
    from amldeploy.viya.config.loader import load_and_validate_text
    try:
        config_text = _git(["show", f"{git_ref}:jobs/config.yaml"], repo_root)
        schema_text = _git(["show", f"{git_ref}:jobs/config.schema.yaml"], repo_root)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"не удалось прочитать jobs/config.yaml или jobs/config.schema.yaml из git-ref '{git_ref}': {e}"
        )
    load_and_validate_text(config_text, schema_text)
    log("[config] jobs/config.yaml провалидирован (schema + version)")


def run_build(repo_root, build_name=None, git_ref="HEAD", out_dir=None, log=print, settings=None):
    out_dir = out_dir or os.path.join(repo_root, "deploy", "dist")
    build_name = build_name.replace("/", "_") if build_name else derive_build_name(git_ref, repo_root)

    commit = _git(["rev-parse", git_ref], repo_root)
    date_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    _validate_config(repo_root, git_ref, log)

    log(f"Сборка '{build_name}' из {git_ref} ({commit})...")
    try:
        archive_path = archive.build_from_git(git_ref, build_name, commit, date_iso, out_dir, repo_root)
        log(f"Готово: {archive_path}")
        log("Перенесите архив на сервер и разверните через: aml-deploy release <archive>")

        # Логировать в audit-лог если settings передан
        if settings:
            details = audit_log.format_build_info_for_log(build_name, commit, date_iso)
            audit_log.log_action("build", "OK", details, settings.audit_log_path, log=log)

        return archive_path
    except Exception as e:
        if settings:
            audit_log.log_action("build", "FAIL", str(e), settings.audit_log_path, log=log)
        raise
