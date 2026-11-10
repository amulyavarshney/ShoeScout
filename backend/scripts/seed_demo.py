"""CLI: seed the demo catalog. Usage: python -m scripts.seed_demo [--force]"""
import asyncio
import sys

from app.db import get_sessionmaker, init_db
from app.seed.seed import seed_demo


async def main() -> None:
    await init_db()
    async with get_sessionmaker()() as db:
        print(await seed_demo(db, force="--force" in sys.argv))


if __name__ == "__main__":
    asyncio.run(main())
