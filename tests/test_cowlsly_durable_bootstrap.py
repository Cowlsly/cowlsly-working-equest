from src.core.durable_bootstrap import bootstrap_projects
from src.core.durable_discovery import RepositoryDescriptor


class FakeSource:
    def list_repositories(self):
        return (
            RepositoryDescriptor("Cowlsly/a", "root"),
            RepositoryDescriptor("Cowlsly/b", "main"),
        )

    def collect_manifests(self, repositories):
        return {
            "Cowlsly/a": {
                "version": 1,
                "enabled": True,
                "project_id": "a",
                "task_files": ["WORK/phase1.json", "WORK/phase2.json"],
            },
            "Cowlsly/b": None,
        }

    def fetch_json_file(self, repository, path):
        if path == "WORK/phase1.json":
            return {
                "tasks": [
                    {
                        "id": "TASK-A",
                        "objective": "first",
                        "acceptance_criteria": ["first done"],
                    }
                ]
            }
        if path == "WORK/phase2.json":
            return {
                "tasks": [
                    {
                        "id": "TASK-B",
                        "objective": "second",
                        "depends_on": ["TASK-A"],
                        "acceptance_criteria": ["second done"],
                    }
                ]
            }
        raise AssertionError(path)


def test_bootstrap_combines_task_files_before_dependency_validation():
    projects = bootstrap_projects(FakeSource())

    assert len(projects) == 1
    assert projects[0].manifest.repository == "Cowlsly/a"
    assert [task.id for task in projects[0].tasks] == ["TASK-A", "TASK-B"]
    assert projects[0].tasks[1].depends_on == {"TASK-A"}
