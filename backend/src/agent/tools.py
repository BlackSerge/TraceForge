import asyncio
import difflib
import os
import sys
from pathlib import Path

# Module-level settings: the eval runner reassigns these per case.
FIXTURE_REPO = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "repo"
TEST_FILE = "test_sample.py"
MAX_OUTPUT_CHARS = 4000
TEST_TIMEOUT_S = 60


def list_repo_files() -> list[str]:
    """Relative paths of the files in FIXTURE_REPO (not an agent tool: used to build the prompt)."""
    root = FIXTURE_REPO.resolve()
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )


async def read_file(path: str) -> dict:
    target = (FIXTURE_REPO / path).resolve()
    if not target.is_relative_to(FIXTURE_REPO.resolve()) or not target.is_file():
        return {"error": "not found"}
    return {"path": path, "content": target.read_text()}


async def list_files(path: str = ".") -> dict:
    """List a directory inside FIXTURE_REPO: directories first, then files, alphabetically."""
    root = FIXTURE_REPO.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_dir():
        return {"error": "not found"}
    children = [c for c in target.iterdir() if c.name != "__pycache__" and c.suffix != ".pyc"]
    children.sort(key=lambda c: (c.is_file(), c.name))
    return {
        "path": path,
        "entries": [{"name": c.name, "type": "dir" if c.is_dir() else "file"} for c in children],
    }


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
    """Run pytest on TEST_FILE inside FIXTURE_REPO."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pytest",
        TEST_FILE,
        "-q",
        "-p",
        "no:cacheprovider",
        cwd=FIXTURE_REPO,
        # no .pyc: a same-size, same-second edit would otherwise load stale bytecode
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
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
