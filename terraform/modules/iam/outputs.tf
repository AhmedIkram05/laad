# LAAD IAM Module Outputs

output "github_oidc_provider_arn" {
  description = "ARN of the GitHub OIDC identity provider"
  value       = data.aws_iam_openid_connect_provider.github.arn
}

output "github_actions_role_arn" {
  description = "ARN of the GitHub Actions OIDC IAM role — store this as a GitHub secret"
  value       = aws_iam_role.github_actions.arn
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task.arn
}

output "sagemaker_execution_role_arn" {
  description = "ARN of the SageMaker execution role"
  value       = aws_iam_role.sagemaker_execution.arn
}
