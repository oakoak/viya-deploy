"""
Разбор env-файла инструмента aml-deploy (KEY=VALUE). Это ОТДЕЛЬНЫЙ файл только для деплой-тулинга
(по умолчанию custom_config/aml-deploy.env), он не разделяется с SAS-рантаймом (params.env) и
не зависит от переменных окружения процесса.

Формат:
  - одна пара KEY=VALUE на строку;
  - строки, начинающиеся с '#', и пустые строки — пропускаются;
  - строки без '=' — игнорируются;
  - значение берётся до конца строки (split по первому '='), пробелы по краям обрезаются;
  - '=' внутри значения сохраняется.

Пустое значение (KEY=) ВАЛИДНО и отличается от «ключ отсутствует» (см. require / require_nonempty).
"""
import os

# Имена ключей aml-deploy.env
KEY_VIYA_TENANT = "AML_DEPLOY_VIYA_TENANT"
KEY_VIYA_HOST = "AML_DEPLOY_VIYA_HOST"
KEY_VIYA_USER = "AML_DEPLOY_VIYA_USER"
KEY_VIYA_PASSWORD = "AML_DEPLOY_VIYA_PASSWORD"
VIYA_KEYS = (KEY_VIYA_TENANT, KEY_VIYA_HOST, KEY_VIYA_USER, KEY_VIYA_PASSWORD)


def parse_env(text):
    values = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_env(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Env-файл aml-deploy не найден: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return parse_env(f.read())


def require(values, key, path=None):
    """Значение ключа; ошибка только если ключа НЕТ (пустая строка — валидна)."""
    if key not in values:
        where = f" в {path}" if path else ""
        raise KeyError(f"В env-файле aml-deploy не задан обязательный параметр '{key}'{where}")
    return values[key]


def require_nonempty(values, key, path=None):
    """Значение ключа; ошибка если ключа нет ИЛИ значение пустое. Для реквизитов (пароли, хосты)."""
    value = require(values, key, path)
    if value == "":
        where = f" в {path}" if path else ""
        raise ValueError(f"Параметр '{key}' пуст{where}, а требуется непустое значение")
    return value
