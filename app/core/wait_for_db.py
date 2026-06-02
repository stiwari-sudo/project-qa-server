"""Block until the database accepts connections (used by the container entrypoint)."""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.core.db import engine


async def _wait(max_attempts: int = 30, delay: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print(f"[wait_for_db] database ready (attempt {attempt})")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[wait_for_db] not ready (attempt {attempt}/{max_attempts}): {exc}")
            await asyncio.sleep(delay)
    print("[wait_for_db] database never became ready", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_wait())
