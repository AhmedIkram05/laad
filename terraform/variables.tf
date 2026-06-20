# LAAD Terraform Variables

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "eu-west-2"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "laad"
}

variable "vpc_cidr" {
  description = "CIDR block for LAAD VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for subnets"
  type        = list(string)
  default     = ["eu-west-2a", "eu-west-2b"]
}

variable "sagemaker_enabled" {
  description = "Enable SageMaker endpoint creation (gated — requires model upload first)"
  type        = bool
  default     = false
}
