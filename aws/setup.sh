#!/bin/bash
# ==================================================
# Quick Setup Script for AWS ECS + Qdrant
# ==================================================

set -e

echo "🚀 RAG Q&A System - AWS ECS Setup"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
export AWS_REGION=${AWS_REGION:-us-east-1}
export CLUSTER_NAME="rag-qa-cluster"
export SERVICE_NAME="rag-qa-service"
export ECR_REPO="rag-qa-system"

echo -e "${YELLOW}⚠  This script will create AWS resources that incur costs${NC}"
echo "   Estimated: ~\$53/month"
echo ""
read -p "Continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    echo "Aborted."
    exit 1
fi

# Get AWS Account ID
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✓${NC} AWS Account: $ACCOUNT_ID"
echo -e "${GREEN}✓${NC} Region: $AWS_REGION"
echo ""

# 1. ECR Repository
echo "📦 Creating ECR repository..."
aws ecr create-repository \
    --repository-name $ECR_REPO \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true \
    2>/dev/null && echo -e "${GREEN}✓${NC} ECR created" || echo -e "${YELLOW}!${NC} ECR already exists"

export ECR_URI="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO"

# 2. CloudWatch Logs
echo "📝 Creating CloudWatch log group..."
aws logs create-log-group \
    --log-group-name /ecs/rag-qa-system \
    --region $AWS_REGION \
    2>/dev/null && echo -e "${GREEN}✓${NC} Log group created" || echo -e "${YELLOW}!${NC} Log group already exists"

# 3. ECS Cluster
echo "🏗️  Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name $CLUSTER_NAME \
    --region $AWS_REGION \
    --capacity-providers FARGATE \
    2>/dev/null && echo -e "${GREEN}✓${NC} Cluster created" || echo -e "${YELLOW}!${NC} Cluster already exists"

# 4. Secrets (interactive)
echo ""
echo "🔐 Setting up secrets..."
echo -e "${YELLOW}Please enter your API keys:${NC}"

read -p "OpenAI API Key: " -s OPENAI_KEY
echo ""
read -p "LangSmith API Key: " -s LANGSMITH_KEY
echo ""

aws secretsmanager create-secret \
    --name rag-qa/openai-api-key \
    --secret-string "$OPENAI_KEY" \
    --region $AWS_REGION \
    2>/dev/null && echo -e "${GREEN}✓${NC} OpenAI secret created" || \
    (aws secretsmanager update-secret \
        --secret-id rag-qa/openai-api-key \
        --secret-string "$OPENAI_KEY" \
        --region $AWS_REGION && echo -e "${GREEN}✓${NC} OpenAI secret updated")

aws secretsmanager create-secret \
    --name rag-qa/langsmith-api-key \
    --secret-string "$LANGSMITH_KEY" \
    --region $AWS_REGION \
    2>/dev/null && echo -e "${GREEN}✓${NC} LangSmith secret created" || \
    (aws secretsmanager update-secret \
        --secret-id rag-qa/langsmith-api-key \
        --secret-string "$LANGSMITH_KEY" \
        --region $AWS_REGION && echo -e "${GREEN}✓${NC} LangSmith secret updated")

# 5. Get VPC info
echo ""
echo "🌐 Getting VPC information..."
export VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text \
    --region $AWS_REGION)
echo -e "${GREEN}✓${NC} VPC: $VPC_ID"

export SUBNETS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[*].SubnetId' \
    --output text \
    --region $AWS_REGION)

# 6. EFS for Qdrant storage
echo "💾 Creating EFS file system..."
export EFS_ID=$(aws efs create-file-system \
    --performance-mode generalPurpose \
    --encrypted \
    --tags Key=Name,Value=rag-qa-qdrant \
    --region $AWS_REGION \
    --query 'FileSystemId' \
    --output text 2>/dev/null)

if [ -z "$EFS_ID" ]; then
    export EFS_ID=$(aws efs describe-file-systems \
        --query "FileSystems[?Tags[?Key=='Name' && Value=='rag-qa-qdrant']].FileSystemId" \
        --output text \
        --region $AWS_REGION)
    echo -e "${YELLOW}!${NC} Using existing EFS: $EFS_ID"
else
    echo -e "${GREEN}✓${NC} EFS created: $EFS_ID"
    echo "   Waiting for EFS to be available..."
    sleep 15
fi

# 7. Security groups
echo "🔒 Creating security groups..."

# EFS Security Group
export EFS_SG_ID=$(aws ec2 create-security-group \
    --group-name rag-qa-efs-sg \
    --description "RAG QA EFS" \
    --vpc-id $VPC_ID \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=rag-qa-efs-sg" \
        --query 'SecurityGroups[0].GroupId' \
        --output text \
        --region $AWS_REGION)

aws ec2 authorize-security-group-ingress \
    --group-id $EFS_SG_ID \
    --protocol tcp \
    --port 2049 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION 2>/dev/null || true

# Create EFS mount targets
for SUBNET in $SUBNETS; do
    aws efs create-mount-target \
        --file-system-id $EFS_ID \
        --subnet-id $SUBNET \
        --security-groups $EFS_SG_ID \
        --region $AWS_REGION 2>/dev/null || true
done

# ALB Security Group
export ALB_SG_ID=$(aws ec2 create-security-group \
    --group-name rag-qa-alb-sg \
    --description "RAG QA ALB" \
    --vpc-id $VPC_ID \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=rag-qa-alb-sg" \
        --query 'SecurityGroups[0].GroupId' \
        --output text \
        --region $AWS_REGION)

aws ec2 authorize-security-group-ingress \
    --group-id $ALB_SG_ID \
    --protocol tcp \
    --port 80 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION 2>/dev/null || true

# ECS Security Group
export ECS_SG_ID=$(aws ec2 create-security-group \
    --group-name rag-qa-ecs-sg \
    --description "RAG QA ECS" \
    --vpc-id $VPC_ID \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=rag-qa-ecs-sg" \
        --query 'SecurityGroups[0].GroupId' \
        --output text \
        --region $AWS_REGION)

aws ec2 authorize-security-group-ingress \
    --group-id $ECS_SG_ID \
    --protocol tcp \
    --port 8000 \
    --source-group $ALB_SG_ID \
    --region $AWS_REGION 2>/dev/null || true

aws ec2 authorize-security-group-ingress \
    --group-id $ECS_SG_ID \
    --protocol tcp \
    --port 6333 \
    --source-group $ECS_SG_ID \
    --region $AWS_REGION 2>/dev/null || true

echo -e "${GREEN}✓${NC} Security groups configured"

# 8. IAM Roles
echo "👤 Creating IAM roles..."

cat > /tmp/ecs-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json \
    2>/dev/null || echo "Execution role exists"

aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy \
    2>/dev/null || true

cat > /tmp/ecs-exec-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": ["arn:aws:secretsmanager:$AWS_REGION:$ACCOUNT_ID:secret:rag-qa/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["elasticfilesystem:ClientMount", "elasticfilesystem:ClientWrite"],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-name AdditionalPerms \
    --policy-document file:///tmp/ecs-exec-policy.json

aws iam create-role \
    --role-name ecsTaskRole \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json \
    2>/dev/null || echo "Task role exists"

echo -e "${GREEN}✓${NC} IAM roles configured"

# 9. Update task definition
echo "📝 Updating task definition..."
cp aws/ecs-task-definition.json /tmp/ecs-task-def-updated.json
sed -i '' "s/YOUR_ACCOUNT_ID/$ACCOUNT_ID/g" /tmp/ecs-task-def-updated.json
sed -i '' "s/fs-XXXXXXXXX/$EFS_ID/g" /tmp/ecs-task-def-updated.json
sed -i '' "s|YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/rag-qa-system:latest|$ECR_URI:latest|g" /tmp/ecs-task-def-updated.json

echo ""
echo "======================================"
echo -e "${GREEN}✅ Infrastructure Setup Complete!${NC}"
echo "======================================"
echo ""
echo "📋 Resources Created:"
echo "   • ECR Repository: $ECR_URI"
echo "   • ECS Cluster: $CLUSTER_NAME"
echo "   • EFS File System: $EFS_ID"
echo "   • Security Groups: ALB ($ALB_SG_ID), ECS ($ECS_SG_ID)"
echo ""
echo "🔧 Next Steps:"
echo ""
echo "1️⃣  Build and push your Docker image:"
echo "   aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI"
echo "   docker build -t $ECR_REPO ."
echo "   docker tag $ECR_REPO:latest $ECR_URI:latest"
echo "   docker push $ECR_URI:latest"
echo ""
echo "2️⃣  Create ALB and ECS service (see DEPLOYMENT.md steps 8-10)"
echo ""
echo "3️⃣  Or use GitHub Actions to deploy automatically"
echo ""
echo "📚 See aws/DEPLOYMENT.md for complete instructions"
echo ""

# Save environment variables
cat > /tmp/rag-qa-env.sh <<EOF
export AWS_REGION=$AWS_REGION
export ACCOUNT_ID=$ACCOUNT_ID
export VPC_ID=$VPC_ID
export EFS_ID=$EFS_ID
export ECS_SG_ID=$ECS_SG_ID
export ALB_SG_ID=$ALB_SG_ID
export ECR_URI=$ECR_URI
export SUBNETS="$SUBNETS"
EOF

echo "💾 Environment variables saved to /tmp/rag-qa-env.sh"
echo "   Run: source /tmp/rag-qa-env.sh"
