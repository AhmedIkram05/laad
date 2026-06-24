terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "project_name" { type = string }
variable "environment" { type = string }
variable "alb_dns_name" { type = string }

module "frontend" {
  source = "../../../modules/frontend"

  project_name = var.project_name
  environment  = var.environment
  alb_dns_name = var.alb_dns_name
}

output "s3_bucket_name" { value = module.frontend.s3_bucket_name }
output "s3_bucket_arn" { value = module.frontend.s3_bucket_arn }
output "cloudfront_distribution_id" { value = module.frontend.cloudfront_distribution_id }
output "cloudfront_domain_name" { value = module.frontend.cloudfront_domain_name }
output "cloudfront_distribution_arn" { value = module.frontend.cloudfront_distribution_arn }
