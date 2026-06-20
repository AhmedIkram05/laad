# ---------------------------------------------------------------------------
# Variables — Secrets Manager module
# ---------------------------------------------------------------------------

variable "project_name" {
  description = "Project name used as a prefix for secret names"
  type        = string
  default     = "laad"
}

variable "environment" {
  description = "Deployment environment (e.g. production, staging)"
  type        = string
  default     = "production"
}
