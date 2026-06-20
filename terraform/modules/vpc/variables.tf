# LAAD VPC Module Variables

variable "vpc_cidr" {
  description = "CIDR block for the LAAD VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "laad"
}

variable "availability_zones" {
  description = "List of availability zones for subnet placement"
  type        = list(string)
  default     = ["eu-west-2a", "eu-west-2b"]
}

variable "aws_region" {
  description = "AWS region (used for VPC Gateway Endpoint service names)"
  type        = string
  default     = "eu-west-2"
}
