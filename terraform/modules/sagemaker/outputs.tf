# SageMaker Module Outputs

output "sagemaker_enabled" {
  description = "Whether SageMaker is enabled"
  value       = var.sagemaker_enabled
}

output "endpoint_name" {
  description = "Name of the SageMaker endpoint"
  value       = var.sagemaker_enabled ? aws_sagemaker_endpoint.champion[0].name : null
}

output "endpoint_arn" {
  description = "ARN of the SageMaker endpoint"
  value       = var.sagemaker_enabled ? aws_sagemaker_endpoint.champion[0].arn : null
}

output "model_name" {
  description = "Name of the SageMaker model"
  value       = var.sagemaker_enabled ? aws_sagemaker_model.champion[0].name : null
}
