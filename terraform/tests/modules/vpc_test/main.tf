terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "project_name" { type = string }
variable "environment" { type = string }
variable "vpc_cidr" { type = string }
variable "availability_zones" { type = list(string) }
variable "aws_region" { type = string }

module "vpc" {
  source = "../../../modules/vpc"

  project_name       = var.project_name
  environment        = var.environment
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  aws_region         = var.aws_region
}

output "vpc_id" { value = module.vpc.vpc_id }
output "public_subnet_ids" { value = module.vpc.public_subnet_ids }
output "private_subnet_ids" { value = module.vpc.private_subnet_ids }
output "alb_sg_id" { value = module.vpc.alb_sg_id }
output "ecs_api_sg_id" { value = module.vpc.ecs_api_sg_id }
output "ecs_consumer_sg_id" { value = module.vpc.ecs_consumer_sg_id }
output "ecs_generator_sg_id" { value = module.vpc.ecs_generator_sg_id }
output "rds_sg_id" { value = module.vpc.rds_sg_id }
output "kafka_sg_id" { value = module.vpc.kafka_sg_id }
output "redis_sg_id" { value = module.vpc.redis_sg_id }
output "chromadb_sg_id" { value = module.vpc.chromadb_sg_id }
output "nat_gateway_id" { value = module.vpc.nat_gateway_id }
output "nat_gateway_public_ip" { value = module.vpc.nat_gateway_public_ip }
