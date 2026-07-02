from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from seeds import forms, sample, stages

log = get_logger("seeds")


async def run() -> None:
    # Stages + forms are structural and safe to (re-)seed anywhere. The sample
    # data is demo-only: it must never land in a database holding real QA data.
    want_sample = settings.seed_sample_data and not settings.is_production
    if settings.seed_sample_data and settings.is_production:
        log.warning("seeds.sample_refused", reason="APP_ENV is production")

    async with SessionLocal() as session:
        await stages.seed(session)
        await forms.seed(session)
        if want_sample:
            await sample.seed_users(session)
            await sample.seed_projects(session)
            await sample.seed_hrb(session)
            await sample.seed_event_logs(session)
        await session.commit()
    log.info("seeds.complete", sample_data=want_sample)


def main() -> None:
    configure_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
