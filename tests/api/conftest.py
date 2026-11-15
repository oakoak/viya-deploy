"""
Фикстуры для API-тестов против реального SAS Viya.

Гейт: если нет deploy/tests/aml-deploy.local.env с непустыми реквизитами — все тесты этого каталога
пропускаются (skip), поэтому обычный юнит-прогон и CI остаются зелёными без доступа к Viya.

Безопасность: каждый тест работает в УНИКАЛЬНОЙ scratch-папке /Environment/__aml_deploy_tests_<uid>
и с уникальным именем модуля M_<uid>. Teardown удаляет только объекты этого uid — существующий
контент дев-стенда не трогается. allow_delete_orphans в тестах НЕ используется (он глобальный).
"""
import os
import uuid

import pytest
import requests

from amldeploy.env_file import VIYA_KEYS, load_env
from amldeploy.viya import folders, job_requests, scheduler
from amldeploy.viya.client import ViyaClient

LOCAL_ENV = os.path.join(os.path.dirname(__file__), "..", "aml-deploy.local.env")


def _local_env():
    if not os.path.isfile(LOCAL_ENV):
        return None
    env = load_env(LOCAL_ENV)
    if any(not env.get(k) for k in VIYA_KEYS):
        return None
    return env


@pytest.fixture(scope="session")
def viya_client():
    env = _local_env()
    if env is None:
        pytest.skip("нет deploy/tests/aml-deploy.local.env с реквизитами Viya — API-тесты пропущены")
    try:
        return ViyaClient.from_env(env)
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Viya недоступен ({e}) — API-тесты пропущены")


@pytest.fixture
def scratch(viya_client):
    uid = uuid.uuid4().hex[:8]
    ctx = {
        "client": viya_client,
        "uid": uid,
        "root_path": f"/Environment/__aml_deploy_tests_{uid}",
        "module": f"M_{uid}",
    }
    try:
        yield ctx
    finally:
        _cleanup(viya_client, ctx["root_path"], ctx["module"])


def _cleanup(client, root_path, module):
    # 1) плоские объекты: наши managed jobRequest'ы этого модуля (+ их расписания)
    try:
        for req in job_requests.find_all_managed(client):
            key = next((p.get("value") for p in (req.get("properties") or [])
                        if p.get("name") == "jobKey"), None)
            if key and key.startswith(f"{module}/"):
                try:
                    scheduler.unschedule(client, req["id"], None, log=lambda *_: None)
                except Exception:
                    pass
                try:
                    job_requests.delete_request(client, req["id"])
                except Exception:
                    pass
    except Exception:
        pass

    # 2) дерево scratch-папки (jobDefinition'ы внутри + подпапки + сама папка)
    try:
        folder = folders.get_folder_by_path(client, root_path)
        if folder:
            _delete_folder_tree(client, f"/folders/folders/{folder['id']}")
    except Exception:
        pass


def _delete_folder_tree(client, folder_uri):
    try:
        members = folders.get_folder_members(client, folder_uri)
    except Exception:
        members = []
    for m in members:
        uri = m.get("uri", "")
        if "/folders/folders/" in uri:
            _delete_folder_tree(client, uri)
        else:
            try:
                client.delete(uri)
            except Exception:
                pass
    try:
        client.delete(folder_uri)
    except Exception:
        pass
