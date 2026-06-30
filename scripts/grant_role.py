"""Set a user's roles by email.

A small bootstrap for the role-based dashboards: mint an admin or a senior
persona, or force a user to be a pure engineer for testing. Real role
assignment will come from SharePoint/Azure later — this is a dev convenience.
It REPLACES the user's roles with exactly the ones given.

Run (from projectqa-api/, persistent cluster up):

    ./.venv/Scripts/python.exe -m scripts.grant_role <email> <role> [<role> ...]

Examples:
    # make the default dev user an admin that can still see everything
    ./.venv/Scripts/python.exe -m scripts.grant_role engineer@hts.uk.com director admin
    # force a user to be a pure (own-only) engineer
    ./.venv/Scripts/python.exe -m scripts.grant_role sam.engineer@hts.uk.com engineer
"""

from __future__ import annotations

import asyncio
import sys

from app.core.db import SessionLocal
from app.repositories import users as users_repo


async def set_roles(email: str, roles: list[str]) -> None:
    async with SessionLocal() as session:
        user = await users_repo.get_by_email(session, email)
        if user is None:
            print(f"No user found with email {email!r}")
            raise SystemExit(1)
        user.roles = roles
        await session.commit()
        print(f"OK — {user.display_name} <{email}> roles set to {roles}")


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "usage: python -m scripts.grant_role <email> <role> [<role> ...]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    asyncio.run(set_roles(sys.argv[1], sys.argv[2:]))


if __name__ == "__main__":
    main()
