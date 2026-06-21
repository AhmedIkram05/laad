# LAAD RDS Module Variables

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "laad"
}

variable "environment" {
  description = "Environment tag"
  type        = string
  default     = "production"
}

variable "vpc_id" {
  description = "VPC ID for the RDS subnet group"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for the DB subnet group"
  type        = list(string)
}

variable "rds_sg_id" {
  description = "Pre-created RDS security group ID from vpc module"
  type        = string
}
