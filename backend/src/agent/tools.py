import asyncio
import difflib
import fnmatch
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

MAX_OUTPUT_CHARS = 4000
MAX_READ_BYTES = 100_000
TEST_TIMEOUT_S = 60
SANDBOX_IMAGE = "devpilot-sandbox:latest"  # built from backend/sandbox/Dockerfile (make sandbox-image)
TEST_FILE_PATTERNS = ("test_*.py", "*_test.py", "conftest.py")


@dataclass
class Workspace:
    """Per-run working copy of a repo. Passed explicitly to every tool (no module globals), so
    concurrent runs cannot clobber each other.

    Flow: the caller (eval runner / script) copies the fixture to a temp dir and builds a
    Workspace on it; propose_patch edits that copy; run_tests mounts that same copy read-only
    in the sandbox container. The host never executes the repo's code.
    """

    root: Path
    test_file: str = "test_main.py"
    last_sandbox: dict | None = None  # metadata of the last run_tests container


def list_repo_files(ws: Workspace) -> list[str]:
    """Relative paths of the files in the workspace (not an agent tool: used to build prompts)."""
    root = ws.root.resolve()
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    )


def _is_test_file(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pat) for pat in TEST_FILE_PATTERNS)


async def read_file(ws: Workspace, path: str) -> dict:
    root = ws.root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return {"error": "not found"}
    if target.stat().st_size > MAX_READ_BYTES:
        return {"error": f"file too large (max {MAX_READ_BYTES} bytes)"}
    try:
        return {"path": path, "content": target.read_text()}
    except UnicodeDecodeError:
        return {"error": "not a text file"}


async def list_files(ws: Workspace, path: str = ".") -> dict:
    """List a directory inside the workspace: directories first, then files, alphabetically."""
    root = ws.root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_dir():
        return {"error": "not found"}
    children = [c for c in target.iterdir() if c.name != "__pycache__" and c.suffix != ".pyc"]
    children.sort(key=lambda c: (c.is_file(), c.name))
    return {
        "path": path,
        "entries": [{"name": c.name, "type": "dir" if c.is_dir() else "file"} for c in children],
    }


async def propose_patch(ws: Workspace, file: str, new_content: str) -> dict:
    """Write new_content to the file and return the unified diff.

    The resolved target must stay strictly inside the workspace (blocks "..", absolute paths and
    symlinks pointing outside), must not be a directory, and must not be a test file: otherwise
    the agent could "fix" the failing test by editing it instead of the code.
    """
    root = ws.root.resolve()
    target = (root / file).resolve()
    if not target.is_relative_to(root) or target == root or target.is_dir():
        return {"error": "path outside repository"}
    if _is_test_file(target) or target == (root / ws.test_file).resolve():
        return {"error": "test files are read-only"}
    old_content = target.read_text() if target.is_file() else ""
    diff = "".join(
        difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{file}",
            tofile=f"b/{file}",
        )
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_content)
    return {"file": file, "diff": diff}


async def run_tests(ws: Workspace) -> dict:
    """Run pytest on ws.test_file inside an ephemeral, network-less Docker container.

    Contract: {"passed": bool, "output": str}. Container metadata goes to ws.last_sandbox
    (the loop records it in the trace), not in the returned dict.
    """
    name = f"devpilot-sandbox-{uuid.uuid4().hex[:12]}"
    ws.last_sandbox = {"container_name": name, "image": SANDBOX_IMAGE, "container_id": None, "exit_code": None}
    uid, gid = os.getuid(), os.getgid()
    with tempfile.TemporaryDirectory(prefix="devpilot_cid_") as cid_dir:
        cidfile = Path(cid_dir) / "cid"
        cmd = [
            "docker", "run", "--rm", "--name", name, "--cidfile", str(cidfile),
            "--network=none", "--memory=512m", "--cpus=1", "--pids-limit=256",
            "--user", f"{uid}:{gid}",
            "--cap-drop=ALL", "--security-opt", "no-new-privileges",
            "--read-only", "--tmpfs", "/tmp:rw,size=64m",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-v", f"{ws.root.resolve()}:/repo:ro,z",
            "-w", "/repo",
            SANDBOX_IMAGE,
            "python", "-m", "pytest", ws.test_file, "-q", "-p", "no:cacheprovider",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
        except OSError as exc:
            return {"passed": False, "output": f"sandbox unavailable: {exc}"}
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=TEST_TIMEOUT_S)
        except asyncio.TimeoutError:
            kill = await asyncio.create_subprocess_exec(
                "docker", "kill", name, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            await kill.wait()
            proc.kill()
            await proc.wait()
            return {"passed": False, "output": "timeout"}
        if cidfile.exists():
            ws.last_sandbox["container_id"] = cidfile.read_text().strip()[:12]
    output = stdout.decode(errors="replace")
    ws.last_sandbox["exit_code"] = proc.returncode
    if proc.returncode in (125, 126, 127):  # docker itself failed (daemon down, image missing, ...)
        return {"passed": False, "output": f"sandbox unavailable: {output.strip()[-500:]}"}
    if len(output) > MAX_OUTPUT_CHARS:
        output = "...(truncated)\n" + output[-MAX_OUTPUT_CHARS:]
    return {"passed": proc.returncode == 0, "output": f"{output}\n[exit code: {proc.returncode}]"}
