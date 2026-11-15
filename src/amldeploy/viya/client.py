"""
SAS Viya REST-клиент: авторизация (OAuth password grant) + HTTP-хелперы с пагинацией по links.next.

Инициализация ленивая: клиент создаётся только когда команда реально идёт в Viya
(deploy / release / switch без --no-viya). Импорт модуля сайд-эффектов не имеет — в отличие от
прежнего auth.py, который читал env-файл и собирал HOST прямо на import (см. обзор, 3.5).

Все запросы идут через один requests.Session: verify/CA-bundle, заголовки и пул соединений
задаются один раз (обзор, 4/python). По умолчанию verify=False (внутренний самоподписанный
сертификат Viya), но это теперь параметр, а не глобально зашитое поведение.
"""
import base64

import requests
import urllib3

from amldeploy.env_file import (
    KEY_VIYA_HOST, KEY_VIYA_PASSWORD, KEY_VIYA_TENANT, KEY_VIYA_USER, require_nonempty,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Публичный CLI-клиент Viya "sas.cli" без секрета (секрет не нужен).
_OAUTH_BASIC = base64.b64encode(b"sas.cli:").decode()
_ACCEPT = "application/json, application/vnd.sas.job.definition+json"


def build_host(env):
    """https://<AML_DEPLOY_VIYA_TENANT>.<AML_DEPLOY_VIYA_HOST>"""
    return "https://{}.{}".format(
        require_nonempty(env, KEY_VIYA_TENANT),
        require_nonempty(env, KEY_VIYA_HOST),
    )


def fetch_token(host, session, env):
    payload = "grant_type=password&username={}&password={}".format(
        require_nonempty(env, KEY_VIYA_USER),
        require_nonempty(env, KEY_VIYA_PASSWORD),
    )
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {_OAUTH_BASIC}",
    }
    resp = session.post(f"{host}/SASLogon/oauth/token", headers=headers, data=payload)
    resp.raise_for_status()
    return resp.json()["access_token"]


class ViyaClient:
    def __init__(self, host, session, token):
        self.host = host
        self.session = session
        self.token = token

    @classmethod
    def from_env(cls, env, verify=False):
        session = requests.Session()
        session.verify = verify
        host = build_host(env)
        token = fetch_token(host, session, env)
        return cls(host, session, token)

    def _headers(self, extra=None):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
            "Accept": _ACCEPT,
        }
        if extra:
            headers.update(extra)
        return headers

    def get_json(self, uri, params=None, extra_headers=None):
        """GET по абсолютному uri (относительно host). Возвращает None на 404."""
        resp = self.session.get(f"{self.host}{uri}", params=params, headers=self._headers(extra_headers))
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_json_with_etag(self, uri):
        resp = self.session.get(f"{self.host}{uri}", headers=self._headers())
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        return resp.json(), resp.headers.get("ETag")

    def post_json(self, uri, payload, params=None, extra_headers=None):
        resp = self.session.post(f"{self.host}{uri}", params=params, json=payload, headers=self._headers(extra_headers))
        resp.raise_for_status()
        return resp.json()

    def put_json(self, uri, payload, etag):
        resp = self.session.put(f"{self.host}{uri}", json=payload, headers=self._headers({"If-Match": etag}))
        resp.raise_for_status()
        return resp.json()

    def delete(self, uri):
        """DELETE по абсолютному uri. True, если удалён или его уже не было (404)."""
        resp = self.session.delete(f"{self.host}{uri}", headers=self._headers())
        if resp.status_code in (204, 200, 404):
            return True
        resp.raise_for_status()
        return True

    def get_all_items(self, uri, params=None):
        """Собрать все items коллекции, следуя links.next (не полагаясь на один большой limit)."""
        items = []
        params = dict(params or {})
        params.setdefault("limit", 100)
        next_uri = uri
        next_params = params
        while next_uri is not None:
            resp = self.session.get(f"{self.host}{next_uri}", params=next_params, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            items.extend(data.get("items", []))
            next_uri = None
            for link in data.get("links", []):
                if link.get("rel") == "next":
                    next_uri = link["uri"]
            next_params = None  # next-ссылка уже содержит start/limit
        return items
