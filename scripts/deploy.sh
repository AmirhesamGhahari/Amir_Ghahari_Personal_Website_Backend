#!/usr/bin/env bash
# deploy.sh — Deploy one or all CloudFormation stacks using config/deployment.json.
#
# Usage:
#   ./scripts/deploy.sh                # deploys all 3 stacks in order
#   ./scripts/deploy.sh --stack foundation
#   ./scripts/deploy.sh --stack website
#   ./scripts/deploy.sh --stack cicd
#
# Prerequisites:
#   - AWS CLI configured with sufficient permissions
#   - config/deployment.json has the correct values (especially CloudFrontCertArn)
#   - 01-foundation must be deployed before 02-website
#   - Frontend pipeline.yaml must have removed its WebsiteBucketPolicy before 02-website is deployed

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${REPO_ROOT}/config/deployment.json"
REGION="${AWS_DEFAULT_REGION:-ca-central-1}"

# Parse config values using Python (stdlib only, no extra deps)
get() {
  python3 -c "import json,sys; d=json.load(open('${CONFIG}')); print(d['$1']['$2'])"
}

# Build --parameter-overrides string from a config section (exclude StackName)
params_for() {
  python3 - <<EOF
import json
with open('${CONFIG}') as f:
    section = json.load(f)['$1']
pairs = [f"{k}={v}" for k, v in section.items() if k not in ('StackName', '_comment')]
print(' '.join(pairs))
EOF
}

deploy_foundation() {
  echo "=== Deploying foundation stack ==="
  local stack_name
  stack_name="$(get foundation StackName)"
  aws cloudformation deploy \
    --template-file "${REPO_ROOT}/cloudformation/01-foundation.yaml" \
    --stack-name "${stack_name}" \
    --parameter-overrides $(params_for foundation) \
    --region "${REGION}"
  echo "Foundation stack deployed: ${stack_name}"
}

deploy_website() {
  echo "=== Deploying website stack ==="
  local stack_name
  stack_name="$(get website StackName)"
  aws cloudformation deploy \
    --template-file "${REPO_ROOT}/cloudformation/02-website.yaml" \
    --stack-name "${stack_name}" \
    --parameter-overrides $(params_for website) \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}"
  echo "Website stack deployed: ${stack_name}"
}

deploy_cicd() {
  echo "=== Deploying CI/CD pipeline stack ==="
  local stack_name
  stack_name="$(get cicd StackName)"
  aws cloudformation deploy \
    --template-file "${REPO_ROOT}/cloudformation/03-cicd-backend.yaml" \
    --stack-name "${stack_name}" \
    --parameter-overrides $(params_for cicd) \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${REGION}"
  echo "CI/CD stack deployed: ${stack_name}"
  echo ""
  echo "REMINDER: If the GitHub connection is Pending, activate it manually:"
  echo "  AWS Console → CodePipeline → Settings → Connections → Update pending connection"
}

TARGET="${1:-all}"
if [[ "${TARGET}" == "--stack" ]]; then
  TARGET="${2:-all}"
fi

case "${TARGET}" in
  foundation) deploy_foundation ;;
  website)    deploy_website ;;
  cicd)       deploy_cicd ;;
  all)
    deploy_foundation
    deploy_website
    deploy_cicd
    ;;
  *)
    echo "Unknown stack: ${TARGET}"
    echo "Usage: $0 [--stack foundation|website|cicd]"
    exit 1
    ;;
esac
