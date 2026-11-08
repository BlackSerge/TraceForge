import difflib
import os
from pathlib import Path

FIXTURE_REPO = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "repo"


async def read_file(path: str) -> dict:
    target = (FIXTURE_REPO / path).resolve()
    if not target.is_relative_to(FIXTURE_REPO.resolve()) or not target.is_file():
        return {"error": "not found"}
    return {"path": path, "content": target.read_text()}


async def propose_patch(file: str, new_content: str) -> dict:
    target = (FIXTURE_REPO / file).resolve()
    old_content = ""
    if target.is_relative_to(FIXTURE_REPO.resolve()) and target.is_file():
        old_content = target.read_text()
    diff = "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file}",
            tofile=f"b/{file}",
        )
    )
    return {"file": file, "diff": diff}


async def run_tests() -> dict:
    """Mock test run. Set MOCK_TESTS_PASS=false to simulate failures."""
    passed = os.getenv("MOCK_TESTS_PASS", "true").strip().lower() not in {"0", "false", "no"}
    return {"passed": passed, "output": "mock: tests passed" if passed else "mock: tests failed"}
