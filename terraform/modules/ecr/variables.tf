# ECR Module Variables

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "laad"
}

variable "environment" {
  description = "Deployment environment (production, staging)"
  type        = string
  default     = "production"
}
