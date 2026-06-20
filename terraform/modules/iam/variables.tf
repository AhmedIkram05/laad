# LAAD IAM Module Variables

variable "project_name" {
  description = "Project name used for IAM resource naming"
  type        = string
  default     = "laad"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"
}

variable "aws_region" {
  description = "AWS region for ARN construction"
  type        = string
  default     = "eu-west-2"
}
