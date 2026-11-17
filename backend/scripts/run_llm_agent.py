import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.loop import run_agent  # noqa: E402
from src.db.session import SessionLocal, engine  # noqa: E402


async def main() -> None:
    async with SessionLocal() as session:
        run_id = await run_agent("https://github.com/example/repo/issues/1", session)
    print(run_id)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
