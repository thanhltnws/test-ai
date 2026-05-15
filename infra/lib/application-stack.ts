import * as cdk from 'aws-cdk-lib';
import {
  aws_lambda as lambda,
  aws_iam as iam,
  aws_scheduler as scheduler,
  aws_ec2 as ec2,
  aws_rds as rds,
  aws_s3 as s3,
  aws_s3_notifications as s3n,
  aws_secretsmanager as secretsmanager,
  custom_resources as cr,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as path from 'path';
import * as fs from 'fs';
import * as crypto from 'crypto';
import { spawnSync } from 'child_process';

type BundleCopy = {
  source: string;
  target?: string;
};

function tryLocalPythonBundle(
  cwd: string,
  requirementsPath: string,
  outputDir: string,
  copies: BundleCopy[],
): boolean {
  fs.rmSync(outputDir, { recursive: true, force: true });
  fs.mkdirSync(outputDir, { recursive: true });

  const pipArgs = [
    'install',
    '-r',
    requirementsPath,
    '--platform',
    'manylinux2014_x86_64',
    '--implementation',
    'cp',
    '--python-version',
    '3.12',
    '--only-binary=:all:',
    '-t',
    outputDir,
    '--quiet',
  ];

  const candidates = [
    {
      command: 'python3',
      args: ['-m', 'pip', ...pipArgs],
      probeArgs: ['-m', 'pip', '--version'],
    },
    {
      command: 'python',
      args: ['-m', 'pip', ...pipArgs],
      probeArgs: ['-m', 'pip', '--version'],
    },
    {
      command: 'pip',
      args: pipArgs,
      probeArgs: ['--version'],
    },
  ];

  const commands = candidates.filter(({ command, probeArgs }) => {
    const probe = spawnSync(command, probeArgs, { cwd, stdio: 'ignore' });
    return probe.status === 0;
  });

  const pip = commands
    .map(({ command, args }) =>
      spawnSync(command, args, { cwd, stdio: 'inherit' }),
    )
    .find((result) => result.status === 0);

  if (!pip) {
    return false;
  }

  try {
    for (const copy of copies) {
      fs.cpSync(
        path.join(cwd, copy.source),
        path.join(outputDir, copy.target ?? copy.source),
        { recursive: true },
      );
    }
  } catch (error) {
    console.warn('Local Lambda bundling copy failed:', error);
    return false;
  }

  return true;
}

export class ApplicationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);
    // ── App auth token (Secrets Manager) ──────────────────────────────────────
    // Token value comes from APP_AUTH_TOKEN env var at deploy time.
    // Lambda reads it at runtime via the ARN — never stored in CloudFormation.
    const appAuthTokenSecret = new secretsmanager.Secret(this, 'AppAuthTokenSecret', {
      secretName: 'ai-insight-hub/app-auth-token',
      description: 'Shared auth token for chat and batch Lambda Function URLs',
      ...(process.env.APP_AUTH_TOKEN
        ? { secretStringValue: cdk.SecretValue.unsafePlainText(process.env.APP_AUTH_TOKEN) }
        : { generateSecretString: { excludePunctuation: true, passwordLength: 32 } }),
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // ── VPC (public subnets only, no NAT Gateway) ──────────────────────────────
    // Aurora sits here with publiclyAccessible=true.
    // Lambda stays OUTSIDE this VPC → retains default internet access
    // → can reach Bedrock without NAT Gateway.
    const vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
      ],
    });

    // ── Aurora security group ──────────────────────────────────────────────────
    // Demo only: open 5432 to internet so Lambda (outside VPC) can connect.
    const dbSg = new ec2.SecurityGroup(this, 'DbSg', {
      vpc,
      description: 'Aurora PostgreSQL - public access (demo only)',
      allowAllOutbound: false,
    });
    dbSg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(5432),
      'PostgreSQL - demo only, restrict to known IPs for production',
    );

    // ── Aurora Serverless v2 ───────────────────────────────────────────────────
    // fromGeneratedSecret: auto-generates credentials and stores them in
    // Secrets Manager. No password in CDK code or CloudFormation template.
    const cluster = new rds.DatabaseCluster(this, 'AuroraCluster', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_4,
      }),
      writer: rds.ClusterInstance.serverlessV2('writer', {
        publiclyAccessible: true,
      }),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      securityGroups: [dbSg],
      defaultDatabaseName: 'ai_insight_hub',
      credentials: rds.Credentials.fromGeneratedSecret('postgres'),
      removalPolicy: cdk.RemovalPolicy.SNAPSHOT,
    });

    // ── DB schema bootstrap ───────────────────────────────────────────────────
    // Runs the idempotent MVP schema against Aurora after the cluster is ready.
    // This creates pgvector, signals, signal_embeddings, and insights.
    const dbInitDir = path.join(__dirname, '../lambda/db-init');
    const dbInitHash = crypto
      .createHash('sha256')
      .update(fs.readFileSync(path.join(dbInitDir, 'handler.py')))
      .digest('hex');

    const dbInitFn = new lambda.Function(this, 'DbInitFn', {
      functionName: 'ai-insight-hub-db-init',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(dbInitDir, {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r requirements.txt -t /asset-output --quiet && cp -r . /asset-output',
          ],
          local: {
            tryBundle(outputDir: string): boolean {
              return tryLocalPythonBundle(dbInitDir, 'requirements.txt', outputDir, [
                { source: '.', target: '.' },
              ]);
            },
          },
        },
      }),
      timeout: cdk.Duration.minutes(2),
      memorySize: 256,
      environment: {
        DB_SECRET_ARN: cluster.secret!.secretArn,
      },
      description: 'Custom resource handler: initialize Aurora schema for MVP/PoC',
    });

    cluster.secret!.grantRead(dbInitFn);

    const dbInitProvider = new cr.Provider(this, 'DbInitProvider', {
      onEventHandler: dbInitFn,
    });

    const dbInit = new cdk.CustomResource(this, 'DbSchema', {
      serviceToken: dbInitProvider.serviceToken,
      properties: {
        SchemaHash: dbInitHash,
      },
    });
    dbInit.node.addDependency(cluster);

    // ── S3 raw landing zone ───────────────────────────────────────────────────
    const rawBucket = new s3.Bucket(this, 'RawBucket', {
      bucketName: `ai-insight-hub-raw-${this.account}-${this.region}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // ── Ingestion Lambda ───────────────────────────────────────────────────────
    // Reads sources.json + mock/ files → writes raw JSON to S3.
    // Triggered manually via Function URL for demo (no schedule).
    const ingestionFn = new lambda.Function(this, 'IngestionFn', {
      functionName: 'ai-insight-hub-ingestion',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(
        path.join(__dirname, '../../backend/ingestion'),
        {
          bundling: {
            image: lambda.Runtime.PYTHON_3_12.bundlingImage,
            command: [
              'bash', '-c',
              'pip install -r requirements.txt --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -t /asset-output --quiet && cp -r . /asset-output',
            ],
            local: {
              tryBundle(outputDir: string): boolean {
                const srcDir = path.join(__dirname, '../../backend/ingestion');
                return tryLocalPythonBundle(srcDir, 'requirements.txt', outputDir, [
                  { source: '.', target: '.' },
                ]);
              },
            },
          },
        },
      ),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        S3_BUCKET: rawBucket.bucketName,
      },
      description: 'Ingestion: read sources.json → write raw JSON to S3 raw/',
    });

    rawBucket.grantPut(ingestionFn);

    const ingestionUrl = ingestionFn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.POST],
        allowedHeaders: ['Content-Type'],
      },
    });

    // Hourly schedule — DISABLED for demo (trigger manually via Function URL or
    // upload JSON directly to S3 raw/ to kick off transform).
    const ingestionSchedulerRole = new iam.Role(this, 'IngestionSchedulerRole', {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
      description: 'Allows EventBridge Scheduler to invoke the ingestion Lambda',
    });
    ingestionFn.grantInvoke(ingestionSchedulerRole);

    new scheduler.CfnSchedule(this, 'HourlyIngestionSchedule', {
      name: 'ai-insight-hub-hourly-ingestion',
      description: 'Trigger ingestion Lambda hourly to pull from configured sources',
      state: 'DISABLED',
      scheduleExpression: 'cron(0 * * * ? *)',
      scheduleExpressionTimezone: 'UTC',
      flexibleTimeWindow: { mode: 'OFF' },
      target: {
        arn: ingestionFn.functionArn,
        roleArn: ingestionSchedulerRole.roleArn,
        retryPolicy: {
          maximumRetryAttempts: 2,
          maximumEventAgeInSeconds: 3600,
        },
      },
    });

    // ── Transform Lambda ──────────────────────────────────────────────────────
    // Triggered by S3 ObjectCreated on raw/ prefix.
    // Normalizes records, calls Bedrock for extraction + embedding, writes to Aurora.
    const transformDir = path.join(__dirname, '../../backend/transform');
    const transformFn = new lambda.Function(this, 'TransformFn', {
      functionName: 'ai-insight-hub-transform',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(transformDir, {
        bundling: {
          image: lambda.Runtime.PYTHON_3_12.bundlingImage,
          command: [
            'bash', '-c',
            'pip install -r requirements.txt --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -t /asset-output --quiet && cp -r . /asset-output',
          ],
          local: {
            tryBundle(outputDir: string): boolean {
              return tryLocalPythonBundle(transformDir, 'requirements.txt', outputDir, [
                { source: '.', target: '.' },
              ]);
            },
          },
        },
      }),
      timeout: cdk.Duration.minutes(10),
      memorySize: 512,
      environment: {
        DB_SECRET_ARN: cluster.secret!.secretArn,
        BEDROCK_MODEL_ID: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
      },
      description: 'Transform: S3 ObjectCreated raw/ → normalize → Bedrock extract → Aurora signals + pgvector',
    });

    cluster.secret!.grantRead(transformFn);
    transformFn.node.addDependency(dbInit);

    transformFn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'TransformBedrockInvoke',
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    // Read raw files + manage processed=true tag for idempotency
    rawBucket.grantRead(transformFn);
    transformFn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'TransformS3Tags',
      actions: ['s3:GetObjectTagging', 's3:PutObjectTagging'],
      resources: [rawBucket.arnForObjects('*')],
    }));

    rawBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(transformFn),
      { prefix: 'raw/' },
    );

    // ── Insights Builder Lambda ────────────────────────────────────────────────
    // Lambda is NOT in a VPC — has full internet access for Bedrock.
    // Reads DB credentials from Secrets Manager at cold start via DB_SECRET_ARN.
    const insightsBuilderFn = new lambda.Function(this, 'InsightsBuilderFn', {
      functionName: 'ai-insight-hub-insights-builder',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(
        path.join(__dirname, '../../backend/application'),
        {
          bundling: {
            image: lambda.Runtime.PYTHON_3_12.bundlingImage,
            command: [
              'bash', '-c',
              'pip install -r batch/requirements.txt -t /asset-output --quiet && cp -r batch/. /asset-output && cp -r common /asset-output/common',
            ],
            local: {
              tryBundle(outputDir: string): boolean {
                const srcDir = path.join(__dirname, '../../backend/application');
                return tryLocalPythonBundle(
                  srcDir,
                  'batch/requirements.txt',
                  outputDir,
                  [
                    { source: 'batch/.', target: '.' },
                    { source: 'common', target: 'common' },
                  ],
                );
              },
            },
          },
        },
      ),
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      environment: {
        DB_SECRET_ARN: cluster.secret!.secretArn,
        APP_AUTH_TOKEN_SECRET_ARN: appAuthTokenSecret.secretArn,
        BEDROCK_MODEL_ID: 'global.anthropic.claude-haiku-4-5-20251001-v1:0',
        BEDROCK_EMBEDDING_MODEL_ID: 'cohere.embed-multilingual-v3',
      },
      description: 'Insights builder: Aurora signals aggregates + Bedrock → insights table',
    });

    // Grant Lambda read access to the Aurora credentials secret and app auth token
    cluster.secret!.grantRead(insightsBuilderFn);
    appAuthTokenSecret.grantRead(insightsBuilderFn);
    insightsBuilderFn.node.addDependency(dbInit);

    insightsBuilderFn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'BedrockInvokeModel',
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    // ── Lambda Function URL ────────────────────────────────────────────────────
    const insightsBuilderUrl = insightsBuilderFn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.POST],
        allowedHeaders: ['Content-Type', 'Authorization', 'X-App-Token'],
      },
    });

    // ── EventBridge Scheduler ──────────────────────────────────────────────────
    const schedulerRole = new iam.Role(this, 'SchedulerRole', {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
      description: 'Allows EventBridge Scheduler to invoke the insights-builder Lambda',
    });
    insightsBuilderFn.grantInvoke(schedulerRole);

    new scheduler.CfnSchedule(this, 'DailyInsightsBuilderSchedule', {
      name: 'ai-insight-hub-daily-insights-builder',
      description: 'Trigger daily insights-builder compute at 02:00 UTC',
      // TODO: Enable this for a live environment. Disabled for MVP demos so
      // insights-builder runs are triggered manually through the Function URL.
      state: 'DISABLED',
      scheduleExpression: 'cron(0 2 * * ? *)',
      scheduleExpressionTimezone: 'UTC',
      flexibleTimeWindow: { mode: 'OFF' },
      target: {
        arn: insightsBuilderFn.functionArn,
        roleArn: schedulerRole.roleArn,
        retryPolicy: {
          maximumRetryAttempts: 2,
          maximumEventAgeInSeconds: 3600,
        },
      },
    });

    // ── API Lambda ─────────────────────────────────────────────────────────────
    const dashboardApiFn = new lambda.Function(this, 'DashboardApiFn', {
      functionName: 'ai-insight-hub-dashboard-api',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(
        path.join(__dirname, '../../backend/application/api'),
        {
          bundling: {
            image: lambda.Runtime.PYTHON_3_12.bundlingImage,
            command: [
              'bash', '-c',
              'pip install -r requirements.txt --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 -t /asset-output --quiet && cp -r . /asset-output',
            ],
            local: {
              tryBundle(outputDir: string): boolean {
                const srcDir = path.join(__dirname, '../../backend/application/api');
                return tryLocalPythonBundle(srcDir, 'requirements.txt', outputDir, [
                  { source: '.', target: '.' },
                ]);
              },
            },
          },
        },
      ),
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        DB_SECRET_ARN: cluster.secret!.secretArn,
      },
      description: 'Dashboard API: GET /insights',
    });

    cluster.secret!.grantRead(dashboardApiFn);
    dashboardApiFn.node.addDependency(dbInit);

    const dashboardApiUrl = dashboardApiFn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.GET],
        allowedHeaders: ['Content-Type'],
      },
    });

    // ── Chat Lambda (Feature 2 — Chatbox / RAG) ───────────────────────────────
    const chatFn = new lambda.Function(this, 'ChatFn', {
      functionName: 'ai-insight-hub-chat',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset(
        path.join(__dirname, '../../backend/application'),
        {
          bundling: {
            image: lambda.Runtime.PYTHON_3_12.bundlingImage,
            command: [
              'bash', '-c',
              'pip install -r chat/requirements.txt -t /asset-output --quiet && cp -r chat/. /asset-output && cp -r common /asset-output/common',
            ],
            local: {
              tryBundle(outputDir: string): boolean {
                const srcDir = path.join(__dirname, '../../backend/application');
                return tryLocalPythonBundle(
                  srcDir,
                  'chat/requirements.txt',
                  outputDir,
                  [
                    { source: 'chat/.', target: '.' },
                    { source: 'common', target: 'common' },
                  ],
                );
              },
            },
          },
        },
      ),
      timeout: cdk.Duration.seconds(60),
      memorySize: 512,
      environment: {
        DB_SECRET_ARN: cluster.secret!.secretArn,
        APP_AUTH_TOKEN_SECRET_ARN: appAuthTokenSecret.secretArn,
        BEDROCK_MODEL_ID: 'global.anthropic.claude-sonnet-4-6',
        BEDROCK_EMBEDDING_MODEL_ID: 'cohere.embed-multilingual-v3',
      },
      description: 'Chat endpoint: POST /chat → Aurora + pgvector context → Bedrock Sonnet → { answer, references }',
    });

    cluster.secret!.grantRead(chatFn);
    appAuthTokenSecret.grantRead(chatFn);
    chatFn.node.addDependency(dbInit);

    chatFn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'BedrockInvokeModelChat',
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    const chatUrl = chatFn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.POST],
        allowedHeaders: ['Content-Type', 'Authorization', 'X-App-Token'],
      },
    });

    // ── Outputs ────────────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, 'AuroraEndpoint', {
      value: cluster.clusterEndpoint.hostname,
      description: 'Aurora endpoint - use for psql client and seed import',
    });

    new cdk.CfnOutput(this, 'DbSecretArn', {
      value: cluster.secret!.secretArn,
      description: 'Secrets Manager ARN - retrieve credentials via: aws secretsmanager get-secret-value --secret-id <arn>',
    });

    new cdk.CfnOutput(this, 'InsightsBuilderFunctionUrl', {
      value: insightsBuilderUrl.url,
      description: 'POST to manually trigger insights-builder run',
    });

    new cdk.CfnOutput(this, 'InsightsBuilderFunctionArn', {
      value: insightsBuilderFn.functionArn,
    });

    new cdk.CfnOutput(this, 'DashboardApiFunctionUrl', {
      value: dashboardApiUrl.url,
      description: 'GET /insights — dashboard data',
    });

    new cdk.CfnOutput(this, 'ChatFunctionUrl', {
      value: chatUrl.url,
      description: 'POST /chat — { question } → { answer, references }',
    });

    new cdk.CfnOutput(this, 'IngestionFunctionUrl', {
      value: ingestionUrl.url,
      description: 'POST to manually trigger ingestion run → writes raw/ to S3',
    });

    new cdk.CfnOutput(this, 'RawBucketName', {
      value: rawBucket.bucketName,
      description: 'S3 bucket for raw ingestion data',
    });

    new cdk.CfnOutput(this, 'AppAuthTokenSecretArn', {
      value: appAuthTokenSecret.secretArn,
      description: 'Secrets Manager ARN for app auth token — retrieve via: aws secretsmanager get-secret-value --secret-id <arn>',
    });
  }
}
