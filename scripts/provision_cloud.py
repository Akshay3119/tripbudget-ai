"""Operator-only one-time setup for dedicated A4 resources. Never prints credentials."""

import asyncio
import json
import os
import secrets
import subprocess
from pathlib import Path

import httpx
import psycopg

from tripbudget.persistence import Store
from tripbudget.settings import Settings

PROJECT = "csci599-a3-hermes-1029"
INSTANCE = "a4-tripbudget"
ENV = dict(os.environ, CLOUDSDK_CONFIG=str(Path(".runtime/gcloud").resolve()))


def gcloud(*args, input=None):
    result = subprocess.run(
        ["gcloud", *args, "--project=" + PROJECT, "--quiet"],
        env=ENV,
        input=input,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        # gcloud may echo sensitive flags: never forward raw stderr from this provisioning helper.
        raise RuntimeError("Cloud command failed: " + args[0] + " " + args[1])
    return result.stdout


async def main():
    if Path(".secrets/cloud-passwords.json").exists():
        raise SystemExit(
            "Initialization already recorded; refusing to rotate existing credentials. Use a deliberate migration procedure."
        )
    settings = Settings()
    token = gcloud("auth", "print-access-token").strip()
    passwords = {k: secrets.token_urlsafe(32) for k in ["postgres", "tripbudget_runtime"]}
    Path(".secrets/cloud-passwords.json").write_text(json.dumps(passwords))
    os.chmod(".secrets/cloud-passwords.json", 0o600)
    async with httpx.AsyncClient(
        headers={"Authorization": "Bearer " + token}, timeout=40, trust_env=False
    ) as client:
        base = f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/instances/{INSTANCE}"

        async def mutate(method, path, data):
            response = await client.request(method, base + path, json=data)
            if response.status_code >= 400:
                raise RuntimeError("Cloud SQL API operation failed with status " + str(response.status_code))
            name = response.json().get("name")
            for _ in range(100):
                result = await client.get(
                    f"https://sqladmin.googleapis.com/sql/v1beta4/projects/{PROJECT}/operations/{name}"
                )
                if result.json().get("status") == "DONE":
                    if result.json().get("error"):
                        raise RuntimeError("Cloud SQL asynchronous operation failed")
                    return
                await asyncio.sleep(1)
            raise RuntimeError("Cloud SQL operation pending")

        await mutate("PUT", "/users?name=postgres", {"name": "postgres", "password": passwords["postgres"]})
        await mutate("POST", "/databases", {"name": "tripbudget"})
        await mutate(
            "POST", "/users", {"name": "tripbudget_runtime", "password": passwords["tripbudget_runtime"]}
        )
    admin = "postgresql://postgres:" + passwords["postgres"] + "@127.0.0.1:55435/tripbudget"
    await Store(
        settings.model_copy(update={"database_url": __import__("pydantic").SecretStr(admin)})
    ).migrate()
    async with await psycopg.AsyncConnection.connect(admin, autocommit=True) as conn:
        await conn.execute("GRANT CONNECT ON DATABASE tripbudget TO tripbudget_runtime")
        await conn.execute("GRANT USAGE ON SCHEMA public TO tripbudget_runtime")
        await conn.execute(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO tripbudget_runtime"
        )
        await conn.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO tripbudget_runtime")
        await conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        await conn.execute("REVOKE cloudsqlsuperuser FROM tripbudget_runtime")
        await conn.execute("ALTER ROLE tripbudget_runtime NOCREATEROLE NOCREATEDB NOREPLICATION")
    prefix = "postgresql://tripbudget_runtime:" + passwords["tripbudget_runtime"]
    dsn = prefix + "@/tripbudget?host=/cloudsql/" + PROJECT + ":us-central1:" + INSTANCE
    Path(".secrets/cloud-runtime-local.env").write_text(
        "TRIPBUDGET_DATABASE_URL=" + prefix + "@127.0.0.1:55435/tripbudget\n"
    )
    os.chmod(".secrets/cloud-runtime-local.env", 0o600)
    account = "a4-tripbudget@" + PROJECT + ".iam.gserviceaccount.com"
    gcloud("iam", "service-accounts", "create", "a4-tripbudget", "--display-name=Assignment 4 TripBudgetAI")
    gcloud(
        "projects",
        "add-iam-policy-binding",
        PROJECT,
        "--member=serviceAccount:" + account,
        "--role=roles/cloudsql.client",
        "--condition=None",
    )
    for name, value in [
        ("db", dsn),
        ("nvidia", settings.nvidia_api_key.get_secret_value()),
        ("tavily", settings.tavily_api_key.get_secret_value()),
    ]:
        gcloud(
            "secrets",
            "create",
            "a4-tripbudget-" + name,
            "--replication-policy=automatic",
            "--data-file=-",
            input=value,
        )
        gcloud(
            "secrets",
            "add-iam-policy-binding",
            "a4-tripbudget-" + name,
            "--member=serviceAccount:" + account,
            "--role=roles/secretmanager.secretAccessor",
        )
    gcloud(
        "artifacts",
        "repositories",
        "create",
        "a4-tripbudget",
        "--repository-format=docker",
        "--location=us-central1",
        "--description=Isolated Assignment 4 capstone",
    )
    Path("deliverables/evidence/cloud-provisioning.json").write_text(
        json.dumps(
            {
                "database": "a4-tripbudget",
                "region": "us-central1",
                "database_version": "POSTGRES_16",
                "tier": "db-f1-micro",
                "runtime_role": "DML on application and official checkpoint tables; no schema CREATE",
                "secrets": "dedicated a4-tripbudget-*; never in source",
            },
            indent=2,
        )
    )
    print(
        "Dedicated A4 database, restricted runtime user, service account, secrets and image registry initialized."
    )


if __name__ == "__main__":
    asyncio.run(main())
