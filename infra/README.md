# AI Insight Hub Infra

CDK stack for the MVP/PoC:

- Aurora PostgreSQL Serverless v2 with pgvector
- DB schema bootstrap custom resource
- Batch Lambda + EventBridge Scheduler
- Chat Lambda Function URL
- Recommendations API Lambda Function URL

## EventBridge Scheduler

The daily batch schedule is created but intentionally disabled for the MVP/PoC.
This keeps demos deterministic and avoids unexpected Bedrock/Aurora usage while
the batch Lambda can still be triggered manually through `BatchFunctionUrl`.

To enable the automatic daily run later, update `DailyBatchSchedule` in
`lib/application-stack.ts` from:

```ts
state: 'DISABLED',
```

to:

```ts
state: 'ENABLED',
```

The configured cron is `cron(0 2 * * ? *)`, which runs at 02:00 UTC.

## Deploy

```powershell
cd infra
npm install
npm run build
npx cdk bootstrap
npx cdk deploy
```

The stack outputs:

- `AuroraEndpoint`
- `DbSecretArn`
- `BatchFunctionUrl`
- `ChatFunctionUrl`
- `ApiFunctionUrl`

## Seed AWS Database

After deploy, fetch the generated DB credentials:

```powershell
aws secretsmanager get-secret-value --secret-id <DbSecretArn>
```

Build a `DATABASE_URL` from the secret fields:

```text
postgresql://<username>:<password>@<host>:<port>/<dbname>
```

Then import the seed data from the repo root:

```powershell
$env:DATABASE_URL="postgresql://..."
$env:AWS_REGION="ap-southeast-1"
$env:SEED_EMBEDDING_PROVIDER="bedrock"
py backend/seed/import.py
```

## Test Function URLs

Chat:

```powershell
Invoke-RestMethod `
  -Method POST `
  -Uri "<ChatFunctionUrl>" `
  -ContentType "application/json" `
  -Body '{"question":"What operational bugs are affecting order management and invoicing?"}'
```

Batch:

```powershell
Invoke-RestMethod -Method POST -Uri "<BatchFunctionUrl>"
```

Recommendations:

```powershell
Invoke-RestMethod -Method GET -Uri "<ApiFunctionUrl>recommendations"
```
