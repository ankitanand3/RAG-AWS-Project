#!/bin/bash
# ==================================================
# Create AWS App Runner ECR Access Role
# ==================================================

set -e

echo "🔧 Creating App Runner ECR Access Role"
echo "======================================"
echo ""

AWS_REGION=${AWS_REGION:-us-east-1}

# Check if role already exists
if aws iam get-role --role-name AppRunnerECRAccessRole 2>/dev/null; then
    echo "✅ Role already exists!"
    ROLE_ARN=$(aws iam get-role --role-name AppRunnerECRAccessRole --query 'Role.Arn' --output text)
    echo ""
    echo "📋 Your APP_RUNNER_ECR_ACCESS_ROLE_ARN:"
    echo "$ROLE_ARN"
    echo ""
    echo "Add this to your GitHub repository secrets as:"
    echo "APP_RUNNER_ECR_ACCESS_ROLE_ARN=$ROLE_ARN"
    exit 0
fi

# Create trust policy for App Runner
cat > /tmp/app-runner-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "build.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the IAM role
echo "Creating IAM role..."
aws iam create-role \
    --role-name AppRunnerECRAccessRole \
    --assume-role-policy-document file:///tmp/app-runner-trust-policy.json \
    --description "Allows App Runner to access ECR"

echo "✓ Role created"

# Attach AWS managed policy for ECR access
echo "Attaching ECR access policy..."
aws iam attach-role-policy \
    --role-name AppRunnerECRAccessRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess

echo "✓ Policy attached"

# Wait a moment for the role to be available
sleep 3

# Get the role ARN
ROLE_ARN=$(aws iam get-role --role-name AppRunnerECRAccessRole --query 'Role.Arn' --output text)

echo ""
echo "======================================"
echo "✅ Success!"
echo "======================================"
echo ""
echo "📋 Your APP_RUNNER_ECR_ACCESS_ROLE_ARN:"
echo "$ROLE_ARN"
echo ""
echo "🔐 Add this to your GitHub repository secrets:"
echo ""
echo "1. Go to: https://github.com/YOUR_USERNAME/RAG-AWS-Project/settings/secrets/actions"
echo "2. Click 'New repository secret'"
echo "3. Name: APP_RUNNER_ECR_ACCESS_ROLE_ARN"
echo "4. Value: $ROLE_ARN"
echo ""
