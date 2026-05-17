# AI Insight Hub Infra

CDK stack for the internal demo:

- Aurora PostgreSQL Serverless v2 with pgvector
- DB schema bootstrap custom resource
- S3 raw bucket (landing zone for ingested data)
- Ingestion Lambda + EventBridge Scheduler (hourly)
- Transform Lambda (S3 trigger → Lambda ETL + Bedrock extraction → Aurora)
- Insights Builder Lambda + EventBridge Scheduler (daily batch)
- Dashboard API Lambda Function URL (`GET /insights`)
- Chat Lambda Function URL (`POST /chat`)

## EventBridge Scheduler

Both schedules are created but intentionally disabled for the demo.
This keeps demos deterministic and avoids unexpected Bedrock/Aurora usage while
each Lambda can still be triggered manually through its Function URL.

- **Ingestion** (`HourlyIngestionSchedule`) — `cron(0 * * * ? *)`, hourly
- **Insights Builder** (`DailyInsightsBuilderSchedule`) — `cron(0 2 * * ? *)`, daily at 02:00 UTC

To enable, set `state: 'ENABLED'` on the relevant `CfnSchedule` in `lib/application-stack.ts`.

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
- `RawBucketName`
- `IngestionFunctionUrl`
- `InsightsBuilderFunctionUrl`
- `DashboardApiFunctionUrl`
- `ChatFunctionUrl`

## Seed AWS Database

After deploy, fetch DB credentials using the helper in [Get DB credentials by ARN](#get-db-credentials-by-arn) and build a `DATABASE_URL`:

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

All commands below use PowerShell.

### Get stack outputs

```powershell
aws cloudformation describe-stacks `
  --stack-name AiInsightHubApplication `
  --query "Stacks[0].Outputs" `
  --output table
```

### Get DB credentials by ARN

```powershell
aws secretsmanager get-secret-value `
  --secret-id <DbSecretArn> `
  --query SecretString `
  --output text | ConvertFrom-Json
```

### Get app auth token

```powershell
aws secretsmanager get-secret-value `
  --secret-id <AppAuthTokenSecretArn> `
  --query SecretString `
  --output text
```

### Invoke Function URLs

Chat (requires auth token):

```powershell
Invoke-RestMethod `
  -Method POST `
  -Uri "<ChatFunctionUrl>" `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer <AppAuthToken>" } `
  -Body '{"question":"What operational bugs are affecting order management and invoicing?"}'
```

Batch (requires auth token):

```powershell
Invoke-RestMethod `
  -Method POST `
  -Uri "<InsightsBuilderFunctionUrl>" `
  -Headers @{ Authorization = "Bearer <AppAuthToken>" }
```

Dashboard API:

```powershell
Invoke-RestMethod -Method GET -Uri "<DashboardApiFunctionUrl>"
```
