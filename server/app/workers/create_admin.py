import asyncio
import getpass
import sys
from sqlalchemy import select

from app.authentication.security import hash_password
from app.database import SessionLocal
from app.models import AdminUser


async def main() -> None:
    email = sys.argv[1] if len(sys.argv) > 1 else input("Email: ").strip()
    password = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Password: ")
    async with SessionLocal() as db:
        existing = (await db.execute(select(AdminUser).where(AdminUser.email == email))).scalar_one_or_none()
        if existing:
            raise SystemExit("Admin already exists")
        db.add(AdminUser(email=email, password_hash=hash_password(password)))
        await db.commit()
    print(f"Created admin {email}")


if __name__ == "__main__":
    asyncio.run(main())
