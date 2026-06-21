# Monitoring Module Outputs

output "budget_sns_topic_arn" {
  description = "ARN of the SNS topic for budget alerts"
  value       = aws_sns_topic.budget_alerts.arn
}

output "rds_cpu_alarm_arn" {
  description = "ARN of the RDS CPU credit balance alarm"
  value       = aws_cloudwatch_metric_alarm.rds_cpu_credit.arn
}
