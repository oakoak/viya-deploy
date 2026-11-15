"""
Анализ "плоских" коллекций jobRequests/scheduler (у них нет родительской папки, поэтому cleanup.py
по SAS Content их не видит — здесь отдельная логика):

- our_orphan_requests: наши (managedBy=deploy_job), но jobKey не входит в текущий конфиг ->
  кандидаты на удаление (наша ответственность).
- unmanaged_requests_on_our_definitions: НЕ наши jobRequest, но ссылаются на jobDefinition, которым
  мы управляем ("левый jobRequest на нашем job'е") -> только предупреждение, не трогаем.
- broken_requests / broken_schedulers: битые ссылки (jobRequest -> удалённый jobDefinition,
  scheduler -> удалённый jobRequest) по всему окружению -> активно рекомендуем удалить.
"""
from amldeploy.viya.job_requests import MANAGED_BY, find_all_by_job_definition_uri, find_all_managed


def _prop(item, name):
    for prop in item.get("properties") or []:
        if prop.get("name") == name:
            return prop.get("value")
    return None


def summarize(item):
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "createdBy": item.get("createdBy"),
        "creationTimeStamp": item.get("creationTimeStamp"),
        "modifiedBy": item.get("modifiedBy"),
        "modifiedTimeStamp": item.get("modifiedTimeStamp"),
    }


def find_orphan_managed_requests(client, expected_job_keys):
    managed = find_all_managed(client)
    return [r for r in managed if _prop(r, "jobKey") not in expected_job_keys]


def find_unmanaged_on_our_definitions(client, job_definition_uris):
    unmanaged = []
    for def_uri in job_definition_uris:
        for req in find_all_by_job_definition_uri(client, def_uri):
            if _prop(req, "managedBy") != MANAGED_BY:
                unmanaged.append({**summarize(req), "jobDefinitionUri": def_uri})
    return unmanaged


def find_broken_links(client, all_job_requests=None, all_scheduler_jobs=None):
    all_job_requests = all_job_requests if all_job_requests is not None else client.get_all_items("/jobExecution/jobRequests")
    all_scheduler_jobs = all_scheduler_jobs if all_scheduler_jobs is not None else client.get_all_items("/scheduler/jobs")

    valid_request_ids = {r["id"] for r in all_job_requests}
    broken_schedulers = []
    for sched in all_scheduler_jobs:
        uri = (sched.get("request") or {}).get("uri", "")
        parts = uri.strip("/").split("/")
        if len(parts) >= 3 and parts[0] == "jobExecution" and parts[1] == "jobRequests":
            if parts[2] not in valid_request_ids:
                broken_schedulers.append(summarize(sched))

    unique_def_uris = {r["jobDefinitionUri"] for r in all_job_requests if r.get("jobDefinitionUri")}
    definition_exists = {uri: client.get_json(uri) is not None for uri in unique_def_uris}
    broken_requests = [
        {**summarize(r), "jobDefinitionUri": r["jobDefinitionUri"]}
        for r in all_job_requests
        if r.get("jobDefinitionUri") and not definition_exists[r["jobDefinitionUri"]]
    ]
    return broken_requests, broken_schedulers


def analyze(client, expected_job_keys, our_job_definition_uris):
    all_job_requests = client.get_all_items("/jobExecution/jobRequests")
    all_scheduler_jobs = client.get_all_items("/scheduler/jobs")

    our_orphan_requests = find_orphan_managed_requests(client, expected_job_keys)
    unmanaged_on_our_defs = find_unmanaged_on_our_definitions(client, our_job_definition_uris)
    broken_requests, broken_schedulers = find_broken_links(client, all_job_requests, all_scheduler_jobs)

    return {
        "our_orphan_requests": [summarize(r) for r in our_orphan_requests],
        "unmanaged_requests_on_our_definitions": unmanaged_on_our_defs,
        "broken_requests": broken_requests,
        "broken_schedulers": broken_schedulers,
        "_raw_orphan_requests": our_orphan_requests,
        "_all_scheduler_jobs": all_scheduler_jobs,
    }
