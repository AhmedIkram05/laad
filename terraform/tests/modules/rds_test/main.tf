terraform {
  required_providers {
    aws    = { source = "hashicorp/aws" }
    random = { source = "hashicorp/random" }
  }
}

variable "project_name" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "rds_sg_id" { type = string }

module "rds" {
  source = "../../../modules/rds"

  project_name       = var.project_name
  environment        = var.environment
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  rds_sg_id          = var.rds_sg_id
}

output "rds_endpoint" { value = module.rds.rds_endpoint }
output "rds_port" { value = module.rds.rds_port }
output "rds_db_name" { value = module.rds.rds_db_name }
output "db_master_secret_arn" { value = module.rds.db_master_secret_arn }
output "rds_instance_id" { value = module.rds.rds_instance_id }
