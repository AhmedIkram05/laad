terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "project_name" { type = string }
variable "environment"  { type = string }
variable "aws_region"   { type = string }

module "iam" {
  source = "../../../modules/iam"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
}

output "github_oidc_provider_arn"    { value = module.iam.github_oidc_provider_arn }
output "github_actions_role_arn"     { value = module.iam.github_actions_role_arn }
output "ecs_execution_role_arn"      { value = module.iam.ecs_execution_role_arn }
output "ecs_task_role_arn"           { value = module.iam.ecs_task_role_arn }
output "sagemaker_execution_role_arn" { value = module.iam.sagemaker_execution_role_arn }
