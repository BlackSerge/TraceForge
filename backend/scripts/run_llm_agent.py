import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent.loop import run_agent  # noqa: E402
from src.db.session import SessionLocal, engine  # noqa: E402


async def main() -> None:
    async with SessionLocal() as session:
        result = await run_agent("https://github.com/example/repo/issues/1", session)
    print(result.run_id)
    if result.error:
        print(f"LLM error: {result.error}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
