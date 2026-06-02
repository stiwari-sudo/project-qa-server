from __future__ import annotations

import asyncio

from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from seeds import forms, sample, stages

log = get_logger("seeds")


async def run() -> None:
    async with SessionLocal() as session:
        await stages.seed(session)
        await sample.seed_users(session)
        await forms.seed(session)
        await sample.seed_projects(session)
        await sample.seed_hrb(session)
        await session.commit()
    log.info("seeds.complete")


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
