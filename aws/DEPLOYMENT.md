# AWS ECS Deployment Guide
## RAG Q&A System with Qdrant

This guide will help you deploy your application to AWS ECS with Qdrant running in the same task.

## Architecture

- **ECS Fargate** - Runs both your app and Qdrant containers
- **EFS** - Persistent storage for Qdrant data
- **Application Load Balancer** - Routes traffic to your app
- **Secrets Manager** - Stores API keys securely

---

## Prerequisites

1. AWS CLI installed and configured
2. AWS Account with appropriate permissions
3. GitHub repository secrets configured (we'll set these up)

---

## Step-by-Step Setup

### 1. Create ECR Repository

```bash
# Set your region
export AWS_REGION=us-east-1

# Create ECR repository for your Docker images
aws ecr create-repository \
    --repository-name rag-qa-system \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true
```

**Note the repository URI** - you'll need it later.

---

### 2. Create ECS Cluster

```bash
aws ecs create-cluster \
    --cluster-name rag-qa-cluster \
    --region $AWS_REGION \
    --capacity-providers FARGATE FARGATE_SPOT \
    --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1
```

---

### 3. Create CloudWatch Log Group

```bash
aws logs create-log-group \
    --log-group-name /ecs/rag-qa-system \
    --region $AWS_REGION
```

---

### 4. Set Up Secrets in AWS Secrets Manager

```bash
# Get your AWS Account ID
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Account ID: $ACCOUNT_ID"

# Create secrets for API keys
aws secretsmanager create-secret \
    --name rag-qa/openai-api-key \
    --secret-string "YOUR_OPENAI_API_KEY_HERE" \
    --region $AWS_REGION

aws secretsmanager create-secret \
    --name rag-qa/langsmith-api-key \
    --secret-string "YOUR_LANGSMITH_API_KEY_HERE" \
    --region $AWS_REGION
```

---

### 5. Create EFS File System for Qdrant Data

```bash
# Get your default VPC ID
export VPC_ID=$(aws ec2 describe-vpcs \
    --filters "Name=isDefault,Values=true" \
    --query 'Vpcs[0].VpcId' \
    --output text \
    --region $AWS_REGION)
echo "VPC ID: $VPC_ID"

# Create EFS file system
export EFS_ID=$(aws efs create-file-system \
    --performance-mode generalPurpose \
    --encrypted \
    --tags Key=Name,Value=rag-qa-qdrant-storage \
    --region $AWS_REGION \
    --query 'FileSystemId' \
    --output text)
echo "EFS ID: $EFS_ID"

# Wait for EFS to be available
echo "Waiting for EFS to become available..."
sleep 30

# Create security group for EFS
export EFS_SG_ID=$(aws ec2 create-security-group \
    --group-name rag-qa-efs-sg \
    --description "Security group for RAG QA EFS" \
    --vpc-id $VPC_ID \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text)

# Allow NFS traffic (port 2049) from anywhere in VPC
aws ec2 authorize-security-group-ingress \
    --group-id $EFS_SG_ID \
    --protocol tcp \
    --port 2049 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION

# Create mount targets in all subnets
for SUBNET in $(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[*].SubnetId' \
    --output text \
    --region $AWS_REGION); do

    echo "Creating mount target in subnet: $SUBNET"
    aws efs create-mount-target \
        --file-system-id $EFS_ID \
        --subnet-id $SUBNET \
        --security-groups $EFS_SG_ID \
        --region $AWS_REGION || echo "Mount target may already exist"
done
```

---

### 6. Create IAM Roles

#### A. ECS Task Execution Role

```bash
# Create trust policy
cat > /tmp/ecs-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create the role
aws iam create-role \
    --role-name ecsTaskExecutionRole \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json

# Attach AWS managed policy
aws iam attach-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Add Secrets Manager and EFS permissions
cat > /tmp/ecs-execution-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:$AWS_REGION:$ACCOUNT_ID:secret:rag-qa/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "elasticfilesystem:ClientMount",
        "elasticfilesystem:ClientWrite"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
    --role-name ecsTaskExecutionRole \
    --policy-name AdditionalPermissions \
    --policy-document file:///tmp/ecs-execution-policy.json
```

#### B. ECS Task Role (for the application)

```bash
aws iam create-role \
    --role-name ecsTaskRole \
    --assume-role-policy-document file:///tmp/ecs-trust-policy.json
```

---

### 7. Update Task Definition

Update the `aws/ecs-task-definition.json` file with your values:

```bash
# Replace placeholders in task definition
sed -i '' "s/YOUR_ACCOUNT_ID/$ACCOUNT_ID/g" aws/ecs-task-definition.json
sed -i '' "s/fs-XXXXXXXXX/$EFS_ID/g" aws/ecs-task-definition.json

echo "✓ Task definition updated"
```

---

### 8. Create Application Load Balancer

```bash
# Get subnets
export SUBNETS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[*].SubnetId' \
    --output text \
    --region $AWS_REGION | tr '\t' ',')

# Create security group for ALB
export ALB_SG_ID=$(aws ec2 create-security-group \
    --group-name rag-qa-alb-sg \
    --description "Security group for RAG QA ALB" \
    --vpc-id $VPC_ID \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text)

# Allow HTTP traffic
aws ec2 authorize-security-group-ingress \
    --group-id $ALB_SG_ID \
    --protocol tcp \
    --port 80 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION

# Create ALB
export ALB_ARN=$(aws elbv2 create-load-balancer \
    --name rag-qa-alb \
    --subnets ${SUBNETS//,/ } \
    --security-groups $ALB_SG_ID \
    --region $AWS_REGION \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text)

echo "ALB ARN: $ALB_ARN"

# Get ALB DNS name
export ALB_DNS=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns $ALB_ARN \
    --query 'LoadBalancers[0].DNSName' \
    --output text \
    --region $AWS_REGION)

echo "ALB DNS: $ALB_DNS"

# Create target group
export TG_ARN=$(aws elbv2 create-target-group \
    --name rag-qa-tg \
    --protocol HTTP \
    --port 8000 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path /health \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 5 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --region $AWS_REGION \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text)

echo "Target Group ARN: $TG_ARN"

# Create listener
aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn=$TG_ARN \
    --region $AWS_REGION
```

---

### 9. Create Security Group for ECS Tasks

```bash
export ECS_SG_ID=$(aws ec2 create-security-group \
    --group-name rag-qa-ecs-sg \
    --description "Security group for RAG QA ECS tasks" \
    --vpc-id $VPC_ID \
    --region $AWS_REGION \
    --query 'GroupId' \
    --output text)

# Allow traffic from ALB
aws ec2 authorize-security-group-ingress \
    --group-id $ECS_SG_ID \
    --protocol tcp \
    --port 8000 \
    --source-group $ALB_SG_ID \
    --region $AWS_REGION

# Allow traffic from within security group (for Qdrant)
aws ec2 authorize-security-group-ingress \
    --group-id $ECS_SG_ID \
    --protocol tcp \
    --port 6333 \
    --source-group $ECS_SG_ID \
    --region $AWS_REGION

echo "ECS Security Group: $ECS_SG_ID"
```

---

### 10. Register Task Definition & Create ECS Service

```bash
# Register task definition
aws ecs register-task-definition \
    --cli-input-json file://aws/ecs-task-definition.json \
    --region $AWS_REGION

# Create ECS service
aws ecs create-service \
    --cluster rag-qa-cluster \
    --service-name rag-qa-service \
    --task-definition rag-qa-system \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNETS//,/\,}],securityGroups=[$ECS_SG_ID],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=$TG_ARN,containerName=rag-api,containerPort=8000" \
    --region $AWS_REGION

echo "✓ ECS Service created!"
```

---

### 11. Configure GitHub Secrets

Add these secrets to your GitHub repository:

```
AWS_ACCESS_KEY_ID=<your-access-key>
AWS_SECRET_ACCESS_KEY=<your-secret-key>
```

The other secrets (OpenAI, LangSmith) are already in AWS Secrets Manager.

---

## Deploy via GitHub Actions

Once everything is set up, just push to main:

```bash
git push origin main
```

The GitHub Actions workflow will:
1. Build your Docker image
2. Push to ECR
3. Deploy to ECS

---

## Access Your Application

After deployment completes, access your app at:

```
http://<ALB_DNS_NAME>
```

You can find the ALB DNS name with:

```bash
echo $ALB_DNS
```

Or:

```bash
aws elbv2 describe-load-balancers \
    --names rag-qa-alb \
    --query 'LoadBalancers[0].DNSName' \
    --output text \
    --region $AWS_REGION
```

---

## Monitoring

- **CloudWatch Logs**: `/ecs/rag-qa-system`
- **ECS Console**: View service status and tasks
- **ALB Target Health**: Check if targets are healthy

---

## Cleanup

To delete all resources:

```bash
# Delete ECS service
aws ecs update-service --cluster rag-qa-cluster --service rag-qa-service --desired-count 0 --region $AWS_REGION
aws ecs delete-service --cluster rag-qa-cluster --service rag-qa-service --region $AWS_REGION

# Delete ALB
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN --region $AWS_REGION
aws elbv2 delete-target-group --target-group-arn $TG_ARN --region $AWS_REGION

# Delete ECS cluster
aws ecs delete-cluster --cluster rag-qa-cluster --region $AWS_REGION

# Delete EFS
aws efs delete-file-system --file-system-id $EFS_ID --region $AWS_REGION

# Delete ECR repository
aws ecr delete-repository --repository-name rag-qa-system --force --region $AWS_REGION

# Delete secrets
aws secretsmanager delete-secret --secret-id rag-qa/openai-api-key --force-delete-without-recovery --region $AWS_REGION
aws secretsmanager delete-secret --secret-id rag-qa/langsmith-api-key --force-delete-without-recovery --region $AWS_REGION
```

---

## Troubleshooting

### Service won't start
- Check CloudWatch Logs at `/ecs/rag-qa-system`
- Verify secrets exist in Secrets Manager
- Check ECS task definition is valid

### Can't access via ALB
- Verify security groups allow traffic
- Check target group health
- Ensure ECS tasks are running

### Qdrant data not persisting
- Verify EFS mount targets are created
- Check EFS security group allows NFS traffic
- Look for mount errors in CloudWatch Logs

---

## Cost Estimate

**Monthly costs (approximate):**
- ECS Fargate (1 task, 1 vCPU, 2GB RAM): ~$30
- EFS (10 GB): ~$3
- ALB: ~$20
- Data transfer: Variable
- **Total: ~$53/month** (plus OpenAI API usage)

You can reduce costs by:
- Using Fargate Spot instances
- Stopping the service when not in use
- Using smaller task sizes
