import asyncio

import pytest
from pydantic import ValidationError

from src.agent import executor
from src.agent.demo_repos import find_demo_repo, list_demo_repos, temp_workspace
from src.schemas.agent import CreateRunRequest


def test_demo_repos_come_from_eval_cases():
    repos = list_demo_repos()
    assert len(repos) >= 15
    assert find_demo_repo("list-files")["test_file"] == "test_main.py"
    assert find_demo_repo("nope") is None


def test_temp_workspace_is_a_fresh_copy_each_time():
    repo = find_demo_repo("add-subtracts")
    with temp_workspace(repo) as ws:
        (ws.root / "calc.py").write_text("changed")
        root = ws.root
    assert not root.exists()
    with temp_workspace(repo) as ws:
        assert "a - b" in (ws.root / "calc.py").read_text()


@pytest.mark.parametrize("issue", ["short", "x" * 4001])
def test_create_run_request_validates_issue_length(issue):
    with pytest.raises(ValidationError):
        CreateRunRequest(issue_text=issue, repo="add-subtracts")


def test_only_one_run_slot():
    async def go():
        assert await executor.try_reserve() is True
        assert await executor.try_reserve() is False
        executor.release()
        assert await executor.try_reserve() is True
        executor.release()

    asyncio.run(go())
