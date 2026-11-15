"""
CRUD jobRequest'ов. jobRequest — обёртка над jobDefinition, необходимая, чтобы job можно было
запускать/ставить на расписание. properties.managedBy + properties.jobKey — наша метка, по которой
отличаем свои объекты от созданных вручную в UI и однозначно связываем с job'ом из конфига
(module/job_name), т.к. на один jobDefinition может существовать много jobRequest.
"""
MANAGED_BY = "deploy_job"


def build_job_key(folder_name, job_name):
    return f"{folder_name}/{job_name}"


def _get_property(item, name):
    for prop in item.get("properties") or []:
        if prop.get("name") == name:
            return prop.get("value")
    return None


def find_all_managed(client):
    """Все jobRequest'ы, помеченные нашей меткой managedBy (по всему окружению)."""
    return client.get_all_items("/jobExecution/jobRequests", params={"filter": f"eq(properties.managedBy,'{MANAGED_BY}')"})


def find_all_by_job_definition_uri(client, job_definition_uri):
    return client.get_all_items("/jobExecution/jobRequests", params={"filter": f"eq(jobDefinitionUri,'{job_definition_uri}')"})


def find_managed_by_key(client, job_key):
    """Найти наш jobRequest по составному ключу module/job_name. Ошибка, если найдено больше одного."""
    matches = [i for i in find_all_managed(client) if _get_property(i, "jobKey") == job_key]
    if len(matches) > 1:
        raise RuntimeError(f"Найдено более одного управляемого jobRequest с jobKey='{job_key}': {[m['id'] for m in matches]}")
    return matches[0] if matches else None


def create(client, name, job_definition_uri, job_key):
    payload = {
        "name": name,
        "jobDefinitionUri": job_definition_uri,
        "properties": [
            {"name": "managedBy", "value": MANAGED_BY},
            {"name": "jobKey", "value": job_key},
        ],
    }
    return client.post_json("/jobExecution/jobRequests", payload)


def delete_request(client, request_id):
    return client.delete(f"/jobExecution/jobRequests/{request_id}")


def ensure(client, name, job_definition_uri, job_key, dry_run=False, log=print):
    """Найти-или-создать наш jobRequest для job'а. Пересоздаёт, если он ссылается на другой jobDefinition."""
    existing = find_managed_by_key(client, job_key)
    if existing is not None and existing.get("jobDefinitionUri") == job_definition_uri:
        log(f"[jobRequest] '{name}': уже существует (id={existing['id']})")
        return existing, False

    if dry_run:
        verb = "будет пересоздан (устаревшая ссылка на jobDefinition)" if existing is not None else "будет создан"
        log(f"[dry-run] jobRequest '{name}': {verb}")
        return existing, True

    if existing is not None:
        log(f"[jobRequest] '{name}': ссылается на устаревший jobDefinition, пересоздаю")
        delete_request(client, existing["id"])

    created = create(client, name, job_definition_uri, job_key)
    log(f"[jobRequest] '{name}': создан (id={created['id']})")
    return created, True
