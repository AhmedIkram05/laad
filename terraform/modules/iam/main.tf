# LAAD IAM Module
# Creates 4 least-privilege IAM roles and the GitHub OIDC identity provider.

# ---------------------------------------------------------------------------
# GitHub OIDC Identity Provider
# ---------------------------------------------------------------------------

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

# ---------------------------------------------------------------------------
# Role 1: GitHub Actions OIDC Role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:ahmedikram05/laad:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-github-actions-role"
  description        = "IAM role assumed by GitHub Actions OIDC for LAAD CI/CD"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume.json

  tags = {
    Name        = "${var.project_name}-github-actions-role"
    Environment = var.environment
    Project     = var.project_name
  }
}

# --- GitHub Actions: ECR inline policy ---

data "aws_iam_policy_document" "github_actions_ecr" {
  statement {
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken"
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage"
    ]
    resources = [
      "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project_name}-app"
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_ecr" {
  name   = "${var.project_name}-github-ecr"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_ecr.json
}

# --- GitHub Actions: ECS inline policy ---

data "aws_iam_policy_document" "github_actions_ecs" {
  statement {
    effect = "Allow"
    actions = [
      "ecs:UpdateService",
      "ecs:DescribeServices",
      "ecs:RegisterTaskDefinition",
      "ecs:RunTask",
      "ecs:DescribeTaskDefinition",
      "ecs:DescribeTasks",
      "ecs:ListTaskDefinitions"
    ]
    resources = ["arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*:${var.project_name}-*"]
  }
}

resource "aws_iam_role_policy" "github_actions_ecs" {
  name   = "${var.project_name}-github-ecs"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_ecs.json
}

# --- GitHub Actions: S3 inline policy (frontend bucket) ---

data "aws_iam_policy_document" "github_actions_s3" {
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject"
    ]
    resources = [
      "arn:aws:s3:::${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}",
      "arn:aws:s3:::${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}/*"
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:ListBucket"
    ]
    resources = [
      "arn:aws:s3:::${var.project_name}-frontend-${data.aws_caller_identity.current.account_id}"
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_s3" {
  name   = "${var.project_name}-github-s3"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_s3.json
}

# --- GitHub Actions: CloudFront inline policy ---

data "aws_iam_policy_document" "github_actions_cloudfront" {
  statement {
    effect = "Allow"
    actions = [
      "cloudfront:CreateInvalidation",
      "cloudfront:GetDistribution",
      "cloudfront:ListDistributions"
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions_cloudfront" {
  name   = "${var.project_name}-github-cloudfront"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_cloudfront.json
}

# ---------------------------------------------------------------------------
# Role 2: ECS Task Execution Role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_execution_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_execution" {
  name               = "${var.project_name}-ecs-execution-role"
  description        = "ECS task execution role for LAAD services"
  assume_role_policy = data.aws_iam_policy_document.ecs_execution_assume.json

  tags = {
    Name        = "${var.project_name}-ecs-execution-role"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Attach the AWS managed ECS task execution policy
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Custom inline policy for Secrets Manager read on laad/* secrets
data "aws_iam_policy_document" "ecs_execution_secrets" {
  statement {
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/*"
    ]
  }
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name   = "${var.project_name}-ecs-execution-secrets"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_secrets.json
}

# ---------------------------------------------------------------------------
# Role 3: ECS Task Role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task" {
  name               = "${var.project_name}-ecs-task-role"
  description        = "ECS task role for LAAD services running in ECS"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json

  tags = {
    Name        = "${var.project_name}-ecs-task-role"
    Environment = var.environment
    Project     = var.project_name
  }
}

# --- ECS Task: SageMaker inference inline policy ---

data "aws_iam_policy_document" "ecs_task_sagemaker" {
  statement {
    effect = "Allow"
    actions = [
      "sagemaker:InvokeEndpoint"
    ]
    resources = [
      "arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.project_name}-*"
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_sagemaker" {
  name   = "${var.project_name}-ecs-task-sagemaker"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_sagemaker.json
}

# --- ECS Task: S3 GetObject on MLflow artifacts bucket ---

data "aws_iam_policy_document" "ecs_task_s3" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = [
      "arn:aws:s3:::${var.project_name}-mlflow-artifacts",
      "arn:aws:s3:::${var.project_name}-mlflow-artifacts/*"
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_s3" {
  name   = "${var.project_name}-ecs-task-s3"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_s3.json
}

# --- ECS Task: CloudWatch logs inline policy ---

data "aws_iam_policy_document" "ecs_task_logs" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/ecs/${var.project_name}-*"
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_logs" {
  name   = "${var.project_name}-ecs-task-logs"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_logs.json
}

# ---------------------------------------------------------------------------
# Role 4: SageMaker Execution Role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "sagemaker_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["sagemaker.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sagemaker_execution" {
  name               = "${var.project_name}-sagemaker-execution-role"
  description        = "SageMaker execution role for LAAD model endpoints"
  assume_role_policy = data.aws_iam_policy_document.sagemaker_assume.json

  tags = {
    Name        = "${var.project_name}-sagemaker-execution-role"
    Environment = var.environment
    Project     = var.project_name
  }
}

# --- SageMaker: Endpoint management inline policy ---

data "aws_iam_policy_document" "sagemaker_endpoints" {
  statement {
    effect = "Allow"
    actions = [
      "sagemaker:CreateEndpoint",
      "sagemaker:CreateEndpointConfig",
      "sagemaker:DescribeEndpoint",
      "sagemaker:InvokeEndpoint"
    ]
    resources = [
      "arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:endpoint-config/${var.project_name}-*",
      "arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.project_name}-*"
    ]
  }
}

resource "aws_iam_role_policy" "sagemaker_endpoints" {
  name   = "${var.project_name}-sagemaker-endpoints"
  role   = aws_iam_role.sagemaker_execution.id
  policy = data.aws_iam_policy_document.sagemaker_endpoints.json
}

# --- SageMaker: S3 GetObject on MLflow models path ---

data "aws_iam_policy_document" "sagemaker_s3" {
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject"
    ]
    resources = [
      "arn:aws:s3:::${var.project_name}-mlflow-artifacts/sagemaker-models/*"
    ]
  }
}

resource "aws_iam_role_policy" "sagemaker_s3" {
  name   = "${var.project_name}-sagemaker-s3"
  role   = aws_iam_role.sagemaker_execution.id
  policy = data.aws_iam_policy_document.sagemaker_s3.json
}

# --- SageMaker: ECR pull for XGBoost inference image ---

data "aws_iam_policy_document" "sagemaker_ecr" {
  statement {
    effect = "Allow"
    actions = [
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage"
    ]
    resources = [
      "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project_name}-sagemaker-xgboost"
    ]
  }
}

resource "aws_iam_role_policy" "sagemaker_ecr" {
  name   = "${var.project_name}-sagemaker-ecr"
  role   = aws_iam_role.sagemaker_execution.id
  policy = data.aws_iam_policy_document.sagemaker_ecr.json
}

# ---------------------------------------------------------------------------
# Data source: current AWS account ID
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}
