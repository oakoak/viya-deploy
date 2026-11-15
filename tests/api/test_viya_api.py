"""
Интеграционные тесты против реального SAS Viya (маркер api). Запускаются только при наличии
deploy/tests/aml-deploy.local.env (иначе skip). Все объекты создаются в scratch-папке и подчищаются
фикстурой scratch (см. conftest.py).
"""
import os

import pytest

from amldeploy.settings import resolve_settings
from amldeploy.viya import deploy as viya_deploy
from amldeploy.viya import folders, job_definitions, job_requests, scheduler

pytestmark = pytest.mark.api

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "jobs", "config.schema.yaml")
LOCAL_ENV = os.path.join(os.path.dirname(__file__), "..", "aml-deploy.local.env")


def _silent(*_a, **_k):
    return None


def test_token_obtained(viya_client):
    assert viya_client.token


def test_ensure_folder_idempotent(scratch):
    c = scratch["client"]
    path = f"{scratch['root_path']}/sub/deep"
    uri1 = folders.ensure_folder_path(c, path, log=_silent)
    uri2 = folders.ensure_folder_path(c, path, log=_silent)
    assert uri1 == uri2
    assert folders.get_folder_by_path(c, path) is not None


def test_job_definition_create_skip_update(scratch):
    c = scratch["client"]
    folder_uri = folders.ensure_folder_path(c, f"{scratch['root_path']}/{scratch['module']}", log=_silent)
    job = {"name": "J1", "type": "Compute", "description": "t",
           "code": "proc options; run;", "parameters": []}
    assert job_definitions.deploy(c, folder_uri, job, log=_silent)["action"] == "created"
    assert job_definitions.deploy(c, folder_uri, job, log=_silent)["action"] == "skipped"
    job2 = dict(job, code="proc print data=sashelp.class; run;")
    assert job_definitions.deploy(c, folder_uri, job2, log=_silent)["action"] == "updated"


def test_schedule_create_match_remove(scratch):
    c = scratch["client"]
    folder_uri = folders.ensure_folder_path(c, f"{scratch['root_path']}/{scratch['module']}", log=_silent)
    job = {"name": "S1", "type": "Compute", "code": "proc options; run;", "parameters": []}
    res = job_definitions.deploy(c, folder_uri, job, log=_silent)
    key = job_requests.build_job_key(scratch["module"], "S1")
    req, _ = job_requests.ensure(c, "S1", res["job_definition_uri"], key, log=_silent)

    sched_cfg = {"type": "daily", "every": 1, "at": "03:00"}
    scheduler.ensure(c, "S1", req["id"], sched_cfg, scheduler.find_all(c), log=_silent)
    found = scheduler.find_for_job_request(c, req["id"])
    assert found is not None
    assert scheduler.schedule_matches(found, sched_cfg)

    assert scheduler.unschedule(c, req["id"], None, log=_silent) is True
    assert scheduler.find_for_job_request(c, req["id"]) is None


def test_end_to_end_deploy_idempotent(scratch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "version: 1\n"
        f"root_folder_path: {scratch['root_path']}\n"
        "modules:\n"
        f"  - folder_name: {scratch['module']}\n"
        "    jobs:\n"
        "      - name: E2E\n"
        '        code: "proc options; run;"\n'
        "        schedule:\n"
        "          type: daily\n"
        "          every: 1\n"
        '          at: "02:00"\n',
        encoding="utf-8",
    )
    settings = resolve_settings(custom_config_root=str(tmp_path), env_file=LOCAL_ENV)

    report = viya_deploy.run(settings, config_path=str(cfg), schema_path=SCHEMA_PATH,
                             report_prefix=str(tmp_path / "rep"), log=_silent)
    assert report.summary["failed"] == 0
    assert report.summary["created"] >= 1
    assert report.summary["schedule_created"] >= 1

    # второй прогон — ничего не поменялось: job пропущен, расписание пропущено
    report2 = viya_deploy.run(settings, config_path=str(cfg), schema_path=SCHEMA_PATH,
                              report_prefix=str(tmp_path / "rep2"), log=_silent)
    assert report2.summary["failed"] == 0
    assert report2.summary["skipped"] >= 1
    assert report2.summary["schedule_skipped"] >= 1
