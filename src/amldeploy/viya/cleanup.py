"""Лишние файлы/папки внутри папок SAS Content, которыми мы управляем (root_folder_path/модуль)."""
from amldeploy.viya import folders


def summarize_member(member):
    return {
        "name": member.get("name"),
        "uri": folders.member_uri(member),
        "createdBy": member.get("createdBy"),
        "creationTimeStamp": member.get("creationTimeStamp"),
        "modifiedBy": member.get("modifiedBy"),
        "modifiedTimeStamp": member.get("modifiedTimeStamp"),
    }


def find_unexpected_members(client, folder_uri, expected_names, log=print):
    members = folders.get_folder_members(client, folder_uri)
    unexpected = [m for m in members if m["name"] not in expected_names]
    if unexpected:
        log(f"[folder] ВНИМАНИЕ: найдены объекты не из конфига: {[m['name'] for m in unexpected]}")
    else:
        log("[folder] лишних объектов не найдено")
    return unexpected


def find_empty_subfolders(client, members):
    """Среди 'лишних' объектов — какие из них папки без содержимого. Определяем через попытку листинга
    members: если у объекта нет собственного списка members, значит это не папка."""
    empty = []
    for member in members:
        try:
            sub_members = folders.get_folder_members(client, folders.member_uri(member))
        except Exception:
            continue
        if not sub_members:
            empty.append(member)
    return empty


def delete_member(client, member):
    return client.delete(folders.member_uri(member))
