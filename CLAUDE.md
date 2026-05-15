# CLAUDE.md — Development Guide for Amir Ghahari Website Backend

This file is for Claude. The human-readable version is README-code.md.

## Project Purpose

Serverless AWS backend and infrastructure-as-code for **amir-ghahari.dev**.
This repo owns all CloudFormation stacks, the Lambda contact form handler, and the
backend CI/CD pipeline. The frontend (Next.js/Plasmic) lives in a separate repo.

---

## Repository Layout

```
.
├── cloudformation/
│   ├── 01-foundation.yaml     # S3 buckets (lambda code, logs, pipeline artifacts)
│   ├── 02-website.yaml        # CloudFront + static hosting + all backend API
│   └── 03-cicd-backend.yaml   # CodePipeline + CodeBuild (deploys all 3 stacks)
├── config/
│   └── deployment.json        # Central config — ALL parameter values for all 3 stacks
├── lambda/
│   └── post_contact/
│       ├── website_post_contact.py   # Lambda handler
│       └── requirements.txt          # boto3 only (pre-installed in Lambda runtime)
├── buildspec/
│   └── backend-buildspec.yml         # CodeBuild instructions
├── scripts/
│   ├── deploy.sh              # Local deployment script (reads deployment.json)
│   └── generate-cfn-configs.py  # Generates per-stack TemplateConfiguration JSONs from deployment.json
└── .gitignore
```

**Never commit `*.zip` files** — the Lambda ZIP is built in CI and uploaded to S3.
**Never commit `config/*-config.json` files** — they are generated at build time from `deployment.json`.

The static website S3 bucket (`amirghahari-website`) is managed by the **frontend repo's**
`infra/pipeline.yaml` stack, not by any stack in this repo.

---

## Central Config: `config/deployment.json`

**All environment-specific values live here.** Edit this file when changing resource names,
domain names, email addresses, or AWS identifiers. Do not edit parameter defaults inside
the templates directly.

Structure:
```json
{
  "foundation": { "StackName": "...", "LoggingBucketName": "...", ... },
  "website":    { "StackName": "...", "FoundationStackName": "...", "CloudFrontCertArn": "...", ... },
  "cicd":       { "StackName": "...", "GitHubRepo": "...", ... }
}
```

`CloudFrontCertArn` must be updated to the actual ACM certificate ARN before first deployment.

At build time, `scripts/generate-cfn-configs.py` splits `deployment.json` into:
- `config/01-foundation-config.json` — CloudFormation TemplateConfiguration for the foundation stack
- `config/02-website-config.json` — CloudFormation TemplateConfiguration for the website stack
- `config/03-cicd-config.json` — CloudFormation TemplateConfiguration for the CI/CD stack

These generated files are included in the CodePipeline build artifact and consumed by the
deploy actions via `TemplateConfiguration`.

---

## 3-Stack Architecture

```
01-foundation  →  S3 shared infra (lambda code, logs, pipeline artifacts)
02-website     →  CloudFront + static hosting + DynamoDB + SNS + Lambda + API Gateway
03-cicd-backend →  CodePipeline + CodeBuild (deploys ALL 3 stacks on push to main)
```

The pipeline deploys stacks in sequence: Foundation → Website → itself (self-update).

The static website S3 bucket exists externally. Stack `02-website` references it by the
`StaticBucketName` parameter and owns its CloudFront OAC bucket policy.

---

## Stack 1: `cloudformation/01-foundation.yaml`

Creates shared S3 infrastructure that all other stacks import. Deploy first.

**Parameters (all with defaults in deployment.json):**
- `LoggingBucketName` — `amirghahari-website-access-logs`
- `LambdasBucketName` — `amir-ghahari-website-lambdas`
- `ArtifactsBucketName` — `amir-ghahari-pipeline-artifacts`

All buckets: `DeletionPolicy: Retain`, versioned, AES-256 encrypted.

**Exports** (format: `<StackName>-<Key>`):
- `<StackName>-LambdasBucketName`
- `<StackName>-LoggingBucketName`
- `<StackName>-ArtifactsBucketName`

Stack name default: `amir-ghahari-foundation`

---

## Stack 2: `cloudformation/02-website.yaml`

All application resources in one deployable unit. Updated by CI/CD on every push.

**Parameters (16 total — all with defaults, all in deployment.json):**
- `FoundationStackName`, `StaticBucketName`, `CloudFrontCertArn`
- `HostedZoneId`, `CloudFrontAlias`, `RootDomain`, `ApiDomain`
- `NotificationEmail`
- `ContactTableName`, `ContactSNSTopicName`
- `LambdaFunctionName`, `LambdaRoleName`, `LambdaS3Key`
- `ApiGatewayRoleName`, `ApiName`, `ApiStageName`

**Static Hosting section:**
- `WebsiteOAC` — CloudFront Origin Access Control (sigv4, always-sign)
- `WebsiteStaticBucketPolicy` — grants CloudFront OAC read on the existing static bucket
- `WebsiteCloudfrontDistribution` — serves static site, alias = `!Ref CloudFrontAlias`
- Route53: `!Ref CloudFrontAlias` → CloudFront, `www.!Ref RootDomain` → root

**Backend API section:**
- `DynamoDBWebsiteContactTable` — composite key: `contact-id` (HASH) + `created-at` (RANGE)
  - `BillingMode: PROVISIONED` (1 RCU / 1 WCU), `DeletionPolicy: Retain`
- `WebsiteContactSNSTopic` + `MySubscription` (email to `!Ref NotificationEmail`)
- `WebsiteContactSNSTopicPolicy` — allows ONLY the Lambda role to publish
- `WebsiteContactLambdaRole` — DynamoDB:PutItem + SNS:Publish + CloudWatch Logs
- `LambdaLogGroup` — `/aws/lambda/!Ref LambdaFunctionName`, 30-day retention
- `WebsiteContactLambda` — Python 3.12, 128 MB, 20s timeout
  - Code: `!ImportValue ${FoundationStackName}-LambdasBucketName` / `!Ref LambdaS3Key`
  - Env vars: `TABLE_NAME = !Ref DynamoDBWebsiteContactTable`, `TOPIC_ARN = !Ref WebsiteContactSNSTopic`
- `ApiGatewayLogGroup` — `/aws/apigateway/!Ref ApiName`, 30-day retention
- `ApiGatewayRole` + `ApiGatewayAccount` — CloudWatch Logs for API Gateway
- `WebsiteApi` — REST API, REGIONAL, name = `!Ref ApiName`
- `/contact-page` resource: POST (AWS_PROXY → Lambda, 3s timeout) + OPTIONS (MOCK CORS preflight)
- `ApiStage` — stage name = `!Ref ApiStageName`, INFO logging, throttle 5 RPS / 15 burst
- `ApiCertificateACM` — `!Ref ApiDomain`, DNS validated (ca-central-1)
- `ApiCustomDomain` + `ApiBasePathMapping` → maps `!Ref ApiDomain` → `!Ref ApiStageName` stage
- Route53: `!Ref ApiDomain` → API Gateway

**Exports:**
- `<StackName>-CloudFrontDistributionId` — used by frontend buildspec for cache invalidation
- `<StackName>-CloudFrontDomainName`
- `<StackName>-ApiUrl`
- `<StackName>-ContactEndpoint`
- `<StackName>-LambdaArn`

Stack name default: `amir-ghahari-website`

---

## Stack 3: `cloudformation/03-cicd-backend.yaml`

Backend deployment pipeline. Watches this GitHub repo and deploys all 3 stacks on every push.

**Parameters (20 total — all with defaults, all in deployment.json):**
- `FoundationStackName`, `BackendStackName`, `CicdStackName`
- `StaticBucketName`, `CloudFrontCertArn`
- `GitHubOwner`, `GitHubRepo`, `GitHubBranch`, `GitHubConnectionName`
- `CodeBuildProjectName`, `CodePipelineName`
- Cross-stack scoping params: `ContactTableName`, `ContactSNSTopicName`, `LambdaFunctionName`,
  `LambdaRoleName`, `ApiGatewayRoleName`, `HostedZoneId`, `LoggingBucketName`,
  `LambdasBucketName`, `ArtifactsBucketName`

**Pipeline stages:**
1. **Source** — GitHub via CodeStar Connection (`!Ref GitHubConnectionName`)
2. **Build** — CodeBuild runs `buildspec/backend-buildspec.yml`:
   - Zips `website_post_contact.py` → uploads to `LambdasBucketName`
   - Generates per-stack TemplateConfiguration JSONs from `config/deployment.json`
   - Validates all 3 templates
   - Outputs all 3 templates + 3 config JSONs as artifact
3. **Deploy** — 3 sequential CloudFormation `CREATE_UPDATE` actions:
   - RunOrder 1: `01-foundation.yaml` with `config/01-foundation-config.json`
   - RunOrder 2: `02-website.yaml` with `config/02-website-config.json`
   - RunOrder 3: `03-cicd-backend.yaml` with `config/03-cicd-config.json` (self-update)

**IAM roles created:**
- `amirghahari-backend-codebuild-role` — S3 + CF validate + CloudWatch Logs
- `amirghahari-backend-codepipeline-role` — S3 + CodeBuild + CF deploy + PassRole (all 3 stacks)
- `amirghahari-backend-cfn-deploy-role` — least-privilege for all resources across all 3 stacks
  (CloudFront, S3, DynamoDB, SNS, Lambda, IAM, API Gateway, ACM, Route53, CodePipeline, CodeBuild, CodeStar)

**One-time manual step after deploying this stack:**
AWS Console → CodePipeline → Settings → Connections → activate `!Ref GitHubConnectionName`

Stack name default: `amir-ghahari-cicd-backend`

---

## Cross-Stack Value Flow

### How stack 2 references the existing static S3 bucket:
```yaml
# In 02-website.yaml — parameter, not !ImportValue (bucket owned by frontend repo)
StaticBucketName:
  Type: String
  Default: amirghahari-website
```

### How the frontend buildspec gets the CloudFront Distribution ID:
Stack 2 exports `<StackName>-CloudFrontDistributionId`. The frontend CodeBuild project
reads it via an environment variable in the frontend `pipeline.yaml`:
```yaml
EnvironmentVariables:
  - Name: BUCKET_NAME
    Value: !Ref WebsiteBucketName        # existing env var, no change
  - Name: CF_DIST_ID
    Value: !ImportValue amir-ghahari-website-CloudFrontDistributionId
```
Then in the frontend `buildspec.yml`:
```bash
aws s3 sync out/ s3://$BUCKET_NAME --delete
aws cloudfront create-invalidation --distribution-id $CF_DIST_ID --paths "/*"
```

---

## Lambda Function

**File:** `lambda/post_contact/website_post_contact.py`

**Flow:**
```
POST /contact-page
  → parse JSON body
  → validate (name, email, subject, message all required; email regex)
  → DynamoDB PutItem (contact-id: UUID, created-at: UTC ISO, name, email, subject, message)
  → SNS Publish (email notification)
  → 200 { success: true, id: <uuid> }
```

**Environment variables** (set by CloudFormation, no hardcoded values):
- `TABLE_NAME` — DynamoDB table name
- `TOPIC_ARN` — SNS topic ARN

---

## Required Frontend `pipeline.yaml` Changes

Before deploying stack 2, the frontend `infra/pipeline.yaml` must be updated and
redeployed to:

**1. Remove from `WebsiteBucket` Properties:**
```yaml
# DELETE these two blocks:
PublicAccessBlockConfiguration:
  BlockPublicAcls: false
  ...
WebsiteConfiguration:
  IndexDocument: index.html
```

**2. Remove the entire `WebsiteBucketPolicy` resource** — stack 2 owns it now.

**3. Add to `CodeBuildRole` policy:**
```yaml
- Effect: Allow
  Action: cloudfront:CreateInvalidation
  Resource: '*'
```

**4. Add `CF_DIST_ID` to `BuildProject` environment variables** (see above).

**5. Remove `WebsiteBucketURL` output** (S3 static website endpoint is no longer valid).

---

## Local Deployment

Edit `config/deployment.json` first (especially `CloudFrontCertArn`), then:

```bash
# Deploy all 3 stacks in order
./scripts/deploy.sh

# Or deploy a single stack
./scripts/deploy.sh --stack foundation
./scripts/deploy.sh --stack website
./scripts/deploy.sh --stack cicd
```

Step 2 (frontend stack update) must happen before `--stack website`. The static bucket
cannot have two separate CloudFormation stacks managing its bucket policy simultaneously.

After deploying the CI/CD stack for the first time:
AWS Console → CodePipeline → Settings → Connections → activate the GitHub connection (one-time).

---

## Debugging

```bash
# Lambda logs
aws logs tail /aws/lambda/amirghahari-website-contact --follow

# API Gateway logs
aws logs tail /aws/apigateway/amirghahari-website-api --follow

# Test the endpoint
curl -X POST https://api.amir-ghahari.dev/contact-page \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","email":"test@example.com","subject":"Hi","message":"Hello"}'

# Check pipeline status
aws codepipeline get-pipeline-state --name amirghahari-backend-pipeline
```

---

## AWS Region

- Primary region: **ca-central-1**
- CloudFront ACM certificate: **us-east-1** (required by CloudFront, pre-created externally)
- Hosted Zone ID (amir-ghahari.dev): see `HostedZoneId` in `config/deployment.json`
