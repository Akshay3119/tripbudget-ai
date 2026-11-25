# Deployment and operations

## Measured deployment

- Standard Cloud Run service `a4-tripbudget`, `us-central1`, 2 vCPU / 2 GiB, request timeout 300 s, concurrency 8, min 0 / max 2 instances.
- Dedicated PostgreSQL16 Enterprise instance `a4-tripbudget`, `db-f1-micro`, zonal, 10 GB storage, daily backup. This economical demo tier has no shared-core SLA and is not an HA production database.
- Dedicated service account with Cloud SQL client and access to only three `a4-tripbudget-*` secrets. The serving DB user has DML/sequence rights and no superuser, role-creation, database-creation or public-schema CREATE privileges. Migrations use an operator account.
- Cloud Run invocation is IAM restricted. Public unauthenticated deployment was rejected by automatic approval review; the safer IAM-restricted deployment succeeded. App endpoints additionally require an owner-scoped application session. Anonymous requests cannot invoke the app.
- Public cloud planning, approval and ledger commit were tested against actual Cloud Run/Cloud SQL. Restricted notes return `LOCAL_UNAVAILABLE` without a configured laptop bridge. No Tailscale grant was changed. The full hybrid app is demonstrated in the local recording.

## Reproduction

Use a Google Cloud project you own and a budget you control. Enable Run, SQL Admin, Artifact Registry and Secret Manager APIs. Create a dedicated SQL instance/database and a DML-only application user. Run `python -m scripts.manage migrate` as the migration owner before serving. Initialization is explicit; serving workers never create schemas or reset passwords.

`Dockerfile` builds linux/amd64 with the frozen uv lock, public BGE weights and a derived Chroma index; it runs as UID10001. `.dockerignore` is an allowlist excluding credentials, prior projects, user state, recordings and local models. Build with:

```sh
docker build --platform linux/amd64 -t YOUR_REGISTRY/tripbudget:RELEASE .
docker push YOUR_REGISTRY/tripbudget:RELEASE
```

Replace `PROJECT` and `RELEASE` in `cloudrun.yaml`. Create dedicated Secret Manager secrets containing the runtime PostgreSQL DSN, NVIDIA key and Tavily key; bind only the serving service account. Cloud SQL Unix socket DSN format is `postgresql://USER:PASSWORD@/tripbudget?host=/cloudsql/PROJECT:REGION:INSTANCE`. Use IAM-restricted invocation when deploying. Do not add an `allUsers` binding.

The one-time helpers `scripts/provision_cloud.py` and `scripts/push_image.py` record the procedure used for this release. They default to the owner's project; edit/configure the project before reuse and never run them against another assignment's resources. The initializer refuses to overwrite its saved local password file. Existing resources require a deliberate operator migration/rotation procedure, not rerunning initialization.

To inspect the private app, use `gcloud run services proxy a4-tripbudget --region us-central1 --project YOUR_PROJECT --port 8085` with an authorized identity. If the optional proxy component is unavailable, `scripts/cloud_smoke.py` demonstrates the separate short-lived IAM `X-Serverless-Authorization` header and application `Authorization` header. Tokens are held in memory and never printed or recorded. Do not put IAM identity tokens into the committed UI or video.

For a local runtime with the same cloud database, use the official Cloud SQL Auth Proxy bound to loopback and a private environment file. `scripts.manage create-user` writes a randomly generated credential to a mode-600 private file. Do not ship seeded passwords. Firebase verification is optional source support; the evaluated deployments use local Argon2 authentication, with IAM as an additional cloud boundary.

## Recovery and resource limits

Process replacement: restart Uvicorn/container, sign in, reload the episode and explicitly resume if needed. Waiting human approvals remain interrupts in PostgreSQL. Check the boot/revision identity from `/api/meta`; a browser refresh alone is not a durability test. Replays must retain the same decision key and payload. After evidence/approval expiry create a new plan; do not edit an immutable approved proposal or bypass expiry.

Connection capacity: one bounded eight-connection semaphore per serving Store, two active graph invocations/process and max two instances (16 app connections steady state; allow 32 for revision overlap plus operator headroom). A long invocation uses one session shared by business/checkpoint calls with a reentrant async lock. Request concurrency does not grant extra model authority. This is not a multi-tenant high-throughput capacity certification.

Observe health/readiness, HTTP error count/latency, `model_failure`, `terminal`, persisted usage reservations and approval age. `monitoring.yaml` is an operator dashboard/alert specification, not a claim that paid alert delivery was configured. Request logs omit bodies, headers, raw notes and secret values. Retain backups and test restoration before treating the demo tier as production infrastructure.

Cost control: min instances zero; maximum instances two; SQL is billed while provisioned. The report estimates weekly deployment and usage costs without assuming credits. Stop/delete only dedicated A4 resources when the owner decides they are no longer needed; no deletion or cleanup of A3 is part of this project. Container registry storage/backups may remain billable after serving stops.
