# LAAD Monitoring Module
# SNS budget alerts, AWS Budgets, and CloudWatch metric alarms.
# Dashboards for container metrics live in the ECS module -- not here.

# ---------------------------------------------------------------------------
# SNS Topic for Budget & Alarm Notifications
# ---------------------------------------------------------------------------

# checkov:skip=CKV_AWS_26:SNS topic encryption not required for dev budget alerts
resource "aws_sns_topic" "budget_alerts" {
  name = "laad-budget-alerts"

  tags = {
    Name        = "laad-budget-alerts"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# SNS Topic Policy -- allow AWS Budgets to publish
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "budget_sns" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }

    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.budget_alerts.arn]
  }
}

resource "aws_sns_topic_policy" "budget_alerts" {
  arn    = aws_sns_topic.budget_alerts.arn
  policy = data.aws_iam_policy_document.budget_sns.json
}

# ---------------------------------------------------------------------------
# CloudWatch Alarm -- RDS CPU Credit Balance
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "rds_cpu_credit" {
  alarm_name          = "laad-rds-cpu-credit-balance"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUCreditBalance"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 20
  alarm_description   = "RDS CPU credit balance below 20"
  alarm_actions       = [aws_sns_topic.budget_alerts.arn]

  dimensions = {
    DBInstanceIdentifier = "laad-postgres"
  }

  tags = {
    Name        = "laad-rds-cpu-credit-balance"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Alarm -- SageMaker Invocation Latency
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "sagemaker_invocation" {
  alarm_name          = "laad-sagemaker-invocation-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ModelLatency"
  namespace           = "AWS/SageMaker"
  period              = 300
  statistic           = "Average"
  threshold           = 5000
  alarm_description   = "SageMaker endpoint invocation latency > 5s"
  alarm_actions       = [aws_sns_topic.budget_alerts.arn]

  dimensions = {
    EndpointName = "laad-anomaly-detection"
  }

  tags = {
    Name        = "laad-sagemaker-invocation-latency"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ---------------------------------------------------------------------------
# CloudWatch Alarm -- ECS API Service Down
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "ecs_api_down" {
  alarm_name          = "laad-ecs-api-service-down"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 1
  alarm_description   = "API ECS service may be down - CPU below 1% for 15 minutes"
  alarm_actions       = [aws_sns_topic.budget_alerts.arn]

  dimensions = {
    ClusterName = "laad-cluster"
    ServiceName = "laad-api"
  }

  tags = {
    Name        = "laad-ecs-api-service-down"
    Environment = var.environment
    Project     = var.project_name
  }
}
