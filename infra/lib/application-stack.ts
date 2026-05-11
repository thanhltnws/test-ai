import * as cdk from 'aws-cdk-lib';
import {
  aws_lambda as lambda,
  aws_iam as iam,
  aws_scheduler as scheduler,
  aws_ec2 as ec2,
  aws_rds as rds,
  custom_resources as cr,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as path from 'path';
import * as fs from 'fs';
import * as crypto from 'crypto';
import { spawnSync } from 'child_process';

export class ApplicationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

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
    // This creates pgvector, insights, insight_embeddings, and recommendations.
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
              if (process.platform === 'win32') return false;
              const pip = spawnSync('pip', [
                'install', '-r', 'requirements.txt',
                '-t', outputDir, '--quiet',
              ], { cwd: dbInitDir, stdio: 'inherit' });
              if (pip.status !== 0) return false;
              fs.cpSync(dbInitDir, outputDir, { recursive: true });
              return true;
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

    // ── Batch Lambda ───────────────────────────────────────────────────────────
    // Lambda is NOT in a VPC — has full internet access for Bedrock.
    // Reads DB credentials from Secrets Manager at cold start via DB_SECRET_ARN.
    const batchFn = new lambda.Function(this, 'BatchFn', {
      functionName: 'ai-insight-hub-batch',
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'handler.handler',
      code: lambda.Code.fromAsset(
        path.join(__dirname, '../../backend/application/batch'),
        {
          bundling: {
            image: lambda.Runtime.PYTHON_3_12.bundlingImage,
            command: [
              'bash', '-c',
              'pip install -r requirements.txt -t /asset-output --quiet && cp -r . /asset-output',
            ],
            local: {
              tryBundle(outputDir: string): boolean {
                if (process.platform === 'win32') return false;
                const srcDir = path.join(__dirname, '../../backend/application/batch');
                const pip = spawnSync('pip', [
                  'install', '-r', 'requirements.txt',
                  '-t', outputDir, '--quiet',
                ], { cwd: srcDir, stdio: 'inherit' });
                if (pip.status !== 0) return false;
                fs.cpSync(srcDir, outputDir, { recursive: true });
                return true;
              },
            },
          },
        },
      ),
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      environment: {
        DB_SECRET_ARN: cluster.secret!.secretArn,
        BEDROCK_MODEL_ID: 'apac.anthropic.claude-3-haiku-20240307-v1:0',
        BEDROCK_EMBEDDING_MODEL_ID: 'apac.amazon.titan-embed-text-v2:0',
      },
      description: 'Daily batch: Aurora aggregates + Bedrock → recommendations table',
    });

    // Grant Lambda read access to the Aurora credentials secret
    cluster.secret!.grantRead(batchFn);
    batchFn.node.addDependency(dbInit);

    batchFn.addToRolePolicy(new iam.PolicyStatement({
      sid: 'BedrockInvokeModel',
      actions: ['bedrock:InvokeModel'],
      resources: ['*'],
    }));

    // ── Lambda Function URL ────────────────────────────────────────────────────
    const batchUrl = batchFn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.POST],
        allowedHeaders: ['Content-Type'],
      },
    });

    // ── EventBridge Scheduler ──────────────────────────────────────────────────
    const schedulerRole = new iam.Role(this, 'SchedulerRole', {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
      description: 'Allows EventBridge Scheduler to invoke the batch Lambda',
    });
    batchFn.grantInvoke(schedulerRole);

    new scheduler.CfnSchedule(this, 'DailyBatchSchedule', {
      name: 'ai-insight-hub-daily-batch',
      description: 'Trigger daily insight batch compute at 02:00 UTC',
      // TODO: Enable this for a live environment. Disabled for MVP demos so
      // batch runs are triggered manually through the Function URL.
      state: 'DISABLED',
      scheduleExpression: 'cron(0 2 * * ? *)',
      scheduleExpressionTimezone: 'UTC',
      flexibleTimeWindow: { mode: 'OFF' },
      target: {
        arn: batchFn.functionArn,
        roleArn: schedulerRole.roleArn,
        retryPolicy: {
          maximumRetryAttempts: 2,
          maximumEventAgeInSeconds: 3600,
        },
      },
    });

    // ── API Lambda ─────────────────────────────────────────────────────────────
    const apiFn = new lambda.Function(this, 'ApiFn', {
      functionName: 'ai-insight-hub-api',
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
                if (process.platform === 'win32') return false;
                const srcDir = path.join(__dirname, '../../backend/application/api');
                const pip = spawnSync('pip', [
                  'install', '-r', 'requirements.txt',
                  '-t', outputDir, '--quiet',
                ], { cwd: srcDir, stdio: 'inherit' });
                if (pip.status !== 0) return false;
                fs.cpSync(srcDir, outputDir, { recursive: true });
                return true;
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
      description: 'REST API: GET /recommendations',
    });

    cluster.secret!.grantRead(apiFn);
    apiFn.node.addDependency(dbInit);

    const apiUrl = apiFn.addFunctionUrl({
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
        path.join(__dirname, '../../backend/application/chat'),
        {
          bundling: {
            image: lambda.Runtime.PYTHON_3_12.bundlingImage,
            command: [
              'bash', '-c',
              'pip install -r requirements.txt -t /asset-output --quiet && cp -r . /asset-output',
            ],
            local: {
              tryBundle(outputDir: string): boolean {
                if (process.platform === 'win32') return false;
                const srcDir = path.join(__dirname, '../../backend/application/chat');
                const pip = spawnSync('pip', [
                  'install', '-r', 'requirements.txt',
                  '-t', outputDir, '--quiet',
                ], { cwd: srcDir, stdio: 'inherit' });
                if (pip.status !== 0) return false;
                fs.cpSync(srcDir, outputDir, { recursive: true });
                return true;
              },
            },
          },
        },
      ),
      timeout: cdk.Duration.seconds(60),
      memorySize: 512,
      environment: {
        DB_SECRET_ARN: cluster.secret!.secretArn,
        BEDROCK_MODEL_ID: 'apac.anthropic.claude-3-5-sonnet-20241022-v2:0',
        BEDROCK_EMBEDDING_MODEL_ID: 'apac.amazon.titan-embed-text-v2:0',
      },
      description: 'Chat endpoint: POST /chat → Aurora + pgvector context → Bedrock Sonnet → { answer, references }',
    });

    cluster.secret!.grantRead(chatFn);
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
        allowedHeaders: ['Content-Type'],
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

    new cdk.CfnOutput(this, 'BatchFunctionUrl', {
      value: batchUrl.url,
      description: 'POST to manually trigger a batch run',
    });

    new cdk.CfnOutput(this, 'BatchFunctionArn', {
      value: batchFn.functionArn,
    });

    new cdk.CfnOutput(this, 'ApiFunctionUrl', {
      value: apiUrl.url,
      description: 'GET /recommendations or GET /insights',
    });

    new cdk.CfnOutput(this, 'ChatFunctionUrl', {
      value: chatUrl.url,
      description: 'POST /chat — { question } → { answer, references }',
    });
  }
}
