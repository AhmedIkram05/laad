# Kafka Module Variables

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "laad"
}

variable "environment" {
  description = "Environment tag for resource identification"
  type        = string
  default     = "production"
}

variable "public_subnet_id" {
  description = "The first public subnet ID from the VPC module for the Kafka EC2 instance placement"
  type        = string
}

variable "kafka_sg_id" {
  description = "Pre-existing Kafka security group ID from the VPC module"
  type        = string
}


