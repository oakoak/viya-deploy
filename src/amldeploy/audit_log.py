"""
Append-only audit-лог для отслеживания всех действий deploy-инструмента.
Формат: TIMESTAMP | ACTION | STATUS | DETAILS
Статусы: OK (успех), FAIL (ошибка), WARN (предупреждение)
"""
import os
import datetime


def log_action(action, status, details, log_file, log=print):
    """Записать действие в audit-лог (append-only).

    Args:
        action: Название действия (build, release, switch, stop-service, start-service, etc.)
        status: Статус (OK, FAIL, WARN)
        details: Дополнительные детали (имя сборки, сообщение об ошибке и т.д.)
        log_file: Путь к файлу audit-лога
        log: Функция логирования (print по умолчанию)
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Экранировать | и новые строки в details
    safe_details = details.replace("|", "\\|").replace("\n", "\\n") if details else ""
    line = f"{timestamp} | {action:20s} | {status:6s} | {safe_details}\n"

    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
        log(f"[audit] {action:20s} {status:6s}")
    except OSError as e:
        log(f"[audit] Ошибка при записи лога: {e}")


def format_build_info_for_log(build_name, commit, date_iso):
    """Форматировать информацию сборки для audit-лога."""
    return f"build={build_name} commit={commit[:7]} date={date_iso}"


def format_archive_info_for_log(archive_path):
    """Форматировать информацию архива для audit-лога."""
    return f"archive={os.path.basename(archive_path)} size={os.path.getsize(archive_path)} bytes"
