"""Standalone enrichment worker process (used by docker-compose `worker` service)."""
import asyncio
import logging

from app.db import init_db
from app.enrichment.worker import worker_loop

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    await init_db()
    await worker_loop()


if __name__ == "__main__":
    asyncio.run(main())
