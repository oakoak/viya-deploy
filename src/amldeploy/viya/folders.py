"""Работа с папками SAS Content: поиск/создание по абсолютному пути, листинг содержимого."""


def get_folder_by_path(client, path):
    return client.get_json("/folders/folders/@item", params={"path": path})


def member_uri(member):
    """uri объекта из ответа members — именно uri, а не id (id в листинге не всегда равен id самого объекта)."""
    return member["uri"]


def get_by_uri(client, uri):
    return client.get_json_with_etag(uri)


def get_root_level_folder(client, name):
    """Папка верхнего уровня по имени (у '/' нет собственного id, поэтому members/@item не подходят)."""
    items = client.get_all_items("/folders/folders", params={"filter": f"eq(name,'{name}')"})
    return items[0] if items else None


def create_root_level_folder(client, name):
    return client.post_json("/folders/folders", {"name": name, "type": "folder"})


def get_subfolder(client, parent_folder_uri, name):
    items = client.get_all_items(f"{parent_folder_uri}/members", params={"filter": f"eq(name,'{name}')"})
    if not items:
        return None
    full, _ = get_by_uri(client, member_uri(items[0]))
    return full


def create_subfolder(client, parent_uri, name):
    return client.post_json("/folders/folders", {"name": name, "type": "folder"}, params={"parentFolderUri": parent_uri})


def ensure_folder_path(client, path, log=print):
    """Убеждается, что вся цепочка папок по абсолютному пути существует, создавая отсутствующие уровни."""
    segments = [s for s in path.strip("/").split("/") if s]
    if not segments:
        raise ValueError("путь к папке не может быть пустым")

    first, rest = segments[0], segments[1:]
    sub = get_root_level_folder(client, first)
    if sub is None:
        log(f"[folder] '{first}' не найдена, создаю...")
        sub = create_root_level_folder(client, first)
    else:
        log(f"[folder] '{first}' уже существует (id={sub['id']})")
    current_uri = f"/folders/folders/{sub['id']}"

    for seg in rest:
        sub = get_subfolder(client, current_uri, seg)
        if sub is None:
            log(f"[folder] '{seg}' не найдена, создаю...")
            sub = create_subfolder(client, current_uri, seg)
        else:
            log(f"[folder] '{seg}' уже существует (id={sub['id']})")
        current_uri = f"/folders/folders/{sub['id']}"

    return current_uri


def get_folder_members(client, folder_uri):
    return client.get_all_items(f"{folder_uri}/members")


def delete_folder(client, folder_uri):
    return client.delete(folder_uri)
