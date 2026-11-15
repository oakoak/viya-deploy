from amldeploy.viya import orphans


class FakeClient:
    """Мини-заглушка клиента: get_json по набору существующих uri, get_all_items — заданный список."""
    def __init__(self, existing_defs=None, managed=None):
        self.existing = set(existing_defs or [])
        self._managed = managed or []

    def get_json(self, uri, params=None):
        return {"id": "x"} if uri in self.existing else None

    def get_all_items(self, uri, params=None):
        return self._managed


def test_find_orphan_managed_requests_filters_by_expected_keys():
    managed = [
        {"id": "a", "properties": [{"name": "jobKey", "value": "M/keep"}]},
        {"id": "b", "properties": [{"name": "jobKey", "value": "M/drop"}]},
    ]
    client = FakeClient(managed=managed)
    result = orphans.find_orphan_managed_requests(client, expected_job_keys={"M/keep"})
    assert [r["id"] for r in result] == ["b"]


def test_find_broken_links_detects_broken_request_and_scheduler():
    reqs = [
        {"id": "r1", "jobDefinitionUri": "/jobDefinitions/definitions/good"},
        {"id": "r2", "jobDefinitionUri": "/jobDefinitions/definitions/gone"},
    ]
    scheds = [
        {"id": "s1", "request": {"uri": "/jobExecution/jobRequests/r1/jobs"}},
        {"id": "s2", "request": {"uri": "/jobExecution/jobRequests/rX/jobs"}},  # ссылка на несуществующий req
    ]
    client = FakeClient(existing_defs={"/jobDefinitions/definitions/good"})
    broken_reqs, broken_scheds = orphans.find_broken_links(client, reqs, scheds)
    assert [r["id"] for r in broken_reqs] == ["r2"]
    assert [s["id"] for s in broken_scheds] == ["s2"]


def test_find_broken_links_all_ok():
    reqs = [{"id": "r1", "jobDefinitionUri": "/jobDefinitions/definitions/good"}]
    scheds = [{"id": "s1", "request": {"uri": "/jobExecution/jobRequests/r1/jobs"}}]
    client = FakeClient(existing_defs={"/jobDefinitions/definitions/good"})
    broken_reqs, broken_scheds = orphans.find_broken_links(client, reqs, scheds)
    assert broken_reqs == [] and broken_scheds == []
