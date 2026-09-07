from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from src.core.durable_discovery import MANIFEST_PATH, RepositoryDescriptor


class GitHubSourceError(RuntimeError):
    pass


@dataclass
class GitHubProjectSource:
    token: str
    owner: str
    api_base: str = "https://api.github.com"
    timeout_seconds: float = 20.0
    transport: httpx.BaseTransport | None = None

    def list_repositories(self, max_pages: int = 20) -> tuple[RepositoryDescriptor, ...]:
        if not self.token.strip():
            raise GitHubSourceError("GitHub token is required to discover private repositories")
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")

        repositories: list[RepositoryDescriptor] = []
        with self._client() as client:
            for page in range(1, max_pages + 1):
                response = client.get(
                    "/user/repos",
                    params={
                        "affiliation": "owner",
                        "per_page": 100,
                        "page": page,
                        "sort": "full_name",
                        "direction": "asc",
                    },
                )
                self._raise(response, "list repositories")
                payload = response.json()
                if not isinstance(payload, list):
                    raise GitHubSourceError("unexpected GitHub repository response")

                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    repo_owner = ((item.get("owner") or {}).get("login") or "")
                    if repo_owner.lower() != self.owner.lower():
                        continue
                    full_name = item.get("full_name")
                    default_branch = item.get("default_branch")
                    if not isinstance(full_name, str) or not isinstance(default_branch, str):
                        continue
                    repositories.append(
                        RepositoryDescriptor(
                            full_name=full_name,
                            default_branch=default_branch,
                            archived=bool(item.get("archived", False)),
                        )
                    )

                if len(payload) < 100:
                    break

        return tuple(repositories)

    def fetch_manifest(self, repository: RepositoryDescriptor) -> dict[str, Any] | None:
        try:
            return self.fetch_json_file(repository, MANIFEST_PATH)
        except FileNotFoundError:
            return None

    def fetch_json_file(self, repository: RepositoryDescriptor, path: str) -> dict[str, Any]:
        owner, name = _split_full_name(repository.full_name)
        quoted_path = quote(path, safe="/")
        with self._client() as client:
            response = client.get(
                f"/repos/{quote(owner, safe='')}/{quote(name, safe='')}/contents/{quoted_path}",
                params={"ref": repository.default_branch},
            )
            if response.status_code == 404:
                raise FileNotFoundError(f"{path} not found in {repository.full_name}")
            self._raise(response, f"fetch {path} from {repository.full_name}")
            payload = response.json()

        if not isinstance(payload, dict) or payload.get("encoding") != "base64":
            raise GitHubSourceError(f"unexpected file response for {repository.full_name}:{path}")
        encoded = payload.get("content")
        if not isinstance(encoded, str):
            raise GitHubSourceError(f"file content missing for {repository.full_name}:{path}")
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
            document = json.loads(decoded)
        except (ValueError, UnicodeDecodeError) as exc:
            raise GitHubSourceError(f"invalid JSON in {repository.full_name}:{path}") from exc
        if not isinstance(document, dict):
            raise GitHubSourceError(f"JSON file must contain an object: {repository.full_name}:{path}")
        return document

    def collect_manifests(
        self, repositories: tuple[RepositoryDescriptor, ...]
    ) -> dict[str, dict[str, Any] | None]:
        return {repository.full_name: self.fetch_manifest(repository) for repository in repositories}

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.api_base.rstrip("/"),
            timeout=self.timeout_seconds,
            transport=self.transport,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "cowlsly-durable-workflow/1",
            },
        )

    @staticmethod
    def _raise(response: httpx.Response, action: str) -> None:
        if response.is_success:
            return
        raise GitHubSourceError(f"GitHub failed to {action}: HTTP {response.status_code}")


def _split_full_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise GitHubSourceError(f"invalid repository name: {full_name}")
    return parts[0], parts[1]
