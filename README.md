# aml-deploy — сборка и деплой env + jobs

Один Python-инструмент (`amldeploy`) и для **сборки**, и для **разворачивания**. Единая
константа `FORMAT_VERSION` внутри пакета — источник правды и для формата архива, и для деплоя,
и для версии `jobs/config.yaml`: собранное этим инструментом гарантированно совместимо с
деплоем этим же инструментом. Старый split на bash+python (`build_env.sh`/`deploy_env.sh`/
`deploy_job.py`/`deploy_viya/`) и старый патч-механизм (`amltool`) удалены.

Каждая сборка — архив с содержимым `env/`, `jobs/` (+ `BUILD_INFO`), который
распаковывается на сервере в версионированную папку `build/<name>/`, а активная версия
переключается симлинком (атомарно). Второй шаг того же
релиза — деплой job definitions и расписаний в SAS Viya по `jobs/config.yaml`. Оба шага —
одной командой `release`.

## Структура

```
deploy/
  pyproject.toml            - пакет amldeploy (src-layout), точка входа aml-deploy
  requirements.txt          - пины рантайма для СЕРВЕРА (Python 3.8, офлайн из wheels/)
  requirements-dev.txt      - pytest + requests-mock для запуска тестов на dev
  bin/
    aml-deploy              - лаунчер (venv python + PYTHONPATH=src + --custom-config-root)
    bootstrap.sh            - однократная установка venv/зависимостей на машине
  src/amldeploy/            - код: cli, build, release, archive, settings, env_file, version,
                              viya/ (client + folders/job_definitions/job_requests/scheduler/…)
  tests/                    - unit/ (offline) и api/ (против реального Viya, gated)
  dist/                     - куда build кладёт архивы (в git не попадает)

jobs/                       - config.yaml + config.schema.yaml (в корне репо, едут в сборку)
```

Сервер (`/opt/sas/aml3/custom_config/` по умолчанию):

```
custom_config/
  aml-deploy.env    - реквизиты Viya ТОЛЬКО для этого инструмента (не в git, не в сборке);
                       с SAS-рантаймом (params.env) не разделяется
  build/
    <build_name>/
      BUILD_INFO      - метаданные сборки (имя, FORMAT_VERSION, TOOL_VERSION, коммит, дата)
      env/            - содержимое env/ на момент сборки
      jobs/           - config.yaml + config.schema.yaml на момент сборки
    .current          - имя активной сборки (служебный файл)
  env  -> build/<build_name>/env    (симлинк, переключается атомарно)
  jobs -> build/<build_name>/jobs   (симлинк, переключается атомарно)
```

Инструмент ставится на машину отдельно (не входит в архив сборки). Пример размещения на
сервере — рядом с custom_config, напр. `/opt/sas/aml3/aml-deploy/` (копия дерева `deploy/`):

```
/opt/sas/aml3/aml-deploy/          <- копия git-каталога deploy/
  bin/aml-deploy  bin/bootstrap.sh  bin/aml-deploy.config (создаёт bootstrap)
  src/  requirements.txt  wheels/ (офлайн-колёса инструмента)  venv/ (создаёт bootstrap)

/opt/sas/aml3/custom_config/       <- рабочий каталог (параметры + сборки + логи)
  bin/
    aml-deploy (лаунчер)
  build/<build_name>/
    env/  jobs/  BUILD_INFO
  current -> build/<active_build>/
  aml-deploy.env <- реквизиты Viya для инструмента (не переключается)
  logs/
    aml_deploy.log
```

Каждый каталог верхнего уровня внутри `build/<name>/` (кроме `BUILD_INFO`) получает свой
симлинк в `custom_config/` с тем же именем. Сейчас это `env` и `jobs`; появятся другие —
для них автоматически появятся симлинки, менять код не нужно.

## Версии — что с чем связано

- `BUILD_NAME` — имя/версия конкретной сборки (по умолчанию имя git-ветки, слеши → `_`; `-n`
  задаёт явно). Это «что развёрнуто».
- `FORMAT_VERSION` (в `src/amldeploy/version.py`) — версия контракта: структура архива, состав
  `BUILD_INFO` **и** обязательное поле `version:` в `jobs/config.yaml`. Меняется только когда
  меняется сам механизм, не при обычных релизах.
- Проверки `FORMAT_VERSION`:
  - **при сборке** (`build`) — `jobs/config.yaml: version` обязан совпасть с `FORMAT_VERSION`
    инструмента (fail-fast до упаковки);
  - **при деплое** (`release`/`deploy`) — `BUILD_INFO: FORMAT_VERSION` из архива и `version` в
    конфиге сверяются с `FORMAT_VERSION` инструмента. Несовпадение → стоп, ничего не меняется.
  Это ловит рассинхрон «на сервере старый инструмент, а сборка по новому формату» (и наоборот).

## Установка

**Dev (машина разработчика, любой современный Python 3.9+):**

```
pip install -e deploy                      # пакет + рантайм-зависимости (requests/PyYAML/jsonschema)
pip install -r deploy/requirements-dev.txt # pytest + requests-mock (для тестов)
```

Дальше можно звать `aml-deploy …` (console-script из pyproject) или `python -m amldeploy …`.

**Сервер (Python 3.8.8, без доступа в PyPI):**

1. **На машине с интернетом** — скачать offline wheels для инструмента deploy:

   ```bash
   pip download -r deploy/requirements.txt \
     --dest deploy/wheels \
     --platform manylinux2014_x86_64 \
     --python-version 38 \
     --implementation cp \
     --abi cp38 \
     --only-binary=:all:
   ```

   **При добавлении новых зависимостей** — пересчитать wheels (повторить команды выше с
   флагом `--upgrade`). Весь каталог `deploy/wheels/` затем скопировать на сервер.

2. **Установить инструмент** на сервере, выполнить bootstrap один раз:

   ```bash
   bin/bootstrap.sh /opt/sas/aml3/custom_config
   ```

   bootstrap создаёт venv в `<tool>/venv`, ставит зависимости офлайн из `deploy/wheels/`
   (или онлайн, если wheels пуст), и запоминает путь custom_config в `bin/aml-deploy.config`.
   После этого лаунчер `bin/aml-deploy` сам подставляет `--custom-config-root` — переменные
   окружения не нужны.

## Команды

```
aml-deploy build [-n имя] [-r git-ref] [-o каталог]   # собрать архив env+jobs из git   [dev/CI]
aml-deploy list                                       # какие сборки распакованы и активна [сервер]
aml-deploy switch <name> [--no-viya]                  # переключить симлинки на сборку (+Viya)
aml-deploy release <archive> [--no-viya] [--dry-run]  # распаковать + переключить + задеплоить Viya
aml-deploy deploy [--dry-run] [--allow-delete] [--allow-delete-orphans]  # только Viya по текущему конфигу
```

Сборка (у разработчика/CI, из корня репозитория):

```
aml-deploy build                 # имя сборки = текущая ветка
aml-deploy build -n release_1.4  # явное имя
aml-deploy build -r <git-ref>    # из конкретного коммита/тега, не из HEAD
# результат: deploy/dist/build-<имя>.tar.gz
```

Разворачивание на сервере (архив переносится руками — scp/rsync):

```
bin/aml-deploy release build-release_1.4.tar.gz   # полный релиз: env-симлинки + job'ы/расписания
bin/aml-deploy list                               # список сборок, активная помечена *
bin/aml-deploy switch release_1.3                 # откат/переключение на распакованную ранее сборку
bin/aml-deploy release build-release_1.4.tar.gz --dry-run   # показать Viya-изменения, не применяя
```

`switch`/`release` после переключения симлинков передеплоивают job definitions и расписания в
Viya по `custom_config/jobs/config.yaml`; `--no-viya` пропускает этот шаг. SAS-код, который
вызывают job'ы, ссылается на стабильный путь `custom_config/env` (симлинк) — сами job definition
при каждом релизе менять не нужно.

## aml-deploy.env и реквизиты Viya

Реквизиты Viya деплой берёт из отдельного env-файла инструмента `custom_config/aml-deploy.env`
(формат `KEY=VALUE`; не зависит от переменных окружения процесса и от SAS-шного `params.env`):

```
AML_DEPLOY_VIYA_TENANT=      # https://<TENANT>.<HOST>
AML_DEPLOY_VIYA_HOST=
AML_DEPLOY_VIYA_USER=
AML_DEPLOY_VIYA_PASSWORD=
```

Все четыре ключа обязательны и должны быть непустыми. Шаблон — `tests/aml-deploy.local.env.example`.
Путь берётся из `--custom-config-root` (его подставляет лаунчер) и переопределяется флагом
`--env-file` (для локального прогона против тестового Viya — см. `tests/`). Файл содержит секрет —
в git и в сборку не попадает.

**Миграция:** на сервере создайте `custom_config/aml-deploy.env` с ключами выше (значения —
из прежних `mvgViyaActiveTenantName`, `mvgViyaHost`, `mvgViyaAdminUserName`, `mvgViyaAdminUserPass`
в `params.env`); из `params.env` деплой больше ничего не читает.

## Тесты

```
cd deploy
pytest tests/unit           # офлайн, без Viya
pytest -m api               # против реального SAS Viya — только при наличии tests/aml-deploy.local.env
pytest                      # всё; api-тесты авто-skip без aml-deploy.local.env
```

`tests/aml-deploy.local.env` (в git не входит) — реквизиты тестового Viya для api-тестов. Шаблон —
`tests/aml-deploy.local.env.example`. Api-тесты создают объекты только в уникальной scratch-папке и
подчищают за собой (см. `tests/api/conftest.py`).

## Не сделано (зафиксировано в /workspace/CLAUDE.md)

- Автоматизация переноса архива по сети (сейчас — руками, scp/rsync).
- Импорт DDL/DML/WebDAV в БД при изменениях — взамен ушедшего в патч-механизм.
- Сборка/деплой custom VI (Angular) — отдельно от `env/`.
