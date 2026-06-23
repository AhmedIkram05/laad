# Root Terraform Outputs

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.ecs.alb_dns_name
}

output "ecr_repository_url" {
  description = "URL of the ECR repository"
  value       = module.ecr.repository_url
}

output "sagemaker_endpoint_name" {
  description = "Name of the SageMaker endpoint (null if sagemaker_enabled is false)"
  value       = var.sagemaker_enabled ? module.sagemaker[0].endpoint_name : null
}

output "sagemaker_endpoint_arn" {
  description = "ARN of the SageMaker endpoint (null if sagemaker_enabled is false)"
  value       = var.sagemaker_enabled ? module.sagemaker[0].endpoint_arn : null
}

output "sagemaker_model_name" {
  description = "Name of the SageMaker model (null if sagemaker_enabled is false)"
  value       = var.sagemaker_enabled ? module.sagemaker[0].model_name : null
}
