import argparse
import asyncio
from getpass import getpass

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import PlatformOwner


async def create_platform_owner() -> None:
    email = input("Platform owner email: ").strip().lower()
    if "@" not in email or len(email) > 320:
        raise SystemExit("Enter a valid email address")
    password = getpass("Password (12+ characters): ")
    confirmation = getpass("Confirm password: ")
    if len(password) < 12 or len(password) > 128:
        raise SystemExit("Password must be between 12 and 128 characters")
    if password != confirmation:
        raise SystemExit("Passwords do not match")

    async with SessionLocal() as db:
        count = await db.scalar(select(func.count()).select_from(PlatformOwner))
        if count:
            raise SystemExit("Platform owner bootstrap has already been completed")
        db.add(PlatformOwner(email=email, password_hash=hash_password(password)))
        await db.commit()
    print(f"Created platform owner {email}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SupportPilot operator commands")
    parser.add_argument("command", choices=["create-platform-owner"])
    args = parser.parse_args()
    if args.command == "create-platform-owner":
        asyncio.run(create_platform_owner())


if __name__ == "__main__":
    main()
