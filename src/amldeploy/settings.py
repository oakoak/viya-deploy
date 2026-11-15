"""
Разрешение путей окружения БЕЗ переменных окружения: всё вычисляется относительно корня
custom_config, а корень передаётся явно (лаунчер bin/aml-deploy вычисляет его из своего
расположения) либо задаётся флагом --custom-config-root. Env-файл инструмента (aml-deploy.env) можно
переопределить флагом --env-file (используется локальными API-тестами).

Раскладка на сервере:
    custom_config/
      bin/aml-deploy         <- лаунчер; отсюда вычисляется корень (dirname(dirname))
      aml-deploy.env         <- реквизиты Viya для инструмента (не в git, не в сборке)
      tmp/                   <- временные файлы SAS (не переключается)
      logs/
        aml_deploy.log       <- append-only audit-лог инструмента
      build/
        <build_name>/
          BUILD_INFO         <- метаданные сборки
          env/
          jobs/
        .current             <- служебный файл (имя активной сборки)
      current -> build/<build_name>/  (один симлинк на всю активную сборку)
"""
import os

ENV_FILE_NAME = "aml-deploy.env"


class Settings:
    def __init__(self, custom_config_root, env_file=None):
        self.root = os.path.abspath(custom_config_root)
        self._env_file = env_file

    @property
    def env_file_path(self):
        """Env-файл инструмента: custom_config/aml-deploy.env (или путь из --env-file)"""
        if self._env_file:
            return os.path.abspath(self._env_file)
        return os.path.join(self.root, ENV_FILE_NAME)

    @property
    def build_root(self):
        return os.path.join(self.root, "build")

    @property
    def jobs_config_path(self):
        """Путь к jobs/config.yaml (через current symlink)"""
        return os.path.join(self.jobs_path, "config.yaml")

    @property
    def jobs_schema_path(self):
        """Путь к jobs/config.schema.yaml (через current symlink)"""
        return os.path.join(self.jobs_path, "config.schema.yaml")

    @property
    def report_prefix(self):
        return os.path.join(self.logs_dir, "deploy_report")

    @property
    def current_link(self):
        """Симлинк на активную сборку: custom_config/current -> build/<name>"""
        return os.path.join(self.root, "current")

    @property
    def env_path(self):
        """Путь к env (через current symlink): custom_config/current/env"""
        return os.path.join(self.current_link, "env")

    @property
    def jobs_path(self):
        """Путь к jobs (через current symlink): custom_config/current/jobs"""
        return os.path.join(self.current_link, "jobs")

    @property
    def logs_dir(self):
        """Каталог логов (не переключается): custom_config/logs"""
        return os.path.join(self.root, "logs")

    @property
    def audit_log_path(self):
        """Audit-лог инструмента: custom_config/logs/aml_deploy.log"""
        return os.path.join(self.logs_dir, "aml_deploy.log")


def resolve_settings(custom_config_root=None, env_file=None):
    """custom_config_root: из --custom-config-root или от лаунчера; если None — текущий каталог.
    env_file: из --env-file (переопределяет расположение aml-deploy.env)."""
    root = custom_config_root or os.getcwd()
    return Settings(root, env_file=env_file)
