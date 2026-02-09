#!/bin/bash
# ==================================================
# AWS Cleanup Script - Delete All Resources
# ==================================================

set -e

AWS_REGION=us-east-1
ACCOUNT_ID=050752648627
EFS_ID=fs-0b633ff96e713b3fb
VPC_ID=vpc-068c7b0bf2045df1f

echo "🧹 Cleaning up AWS resources..."
echo "======================================"

# 1. Delete EFS Mount Targets first
echo "Deleting EFS mount targets..."
for MT_ID in $(aws efs describe-mount-targets --file-system-id $EFS_ID --region $AWS_REGION --query 'MountTargets[*].MountTargetId' --output text); do
    echo "  Deleting mount target: $MT_ID"
    aws efs delete-mount-target --mount-target-id $MT_ID --region $AWS_REGION
done
echo "Waiting for mount targets to be deleted..."
sleep 30

# 2. Delete EFS File System
echo "Deleting EFS file system..."
aws efs delete-file-system --file-system-id $EFS_ID --region $AWS_REGION || echo "EFS might already be deleted"

# 3. Delete ECS Cluster
echo "Deleting ECS cluster..."
aws ecs delete-cluster --cluster rag-qa-cluster --region $AWS_REGION || echo "Cluster might already be deleted"

# 4. Delete ECR Repository
echo "Deleting ECR repository..."
aws ecr delete-repository --repository-name rag-qa-system --region $AWS_REGION --force || echo "ECR might already be deleted"

# 5. Delete Security Groups
echo "Deleting security groups..."
aws ec2 delete-security-group --group-id sg-0d1023ae59a6d9450 --region $AWS_REGION 2>/dev/null || echo "ECS SG might already be deleted"
aws ec2 delete-security-group --group-id sg-03b3295062320512b --region $AWS_REGION 2>/dev/null || echo "ALB SG might already be deleted"
aws ec2 delete-security-group --group-id sg-0726a58e919c1a125 --region $AWS_REGION 2>/dev/null || echo "EFS SG might already be deleted"

# 6. Delete Secrets
echo "Deleting secrets..."
aws secretsmanager delete-secret --secret-id rag-qa/openai-api-key --force-delete-without-recovery --region $AWS_REGION 2>/dev/null || echo "OpenAI secret might already be deleted"
aws secretsmanager delete-secret --secret-id rag-qa/langsmith-api-key --force-delete-without-recovery --region $AWS_REGION 2>/dev/null || echo "LangSmith secret might already be deleted"

# 7. Delete IAM Roles
echo "Deleting IAM roles..."
aws iam detach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy 2>/dev/null || true
aws iam delete-role-policy --role-name ecsTaskExecutionRole --policy-name AdditionalPerms 2>/dev/null || true
aws iam delete-role --role-name ecsTaskExecutionRole 2>/dev/null || echo "Execution role might already be deleted"
aws iam delete-role --role-name ecsTaskRole 2>/dev/null || echo "Task role might already be deleted"

# 8. Delete CloudWatch Log Group
echo "Deleting CloudWatch log group..."
aws logs delete-log-group --log-group-name /ecs/rag-qa-system --region $AWS_REGION 2>/dev/null || echo "Log group might already be deleted"

# 9. Delete App Runner Role (if exists)
echo "Deleting App Runner role..."
aws iam detach-role-policy --role-name AppRunnerECRAccessRole --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess 2>/dev/null || true
aws iam delete-role --role-name AppRunnerECRAccessRole 2>/dev/null || echo "App Runner role might already be deleted"

echo ""
echo "======================================"
echo "✅ Cleanup Complete!"
echo "======================================"
echo ""
echo "All AWS resources have been deleted."
echo "Final cost: ~\$0.50 for the test period"
echo ""
echo "You can verify in AWS Console:"
echo "- ECR: https://console.aws.amazon.com/ecr/"
echo "- ECS: https://console.aws.amazon.com/ecs/"
echo "- EFS: https://console.aws.amazon.com/efs/"
echo ""
