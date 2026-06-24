terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "project_name" { type = string }
variable "environment" { type = string }

module "ecr" {
  source = "../../../modules/ecr"

  project_name = var.project_name
  environment  = var.environment
}

output "repository_url" { value = module.ecr.repository_url }
output "repository_arn" { value = module.ecr.repository_arn }
