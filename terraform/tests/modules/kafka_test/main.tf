terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

variable "project_name" { type = string }
variable "environment" { type = string }
variable "public_subnet_id" { type = string }
variable "kafka_sg_id" { type = string }

module "kafka" {
  source = "../../../modules/kafka"

  project_name     = var.project_name
  environment      = var.environment
  public_subnet_id = var.public_subnet_id
  kafka_sg_id      = var.kafka_sg_id
}

output "kafka_private_ip" { value = module.kafka.kafka_private_ip }
output "kafka_public_ip" { value = module.kafka.kafka_public_ip }
output "kafka_eip_id" { value = module.kafka.kafka_eip_id }
output "kafka_instance_id" { value = module.kafka.kafka_instance_id }
output "kafka_sg_id" { value = module.kafka.kafka_sg_id }
