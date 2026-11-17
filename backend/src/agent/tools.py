import asyncio
import difflib
import sys
from pathlib import Path

FIXTURE_REPO = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "repo"
MAX_OUTPUT_CHARS = 4000
TEST_TIMEOUT_S = 60


async def read_file(path: str) -> dict:
    target = (FIXTURE_REPO / path).resolve()
    if not target.is_relative_to(FIXTURE_REPO.resolve()) or not target.is_file():
        return {"error": "not found"}
    return {"path": path, "content": target.read_text()}


async def propose_patch(file: str, new_content: str) -> dict:
    """Write new_content to the file (inside the fixture repo) and return the unified diff."""
    target = (FIXTURE_REPO / file).resolve()
    if not target.is_relative_to(FIXTURE_REPO.resolve()):
        return {"error": "path outside repository"}
    old_content = target.read_text() if target.is_file() else ""
    diff = "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file}",
            tofile=f"b/{file}",
        )
    )
    target.write_text(new_content)
    return {"file": file, "diff": diff}


async def run_tests() -> dict:
    """Run pytest on test_sample.py inside the fixture repo."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pytest",
        "test_sample.py",
        "-q",
        "-p",
        "no:cacheprovider",
        cwd=FIXTURE_REPO,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TEST_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"passed": False, "output": f"pytest timed out after {TEST_TIMEOUT_S}s"}
    output = stdout.decode(errors="replace")
    if len(output) > MAX_OUTPUT_CHARS:
        output = "...(truncated)\n" + output[-MAX_OUTPUT_CHARS:]
    return {"passed": proc.returncode == 0, "output": output}
