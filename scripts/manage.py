import argparse
import asyncio
import os
import secrets
from pathlib import Path

from tripbudget.auth import HASHER
from tripbudget.persistence import Store
from tripbudget.settings import Settings


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "create-user", "status"])
    parser.add_argument("--username", default="organizer")
    parser.add_argument("--role", choices=["organizer", "evaluation", "admin"], default="organizer")
    args = parser.parse_args()
    s = Settings()
    store = Store(s)
    if args.command == "migrate":
        await store.migrate()
        print("Application schema and official PostgreSQL checkpointer initialized")
    elif args.command == "create-user":
        password = secrets.token_urlsafe(24)
        old = await store.one("SELECT uid FROM app_users WHERE username=%s", (args.username,))
        if old:
            raise SystemExit("User already exists; not resetting a password")
        await store.execute(
            "INSERT INTO app_users(uid,username,password_hash,role) VALUES(%s,%s,%s,%s)",
            (secrets.token_hex(16), args.username, HASHER.hash(password), args.role),
        )
        directory = Path(".secrets")
        directory.mkdir(mode=0o700, exist_ok=True)
        file = directory / (args.username + ".txt")
        file.write_text(f"username={args.username}\npassword={password}\n")
        os.chmod(file, 0o600)
        print("Created account; credentials saved privately to", file)
    else:
        row = await store.one("SELECT count(*) AS episodes FROM episodes")
        print(row)


if __name__ == "__main__":
    asyncio.run(main())
