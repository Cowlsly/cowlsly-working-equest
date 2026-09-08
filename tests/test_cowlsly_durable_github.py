import base64
import json

import httpx

from src.core.durable_discovery import RepositoryDescriptor
from src.core.durable_github import GitHubProjectSource, GitHubSourceError


def _transport(handler):
    return httpx.MockTransport(handler)


def test_lists_only_repositories_owned_by_configured_owner():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/user/repos"
        return httpx.Response(
            200,
            json=[
                {
                    "full_name": "Cowlsly/a",
                    "default_branch": "root",
                    "archived": False,
                    "owner": {"login": "Cowlsly"},
                },
                {
                    "full_name": "someone/else",
                    "default_branch": "main",
                    "archived": False,
                    "owner": {"login": "someone"},
                },
            ],
        )

    source = GitHubProjectSource("token", "Cowlsly", transport=_transport(handler))
    repos = source.list_repositories()

    assert repos == (RepositoryDescriptor("Cowlsly/a", "root", False),)


def test_fetch_manifest_uses_repository_default_branch():
    manifest = {"version": 1, "enabled": True, "project_id": "a"}
    encoded = base64.b64encode(json.dumps(manifest).encode()).decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/.cowlsly/workflow.json")
        assert request.url.params["ref"] == "root"
        return httpx.Response(200, json={"encoding": "base64", "content": encoded})

    source = GitHubProjectSource("token", "Cowlsly", transport=_transport(handler))
    payload = source.fetch_manifest(RepositoryDescriptor("Cowlsly/a", "root"))

    assert payload == manifest


def test_missing_manifest_means_repository_is_not_opted_in():
    source = GitHubProjectSource(
        "token",
        "Cowlsly",
        transport=_transport(lambda request: httpx.Response(404, json={"message": "Not Found"})),
    )

    assert source.fetch_manifest(RepositoryDescriptor("Cowlsly/a", "main")) is None


def test_private_discovery_requires_token():
    source = GitHubProjectSource("", "Cowlsly", transport=_transport(lambda request: httpx.Response(500)))
    try:
        source.list_repositories()
    except GitHubSourceError as exc:
        assert "token" in str(exc).lower()
    else:
        raise AssertionError("missing token must fail before network access")


def test_invalid_manifest_json_fails_closed():
    encoded = base64.b64encode(b"not-json").decode()
    source = GitHubProjectSource(
        "token",
        "Cowlsly",
        transport=_transport(lambda request: httpx.Response(200, json={"encoding": "base64", "content": encoded})),
    )

    try:
        source.fetch_manifest(RepositoryDescriptor("Cowlsly/a", "main"))
    except GitHubSourceError as exc:
        assert "invalid JSON" in str(exc)
    else:
        raise AssertionError("invalid manifest JSON must fail closed")
