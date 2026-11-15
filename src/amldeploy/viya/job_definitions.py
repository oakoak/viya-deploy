"""CRUD job definitions. Версия объекта — забота сервера, мы её никогда не задаём и не увеличиваем сами."""
from amldeploy.viya import folders

CONTENT_KEYS = ["name", "description", "type", "code", "parameters"]


def find_job_in_folder(client, folder_uri, name):
    """Найти job definition по имени среди членов папки. Ошибка, если найдено более одного совпадения."""
    items = client.get_all_items(f"{folder_uri}/members", params={"filter": f"eq(name,'{name}')"})
    if len(items) > 1:
        raise RuntimeError(f"Найдено более одного job'а с именем '{name}' в папке деплоя: {[i['uri'] for i in items]}")
    return items[0] if items else None


def content_matches(existing, expected):
    for key in CONTENT_KEYS:
        if existing.get(key) != expected.get(key):
            return False
    return True


def create(client, folder_uri, job):
    return client.post_json("/jobDefinitions/definitions", job, params={"parentFolderUri": folder_uri})


def update(client, job_uri, existing_full, job, etag):
    """Мержим новые поля поверх текущего объекта (включая его текущую version) и шлём PUT со свежим ETag."""
    updated = dict(existing_full)
    updated.update(job)
    return client.put_json(job_uri, updated, etag)


def delete_definition(client, job_uri):
    return client.delete(job_uri)


def deploy(client, folder_uri, job, dry_run=False, log=print):
    """Создать/обновить/пропустить job definition. Возвращает dict с action и uri/id итогового объекта.

    В dry-run для НОВОГО job'а job_definition_uri/id будут None — реального id ещё нет, поэтому шаг
    постановки на расписание для таких job'ов в dry-run пропускается оркестратором."""
    name = job["name"]
    member = find_job_in_folder(client, folder_uri, name)

    if member is None:
        if dry_run:
            log(f"[dry-run] job '{name}': будет создан")
            return {"action": "created", "job_definition_uri": None, "job_definition_id": None}
        created = create(client, folder_uri, job)
        job_uri = f"/jobDefinitions/definitions/{created['id']}"
        log(f"[job] '{name}': создан")
        return {"action": "created", "job_definition_uri": job_uri, "job_definition_id": created["id"]}

    job_uri = folders.member_uri(member)
    existing_full, etag = client.get_json_with_etag(job_uri)

    if content_matches(existing_full, job):
        log(f"[job] '{name}': без изменений, пропуск")
        return {"action": "skipped", "job_definition_uri": job_uri, "job_definition_id": existing_full["id"]}

    if dry_run:
        log(f"[dry-run] job '{name}': будет обновлён")
        return {"action": "updated", "job_definition_uri": job_uri, "job_definition_id": existing_full["id"]}

    update(client, job_uri, existing_full, job, etag)
    log(f"[job] '{name}': обновлён")
    return {"action": "updated", "job_definition_uri": job_uri, "job_definition_id": existing_full["id"]}
