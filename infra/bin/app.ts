import * as cdk from 'aws-cdk-lib';
import { ApplicationStack } from '../lib/application-stack';

const app = new cdk.App();

new ApplicationStack(app, 'AiInsightHubApplication', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION ?? 'ap-southeast-1',
  },
  description: 'AI Insight Hub — Application layer (Batch Lambda + EventBridge)',
});
