"""
Разворачивание на сервере: распаковка архива в build/<name>/ и атомарное переключение симлинков
custom_config/<dir> -> build/<name>/<dir> для каждого каталога верхнего уровня сборки. Порт
deploy_env.sh на Python: os.symlink во временную ссылку + os.replace (атомарный rename).

Также умеет переключаться между уже распакованными сборками (switch) и показывать список (list).
Деплой job'ов/расписаний в Viya (второй шаг release/switch) подключается отдельно — здесь только
файловая часть.
"""
import os
import shutil
import tempfile

from amldeploy import archive
from amldeploy import audit_log

CURRENT_MARKER = ".current"

def ensure_scripts_executable(build_dir, log=print):
    """Проставить +x всем *.sh в распакованной сборке.

    Репозиторий смонтирован с Windows (`core.filemode=false`), поэтому исполняемый бит для
    большинства shell-скриптов в env/ никогда не был застейджен в git (в отличие от
    deploy/bin/*, где это сделано явно) — `git archive`/распаковка архива приносят их с
    правами 644, и они не запускаются на сервере без этого шага.
    """
    changed = []
    for root, _dirs, files in os.walk(build_dir):
        for fn in files:
            if not fn.endswith(".sh"):
                continue
            path = os.path.join(root, fn)
            mode = os.stat(path).st_mode
            new_mode = mode | 0o111
            if new_mode != mode:
                os.chmod(path, new_mode)
                changed.append(os.path.relpath(path, build_dir))
    if changed:
        log(f"  [chmod +x] {len(changed)} скрипт(ов): {', '.join(sorted(changed))}")
    return changed


def _read_current(build_root):
    marker = os.path.join(build_root, CURRENT_MARKER)
    if os.path.isfile(marker):
        with open(marker, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def _write_current(build_root, name):
    with open(os.path.join(build_root, CURRENT_MARKER), "w", encoding="utf-8") as f:
        f.write(name)


def switch_to_build(settings, name, log=print):
    """Атомарно переключить симлинк custom_config/current -> build/<name>."""
    build_dir = os.path.join(settings.build_root, name)
    if not os.path.isdir(build_dir):
        raise RuntimeError(f"Сборка '{name}' не найдена в {settings.build_root}")

    try:
        # Переключить симлинк current -> build/<name> (атомарно)
        link_target = os.path.join("build", name)  # относительный target (относительно custom_config)
        link_path = settings.current_link
        tmp_link = os.path.join(settings.root, ".current.new")

        if os.path.islink(tmp_link) or os.path.exists(tmp_link):
            os.remove(tmp_link)
        os.symlink(link_target, tmp_link)
        os.replace(tmp_link, link_path)  # атомарная замена симлинка (одна операция)
        log(f"  current -> {link_target}")
        audit_log.log_action("switch-symlink", "OK", f"build={name}",
                             settings.audit_log_path, log=log)

        _write_current(settings.build_root, name)
        log(f"Активная сборка: {name}")
        return name
    except Exception as e:
        audit_log.log_action("switch", "FAIL", str(e), settings.audit_log_path, log=log)
        raise


def list_builds(settings, log=print):
    build_root = settings.build_root
    if not os.path.isdir(build_root):
        log(f"Каталог сборок не найден: {build_root}")
        return []
    current = _read_current(build_root)
    names = sorted(e for e in os.listdir(build_root) if os.path.isdir(os.path.join(build_root, e)))
    log(f"Доступные сборки в {build_root}:")
    for name in names:
        mark = "  * " if name == current else "    "
        suffix = "  (активна)" if name == current else ""
        log(f"{mark}{name}{suffix}")
    return names


def deploy_archive(settings, archive_path, log=print):
    """Распаковать архив в build/<name>/ (с проверкой FORMAT_VERSION) и переключиться на него."""
    if not os.path.isfile(archive_path):
        raise RuntimeError(f"Файл '{archive_path}' не найден")

    try:
        top, info = archive.read_build_info_from_archive(archive_path)
        archive.check_format_version(info)
        build_name = info.get("BUILD_NAME") or top

        log(f"Распаковка архива...")
        audit_log.log_action("release-start", "OK", audit_log.format_archive_info_for_log(archive_path),
                             settings.audit_log_path, log=log)

        os.makedirs(settings.build_root, exist_ok=True)
        tmp = tempfile.mkdtemp()
        try:
            archive.extract_archive(archive_path, tmp)
            extracted = os.path.join(tmp, top)
            if not os.path.isdir(extracted):
                raise RuntimeError(f"В архиве не найден ожидаемый каталог сборки '{top}'")
            target = os.path.join(settings.build_root, build_name)
            if os.path.exists(target):
                log(f"Внимание: сборка '{build_name}' уже распакована ранее, будет перезаписана.")
                shutil.rmtree(target)
            shutil.move(extracted, target)
            log(f"Сборка '{build_name}' распакована в {target}")
            audit_log.log_action("release-extract", "OK", f"build={build_name}",
                                 settings.audit_log_path, log=log)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # Проставить +x на *.sh — git на Windows-маунте не хранит исполняемый бит (см. docstring)
        changed = ensure_scripts_executable(target, log=log)
        if changed:
            audit_log.log_action("chmod-scripts", "OK", f"build={build_name} count={len(changed)}",
                                 settings.audit_log_path, log=log)

        switch_to_build(settings, build_name, log=log)
        audit_log.log_action("release-finish", "OK", f"build={build_name}",
                             settings.audit_log_path, log=log)
        return build_name
    except Exception as e:
        audit_log.log_action("release", "FAIL", str(e), settings.audit_log_path, log=log)
        raise
