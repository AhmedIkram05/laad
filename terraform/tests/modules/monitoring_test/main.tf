terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "project_name" { type = string }
variable "environment" { type = string }

module "monitoring" {
  source = "../../../modules/monitoring"

  project_name = var.project_name
  environment  = var.environment
}

output "budget_sns_topic_arn" { value = module.monitoring.budget_sns_topic_arn }
output "rds_cpu_alarm_arn" { value = module.monitoring.rds_cpu_alarm_arn }
