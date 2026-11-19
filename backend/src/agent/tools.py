import asyncio
import difflib
import os
import tempfile
import uuid
from pathlib import Path

# Module-level settings: the eval runner reassigns these per case.
FIXTURE_REPO = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "repo"
TEST_FILE = "test_sample.py"
MAX_OUTPUT_CHARS = 4000
TEST_TIMEOUT_S = 60
SANDBOX_IMAGE = "devpilot-sandbox:latest"  # built from backend/sandbox/Dockerfile (make sandbox-image)
LAST_SANDBOX: dict | None = None  # metadata of the last run_tests container


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
    """Write new_content to the file and return the unified diff.

    FIXTURE_REPO must be a temporary copy of the fixture (the runner guarantees it); the
    resolved target must stay strictly inside it (blocks "..", absolute paths and symlinks
    that point outside), and must not be a directory.
    """
    root = FIXTURE_REPO.resolve()
    target = (root / file).resolve()
    if not target.is_relative_to(root) or target == root or target.is_dir():
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
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new_content)
    return {"file": file, "diff": diff}


async def run_tests() -> dict:
    """Run pytest on TEST_FILE inside an ephemeral, network-less Docker container.

    Flow: the eval runner (or any caller) copies the fixture to a temp dir and points
    FIXTURE_REPO at it; propose_patch edits that copy; this function mounts that same copy
    read-only in the container. The host never executes the repo's code.
    Contract: {"passed": bool, "output": str}. Container metadata goes to LAST_SANDBOX
    (the loop records it in the trace), not in the returned dict.
    """
    global LAST_SANDBOX
    name = f"devpilot-sandbox-{uuid.uuid4().hex[:12]}"
    LAST_SANDBOX = {"container_name": name, "image": SANDBOX_IMAGE, "container_id": None, "exit_code": None}
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
            "-v", f"{FIXTURE_REPO.resolve()}:/repo:ro,z",
            "-w", "/repo",
            SANDBOX_IMAGE,
            "python", "-m", "pytest", TEST_FILE, "-q", "-p", "no:cacheprovider",
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
            LAST_SANDBOX["container_id"] = cidfile.read_text().strip()[:12]
    output = stdout.decode(errors="replace")
    LAST_SANDBOX["exit_code"] = proc.returncode
    if proc.returncode in (125, 126, 127):  # docker itself failed (daemon down, image missing, ...)
        return {"passed": False, "output": f"sandbox unavailable: {output.strip()[-500:]}"}
    if len(output) > MAX_OUTPUT_CHARS:
        output = "...(truncated)\n" + output[-MAX_OUTPUT_CHARS:]
    return {"passed": proc.returncode == 0, "output": f"{output}\n[exit code: {proc.returncode}]"}
