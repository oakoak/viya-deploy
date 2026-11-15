"""
Загрузка и валидация jobs/config.yaml.

Структура и обязательные поля описаны декларативно в config.schema.yaml (JSON Schema). Здесь —
только то, что JSON Schema плохо выражает (проверка version против FORMAT_VERSION инструмента,
уникальность имён в модуле, валидация timezone) и подстановка констант, которые в 99% случаев
не нужно писать руками (job.type, parameters[].version).

Проверка version == FORMAT_VERSION — это реализация принципа «версия конфига/схемы привязана к
версии сборщика»: config.yaml несёт version, инструмент несёт FORMAT_VERSION, и они обязаны
совпадать. Проверяется и при сборке (build, до упаковки), и при деплое (deploy).

zoneinfo доступен с Python 3.9. На сервере 3.8.8 его может не быть (и backports не установлен) —
тогда валидация timezone деградирует до best-effort (строгая на dev/CI 3.9+, мягкая на 3.8).
"""
import jsonschema
import yaml

from amldeploy.version import FORMAT_VERSION

DEFAULT_JOB_TYPE = "Compute"
DEFAULT_PARAMETER_VERSION = 1

try:  # 3.9+
    import zoneinfo as _zoneinfo
    _available_timezones = _zoneinfo.available_timezones
except ImportError:  # pragma: no cover - зависит от версии python
    try:
        from backports import zoneinfo as _zoneinfo
        _available_timezones = _zoneinfo.available_timezones
    except ImportError:
        _available_timezones = None


def _load_yaml_text(text):
    return yaml.safe_load(text)


def _apply_defaults(config):
    for module in config.get("modules") or []:
        for job in module.get("jobs") or []:
            job.setdefault("type", DEFAULT_JOB_TYPE)
            # description по умолчанию — пустая строка (а не отсутствие поля): update() в
            # job_definitions.py делает ТОЛЬКО поверхностный merge (dict(existing); .update(job)),
            # поэтому ключ, которого нет в job, никогда не перезаписывается и existing["description"]
            # навсегда останется тем, что было (обычно "" с сервера) — а content_matches() сравнивал бы
            # его с None из конфига вечно, на каждом прогоне ("изменение", которое невозможно погасить).
            # parameters — другой случай: это один ключ верхнего уровня, при апдейте перезаписывается
            # целиком (значит, список параметров сам по себе не нуждается в дефолте отдельных полей —
            # что мы туда положим, то на сервере и останется после первого же реального деплоя).
            job.setdefault("description", "")
            job.setdefault("parameters", [])
            for param in job["parameters"]:
                param.setdefault("version", DEFAULT_PARAMETER_VERSION)


def _check_version(config):
    version = config.get("version")
    if version != FORMAT_VERSION:
        raise RuntimeError(
            f"jobs/config.yaml: version={version!r} не совпадает с версией инструмента "
            f"(FORMAT_VERSION={FORMAT_VERSION}). Обновите aml-deploy или приведите config.yaml "
            f"к поддерживаемой версии."
        )


def _validate_business_rules(config):
    errors = []
    for m_idx, module in enumerate(config.get("modules") or []):
        module_label = module.get("folder_name", f"#{m_idx}")
        names_seen = set()
        for job in module.get("jobs") or []:
            name = job.get("name")
            if name:
                if name in names_seen:
                    errors.append(f"module '{module_label}': дублирующееся имя job'а в конфиге: '{name}'")
                names_seen.add(name)

            schedule = job.get("schedule")
            if not schedule:
                continue
            tz_name = schedule.get("timezone")
            if tz_name and _available_timezones is not None and tz_name not in _available_timezones():
                errors.append(f"module '{module_label}', job '{name}': неизвестная timezone '{tz_name}'")

    if errors:
        raise RuntimeError("Ошибки валидации конфига:\n  - " + "\n  - ".join(errors))


def _validate_against_schema(config, schema):
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    schema_errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))
    if schema_errors:
        formatted = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in schema_errors]
        raise RuntimeError("Ошибки валидации конфига (schema):\n  - " + "\n  - ".join(formatted))


def load_and_validate_text(config_text, schema_text):
    config = _load_yaml_text(config_text)
    schema = _load_yaml_text(schema_text)
    _validate_against_schema(config, schema)
    _check_version(config)
    _validate_business_rules(config)
    _apply_defaults(config)
    return config


def load_and_validate(config_path, schema_path):
    with open(config_path, "r", encoding="utf-8") as f:
        config_text = f.read()
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_text = f.read()
    return load_and_validate_text(config_text, schema_text)
