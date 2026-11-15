"""Тесты ViyaClient через мок HTTP (requests-mock перехватывает и запросы через Session)."""
from amldeploy.viya.client import ViyaClient, build_host

ENV = {
    "AML_DEPLOY_VIYA_TENANT": "aml3",
    "AML_DEPLOY_VIYA_HOST": "example.local",
    "AML_DEPLOY_VIYA_USER": "u",
    "AML_DEPLOY_VIYA_PASSWORD": "p",
}
HOST = "https://aml3.example.local"


def test_build_host():
    assert build_host(ENV) == HOST


def test_from_env_fetches_token(requests_mock):
    requests_mock.post(f"{HOST}/SASLogon/oauth/token", json={"access_token": "tok"})
    client = ViyaClient.from_env(ENV)
    assert client.token == "tok"
    assert client.host == HOST
    # проверим, что ушёл grant_type=password с логином/паролем
    body = requests_mock.last_request.text
    assert "grant_type=password" in body and "username=u" in body and "password=p" in body


def _client(requests_mock):
    requests_mock.post(f"{HOST}/SASLogon/oauth/token", json={"access_token": "tok"})
    return ViyaClient.from_env(ENV)


def test_get_json_returns_none_on_404(requests_mock):
    client = _client(requests_mock)
    requests_mock.get(f"{HOST}/folders/x", status_code=404)
    assert client.get_json("/folders/x") is None


def test_get_json_bearer_header(requests_mock):
    client = _client(requests_mock)
    requests_mock.get(f"{HOST}/thing", json={"ok": True})
    assert client.get_json("/thing") == {"ok": True}
    assert requests_mock.last_request.headers["Authorization"] == "Bearer tok"


def test_delete_treats_404_as_success(requests_mock):
    client = _client(requests_mock)
    requests_mock.delete(f"{HOST}/gone", status_code=404)
    assert client.delete("/gone") is True


def test_get_all_items_follows_pagination(requests_mock):
    client = _client(requests_mock)
    requests_mock.get(f"{HOST}/coll", [
        {"json": {"items": [{"id": "a"}], "links": [{"rel": "next", "uri": "/coll?start=1&limit=100"}]}},
        {"json": {"items": [{"id": "b"}], "links": []}},
    ])
    items = client.get_all_items("/coll")
    assert [i["id"] for i in items] == ["a", "b"]
