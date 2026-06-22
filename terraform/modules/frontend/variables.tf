# Frontend Module Variables

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

variable "alb_dns_name" {
  description = "DNS name of the ALB for proxying API requests"
  type        = string
}
