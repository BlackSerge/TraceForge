"""Demo repositories a user can run the agent on: the fixtures of the eval cases."""
import functools
import json
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from src.agent.tools import Workspace

EVALS_DIR = Path(__file__).resolve().parents[3] / "evals"


@functools.cache
def _load_demo_repos() -> tuple[dict, ...]:
    repos = []
    for path in sorted((EVALS_DIR / "cases").glob("*.json")):
        case = json.loads(path.read_text())
        repos.append(
            {
                "slug": case["slug"],
                "description": case["description"],
                "example_issue": case["issue_text"],
                "fixture_dir": case["fixture_dir"],
                "test_file": case["test_file"],
            }
        )
    return tuple(repos)


def list_demo_repos() -> list[dict]:
    return list(_load_demo_repos())


def find_demo_repo(slug: str) -> dict | None:
    return next((r for r in list_demo_repos() if r["slug"] == slug), None)


@contextmanager
def temp_workspace(repo: dict) -> Iterator[Workspace]:
    """Fresh copy of the demo repo; removed when the run ends."""
    with tempfile.TemporaryDirectory(prefix="traceforge_run_") as tmp:
        root = Path(tmp) / "repo"
        shutil.copytree(EVALS_DIR / "fixtures" / repo["fixture_dir"], root)
        yield Workspace(root=root, test_file=repo["test_file"])
